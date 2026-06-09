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
from datetime import datetime, timedelta
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
        Uses merge=True so re-fetched articles don't overwrite existing records.
        Returns the number of articles written.

        Firestore batches are capped at 500 ops — we chunk automatically.
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
                batch.set(ref, article.model_dump(mode="json"), merge=True)
                total += 1

            await batch.commit()

        logger.info(f"[DB] Saved {total} articles to Firestore")
        return total

    async def get_recent_articles(self, hours: int = 24) -> List[Article]:
        """
        Return all articles fetched within the last `hours` hours.
        This is the pool handed to the scoring agent.
        """
        cutoff = datetime.utcnow() - timedelta(hours=hours)

        docs = (
            self._db.collection("articles")
            .where("fetched_at", ">=", cutoff)
            .stream()
        )

        articles: List[Article] = []
        async for doc in docs:
            try:
                articles.append(Article(**doc.to_dict()))
            except Exception as e:
                logger.debug(f"[DB] Skipping malformed article doc {doc.id}: {e}")

        logger.info(f"[DB] Retrieved {len(articles)} recent articles (last {hours}h)")
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
