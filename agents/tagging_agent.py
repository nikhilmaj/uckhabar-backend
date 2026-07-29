"""
UCKhabar — Article Tagging Agent (V2)

Replaces the old ScoringAgent.
Instead of scoring an article per user, this agent evaluates an article ONCE
when it is ingested. It tags the article with categories, subcategories, and 
content type booleans.

These tags are saved to Firestore and used by plain Python logic later to 
match against user preferences at zero additional AI cost.

SDK: Uses the google-genai SDK (Vertex AI backend) instead of the deprecated
vertexai SDK which was removed June 24, 2026.
"""

import json
import logging
import asyncio
from pydantic import BaseModel
from typing import List, Dict, Literal

from google import genai
from google.genai import types

from models.schemas import Article

CategoryEnum = Literal[
    "Geopolitics", "Finance", "AI", "Politics", "Technology", "Science & Research", 
    "Health & Medicine", "Business & Industry", "Defence & Military", "Environment & Climate", 
    "International News", "Law & Justice", "Social Issues", "Entertainment", "Cricket", 
    "Football", "Other Sports", "Video Gaming", "Automotive", "Agriculture & Rural"
]

class ContentTypeTag(BaseModel):
    is_hard_news: bool
    is_editorial: bool
    is_sponsored: bool
    is_explicit: bool
    is_aggregated: bool

class ArticleTag(BaseModel):
    article_id: str
    categories: List[CategoryEnum]
    subcategories: List[str]
    content_type: ContentTypeTag
    is_breaking: bool = False
    is_globally_significant: bool = False


logger = logging.getLogger("uckhabar.tagging")

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

TAGGING_SYSTEM_PROMPT = (
    "You are a precision news classification engine for UCKhabar. "
    "Your job is to tag incoming news articles with specific categories, "
    "subcategories, and content-type flags. "
    "Always return valid JSON."
)

def _build_tagging_prompt(articles: List[Article]) -> str:
    articles_payload = [
        {
            "id":          a.id,
            "title":       a.title,
            "description": (a.description or "")[:180],   # trim for token efficiency
            "source":      a.source,
            "original_category": a.category or "",
        }
        for a in articles
    ]

    return f"""Tag these {len(articles)} news articles.

ARTICLES TO TAG:
{json.dumps(articles_payload, indent=2)}

TAGGING RULES:
1. categories: Array of strings. Must strictly be from this list: ["Geopolitics", "Finance", "AI", "Politics", "Technology", "Science & Research", "Health & Medicine", "Business & Industry", "Defence & Military", "Environment & Climate", "International News", "Law & Justice", "Social Issues", "Entertainment", "Cricket", "Football", "Other Sports", "Video Gaming", "Automotive", "Agriculture & Rural"]. If none apply, use an empty array [].
   - CRITICAL RULE FOR "Business & Industry": Only apply "Business & Industry" to corporate news, company financial reports, startups, mergers & acquisitions, private sector manufacturing, corporate strategy, or commercial enterprises. Do NOT tag "Business & Industry" for municipal utilities (water boards, electricity distribution complaints), government civic infrastructure, railway/highway redevelopment by public authorities, or political party demands regarding civic projects.
2. subcategories: Array of strings. Extract specific topics (e.g. "Indian Economy", "Rockstar Games", "Startups & VC", etc.). Be specific but concise. Max 3.
3. is_breaking: Boolean. true ONLY for genuine national or international emergencies of very high public impact — e.g. a war declaration, a major terror attack, a sitting head-of-state dying, a catastrophic natural disaster, a major financial market collapse, or a historic election result.
   STRICT EXCLUSIONS for is_breaking (always false for these):
   - Any sports play-by-play: wickets taken, goals scored, match scores, innings updates, player statistics
   - Any sports match starting, ending, or a team winning a series/tournament (unless it is a historic World Cup final moment of truly national significance AND no other article about the same match has already been flagged breaking)
   - Press conferences, previews, squad announcements, transfer rumours
   - Stock market routine updates, company earnings, product launches
   - Celebrity news, award shows, box office results
   - Opinion pieces, editorials, analysis articles
   - Any article that is clearly a follow-up or update to an already-known ongoing story (e.g. day-3 of an ongoing war)
4. is_globally_significant: Boolean. true if this story is a major world event that every person regardless of their interests should know about — even if it is NOT breaking in the emergency sense. Examples: a war escalating significantly, a major earthquake killing hundreds, a landmark international agreement, a historic scientific discovery. Routine political news, cricket scores, market movements are NOT globally significant.
5. content_type: Object with 5 exact boolean fields:
   - "is_hard_news": true if factual reporting on events, false otherwise.
   - "is_editorial": true if opinion, analysis, or editorial.
   - "is_sponsored": true if promotional, PR, or sponsored content.
   - "is_explicit": true if contains graphic violence, crime, or sensitive mature content.
   - "is_aggregated": true if just a summary/roundup of other news.

Return ONLY a JSON array matching this exact schema for each article:
[
  {{
    "article_id": "...",
    "categories": ["Finance"],
    "subcategories": ["Indian Economy", "RBI"],
    "is_breaking": false,
    "is_globally_significant": false,
    "content_type": {{
      "is_hard_news": true,
      "is_editorial": false,
      "is_sponsored": false,
      "is_explicit": false,
      "is_aggregated": false
    }}
  }},
  ...
]"""


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

