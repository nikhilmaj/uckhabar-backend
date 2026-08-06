import asyncio
from agents.summarization_agent import SummarizationAgent

async def main():
    agent = SummarizationAgent(project_id="uckhabar")
    print("Testing get_full_story...")
    res = await agent.get_full_story("Stock Market Crashes", "NY Times", "The stock market crashed today.")
    print("RESULT:", res)

if __name__ == "__main__":
    asyncio.run(main())
