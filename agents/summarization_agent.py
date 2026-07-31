import logging
import json
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types

from models.schemas import ScoredArticle

logger = logging.getLogger("uckhabar.summarization")

class SummarizationAgent:
    def __init__(self, project_id: str, location: str = "us-central1", model_name: str = "gemini-2.5-flash-lite"):
        self._model_name = model_name
        self._client = genai.Client(
            vertexai=True,
            project=project_id,
            location="us-central1",
        )

    async def generate_interval_summary(self, articles: List[ScoredArticle], tone: str) -> Optional[str]:
        if not articles:
            return None

        payload = ""
        for a in articles:
            payload += f"- Title: {a.title}\n  Source: {a.source}\n\n"

        tone = (tone or "").lower()
        if tone == "formal":
            sys_instruct = "You are a professional news anchor. Summarize the major developments in a clean, objective, journalistic style. Keep it to 3-5 sentences."
        elif tone == "humorous":
            sys_instruct = "You are a witty late-night talk show host. Give a clever, punchy summary of the news, including a lighthearted joke or pun if appropriate. Keep it to 3-5 sentences."
        elif tone == "bullets":
            sys_instruct = "You are a busy executive assistant. Provide a concise, bulleted list of the top highlights. No introductory text, just the bullet points. Maximum 4 bullets."
        else: # "light" or default
            sys_instruct = "You are a friendly, conversational companion. Catch the reader up on the news in a casual, easy-going tone. Keep it to 3-5 sentences."

        prompt = f"Here are the top news articles from the recent interval. Please summarize them according to your persona.\n\nARTICLES:\n{payload}"

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=sys_instruct,
                    temperature=0.7
                )
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"[SummarizationAgent] Failed to generate interval summary: {e}")
            return None

    async def get_full_story(self, article_title: str, article_source: str, article_snippet: str = "") -> Optional[Dict[str, Any]]:
        sys_instruct = (
            "You are a master news researcher and context provider. "
            "You are given a current news headline and snippet. "
            "Using your vast world knowledge, find the backstory, significance, and timeline of events leading up to this. "
            "Return ONLY a JSON object with this exact schema:\n"
            "{\n"
            '  "current_status": "1-line summary of what is happening now (based on the snippet)",\n'
            '  "story_so_far": "2-3 sentences explaining the origins, key players, and backstory",\n'
            '  "why_it_matters": "1-sentence explaining why this is significant",\n'
            '  "timeline": ["Chronological event 1", "Chronological event 2", "Chronological event 3"],\n'
            '  "main_entity_wikipedia_search_term": "Exact name of the primary subject for a Wikipedia search (e.g. \'Roger Federer\', \'Nvidia\', \'India\'), or empty string if none."\n'
            "}"
        )
        prompt = f"Headline: {article_title}\nSource: {article_source}\nSnippet: {article_snippet}\n\nPlease generate the full story context and return the requested JSON."
        try:
            # We use flash-lite (no search grounding) for ultra-low latency & cost
            response = await self._client.aio.models.generate_content(
                model=self._model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=sys_instruct,
                    response_mime_type="application/json",
                    temperature=0.3
                )
            )
            raw_text = response.text.strip()
            
            # Find JSON block purely by braces to ignore any markdown or intro text
            start_idx = raw_text.find('{')
            end_idx = raw_text.rfind('}')
            
            if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
                json_str = raw_text[start_idx:end_idx+1]
                return json.loads(json_str)
            else:
                logger.error(f"[SummarizationAgent] Could not find JSON braces in response: {raw_text}")
                return None
                
        except Exception as e:
            logger.error(f"[SummarizationAgent] Failed to generate full story. Exception: {e}")
            return None
