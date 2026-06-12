"""
UCKhabar — Topic Taxonomy (Comprehensive Edition)

Full hierarchy of news categories → subcategories → RSS keyword filters.
Used by:
  1. The scoring agent to pre-filter articles before Gemini scoring
  2. The /onboarding/complete endpoint to build UserProfile.topics

Structure:
    TAXONOMY[category_name] = {
        "base_keywords": [always matched for this category],
        "subcategories": {
            "subcategory_name": [keyword, keyword, ...]
        }
    }

Keywords are matched against article title + description (case-insensitive substring).
An article passes the filter if ANY keyword matches.
"""

from typing import Dict, List

TAXONOMY: Dict[str, Dict] = {

    # ─────────────────────────────────────────────────────────────
    "Geopolitics": {
        "base_keywords": [
            "geopolitics", "foreign policy", "international relations",
            "diplomatic", "sanctions", "conflict", "military", "war",
            "border", "alliance", "treaty", "sovereignty", "coup",
            "insurgency", "ceasefire", "occupation", "annexed",
        ],
        "subcategories": {
            "Middle East": [
                "israel", "palestine", "palestin", "iran", "saudi arabia", "saudi",
                "yemen", "lebanon", "hezbollah", "hamas", "gaza", "west bank",
                "syria", "jordan", "iraq", "bahrain", "oman", "gulf cooperation",
                "netanyahu", "khamenei", "mbs", "arab", "idf", "houthi",
                "qatar", "kuwait", "uae", "abu dhabi", "dubai conflict",
                "red sea attack", "strait of hormuz",
            ],
            "US-China Relations": [
                "taiwan", "south china sea", "tariff china", "trade war",
                "xi jinping", "us china", "china us", "beijing washington",
                "decoupling", "tech ban china", "huawei", "tiktok ban",
                "china relations", "indo-pacific", "first island chain",
                "china military", "pla", "chip export ban",
            ],
            "India-Pakistan": [
                "kashmir", "line of control", "loc", "pakistan army", "imf pakistan",
                "india pakistan", "surgical strike", "cross border",
                "pulwama", "atari border", "wagah", "indus water",
                "pakistan india", "pakistan terror", "hafiz saeed",
                "jaish", "lashkar", "border standoff",
            ],
            "Russia-Ukraine": [
                "ukraine", "zelensky", "putin", "nato", "crimea", "kyiv", "kharkiv",
                "russian troops", "war ukraine", "ukraine war", "russia ukraine",
                "donbas", "zaporizhzhia", "kherson", "odessa",
                "peace talks ukraine", "ukraine aid", "russian missile",
                "mariupol", "drone attack ukraine", "bakhmut",
            ],
            "China-India Relations": [
                "china india border", "lac", "galwan", "arunachal", "doklam",
                "india china tension", "pla india", "line of actual control",
                "hindi chini", "china infrastructure india", "bri india",
            ],
            "South Asia": [
                "bangladesh", "sri lanka", "nepal", "myanmar", "afghanistan",
                "bhutan", "maldives", "hasina", "rajapaksa", "rohingya",
                "south asia", "saarc", "bay of bengal", "imran khan",
                "taliban", "kabul", "dhaka", "kathmandu", "colombo",
            ],
            "Africa": [
                "ethiopia", "somalia", "sudan", "kenya", "nigeria", "sahel",
                "mozambique", "mali", "niger", "burkina faso", "congo", "drc",
                "african union", "sub saharan", "east africa", "west africa",
                "rwanda", "zimbabwe", "south africa politics", "senegal",
                "egypt politics", "tunisia", "morocco conflict", "algeria",
            ],
            "Europe": [
                "european union", "eu parliament", "uk politics", "france",
                "germany", "nato europe", "macron", "scholz", "ursula",
                "brexit", "ukraine aid europe", "eu sanctions", "europe",
                "poland", "hungary orban", "turkey eu", "balkans",
                "eu elections", "far right europe", "spain politics",
            ],
            "Latin America": [
                "brazil", "mexico", "argentina", "colombia", "venezuela",
                "chile", "cuba", "lula", "amlo", "maduro",
                "latin america", "cartel", "central america",
                "imf argentina", "peso crisis", "petro colombia",
            ],
            "East Asia & Pacific": [
                "japan", "south korea", "north korea", "kim jong un",
                "philippines", "vietnam", "indonesia", "asean",
                "australia foreign policy", "new zealand", "pacific islands",
                "china sea", "korean peninsula", "kim nuclear", "apec",
            ],
        },
    },

    # ─────────────────────────────────────────────────────────────
    "Finance": {
        "base_keywords": [
            "economy", "economic", "finance", "financial", "market",
            "investment", "fiscal", "monetary", "revenue", "profit",
            "debt", "capital", "liquidity", "assets", "portfolio",
        ],
        "subcategories": {
            "Indian Stock Markets": [
                "sensex", "nifty", "bse", "nse", "equity", "shares", "stock market",
                "market rally", "bull run", "bear market", "market crash",
                "fii", "dii", "mutual fund", "trading", "demat",
                "sebi", "smallcap", "midcap", "large cap", "derivatives",
                "futures", "options", "stock exchange", "ipo listing",
            ],
            "Global Stock Markets": [
                "dow jones", "s&p 500", "nasdaq", "nyse", "wall street",
                "ftse", "dax", "nikkei", "hang seng", "euro stoxx",
                "global stocks", "market selloff", "global rally",
            ],
            "Cryptocurrency": [
                "bitcoin", "ethereum", "crypto", "cryptocurrency", "blockchain",
                "defi", "web3", "binance", "coinbase", "solana", "altcoin",
                "nft", "stablecoin", "usdt", "digital currency",
                "crypto exchange", "crypto regulation", "sec crypto",
                "xrp", "cardano", "polkadot", "avalanche", "matic",
                "crypto crash", "bull market crypto",
            ],
            "Indian Economy": [
                "rbi", "gdp india", "inflation india", "rupee", "fiscal deficit",
                "union budget", "gst", "india economy", "reserve bank",
                "cpi india", "rbi policy", "repo rate", "india growth",
                "economic survey", "government spending", "tax revenue india",
                "current account deficit", "forex reserves", "disinvestment",
                "india manufacturing", "pli scheme",
            ],
            "Global Economy": [
                "federal reserve", "fed rate", "ecb", "interest rate", "inflation",
                "recession", "imf", "world bank", "gdp growth", "global trade",
                "supply chain", "wto", "trade deficit", "stagflation",
                "economic slowdown", "global recession", "tariff war",
                "boe", "bank of england", "boj", "bank of japan",
            ],
            "Corporate & Earnings": [
                "quarterly results", "earnings", "merger", "acquisition", "ipo",
                "operating profit", "ebitda", "board meeting", "ceo", "cfo",
                "layoff", "restructuring", "valuation", "deal signed",
                "takeover", "joint venture", "corporate", "annual report",
                "revenue growth", "net profit", "operating loss",
                "shareholder", "dividend", "buyback",
            ],
            "Indian Banking": [
                "hdfc", "sbi", "icici", "axis bank", "rbi policy", "npa",
                "neft", "banking sector", "credit growth", "deposit rate",
                "loan", "nbfc", "microfinance", "banking reform", "bad loan",
                "banking crisis", "kotak", "yes bank", "pnb", "idbi",
                "upi", "digital banking", "bank merger", "rbi action",
            ],
            "Startups & Venture Capital": [
                "startup india", "unicorn", "funding round", "venture capital",
                "series a", "series b", "series c", "angel invest", "valuation",
                "bootstrapped", "founder", "accelerator", "y combinator",
                "sequoia india", "tiger global", "startup ecosystem",
                "startup layoff", "startup shutdown", "blitzscaling",
                "growth stage", "pre-ipo",
            ],
            "Real Estate & Infrastructure": [
                "real estate", "property market", "housing", "reit",
                "residential", "commercial property", "office space",
                "construction", "infrastructure india", "smart city",
                "nhai", "highway", "metro project", "affordable housing",
                "dlf", "godrej properties", "housing prices",
            ],
            "Commodities & Energy": [
                "crude oil", "brent", "wti oil", "opec", "natural gas",
                "gold price", "silver", "copper", "commodities",
                "coal", "energy prices", "fuel price", "petrol diesel",
                "refinery", "pipeline", "energy crisis",
            ],
        },
    },

    # ─────────────────────────────────────────────────────────────
    "AI": {
        "base_keywords": [
            "artificial intelligence", "ai", "machine learning", "deep learning",
            "neural network", "large language model", "llm", "foundation model",
            "generative ai", "ai model", "ai system", "language model",
        ],
        "subcategories": {
            "ChatGPT & OpenAI": [
                "openai", "chatgpt", "gpt-4", "gpt-5", "gpt4", "gpt5",
                "sam altman", "openai ceo", "openai funding", "openai board",
                "chatgpt update", "openai api", "dalle", "sora openai",
                "operator openai", "openai safety", "o1 model", "o3 model",
            ],
            "Claude & Anthropic": [
                "anthropic", "claude ai", "dario amodei", "amanda askell",
                "claude 3", "claude 4", "claude sonnet", "claude opus",
                "anthropic funding", "constitutional ai", "anthropic safety",
            ],
            "Gemini & Google AI": [
                "google gemini", "google ai", "bard google", "gemini ultra",
                "gemini pro", "gemini flash", "deepmind", "google llm",
                "sundar pichai ai", "google ai model", "vertex ai",
                "google io ai", "google search ai", "gemini 2",
                "veo google", "imagen google",
            ],
            "DeepSeek": [
                "deepseek", "deepseek r1", "deepseek v3", "deepseek ai",
                "deepseek china", "deepseek open source", "deepseek coder",
            ],
            "Other LLMs": [
                "mistral", "llama", "meta ai", "cohere", "ai21", "phi microsoft",
                "qwen alibaba", "grok xai", "elon musk ai", "falcon ai",
                "command r", "open source llm", "hugging face", "ollama",
                "amazon bedrock", "nvidia ai", "perplexity ai",
            ],
            "AI Safety & Ethics": [
                "ai research", "ai safety", "alignment research", "agi",
                "superintelligence", "ai risk", "ai regulation", "eu ai act",
                "responsible ai", "ai ethics", "ai bias", "deepfake",
                "ai governance", "ai policy", "ai transparency",
            ],
            "AI Applications": [
                "diffusion model", "transformer model", "multimodal ai",
                "vision model", "text to image", "text to video", "ai agent",
                "agentic ai", "reasoning model", "chain of thought",
                "fine tuning", "rlhf", "ai benchmark", "ai performance",
                "ai in healthcare", "ai in education", "ai coding",
                "ai music", "ai art", "synthetic media",
            ],
            "AI Industry": [
                "ai startup", "ai investment", "ai chip", "ai data center",
                "microsoft ai", "amazon ai", "apple ai", "ai jobs",
                "ai layoff", "ai funding", "ai valuation",
                "nvidia revenue", "gpu shortage", "ai infrastructure",
            ],
        },
    },

    # ─────────────────────────────────────────────────────────────
    "Politics": {
        "base_keywords": [
            "politics", "political", "government", "parliament", "legislation",
            "policy", "minister", "president", "prime minister", "senator",
            "congress", "election", "vote", "democracy", "opposition",
        ],
        "subcategories": {
            "Indian Politics": [
                "bjp", "congress party", "modi", "rahul gandhi", "lok sabha",
                "rajya sabha", "aap", "aam aadmi party", "tmc", "trinamool",
                "shiv sena", "nda", "india alliance", "yogi adityanath",
                "amit shah", "smriti irani", "arvind kejriwal", "mamata",
                "state government india", "india politics", "jdu", "bjd",
                "telangana politics", "karnataka politics", "maharashtra politics",
                "uttarakhand", "himachal politics",
            ],
            "US Politics": [
                "trump", "biden", "kamala harris", "democrat", "republican",
                "us congress", "us senate", "white house", "maga", "gop",
                "supreme court us", "oval office", "us president",
                "nancy pelosi", "chuck schumer", "doge", "elon trump",
                "us midterm", "us election", "us cabinet",
                "house of representatives", "filibuster",
            ],
            "UK Politics": [
                "keir starmer", "rishi sunak", "labour party", "conservative",
                "uk parliament", "house of commons", "westminster",
                "uk cabinet", "chancellor", "home secretary",
                "tory", "uk election", "scotland independence",
            ],
            "Elections": [
                "election", "voting", "ballot", "polls", "candidate",
                "constituency", "voter turnout", "exit poll", "election result",
                "campaign", "swing state", "electoral college", "by-election",
                "referendum", "general election", "election commission",
            ],
            "Policy & Governance": [
                "government policy", "union budget", "legislation", "parliament session",
                "cabinet decision", "ordinance", "reform", "bill passed",
                "government scheme", "pli scheme", "make in india",
                "infrastructure policy", "public sector", "privatisation",
                "rti", "lokpal", "judicial reform",
            ],
            "International Relations": [
                "diplomacy", "bilateral", "g20", "g7", "quad", "brics",
                "united nations general", "embassy", "foreign minister",
                "state visit", "diplomatic ties", "sanctions", "foreign aid",
                "trade agreement", "free trade", "mou signed", "sco",
                "non-aligned", "commonwealth", "asean summit",
            ],
        },
    },

    # ─────────────────────────────────────────────────────────────
    "Technology": {
        "base_keywords": [
            "technology", "tech", "digital", "software", "hardware",
            "innovation", "internet", "computing", "data", "platform",
        ],
        "subcategories": {
            "Cybersecurity": [
                "hack", "data breach", "ransomware", "malware", "cybersecurity",
                "phishing", "vulnerability", "zero-day", "cyberattack",
                "ddos", "data leak", "password breach", "security flaw",
                "cyber threat", "dark web", "identity theft", "cyber crime",
                "spyware", "pegasus spyware", "cyber espionage",
                "critical infrastructure attack", "cloud security",
            ],
            "Semiconductors & Hardware": [
                "chip shortage", "semiconductor", "intel", "tsmc", "nvidia chip",
                "amd", "processor", "foundry", "fab plant", "chip manufacturing",
                "arm holdings", "qualcomm chip", "chip act", "wafer",
                "microchip", "gpu", "chip geopolitics", "apple silicon",
                "risc-v", "samsung foundry",
            ],
            "Big Tech & Platforms": [
                "apple", "google", "microsoft", "amazon", "meta",
                "alphabet", "antitrust tech", "big tech regulation",
                "app store", "android", "windows", "azure", "aws",
                "facebook", "instagram", "whatsapp", "youtube",
                "google play", "apple watch", "iphone",
            ],
            "Social Media": [
                "twitter", "x elon", "instagram", "threads meta", "tiktok",
                "snapchat", "linkedin", "pinterest", "reddit",
                "social media", "content moderation", "platform ban",
                "social media addiction", "algorithm", "viral post",
                "influencer", "creator economy",
            ],
            "Startups & SaaS": [
                "silicon valley", "saas", "cloud computing", "fintech",
                "edtech", "healthtech", "proptech", "insuretech",
                "series a tech", "product launch", "app launch",
                "india tech", "bangalore startup", "hyderabad tech",
                "software", "enterprise software",
            ],
            "Space Technology": [
                "isro", "nasa", "spacex", "rocket launch", "satellite",
                "mars mission", "moon mission", "gaganyaan", "chandrayaan",
                "artemis", "james webb telescope", "starship", "blue origin",
                "space station", "iss", "astronaut", "spacecraft",
                "commercial space", "launch vehicle", "orbital",
            ],
            "Electric Vehicles & Mobility": [
                "tesla", "electric vehicle", "electric car", "ev adoption",
                "battery technology", "charging station", "ev sales",
                "solid state battery", "byd", "rivian", "lucid motors",
                "ola electric", "tata ev", "mahindra ev", "ev policy",
                "range electric", "hyundai ioniq", "ev charging infrastructure",
            ],
            "Internet & Connectivity": [
                "5g", "broadband", "internet speed", "wifi", "starlink",
                "fiber optic", "telecom", "jio", "airtel broadband",
                "bsnl", "vi vodafone", "spectrum auction",
                "net neutrality", "digital india", "rural internet",
            ],
        },
    },

    # ─────────────────────────────────────────────────────────────
    "Science & Research": {
        "base_keywords": [
            "science", "research", "study", "scientists", "discovery",
            "experiment", "laboratory", "published", "journal", "peer review",
        ],
        "subcategories": {
            "Physics & Astronomy": [
                "particle physics", "cern", "black hole", "galaxy",
                "dark matter", "dark energy", "quantum", "gravitational wave",
                "neutron star", "supernova", "telescope", "exoplanet",
                "nasa discovery", "james webb", "light speed", "nuclear fusion",
            ],
            "Biology & Genetics": [
                "genetics", "dna", "gene editing", "crispr", "genome",
                "evolution", "species", "biodiversity", "ecology",
                "marine biology", "cell biology", "microbiology",
                "virus biology", "bacteria", "fungi", "antibiotic resistance",
            ],
            "Climate Science": [
                "climate study", "global temperature", "sea level", "ice shelf",
                "arctic", "antarctic", "permafrost", "ocean acidification",
                "weather pattern", "extreme heat", "flooding study",
                "co2 levels", "greenhouse gas", "ipcc", "climate model",
            ],
            "Medical Research": [
                "clinical trial", "drug approval", "fda", "cdsco", "vaccine research",
                "cancer treatment", "alzheimer research", "stem cell",
                "medical breakthrough", "rare disease", "gene therapy",
                "immunotherapy", "biosimilar", "antibiotic",
            ],
            "Space Exploration": [
                "mars exploration", "moon landing", "deep space", "asteroid",
                "comet", "solar system", "outer planets", "spacecraft mission",
                "isro mission", "nasa rover", "europa", "titan",
            ],
            "Technology Research": [
                "quantum computing", "materials science", "nanotechnology",
                "robotics research", "brain computer interface",
                "renewable energy research", "battery research",
                "3d printing", "augmented reality research",
            ],
        },
    },

    # ─────────────────────────────────────────────────────────────
    "Health & Medicine": {
        "base_keywords": [
            "health", "healthcare", "medicine", "medical", "hospital",
            "doctor", "patient", "disease", "treatment", "wellness",
        ],
        "subcategories": {
            "Pandemics & Outbreaks": [
                "covid", "pandemic", "epidemic", "outbreak", "mpox",
                "who alert", "new virus", "disease spread", "quarantine",
                "lockdown", "health emergency", "dengue outbreak",
                "cholera", "ebola", "influenza pandemic",
            ],
            "Cancer & Chronic Disease": [
                "cancer treatment", "oncology", "chemotherapy", "immunotherapy",
                "lung cancer", "breast cancer", "diabetes", "heart disease",
                "hypertension", "stroke", "kidney disease", "liver disease",
                "arthritis", "autoimmune",
            ],
            "Mental Health": [
                "mental health", "depression", "anxiety disorder", "suicide",
                "therapy", "psychiatry", "psychological", "mental wellness",
                "burnout", "stress", "ptsd", "schizophrenia",
                "mental health policy", "counselling",
            ],
            "Healthcare Policy": [
                "healthcare policy", "nhs", "ayushman bharat", "health insurance",
                "medical cost", "hospital beds", "doctor shortage",
                "health budget", "pharma regulation", "drug price",
                "universal health", "who policy",
            ],
            "Nutrition & Lifestyle": [
                "nutrition", "diet study", "obesity", "junk food", "ultra processed",
                "sugar health", "alcohol health", "smoking health",
                "exercise benefit", "sleep health", "gut health",
            ],
            "Pharma & Biotech": [
                "pharmaceutical", "biotech", "drug approval", "clinical trial",
                "pfizer", "moderna", "astrazeneca", "sun pharma", "cipla",
                "dr reddy", "serum institute", "vaccine", "biosimilar",
                "generic drug", "patent drug",
            ],
        },
    },

    # ─────────────────────────────────────────────────────────────
    "Business & Industry": {
        "base_keywords": [
            "business", "industry", "manufacturing", "trade", "export",
            "import", "supply chain", "factory", "production", "commerce",
        ],
        "subcategories": {
            "Indian Business": [
                "tata", "reliance", "adani", "infosys", "wipro",
                "hcl", "mahindra", "bajaj", "larsen toubro", "ltimindtree",
                "maruti", "hero motocorp", "bhel", "ongc", "ntpc",
                "india inc", "indian business", "promoter",
            ],
            "Global Trade": [
                "trade deal", "free trade agreement", "fta", "wto dispute",
                "export ban", "import tariff", "trade surplus", "trade deficit",
                "shipping", "logistics", "port", "container shortage",
                "supply chain disruption", "global trade",
            ],
            "Retail & Consumer": [
                "amazon india", "flipkart", "retail", "ecommerce",
                "quick commerce", "zomato", "swiggy", "blinkit",
                "d2c brand", "fmcg", "consumer goods", "fmcg sales",
                "reliance retail", "dmart", "big bazaar",
            ],
            "Energy & Oil": [
                "crude oil", "opec", "natural gas", "lpg", "coal india",
                "adani energy", "renewable energy company", "solar energy",
                "wind energy", "power plant", "electricity tariff",
                "oil company", "petrol pump", "refinery profit",
            ],
            "Aviation & Transport": [
                "aviation", "airline", "air india", "indigo", "spicejet",
                "vistara", "airport", "dgca", "flight", "airbus", "boeing",
                "cargo", "freight", "shipping company",
                "railway", "irfc", "indian railways revenue",
            ],
            "Telecom": [
                "reliance jio", "airtel", "bsnl", "vodafone idea",
                "telecom sector", "5g rollout", "spectrum", "trai",
                "mobile subscriber", "telecom revenue",
            ],
        },
    },

    # ─────────────────────────────────────────────────────────────
    "Defence & Military": {
        "base_keywords": [
            "defence", "military", "army", "navy", "air force",
            "weapon", "missile", "soldier", "combat", "armed forces",
        ],
        "subcategories": {
            "Indian Defence": [
                "indian army", "indian navy", "indian air force", "iaf",
                "drdo", "bsf", "crpf", "cisf", "coast guard",
                "defence budget", "defence procurement", "indigenisation",
                "atmanirbhar defence", "rafale", "tejas fighter",
                "ins vikrant", "brahmos", "agni missile", "defence deal india",
            ],
            "US Military": [
                "pentagon", "us army", "us navy", "us air force", "marine corps",
                "us defence budget", "nato expansion", "us bases",
                "us military aid", "us weapon", "f-35", "aircraft carrier us",
            ],
            "Arms & Weapons": [
                "arms deal", "weapons supply", "missile system", "drone warfare",
                "hypersonic", "nuclear weapon", "submarine", "tank",
                "artillery", "air defence system", "s-400", "patriot",
                "iron dome", "javelin missile", "cluster munition",
            ],
            "Global Conflicts": [
                "conflict zone", "war", "ceasefire", "military operation",
                "peacekeeping", "rebel group", "insurgency",
                "occupied territory", "siege", "civilian casualties",
                "war crime", "nato operation",
            ],
            "Nuclear Affairs": [
                "nuclear", "nuclear deal", "iaea", "non-proliferation",
                "nuclear test", "nuclear warhead", "nuclear treaty",
                "iran nuclear", "north korea nuclear", "arms control",
            ],
        },
    },

    # ─────────────────────────────────────────────────────────────
    "Environment & Climate": {
        "base_keywords": [
            "environment", "climate", "ecology", "carbon", "emissions",
            "pollution", "biodiversity", "wildlife", "conservation",
            "sustainable", "green energy",
        ],
        "subcategories": {
            "Climate Change": [
                "climate change", "global warming", "cop28", "cop29", "cop30",
                "carbon emissions", "net zero", "paris agreement",
                "carbon tax", "carbon credit", "climate crisis",
                "temperature record", "heat record",
            ],
            "Renewable Energy": [
                "solar energy", "wind energy", "renewable", "green hydrogen",
                "solar panel", "wind turbine", "rooftop solar",
                "energy storage", "battery storage", "biofuel",
                "hydropower", "tidal energy", "geothermal",
                "adani green", "suzlon",
            ],
            "Pollution": [
                "air pollution", "water pollution", "plastic pollution",
                "aqi", "particulate matter", "pm2.5", "smog",
                "delhi pollution", "industrial waste", "river pollution",
                "ocean plastic", "microplastic",
            ],
            "Wildlife & Conservation": [
                "wildlife", "tiger", "elephant", "poaching", "deforestation",
                "national park", "sanctuary", "endangered species",
                "coral reef", "amazon", "biodiversity loss",
                "iucn", "wwf", "illegal trade wildlife",
            ],
            "Natural Disasters": [
                "earthquake", "tsunami", "cyclone", "flood", "landslide",
                "drought", "wildfire", "heatwave", "blizzard",
                "hurricane", "tornado", "volcanic eruption",
                "disaster relief", "ndrf",
            ],
            "Environmental Policy": [
                "environmental policy", "cop summit", "carbon trading",
                "emissions target", "paris accord", "eu green deal",
                "india climate", "ndc", "fossil fuel subsidy",
                "plastic ban", "single use plastic", "afforestation",
            ],
        },
    },

    # ─────────────────────────────────────────────────────────────
    "International News": {
        "base_keywords": [
            "international", "global", "world news", "foreign", "overseas",
            "worldwide", "multinational",
        ],
        "subcategories": {
            "United Nations": [
                "united nations", "un security council", "un resolution",
                "secretary general", "un peacekeeping", "guterres",
                "general assembly", "unhcr", "who un", "unicef", "wfp",
                "un sanctions", "veto power", "p5",
            ],
            "Human Rights": [
                "human rights", "amnesty international", "genocide", "war crimes",
                "refugees", "displaced persons", "persecution", "torture report",
                "icc", "international criminal court", "child labour",
                "press freedom", "journalists killed", "prisoner of war",
            ],
            "Migration & Refugees": [
                "refugee", "asylum seeker", "migrant", "deportation",
                "immigration", "border crossing", "rohingya refugee",
                "syrian refugee", "ukrainian refugee", "boat people",
                "unhcr", "eu migration", "us border migration",
            ],
            "Global Economy News": [
                "imf report", "world bank report", "g20 summit",
                "wto decision", "davos", "global trade data",
                "foreign exchange", "dollar index", "global inflation",
            ],
        },
    },

    # ─────────────────────────────────────────────────────────────
    "Law & Justice": {
        "base_keywords": [
            "court", "judge", "verdict", "law", "legal", "justice",
            "lawsuit", "trial", "criminal", "judiciary",
        ],
        "subcategories": {
            "Supreme Court of India": [
                "supreme court", "sc india", "chief justice", "cji",
                "constitution bench", "sc verdict", "sc judgment",
                "sc hearing", "fundamental rights", "article 370",
                "sc on elections", "sc on environment",
            ],
            "High Courts": [
                "high court", "delhi hc", "bombay hc", "calcutta hc",
                "madras hc", "allahabad hc", "hc verdict", "hc order",
            ],
            "Criminal Cases": [
                "arrest", "fir", "chargesheet", "conviction", "acquittal",
                "murder case", "rape case", "fraud case", "cbi probe",
                "ed raid", "enforcement directorate", "income tax raid",
                "nia", "anti-terror law",
            ],
            "Corporate Law": [
                "sebi action", "nclat", "nclt", "insolvency", "ibc",
                "corporate fraud", "money laundering", "hawala",
                "corporate governance", "class action",
            ],
            "International Law": [
                "international court of justice", "icj", "icc",
                "war crimes tribunal", "un law", "maritime law",
                "extradition", "bilateral treaty law",
            ],
        },
    },

    # ─────────────────────────────────────────────────────────────
    "Social Issues": {
        "base_keywords": [
            "social", "society", "community", "inequality", "poverty",
            "discrimination", "rights", "protest", "movement",
        ],
        "subcategories": {
            "Gender & Women's Rights": [
                "women rights", "gender equality", "feminism", "sexual harassment",
                "domestic violence", "rape", "marital rape", "gender pay gap",
                "women empowerment", "girl education", "metoo",
                "women reservation", "mahila",
            ],
            "Caste & Religion": [
                "caste", "dalit", "obc", "reservation", "atrocity",
                "discrimination caste", "hindu muslim", "communal tension",
                "religious violence", "riot", "mosque temple",
                "minority rights", "conversion", "love jihad",
            ],
            "Education": [
                "education policy", "nep", "school", "college", "university",
                "exam", "student", "dropout", "higher education",
                "iit", "iim", "neet", "jee", "board exam",
                "digital education", "edtech india", "scholarship",
            ],
            "Poverty & Development": [
                "poverty", "hunger", "malnutrition", "food security",
                "sdg", "human development", "rural development",
                "tribal rights", "adivasi", "displacement", "slum",
                "mgnrega", "welfare scheme",
            ],
            "LGBTQ+ Rights": [
                "lgbtq", "gay rights", "same sex", "transgender",
                "queer", "pride march", "section 377",
                "same sex marriage", "gender identity",
            ],
        },
    },

    # ─────────────────────────────────────────────────────────────
    "Entertainment": {
        "base_keywords": [
            "entertainment", "film", "movie", "music", "celebrity",
            "award", "streaming", "box office", "ott",
        ],
        "subcategories": {
            "Bollywood": [
                "bollywood", "hindi film", "box office india", "srk", "shah rukh khan",
                "salman khan", "deepika", "ranveer", "alia bhatt", "hrithik",
                "akshay kumar", "kareena", "priyanka chopra", "ranbir",
                "katrina", "tiger shroff", "yash raj", "dharma productions",
                "bade miyan chote miyan", "pathaan", "jawan",
            ],
            "Hollywood": [
                "hollywood", "marvel", "dc", "avengers", "disney",
                "netflix original", "amazon prime video", "hbo",
                "oscar", "golden globe", "cannes", "tom cruise",
                "dwayne johnson", "ryan reynolds", "taylor swift",
                "beyonce", "box office usa",
            ],
            "OTT & Streaming": [
                "netflix", "amazon prime video", "disney hotstar", "jiocinema",
                "apple tv", "hbo max", "peacock", "paramount",
                "streaming war", "ott platform", "webseries",
                "binge watch", "content creator",
            ],
            "South Indian Cinema": [
                "tollywood", "kollywood", "mollywood", "kannada film",
                "prabhas", "allu arjun", "vijay", "rajinikanth",
                "mahesh babu", "jr ntr", "ram charan", "nayanthara",
                "bahubali", "rrr", "pushpa", "kalki",
            ],
            "Music": [
                "music album", "concert", "grammy", "spotify chart",
                "arijit singh", "ap dhillon", "diljit dosanjh",
                "ar rahman", "atif aslam", "badshah", "yo yo honey singh",
                "taylor swift album", "bts", "k-pop",
            ],
            "Celebrity & Lifestyle": [
                "celebrity", "star", "actor arrested", "divorce celebrity",
                "celebrity wedding", "controversy celebrity",
                "paparazzi", "red carpet",
            ],
        },
    },

    # ─────────────────────────────────────────────────────────────
    "Cricket": {
        "base_keywords": [
            "cricket", "icc", "bcci", "wicket", "innings", "over",
            "batting", "bowling", "fielding", "test", "odi", "t20",
            "runs", "century", "dismissal",
        ],
        "subcategories": {
            "IPL": [
                "ipl", "indian premier league", "ipl auction", "ipl match",
                "franchise cricket", "ipl final", "ipl season", "ipl 2025",
                "csk", "mi", "rcb", "kkr", "dc", "srh", "pbks", "gt", "lsg", "rr",
                "dhoni", "bumrah ipl", "virat ipl", "ipl retained", "ipl trade",
            ],
            "Test Cricket": [
                "test match", "test series", "ashes", "border gavaskar trophy",
                "red ball cricket", "test championship", "wtc final",
                "test debut", "five day", "test ranking",
            ],
            "ODI & Champions Trophy": [
                "one day international", "odi series", "cricket world cup",
                "50 over", "odi match", "champions trophy",
                "odi ranking", "odi squad", "world cup qualifier",
            ],
            "T20 World Cup": [
                "t20 world cup", "icc t20 world cup", "twenty20 international",
                "t20 championship", "super 8", "t20 squad", "t20 rankings",
            ],
            "Indian Team": [
                "team india", "virat kohli", "rohit sharma", "bumrah",
                "shami", "hardik pandya", "sky suryakumar", "gill",
                "siraj", "jadeja", "ashwin", "india cricket", "bcci selection",
                "india squad", "yashasvi jaiswal", "rinku singh",
            ],
            "International Teams": [
                "australia cricket", "england cricket", "pakistan cricket",
                "west indies cricket", "south africa cricket",
                "new zealand cricket", "sri lanka cricket",
                "bangladesh cricket", "afghanistan cricket", "zimbabwe cricket",
            ],
            "Women's Cricket": [
                "women's cricket", "wpl", "india women", "bcci women",
                "smriti mandhana", "harmanpreet", "shafali verma",
                "women's t20 world cup", "women's odi",
            ],
        },
    },

    # ─────────────────────────────────────────────────────────────
    "Football": {
        "base_keywords": [
            "football", "soccer", "match", "goal", "striker",
            "midfielder", "defender", "goalkeeper", "transfer", "league",
            "manager", "fixture",
        ],
        "subcategories": {
            "Premier League": [
                "premier league", "epl", "arsenal", "manchester city",
                "chelsea", "liverpool", "tottenham", "man utd", "manchester united",
                "aston villa", "newcastle", "west ham", "everton",
                "brighton", "brentford", "wolves",
            ],
            "La Liga": [
                "la liga", "barcelona", "real madrid", "atletico madrid",
                "sevilla", "villarreal", "laliga", "spain football",
                "vinicius", "bellingham", "lewandowski", "yamal",
                "xavi", "ancelotti",
            ],
            "Serie A & Bundesliga": [
                "serie a", "juventus", "inter milan", "ac milan", "napoli",
                "roma", "bundesliga", "bayern munich", "borussia dortmund",
                "bayer leverkusen", "italian football", "german football",
            ],
            "FIFA & World Cup": [
                "fifa", "world cup football", "world cup 2026",
                "qualify world cup", "fifa ranking", "infantino",
                "copa america", "euro cup", "afcon",
            ],
            "Champions League": [
                "champions league", "ucl", "europa league", "european football",
                "cl final", "knockout round", "group stage ucl",
                "conference league",
            ],
            "Transfers & Signings": [
                "transfer window", "football transfer", "signing", "loan move",
                "fee paid", "release clause", "transfer news",
                "wage", "contract extension", "free agent",
            ],
            "Indian Football": [
                "isl", "indian super league", "all india football", "aiff",
                "indian football team", "sunil chhetri", "blue tigers",
                "i-league",
            ],
        },
    },

    # ─────────────────────────────────────────────────────────────
    "Other Sports": {
        "base_keywords": [
            "sport", "athlete", "championship", "tournament",
            "gold medal", "world record", "competition", "coach",
        ],
        "subcategories": {
            "Tennis": [
                "wimbledon", "us open tennis", "french open", "australian open",
                "atp", "wta", "grand slam", "federer", "nadal", "djokovic",
                "alcaraz", "sinner", "swiatek", "tennis final", "tennis ranking",
                "davis cup", "billie jean king",
            ],
            "Formula 1": [
                "formula 1", "f1", "formula one", "ferrari f1",
                "mercedes f1", "red bull racing", "verstappen", "hamilton",
                "leclerc", "norris", "grand prix", "gp race", "monaco gp",
                "f1 championship", "mclaren", "williams f1", "haas f1",
                "sprint race", "f1 points",
            ],
            "Olympics": [
                "olympics", "olympic games", "ioc", "paris 2024",
                "los angeles 2028", "medal tally", "olympic gold",
                "olympic record", "olympic athlete", "olympic qualifier",
                "commonwealth games", "asian games", "neeraj chopra",
            ],
            "Basketball": [
                "nba", "basketball", "lebron james", "stephen curry",
                "kevin durant", "nba finals", "nba playoffs", "nba trade",
                "slam dunk", "three pointer", "jaylen brown", "luka doncic",
            ],
            "Badminton": [
                "badminton", "bwf", "pv sindhu", "saina nehwal",
                "shuttler", "all england badminton", "thomas cup",
                "uber cup", "world badminton", "lakshya sen", "kidambi srikanth",
            ],
            "Wrestling & MMA": [
                "wwe", "wrestling", "ufc", "mma", "mixed martial arts",
                "heavyweight champion", "raw smackdown", "wrestlemania",
                "ufc fight night", "conor mcgregor", "jon jones",
            ],
            "Hockey": [
                "hockey india", "indian hockey team", "hockey world cup",
                "fih", "pro league hockey", "pr sreejesh",
                "harmanpreet singh hockey",
            ],
            "Boxing": [
                "boxing", "wbc", "wba", "wbo", "ibf", "heavyweight boxing",
                "world boxing champion", "knockout", "boxer",
                "fury", "usyk", "canelo",
            ],
            "Golf": [
                "golf", "pga tour", "liv golf", "masters golf", "us open golf",
                "british open golf", "rory mcilroy", "tiger woods",
                "scottie scheffler", "golf ranking",
            ],
            "Athletics & Track": [
                "athletics", "100m", "marathon", "world athletics",
                "neeraj chopra javelin", "sprinter", "world championship athletics",
                "olympic athletics", "track and field",
            ],
        },
    },

    # ─────────────────────────────────────────────────────────────
    "Automotive": {
        "base_keywords": [
            "car", "vehicle", "automobile", "auto", "motor", "driving",
            "road", "two wheeler",
        ],
        "subcategories": {
            "Indian Auto Market": [
                "maruti suzuki", "tata motors", "hyundai india", "honda india",
                "mahindra car", "kia india", "mg motor", "skoda india",
                "volkswagen india", "auto sales india", "passenger vehicle",
                "commercial vehicle", "tractors", "two wheeler india",
            ],
            "Global Auto": [
                "toyota", "honda global", "volkswagen", "bmw", "mercedes benz",
                "ford", "general motors", "hyundai global", "stellantis",
                "auto industry", "global car sales", "auto tariff",
            ],
            "EV Market": [
                "electric vehicle market", "ev sales data", "ev adoption rate",
                "charging network", "ev battery cost", "ev range",
                "ev subsidy", "ev policy india",
            ],
            "Motorcycles & Two-Wheelers": [
                "hero motocorp", "honda motorcycle", "bajaj bike", "tvs motor",
                "royal enfield", "ktm india", "ola scooter",
                "two wheeler sales", "electric scooter",
            ],
        },
    },

    # ─────────────────────────────────────────────────────────────
    "Agriculture & Rural": {
        "base_keywords": [
            "agriculture", "farming", "farmer", "crop", "harvest",
            "rural", "village", "agri", "food production",
        ],
        "subcategories": {
            "Farmer Issues": [
                "farmer protest", "msp", "minimum support price",
                "farm law", "kisan", "debt waiver", "farmer suicide",
                "crop insurance", "pm kisan", "farmer income",
            ],
            "Crops & Commodities": [
                "wheat production", "rice production", "pulses", "oilseeds",
                "sugarcane", "cotton crop", "kharif", "rabi",
                "foodgrain", "vegetable price", "onion price",
                "tomato price", "potato price",
            ],
            "Rural Development": [
                "rural india", "village", "gram panchayat", "swachh bharat",
                "pm gram sadak", "rural employment", "nrega",
                "rural electrification", "jal jeevan",
            ],
            "Food Security": [
                "food security", "malnutrition", "hunger index",
                "public distribution", "ration card", "food inflation",
                "fci", "buffer stock", "food export",
            ],
        },
    },
}


