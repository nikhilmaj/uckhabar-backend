"""
UCKhabar — FastAPI Application Entry Point

Exposes:
  POST  /onboarding/start             — begin AI onboarding chat
  POST  /onboarding/message           — continue onboarding chat
  GET   /feed/{user_id}               — get pre-built curated feed
  POST  /feed/refresh/{user_id}       — manually trigger feed refresh (test)
  POST  /admin/rss/poll               — manually trigger RSS poll (test)
  POST  /admin/scoring/run            — manually trigger scoring job (test)
  GET   /health                       — health check + scheduler status

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
from fastapi import BackgroundTasks, FastAPI, HTTPException

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
# Service singletons (initialised once, shared across all requests)
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
    """
    Runs every 30 minutes.
    Fetches all 5 RSS sources and stores new articles in Firestore.
    No Gemini calls — completely free.
    """
    logger.info("[Scheduler] RSS polling job started")
    try:
        articles = await fetch_all_feeds()
        saved = await db.save_articles(articles)
        logger.info(f"[Scheduler] RSS poll done — {saved} articles stored")
    except Exception as exc:
        logger.error(f"[Scheduler] RSS polling failed: {exc}")


async def scoring_job() -> None:
    """
    Runs every 2 hours.
    Scores recent articles against every user's interest profile using Gemini,
    then writes each user's pre-built feed to Firestore.
    """
    logger.info("[Scheduler] Scoring job started")
    try:
        articles = await db.get_recent_articles(hours=settings.ARTICLE_RETENTION_HOURS)
        profiles = await db.get_all_user_profiles()

        logger.info(
            f"[Scheduler] Scoring {len(articles)} articles "
            f"for {len(profiles)} users"
        )

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

        logger.info(f"[Scheduler] Scoring job done — {len(profiles)} feeds updated")
    except Exception as exc:
        logger.error(f"[Scheduler] Scoring job failed: {exc}")


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Register schedulers and run an initial RSS poll on startup."""
    logger.info("UCKhabar backend starting…")

    scheduler.add_job(
        rss_polling_job,
        "interval",
        minutes=settings.RSS_POLL_INTERVAL_MINUTES,
        id="rss_poll",
        max_instances=1,   # prevent overlap if a job runs long
    )
    scheduler.add_job(
        scoring_job,
        "interval",
        minutes=settings.SCORING_INTERVAL_MINUTES,
        id="scoring",
        max_instances=1,
    )
    scheduler.start()

    # Warm up: fetch RSS immediately on startup so the article pool isn't empty
    asyncio.create_task(rss_polling_job())

    logger.info(
        f"Scheduler started. RSS every {settings.RSS_POLL_INTERVAL_MINUTES} min, "
        f"scoring every {settings.SCORING_INTERVAL_MINUTES} min."
    )
    yield

    scheduler.shutdown(wait=False)
    logger.info("UCKhabar backend shut down cleanly.")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="UCKhabar API",
    description="Uncluttered Khabar — AI-powered personal news curation backend",
    version="1.0.0",
    lifespan=lifespan,
)


# -----------------------------------------------------------------------
# Onboarding endpoints
# -----------------------------------------------------------------------

@app.post(
    "/onboarding/start",
    response_model=StartOnboardingResponse,
    summary="Start AI onboarding chat",
    tags=["Onboarding"],
)
async def start_onboarding(request: StartOnboardingRequest):
    """
    Kick off a new onboarding session for a first-time user.
    Returns a `session_id` and the first AI greeting message.
    """
    try:
        session_id, first_message = onboarding_agent.start_session(
            user_id=request.user_id,
            name=request.name,
        )
        return StartOnboardingResponse(session_id=session_id, message=first_message)
    except Exception as exc:
        logger.error(f"start_onboarding error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post(
    "/onboarding/message",
    response_model=SendMessageResponse,
    summary="Continue onboarding chat",
    tags=["Onboarding"],
)
async def send_onboarding_message(request: SendMessageRequest):
    """
    Forward the user's reply to Gemini and get the next AI message.
    When `is_complete=True` the user's interest profile has been built
    and saved to Firestore — no further calls needed.
    """
    try:
        ai_response, is_complete, profile = onboarding_agent.send_message(
            session_id=request.session_id,
            user_message=request.message,
        )

        if is_complete and profile:
            await db.save_user_profile(profile)
            logger.info(
                f"Onboarding complete for user {profile.user_id}. "
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


# -----------------------------------------------------------------------
# Feed endpoints
# -----------------------------------------------------------------------

@app.get(
    "/feed/{user_id}",
    response_model=UserFeed,
    summary="Get curated feed for a user",
    tags=["Feed"],
)
async def get_user_feed(user_id: str):
    """
    Return the pre-built, personalised news feed for a user.
    The feed is refreshed every 2 hours by the scoring scheduler.
    """
    feed = await db.get_user_feed(user_id)
    if not feed:
        raise HTTPException(
            status_code=404,
            detail=(
                "Feed not found. Either the user hasn't completed onboarding "
                "or the first scoring cycle hasn't run yet."
            ),
        )
    return feed


@app.post(
    "/feed/refresh/{user_id}",
    summary="Manually refresh a user's feed (testing)",
    tags=["Feed"],
)
async def refresh_user_feed(user_id: str, background_tasks: BackgroundTasks):
    """
    Trigger an on-demand feed refresh for one user.
    Useful for testing without waiting for the 2-hour scheduler.
    """
    profile = await db.get_user_profile(user_id)
    if not profile:
        raise HTTPException(
            status_code=404,
            detail=f"No profile found for user '{user_id}'. Complete onboarding first.",
        )

    async def _do_refresh():
        articles = await db.get_recent_articles(hours=settings.ARTICLE_RETENTION_HOURS)
        scored = scoring_agent.score_articles(profile, articles)
        top = scored[: settings.MAX_ARTICLES_PER_FEED]
        feed = UserFeed(
            user_id=user_id,
            articles=top,
            generated_at=datetime.utcnow(),
            article_count=len(top),
        )
        await db.save_user_feed(feed)
        logger.info(f"Manual feed refresh done for {user_id}: {len(top)} articles")

    background_tasks.add_task(_do_refresh)
    return {"message": "Feed refresh triggered", "user_id": user_id}


# -----------------------------------------------------------------------
# Admin / testing endpoints
# -----------------------------------------------------------------------

@app.post(
    "/admin/rss/poll",
    summary="Manually trigger RSS poll (testing)",
    tags=["Admin"],
)
async def manual_rss_poll(background_tasks: BackgroundTasks):
    """Trigger an immediate RSS poll. Useful during development."""
    background_tasks.add_task(rss_polling_job)
    return {"message": "RSS polling triggered in background"}


@app.post(
    "/admin/scoring/run",
    summary="Manually trigger full scoring job (testing)",
    tags=["Admin"],
)
async def manual_scoring_run(background_tasks: BackgroundTasks):
    """Trigger an immediate scoring run for all users. Useful during development."""
    background_tasks.add_task(scoring_job)
    return {"message": "Scoring job triggered in background"}


# -----------------------------------------------------------------------
# Health check
# -----------------------------------------------------------------------

@app.get("/health", summary="Health check", tags=["System"])
async def health_check():
    return {
        "status":           "healthy",
        "service":          "UCKhabar API",
        "version":          "1.0.0",
        "environment":      settings.APP_ENV,
        "scheduler_running": scheduler.running,
        "gemini_model":     settings.GEMINI_MODEL,
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
