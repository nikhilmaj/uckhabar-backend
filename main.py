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
from datetime import datetime, timedelta, timezone

import httpx
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from agents.tagging_agent import TaggingAgent
from config import settings
from models.schemas import (
    CompleteOnboardingRequest,
    CompleteOnboardingResponse,
    UserFeed,
    UserProfile,
    ScoredArticle,
)
from services.auth_service import get_current_user
from services.db_service import DatabaseService
from services.rss_service import fetch_all_feeds
from services.topic_taxonomy import build_topics_from_selections

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

tagging_agent = TaggingAgent(
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
    """Every 30 min — fetch all RSS feeds, tag with Gemini, store new articles."""
    logger.info("[Scheduler] RSS polling & tagging job started")
    try:
        articles = await fetch_all_feeds()
        # V2: Tag articles at ingestion (Gemini batch call)
        tagged_articles = await tagging_agent.tag_articles(articles)
        saved = await db.save_articles(tagged_articles)
        logger.info(f"[Scheduler] RSS poll & tag done — {saved} articles stored")
    except Exception as exc:
        logger.error(f"[Scheduler] RSS polling/tagging failed: {exc}")


async def feed_builder_job() -> None:
    """Every 4 hours — match articles against user profiles using plain Python.
    Also handles inactive user management:
      - 7+ days no login  → set scoring_paused = True (skip building)
      - 60+ days no login → delete profile and feed from Firestore
    """
    logger.info("[Scheduler] Feed builder job started")
    try:
        # V2: Strict 3-day recency rule per instructions (instead of old 7-day)
        articles = await db.get_recent_articles(hours=72)
        profiles = await db.get_all_user_profiles()
        logger.info(f"[Scheduler] Matching {len(articles)} articles for {len(profiles)} users")

        now = datetime.now(timezone.utc)
        skipped = 0
        deleted = 0

        for profile in profiles:
            # --- Inactive user management ---
            if profile.last_seen:
                days_inactive = (now - profile.last_seen.replace(tzinfo=timezone.utc)).days

                if days_inactive >= 60:
                    await db.delete_user_data(profile.user_id)
                    logger.info(f"[Scheduler] Deleted data for inactive user {profile.user_id} ({days_inactive}d)")
                    deleted += 1
                    continue

                if days_inactive >= 7 and not profile.scoring_paused:
                    await db.set_scoring_paused(profile.user_id, True)
                    logger.info(f"[Scheduler] Paused scoring for user {profile.user_id} ({days_inactive}d inactive)")
                    skipped += 1
                    continue

            if profile.scoring_paused:
                skipped += 1
                continue

            # --- Feed Matching (No AI) ---
            user_feed = []
            user_cats = set(profile.selected_categories)
            
            # Combine all selected subcategories into a single flat set
            user_subs = set()
            for subs in profile.selected_subcategories.values():
                for s in subs:
                    user_subs.add(s)

            for a in articles:
                # 1. Check Content Filters (all filters must pass if user turned them off)
                cf = profile.content_filters
                act = a.content_type
                
                # If user disabled a filter, and the article IS that type, reject it.
                if act.get("is_hard_news", False) and not cf.get("is_hard_news", True): continue
                if act.get("is_editorial", False) and not cf.get("is_editorial", True): continue
                if act.get("is_sponsored", False) and not cf.get("is_sponsored", True): continue
                if act.get("is_explicit", False) and not cf.get("is_explicit", True): continue
                if act.get("is_aggregated", False) and not cf.get("is_aggregated", True): continue
                
                # 2. Check Match
                article_cats = set(a.categories)
                article_subs = set(a.subcategories)
                
                matched = False
                if user_cats.intersection(article_cats):
                    matched = True
                elif user_subs.intersection(article_subs):
                    matched = True
                    
                if matched:
                    # Assign a dummy relevance score to maintain compatibility,
                    # but sort primarily by publish date.
                    user_feed.append(ScoredArticle(
                        article_id=a.id,
                        title=a.title,
                        url=a.url,
                        source=a.source,
                        relevance_score=10.0,
                        published_at=a.published_at,
                        categories=a.categories,
                        subcategories=a.subcategories,
                    ))
                    
            # Sort chronologically, newest first
            user_feed.sort(
                key=lambda x: x.published_at.timestamp() if x.published_at else 0,
                reverse=True
            )
            
            # We don't cap the article count anymore per V2 instructions
            feed = UserFeed(
                user_id=profile.user_id,
                user_name=profile.name,
                articles=user_feed,
                generated_at=now,
                article_count=len(user_feed),
            )
            await db.save_user_feed(feed)

        logger.info(
            f"[Scheduler] Feed build done — {len(profiles) - skipped - deleted} feeds updated, "
            f"{skipped} skipped (inactive), {deleted} deleted (60d+)"
        )
    except Exception as exc:
        logger.error(f"[Scheduler] Feed building failed: {exc}")

async def daily_cleanup_job() -> None:
    """Deletes articles older than 7 days from Firestore."""
    logger.info("[Scheduler] Daily cleanup job started")
    try:
        deleted = await db.delete_old_articles(days=7)
    except Exception as exc:
        logger.error(f"[Scheduler] Cleanup job failed: {exc}")


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("UCKhabar backend starting…")

    scheduler.add_job(rss_polling_job, "interval",
                      minutes=settings.RSS_POLL_INTERVAL_MINUTES,
                      id="rss_poll", max_instances=1)
    scheduler.add_job(feed_builder_job, "interval",
                      minutes=settings.SCORING_INTERVAL_MINUTES,
                      id="scoring", max_instances=1)
    scheduler.add_job(daily_cleanup_job, "interval",
                      hours=24,
                      id="daily_cleanup", max_instances=1)
    scheduler.start()

    # Warm up article pool immediately on startup
    asyncio.create_task(rss_polling_job())

    logger.info(
        f"Scheduler live. RSS every {settings.RSS_POLL_INTERVAL_MINUTES} min, "
        f"scoring every {settings.SCORING_INTERVAL_MINUTES} min, cleanup every 24h."
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
# Feed  (auth required)
# ---------------------------------------------------------------------------

@app.get(
    "/feed/me",
    summary="Get my curated feed",
    tags=["Feed"],
)
async def get_my_feed(
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user)
):
    """
    Return the authenticated user's pre-built personalised news feed.
    Refreshed every 4 hours by the scoring scheduler.
    Also updates last_seen so inactive user management works correctly.
    """
    uid = user["uid"]
    
    # Check if the user was paused before we update last_seen
    profile = await db.get_user_profile(uid)
    if profile and profile.scoring_paused:
        # User is returning after being paused (>7 days inactivity)
        await db.delete_user_feed_only(uid)
        await db.update_last_seen(uid)
        background_tasks.add_task(feed_builder_job)
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=202,
            content={"detail": "Welcome back! Your feed was paused due to inactivity. Please return in 15-30 minutes while we refill your news feed."}
        )

    # Normal active path: Update last_seen + clear scoring_paused
    await db.update_last_seen(uid)

    feed = await db.get_user_feed(uid)
    if not feed:
        from fastapi.responses import JSONResponse
        if profile:
            background_tasks.add_task(feed_builder_job)
            return JSONResponse(status_code=202, content={"detail": "Feed is building"})
        else:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Your feed isn't ready yet. "
                    "Complete onboarding first, then wait a moment for the first scoring cycle."
                ),
            )
    return feed


