"""
UCKhabar — FastAPI Application Entry Point

Auth-protected endpoints (require Firebase Google Sign-In token):
  POST  /onboarding/start             — begin AI onboarding chat
  POST  /onboarding/message           — continue onboarding chat
  GET   /feed/me                      — get my curated feed
  POST  /feed/refresh                 — manually refresh my feed (test)

Public endpoints:
  GET   /health                       — health check

Admin/test endpoints (no auth — restrict these in production):
  POST  /admin/rss/poll               — manually trigger RSS poll
  POST  /admin/scoring/run            — manually trigger scoring for all users

Background jobs (APScheduler):
  Every 30 min  → rss_polling_job()
  Every 2 hours → scoring_job()
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from agents.onboarding_agent import OnboardingAgent
from agents.scoring_agent import ScoringAgent
from config import settings
from models.schemas import (
    CompleteOnboardingRequest,
    CompleteOnboardingResponse,
    SendMessageRequest,
    SendMessageResponse,
    StartOnboardingRequest,
    StartOnboardingResponse,
    UserFeed,
    UserProfile,
)
from services.auth_service import get_current_user
from services.db_service import DatabaseService
from services.rss_service import fetch_all_feeds
from services.topic_taxonomy import build_topics_from_selections, get_keywords_for_profile

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger("uckhabar.main")

# ---------------------------------------------------------------------------
# Service singletons
# ---------------------------------------------------------------------------

onboarding_agent = OnboardingAgent(
    project_id=settings.GCP_PROJECT_ID,
    location=settings.GCP_REGION,
    model_name=settings.GEMINI_MODEL,
)
scoring_agent = ScoringAgent(
    project_id=settings.GCP_PROJECT_ID,
    location=settings.GCP_REGION,
    model_name=settings.GEMINI_MODEL,
)
db = DatabaseService(project_id=settings.GCP_PROJECT_ID)
scheduler = AsyncIOScheduler(timezone="UTC")

# ---------------------------------------------------------------------------
# Scheduled jobs
# ---------------------------------------------------------------------------

async def rss_polling_job() -> None:
    """Every 30 min — fetch all RSS feeds, store new articles. No Gemini calls."""
    logger.info("[Scheduler] RSS polling job started")
    try:
        articles = await fetch_all_feeds()
        saved = await db.save_articles(articles)
        logger.info(f"[Scheduler] RSS poll done — {saved} articles stored")
    except Exception as exc:
        logger.error(f"[Scheduler] RSS polling failed: {exc}")


async def scoring_job() -> None:
    """Every 4 hours — score articles against all user profiles, update feeds.
    Also handles inactive user management:
      - 7+ days no login  → set scoring_paused = True (skip scoring)
      - 60+ days no login → delete profile and feed from Firestore
    """
    logger.info("[Scheduler] Scoring job started")
    try:
        articles = await db.get_recent_articles(hours=settings.ARTICLE_RETENTION_HOURS)
        profiles = await db.get_all_user_profiles()
        logger.info(f"[Scheduler] Scoring {len(articles)} articles for {len(profiles)} users")

        now = datetime.utcnow()
        skipped = 0
        deleted = 0

        for profile in profiles:
            # --- Inactive user management ---
            if profile.last_seen:
                days_inactive = (now - profile.last_seen).days

                if days_inactive >= 60:
                    # Hard delete: remove profile and feed
                    await db.delete_user_data(profile.user_id)
                    logger.info(f"[Scheduler] Deleted data for inactive user {profile.user_id} ({days_inactive}d)")
                    deleted += 1
                    continue

                if days_inactive >= 7 and not profile.scoring_paused:
                    # Soft pause: mark as paused, skip this cycle
                    await db.set_scoring_paused(profile.user_id, True)
                    logger.info(f"[Scheduler] Paused scoring for user {profile.user_id} ({days_inactive}d inactive)")
                    skipped += 1
                    continue

            if profile.scoring_paused:
                skipped += 1
                continue

            # --- Score articles for active user ---
            scored = scoring_agent.score_articles(
                profile,
                articles,
                max_per_batch=settings.MAX_ARTICLES_PER_GEMINI_CALL,
            )
            top = scored[: settings.MAX_ARTICLES_PER_FEED]
            feed = UserFeed(
                user_id=profile.user_id,
                user_name=profile.name,
                articles=top,
                generated_at=datetime.utcnow(),
                article_count=len(top),
            )
            await db.save_user_feed(feed)

        logger.info(
            f"[Scheduler] Scoring done — {len(profiles) - skipped - deleted} feeds updated, "
            f"{skipped} skipped (inactive), {deleted} deleted (60d+)"
        )
    except Exception as exc:
        logger.error(f"[Scheduler] Scoring job failed: {exc}")


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("UCKhabar backend starting…")

    scheduler.add_job(rss_polling_job, "interval",
                      minutes=settings.RSS_POLL_INTERVAL_MINUTES,
                      id="rss_poll", max_instances=1)
    scheduler.add_job(scoring_job, "interval",
                      minutes=settings.SCORING_INTERVAL_MINUTES,
                      id="scoring", max_instances=1)
    scheduler.start()

    # Warm up article pool immediately on startup
    asyncio.create_task(rss_polling_job())

    logger.info(
        f"Scheduler live. RSS every {settings.RSS_POLL_INTERVAL_MINUTES} min, "
        f"scoring every {settings.SCORING_INTERVAL_MINUTES} min."
    )
    yield

    scheduler.shutdown(wait=False)
    logger.info("UCKhabar backend shut down.")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="UCKhabar API",
    description="Uncluttered Khabar — AI-powered personal news curation",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allows the frontend (Firebase Hosting / any domain) to call this API.
# In production you can restrict allow_origins to your exact domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# ---------------------------------------------------------------------------
# Onboarding  (auth required)
# ---------------------------------------------------------------------------

@app.post(
    "/onboarding/start",
    response_model=StartOnboardingResponse,
    summary="Start AI onboarding chat",
    tags=["Onboarding"],
)
async def start_onboarding(
    request: StartOnboardingRequest,
    user=Depends(get_current_user),   # ← Firebase token verified here
):
    """
    Kick off the onboarding conversation for a first-time user.
    The user's Google account UID and display name are taken from the auth token.
    Returns a session_id and the first AI greeting.
    """
    # Name priority: request override → Google account name → fallback
    display_name = request.name or user.get("name") or "there"

    try:
        session_id, first_message = onboarding_agent.start_session(
            user_id=user["uid"],       # Firebase UID is the user_id
            name=display_name,
        )
        return StartOnboardingResponse(session_id=session_id, message=first_message)
    except Exception as exc:
        logger.error(f"start_onboarding error for {user['uid']}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post(
    "/onboarding/message",
    response_model=SendMessageResponse,
    summary="Continue onboarding chat",
    tags=["Onboarding"],
)
async def send_onboarding_message(
    request: SendMessageRequest,
    user=Depends(get_current_user),
):
    """
    Forward the user's reply to the Gemini agent.
    When is_complete=True, the interest profile has been built and saved to Firestore.
    """
    try:
        ai_response, is_complete, profile = onboarding_agent.send_message(
            session_id=request.session_id,
            user_message=request.message,
        )

        if is_complete and profile:
            # Safety check: ensure the session belongs to the authenticated user
            session = onboarding_agent.get_session(request.session_id)
            if session and session.user_id != user["uid"]:
                raise HTTPException(status_code=403, detail="Session does not belong to this user.")

            await db.save_user_profile(profile)
            logger.info(
                f"Onboarding complete for {user['uid']} ({user.get('email')}). "
                f"Topics: {[t.topic for t in profile.topics]}"
            )

        return SendMessageResponse(
            message=ai_response,
            is_complete=is_complete,
            profile=profile if is_complete else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"send_onboarding_message error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Feed  (auth required)
# ---------------------------------------------------------------------------

@app.get(
    "/feed/me",
    response_model=UserFeed,
    summary="Get my curated feed",
    tags=["Feed"],
)
async def get_my_feed(user=Depends(get_current_user)):
    """
    Return the authenticated user's pre-built personalised news feed.
    Refreshed every 4 hours by the scoring scheduler.
    Also updates last_seen so inactive user management works correctly.
    """
    uid = user["uid"]
    # Update last_seen + clear scoring_paused on every active visit
    await db.update_last_seen(uid)

    feed = await db.get_user_feed(uid)
    if not feed:
        raise HTTPException(
            status_code=404,
            detail=(
                "Your feed isn't ready yet. "
                "Complete onboarding first, then wait a moment for the first scoring cycle."
            ),
        )
    return feed


@app.post(
    "/feed/refresh",
    summary="Manually refresh my feed (testing)",
    tags=["Feed"],
)
async def refresh_my_feed(
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
):
    """On-demand feed refresh for the authenticated user. Useful during testing."""
    uid = user["uid"]
    profile = await db.get_user_profile(uid)
    if not profile:
        raise HTTPException(
            status_code=404,
            detail="No profile found. Complete onboarding first.",
        )

    async def _do_refresh():
        # Because Cloud Run sleeps between requests, the background RSS poll might not finish.
        # Force a fetch right now so we definitely have fresh articles to score.
        await rss_polling_job()

        articles = await db.get_recent_articles(hours=settings.ARTICLE_RETENTION_HOURS)
        scored = scoring_agent.score_articles(profile, articles)
        top = scored[: settings.MAX_ARTICLES_PER_FEED]
        feed = UserFeed(
            user_id=uid,
            user_name=profile.name,
            articles=top,
            generated_at=datetime.utcnow(),
            article_count=len(top),
        )
        await db.save_user_feed(feed)
        logger.info(f"Manual feed refresh done for {uid}: {len(top)} articles")

    background_tasks.add_task(_do_refresh)
    return {"message": "Feed refresh triggered", "user_id": uid}


# ---------------------------------------------------------------------------
# Onboarding complete  (auth required) — new structured endpoint
# ---------------------------------------------------------------------------

@app.post(
    "/onboarding/complete",
    response_model=CompleteOnboardingResponse,
    summary="Complete structured onboarding with checkbox selections",
    tags=["Onboarding"],
)
async def complete_onboarding(
    request: CompleteOnboardingRequest,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
):
    """
    Accept the structured onboarding result (category checkboxes + optional AI extras).
    Builds a full UserProfile from the taxonomy, saves to Firestore,
    and triggers an immediate feed refresh in the background.
    """
    uid   = user["uid"]
    name  = request.name or user.get("name") or "there"
    now   = datetime.utcnow()

    # Build topics from taxonomy
    topics = build_topics_from_selections(
        selected_categories=request.selected_categories,
        selected_subcategories=request.selected_subcategories,
        ai_extras=request.ai_extras,
    )

    # Check if profile already exists (to preserve created_at)
    existing = await db.get_user_profile(uid)
    created_at = existing.created_at if existing else now

    profile = UserProfile(
        schema_version=2,
        user_id=uid,
        name=name,
        topics=topics,
        selected_categories=request.selected_categories,
        selected_subcategories=request.selected_subcategories,
        ai_extras=request.ai_extras,
        created_at=created_at,
        updated_at=now,
        last_seen=now,
        scoring_paused=False,
    )

    await db.save_user_profile(profile)
    logger.info(
        f"Structured onboarding complete for {uid}: "
        f"categories={request.selected_categories}"
    )

    # Trigger immediate feed build in background
    async def _build_feed():
        await rss_polling_job()
        articles = await db.get_recent_articles(hours=settings.ARTICLE_RETENTION_HOURS)
        scored = scoring_agent.score_articles(profile, articles)
        top = scored[: settings.MAX_ARTICLES_PER_FEED]
        feed = UserFeed(
            user_id=uid,
            user_name=profile.name,
            articles=top,
            generated_at=datetime.utcnow(),
            article_count=len(top),
        )
        await db.save_user_feed(feed)
        logger.info(f"Initial feed built for {uid}: {len(top)} articles")

    background_tasks.add_task(_build_feed)
    return CompleteOnboardingResponse(status="processing", estimated_minutes=4)


# ---------------------------------------------------------------------------
# Profile  (auth required)
# ---------------------------------------------------------------------------

@app.get(
    "/profile/me",
    response_model=UserProfile,
    summary="Get my profile",
    tags=["Profile"],
)
async def get_my_profile(user=Depends(get_current_user)):
    """
    Return the authenticated user's interest profile from Firestore.
    Used by the frontend to pre-populate the preferences flow.
    """
    uid = user["uid"]
    await db.update_last_seen(uid)
    profile = await db.get_user_profile(uid)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found. Complete onboarding first.")
    return profile


# ---------------------------------------------------------------------------
# Admin / testing  (no auth — restrict in production via Cloud Run IAM)
# ---------------------------------------------------------------------------

@app.post("/admin/rss/poll", summary="Trigger RSS poll (admin)", tags=["Admin"])
async def manual_rss_poll(background_tasks: BackgroundTasks):
    background_tasks.add_task(rss_polling_job)
    return {"message": "RSS polling triggered"}


@app.post("/admin/scoring/run", summary="Trigger scoring job (admin)", tags=["Admin"])
async def manual_scoring_run(background_tasks: BackgroundTasks):
    background_tasks.add_task(scoring_job)
    return {"message": "Scoring job triggered"}


# ---------------------------------------------------------------------------
# Health check  (public)
# ---------------------------------------------------------------------------

@app.get("/health", summary="Health check", tags=["System"])
async def health_check():
    return {
        "status":            "healthy",
        "service":           "UCKhabar API",
        "version":           "1.0.0",
        "environment":       settings.APP_ENV,
        "scheduler_running": scheduler.running,
        "gemini_model":      settings.GEMINI_MODEL,
    }


# ---------------------------------------------------------------------------
# Local dev entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=(settings.APP_ENV == "development"),
    )
