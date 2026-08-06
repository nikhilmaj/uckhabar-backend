import asyncio
from services.db_service import DatabaseService
from config import settings

db = DatabaseService(settings.GCP_PROJECT)

async def check():
    await db.initialize()
    profiles = await db.get_all_user_profiles()
    for p in profiles:
        print(f"User: {p.user_name} ({p.user_id})")
        print(f"  Last Seen: {p.last_seen}")
        print(f"  Scoring Paused: {p.scoring_paused}")

asyncio.run(check())
