"""
UCKhabar — Core data models (Pydantic v2)
All the shared types used across agents, services, and API layer.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SentimentPreference(str, Enum):
    ANY      = "any"
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL  = "neutral"


# ---------------------------------------------------------------------------
# User / Profile models
# ---------------------------------------------------------------------------

class TopicFilter(BaseModel):
    """One topic the user cares about, with fine-grained include/exclude control."""
    topic:     str
    include:   List[str] = Field(default_factory=list,
                                  description="Specific angles/subtopics to prioritise")
    exclude:   List[str] = Field(default_factory=list,
                                  description="Specific angles/subtopics to avoid")
    sentiment: SentimentPreference = SentimentPreference.ANY


class UserProfile(BaseModel):
    """Structured interest profile built during onboarding."""
    user_id:           str
    name:              Optional[str] = None
    topics:            List[TopicFilter]
    preferred_sources: List[str] = Field(default_factory=list)
    language:          str = "en"
    created_at:        Optional[datetime] = None
    updated_at:        Optional[datetime] = None


# ---------------------------------------------------------------------------
# Article models
# ---------------------------------------------------------------------------

class Article(BaseModel):
    """A raw article fetched from an RSS feed."""
    id:           str                        # MD5 hash of URL — stable, dedup-safe
    title:        str
    description:  Optional[str] = None
    url:          str
    source:       str                        # "BBC", "The Hindu", etc.
    category:     Optional[str] = None
    published_at: Optional[datetime] = None
    fetched_at:   datetime = Field(default_factory=datetime.utcnow)


class ScoredArticle(BaseModel):
    """An article after Gemini has scored it for relevance to a specific user."""
    article_id:       str
    title:            str
    url:              str
    source:           str
    relevance_score:  float   # 0–10; only articles >= 6 are kept in feeds
    reason:           Optional[str] = None   # one-line explanation from Gemini
    published_at:     Optional[datetime] = None


class UserFeed(BaseModel):
    """Pre-built, ready-to-serve feed for one user."""
    user_id:       str
    articles:      List[ScoredArticle] = Field(default_factory=list)
    generated_at:  datetime = Field(default_factory=datetime.utcnow)
    article_count: int = 0


# ---------------------------------------------------------------------------
# Onboarding session
# ---------------------------------------------------------------------------

class OnboardingSession(BaseModel):
    """In-memory state for an active onboarding chat."""
    session_id:  str
    user_id:     str
    name:        Optional[str] = None
    messages:    List[Dict[str, str]] = Field(default_factory=list)
    is_complete: bool = False
    profile:     Optional[UserProfile] = None


# ---------------------------------------------------------------------------
# API request / response schemas
# ---------------------------------------------------------------------------

class StartOnboardingRequest(BaseModel):
    user_id: str
    name:    Optional[str] = None


class StartOnboardingResponse(BaseModel):
    session_id: str
    message:    str   # first AI greeting


class SendMessageRequest(BaseModel):
    session_id: str
    message:    str


class SendMessageResponse(BaseModel):
    message:     str
    is_complete: bool
    profile:     Optional[UserProfile] = None   # populated only when is_complete=True
