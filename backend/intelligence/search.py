import os
import httpx
import asyncio
import re
import random
import html
from google import genai
from google.genai import types

BRAVE_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY")
BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"

gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
PRIMARY_MODEL = os.getenv("PRIMARY_MODEL", "gemini-3.5-flash")


async def _duckduckgo_search(query: str, num_results: int = 5) -> list:
    """Fallback search scraper using DuckDuckGo HTML interface."""
    try:
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0"
        ]
        headers = {
            "User-Agent": random.choice(user_agents)
        }
        url = "https://html.duckduckgo.com/html/"
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.post(url, data={"q": query}, headers=headers)
            resp.raise_for_status()
            html_text = resp.text
            
        import urllib.parse
        results = []
        
        # Regex matches matching the class names with flexible positioning
        title_matches = re.findall(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            html_text,
            re.DOTALL
        )
        snippet_matches = re.findall(
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            html_text,
            re.DOTALL
        )
        
        for i in range(min(len(title_matches), len(snippet_matches), num_results)):
            raw_url = title_matches[i][0]
            
            # Clean HTML tags and decode HTML entity codes (e.g. &amp;, &quot;, &rsquo;, etc.)
            title = re.sub(r'<[^>]+>', '', title_matches[i][1]).strip()
            title = html.unescape(urllib.parse.unquote(title))
            
            snippet = re.sub(r'<[^>]+>', '', snippet_matches[i]).strip()
            snippet = html.unescape(urllib.parse.unquote(snippet))
            
            # Extract real URL from DDG redirect
            url = raw_url
            if "uddg=" in raw_url:
                parsed = urllib.parse.urlparse(raw_url)
                qs = urllib.parse.parse_qs(parsed.query)
                if "uddg" in qs:
                    url = qs["uddg"][0]
                    
            results.append({
                "title": title,
                "snippet": snippet,
                "url": url
            })
            
        return results
    except Exception as e:
        print(f"DuckDuckGo fallback search error: {e}")
        return []

async def web_search(query: str, num_results: int = 5) -> dict:
    """Search the web via Brave or fall back to DuckDuckGo if Brave Key is unconfigured."""
    # Check if API key is placeholder or missing -> Fallback to DDG
    if not BRAVE_API_KEY or BRAVE_API_KEY == "your_key_here":
        print(f"Brave Search API Key unconfigured, using DuckDuckGo fallback for: '{query}'")
        results = await _duckduckgo_search(query, num_results=num_results)
        return {"query": query, "results": results}

    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": BRAVE_API_KEY
    }
    params = {"q": query, "count": num_results}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(BRAVE_URL, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

        results = []
        for item in data.get("web", {}).get("results", []):
            results.append({
                "title": item.get("title", ""),
                "snippet": item.get("description", ""),
                "url": item.get("url", "")
            })
        return {"query": query, "results": results}
    except Exception as e:
        print(f"Brave Search API Error: {e}, falling back to DuckDuckGo...")
        results = await _duckduckgo_search(query, num_results=num_results)
        return {"query": query, "results": results}


async def fetch_page_text(url: str) -> str:
    """Fetch plain text content from a URL."""
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            text = re.sub(r"<[^>]+>", " ", resp.text)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:3000]
    except Exception as e:
        return f"[Could not fetch page: {e}]"


async def deep_research(query: str) -> dict:
    """Search + fetch top 3 pages + Gemini synthesizes one answer with sources."""
    search_data = await web_search(query, num_results=5)
    results = search_data["results"]

    if not results:
        return {"query": query, "answer": "No results found.", "sources": []}

    top_urls = [r["url"] for r in results[:3]]
    page_texts = await asyncio.gather(*[fetch_page_text(url) for url in top_urls])

    context_parts = []
    for i, (result, page_text) in enumerate(zip(results[:3], page_texts)):
        context_parts.append(
            f"Source {i+1}: {result['title']}\n"
            f"URL: {result['url']}\n"
            f"Snippet: {result['snippet']}\n"
            f"Content: {page_text}"
        )
    context = "\n\n---\n\n".join(context_parts)

    prompt = (
        f"You are ARIS, an AI research assistant. Based on the following sources, "
        f"provide a clear, concise, synthesized answer to: '{query}'\n\n"
        f"{context}\n\n"
        f"Respond in 3–5 sentences. End with a 'Sources:' section listing the URLs used."
    )

    response = gemini_client.models.generate_content(
        model=PRIMARY_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        )
    )

    return {
        "query": query,
        "answer": response.text,
        "sources": [{"title": r["title"], "url": r["url"]} for r in results[:3]]
    }


async def fact_check(claim: str) -> dict:
    """Cross-reference a claim across multiple sources."""
    query = f"fact check: {claim}"
    search_data = await web_search(query, num_results=6)
    results = search_data["results"]

    snippets = "\n".join(
        f"- {r['title']}: {r['snippet']}" for r in results
    )

    prompt = (
        f"You are ARIS fact-checking this claim: '{claim}'\n\n"
        f"Search results from multiple sources:\n{snippets}\n\n"
        f"Verdict: Is the claim TRUE, FALSE, PARTIALLY TRUE, or UNVERIFIED? "
        f"Give a 2–3 sentence explanation citing which sources agree or disagree."
    )

    response = gemini_client.models.generate_content(
        model=PRIMARY_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        )
    )

    return {
        "claim": claim,
        "verdict": response.text,
        "sources": [{"title": r["title"], "url": r["url"]} for r in results]
    }