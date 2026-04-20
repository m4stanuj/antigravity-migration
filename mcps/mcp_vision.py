"""
mcp_vision.py — M4ST Vision MCP Server
Antigravity Migration | v6.0

Tools:
  screenshot_take       — DPI-aware full/region screenshot
  screenshot_annotate   — Draw boxes/labels on screenshot
  vision_analyze        — Send image to Qwen3-VL for analysis
  vision_ocr            — Extract text from image (Qwen3-VL or pytesseract)
  element_find          — Find UI element on screen by description
  element_click         — Find + click element in one call (M4ST v12 feature)

Vision backend: Local Qwen3-VL via llama-server (localhost:8080)
Fallback: OpenAI-compatible vision (Claude / GPT-4o)
"""

import asyncio
import base64
import io
import json
import os
import httpx
import ctypes
from pathlib import Path
from datetime import datetime
from typing import Any

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    raise SystemExit("pip install mcp")

try:
    import pyautogui
    from PIL import Image, ImageDraw, ImageFont
    HAS_GUI = True
except ImportError:
    HAS_GUI = False

# ── CONFIG ──────────────────────────────────────────────────────
VISION_URL = os.environ.get("VISION_URL", "http://localhost:8080/v1")  # llama-server
VISION_MODEL = os.environ.get("VISION_MODEL", "qwen3-vl-7b")
FALLBACK_URL = os.environ.get("FALLBACK_VISION_URL", "https://api.anthropic.com/v1")
SCREENSHOTS_DIR = Path.home() / ".m4st" / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

app = Server("m4st-vision")


def _get_dpi_scale() -> float:
    """Windows DPI scaling factor."""
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return dpi / 96.0
    except Exception:
        return 1.0


def _capture(region=None) -> Image.Image:
    """DPI-aware screenshot using pyautogui."""
    scale = _get_dpi_scale()
    img = pyautogui.screenshot(region=region)
    if scale != 1.0 and region is None:
        # Downscale to logical resolution
        logical_w = int(img.width / scale)
        logical_h = int(img.height / scale)
        img = img.resize((logical_w, logical_h), Image.LANCZOS)
    return img


def _img_to_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


async def _vision_query(b64_image: str, prompt: str) -> str:
    """Send image to Qwen3-VL via llama-server (OpenAI-compatible)."""
    payload = {
        "model": VISION_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_image}"}},
                {"type": "text", "text": prompt}
            ]
        }],
        "max_tokens": 1024
    }
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(f"{VISION_URL}/chat/completions", json=payload)
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Vision error: {e}"


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="screenshot_take",
             description="Take a DPI-aware screenshot of full screen or a region. Returns base64 PNG + saves to disk.",
             inputSchema={"type": "object",
                         "properties": {
                             "region": {"type": "array", "items": {"type": "integer"},
                                       "description": "[x, y, width, height] in logical pixels. Full screen if omitted."},
                             "save": {"type": "boolean", "default": True, "description": "Save to ~/.m4st/screenshots/"},
                             "filename": {"type": "string", "description": "Custom filename (optional)"}
                         }}),

        Tool(name="screenshot_annotate",
             description="Draw bounding boxes and labels on a screenshot. Useful for highlighting UI elements.",
             inputSchema={"type": "object", "required": ["base64_png", "boxes"],
                         "properties": {
                             "base64_png": {"type": "string"},
                             "boxes": {
                                 "type": "array",
                                 "items": {
                                     "type": "object",
                                     "properties": {
                                         "x": {"type": "integer"}, "y": {"type": "integer"},
                                         "w": {"type": "integer"}, "h": {"type": "integer"},
                                         "label": {"type": "string"},
                                         "color": {"type": "string", "default": "red"}
                                     }
                                 }
                             }
                         }}),

        Tool(name="vision_analyze",
             description="Analyze an image with Qwen3-VL. Can describe UI, identify elements, read content.",
             inputSchema={"type": "object", "required": ["prompt"],
                         "properties": {
                             "prompt": {"type": "string", "description": "What to analyze or extract"},
                             "base64_png": {"type": "string", "description": "Image to analyze (takes screenshot if omitted)"},
                             "region": {"type": "array", "items": {"type": "integer"},
                                       "description": "[x, y, w, h] — capture region if no image provided"}
                         }}),

        Tool(name="vision_ocr",
             description="Extract text from image using Qwen3-VL (or pytesseract fallback).",
             inputSchema={"type": "object",
                         "properties": {
                             "base64_png": {"type": "string"},
                             "region": {"type": "array", "items": {"type": "integer"}},
                             "language": {"type": "string", "default": "eng"}
                         }}),

        Tool(name="element_find",
             description="Find a UI element on screen by description. Returns coordinates.",
             inputSchema={"type": "object", "required": ["description"],
                         "properties": {
                             "description": {"type": "string",
                                            "description": "Natural language description of element (e.g. 'Submit button', 'search box')"},
                             "confidence_threshold": {"type": "number", "default": 0.7}
                         }}),

        Tool(name="element_click",
             description="Find a UI element by description and click it. One-step find+click (M4ST v12).",
             inputSchema={"type": "object", "required": ["description"],
                         "properties": {
                             "description": {"type": "string"},
                             "button": {"type": "string", "enum": ["left", "right", "double"], "default": "left"},
                             "screenshot_after": {"type": "boolean", "default": True}
                         }}),

        Tool(name="vision_compare",
             description="Compare two screenshots and describe differences.",
             inputSchema={"type": "object", "required": ["image1_b64", "image2_b64"],
                         "properties": {
                             "image1_b64": {"type": "string"},
                             "image2_b64": {"type": "string"},
                             "focus": {"type": "string", "description": "What to focus comparison on"}
                         }}),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        result = await _dispatch(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e), "tool": name}))]


