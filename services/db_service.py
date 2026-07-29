"""
UCKhabar — Firestore Database Service

Thin async wrapper around Cloud Firestore.
Uses AsyncClient so it plays nicely with FastAPI's event loop.

Collections:
  articles       — raw fetched articles (TTL: auto-cleaned after 48 h via Firestore TTL policy)
  user_profiles  — structured interest profiles built during onboarding
  user_feeds     — pre-built, ready-to-serve article feeds per user
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from google.cloud import firestore
from google.cloud.firestore_v1.async_client import AsyncClient

from models.schemas import Article, UserProfile, UserFeed

logger = logging.getLogger("uckhabar.db")


class DatabaseService:
    """
    All Firestore operations for UCKhabar.

    Initialise once at app startup and share across the app:
        db = DatabaseService(project_id="my-gcp-project")
    """

    def __init__(self, project_id: str):
        self._db: AsyncClient = firestore.AsyncClient(project=project_id)

    # -----------------------------------------------------------------------
    # Articles
    # -----------------------------------------------------------------------

    async def save_articles(self, articles: List[Article]) -> int:
        """
        Batch-upsert articles into Firestore.
        Uses merge=True so re-fetched articles don't overwrite existing records,
        EXCEPT for fetched_at which is always refreshed so recency queries work.
        Returns the number of articles written.

        Firestore batches are capped at 500 ops — we chunk automatically.

        IMPORTANT: fetched_at must be stored as a native datetime (not an ISO
        string) so that Firestore range queries (>= cutoff datetime) work correctly.
        model_dump(mode="json") would produce an ISO string — we handle this by
        building the dict manually and keeping fetched_at as a real datetime object.
        """
        if not articles:
            return 0

        total = 0
        chunk_size = 499   # stay safely under the 500-op limit

        for i in range(0, len(articles), chunk_size):
            chunk = articles[i : i + chunk_size]
            batch = self._db.batch()

            for article in chunk:
                ref = self._db.collection("articles").document(article.id)
                # Serialize to dict, then restore fetched_at as a real datetime
                # so Firestore stores it as a Timestamp (not a string).
                data = article.model_dump(mode="json")
                data["fetched_at"] = datetime.utcnow()   # always refresh; keeps recency window accurate
                if article.published_at is not None:
                    data["published_at"] = article.published_at   # keep as datetime too
                batch.set(ref, data, merge=True)
                total += 1

            await batch.commit()

        logger.info(f"[DB] Saved {total} articles to Firestore")
        return total

    async def get_existing_article_ids(self, article_ids: List[str]) -> set:
        """
        Given a list of article IDs, return the subset that already exist in Firestore.
        Used before Gemini tagging to skip articles that are already tagged —
        avoids re-sending the same articles to Gemini every 20 minutes.

        Uses Firestore batch get (one round trip for up to 100 docs at a time).
        """
        if not article_ids:
            return set()

        existing_ids: set = set()
        chunk_size = 100   # Firestore batch get handles up to ~300 but 100 is safe

        for i in range(0, len(article_ids), chunk_size):
            chunk = article_ids[i : i + chunk_size]
            refs = [self._db.collection("articles").document(aid) for aid in chunk]
            async for snap in self._db.get_all(refs):
                if snap.exists:
                    d = snap.to_dict() or {}
                    # Consider an article "existing" if it has already been processed by Gemini (ai_tagged=True)
                    # OR if it already has category or subcategory tags from a previous run.
                    if d.get("ai_tagged") is True or bool(d.get("categories")) or bool(d.get("subcategories")):
                        existing_ids.add(snap.id)

        logger.debug(f"[DB] {len(existing_ids)}/{len(article_ids)} articles already exist and are tagged in Firestore")
        return existing_ids

    async def refresh_article_timestamps(self, article_ids: List[str]) -> None:
        """
        Update ONLY fetched_at for existing articles so they stay within the
        72-hour recency window used by get_recent_articles.
        Does NOT overwrite categories/subcategories/content_type tags.
        Called for articles that are already tagged — avoids Gemini cost.
        """
        if not article_ids:
            return

        now = datetime.utcnow()
        chunk_size = 499
        count = 0
        batch = self._db.batch()

        for article_id in article_ids:
            ref = self._db.collection("articles").document(article_id)
            batch.update(ref, {"fetched_at": now})
            count += 1
            if count % chunk_size == 0:
                await batch.commit()
                batch = self._db.batch()

        if count % chunk_size != 0:
            await batch.commit()

        logger.debug(f"[DB] Refreshed fetched_at for {count} existing articles")


    async def get_article(self, article_id: str) -> Optional[Article]:
        """Fetch a specific article by ID."""
        doc = await self._db.collection("articles").document(article_id).get()
        if doc.exists:
            return Article(**doc.to_dict())
        return None

    async def update_article_full_story(self, article_id: str, full_story: dict) -> None:
        """Cache the AI-generated full story for an article."""
        await self._db.collection("articles").document(article_id).update({
            "full_story": full_story
        })

    async def get_recent_articles(self, hours: int = 24) -> List[Article]:
        """
        Return all articles fetched within the last `hours` hours AND
        published within the last 7 days.

        The dual filter ensures:
        - fetched_at: only articles from this polling window are considered
        - published_at: stale articles that slipped through ingest are excluded

        Note: fetched_at is stored as a native Firestore Timestamp (datetime),
        so the >= comparison with a Python datetime works correctly.
        """
        cutoff_fetched   = datetime.now(timezone.utc) - timedelta(hours=hours)
        cutoff_published = datetime.now(timezone.utc) - timedelta(days=7)

        query = (
            self._db.collection("articles")
            .where("fetched_at", ">=", cutoff_fetched)
            .order_by("fetched_at", direction=firestore.Query.DESCENDING)
            .limit(2000)
        )
        docs = await query.get()

        articles: List[Article] = []
        for doc in docs:
            try:
                d = doc.to_dict()
                published_at = d.get("published_at")
                if published_at and hasattr(published_at, 'utcoffset'):
                    # Ensure comparison is timezone-aware on both sides
                    if published_at.utcoffset() is None:
                        published_at = published_at.replace(tzinfo=timezone.utc)
                    if published_at < cutoff_published:
                        continue
                articles.append(Article(**d))
            except Exception as e:
                logger.debug(f"[DB] Skipping malformed article doc {doc.id}: {e}")

        logger.info(f"[DB] Retrieved {len(articles)} recent articles (last {hours}h, max 7d old)")
        return articles

    async def delete_old_articles(self, days: int = 7) -> int:
        """
        Delete all articles published more than `days` ago.
        Called by the daily cleanup scheduled job.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        docs = (
            self._db.collection("articles")
            .where("published_at", "<", cutoff)
            .stream()
        )
        
        deleted = 0
        batch = self._db.batch()
        
        async for doc in docs:
            batch.delete(doc.reference)
            deleted += 1
            if deleted % 499 == 0:
                await batch.commit()
                batch = self._db.batch()
                
        if deleted % 499 != 0:
            await batch.commit()
            
        logger.info(f"[DB] Deleted {deleted} articles older than {days} days")
        return deleted

    # -----------------------------------------------------------------------
    # User profiles
    # -----------------------------------------------------------------------

    async def save_user_profile(self, profile: UserProfile) -> None:
        """Create or update a user's interest profile."""
        ref = self._db.collection("user_profiles").document(profile.user_id)
        await ref.set(profile.model_dump(mode="json"), merge=True)
        logger.info(f"[DB] Profile saved for user {profile.user_id} "
                    f"({len(profile.topics)} topics)")

    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """Fetch a single user's profile. Returns None if not found."""
        ref = self._db.collection("user_profiles").document(user_id)
        doc = await ref.get()
        if doc.exists:
            return UserProfile(**doc.to_dict())
        return None

    async def get_all_user_profiles(self) -> List[UserProfile]:
        """
        Fetch all user profiles.
        Called by the scoring scheduler to build feeds for every user.
        """
        profiles: List[UserProfile] = []
        async for doc in self._db.collection("user_profiles").stream():
            try:
                profiles.append(UserProfile(**doc.to_dict()))
            except Exception as e:
                logger.debug(f"[DB] Skipping malformed profile {doc.id}: {e}")

        logger.info(f"[DB] Loaded {len(profiles)} user profiles")
        return profiles

    # -----------------------------------------------------------------------
    # User feeds
    # -----------------------------------------------------------------------

    async def save_user_feed(self, feed: UserFeed) -> None:
        """Overwrite a user's pre-built feed (latest always wins)."""
        ref = self._db.collection("user_feeds").document(feed.user_id)
        await ref.set(feed.model_dump(mode="json"))
        logger.info(f"[DB] Feed saved for user {feed.user_id} "
                    f"({feed.article_count} articles)")

    async def get_user_feed(self, user_id: str) -> Optional[UserFeed]:
        """Fetch the pre-built feed for a user. Returns None if not yet generated."""
        ref = self._db.collection("user_feeds").document(user_id)
        doc = await ref.get()
        if doc.exists:
            return UserFeed(**doc.to_dict())
        return None

    # -----------------------------------------------------------------------
    # User activity / lifecycle management
    # -----------------------------------------------------------------------

    async def update_last_seen(self, user_id: str) -> None:
        """
        Stamp the user's last_seen time ONLY.
        Does NOT touch scoring_paused — call unpause_user() explicitly when
        you want to resume scoring (e.g. in get_my_feed when a paused user returns).
        Called on every /feed/me and /profile/me request.
        """
        ref = self._db.collection("user_profiles").document(user_id)
        doc = await ref.get()
        if doc.exists:
            await ref.update({"last_seen": datetime.utcnow()})

    async def unpause_user(self, user_id: str) -> None:
        """
        Reset scoring_paused to False AND update last_seen.
        Only called explicitly from get_my_feed when a paused user returns.
        Keeping this separate from update_last_seen prevents a profile-page
        visit from silently clearing the paused state without triggering a rebuild.
        """
        ref = self._db.collection("user_profiles").document(user_id)
        doc = await ref.get()
        if doc.exists:
            await ref.update({
                "last_seen": datetime.utcnow(),
                "scoring_paused": False,
            })

    async def set_scoring_paused(self, user_id: str, paused: bool) -> None:
        """Mark a user as scoring-paused (inactive >7 days) or resume them."""
        ref = self._db.collection("user_profiles").document(user_id)
        doc = await ref.get()
        if doc.exists:
            await ref.update({"scoring_paused": paused})
            logger.info(f"[DB] scoring_paused={paused} for user {user_id}")

    async def delete_user_feed_only(self, user_id: str) -> None:
        """
        Hard-delete a user's feed from Firestore, but keep their profile.
        Called when returning a paused user (re-trigger build), or when
        pruning stale feeds for 60-day+ inactive users.
        The user profile is preserved so historical user records are kept.
        """
        feed_ref = self._db.collection("user_feeds").document(user_id)
        await feed_ref.delete()
        logger.info(f"[DB] Deleted feed for user {user_id} (profile kept)")

    async def get_analytics_summary(self) -> dict:
        """Aggregate hitpoint counts from analytics_events collection."""
        docs = await self._db.collection("analytics_events").get()
        total = 0
        counts = {}
        for d in docs:
            total += 1
            data = d.to_dict()
            ev = data.get("event", "unknown")
            counts[ev] = counts.get(ev, 0) + 1
        return {"total_events": total, "event_counts": counts}

