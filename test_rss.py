import asyncio
from services.rss_service import rss_polling_job
from services.db_service import db

async def run():
    print("Running RSS Poll...")
    await rss_polling_job()
    articles = await db.get_recent_articles(hours=48)
    print(f"Total articles in DB: {len(articles)}")
    
asyncio.run(run())