@app.get(
    "/feed/discovery",
    summary="Public discovery feed — top recent articles, no auth required",
    tags=["Feed"],
)
async def get_discovery_feed():
    """
    Returns the 20 most recently published articles across all sources.
    Public endpoint — no authentication required.
    Used on the waiting screen while a new user's personalised feed is built.
    """
    articles = await db.get_recent_articles(hours=48)
    sorted_articles = sorted(
        articles,
        key=lambda a: (
            a.published_at
            if a.published_at and a.published_at.tzinfo
            else datetime.min.replace(tzinfo=timezone.utc)
        ),
        reverse=True,
    )[:20]
    return {
        "articles": [
            {
                "id":          a.id,
                "title":       a.title,
                "url":         a.url,
                "source":      a.source,
                "description": (a.description or "")[:200],
                "published_at": a.published_at.isoformat() if a.published_at else None,
            }
            for a in sorted_articles
        ],
        "count": len(sorted_articles),
    }


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

    background_tasks.add_task(feed_builder_job)
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
    email = user.get("email")
    ip_addr = user.get("ip")
    now   = datetime.utcnow()

    # Build topics from taxonomy
    topics = build_topics_from_selections(
        selected_categories=request.selected_categories,
        selected_subcategories=request.selected_subcategories,
        ai_extras=request.ai_extras,
    )

    # Extract AI keywords for filtering if extra interests were provided
    # Removing onboarding_agent so we'll just extract simple words
    ai_keywords = []
    if request.ai_extras and request.ai_extras.strip():
        ai_keywords = [w.lower() for w in request.ai_extras.replace(",", " ").split() if len(w) > 3]

    # Check if profile already exists (to preserve created_at)
    existing = await db.get_user_profile(uid)
    created_at = existing.created_at if existing else now
    
    # Geo lookup if IP changed or new
    city, country = None, None
    if existing:
        city = existing.last_login_city
        country = existing.last_login_country
        
    if ip_addr and (not existing or existing.last_login_ip != ip_addr):
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"http://ip-api.com/json/{ip_addr}?fields=status,city,country")
                if resp.status_code == 200:
                    geo = resp.json()
                    if geo.get("status") == "success":
                        city = geo.get("city")
                        country = geo.get("country")
        except Exception as e:
            logger.warning(f"Failed to resolve geo for IP {ip_addr}: {e}")

    profile = UserProfile(
        schema_version=2,
        user_id=uid,
        name=name,
        email=email,
        topics=topics,
        selected_categories=request.selected_categories,
        selected_subcategories=request.selected_subcategories,
        ai_extras=request.ai_extras,
        ai_extras_keywords=ai_keywords,
        content_filters=request.content_filters,
        created_at=created_at,
        updated_at=now,
        last_seen=now,
        last_login_ip=ip_addr,
        last_login_city=city,
        last_login_country=country,
        scoring_paused=False,
    )

    await db.save_user_profile(profile)
    logger.info(
        f"Structured onboarding complete for {uid}: "
        f"categories={request.selected_categories}"
    )

    # Trigger immediate feed build in background
    background_tasks.add_task(feed_builder_job)
    return CompleteOnboardingResponse(status="processing", estimated_minutes=1)


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
    background_tasks.add_task(feed_builder_job)
    return {"message": "Feed builder job triggered"}


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
