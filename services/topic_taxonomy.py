"""
UCKhabar — Topic Taxonomy

Defines the full hierarchy of news categories, their subcategories,
and the RSS keyword filters used for pre-filtering articles before
they are sent to Gemini for semantic scoring.

Structure:
    TAXONOMY[category_name] = {
        "subcategories": {
            "subcategory_name": [keyword, keyword, ...],
            ...
        },
        "base_keywords": [keyword, ...]  # always included for this category
    }

Keywords are matched against article title + description (case-insensitive,
substring match). An article passes the filter if ANY keyword matches.

This file is the single source of truth. The frontend JS mirrors this
structure (as TOPIC_TAXONOMY constant) for the checkbox UI screens.
"""

from typing import Dict, List

TAXONOMY: Dict[str, Dict] = {

    "Geopolitics": {
        "base_keywords": [
            "geopolitics", "foreign policy", "international relations",
            "diplomatic", "sanctions", "conflict", "military", "war",
            "border", "alliance", "treaty", "sovereignty",
        ],
        "subcategories": {
            "Middle East": [
                "israel", "palestine", "palestin", "iran", "saudi arabia", "saudi",
                "yemen", "lebanon", "hezbollah", "hamas", "gaza", "west bank",
                "syria", "jordan", "iraq", "bahrain", "oman", "gulf cooperation",
                "netanyahu", "khamenei", "mbs", "arab", "idf", "houthi",
            ],
            "US-China Relations": [
                "taiwan", "south china sea", "tariff", "trade war", "xi jinping",
                "us china", "china us", "beijing washington", "decoupling",
                "tech ban", "chip export", "huawei", "tiktok ban", "china relations",
            ],
            "India-Pakistan": [
                "kashmir", "line of control", "loc", "pakistan army", "imf pakistan",
                "india pakistan", "surgical strike", "cross border", "uri",
                "pulwama", "atari border", "wagah", "indus water", "pakistan india",
            ],
            "Russia-Ukraine": [
                "ukraine", "zelensky", "putin", "nato", "crimea", "kyiv", "kharkiv",
                "russian troops", "war ukraine", "ukraine war", "russia ukraine",
                "donbas", "zaporizhzhia", "kherson", "odessa", "peace talks ukraine",
            ],
            "South Asia": [
                "bangladesh", "sri lanka", "nepal", "myanmar", "afghanistan",
                "bhutan", "maldives", "hasina", "rajapaksa", "rohingya",
                "south asia", "saarc", "bay of bengal",
            ],
            "Africa": [
                "ethiopia", "somalia", "sudan", "kenya", "nigeria", "sahel",
                "mozambique", "mali", "niger", "burkina faso", "congo", "drc",
                "african union", "sub saharan", "east africa", "west africa",
            ],
            "Europe": [
                "european union", "eu parliament", "uk politics", "france",
                "germany", "nato europe", "macron", "scholz", "ursula",
                "brexit", "ukraine aid europe", "eu sanctions", "europe",
            ],
        },
    },

    "Finance": {
        "base_keywords": [
            "economy", "economic", "finance", "financial", "market", "investment",
            "fiscal", "monetary", "revenue", "profit", "debt", "capital",
        ],
        "subcategories": {
            "Stock Markets": [
                "sensex", "nifty", "bse", "nse", "dow jones", "s&p 500", "nasdaq",
                "equity", "shares", "stock market", "market rally", "bull run",
                "bear market", "market crash", "ipo listing", "fii", "dii",
                "mutual fund", "trading", "demat",
            ],
            "Cryptocurrency": [
                "bitcoin", "ethereum", "crypto", "cryptocurrency", "blockchain",
                "defi", "web3", "binance", "coinbase", "solana", "altcoin",
                "nft", "stablecoin", "usdt", "digital currency", "crypto exchange",
                "crypto regulation", "sec crypto",
            ],
            "Indian Economy": [
                "rbi", "gdp india", "inflation india", "rupee", "fiscal deficit",
                "union budget", "gst", "india economy", "reserve bank", "cpi india",
                "rbi policy", "repo rate", "india growth", "economic survey",
                "government spending", "tax revenue india",
            ],
            "Global Economy": [
                "federal reserve", "fed rate", "ecb", "interest rate", "inflation",
                "recession", "imf", "world bank", "gdp growth", "global trade",
                "supply chain", "wto", "trade deficit", "current account",
                "stagflation", "economic slowdown",
            ],
            "Corporate News": [
                "earnings", "quarterly results", "merger", "acquisition", "ipo",
                "revenue growth", "operating profit", "ebitda", "board meeting",
                "ceo", "cfo", "layoff", "restructuring", "valuation", "deal",
                "takeover", "joint venture", "corporate", "annual report",
            ],
            "Banking": [
                "hdfc", "sbi", "icici", "axis bank", "rbi policy", "npa",
                "neft", "banking sector", "credit growth", "deposit rate",
                "loan", "nbfc", "microfinance", "banking reform", "bad loan",
                "banking crisis", "kotak", "yes bank", "pnb", "idbi",
            ],
            "Startups": [
                "startup india", "unicorn", "funding round", "venture capital",
                "series a", "series b", "series c", "angel invest", "valuation",
                "bootstrapped", "founder", "accelerator", "y combinator",
                "sequoia india", "tiger global", "startup ecosystem",
            ],
        },
    },

    "AI": {
        "base_keywords": [
            "artificial intelligence", "ai", "machine learning", "deep learning",
            "neural network", "large language model", "llm", "foundation model",
            "generative ai", "ai model", "ai system",
        ],
        "subcategories": {
            "ChatGPT": [
                "openai", "chatgpt", "gpt-4", "gpt-5", "gpt4", "gpt5",
                "sam altman", "openai ceo", "openai funding", "openai board",
                "chatgpt update", "openai api", "dalle", "sora openai",
            ],
            "Claude": [
                "anthropic", "claude ai", "dario amodei", "amanda askell",
                "claude 3", "claude sonnet", "claude opus", "anthropic funding",
                "constitutional ai", "anthropic safety",
            ],
            "Gemini": [
                "google gemini", "google ai", "bard google", "gemini ultra",
                "gemini pro", "gemini flash", "deepmind", "google llm",
                "sundar pichai ai", "google ai model", "vertex ai",
            ],
            "DeepSeek": [
                "deepseek", "deepseek r1", "deepseek v3", "deepseek ai",
                "deepseek china", "deepseek open source",
            ],
            "Other LLMs": [
                "mistral", "llama", "meta ai", "cohere", "ai21", "phi microsoft",
                "qwen alibaba", "grok xai", "elon musk ai", "falcon ai",
                "command r", "open source llm", "hugging face", "ollama",
            ],
            "Innovations": [
                "ai research", "ai safety", "alignment research", "agi",
                "superintelligence", "ai risk", "ai regulation", "eu ai act",
                "responsible ai", "ai ethics", "ai breakthrough", "ai paper",
                "arxiv ai", "ai laboratory", "research lab",
            ],
            "Advancements": [
                "diffusion model", "transformer model", "multimodal ai",
                "vision model", "text to image", "text to video", "ai agent",
                "agentic ai", "reasoning model", "chain of thought",
                "fine tuning", "rlhf", "ai benchmark", "ai performance",
            ],
        },
    },

    "Politics": {
        "base_keywords": [
            "politics", "political", "government", "parliament", "legislation",
            "policy", "minister", "president", "prime minister", "senator",
            "congress", "election", "vote", "democracy",
        ],
        "subcategories": {
            "Indian Politics": [
                "bjp", "congress party", "modi", "rahul gandhi", "lok sabha",
                "rajya sabha", "aap", "aam aadmi party", "tmc", "trinamool",
                "shiv sena", "nda", "upa", "india alliance", "yogi adityanath",
                "amit shah", "smriti irani", "arvind kejriwal", "mamata",
                "state government india", "india politics",
            ],
            "US Politics": [
                "trump", "biden", "kamala harris", "democrat", "republican",
                "us congress", "us senate", "white house", "maga", "gop",
                "supreme court us", "oval office", "us president",
                "nancy pelosi", "chuck schumer", "doge", "elon trump",
            ],
            "Elections": [
                "election", "voting", "ballot", "polls", "candidate",
                "constituency", "voter turnout", "exit poll", "election result",
                "campaign", "swing state", "electoral college", "by-election",
                "referendum", "general election",
            ],
            "Policy & Governance": [
                "government policy", "union budget", "legislation", "parliament session",
                "cabinet decision", "ordinance", "reform", "bill passed",
                "government scheme", "pli scheme", "make in india",
                "infrastructure policy", "public sector", "privatisation",
            ],
            "International Relations": [
                "diplomacy", "bilateral", "g20", "g7", "quad", "brics",
                "united nations general", "embassy", "foreign minister",
                "state visit", "diplomatic ties", "sanctions", "foreign aid",
                "trade agreement", "free trade", "mou signed",
            ],
        },
    },

    "Technology": {
        "base_keywords": [
            "technology", "tech", "digital", "software", "hardware",
            "innovation", "startup", "internet", "computing", "data",
        ],
        "subcategories": {
            "Cybersecurity": [
                "hack", "data breach", "ransomware", "malware", "cybersecurity",
                "phishing", "vulnerability", "zero-day", "cyberattack",
                "ddos", "data leak", "password breach", "security flaw",
                "cyber threat", "dark web", "identity theft", "cyber crime",
            ],
            "Space": [
                "isro", "nasa", "spacex", "rocket launch", "satellite",
                "mars mission", "moon mission", "gaganyaan", "chandrayaan",
                "artemis", "james webb", "starship", "blue origin",
                "space station", "iss", "astronaut", "spacecraft",
            ],
            "Electric Vehicles": [
                "tesla", "electric vehicle", "electric car", "ev adoption",
                "battery technology", "charging station", "ev sales",
                "range anxiety", "solid state battery", "byd", "rivian",
                "lucid motors", "ola electric", "tata ev", "mahindra ev",
            ],
            "Semiconductors": [
                "chip shortage", "semiconductor", "intel", "tsmc", "nvidia chip",
                "amd", "processor", "foundry", "fab plant", "chip manufacturing",
                "arm holdings", "qualcomm chip", "chip act", "chips and science",
                "wafer", "microchip", "gpu", "chip geopolitics",
            ],
            "Big Tech": [
                "apple", "google", "microsoft", "amazon", "meta",
                "alphabet", "antitrust tech", "big tech regulation",
                "app store", "android", "windows", "azure", "aws",
                "facebook", "instagram", "whatsapp", "youtube",
            ],
            "Tech Startups": [
                "silicon valley", "saas", "cloud computing", "fintech",
                "edtech", "healthtech", "proptech", "insuretech",
                "series a tech", "product launch", "app launch",
                "india tech", "bangalore startup", "hyderabad tech",
            ],
        },
    },

    "International News": {
        "base_keywords": [
            "international", "global", "world news", "foreign", "overseas",
            "cross border", "worldwide", "multinational",
        ],
        "subcategories": {
            "United Nations": [
                "united nations", "un security council", "un resolution",
                "secretary general", "un peacekeeping", "guterres",
                "general assembly", "unhcr", "who un", "unicef", "wfp",
                "un sanctions", "veto power", "p5",
            ],
            "Climate & Environment": [
                "climate change", "global warming", "cop28", "cop29", "cop30",
                "carbon emissions", "renewable energy", "net zero",
                "deforestation", "amazon rainforest", "arctic ice",
                "sea level rise", "extreme weather", "heatwave", "flood",
                "drought", "paris agreement", "carbon tax", "solar wind energy",
            ],
            "Human Rights": [
                "human rights", "amnesty international", "genocide", "war crimes",
                "refugees", "displaced persons", "persecution", "torture report",
                "icc", "international criminal court", "child labour",
                "press freedom", "journalists killed",
            ],
            "Global Conflicts": [
                "conflict zone", "ceasefire", "military operation",
                "peacekeeping", "arms deal", "weapons supply", "civil war",
                "rebel group", "insurgency", "coup", "regime change",
                "occupied territory", "siege",
            ],
        },
    },

    "Cricket": {
        "base_keywords": [
            "cricket", "icc", "bcci", "wicket", "innings", "over",
            "batting", "bowling", "fielding", "test", "odi", "t20",
        ],
        "subcategories": {
            "IPL": [
                "ipl", "indian premier league", "ipl auction", "ipl match",
                "franchise cricket", "ipl final", "ipl season", "ipl 2025",
                "csk", "mi", "rcb", "kkr", "dc", "srh", "pbks", "gt", "lsg", "rr",
                "dhoni", "bumrah ipl", "virat ipl",
            ],
            "Test Cricket": [
                "test match", "test series", "ashes", "border gavaskar trophy",
                "red ball cricket", "test championship", "wtc",
                "test debut", "test cricket", "five day",
            ],
            "ODI": [
                "one day international", "odi series", "cricket world cup",
                "50 over", "odi match", "champions trophy",
                "odi ranking", "odi squad",
            ],
            "T20 World Cup": [
                "t20 world cup", "icc t20 world cup", "twenty20 international",
                "t20 championship", "super 8", "t20 squad",
            ],
            "Indian Team": [
                "team india", "virat kohli", "rohit sharma", "bumrah",
                "shami", "hardik pandya", "sky suryakumar", "gill",
                "siraj", "jadeja", "ashwin", "india cricket",
            ],
            "International Teams": [
                "australia cricket", "england cricket", "pakistan cricket",
                "west indies", "south africa cricket", "new zealand cricket",
                "sri lanka cricket", "bangladesh cricket", "afghanistan cricket",
            ],
        },
    },

    "Football": {
        "base_keywords": [
            "football", "soccer", "match", "goal", "striker",
            "midfielder", "defender", "goalkeeper", "transfer", "league",
        ],
        "subcategories": {
            "Premier League": [
                "premier league", "epl", "arsenal", "manchester city",
                "chelsea", "liverpool", "tottenham", "man utd", "manchester united",
                "aston villa", "newcastle", "west ham", "everton",
            ],
            "La Liga": [
                "la liga", "barcelona", "real madrid", "atletico madrid",
                "sevilla", "villarreal", "laliga", "spain football",
                "vinicius", "bellingham", "lewandowski", "yamal",
            ],
            "FIFA": [
                "fifa", "world cup football", "world cup 2026",
                "qualify world cup", "fifa ranking", "infantino",
                "international break football",
            ],
            "Champions League": [
                "champions league", "ucl", "europa league", "european football",
                "cl final", "knockout round", "group stage ucl",
            ],
            "Indian Football": [
                "isl", "indian super league", "all india football", "aiff",
                "indian football team", "sunil chhetri", "blue tigers",
            ],
        },
    },

    "Other Sports": {
        "base_keywords": [
            "sport", "athlete", "championship", "tournament",
            "gold medal", "world record", "competition",
        ],
        "subcategories": {
            "Tennis": [
                "wimbledon", "us open tennis", "french open", "australian open",
                "atp", "wta", "grand slam", "federer", "nadal", "djokovic",
                "alcaraz", "sinner", "swiatek", "tennis final",
            ],
            "Formula 1": [
                "formula 1", "f1", "formula one", "ferrari f1",
                "mercedes f1", "red bull racing", "verstappen", "hamilton",
                "leclerc", "norris", "grand prix", "gp race", "monaco gp",
                "f1 championship",
            ],
            "Olympics": [
                "olympics", "olympic games", "ioc", "paris 2024",
                "los angeles 2028", "medal tally", "olympic gold",
                "olympic record", "olympic athlete", "olympic qualifier",
            ],
            "Basketball": [
                "nba", "basketball", "lebron james", "stephen curry",
                "kevin durant", "nba finals", "nba playoffs", "nba trade",
                "slam dunk", "three pointer",
            ],
            "Badminton": [
                "badminton", "bwf", "pv sindhu", "saina nehwal",
                "shuttler", "all england badminton", "thomas cup",
                "uber cup", "world badminton", "lakshya sen",
            ],
            "Wrestling & MMA": [
                "wwe", "wrestling", "ufc", "mma", "mixed martial arts",
                "heavyweight champion", "raw smackdown", "wrestlemania",
                "ufc fight night", "conor mcgregor",
            ],
        },
    },
}


