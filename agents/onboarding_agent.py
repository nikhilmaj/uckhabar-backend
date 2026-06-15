"""
UCKhabar — Onboarding Agent

Handles the one-time, multi-turn conversation that builds a user's interest profile.

Flow:
  1. start_session()  → returns session_id + first AI greeting
  2. send_message()   → user replies, AI continues until it signals [PROFILE_COMPLETE]
  3. _extract_profile() → second Gemini call converts conversation → structured JSON

Session state is held in memory (fine for single Cloud Run instance / MVP).
TODO: migrate _sessions to Firestore or Redis for multi-instance deployments.
"""

import json
import uuid
import logging
from datetime import datetime
from typing import Dict, Tuple, Optional

import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

from models.schemas import (
    OnboardingSession, UserProfile, TopicFilter, SentimentPreference
)

logger = logging.getLogger("uckhabar.onboarding")

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

ONBOARDING_SYSTEM_PROMPT = """You are the onboarding assistant for UCKhabar.

The user has already selected their main categories and subcategories using checkboxes. The system will provide these to you in its first hidden message.
Your job is to hold a warm, natural conversation to understand if there is anything ELSE specific they want to include or avoid (e.g. "I love AI, but no crypto", or "Only Indian test cricket").

RULES:
1. Be concise. 1 to 2 lines per response maximum.
2. Sound human, not like a form. No bullet lists.
3. Acknowledge what they've already selected briefly, then ask if they have any specific nuances, angles, or topics they want to add or exclude.
4. When the user provides a custom interest (e.g., "no editorials"), ALWAYS reply back to confirm their choice, summarize what it means (e.g. "Got it, you prefer factual reporting"), and ask if there's anything else. Do NOT end the conversation immediately after their first reply.
5. ONLY end the conversation when the user explicitly says they have nothing else to add, says "no", "that's it", or you have reached a natural conclusion.
6. When the chat is truly done, end your reply with this EXACT marker on its own line:
   [PROFILE_COMPLETE]

Keep it conversational and warm throughout."""


PROFILE_EXTRACTION_PROMPT = """You are a data extraction assistant.

Below is an onboarding conversation transcript. Extract the user's news interests and return ONLY a valid JSON object — no markdown, no explanation, just the JSON.

CONVERSATION:
{conversation}

Return this exact structure:
{{
  "topics": [
    {{
      "topic": "topic name (e.g. Artificial Intelligence)",
      "include": ["specific angle to include", "another angle"],
      "exclude": ["angle to avoid"],
      "sentiment": "any"
    }}
  ]
}}

RULES:
- "sentiment" must be exactly one of: "any", "positive", "negative", "neutral"
- "include" and "exclude" can be empty arrays []
- Extract ALL distinct topics mentioned, even briefly
- Be specific in include/exclude — use the exact angles the user mentioned
- Return ONLY the JSON object, nothing else"""


KEYWORD_EXTRACTION_PROMPT = """You are an expert news librarian. 
The user has provided a custom, free-form text describing their specific news interests.
Your job is to extract a list of 1-to-3 word POSITIVE keywords from their text that can be used to filter RSS articles.

CRITICAL RULES:
- ONLY extract keywords for topics the user WANTS to read about.
- Do NOT extract keywords for topics the user wants to AVOID or EXCLUDE (e.g. if they say "no politics", do not extract "politics").

USER INTERESTS:
{text}

Return ONLY a JSON array of strings. No markdown, no explanation.
Example: ["cricket", "ai startups", "spacex"]"""


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

