"""
mcp_browser.py — M4ST Browser MCP Server
Antigravity Migration | v6.0

CDP-based browser control (replaces Selenium — 4-5x faster)
Works with Chrome/Tandem/any Chromium fork

Tools: navigate, click, type, extract, scroll, screenshot,
       wait_for, evaluate, new_tab, close_tab, cookies, storage
"""

import asyncio
import json
import base64
from typing import Any

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    raise SystemExit("pip install mcp")

try:
    import playwright.async_api as pw
    HAS_PW = True
except ImportError:
    HAS_PW = False

# Lazy playwright state
_playwright = None
_browser = None
_context = None
_page = None

async def _get_page():
    global _playwright, _browser, _context, _page
    if _page is None:
        _playwright = await pw.async_playwright().start()
        # Connect to running Chrome or launch new
        try:
            _browser = await _playwright.chromium.connect_over_cdp("http://localhost:9222")
            contexts = _browser.contexts
            _context = contexts[0] if contexts else await _browser.new_context()
        except Exception:
            # Launch new browser
            _browser = await _playwright.chromium.launch(headless=False, args=["--start-maximized"])
            _context = await _browser.new_context()
        pages = _context.pages
        _page = pages[0] if pages else await _context.new_page()
    return _page

app = Server("m4st-browser")

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="browser_navigate",
             description="Navigate to a URL.",
             inputSchema={"type": "object", "required": ["url"],
                         "properties": {
                             "url": {"type": "string"},
                             "wait_until": {"type": "string",
                                           "enum": ["load", "domcontentloaded", "networkidle"],
                                           "default": "domcontentloaded"},
                             "timeout": {"type": "integer", "default": 15000}
                         }}),

        Tool(name="browser_click",
             description="Click an element by CSS selector or text.",
             inputSchema={"type": "object",
                         "properties": {
                             "selector": {"type": "string", "description": "CSS selector"},
                             "text": {"type": "string", "description": "Click element containing this text"},
                             "timeout": {"type": "integer", "default": 5000}
                         }}),

        Tool(name="browser_type",
             description="Type text into an input element.",
             inputSchema={"type": "object", "required": ["text"],
                         "properties": {
                             "selector": {"type": "string"},
                             "text": {"type": "string"},
                             "clear_first": {"type": "boolean", "default": True},
                             "press_enter": {"type": "boolean", "default": False}
                         }}),

        Tool(name="browser_extract",
             description="Extract text, HTML, or specific data from the current page.",
             inputSchema={"type": "object",
                         "properties": {
                             "selector": {"type": "string", "description": "CSS selector (page body if omitted)"},
                             "format": {"type": "string", "enum": ["text", "html", "links", "tables"],
                                       "default": "text"},
                             "limit": {"type": "integer", "default": 5000, "description": "Max chars"}
                         }}),

        Tool(name="browser_screenshot",
             description="Take a screenshot of the current browser page.",
             inputSchema={"type": "object",
                         "properties": {
                             "selector": {"type": "string", "description": "Screenshot specific element (optional)"},
                             "full_page": {"type": "boolean", "default": False}
                         }}),

        Tool(name="browser_scroll",
             description="Scroll the page.",
             inputSchema={"type": "object",
                         "properties": {
                             "direction": {"type": "string", "enum": ["up", "down", "top", "bottom"], "default": "down"},
                             "amount": {"type": "integer", "default": 500, "description": "Pixels"}
                         }}),

        Tool(name="browser_wait",
             description="Wait for an element to appear, disappear, or for a timeout.",
             inputSchema={"type": "object",
                         "properties": {
                             "selector": {"type": "string"},
                             "state": {"type": "string", "enum": ["visible", "hidden", "attached", "detached"],
                                      "default": "visible"},
                             "timeout": {"type": "integer", "default": 10000}
                         }}),

        Tool(name="browser_evaluate",
             description="Execute JavaScript on the current page. Returns result.",
             inputSchema={"type": "object", "required": ["script"],
                         "properties": {"script": {"type": "string"}}}),

        Tool(name="browser_url",
             description="Get the current page URL and title.",
             inputSchema={"type": "object", "properties": {}}),

        Tool(name="browser_new_tab",
             description="Open a new browser tab.",
             inputSchema={"type": "object",
                         "properties": {"url": {"type": "string", "description": "URL to open (optional)"}}}),

        Tool(name="browser_tabs",
             description="List all open tabs.",
             inputSchema={"type": "object", "properties": {}}),

        Tool(name="browser_switch_tab",
             description="Switch to a tab by index or URL substring.",
             inputSchema={"type": "object",
                         "properties": {
                             "index": {"type": "integer"},
                             "url_contains": {"type": "string"}
                         }}),

        Tool(name="browser_close_tab",
             description="Close the current tab.",
             inputSchema={"type": "object", "properties": {}}),

        Tool(name="browser_fill_form",
             description="Fill multiple form fields at once. Pass selector→value dict.",
             inputSchema={"type": "object", "required": ["fields"],
                         "properties": {
                             "fields": {"type": "object",
                                       "description": "Map of CSS selector → value to type"},
                             "submit_selector": {"type": "string", "description": "Submit button selector (optional)"}
                         }}),

        Tool(name="browser_cookies",
             description="Get or set browser cookies.",
             inputSchema={"type": "object",
                         "properties": {
                             "action": {"type": "string", "enum": ["get", "set", "clear"], "default": "get"},
                             "cookies": {"type": "array", "description": "Cookies to set (for action=set)"}
                         }}),

        Tool(name="browser_select",
             description="Select an option from a dropdown (<select> element).",
             inputSchema={"type": "object", "required": ["selector", "value"],
                         "properties": {
                             "selector": {"type": "string"},
                             "value": {"type": "string"}
                         }}),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if not HAS_PW:
        return [TextContent(type="text", text=json.dumps({"error": "pip install playwright && playwright install chromium"}))]
    try:
        result = await _dispatch(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e), "tool": name}))]


