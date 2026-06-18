import asyncio
from datetime import datetime, timedelta, timezone
from google.cloud import firestore

from config import settings
from services.db_service import DatabaseService
from agents.tagging_agent import TaggingAgent
from models.schemas import Article

db = DatabaseService(project_id=settings.GCP_PROJECT_ID)

async def main():
    print("Fetching articles from the last 3 days...")
    cutoff = datetime.now(timezone.utc) - timedelta(days=3)
    
    # We will fetch all recent articles
    articles_db = await db.get_recent_articles(hours=72)
    print(f"Found {len(articles_db)} total articles in the last 72 hours.")
    
    # Filter those that don't have categories (or maybe just retag all of them to be safe)
    # The user said "gemini hasn't read the existing articles yet... so we need gemini to run through the last 3 days articles"
    # We'll retag all of them.
    
    tagger = TaggingAgent(
        project_id=settings.GCP_PROJECT_ID,
        location=settings.GCP_REGION
    )
    batch_size = 10
    
    for i in range(0, len(articles_db), batch_size):
        batch = articles_db[i:i+batch_size]
        print(f"Tagging batch {i//batch_size + 1} of {len(articles_db)//batch_size + 1} ({len(batch)} articles)...")
        
        # tag_articles takes a list of Articles and returns a list of TaggedArticles
        tagged_results = await tagger.tag_articles(batch)
        
        # Save them back
        for tagged in tagged_results:
            # We overwrite the firestore doc with the new tagged details
            # Get existing doc ID
            ref = db._db.collection("articles").document(tagged.id)
            await ref.set(tagged.model_dump(mode="json"), merge=True)
            print(f" -> Updated {tagged.id}: {tagged.title[:30]}... Categories: {tagged.categories}")
            
    print("Done retagging.")

if __name__ == "__main__":
    asyncio.run(main())
