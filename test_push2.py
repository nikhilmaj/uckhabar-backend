import asyncio
from services.push_service import send_breaking_news_push
from services.auth_service import _init_firebase
import os

_init_firebase()

async def main():
    await send_breaking_news_push("Test Global Alert")

if __name__ == "__main__":
    asyncio.run(main())
