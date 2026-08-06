import asyncio
from services.push_service import send_breaking_news_push
from services.auth_service import get_current_user
import firebase_admin
from firebase_admin import credentials
import os

project_id = os.environ.get("GCP_PROJECT_ID", "uckhabar")
try:
    cred = credentials.ApplicationDefault()
    options = {"projectId": project_id} if project_id else {}
    firebase_admin.initialize_app(cred, options)
except Exception as e:
    print(f"Init Error: {e}")

async def main():
    await send_breaking_news_push("Test Global Alert")

if __name__ == "__main__":
    asyncio.run(main())
