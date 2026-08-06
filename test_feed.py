import asyncio
from main import feed_builder_job
import logging

logging.basicConfig(level=logging.INFO)

async def test():
    await feed_builder_job()

asyncio.run(test())