def get_keywords_for_profile(
    selected_categories: list,
    selected_subcategories: dict,
) -> list:
    """
    Build a flat keyword list for use in the pre-filter.

    - If a category has NO specific subcategories selected → use base_keywords + ALL subcategory keywords
    - If specific subcategories ARE selected → use base_keywords + only those subcategory keywords
    """
    keywords = []
    for cat in selected_categories:
        cat_data = TAXONOMY.get(cat)
        if not cat_data:
            # Unknown category — just add the category name itself as a keyword
            keywords.append(cat.lower())
            continue

        keywords.extend(cat_data.get("base_keywords", []))
        chosen_subs = selected_subcategories.get(cat, [])

        if not chosen_subs:
            # No subcategory preference — include all subcategory keywords
            for kws in cat_data["subcategories"].values():
                keywords.extend(kws)
        else:
            # Only include keywords for chosen subcategories
            for sub in chosen_subs:
                kws = cat_data["subcategories"].get(sub, [])
                keywords.extend(kws)

    # Deduplicate
    return list(set(k.lower() for k in keywords))


def build_topics_from_selections(
    selected_categories: list,
    selected_subcategories: dict,
    ai_extras: str = None,
) -> list:
    """
    Convert checkbox selections into a list of TopicFilter-compatible dicts
    that can be passed to UserProfile.

    Each selected category becomes one TopicFilter where:
      - topic = category name
      - include = list of selected subcategory names (or empty if "All" selected)
    """
    from models.schemas import TopicFilter, SentimentPreference

    topics = []
    for cat in selected_categories:
        chosen_subs = selected_subcategories.get(cat, [])
        topics.append(TopicFilter(
            topic=cat,
            include=chosen_subs,   # empty list = interested in all subcategories
            exclude=[],
            sentiment=SentimentPreference.ANY,
        ))

    if ai_extras and ai_extras.strip():
        # Free-text extras become a separate catch-all topic
        topics.append(TopicFilter(
            topic=f"Additional interests: {ai_extras.strip()}",
            include=[],
            exclude=[],
            sentiment=SentimentPreference.ANY,
        ))

    return topics
