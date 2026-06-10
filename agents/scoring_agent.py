"""
UCKhabar — Article Scoring Agent

Scores a pool of RSS articles against a user's interest profile using Gemini.

Two-stage pipeline (cost-optimised):
  Stage 1 — keyword_prefilter()  : free, instant, eliminates ~60 % of articles
  Stage 2 — score_articles()     : single batched Gemini call per user (or cluster)

Only articles scoring >= 6 / 10 survive into the final feed.
"""

import json
import logging
from typing import List, Dict, Optional

import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

from models.schemas import Article, ScoredArticle, UserProfile

logger = logging.getLogger("uckhabar.scoring")

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SCORING_SYSTEM_PROMPT = (
    "You are a precision news relevance engine for UCKhabar. "
    "Score articles strictly against the user's interest profile. "
    "If the profile is broad, allow major headlines to pass. "
    "Always return valid JSON."
)

def _build_scoring_prompt(profile: UserProfile, articles: List[Article]) -> str:
    if not profile.topics:
        profile_payload = {
            "topics": [
                {
                    "topic": "General News, Top Stories, World Events",
                    "must_include_angles": [],
                    "must_exclude_angles": [],
                    "sentiment_preference": "any",
                }
            ]
        }
    else:
        profile_payload = {
            "topics": [
                {
                    "topic": t.topic,
                    "must_include_angles": t.include,
                    "must_exclude_angles": t.exclude,
                    "sentiment_preference": t.sentiment.value,
                }
                for t in profile.topics
            ]
        }

    articles_payload = [
        {
            "id":          a.id,
            "title":       a.title,
            "description": (a.description or "")[:300],   # trim for token efficiency
            "source":      a.source,
            "category":    a.category or "",
        }
        for a in articles
    ]

    return f"""Score these {len(articles)} news articles for the user based on their interest profile.

USER INTEREST PROFILE:
{json.dumps(profile_payload, indent=2)}

ARTICLES TO SCORE:
{json.dumps(articles_payload, indent=2)}

SCORING RULES:
- Score 0–10 where 10 = perfect match, 0 = completely irrelevant.
- Penalise heavily if the article matches any "must_exclude_angles".
- Reward articles that match "must_include_angles" for the relevant topic.
- Apply sentiment preference if it is not "any".
- ONLY include articles with score >= 6 in the output.
- Sort results by score, highest first.

Return ONLY a JSON array (no markdown, no explanation):
[
  {{"article_id": "...", "score": 8.5, "reason": "one short sentence"}},
  ...
]

If nothing is relevant, return an empty array: []"""


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

COMMON_STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
    "for", "of", "with", "by", "from", "as", "is", "it", "its",
    "be", "was", "are", "were", "has", "have", "had", "that", "this",
}


