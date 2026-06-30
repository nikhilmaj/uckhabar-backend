"""
UCKhabar — FastAPI Application Entry Point

Auth-protected endpoints (require Firebase Google Sign-In token):
  GET   /feed/me                      — get my curated feed
  POST  /feed/refresh                 — manually refresh my feed
  POST  /onboarding/complete          — complete structured onboarding
  GET   /profile/me                   — get my profile

Public endpoints:
  GET   /feed/discovery               — top recent articles (no auth)
  GET   /health                       — health check

Admin endpoints (require X-Admin-Secret header):
  POST  /admin/rss/poll               — manually trigger RSS poll
  POST  /admin/scoring/run            — manually trigger scoring for all users

Background jobs (Cloud Scheduler → HTTP, not APScheduler):
  Every 20 min  → POST /admin/rss/poll
  Every 30 min  → POST /admin/scoring/run
  Every 24 hours → POST /admin/cleanup/run
"""

import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import httpx
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
# Scheduling is handled by Google Cloud Scheduler (external HTTP calls to /admin/* endpoints)

# ---------------------------------------------------------------------------
# Security — Admin dependency
# ---------------------------------------------------------------------------

async def verify_admin(x_admin_secret: str = Header(None)):
    """
    Protect admin endpoints with a shared secret passed via the
    X-Admin-Secret HTTP header. The secret is set as a Cloud Run
    environment variable (ADMIN_SECRET). Never expose this in client code.
    """
    if not x_admin_secret or not secrets.compare_digest(x_admin_secret, settings.ADMIN_SECRET):
        raise HTTPException(
            status_code=403,
            detail="Forbidden: valid X-Admin-Secret header required."
        )

# ---------------------------------------------------------------------------
# Scheduled jobs
# ---------------------------------------------------------------------------

async def rss_polling_job() -> None:
    """Every 20 min — fetch all RSS feeds, tag NEW articles with Gemini, store results."""
    logger.info("[Scheduler] RSS polling & tagging job started")
    try:
        articles = await fetch_all_feeds()
        if not articles:
            logger.info("[Scheduler] No articles fetched — skipping")
            return

        # Check which articles are already in Firestore (already tagged)
        article_ids = [a.id for a in articles]
        existing_ids = await db.get_existing_article_ids(article_ids)

        new_articles      = [a for a in articles if a.id not in existing_ids]
        existing_articles = [a for a in articles if a.id in existing_ids]

        logger.info(
            f"[Scheduler] {len(new_articles)} new articles to tag, "
            f"{len(existing_articles)} already tagged (skipping Gemini)"
        )

        # Tag ONLY new articles — major cost saving vs re-tagging everything
        if new_articles:
            tagged = await tagging_agent.tag_articles(new_articles)
            saved = await db.save_articles(tagged)
            logger.info(f"[Scheduler] Saved {saved} newly tagged articles")

        # For existing articles, just refresh fetched_at so they stay in recency window
        # WITHOUT overwriting their existing categories/subcategories tags
        if existing_articles:
            await db.refresh_article_timestamps([a.id for a in existing_articles])

        logger.info("[Scheduler] RSS poll & tag done")
    except Exception as exc:
        logger.error(f"[Scheduler] RSS polling/tagging failed: {exc}")



