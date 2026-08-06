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
import re
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import httpx
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Header, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agents.tagging_agent import TaggingAgent
from agents.summarization_agent import SummarizationAgent
from config import settings
from models.schemas import (
    CompleteOnboardingRequest,
    CompleteOnboardingResponse,
    UserFeed,
    UserProfile,
    ScoredArticle,
    UpdateProfileRequest,
    UserSummary,
)
from services.auth_service import get_current_user
from services.db_service import DatabaseService
from services.rss_service import fetch_all_feeds
from services.topic_taxonomy import build_topics_from_selections
from services.push_service import send_breaking_news_push, send_feed_ready_push, subscribe_token_to_topics, send_personalized_push, unsubscribe_token_from_topics
from pydantic import BaseModel

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
summarization_agent = SummarizationAgent(
    project_id=settings.GCP_PROJECT_ID,
    location=settings.GCP_REGION,
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
            
            global _LAST_PUSH_TIME
            if '_LAST_PUSH_TIME' not in globals():
                _LAST_PUSH_TIME = datetime.min
                
            now = datetime.utcnow()
            if (now - _LAST_PUSH_TIME).total_seconds() > (3600 * 3):
                for art in tagged:
                    if getattr(art, 'is_breaking', False) or getattr(art, 'is_breaking_news', False):
                        await send_breaking_news_push(title=art.title, article_id=art.id, url=art.url or "/", topic="breaking_news")
                        _LAST_PUSH_TIME = now
                        break
                    elif getattr(art, 'is_globally_significant', False):
                        await send_breaking_news_push(title=art.title, article_id=art.id, url=art.url or "/", topic="global_alerts")
                        _LAST_PUSH_TIME = now
                        break

        # For existing articles, just refresh fetched_at so they stay in recency window
        # WITHOUT overwriting their existing categories/subcategories tags
        if existing_articles:
            await db.refresh_article_timestamps([a.id for a in existing_articles])

        logger.info("[Scheduler] RSS poll & tag done")
    except Exception as exc:
        logger.error(f"[Scheduler] RSS polling/tagging failed: {exc}")



CATEGORY_SYNONYMS = {
    "AI": {"AI", "Technology", "Science & Research"},
    "Technology": {"Technology", "AI", "Science & Research", "Video Gaming"},
    "Finance": {"Finance", "Business & Industry", "Agriculture & Rural"},
    "Politics": {"Politics", "Geopolitics", "International News", "Law & Justice", "Social Issues", "Defence & Military"},
    "Entertainment": {"Entertainment", "Video Gaming"},
    "Sports": {"Cricket", "Football", "Other Sports"},
    "Environment": {"Environment & Climate", "Agriculture & Rural"},
    "Health": {"Health & Medicine"},
}

def build_matched_feed_for_profile(articles, profile, min_articles=40):
    user_feed = []
    seen_ids = set()

    sel_cats = getattr(profile, 'selected_categories', None) or []
    expanded_cats = set(sel_cats)
    for cat in sel_cats:
        if cat in CATEGORY_SYNONYMS:
            expanded_cats.update(CATEGORY_SYNONYMS[cat])

    user_subs = set()
    sel_subs = getattr(profile, 'selected_subcategories', None) or {}
    for subs in sel_subs.values():
        for s in (subs or []):
            user_subs.add(s)

    for a in articles:
        cf = getattr(profile, 'content_filters', None) or {}
        act = getattr(a, 'content_type', None) or {}
        if act.get("is_hard_news", False)  and not cf.get("is_hard_news", True):  continue
        if act.get("is_editorial", False)  and not cf.get("is_editorial", True):  continue
        if act.get("is_sponsored", False)  and not cf.get("is_sponsored", True):  continue
        if act.get("is_explicit", False)   and not cf.get("is_explicit", True):   continue
        if act.get("is_aggregated", False) and not cf.get("is_aggregated", True): continue

        article_cats = set(getattr(a, 'categories', None) or [])
        article_subs = set(getattr(a, 'subcategories', None) or [])
        matched = bool(
            expanded_cats.intersection(article_cats) or
            user_subs.intersection(article_subs)
        )
        if matched:
            seen_ids.add(a.id)
            user_feed.append(ScoredArticle(
                article_id=a.id,
                title=a.title or "",
                url=a.url or "",
                image_url=a.image_url,
                source=a.source or "UCKhabar",
                relevance_score=10.0,
                published_at=a.published_at,
                is_breaking=getattr(a, 'is_breaking', False),
                categories=getattr(a, 'categories', None) or [],
                subcategories=getattr(a, 'subcategories', None) or [],
            ))

    if len(user_feed) < min_articles:
        for a in articles:
            if len(user_feed) >= min_articles:
                break
            if a.id in seen_ids:
                continue
            cf = getattr(profile, 'content_filters', None) or {}
            act = getattr(a, 'content_type', None) or {}
            if act.get("is_hard_news", False)  and not cf.get("is_hard_news", True):  continue
            if act.get("is_editorial", False)  and not cf.get("is_editorial", True):  continue
            if act.get("is_sponsored", False)  and not cf.get("is_sponsored", True):  continue
            if act.get("is_explicit", False)   and not cf.get("is_explicit", True):   continue
            if act.get("is_aggregated", False) and not cf.get("is_aggregated", True): continue

            seen_ids.add(a.id)
            user_feed.append(ScoredArticle(
                article_id=a.id,
                title=a.title or "",
                url=a.url or "",
                image_url=a.image_url,
                source=a.source or "UCKhabar",
                relevance_score=8.0,
                published_at=a.published_at,
                is_breaking=getattr(a, 'is_breaking', False),
                categories=getattr(a, 'categories', None) or [],
                subcategories=getattr(a, 'subcategories', None) or [],
            ))

    user_feed.sort(
        key=lambda x: x.published_at.timestamp() if x.published_at else 0,
        reverse=True,
    )
    if len(user_feed) > 1000:
        user_feed = user_feed[:1000]
    return user_feed


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
        articles.sort(
            key=lambda a: a.published_at.timestamp() if a.published_at else 0,
            reverse=True,
        )
        seen_titles = set()
        unique_articles = []
        for a in articles:
            clean_t = re.sub(r'[^a-zA-Z0-9]+', '', a.title).lower() if a.title else ""
            if clean_t and clean_t not in seen_titles:
                seen_titles.add(clean_t)
                unique_articles.append(a)
            elif not clean_t:
                unique_articles.append(a)
        articles = unique_articles
        profiles = await db.get_all_user_profiles()
        logger.info(f"[Scheduler] Matching {len(articles)} unique articles for {len(profiles)} users")

        now = datetime.now(timezone.utc)
        skipped = 0
        pruned = 0

        for profile in profiles:
            try:
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

                # --- Feed Matching (Expanded Synonyms + Minimum Feed Backfill) ---
                user_feed = build_matched_feed_for_profile(articles, profile, min_articles=40)

                # --- Interval Summary ("While You Were Away") ---
                ist_hour = (now.hour + 5 + (1 if (now.minute + 30) >= 60 else 0)) % 24
                if 5 <= ist_hour < 12:
                    window_label = "Your Morning Briefing"
                elif 12 <= ist_hour < 17:
                    window_label = "The Midday Catch-Up"
                elif 17 <= ist_hour < 21:
                    window_label = "The Evening Wrap"
                else:
                    window_label = "The Nightly Digest"

                interval_summary_text = None
                
                # Check if this is a trigger interval (8am, 12pm, 5pm, 9pm) and first run of the hour
                TRIGGER_HOURS_IST = [8, 12, 17, 21]
                is_trigger_hour = (ist_hour in TRIGGER_HOURS_IST) and (now.minute < 30)

                tone = getattr(profile, 'tone_preference', 'light') or 'light'
                existing_feed = await db.get_user_feed(profile.user_id)
                needs_new_summary = False
                
                if is_trigger_hour:
                    needs_new_summary = True
                elif existing_feed and getattr(existing_feed, 'interval_summary_window', None) == window_label:
                    if getattr(existing_feed, 'interval_summary_tone', None) != tone:
                        needs_new_summary = True

                if needs_new_summary:
                    # Filter top recent articles for the summary (last 12 hours)
                    recent_articles_for_summary = [
                        a for a in user_feed
                        if a.published_at and (now - a.published_at.replace(tzinfo=timezone.utc)).total_seconds() < 12 * 3600
                    ][:8]

                    if len(recent_articles_for_summary) >= 3:
                        window_time = window_label.split(" ")[1] if " " in window_label else window_label
                        interval_summary_text = await summarization_agent.generate_interval_summary(
                            recent_articles_for_summary, tone, window=window_time
                        )
                        if interval_summary_text:
                            cats = getattr(profile, 'selected_categories', [])
                            summary_obj = UserSummary(
                                user_id=profile.user_id,
                                user_name=profile.name,
                                content=interval_summary_text,
                                tone=tone,
                                categories=cats,
                                window=window_label
                            )
                            await db.save_user_summary(summary_obj)
                else:
                    # Not a trigger hour, try to carry over the existing summary if it matches the current window
                    if existing_feed and getattr(existing_feed, 'interval_summary_window', None) == window_label:
                        interval_summary_text = getattr(existing_feed, 'interval_summary', None)

                feed = UserFeed(
                    user_id=profile.user_id,
                    user_name=profile.name,
                    articles=user_feed,
                    generated_at=now,
                    article_count=len(user_feed),
                    interval_summary=interval_summary_text,
                    interval_summary_window=window_label,
                    interval_summary_tone=tone,
                )
                await db.save_user_feed(feed)

                if getattr(profile, 'push_tokens', None):
                    if is_trigger_hour:
                        if getattr(profile, 'summary_alerts_enabled', True):
                            tod = "morning" if 5 <= ist_hour < 12 else ("afternoon" if 12 <= ist_hour < 18 else "evening")
                            dead_tokens = await send_feed_ready_push(profile.push_tokens, time_of_day=tod)
                            if dead_tokens:
                                profile.push_tokens = [t for t in profile.push_tokens if t not in dead_tokens]
                                await db.save_user_profile(profile)
                    elif getattr(profile, 'trendy_alerts_enabled', True):
                        # Try to send a personalized trendy push (max 1 every 1.5 hours)
                        last_trendy = getattr(profile, 'last_trendy_push', None)
                        last_trendy_dt = last_trendy.replace(tzinfo=timezone.utc) if last_trendy else datetime.min.replace(tzinfo=timezone.utc)
                        if (now - last_trendy_dt).total_seconds() >= (1.5 * 3600):
                            pushed_ids = set(getattr(profile, 'pushed_article_ids', []) or [])
                            trendy_art = None
                            for art in user_feed:
                                if art.id not in pushed_ids:
                                    trendy_art = art
                                    break
                            
                            if trendy_art:
                                await send_personalized_push(profile.push_tokens, title=trendy_art.title, article_id=trendy_art.id, url=trendy_art.url or "/")
                                profile.last_trendy_push = now
                                pushed_ids.add(trendy_art.id)
                                profile.pushed_article_ids = list(pushed_ids)[-100:] # Keep last 100
                                await db.save_user_profile(profile)
            except Exception as user_exc:
                logger.error(f"[Scheduler] Failed building feed for user {profile.user_id}: {user_exc}")
                continue

        logger.info(
            f"[Scheduler] Feed build done — "
            f"{len(profiles) - skipped - pruned} feeds updated, "
            f"{skipped} skipped (inactive <60d), {pruned} pruned (60d+)"
        )
    except Exception as exc:
        logger.error(f"[Scheduler] Feed building failed: {exc}")


async def build_feed_for_single_user(target_uid: str) -> None:
    """Builds and saves a fresh feed immediately for a single user (e.g. after preference update)."""
    logger.info(f"[FeedBuilder] Building immediate feed for user {target_uid}")
    try:
        profile = await db.get_user_profile(target_uid)
        if not profile or profile.scoring_paused:
            return

        articles = await db.get_recent_articles(hours=120)
        articles.sort(key=lambda a: a.published_at.timestamp() if a.published_at else 0, reverse=True)

        seen_titles = set()
        unique_articles = []
        for a in articles:
            clean_t = re.sub(r'[^a-zA-Z0-9]+', '', a.title).lower() if a.title else ""
            if clean_t and clean_t not in seen_titles:
                seen_titles.add(clean_t)
                unique_articles.append(a)
            elif not clean_t:
                unique_articles.append(a)

        user_feed = build_matched_feed_for_profile(unique_articles, profile, min_articles=40)

        now = datetime.now(timezone.utc)
        
        # --- Interval Summary ("While You Were Away") ---
        ist_hour = (now.hour + 5 + (1 if (now.minute + 30) >= 60 else 0)) % 24
        if 5 <= ist_hour < 12:
            window_label = "Your Morning Briefing"
        elif 12 <= ist_hour < 17:
            window_label = "The Midday Catch-Up"
        elif 17 <= ist_hour < 21:
            window_label = "The Evening Wrap"
        else:
            window_label = "The Nightly Digest"

        recent_articles_for_summary = [
            a for a in user_feed
            if a.published_at and (now - a.published_at.replace(tzinfo=timezone.utc)).total_seconds() < 12 * 3600
        ][:8]

        interval_summary_text = None
        tone = getattr(profile, 'tone_preference', 'light') or 'light'
        
        # Determine if we need to regenerate
        needs_new_summary = True
        existing_feed = await db.get_user_feed(profile.user_id)
        if existing_feed and getattr(existing_feed, 'interval_summary_window', None) == window_label:
            if getattr(existing_feed, 'interval_summary_tone', None) == tone:
                needs_new_summary = False
                interval_summary_text = getattr(existing_feed, 'interval_summary', None)
                
        if needs_new_summary and len(recent_articles_for_summary) >= 3:
            window_time = window_label.split(" ")[1] if " " in window_label else window_label
            interval_summary_text = await summarization_agent.generate_interval_summary(
                recent_articles_for_summary, tone, window=window_time
            )
            if interval_summary_text:
                cats = getattr(profile, 'selected_categories', [])
                summary_obj = UserSummary(
                    user_id=profile.user_id,
                    user_name=profile.name,
                    content=interval_summary_text,
                    tone=tone,
                    categories=cats,
                    window=window_label
                )
                await db.save_user_summary(summary_obj)

        feed = UserFeed(
            user_id=profile.user_id,
            user_name=profile.name,
            articles=user_feed,
            generated_at=now,
            article_count=len(user_feed),
            interval_summary=interval_summary_text,
            interval_summary_window=window_label,
            interval_summary_tone=tone,
        )
        await db.save_user_feed(feed)
        if getattr(profile, 'push_tokens', None) and getattr(profile, 'summary_alerts_enabled', True):
            dead_tokens = await send_feed_ready_push(profile.push_tokens, time_of_day="curated")
            if dead_tokens:
                profile.push_tokens = [t for t in profile.push_tokens if t not in dead_tokens]
                await db.save_user_profile(profile)
        logger.info(f"[FeedBuilder] Immediately rebuilt {len(user_feed)} articles for {target_uid}")
    except Exception as exc:
        logger.error(f"[FeedBuilder] Single user build failed for {target_uid}: {exc}")


async def daily_cleanup_job() -> None:
    """Deletes articles older than 7 days and summaries older than 5 days from Firestore."""
    logger.info("[Scheduler] Daily cleanup job started")
    try:
        deleted_art = await db.delete_old_articles(days=7)
        deleted_sum = await db.delete_old_summaries(days=5)
        logger.info(f"[Scheduler] Daily cleanup done — {deleted_art} articles, {deleted_sum} summaries removed")
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
    "/api/article/{article_id}/full-story",
    summary="Fetch the full backstory of an article using AI search grounding",
    tags=["Feed"],
)
async def get_full_story_endpoint(article_id: str):
    """
    Fetches the article from Firestore by ID.
    If the 'Full Story' context is already cached, it returns it instantly.
    Otherwise, calls the SummarizationAgent to build the context (with Google Search) and saves it to Firestore.
    """
    article = await db.get_article(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    # Return cached story if available
    if article.full_story:
        cached_story = dict(article.full_story)
        if "image_url" not in cached_story and getattr(article, "image_url", None):
            cached_story["image_url"] = article.image_url
        return cached_story
    
    # Otherwise generate it (costs API tokens)
    snippet = article.description or ""
    full_story = await summarization_agent.get_full_story(article.title, article.source, snippet)
    if not full_story:
        raise HTTPException(status_code=500, detail="Failed to generate full story context.")
    
    # Prioritize the original article thumbnail
    if getattr(article, "image_url", None):
        full_story["image_url"] = article.image_url
    else:
        # Try to fetch Wikipedia image for the main entity
        search_term = full_story.get("main_entity_wikipedia_search_term")
        if search_term:
            import urllib.parse
            wiki_url = f"https://en.wikipedia.org/w/api.php?action=query&prop=pageimages&format=json&pithumbsize=800&titles={urllib.parse.quote(search_term)}"
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    res = await client.get(wiki_url)
                    if res.status_code == 200:
                        data = res.json()
                        pages = data.get("query", {}).get("pages", {})
                        for k, v in pages.items():
                            if "thumbnail" in v and "source" in v["thumbnail"]:
                                full_story["image_url"] = v["thumbnail"]["source"]
                                break
            except Exception as e:
                logging.getLogger("uckhabar.feed").warning(f"Failed to fetch wikipedia image: {e}")
    
    # Save back to database to cache it
    await db.update_article_full_story(article_id, full_story)
    
    return full_story



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
    articles = await db.get_recent_articles(hours=168)
    articles.sort(
        key=lambda a: a.published_at.timestamp() if a.published_at else 0,
        reverse=True,
    )
    seen_titles = set()
    unique_articles = []
    for a in articles:
        clean_t = re.sub(r'[^a-zA-Z0-9]+', '', a.title).lower() if a.title else ""
        if clean_t and clean_t not in seen_titles:
            seen_titles.add(clean_t)
            unique_articles.append(a)
        elif not clean_t:
            unique_articles.append(a)
    sorted_articles = sorted(
        unique_articles,
        key=lambda a: a.published_at.timestamp() if a.published_at else 0,
        reverse=True,
    )[:300]
    return {
        "articles": [
            {
                "id":            a.id,
                "title":         a.title,
                "url":           a.url,
                "source":        a.source,
                "description":   (a.description or "")[:200],
                "published_at":  a.published_at.isoformat() if a.published_at else None,
                "categories":    a.categories or [],
                "subcategories": a.subcategories or [],
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

    if profile.scoring_paused:
        await db.unpause_user(uid)

    background_tasks.add_task(build_feed_for_single_user, uid)
    return {"message": "Feed refresh triggered", "user_id": uid}


class PushTokenRequest(BaseModel):
    token: str

@app.post(
    "/notifications/subscribe",
    summary="Subscribe device push token for background notifications",
    tags=["Notifications"],
)
async def subscribe_push_token(req: PushTokenRequest, user=Depends(get_current_user)):
    uid = user["uid"]
    token = req.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token is required")
    profile = await db.get_user_profile(uid)
    if profile:
        tokens = set(getattr(profile, 'push_tokens', []) or [])
        tokens.add(token)
        profile.push_tokens = list(tokens)
        await db.save_user_profile(profile)
    else:
        await db._db.collection("user_profiles").document(uid).set({"push_tokens": [token]}, merge=True)
    
    topics_to_subscribe = []
    topics_to_unsubscribe = []
    
    if profile and getattr(profile, 'global_alerts_enabled', True):
        topics_to_subscribe.extend(["breaking_news", "global_alerts"])
    else:
        topics_to_unsubscribe.extend(["breaking_news", "global_alerts"])
        
    if topics_to_subscribe:
        await subscribe_token_to_topics(token, topics_to_subscribe)
    if topics_to_unsubscribe:
        await unsubscribe_token_from_topics(token, topics_to_unsubscribe)
        
    return {"status": "ok", "message": "Subscribed to background push notifications"}


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
        tone_preference=request.tone_preference,
        global_alerts_enabled=request.global_alerts_enabled,
        category_alerts_enabled=request.category_alerts_enabled,
        trendy_alerts_enabled=request.trendy_alerts_enabled,
        summary_alerts_enabled=request.summary_alerts_enabled,
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

    background_tasks.add_task(build_feed_for_single_user, uid)
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

@app.post(
    "/profile/update",
    response_model=UserProfile,
    summary="Update specific profile fields (Settings)",
    tags=["Profile"],
)
async def update_my_profile(request: UpdateProfileRequest, user=Depends(get_current_user)):
    uid = user["uid"]
    profile = await db.get_user_profile(uid)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")
    
    if request.tone_preference is not None:
        profile.tone_preference = request.tone_preference
    if request.global_alerts_enabled is not None:
        profile.global_alerts_enabled = request.global_alerts_enabled
        if getattr(profile, 'push_tokens', None):
            for token in profile.push_tokens:
                if profile.global_alerts_enabled:
                    await subscribe_token_to_topics(token, ["breaking_news", "global_alerts"])
                else:
                    await unsubscribe_token_from_topics(token, ["breaking_news", "global_alerts"])
    
    if request.category_alerts_enabled is not None:
        profile.category_alerts_enabled = request.category_alerts_enabled
    if request.trendy_alerts_enabled is not None:
        profile.trendy_alerts_enabled = request.trendy_alerts_enabled
    if request.summary_alerts_enabled is not None:
        profile.summary_alerts_enabled = request.summary_alerts_enabled
        
    await db.save_user_profile(profile)
    return profile


# ---------------------------------------------------------------------------
# Activity ping  (auth required)
# ---------------------------------------------------------------------------

@app.post(
    "/activity",
    summary="Update last_seen timestamp (called by frontend on each visit)",
    tags=["Feed"],
)
async def record_activity(request: Request, user=Depends(get_current_user)):
    """
    Lightweight endpoint called by the frontend on each page load.
    Updates the user's last_seen timestamp so the inactivity logic
    (7-day pause / 60-day cleanup) stays accurate without requiring
    the frontend to call the heavier /feed/me endpoint.
    Also accepts optional { installed_app: bool } to track PWA installs.
    """
    uid = user["uid"]
    await db.update_last_seen(uid)

    # Optionally update installed_app flag
    try:
        body = await request.json()
        if isinstance(body, dict) and "installed_app" in body:
            ref = db._db.collection("user_profiles").document(uid)
            await ref.set({"installed_app": body["installed_app"]}, merge=True)
    except Exception:
        pass  # No body or invalid JSON — that's fine

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
    "/admin/rss/retag",
    summary="Re-tag recent articles from Firestore with current schema (admin only)",
    tags=["Admin"],
    dependencies=[Depends(verify_admin)],
)
async def manual_rss_retag():
    """Fetch uncategorized articles from last 120 hours and tag them with Gemini."""
    articles_db = await db.get_recent_articles(hours=120)
    if not articles_db:
        return {"message": "No recent articles found in database"}
    uncategorized = [a for a in articles_db if not a.ai_tagged and not a.categories and not a.subcategories][:200]
    if not uncategorized:
        return {"message": "All recent articles have already been tagged!"}
    batch_size = 20
    total_updated = 0
    for i in range(0, len(uncategorized), batch_size):
        batch = uncategorized[i:i+batch_size]
        tagged_results = await tagging_agent.tag_articles(batch)
        total_updated += await db.save_articles(tagged_results)
        await asyncio.sleep(1)  # Pace requests to prevent Vertex AI rate limiting
    return {"message": f"Successfully tagged {total_updated} out of {len(uncategorized)} uncategorized articles"}


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
    "/admin/feed/rebuild/{uid}",
    summary="Trigger immediate feed rebuild for a specific user ID",
    tags=["Admin"],
    dependencies=[Depends(verify_admin)],
)
async def rebuild_single_user_feed(uid: str):
    await build_feed_for_single_user(uid)
    return {"message": f"Successfully rebuilt feed for user {uid}"}


@app.post(
    "/admin/test/push/{uid}",
    summary="Trigger a test push notification for a specific user ID",
    tags=["Admin"],
    dependencies=[Depends(verify_admin)],
)
async def test_push_for_single_user(uid: str):
    from firebase_admin import messaging as fcm_messaging
    profile = await db.get_user_profile(uid)
    if not profile:
        return {"error": "User not found"}
    if getattr(profile, 'push_tokens', None) is None or len(profile.push_tokens) == 0:
        return {"error": "User has no push tokens registered"}
    
    results = []
    for token in profile.push_tokens:
        try:
            msg = fcm_messaging.Message(
                notification=fcm_messaging.Notification(
                    title="UCKhabar Test",
                    body="This is a test notification. If you see this, push is working!"
                ),
                data={"tag": "test-push", "url": "/"},
                token=token
            )
            resp = fcm_messaging.send(msg)
            results.append({"token": token[:20] + "...", "status": "success", "response": str(resp)})
        except Exception as e:
            results.append({"token": token[:20] + "...", "status": "failed", "error": str(e)})
    
    return {"message": f"Push test for {uid}", "token_count": len(profile.push_tokens), "results": results}


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


@app.get(
    "/admin/analytics/summary",
    summary="Get aggregated counts of all hitpoints and analytics events (admin only)",
    tags=["Admin"],
    dependencies=[Depends(verify_admin)],
)
async def analytics_summary():
    """Fetch hitpoints breakdown from analytics_events in Firestore."""
    summary = await db.get_analytics_summary()
    return summary


# ---------------------------------------------------------------------------
# Health check  (public)
# ---------------------------------------------------------------------------

@app.get("/health", summary="Health check", tags=["System"])
async def health_check():
    return {
        "status":       "healthy",
        "service":      "UCKhabar API",
        "version":      "2.0.0",
        "environment":  settings.APP_ENV,
        "scheduler":    "managed by Google Cloud Scheduler (external)",
        "gemini_model": settings.GEMINI_MODEL,
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
