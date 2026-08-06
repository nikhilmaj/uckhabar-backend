import os
os.environ["GCP_PROJECT_ID"] = "uckhabar"
os.environ["GCP_REGION"] = "asia-south1"
os.environ["APP_ENV"] = "production"
os.environ["ADMIN_SECRET"] = "dummy"

import asyncio
from services.db_service import DatabaseService
from services.auth_service import _init_firebase
import main

_init_firebase()
db = DatabaseService()

async def run_test():
    docs = await db._db.collection("articles").limit(1).get()
    article_id = docs[0].id
    print(f"Testing article: {article_id}")
    
    from fastapi import Request
    class MockRequest:
        state = type("State", (), {"user": {"uid": "test_uid"}})()
    
    try:
        res = await main.get_full_story_endpoint(article_id, MockRequest())
        print(res)
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_test())