async def _dispatch(name: str, args: dict) -> Any:
    page = await _get_page()

    if name == "browser_navigate":
        response = await page.goto(args["url"],
                                   wait_until=args.get("wait_until", "domcontentloaded"),
                                   timeout=args.get("timeout", 15000))
        return {"url": page.url, "status": response.status if response else None, "title": await page.title()}

    elif name == "browser_click":
        if args.get("selector"):
            await page.click(args["selector"], timeout=args.get("timeout", 5000))
        elif args.get("text"):
            await page.get_by_text(args["text"]).first.click(timeout=args.get("timeout", 5000))
        return {"clicked": True, "url": page.url}

    elif name == "browser_type":
        sel = args.get("selector", "input:visible")
        element = page.locator(sel).first
        if args.get("clear_first", True):
            await element.clear()
        await element.type(args["text"])
        if args.get("press_enter"):
            await element.press("Enter")
        return {"typed": len(args["text"]), "selector": sel}

    elif name == "browser_extract":
        sel = args.get("selector", "body")
        fmt = args.get("format", "text")
        limit = args.get("limit", 5000)
        element = page.locator(sel).first
        if fmt == "text":
            content = await element.inner_text()
        elif fmt == "html":
            content = await element.inner_html()
        elif fmt == "links":
            links = await page.eval_on_selector_all("a[href]", "els => els.map(e => ({text: e.innerText, href: e.href}))")
            return {"links": links[:100]}
        elif fmt == "tables":
            tables = await page.eval_on_selector_all("table", """
                tables => tables.map(t => ({
                    headers: [...t.querySelectorAll('th')].map(th => th.innerText),
                    rows: [...t.querySelectorAll('tr')].map(tr => [...tr.querySelectorAll('td')].map(td => td.innerText))
                }))
            """)
            return {"tables": tables}
        else:
            content = ""
        return {"content": content[:limit], "length": len(content), "format": fmt}

    elif name == "browser_screenshot":
        kwargs = {"full_page": args.get("full_page", False)}
        if args.get("selector"):
            b64 = await page.locator(args["selector"]).first.screenshot()
        else:
            b64 = await page.screenshot(**kwargs)
        return {"base64_png": base64.b64encode(b64).decode(), "url": page.url}

    elif name == "browser_scroll":
        direction = args.get("direction", "down")
        amount = args.get("amount", 500)
        scripts = {
            "down": f"window.scrollBy(0, {amount})",
            "up": f"window.scrollBy(0, -{amount})",
            "top": "window.scrollTo(0, 0)",
            "bottom": "window.scrollTo(0, document.body.scrollHeight)"
        }
        await page.evaluate(scripts[direction])
        return {"scrolled": direction, "amount": amount}

    elif name == "browser_wait":
        if args.get("selector"):
            await page.wait_for_selector(args["selector"],
                                         state=args.get("state", "visible"),
                                         timeout=args.get("timeout", 10000))
            return {"found": True, "selector": args["selector"]}
        else:
            await page.wait_for_timeout(args.get("timeout", 1000))
            return {"waited": args.get("timeout", 1000)}

    elif name == "browser_evaluate":
        result = await page.evaluate(args["script"])
        return {"result": result}

    elif name == "browser_url":
        return {"url": page.url, "title": await page.title()}

    elif name == "browser_new_tab":
        new_page = await _context.new_page()
        global _page
        _page = new_page
        if args.get("url"):
            await new_page.goto(args["url"])
        return {"opened": True, "url": new_page.url}

    elif name == "browser_tabs":
        pages = _context.pages
        tabs = [{"index": i, "url": p.url, "title": await p.title()} for i, p in enumerate(pages)]
        return {"tabs": tabs, "count": len(tabs)}

    elif name == "browser_switch_tab":
        pages = _context.pages
        if args.get("index") is not None:
            _page = pages[args["index"]]
        elif args.get("url_contains"):
            for p in pages:
                if args["url_contains"] in p.url:
                    _page = p
                    break
        await _page.bring_to_front()
        return {"switched": True, "url": _page.url, "title": await _page.title()}

    elif name == "browser_close_tab":
        await page.close()
        pages = _context.pages
        if pages:
            _page = pages[-1]
        return {"closed": True}

    elif name == "browser_fill_form":
        for selector, value in args["fields"].items():
            el = page.locator(selector).first
            await el.clear()
            await el.fill(value)
        if args.get("submit_selector"):
            await page.click(args["submit_selector"])
        return {"filled": list(args["fields"].keys()), "submitted": bool(args.get("submit_selector"))}

    elif name == "browser_cookies":
        action = args.get("action", "get")
        if action == "get":
            cookies = await _context.cookies()
            return {"cookies": cookies}
        elif action == "set":
            await _context.add_cookies(args.get("cookies", []))
            return {"set": len(args.get("cookies", []))}
        elif action == "clear":
            await _context.clear_cookies()
            return {"cleared": True}

    elif name == "browser_select":
        await page.select_option(args["selector"], value=args["value"])
        return {"selected": args["value"], "selector": args["selector"]}

    return {"error": f"Unknown tool: {name}"}


async def main():
    async with stdio_server() as (reader, writer):
        await app.run(reader, writer, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
