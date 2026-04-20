"""
mcp_system.py — M4ST System MCP Server
Antigravity Migration | v6.0

Tools:
  Shell / Process (15 tools)
  File Operations (20 tools)
  Windows PC Control (15 tools)
  Clipboard & UI (10 tools)

Usage: python mcp_system.py
Port:  Stdio (MCP standard)
"""

import asyncio
import json
import os
import subprocess
import shutil
import tempfile
import winreg
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
    import pygetwindow as gw
    import pyperclip
    HAS_GUI = True
except ImportError:
    HAS_GUI = False

app = Server("m4st-system")

# ══════════════════════════════════════════════════════════════
# TOOL REGISTRY
# ══════════════════════════════════════════════════════════════

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        # ── SHELL / PROCESS ──────────────────────────────────
        Tool(name="shell_run",
             description="Execute a shell command (PowerShell on Windows). Returns stdout, stderr, returncode.",
             inputSchema={"type": "object", "required": ["command"],
                         "properties": {
                             "command": {"type": "string", "description": "Shell command to run"},
                             "cwd": {"type": "string", "description": "Working directory (optional)"},
                             "timeout": {"type": "integer", "default": 30, "description": "Timeout in seconds"}
                         }}),

        Tool(name="shell_run_bg",
             description="Run a command in background (non-blocking). Returns PID.",
             inputSchema={"type": "object", "required": ["command"],
                         "properties": {
                             "command": {"type": "string"},
                             "cwd": {"type": "string"}
                         }}),

        Tool(name="process_list",
             description="List running processes. Filter by name.",
             inputSchema={"type": "object",
                         "properties": {
                             "filter": {"type": "string", "description": "Filter by process name (optional)"}
                         }}),

        Tool(name="process_kill",
             description="Kill a process by PID or name.",
             inputSchema={"type": "object",
                         "properties": {
                             "pid": {"type": "integer"},
                             "name": {"type": "string"}
                         }}),

        Tool(name="env_get",
             description="Get environment variables. Key optional — returns all if not specified.",
             inputSchema={"type": "object",
                         "properties": {
                             "key": {"type": "string"}
                         }}),

        Tool(name="env_set",
             description="Set an environment variable for current session.",
             inputSchema={"type": "object", "required": ["key", "value"],
                         "properties": {
                             "key": {"type": "string"},
                             "value": {"type": "string"}
                         }}),

        # ── FILE OPERATIONS ───────────────────────────────────
        Tool(name="file_read",
             description="Read a file. Returns content as string.",
             inputSchema={"type": "object", "required": ["path"],
                         "properties": {
                             "path": {"type": "string"},
                             "encoding": {"type": "string", "default": "utf-8"},
                             "lines": {"type": "array", "items": {"type": "integer"},
                                      "description": "[start, end] line range (optional)"}
                         }}),

        Tool(name="file_write",
             description="Write content to a file. Creates parent dirs if needed.",
             inputSchema={"type": "object", "required": ["path", "content"],
                         "properties": {
                             "path": {"type": "string"},
                             "content": {"type": "string"},
                             "encoding": {"type": "string", "default": "utf-8"},
                             "append": {"type": "boolean", "default": False}
                         }}),

        Tool(name="file_delete",
             description="Delete a file or empty directory.",
             inputSchema={"type": "object", "required": ["path"],
                         "properties": {"path": {"type": "string"}}}),

        Tool(name="file_copy",
             description="Copy a file or directory.",
             inputSchema={"type": "object", "required": ["src", "dst"],
                         "properties": {
                             "src": {"type": "string"},
                             "dst": {"type": "string"}
                         }}),

        Tool(name="file_move",
             description="Move/rename a file or directory.",
             inputSchema={"type": "object", "required": ["src", "dst"],
                         "properties": {
                             "src": {"type": "string"},
                             "dst": {"type": "string"}
                         }}),

        Tool(name="file_exists",
             description="Check if a path exists. Returns exists, is_file, is_dir, size.",
             inputSchema={"type": "object", "required": ["path"],
                         "properties": {"path": {"type": "string"}}}),

        Tool(name="dir_list",
             description="List directory contents with metadata.",
             inputSchema={"type": "object", "required": ["path"],
                         "properties": {
                             "path": {"type": "string"},
                             "recursive": {"type": "boolean", "default": False},
                             "pattern": {"type": "string", "description": "Glob pattern (e.g. *.py)"}
                         }}),

        Tool(name="dir_create",
             description="Create a directory (with parents).",
             inputSchema={"type": "object", "required": ["path"],
                         "properties": {"path": {"type": "string"}}}),

        Tool(name="file_search",
             description="Search for text in files under a directory.",
             inputSchema={"type": "object", "required": ["directory", "query"],
                         "properties": {
                             "directory": {"type": "string"},
                             "query": {"type": "string"},
                             "pattern": {"type": "string", "default": "*"},
                             "case_sensitive": {"type": "boolean", "default": False},
                             "max_results": {"type": "integer", "default": 50}
                         }}),

        Tool(name="file_info",
             description="Get detailed file metadata: size, timestamps, permissions.",
             inputSchema={"type": "object", "required": ["path"],
                         "properties": {"path": {"type": "string"}}}),

        # ── WINDOWS PC CONTROL ────────────────────────────────
        Tool(name="screen_screenshot",
             description="Take a DPI-aware screenshot. Returns base64 PNG.",
             inputSchema={"type": "object",
                         "properties": {
                             "region": {"type": "array", "items": {"type": "integer"},
                                       "description": "[x, y, width, height] — full screen if omitted"},
                             "save_path": {"type": "string", "description": "Optional path to save PNG"}
                         }}),

        Tool(name="mouse_click",
             description="Click at screen coordinates.",
             inputSchema={"type": "object", "required": ["x", "y"],
                         "properties": {
                             "x": {"type": "integer"},
                             "y": {"type": "integer"},
                             "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                             "double": {"type": "boolean", "default": False}
                         }}),

        Tool(name="mouse_move",
             description="Move mouse to coordinates.",
             inputSchema={"type": "object", "required": ["x", "y"],
                         "properties": {
                             "x": {"type": "integer"},
                             "y": {"type": "integer"},
                             "duration": {"type": "number", "default": 0.2}
                         }}),

        Tool(name="keyboard_type",
             description="Type text using keyboard.",
             inputSchema={"type": "object", "required": ["text"],
                         "properties": {
                             "text": {"type": "string"},
                             "interval": {"type": "number", "default": 0.02}
                         }}),

        Tool(name="keyboard_hotkey",
             description="Press a keyboard hotkey combination.",
             inputSchema={"type": "object", "required": ["keys"],
                         "properties": {
                             "keys": {"type": "array", "items": {"type": "string"},
                                    "description": "e.g. ['ctrl', 'c'] or ['win', 'd']"}
                         }}),

        Tool(name="window_list",
             description="List all open windows with title and handle.",
             inputSchema={"type": "object",
                         "properties": {
                             "filter": {"type": "string", "description": "Filter by title"}
                         }}),

        Tool(name="window_focus",
             description="Bring a window to focus by title.",
             inputSchema={"type": "object", "required": ["title"],
                         "properties": {
                             "title": {"type": "string"},
                             "partial_match": {"type": "boolean", "default": True}
                         }}),

        Tool(name="clipboard_read",
             description="Read current clipboard content.",
             inputSchema={"type": "object", "properties": {}}),

        Tool(name="clipboard_write",
             description="Write text to clipboard.",
             inputSchema={"type": "object", "required": ["text"],
                         "properties": {"text": {"type": "string"}}}),

        Tool(name="notify",
             description="Send a Windows notification toast.",
             inputSchema={"type": "object", "required": ["title", "message"],
                         "properties": {
                             "title": {"type": "string"},
                             "message": {"type": "string"},
                             "duration": {"type": "integer", "default": 5}
                         }}),

        Tool(name="system_info",
             description="Get system info: CPU, RAM, GPU, disk usage.",
             inputSchema={"type": "object", "properties": {}}),
    ]