class OnboardingAgent:
    """
    Manages multi-turn onboarding conversations with Gemini.

    Each session holds:
      - an OnboardingSession (messages, state, eventual profile)
      - a live Gemini ChatSession (stateful conversation history)
    """

    def __init__(self, project_id: str, location: str, model_name: str = "gemini-2.5-flash"):
        vertexai.init(project=project_id, location=location)

        # Chat model — carries system prompt and conversation history
        self._chat_model = GenerativeModel(
            model_name=model_name,
            system_instruction=ONBOARDING_SYSTEM_PROMPT,
        )

        # Extraction model — single-shot, no system prompt needed
        self._extraction_model = GenerativeModel(model_name=model_name)

        # session_id → (OnboardingSession, genai.ChatSession)
        self._sessions: Dict[str, Tuple[OnboardingSession, object]] = {}

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def start_session(
        self, 
        user_id: str, 
        name: Optional[str] = None,
        categories: Optional[list] = None,
        subcategories: Optional[dict] = None
    ) -> Tuple[str, str]:
        """
        Start a new onboarding session.
        Returns (session_id, first_ai_message).
        """
        session_id = str(uuid.uuid4())
        chat = self._chat_model.start_chat(history=[])

        # Seed the conversation with user context (not shown to the user)
        seed = f"The user's name is {name}. " if name else "The user is setting up their feed. "
        if categories:
            seed += f"They have ALREADY selected these main categories: {', '.join(categories)}. "
            if subcategories:
                seed += f"Specific subcategories selected: {json.dumps(subcategories)}. "
        seed += "Greet the user warmly, acknowledge their selections if any, and ask if there's anything specific they want to add or avoid."
        
        response = chat.send_message(seed)
        first_message = response.text.replace("[PROFILE_COMPLETE]", "").strip()

        session = OnboardingSession(
            session_id=session_id,
            user_id=user_id,
            name=name,
            messages=[{"role": "assistant", "content": first_message}],
        )
        self._sessions[session_id] = (session, chat)

        logger.info(f"Onboarding session started: {session_id} for user {user_id}")
        return session_id, first_message

    def send_message(
        self,
        session_id: str,
        user_message: str,
    ) -> Tuple[str, bool, Optional[UserProfile]]:
        """
        Forward a user message to the active Gemini chat.
        Returns (ai_response_text, is_complete, profile_or_None).

        When is_complete=True the profile is fully built and ready to save.
        """
        if session_id not in self._sessions:
            raise ValueError(f"Session '{session_id}' not found. Call start_session first.")

        session, chat = self._sessions[session_id]

        if session.is_complete:
            raise ValueError(f"Session '{session_id}' is already complete.")

        # Send user message to Gemini
        response = chat.send_message(user_message)
        raw_response = response.text

        # Record messages
        session.messages.append({"role": "user",      "content": user_message})
        session.messages.append({"role": "assistant",  "content": raw_response})

        # Detect completion signal
        is_complete = "[PROFILE_COMPLETE]" in raw_response
        clean_response = raw_response.replace("[PROFILE_COMPLETE]", "").strip()

        profile: Optional[UserProfile] = None
        if is_complete:
            logger.info(f"Session {session_id} complete. Extracting profile…")
            profile = self._extract_profile(session)
            session.is_complete = True
            session.profile = profile

        return clean_response, is_complete, profile

    def extract_keywords(self, ai_extras_text: str) -> list[str]:
        """
        Extract concise keywords from a free-form text of user interests.
        Used for V2 schemas to bolster the taxonomy-based pre-filter.
        """
        prompt = KEYWORD_EXTRACTION_PROMPT.format(text=ai_extras_text)
        try:
            response = self._extraction_model.generate_content(
                prompt,
                generation_config=GenerationConfig(
                    response_mime_type="application/json",
                ),
            )
            raw_text = response.text.strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[-1].rsplit("\n", 1)[0]
            keywords = json.loads(raw_text)
            if isinstance(keywords, list):
                # Ensure they are lowercase strings
                return [str(k).lower() for k in keywords]
            return []
        except Exception as e:
            logger.warning(f"Keyword extraction failed: {e}")
            return []

    def get_session(self, session_id: str) -> Optional[OnboardingSession]:
        """Return the session metadata (without the live chat object)."""
        entry = self._sessions.get(session_id)
        return entry[0] if entry else None

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _extract_profile(self, session: OnboardingSession) -> UserProfile:
        """
        Second Gemini call: convert raw conversation → structured UserProfile.
        Uses JSON mode for reliable parsing.
        """
        # Build a clean transcript string
        transcript = "\n".join(
            f"{msg['role'].upper()}: {msg['content']}"
            for msg in session.messages
        )

        prompt = PROFILE_EXTRACTION_PROMPT.format(conversation=transcript)

        response = self._extraction_model.generate_content(
            prompt,
            generation_config=GenerationConfig(
                response_mime_type="application/json",
            ),
        )

        data = json.loads(response.text)

        topics: list[TopicFilter] = []
        for t in data.get("topics", []):
            raw_sentiment = t.get("sentiment", "any")
            # Gracefully handle unexpected values
            valid_sentiments = {e.value for e in SentimentPreference}
            sentiment = raw_sentiment if raw_sentiment in valid_sentiments else "any"

            topics.append(TopicFilter(
                topic=t.get("topic", "General"),
                include=t.get("include", []),
                exclude=t.get("exclude", []),
                sentiment=SentimentPreference(sentiment),
            ))

        now = datetime.utcnow()
        return UserProfile(
            user_id=session.user_id,
            name=session.name,
            topics=topics,
            created_at=now,
            updated_at=now,
        )
