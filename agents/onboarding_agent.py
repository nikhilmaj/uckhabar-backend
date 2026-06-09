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

import google.generativeai as genai

from models.schemas import (
    OnboardingSession, UserProfile, TopicFilter, SentimentPreference
)

logger = logging.getLogger("uckhabar.onboarding")

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

ONBOARDING_SYSTEM_PROMPT = """You are the onboarding assistant for UCKhabar — a clean, distraction-free personal news app.

Your sole job: hold a warm, natural conversation to understand exactly what news the user wants to read every day.

RULES:
1. Be concise. This runs on mobile — 2 to 4 lines per response maximum.
2. Sound human, not like a form. No bullet lists. No numbered questions.
3. Ask about their main interests first, then naturally dig into specifics:
   - "What angle of [topic] interests you most?"
   - "Anything about [topic] you'd rather skip?"
4. Cover at least 2 to 3 distinct topic areas before wrapping up.
5. After 4 to 6 exchanges, summarise what you've heard clearly in plain English and ask: "Does this sound right?"
6. When the user confirms (yes / correct / looks good / perfect / etc.), end your reply with this EXACT marker on its own line:
   [PROFILE_COMPLETE]

Do NOT ask about news sources — that is handled separately.
Do NOT use bullet points or lists in your responses.
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

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash-preview-05-20"):
        genai.configure(api_key=api_key)

        # Chat model — carries system prompt and conversation history
        self._chat_model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=ONBOARDING_SYSTEM_PROMPT,
        )

        # Extraction model — single-shot, no system prompt needed
        self._extraction_model = genai.GenerativeModel(model_name=model_name)

        # session_id → (OnboardingSession, genai.ChatSession)
        self._sessions: Dict[str, Tuple[OnboardingSession, object]] = {}

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def start_session(self, user_id: str, name: Optional[str] = None) -> Tuple[str, str]:
        """
        Start a new onboarding session.
        Returns (session_id, first_ai_message).
        """
        session_id = str(uuid.uuid4())
        chat = self._chat_model.start_chat(history=[])

        # Seed the conversation with user context (not shown to the user)
        seed = f"The user's name is {name}. Begin the onboarding." if name else "Begin the onboarding."
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
            generation_config=genai.GenerationConfig(
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
