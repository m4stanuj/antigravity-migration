"""
mcp_web.py — M4ST Web Research MCP Server
Antigravity Migration | v6.0

Tools:
  web_search       — DuckDuckGo / SearXNG (free, no key)
  web_fetch        — Fast HTTP fetch with readability extraction
  web_scrape       — Scrapling-powered structured extraction
  web_research     — Multi-step deep research (search → fetch → synthesize)
  news_search      — News-focused search (RSS + web)
  url_screenshot   — Fetch URL + screenshot via browser
"""

import asyncio
import json
import re
from datetime import datetime
from typing import Any

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    raise SystemExit("pip install mcp")

try:
    import httpx
    HAS_HTTP = True
except ImportError:
    HAS_HTTP = False

try:
    from scrapling import Fetcher
    HAS_SCRAPLING = True
except ImportError:
    HAS_SCRAPLING = False

app = Server("m4st-web")


def _clean_text(text: str, limit: int = 8000) -> str:
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:limit]


async def _ddg_search(query: str, max_results: int = 10) -> list[dict]:
    """DuckDuckGo search via HTML scraping (no API key needed)."""
    url = "https://html.duckduckgo.com/html/"
    params = {"q": query, "kl": "in-en"}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.post(url, data=params, headers=headers)
        # Parse results
        results = []
        pattern = r'class="result__title".*?href="(.*?)".*?class="result__snippet">(.*?)</a>'
        matches = re.findall(pattern, resp.text, re.DOTALL)
        for href, snippet in matches[:max_results]:
            # Decode DDG redirect
            actual_url = re.search(r'uddg=(.*?)&', href)
            if actual_url:
                from urllib.parse import unquote
                href = unquote(actual_url.group(1))
            results.append({"url": href, "snippet": re.sub(r'<.*?>', '', snippet).strip()})
        return results


