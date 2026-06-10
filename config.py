"""
UCKhabar — App Configuration

Reads from environment variables (or a local .env file for development).
A single `settings` singleton is imported everywhere in the app.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # ------------------------------------------------------------------
    # Gemini
    # ------------------------------------------------------------------
    GEMINI_MODEL:   str = Field(
        default="gemini-2.5-flash",
        description="Gemini model identifier"
    )

    # ------------------------------------------------------------------
    # Google Cloud
    # ------------------------------------------------------------------
    GCP_PROJECT_ID: str = Field(..., description="GCP project ID")
    GCP_REGION:     str = Field(default="asia-south1", description="GCP region for Vertex AI")

    # ------------------------------------------------------------------
    # App
    # ------------------------------------------------------------------
    APP_ENV: str = Field(default="development")
    PORT:    int = Field(default=8080)

    # ------------------------------------------------------------------
    # Feed tuning
    # ------------------------------------------------------------------
    MAX_ARTICLES_PER_FEED:        int = Field(default=15,  description="Max headlines per user feed")
    RSS_POLL_INTERVAL_MINUTES:    int = Field(default=30,  description="How often to fetch RSS feeds")
    SCORING_INTERVAL_MINUTES:     int = Field(default=120, description="How often to run Gemini scoring (2 hrs)")
    ARTICLE_RETENTION_HOURS:      int = Field(default=24,  description="How old articles can be before scoring ignores them")
    MAX_ARTICLES_PER_GEMINI_CALL: int = Field(default=40,  description="Batch size sent to Gemini per call")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
