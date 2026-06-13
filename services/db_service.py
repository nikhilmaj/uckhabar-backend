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

        docs = (
            self._db.collection("articles")
            .where("fetched_at", ">=", cutoff_fetched)
            .stream()
        )

        articles: List[Article] = []
        async for doc in docs:
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
        Stamp the user's last_seen time and ensure scoring_paused is False.
        Called on every /feed/me and /profile/me request so the inactivity
        timer resets whenever a user opens the app.
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

    async def delete_user_data(self, user_id: str) -> None:
        """
        Hard-delete a user's profile and feed from Firestore.
        Called when a user has been inactive for >= 60 days.
        The user can re-onboard at any time — their auth account is untouched.
        """
        profile_ref = self._db.collection("user_profiles").document(user_id)
        feed_ref    = self._db.collection("user_feeds").document(user_id)
        await profile_ref.delete()
        await feed_ref.delete()
        logger.info(f"[DB] Deleted profile + feed for inactive user {user_id}")