async def feed_builder_job() -> None:
    """Every 4 hours — match articles against user profiles using plain Python.
    Also handles inactive user management:
      - 7+ days no login  → set scoring_paused = True (skip building)
      - 60+ days no login → delete feed only (keep profile for historical records)
    """
    logger.info("[Scheduler] Feed builder job started")
    try:
        # V2: Expanded 5-day recency rule to ensure enough articles per category
        articles = await db.get_recent_articles(hours=120)
        profiles = await db.get_all_user_profiles()
        logger.info(f"[Scheduler] Matching {len(articles)} articles for {len(profiles)} users")

        now = datetime.now(timezone.utc)
        skipped = 0
        pruned = 0

        for profile in profiles:
            # --- Inactive user management ---
            if profile.last_seen:
                days_inactive = (now - profile.last_seen.replace(tzinfo=timezone.utc)).days

                if days_inactive >= 60:
                    # Delete their stale feed to free Firestore space; KEEP the profile
                    # so we maintain a historical record of all users (active + past).
                    await db.delete_user_feed_only(profile.user_id)
                    await db.set_scoring_paused(profile.user_id, True)
                    logger.info(
                        f"[Scheduler] Pruned feed for 60d+ inactive user {profile.user_id}"
                    )
                    pruned += 1
                    continue

                if days_inactive >= 7 and not profile.scoring_paused:
                    await db.set_scoring_paused(profile.user_id, True)
                    logger.info(
                        f"[Scheduler] Paused scoring for user {profile.user_id} ({days_inactive}d inactive)"
                    )
                    skipped += 1
                    continue

            if profile.scoring_paused:
                skipped += 1
                continue

            # --- Feed Matching (No AI — pure Python keyword/category matching) ---
            user_feed = []
            user_cats = set(profile.selected_categories)

            # Combine all selected subcategories into a single flat set
            user_subs = set()
            for subs in profile.selected_subcategories.values():
                for s in subs:
                    user_subs.add(s)

            for a in articles:
                # 1. Apply Content Filters
                cf = profile.content_filters
                act = a.content_type

                # If user disabled a filter and the article IS that type → reject it
                if act.get("is_hard_news", False)  and not cf.get("is_hard_news", True):  continue
                if act.get("is_editorial", False)  and not cf.get("is_editorial", True):  continue
                if act.get("is_sponsored", False)  and not cf.get("is_sponsored", True):  continue
                if act.get("is_explicit", False)   and not cf.get("is_explicit", True):   continue
                if act.get("is_aggregated", False) and not cf.get("is_aggregated", True): continue

                # 2. Category/Subcategory match
                article_cats = set(a.categories)
                article_subs = set(a.subcategories)

                matched = bool(
                    user_cats.intersection(article_cats) or
                    user_subs.intersection(article_subs)
                )

                if matched:
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
                reverse=True,
            )

            feed = UserFeed(
                user_id=profile.user_id,
                user_name=profile.name,
                articles=user_feed,
                generated_at=now,
                article_count=len(user_feed),
            )
            await db.save_user_feed(feed)

        logger.info(
            f"[Scheduler] Feed build done — "
            f"{len(profiles) - skipped - pruned} feeds updated, "
            f"{skipped} skipped (inactive <60d), {pruned} pruned (60d+)"
        )
    except Exception as exc:
        logger.error(f"[Scheduler] Feed building failed: {exc}")


async def daily_cleanup_job() -> None:
    """Deletes articles older than 7 days from Firestore to control storage costs."""
    logger.info("[Scheduler] Daily cleanup job started")
    try:
        deleted = await db.delete_old_articles(days=7)
        logger.info(f"[Scheduler] Daily cleanup done — {deleted} old articles removed")
    except Exception as exc:
        logger.error(f"[Scheduler] Cleanup job failed: {exc}")


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("UCKhabar backend starting…")

    # NOTE: RSS polling and feed building are handled ENTIRELY by Google Cloud Scheduler
    # via HTTP calls to /admin/rss/poll and /admin/scoring/run.
    # We do NOT trigger a poll on startup to avoid surprise Gemini costs on every
    # redeployment or Cloud Run cold start.

    logger.info("UCKhabar backend started. Background jobs managed by Cloud Scheduler.")
    yield
    logger.info("UCKhabar backend shut down.")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="UCKhabar API",
    description="Uncluttered Khabar — AI-powered personal news curation",
    version="2.0.0",
    lifespan=lifespan,
    # Disable automatic /docs and /redoc in production to reduce attack surface
    docs_url="/docs" if settings.APP_ENV == "development" else None,
    redoc_url=None,
)