class ScoringAgent:
    """
    Scores a batch of articles against a user profile using Gemini.

    Usage (called by the 2-hour scheduler in main.py):
        agent = ScoringAgent(api_key=..., model_name=...)
        scored = agent.score_articles(profile, articles)
        top_feed = scored[:15]   # keep top N
    """

    def __init__(self, project_id: str, location: str, model_name: str = "gemini-2.5-flash"):
        vertexai.init(project=project_id, location=location)
        self._model = GenerativeModel(
            model_name=model_name,
            system_instruction=SCORING_SYSTEM_PROMPT,
        )

    # -----------------------------------------------------------------------
    # Stage 1 — keyword pre-filter (free)
    # -----------------------------------------------------------------------

    def keyword_prefilter(
        self,
        profile: UserProfile,
        articles: List[Article],
    ) -> List[Article]:
        """
        Eliminates obviously irrelevant articles without any API call.
        Articles that pass are sent to Gemini for precise scoring.

        Logic:
          - Build a keyword set from all topic names and include-angles.
          - Any article whose title/description/category contains at least one
            keyword is kept.
          - If the profile has very few keywords (<= 3), we skip filtering
            entirely to avoid over-restricting broad profiles.
        """
        keywords: set[str] = set()
        for topic in profile.topics:
            for word in topic.topic.lower().split():
                keywords.add(word)
            for angle in topic.include:
                for word in angle.lower().split():
                    keywords.add(word)

        # Remove stop words to avoid matching everything
        keywords -= COMMON_STOP_WORDS

        # Bypass keyword prefilter for the MVP to allow semantic matching
        # since the article pool is small enough.
        return articles

        filtered: List[Article] = []
        for article in articles:
            searchable = " ".join([
                article.title,
                article.description or "",
                article.category or "",
            ]).lower()

            if any(kw in searchable for kw in keywords):
                filtered.append(article)

        logger.debug(
            f"Keyword pre-filter: {len(articles)} → {len(filtered)} articles "
            f"(removed {len(articles) - len(filtered)})"
        )
        return filtered

    # -----------------------------------------------------------------------
    # Stage 2 — Gemini scoring
    # -----------------------------------------------------------------------

    def score_articles(
        self,
        profile: UserProfile,
        articles: List[Article],
        max_per_batch: int = 40,
    ) -> List[ScoredArticle]:
        """
        Full pipeline: pre-filter → batch Gemini scoring → sorted results.

        `max_per_batch` caps articles per Gemini call to stay within token limits.
        Large article pools are split into multiple calls automatically.

        Returns articles sorted by relevance_score DESC (highest first).
        Only articles with score >= 6 are returned.
        """
        if not articles:
            return []

        # Stage 1 — cheap keyword filter
        candidates = self.keyword_prefilter(profile, articles)
        if not candidates:
            logger.info(f"No articles passed pre-filter for user {profile.user_id}")
            return []

        article_map: Dict[str, Article] = {a.id: a for a in candidates}
        all_scored: List[ScoredArticle] = []

        # Stage 2 — batch Gemini scoring
        for i in range(0, len(candidates), max_per_batch):
            batch = candidates[i : i + max_per_batch]
            logger.info(
                f"Scoring batch {i // max_per_batch + 1} "
                f"({len(batch)} articles) for user {profile.user_id}"
            )
            batch_results = self._score_batch(profile, batch, article_map)
            all_scored.extend(batch_results)

        # Sort highest relevance first
        all_scored.sort(key=lambda x: x.relevance_score, reverse=True)

        logger.info(
            f"Scoring complete for user {profile.user_id}: "
            f"{len(candidates)} candidates → {len(all_scored)} relevant articles"
        )
        return all_scored

    def _score_batch(
        self,
        profile: UserProfile,
        articles: List[Article],
        article_map: Dict[str, Article],
    ) -> List[ScoredArticle]:
        """Single Gemini API call for one batch of articles."""
        prompt = _build_scoring_prompt(profile, articles)

        try:
            response = self._model.generate_content(
                prompt,
                generation_config=GenerationConfig(
                    response_mime_type="application/json",
                ),
            )
            raw_text = response.text.strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[-1].rsplit("\n", 1)[0]
            scores_data = json.loads(raw_text)
        except (json.JSONDecodeError, Exception) as e:
            # Graceful degradation — skip this batch rather than crashing
            logger.warning(f"Scoring batch failed for user {profile.user_id}: {e}")
            return []

        scored: List[ScoredArticle] = []
        for item in scores_data:
            article_id = item.get("article_id", "")
            score = float(item.get("score", 0))

            if score < 6.0:
                continue   # Gemini shouldn't send these, but double-check

            if article_id not in article_map:
                continue   # Hallucinated ID — skip

            original = article_map[article_id]
            scored.append(ScoredArticle(
                article_id=original.id,
                title=original.title,
                url=original.url,
                source=original.source,
                relevance_score=score,
                reason=item.get("reason"),
                published_at=original.published_at,
            ))

        return scored
