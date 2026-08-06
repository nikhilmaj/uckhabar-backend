import asyncio
import httpx
import urllib.parse

async def test():
    search_term = "Roger Federer"
    wiki_url = f"https://en.wikipedia.org/w/api.php?action=query&prop=pageimages&format=json&piprop=original&titles={urllib.parse.quote(search_term)}"
    print(f"Requesting: {wiki_url}")
    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.get(wiki_url)
        print("Status:", res.status_code)
        if res.status_code == 200:
            data = res.json()
            pages = data.get("query", {}).get("pages", {})
            for k, v in pages.items():
                print("Page:", v)
                if "original" in v and "source" in v["original"]:
                    print("Found image:", v["original"]["source"])

asyncio.run(test())