def get_keywords_for_profile(
    selected_categories: list,
    selected_subcategories: dict,
) -> list:
    """
    Build a flat keyword list for use in pre-filtering articles.

    - Category with NO specific subcategories selected → use base_keywords + ALL subcategory keywords
    - Category with specific subcategories selected → use base_keywords + only those subcategory keywords
    """
    keywords = []
    for cat in selected_categories:
        cat_data = TAXONOMY.get(cat)
        if not cat_data:
            keywords.append(cat.lower())
            continue

        keywords.extend(cat_data.get("base_keywords", []))
        chosen_subs = selected_subcategories.get(cat, [])

        if not chosen_subs:
            for kws in cat_data["subcategories"].values():
                keywords.extend(kws)
        else:
            for sub in chosen_subs:
                kws = cat_data["subcategories"].get(sub, [])
                keywords.extend(kws)

    return list(set(k.lower() for k in keywords))


def build_topics_from_selections(
    selected_categories: list,
    selected_subcategories: dict,
    ai_extras: str = None,
) -> list:
    """
    Convert checkbox selections into TopicFilter objects for UserProfile.
    """
    from models.schemas import TopicFilter, SentimentPreference

    topics = []
    for cat in selected_categories:
        chosen_subs = selected_subcategories.get(cat, [])
        topics.append(TopicFilter(
            topic=cat,
            include=chosen_subs,
            exclude=[],
            sentiment=SentimentPreference.ANY,
        ))

    if ai_extras and ai_extras.strip():
        topics.append(TopicFilter(
            topic=f"Additional interests: {ai_extras.strip()}",
            include=[],
            exclude=[],
            sentiment=SentimentPreference.ANY,
        ))

    return topics
