"""
UCKhabar — RSS Polling Service

Fetches the latest articles from UCKhabar's 5 curated news sources.
Runs every 30 minutes (free — no AI involved).
Results are stored in Firestore for the scoring agent to consume.

Sources chosen to cover:
  - India depth       → The Hindu
  - Western intl      → BBC
  - Markets / wire    → Reuters
  - Tech / geopolitics→ Telegraph
  - Gulf / non-Western→ Al Jazeera
"""

import asyncio
import hashlib
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional

import feedparser
import httpx

from models.schemas import Article

logger = logging.getLogger("uckhabar.rss")

# ---------------------------------------------------------------------------
# Source registry
# ---------------------------------------------------------------------------

RSS_SOURCES: dict[str, str] = {
    "The Hindu":  "https://www.thehindu.com/news/feeder/default.rss",
    "BBC":        "https://feeds.bbci.co.uk/news/rss.xml",
    "Reuters":    "https://news.google.com/rss/search?q=site:reuters.com",
    "Telegraph":  "https://www.telegraph.co.uk/rss.xml",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "CNBC":       "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "TechCrunch": "https://techcrunch.com/feed/",
    "VentureBeat": "https://feeds.feedburner.com/venturebeat/SZYF",
    "Times of India": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
    "Variety":    "https://variety.com/feed/",
}

REQUEST_TIMEOUT  = 12.0   # seconds per source
USER_AGENT       = "UCKhabar/1.0 (+https://uckhabar.in)"
MAX_DESCRIPTION  = 500    # chars — trim long descriptions to save Firestore bytes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _article_id(title: str) -> str:
    """Stable, collision-resistant ID from the article title (prevents duplicate tagging if URLs change)."""
    clean_title = re.sub(r'[^a-zA-Z0-9]+', '', title).lower()
    return hashlib.md5(clean_title.encode("utf-8")).hexdigest()


def _parse_rfc2822(date_str: Optional[str]) -> Optional[datetime]:
    """Parse an RFC 2822 date string into a naive UTC datetime."""
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        # Convert to UTC and strip tzinfo so it is naive, matching the rest of the app
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    except Exception:
        pass
    return None


def _extract_category(entry: dict) -> Optional[str]:
    """Pull first tag/category from an RSS entry if present."""
    tags = entry.get("tags", [])
    if tags:
        return tags[0].get("term") or tags[0].get("label")
    return None


# ---------------------------------------------------------------------------
# Single-source fetcher
# ---------------------------------------------------------------------------

async def fetch_rss_feed(source_name: str, feed_url: str) -> List[Article]:
    """
    Fetch one RSS feed and parse into Article objects.
    Returns an empty list on any error (graceful degradation — one broken
    source should not break the whole polling cycle).
    """
    articles: List[Article] = []

    try:
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            resp = await client.get(feed_url)
            resp.raise_for_status()
            raw_xml = resp.text

        feed = feedparser.parse(raw_xml)

        for entry in feed.entries:
            url = entry.get("link", "").strip()
            title = entry.get("title", "").strip()

            if not url or not title:
                continue   # skip malformed entries

            description = (
                entry.get("summary") or entry.get("description") or ""
            ).strip()[:MAX_DESCRIPTION]

            published_at = _parse_rfc2822(entry.get("published"))

            # Skip articles older than 5 days (or missing dates) to save Gemini tagging costs,
            # since feed_builder only uses articles from the last 120 hours.
            if not published_at or (datetime.utcnow() - published_at).days > 5:
                continue

            articles.append(Article(
                id=_article_id(title),
                title=title,
                description=description if description else None,
                url=url,
                source=source_name,
                category=_extract_category(entry),
                published_at=published_at,
                fetched_at=datetime.utcnow(),
            ))

        logger.info(f"[RSS] {source_name}: {len(articles)} articles fetched")

    except httpx.HTTPStatusError as e:
        logger.warning(f"[RSS] {source_name} HTTP {e.response.status_code}: {feed_url}")
    except httpx.RequestError as e:
        logger.warning(f"[RSS] {source_name} connection error: {e}")
    except Exception as e:
        logger.error(f"[RSS] {source_name} unexpected error: {e}")

    return articles


# ---------------------------------------------------------------------------
# All-sources fetcher
# ---------------------------------------------------------------------------

async def fetch_all_feeds() -> List[Article]:
    """
    Fetch all configured RSS feeds concurrently.
    Deduplicates by article ID before returning.

    Called by the 30-minute scheduler in main.py.
    """
    tasks = [
        fetch_rss_feed(name, url)
        for name, url in RSS_SOURCES.items()
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    seen: set[str] = set()
    unique: List[Article] = []

    for result in results:
        if not isinstance(result, list):
            continue   # gather returned an exception — already logged inside fetch_rss_feed
        for article in result:
            if article.id not in seen:
                seen.add(article.id)
                unique.append(article)

    logger.info(
        f"[RSS] Poll complete: {len(unique)} unique articles "
        f"from {len(RSS_SOURCES)} sources"
    )
    return unique