# CORS — locked to known frontend origins only.
# Do NOT use allow_origins=["*"] — that lets any website impersonate your users.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
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
    Refreshed every 4 hours by the feed builder scheduler.
    Also updates last_seen so inactive user management works correctly.
    """
    uid = user["uid"]

    # Check if the user was paused BEFORE updating last_seen
    profile = await db.get_user_profile(uid)
    if profile and profile.scoring_paused:
        # User is returning after being paused (>7 days inactivity).
        # Delete the stale/empty feed, explicitly unpause, then trigger a rebuild.
        await db.delete_user_feed_only(uid)
        await db.unpause_user(uid)   # sets scoring_paused=False + updates last_seen
        background_tasks.add_task(feed_builder_job)
        return JSONResponse(
            status_code=202,
            content={
                "detail": (
                    "Welcome back! Your feed was paused due to inactivity. "
                    "Please return in 15–30 minutes while we refill your news feed."
                )
            }
        )

    # Normal active path: update timestamp only (do NOT reset scoring_paused here)
    await db.update_last_seen(uid)

    feed = await db.get_user_feed(uid)
    if not feed:
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
                "id":           a.id,
                "title":        a.title,
                "url":          a.url,
                "source":       a.source,
                "description":  (a.description or "")[:200],
                "published_at": a.published_at.isoformat() if a.published_at else None,
            }
            for a in sorted_articles
        ],
        "count": len(sorted_articles),
    }


@app.post(
    "/feed/refresh",
    summary="Manually refresh my feed",
    tags=["Feed"],
)
async def refresh_my_feed(
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
):
    """On-demand feed refresh for the authenticated user."""
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
# Onboarding  (auth required)
# ---------------------------------------------------------------------------

@app.post(
    "/onboarding/complete",
    response_model=CompleteOnboardingResponse,
    summary="Complete structured onboarding",
    tags=["Onboarding"],
)
async def complete_onboarding(
    request: CompleteOnboardingRequest,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
):
    """
    Accept the structured onboarding result (category checkboxes + content filters).
    Builds a full UserProfile from the taxonomy, saves to Firestore,
    and triggers an immediate feed build in the background.
    """
    uid   = user["uid"]
    name  = request.name or user.get("name") or "there"
    email = user.get("email")
    ip_addr = user.get("ip")
    now   = datetime.utcnow()

    # Build keyword topics from taxonomy
    topics = build_topics_from_selections(
        selected_categories=request.selected_categories,
        selected_subcategories=request.selected_subcategories,
        ai_extras=request.ai_extras,
    )

    # Simple keyword extraction from free-text extras (no AI required here)
    ai_keywords = []
    if request.ai_extras and request.ai_extras.strip():
        ai_keywords = [w.lower() for w in request.ai_extras.replace(",", " ").split() if len(w) > 3]

    # Preserve created_at for returning users updating preferences
    existing = await db.get_user_profile(uid)
    created_at = existing.created_at if existing else now

    # Geo lookup (best-effort, non-blocking)
    city, country = None, None
    if existing:
        city    = existing.last_login_city
        country = existing.last_login_country

    if ip_addr and (not existing or existing.last_login_ip != ip_addr):
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"http://ip-api.com/json/{ip_addr}?fields=status,city,country")
                if resp.status_code == 200:
                    geo = resp.json()
                    if geo.get("status") == "success":
                        city    = geo.get("city")
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
        f"Onboarding complete for {uid}: categories={request.selected_categories}"
    )

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
    Only updates last_seen — does NOT reset scoring_paused.
    """
    uid = user["uid"]
    await db.update_last_seen(uid)   # timestamp only; does not touch scoring_paused
    profile = await db.get_user_profile(uid)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found. Complete onboarding first.")
    return profile


# ---------------------------------------------------------------------------
# Activity ping  (auth required)
# ---------------------------------------------------------------------------

@app.post(
    "/activity",
    summary="Update last_seen timestamp (called by frontend on each visit)",
    tags=["Feed"],
)
async def record_activity(user=Depends(get_current_user)):
    """
    Lightweight endpoint called by the frontend on each page load.
    Updates the user's last_seen timestamp so the inactivity logic
    (7-day pause / 60-day cleanup) stays accurate without requiring
    the frontend to call the heavier /feed/me endpoint.
    """
    uid = user["uid"]
    await db.update_last_seen(uid)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Admin endpoints — protected by X-Admin-Secret header
# Called by Google Cloud Scheduler; run synchronously so Cloud Scheduler
# waits for completion before marking the job as succeeded.
# ---------------------------------------------------------------------------

@app.post(
    "/admin/rss/poll",
    summary="Trigger RSS poll (admin only — called by Cloud Scheduler every 20 min)",
    tags=["Admin"],
    dependencies=[Depends(verify_admin)],
)
async def manual_rss_poll():
    """Fetch all RSS feeds, tag only NEW articles via Gemini, persist to Firestore."""
    await rss_polling_job()
    return {"message": "RSS polling complete"}


@app.post(
    "/admin/scoring/run",
    summary="Trigger feed builder (admin only — called by Cloud Scheduler every 30 min)",
    tags=["Admin"],
    dependencies=[Depends(verify_admin)],
)
async def manual_scoring_run():
    """Run the feed builder for all active users and write updated user_feeds to Firestore."""
    await feed_builder_job()
    return {"message": "Feed builder complete"}


@app.post(
    "/admin/cleanup/run",
    summary="Delete articles older than 7 days (admin only — called by Cloud Scheduler daily)",
    tags=["Admin"],
    dependencies=[Depends(verify_admin)],
)
async def manual_cleanup_run():
    """Delete articles older than 7 days from Firestore to control storage costs."""
    await daily_cleanup_job()
    return {"message": "Cleanup complete"}


# ---------------------------------------------------------------------------
# Health check  (public)
# ---------------------------------------------------------------------------

@app.get("/health", summary="Health check", tags=["System"])
async def health_check():
    return {
        "status":            "healthy",
        "service":           "UCKhabar API",
        "version":           "2.0.0",
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
