"""
UCKhabar — Article Tagging Agent (V2)

Replaces the old ScoringAgent.
Instead of scoring an article per user, this agent evaluates an article ONCE
when it is ingested. It tags the article with categories, subcategories, and 
content type booleans.

These tags are saved to Firestore and used by plain Python logic later to 
match against user preferences at zero additional AI cost.
"""

import json
import logging
import asyncio
from typing import List, Dict

import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

from models.schemas import Article

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
            "description": (a.description or "")[:400],   # trim for token efficiency
            "source":      a.source,
            "original_category": a.category or "",
        }
        for a in articles
    ]

    return f"""Tag these {len(articles)} news articles.

ARTICLES TO TAG:
{json.dumps(articles_payload, indent=2)}

TAGGING RULES:
1. categories: Array of strings. Must strictly be from this list: ["Geopolitics", "Finance", "AI", "Politics", "Technology", "International News", "Cricket", "Football", "Other Sports", "Video Gaming", "Automotive", "Agriculture & Rural"]. If none apply, use an empty array [].
2. subcategories: Array of strings. Extract specific topics (e.g. "Indian Economy", "Rockstar Games", "Startups & VC", etc.). Be specific but concise. Max 3.
3. content_type: Object with 5 exact boolean fields:
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
    Tags a batch of articles during ingestion using Gemini.

    Usage (called by the RSS polling job):
        agent = TaggingAgent(project_id=..., location=..., model_name=...)
        tagged_articles = await agent.tag_articles(articles)
    """

    def __init__(self, project_id: str, location: str, model_name: str = "gemini-2.5-flash"):
        vertexai.init(project=project_id, location=location)
        self._model = GenerativeModel(
            model_name=model_name,
            system_instruction=TAGGING_SYSTEM_PROMPT,
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
            response = await self._model.generate_content_async(
                prompt,
                generation_config=GenerationConfig(
                    response_mime_type="application/json",
                ),
            )
            raw_text = response.text.strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[-1].rsplit("\n", 1)[0]
            tags_data = json.loads(raw_text)
        except (json.JSONDecodeError, Exception) as e:
            # Graceful degradation — skip this batch rather than crashing
            logger.warning(f"Tagging batch failed: {e}")
            return

        for item in tags_data:
            article_id = item.get("article_id", "")
            if article_id not in article_map:
                continue   # Hallucinated ID — skip

            original = article_map[article_id]
            
            # Apply the tags to the original Article object
            original.categories = item.get("categories", [])
            original.subcategories = item.get("subcategories", [])
            
            ct = item.get("content_type", {})
            original.content_type = {
                "is_hard_news": bool(ct.get("is_hard_news", True)),
                "is_editorial": bool(ct.get("is_editorial", False)),
                "is_sponsored": bool(ct.get("is_sponsored", False)),
                "is_explicit": bool(ct.get("is_explicit", False)),
                "is_aggregated": bool(ct.get("is_aggregated", False))
            }
