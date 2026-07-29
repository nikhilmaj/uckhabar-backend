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
from typing import List, Optional, Dict, Literal
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
    schema_version:          int  = Field(default=2, description="Profile schema version")
    user_id:                 str
    name:                    Optional[str] = None
    email:                   Optional[str] = None
    # Canonical scoring field — always present
    topics:                  List[TopicFilter] = Field(default_factory=list)
    # V2 UI fields — populated only for schema_version >= 2
    selected_categories:     List[str] = Field(default_factory=list)
    selected_subcategories:  Dict[str, List[str]] = Field(default_factory=dict)
    tone_preference:         Literal["formal", "light", "humorous", "bullets"] = "formal"
    global_alerts_enabled:   bool = True
    ai_extras:               Optional[str] = None
    ai_extras_keywords:      List[str] = Field(default_factory=list)
    # V2 Content Filters
    content_filters:         Dict[str, bool] = Field(default_factory=lambda: {
        "is_hard_news": True,
        "is_editorial": True,
        "is_sponsored": True,
        "is_explicit": True,
        "is_aggregated": True
    })
    # Metadata
    preferred_sources:       List[str] = Field(default_factory=list)
    language:                str = "en"
    created_at:              Optional[datetime] = None
    updated_at:              Optional[datetime] = None
    last_seen:               Optional[datetime] = None
    last_login_ip:           Optional[str] = None
    last_login_city:         Optional[str] = None
    last_login_country:      Optional[str] = None
    scoring_paused:          bool = False
    push_tokens:             List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Article models
# ---------------------------------------------------------------------------

class Article(BaseModel):
    """A raw article fetched from an RSS feed, with tags from Gemini."""
    id:           str                        # MD5 hash of URL — stable, dedup-safe
    title:        str
    description:  Optional[str] = None
    url:          str
    image_url:    Optional[str] = None
    source:       str                        # "BBC", "The Hindu", etc.
    category:     Optional[str] = None
    published_at: Optional[datetime] = None
    fetched_at:   datetime = Field(default_factory=datetime.utcnow)
    
    # V2 Tagging Fields (populated by tagging agent)
    ai_tagged:                bool = False
    is_breaking:              bool = False
    is_globally_significant:  bool = False
    categories:    List[str] = Field(default_factory=list)
    subcategories: List[str] = Field(default_factory=list)
    tags:          List[str] = Field(default_factory=list)
    entities:      List[str] = Field(default_factory=list)
    sentiment:     str = "neutral"
    
    # Feature 1: The Full Story Cache
    full_story:    Optional[Dict[str, Any]] = None
    
    content_type:  Dict[str, bool] = Field(default_factory=lambda: {
        "is_hard_news": True,
        "is_editorial": False,
        "is_sponsored": False,
        "is_explicit": False,
        "is_aggregated": False
    })


class ScoredArticle(BaseModel):
    """An article after being matched for relevance to a specific user."""
    article_id:               str
    title:                    str
    url:                      str
    image_url:                Optional[str] = None
    source:                   str
    relevance_score:          float   # 0-10; only articles >= 6 are kept in feeds
    published_at:             Optional[datetime] = None
    is_breaking:              bool = False
    is_globally_significant:  bool = False
    categories:               List[str] = Field(default_factory=list)
    subcategories:            List[str] = Field(default_factory=list)


class UserFeed(BaseModel):
    """Pre-built, ready-to-serve feed for one user."""
    user_id:       str
    user_name:     Optional[str] = None
    articles:      List[ScoredArticle] = Field(default_factory=list)
    generated_at:  datetime = Field(default_factory=datetime.utcnow)
    article_count: int = 0
    interval_summary:        Optional[str] = None
    interval_summary_window: Optional[str] = None


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
    selected_categories: Optional[List[str]] = None
    selected_subcategories: Optional[Dict[str, List[str]]] = None
    existing_ai_extras: Optional[str] = None


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
    tone_preference:         Literal["formal", "light", "humorous", "bullets"] = "formal"
    global_alerts_enabled:   bool = True
    ai_extras:               Optional[str] = None   # free-text from Screen 4 AI chat
    content_filters:         Dict[str, bool] = Field(default_factory=lambda: {
        "is_hard_news": True,
        "is_editorial": True,
        "is_sponsored": True,
        "is_explicit": True,
        "is_aggregated": True
    })


class CompleteOnboardingResponse(BaseModel):
    status:             str = "processing"
    estimated_minutes:  int = 4


class AuthenticatedUser(BaseModel):
    """Decoded Firebase ID token payload — returned by get_current_user dependency."""
    uid:     str
    email:   Optional[str] = None
    name:    Optional[str] = None
    picture: Optional[str] = None
