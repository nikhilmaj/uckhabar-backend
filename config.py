"""
UCKhabar — App Configuration

Reads from environment variables (or a local .env file for development).
A single `settings` singleton is imported everywhere in the app.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List


class Settings(BaseSettings):
    # ------------------------------------------------------------------
    # Gemini
    # ------------------------------------------------------------------
    GEMINI_MODEL:   str = Field(
        default="gemini-1.5-flash",
        description="Gemini model identifier"
    )

    # ------------------------------------------------------------------
    # Google Cloud
    # ------------------------------------------------------------------
    GCP_PROJECT_ID: str = Field(..., description="GCP project ID")
    GCP_REGION:     str = Field(default="asia-south1", description="GCP region for Vertex AI")

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------
    ADMIN_SECRET: str = Field(
        ...,
        description="Secret token required for /admin/* endpoints. Set via Cloud Run env var."
    )
    ALLOWED_ORIGINS: List[str] = Field(
        default=[
            "https://uckhabar.web.app",
            "https://uckhabar.firebaseapp.com",
            "http://localhost:5500",
            "http://localhost:3000",
        ],
        description="CORS allowed origins. Add your custom domain here if needed."
    )

    # ------------------------------------------------------------------
    # App
    # ------------------------------------------------------------------
    APP_ENV: str = Field(default="development")
    PORT:    int = Field(default=8080)

    # ------------------------------------------------------------------
    # Feed tuning
    # ------------------------------------------------------------------
    MAX_ARTICLES_PER_FEED:        int = Field(default=50,  description="Max headlines per user feed")
    RSS_POLL_INTERVAL_MINUTES:    int = Field(default=20,  description="How often to fetch + Gemini-tag RSS feeds (minutes)")
    SCORING_INTERVAL_MINUTES:     int = Field(default=30,  description="How often to run feed builder and distribute to users (minutes)")
    ARTICLE_RETENTION_HOURS:      int = Field(default=48,  description="How old articles can be before scoring ignores them")
    MAX_ARTICLES_PER_GEMINI_CALL: int = Field(default=60,  description="Batch size sent to Gemini per call")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
