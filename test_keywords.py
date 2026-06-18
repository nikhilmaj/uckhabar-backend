from services.topic_taxonomy import get_keywords_for_profile, TAXONOMY

cats = ["Finance", "AI", "Science & Research", "Entertainment"]
subs = {
    "Finance": ["Indian Stock Markets", "Indian Economy", "Startups & Venture Capital", "Global Stock Markets"],
    "AI": ["ChatGPT & OpenAI", "Claude & Anthropic", "Gemini & Google AI"]
}

keywords = get_keywords_for_profile(cats, subs)
print(f"Number of keywords: {len(keywords)}")
print(keywords[:20])
