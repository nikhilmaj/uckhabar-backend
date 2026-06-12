"""
UCKhabar — Core data models (Pydantic v2)
All the shared types used across agents, services, and API layer.

Schema versioning:
  v1 — AI-only onboarding (free-form topics list, no selected_categories)
  v2 — Structured onboarding (selected_categories + subcategories + topics built from taxonomy)

The `topics` field is ALWAYS the canonical source for scoring. All other
fields (selected_categories, selected_subcategories) are UI helpers.
This ensures backward compatibility: old v1 profiles continue to score
correctly even after the v2 migration.
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
    """Structured interest profile built during onboarding.

    schema_version:
        1 = legacy AI-only onboarding (only `topics` populated)
        2 = structured onboarding (selected_categories + topics populated)

    Scoring always reads from `topics` — never from selected_categories directly.
    This ensures old v1 profiles continue to work without any migration.
    """
    schema_version:          int  = Field(default=1, description="Profile schema version")
    user_id:                 str
    name:                    Optional[str] = None
    # Canonical scoring field — always present
    topics:                  List[TopicFilter] = Field(default_factory=list)
    # V2 UI fields — populated only for schema_version >= 2
    selected_categories:     List[str] = Field(default_factory=list)
    selected_subcategories:  Dict[str, List[str]] = Field(default_factory=dict)
    ai_extras:               Optional[str] = None
    # Metadata
    preferred_sources:       List[str] = Field(default_factory=list)
    language:                str = "en"
    created_at:              Optional[datetime] = None
    updated_at:              Optional[datetime] = None
    last_seen:               Optional[datetime] = None
    scoring_paused:          bool = False


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
    relevance_score:  float   # 0-10; only articles >= 6 are kept in feeds
    reason:           Optional[str] = None   # one-line explanation from Gemini
    published_at:     Optional[datetime] = None


class UserFeed(BaseModel):
    """Pre-built, ready-to-serve feed for one user."""
    user_id:       str
    user_name:     Optional[str] = None
    articles:      List[ScoredArticle] = Field(default_factory=list)
    generated_at:  datetime = Field(default_factory=datetime.utcnow)
    article_count: int = 0


# ---------------------------------------------------------------------------
# Onboarding session (AI chat state, stored in-memory)
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
    # user_id is NOT here — it comes from the Firebase auth token
    name: Optional[str] = None   # display name override (optional)


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


class CompleteOnboardingRequest(BaseModel):
    """
    Structured onboarding payload sent after the checkbox + AI chat flow.
    The backend converts this into a full UserProfile with topics built from
    the taxonomy keywords for each selected category/subcategory.
    """
    name:                    Optional[str] = None
    selected_categories:     List[str]
    selected_subcategories:  Dict[str, List[str]] = Field(default_factory=dict)
    ai_extras:               Optional[str] = None   # free-text from Screen 4 AI chat


class CompleteOnboardingResponse(BaseModel):
    status:             str = "processing"
    estimated_minutes:  int = 4


class AuthenticatedUser(BaseModel):
    """Decoded Firebase ID token payload — returned by get_current_user dependency."""
    uid:     str
    email:   Optional[str] = None
    name:    Optional[str] = None
    picture: Optional[str] = None