class TaggingAgent:
    """
    Tags a batch of articles during ingestion using Gemini via the google-genai SDK.

    Usage (called by the RSS polling job):
        agent = TaggingAgent(project_id=..., location=..., model_name=...)
        tagged_articles = await agent.tag_articles(articles)
    """

    def __init__(self, project_id: str, location: str = "us-central1", model_name: str = "gemini-2.5-flash-lite"):
        self._model_name = model_name
        self._system_instruction = TAGGING_SYSTEM_PROMPT
        # Use Vertex AI backend in us-central1 where Gemini models are reliably hosted
        self._client = genai.Client(
            vertexai=True,
            project=project_id,
            location="us-central1",
        )

    async def tag_articles(self, articles: List[Article], max_per_batch: int = 40) -> List[Article]:
        """
        Takes raw articles, batches them, calls Gemini to get tags, 
        and populates the fields on the Article objects in-place.
        Returns the mutated list of articles.
        """
        if not articles:
            return []

        article_map: Dict[str, Article] = {a.id: a for a in articles}
        tasks = []
        
        for i in range(0, len(articles), max_per_batch):
            batch = articles[i : i + max_per_batch]
            logger.info(f"Queuing tagging batch {i // max_per_batch + 1} ({len(batch)} articles)")
            tasks.append(self._tag_batch(batch, article_map))
        
        await asyncio.gather(*tasks)
        
        logger.info(f"Tagging complete for {len(articles)} articles.")
        return articles

    async def _tag_batch(
        self,
        articles: List[Article],
        article_map: Dict[str, Article],
    ) -> None:
        """Single Gemini API call for one batch of articles. Mutates the articles in article_map."""
        prompt = _build_tagging_prompt(articles)

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self._system_instruction,
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            raw_text = response.text.strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[-1].rsplit("\n", 1)[0]
            tags_data = json.loads(raw_text)
        except (json.JSONDecodeError, Exception) as e:
            # Graceful degradation — skip this batch rather than crashing ingestion
            logger.warning(f"Tagging batch failed: {e}")
            return

        for a in articles:
            a.ai_tagged = True

        for item in tags_data:
            article_id = item.get("article_id", "")
            if article_id not in article_map:
                continue   # Hallucinated ID — skip

            original = article_map[article_id]
            
            # Apply the tags to the original Article object
            original.categories = item.get("categories", [])
            original.subcategories = item.get("subcategories", [])
            original.is_breaking = bool(item.get("is_breaking", False))
            original.is_globally_significant = bool(item.get("is_globally_significant", False))
            
            ct = item.get("content_type", {})
            original.content_type = {
                "is_hard_news": bool(ct.get("is_hard_news", True)),
                "is_editorial": bool(ct.get("is_editorial", False)),
                "is_sponsored": bool(ct.get("is_sponsored", False)),
                "is_explicit":  bool(ct.get("is_explicit", False)),
                "is_aggregated": bool(ct.get("is_aggregated", False))
            }