async def _dispatch(name: str, args: dict) -> Any:

    if name == "screenshot_take":
        if not HAS_GUI:
            return {"error": "pip install pyautogui pillow"}
        region = tuple(args["region"]) if args.get("region") else None
        img = _capture(region)
        b64 = _img_to_b64(img)
        saved_path = None
        if args.get("save", True):
            fname = args.get("filename") or f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            saved_path = str(SCREENSHOTS_DIR / fname)
            img.save(saved_path)
        return {
            "width": img.width, "height": img.height,
            "base64_png": b64,
            "saved": saved_path
        }

    elif name == "screenshot_annotate":
        img_data = base64.b64decode(args["base64_png"])
        img = Image.open(io.BytesIO(img_data)).copy()
        draw = ImageDraw.Draw(img)
        for box in args["boxes"]:
            x, y, w, h = box["x"], box["y"], box.get("w", 50), box.get("h", 30)
            color = box.get("color", "red")
            draw.rectangle([x, y, x+w, y+h], outline=color, width=2)
            label = box.get("label")
            if label:
                draw.text((x+4, y+4), label, fill=color)
        return {"annotated_png": _img_to_b64(img)}

    elif name == "vision_analyze":
        if args.get("base64_png"):
            b64 = args["base64_png"]
        else:
            if not HAS_GUI:
                return {"error": "pip install pyautogui"}
            region = tuple(args["region"]) if args.get("region") else None
            img = _capture(region)
            b64 = _img_to_b64(img)
        answer = await _vision_query(b64, args["prompt"])
        return {"analysis": answer, "prompt": args["prompt"]}

    elif name == "vision_ocr":
        if args.get("base64_png"):
            b64 = args["base64_png"]
        else:
            if not HAS_GUI:
                return {"error": "pip install pyautogui"}
            region = tuple(args["region"]) if args.get("region") else None
            img = _capture(region)
            b64 = _img_to_b64(img)
        # Try Qwen3-VL first
        text = await _vision_query(b64, "Extract all visible text from this image. Return only the text, no commentary.")
        if text.startswith("Vision error"):
            # Fallback to pytesseract
            try:
                import pytesseract
                img_data = base64.b64decode(b64)
                img = Image.open(io.BytesIO(img_data))
                text = pytesseract.image_to_string(img, lang=args.get("language", "eng"))
            except ImportError:
                return {"error": "Qwen3-VL unavailable and pytesseract not installed"}
        return {"text": text}

    elif name == "element_find":
        if not HAS_GUI:
            return {"error": "pip install pyautogui pillow"}
        img = _capture()
        b64 = _img_to_b64(img)
        prompt = f"""
        Look at this screenshot. Find the UI element described as: "{args['description']}"
        Return a JSON object with:
        {{
          "found": true/false,
          "x": center_x_coordinate,
          "y": center_y_coordinate,
          "description": "what you found",
          "confidence": 0.0-1.0
        }}
        Return only the JSON, nothing else.
        """
        response = await _vision_query(b64, prompt)
        try:
            # Extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                result["screenshot_size"] = {"width": img.width, "height": img.height}
                return result
        except Exception:
            pass
        return {"found": False, "raw_response": response}

    elif name == "element_click":
        find_result = await _dispatch("element_find", {"description": args["description"]})
        if not find_result.get("found"):
            return {"clicked": False, "reason": "Element not found", "find_result": find_result}
        x, y = find_result["x"], find_result["y"]
        import pyautogui
        button = args.get("button", "left")
        if button == "double":
            pyautogui.doubleClick(x, y)
        else:
            pyautogui.click(x, y, button=button)
        result = {"clicked": True, "x": x, "y": y, "element": find_result.get("description")}
        if args.get("screenshot_after", True):
            import asyncio
            await asyncio.sleep(0.5)
            after = await _dispatch("screenshot_take", {"save": False})
            result["screenshot_after"] = after.get("base64_png")
        return result

    elif name == "vision_compare":
        prompt = f"Compare these two screenshots and describe what changed or is different."
        if args.get("focus"):
            prompt += f" Focus specifically on: {args['focus']}"
        # Analyze both separately then compare
        a1 = await _vision_query(args["image1_b64"], "Describe this screenshot in detail.")
        a2 = await _vision_query(args["image2_b64"], "Describe this screenshot in detail.")
        comparison_prompt = f"""
        Screenshot 1: {a1}
        Screenshot 2: {a2}
        What are the key differences between these two?
        """
        diff = await _vision_query(args["image1_b64"], comparison_prompt)
        return {"comparison": diff, "image1_desc": a1, "image2_desc": a2}

    return {"error": f"Unknown tool: {name}"}


async def main():
    async with stdio_server() as (reader, writer):
        await app.run(reader, writer, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
