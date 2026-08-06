import asyncio
from services.db_service import DatabaseService
from services.auth_service import _init_firebase
import os

_init_firebase()
db = DatabaseService()

async def main():
    docs = await db._db.collection("user_feeds").limit(1).get()
    for doc in docs:
        await db._db.collection("user_feeds").document(doc.id).update({
            "interval_summary": "Yesterday, global markets saw a sharp dip following tech stock selloffs, while in sports, India clinched a thrilling victory in the final over. Meanwhile, tensions in the Middle East escalated, leading to emergency UN meetings.",
            "interval_summary_window": "While You Were Asleep"
        })
        print(f"Injected summary into feed for user {doc.id}")

if __name__ == "__main__":
    asyncio.run(main())