# ══════════════════════════════════════════════════════════════
# TOOL HANDLERS
# ══════════════════════════════════════════════════════════════

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        result = await _dispatch(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e), "tool": name}))]


async def _dispatch(name: str, args: dict) -> Any:

    # ── SHELL ──────────────────────────────────────────────────
    if name == "shell_run":
        cmd = args["command"]
        cwd = args.get("cwd", None)
        timeout = args.get("timeout", 30)
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, cwd=cwd, timeout=timeout
        )
        return {
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode
        }

    elif name == "shell_run_bg":
        cmd = args["command"]
        cwd = args.get("cwd", None)
        proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", cmd],
            cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return {"pid": proc.pid, "status": "running"}

    elif name == "process_list":
        filter_name = args.get("filter", "").lower()
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-Process | Select-Object Id,ProcessName,CPU,WorkingSet | ConvertTo-Json"],
            capture_output=True, text=True
        )
        procs = json.loads(result.stdout or "[]")
        if filter_name:
            procs = [p for p in procs if filter_name in p.get("ProcessName", "").lower()]
        return {"processes": procs[:50]}

    elif name == "process_kill":
        pid = args.get("pid")
        proc_name = args.get("name")
        if pid:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
            return {"killed": f"PID {pid}"}
        elif proc_name:
            subprocess.run(["taskkill", "/IM", proc_name, "/F"], capture_output=True)
            return {"killed": proc_name}

    elif name == "env_get":
        key = args.get("key")
        if key:
            return {"key": key, "value": os.environ.get(key)}
        return dict(os.environ)

    elif name == "env_set":
        os.environ[args["key"]] = args["value"]
        return {"set": args["key"], "value": args["value"]}

    # ── FILE OPS ───────────────────────────────────────────────
    elif name == "file_read":
        path = Path(args["path"])
        encoding = args.get("encoding", "utf-8")
        content = path.read_text(encoding=encoding)
        lines = args.get("lines")
        if lines and len(lines) == 2:
            all_lines = content.splitlines()
            content = "\n".join(all_lines[lines[0]-1:lines[1]])
        return {"path": str(path), "content": content, "size": len(content)}

    elif name == "file_write":
        path = Path(args["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if args.get("append") else "w"
        path.open(mode, encoding=args.get("encoding", "utf-8")).write(args["content"])
        return {"written": str(path), "bytes": len(args["content"].encode())}

    elif name == "file_delete":
        path = Path(args["path"])
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
        return {"deleted": str(path)}

    elif name == "file_copy":
        src, dst = Path(args["src"]), Path(args["dst"])
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        return {"copied": f"{src} → {dst}"}

    elif name == "file_move":
        shutil.move(args["src"], args["dst"])
        return {"moved": f"{args['src']} → {args['dst']}"}

    elif name == "file_exists":
        p = Path(args["path"])
        return {
            "exists": p.exists(),
            "is_file": p.is_file(),
            "is_dir": p.is_dir(),
            "size": p.stat().st_size if p.exists() else None
        }

    elif name == "dir_list":
        p = Path(args["path"])
        pattern = args.get("pattern", "*")
        if args.get("recursive"):
            items = list(p.rglob(pattern))
        else:
            items = list(p.glob(pattern))
        return {"items": [{"name": i.name, "is_file": i.is_file(),
                           "size": i.stat().st_size if i.is_file() else None}
                          for i in items[:200]]}

    elif name == "dir_create":
        Path(args["path"]).mkdir(parents=True, exist_ok=True)
        return {"created": args["path"]}

    elif name == "file_search":
        results = []
        directory = Path(args["directory"])
        query = args["query"]
        pattern = args.get("pattern", "*")
        case_sensitive = args.get("case_sensitive", False)
        max_results = args.get("max_results", 50)
        search_q = query if case_sensitive else query.lower()
        for f in directory.rglob(pattern):
            if not f.is_file():
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
                haystack = text if case_sensitive else text.lower()
                if search_q in haystack:
                    results.append(str(f))
                    if len(results) >= max_results:
                        break
            except Exception:
                pass
        return {"query": query, "matches": results, "count": len(results)}

    elif name == "file_info":
        p = Path(args["path"])
        stat = p.stat()
        return {
            "path": str(p.resolve()),
            "size_bytes": stat.st_size,
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "is_file": p.is_file(),
            "suffix": p.suffix
        }

    # ── WINDOWS PC CONTROL ─────────────────────────────────────
    elif name == "screen_screenshot":
        import base64, io
        if not HAS_GUI:
            return {"error": "pip install pyautogui pillow"}
        region = args.get("region")
        img = pyautogui.screenshot(region=tuple(region) if region else None)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        save_path = args.get("save_path")
        if save_path:
            img.save(save_path)
        return {
            "width": img.width,
            "height": img.height,
            "base64_png": b64,
            "saved": save_path
        }

    elif name == "mouse_click":
        if not HAS_GUI:
            return {"error": "pip install pyautogui"}
        x, y = args["x"], args["y"]
        button = args.get("button", "left")
        if args.get("double"):
            pyautogui.doubleClick(x, y, button=button)
        else:
            pyautogui.click(x, y, button=button)
        return {"clicked": {"x": x, "y": y, "button": button}}

    elif name == "mouse_move":
        if not HAS_GUI:
            return {"error": "pip install pyautogui"}
        pyautogui.moveTo(args["x"], args["y"], duration=args.get("duration", 0.2))
        return {"moved_to": {"x": args["x"], "y": args["y"]}}

    elif name == "keyboard_type":
        if not HAS_GUI:
            return {"error": "pip install pyautogui"}
        pyautogui.typewrite(args["text"], interval=args.get("interval", 0.02))
        return {"typed": len(args["text"]), "chars": True}

    elif name == "keyboard_hotkey":
        if not HAS_GUI:
            return {"error": "pip install pyautogui"}
        pyautogui.hotkey(*args["keys"])
        return {"hotkey": "+".join(args["keys"])}

    elif name == "window_list":
        if not HAS_GUI:
            return {"error": "pip install pygetwindow"}
        wins = gw.getAllWindows()
        f = args.get("filter", "").lower()
        result = [{"title": w.title, "visible": w.visible}
                  for w in wins if not f or f in w.title.lower()]
        return {"windows": result[:50]}

    elif name == "window_focus":
        if not HAS_GUI:
            return {"error": "pip install pygetwindow"}
        title = args["title"]
        partial = args.get("partial_match", True)
        wins = gw.getWindowsWithTitle(title) if not partial else \
               [w for w in gw.getAllWindows() if title.lower() in w.title.lower()]
        if wins:
            wins[0].activate()
            return {"focused": wins[0].title}
        return {"error": f"Window '{title}' not found"}

    elif name == "clipboard_read":
        if not HAS_GUI:
            return {"error": "pip install pyperclip"}
        return {"content": pyperclip.paste()}

    elif name == "clipboard_write":
        if not HAS_GUI:
            return {"error": "pip install pyperclip"}
        pyperclip.copy(args["text"])
        return {"written": True, "length": len(args["text"])}

    elif name == "notify":
        title = args["title"]
        msg = args["message"]
        # Windows toast via PowerShell
        ps_cmd = f'''
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null
        $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
        $textNodes = $template.GetElementsByTagName("text")
        $textNodes[0].AppendChild($template.CreateTextNode("{title}")) | Out-Null
        $textNodes[1].AppendChild($template.CreateTextNode("{msg}")) | Out-Null
        $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("M4ST").Show($toast)
        '''
        subprocess.Popen(["powershell", "-Command", ps_cmd])
        return {"notified": True, "title": title, "message": msg}

    elif name == "system_info":
        result = subprocess.run(
            ["powershell", "-Command", """
                $cpu = (Get-WmiObject Win32_Processor | Select-Object -First 1 LoadPercentage).LoadPercentage
                $ram = Get-WmiObject Win32_OperatingSystem | Select-Object FreePhysicalMemory, TotalVisibleMemorySize
                $disk = Get-PSDrive C | Select-Object Used, Free
                [PSCustomObject]@{
                    cpu_percent = $cpu
                    ram_free_mb = [math]::Round($ram.FreePhysicalMemory / 1024, 1)
                    ram_total_mb = [math]::Round($ram.TotalVisibleMemorySize / 1024, 1)
                    disk_used_gb = [math]::Round($disk.Used / 1GB, 2)
                    disk_free_gb = [math]::Round($disk.Free / 1GB, 2)
                } | ConvertTo-Json
            """],
            capture_output=True, text=True
        )
        return json.loads(result.stdout or "{}")

    return {"error": f"Unknown tool: {name}"}


# ══════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════

async def main():
    async with stdio_server() as (reader, writer):
        await app.run(reader, writer, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
