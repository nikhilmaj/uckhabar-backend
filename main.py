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
from datetime import datetime

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException

from agents.onboarding_agent import OnboardingAgent
from agents.scoring_agent import ScoringAgent
from config import settings
from models.schemas import (
    SendMessageRequest,
    SendMessageResponse,
    StartOnboardingRequest,
    StartOnboardingResponse,
    UserFeed,
)
from services.auth_service import get_current_user
from services.db_service import DatabaseService
from services.rss_service import fetch_all_feeds

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
    api_key=settings.GEMINI_API_KEY,
    model_name=settings.GEMINI_MODEL,
)
scoring_agent = ScoringAgent(
    api_key=settings.GEMINI_API_KEY,
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
    """Every 2 hours — score articles against all user profiles, update feeds."""
    logger.info("[Scheduler] Scoring job started")
    try:
        articles = await db.get_recent_articles(hours=settings.ARTICLE_RETENTION_HOURS)
        profiles = await db.get_all_user_profiles()
        logger.info(f"[Scheduler] Scoring {len(articles)} articles for {len(profiles)} users")

        for profile in profiles:
            scored = scoring_agent.score_articles(
                profile,
                articles,
                max_per_batch=settings.MAX_ARTICLES_PER_GEMINI_CALL,
            )
            top = scored[: settings.MAX_ARTICLES_PER_FEED]
            feed = UserFeed(
                user_id=profile.user_id,
                articles=top,
                generated_at=datetime.utcnow(),
                article_count=len(top),
            )
            await db.save_user_feed(feed)

        logger.info(f"[Scheduler] Scoring done — {len(profiles)} feeds updated")
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
    Refreshed every 2 hours by the scoring scheduler.
    """
    feed = await db.get_user_feed(user["uid"])
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
        articles = await db.get_recent_articles(hours=settings.ARTICLE_RETENTION_HOURS)
        scored = scoring_agent.score_articles(profile, articles)
        top = scored[: settings.MAX_ARTICLES_PER_FEED]
        feed = UserFeed(
            user_id=uid,
            articles=top,
            generated_at=datetime.utcnow(),
            article_count=len(top),
        )
        await db.save_user_feed(feed)
        logger.info(f"Manual feed refresh done for {uid}: {len(top)} articles")

    background_tasks.add_task(_do_refresh)
    return {"message": "Feed refresh triggered", "user_id": uid}


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