async def _fetch_readable(url: str, limit: int = 8000) -> dict:
    """Fetch URL and extract readable content."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers) as client:
        resp = await client.get(url)
        html = resp.text
    # Simple readability — strip scripts, styles, extract text
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', html)
    text = _clean_text(text, limit)
    # Try to get title
    title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
    title = title_match.group(1) if title_match else url
    return {"url": url, "title": title, "content": text, "length": len(text)}


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="web_search",
             description="Search the web using DuckDuckGo (no API key required). Returns titles, URLs, snippets.",
             inputSchema={"type": "object", "required": ["query"],
                         "properties": {
                             "query": {"type": "string"},
                             "max_results": {"type": "integer", "default": 10},
                             "region": {"type": "string", "default": "in-en"}
                         }}),

        Tool(name="web_fetch",
             description="Fetch and extract readable text content from a URL.",
             inputSchema={"type": "object", "required": ["url"],
                         "properties": {
                             "url": {"type": "string"},
                             "limit": {"type": "integer", "default": 8000, "description": "Max chars to return"},
                             "selector": {"type": "string", "description": "CSS selector to extract specific section"}
                         }}),

        Tool(name="web_scrape",
             description="Structured web scraping — extract specific data from a page (tables, lists, specific elements).",
             inputSchema={"type": "object", "required": ["url"],
                         "properties": {
                             "url": {"type": "string"},
                             "selectors": {"type": "object", "description": "Map of label → CSS selector to extract"},
                             "extract_links": {"type": "boolean", "default": False},
                             "extract_tables": {"type": "boolean", "default": False}
                         }}),

        Tool(name="web_research",
             description="Multi-step deep research — search, fetch top results, synthesize. Best for thorough questions.",
             inputSchema={"type": "object", "required": ["query"],
                         "properties": {
                             "query": {"type": "string"},
                             "depth": {"type": "integer", "default": 3,
                                      "description": "Number of URLs to fetch and read"},
                             "focus": {"type": "string", "description": "Specific angle to focus on"},
                             "format": {"type": "string", "enum": ["summary", "raw", "bullets"],
                                       "default": "summary"}
                         }}),

        Tool(name="news_search",
             description="Search for recent news on a topic.",
             inputSchema={"type": "object", "required": ["query"],
                         "properties": {
                             "query": {"type": "string"},
                             "max_results": {"type": "integer", "default": 10}
                         }}),

        Tool(name="web_headers",
             description="Get HTTP headers and status for a URL without downloading body.",
             inputSchema={"type": "object", "required": ["url"],
                         "properties": {"url": {"type": "string"}}}),

        Tool(name="web_download",
             description="Download a file from a URL to local disk.",
             inputSchema={"type": "object", "required": ["url", "save_path"],
                         "properties": {
                             "url": {"type": "string"},
                             "save_path": {"type": "string"},
                             "chunk_size": {"type": "integer", "default": 8192}
                         }}),

        Tool(name="url_extract_links",
             description="Extract all links from a webpage.",
             inputSchema={"type": "object", "required": ["url"],
                         "properties": {
                             "url": {"type": "string"},
                             "filter_domain": {"type": "string", "description": "Only links from this domain"},
                             "limit": {"type": "integer", "default": 100}
                         }}),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if not HAS_HTTP:
        return [TextContent(type="text", text=json.dumps({"error": "pip install httpx"}))]
    try:
        result = await _dispatch(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e), "tool": name}))]


async def _dispatch(name: str, args: dict) -> Any:

    if name == "web_search":
        results = await _ddg_search(args["query"], args.get("max_results", 10))
        return {"query": args["query"], "results": results, "count": len(results)}

    elif name == "web_fetch":
        data = await _fetch_readable(args["url"], args.get("limit", 8000))
        return data

    elif name == "web_scrape":
        if HAS_SCRAPLING:
            fetcher = Fetcher()
            page = await asyncio.to_thread(fetcher.get, args["url"])
            result = {"url": args["url"]}
            if args.get("selectors"):
                for label, sel in args["selectors"].items():
                    elements = page.find_all(sel)
                    result[label] = [el.text for el in elements]
            if args.get("extract_links"):
                result["links"] = [a.attrib.get("href") for a in page.find_all("a") if a.attrib.get("href")]
            if args.get("extract_tables"):
                tables = []
                for table in page.find_all("table"):
                    rows = [[td.text for td in row.find_all("td,th")] for row in table.find_all("tr")]
                    tables.append(rows)
                result["tables"] = tables
            return result
        else:
            # Fallback — basic httpx extraction
            data = await _fetch_readable(args["url"])
            result = {"url": args["url"], "content": data["content"]}
            if args.get("selectors"):
                result["note"] = "Install scrapling for CSS selector extraction"
            return result

    elif name == "web_research":
        query = args["query"]
        depth = args.get("depth", 3)
        focus = args.get("focus", "")
        # Step 1: Search
        search_query = f"{query} {focus}".strip()
        search_results = await _ddg_search(search_query, max_results=depth + 2)
        # Step 2: Fetch top results
        sources = []
        tasks = [_fetch_readable(r["url"], limit=3000) for r in search_results[:depth]]
        fetched = await asyncio.gather(*tasks, return_exceptions=True)
        for i, (sr, content) in enumerate(zip(search_results[:depth], fetched)):
            if isinstance(content, Exception):
                continue
            sources.append({
                "source": sr["url"],
                "title": content.get("title", ""),
                "content": content.get("content", "")
            })
        return {
            "query": query,
            "focus": focus,
            "sources_fetched": len(sources),
            "sources": sources,
            "timestamp": datetime.now().isoformat()
        }

    elif name == "news_search":
        query = args["query"] + " site:news.google.com OR site:reuters.com OR site:bbc.com"
        results = await _ddg_search(query, args.get("max_results", 10))
        return {"query": args["query"], "news": results}

    elif name == "web_headers":
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.head(args["url"], follow_redirects=True)
            return {
                "url": str(resp.url),
                "status": resp.status_code,
                "headers": dict(resp.headers),
                "content_type": resp.headers.get("content-type")
            }

    elif name == "web_download":
        save_path = args["save_path"]
        chunk_size = args.get("chunk_size", 8192)
        total = 0
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            async with client.stream("GET", args["url"]) as resp:
                with open(save_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size):
                        f.write(chunk)
                        total += len(chunk)
        return {"downloaded": True, "path": save_path, "bytes": total}

    elif name == "url_extract_links":
        data = await _fetch_readable(args["url"])
        # Re-fetch to get raw HTML for link extraction
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(args["url"],
                                    headers={"User-Agent": "Mozilla/5.0"})
        links = re.findall(r'href=["\']([^"\']+)["\']', resp.text)
        from urllib.parse import urljoin, urlparse
        base = args["url"]
        domain_filter = args.get("filter_domain", "")
        resolved = []
        for link in links:
            full = urljoin(base, link)
            if domain_filter and domain_filter not in full:
                continue
            if full.startswith("http"):
                resolved.append(full)
        unique = list(dict.fromkeys(resolved))[:args.get("limit", 100)]
        return {"url": args["url"], "links": unique, "count": len(unique)}

    return {"error": f"Unknown tool: {name}"}


async def main():
    async with stdio_server() as (reader, writer):
        await app.run(reader, writer, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
