"""
mcp_memory.py — M4ST 3-Tier Memory MCP Server
Antigravity Migration | v6.0

Tier 1 — WORKING  : In-memory dict (session-scoped, instant)
Tier 2 — EPISODIC : SQLite (conversation history, task log)
Tier 3 — SEMANTIC : ChromaDB (vector search, long-term knowledge)

Usage: python mcp_memory.py
"""

import asyncio
import json
import sqlite3
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    raise SystemExit("pip install mcp")

try:
    import chromadb
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False

# ── CONFIG ──────────────────────────────────────────────────────
DATA_DIR = Path.home() / ".m4st" / "memory"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SQLITE_PATH = DATA_DIR / "episodic.db"
CHROMA_PATH = str(DATA_DIR / "semantic")

# ── TIER 1: WORKING MEMORY ───────────────────────────────────────
_working: dict[str, Any] = {}

# ── TIER 2: EPISODIC SQLITE ──────────────────────────────────────
def _get_db():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            session_id TEXT,
            type TEXT,
            content TEXT NOT NULL,
            tags TEXT,
            importance INTEGER DEFAULT 5
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_type ON episodes(type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON episodes(session_id)")
    conn.commit()
    return conn

# ── TIER 3: SEMANTIC CHROMA ───────────────────────────────────────
def _get_collection():
    if not HAS_CHROMA:
        return None
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return client.get_or_create_collection("m4st_semantic")

app = Server("m4st-memory")

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        # ── TIER 1: WORKING ──────────────────────────────────────
        Tool(name="memory_working_set",
             description="Store a value in working memory (session-scoped, fast).",
             inputSchema={"type": "object", "required": ["key", "value"],
                         "properties": {
                             "key": {"type": "string"},
                             "value": {}
                         }}),

        Tool(name="memory_working_get",
             description="Get a value from working memory by key.",
             inputSchema={"type": "object", "required": ["key"],
                         "properties": {"key": {"type": "string"}}}),

        Tool(name="memory_working_list",
             description="List all keys in working memory.",
             inputSchema={"type": "object", "properties": {}}),

        Tool(name="memory_working_clear",
             description="Clear working memory (all or specific key).",
             inputSchema={"type": "object",
                         "properties": {"key": {"type": "string", "description": "If omitted, clears all"}}}),

        # ── TIER 2: EPISODIC ──────────────────────────────────────
        Tool(name="memory_episode_save",
             description="Save an episode to episodic memory (conversation, task, decision, event).",
             inputSchema={"type": "object", "required": ["content"],
                         "properties": {
                             "content": {"type": "string", "description": "What happened / what was said"},
                             "type": {"type": "string",
                                     "enum": ["conversation", "task", "decision", "error", "insight", "note"],
                                     "default": "note"},
                             "session_id": {"type": "string"},
                             "tags": {"type": "array", "items": {"type": "string"}},
                             "importance": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5}
                         }}),

        Tool(name="memory_episode_search",
             description="Search episodic memory by keyword, type, date, or tags.",
             inputSchema={"type": "object",
                         "properties": {
                             "query": {"type": "string", "description": "Keyword search"},
                             "type": {"type": "string", "enum": ["conversation", "task", "decision", "error", "insight", "note"]},
                             "tags": {"type": "array", "items": {"type": "string"}},
                             "date_from": {"type": "string", "description": "ISO date string"},
                             "date_to": {"type": "string"},
                             "limit": {"type": "integer", "default": 20},
                             "min_importance": {"type": "integer", "default": 1}
                         }}),

        Tool(name="memory_episode_recent",
             description="Get the N most recent episodes.",
             inputSchema={"type": "object",
                         "properties": {
                             "n": {"type": "integer", "default": 10},
                             "type": {"type": "string"}
                         }}),

        # ── TIER 3: SEMANTIC ──────────────────────────────────────
        Tool(name="memory_semantic_store",
             description="Store a knowledge chunk in semantic memory (long-term, vector-searchable).",
             inputSchema={"type": "object", "required": ["text"],
                         "properties": {
                             "text": {"type": "string", "description": "Knowledge to store"},
                             "id": {"type": "string", "description": "Unique ID (auto-generated if omitted)"},
                             "metadata": {"type": "object", "description": "Extra metadata dict"}
                         }}),

        Tool(name="memory_semantic_search",
             description="Search semantic memory by meaning (vector similarity). Tier 3.",
             inputSchema={"type": "object", "required": ["query"],
                         "properties": {
                             "query": {"type": "string", "description": "Natural language query"},
                             "n_results": {"type": "integer", "default": 5},
                             "filter": {"type": "object", "description": "Metadata filter dict"}
                         }}),

        Tool(name="memory_semantic_delete",
             description="Delete a semantic memory chunk by ID.",
             inputSchema={"type": "object", "required": ["id"],
                         "properties": {"id": {"type": "string"}}}),

        # ── CROSS-TIER ────────────────────────────────────────────
        Tool(name="memory_recall",
             description="Smart recall — searches ALL tiers and returns best matches. Use this as default.",
             inputSchema={"type": "object", "required": ["query"],
                         "properties": {
                             "query": {"type": "string"},
                             "tiers": {"type": "array", "items": {"type": "string"},
                                      "default": ["working", "episodic", "semantic"],
                                      "description": "Which tiers to search"},
                             "limit_per_tier": {"type": "integer", "default": 3}
                         }}),

        Tool(name="memory_stats",
             description="Get memory system stats: counts per tier, disk usage.",
             inputSchema={"type": "object", "properties": {}}),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        result = await _dispatch(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e), "tool": name}))]


async def _dispatch(name: str, args: dict) -> Any:
    # ── TIER 1 ────────────────────────────────────────────────
    if name == "memory_working_set":
        _working[args["key"]] = args["value"]
        return {"stored": args["key"], "tier": 1}

    elif name == "memory_working_get":
        key = args["key"]
        return {"key": key, "value": _working.get(key), "found": key in _working}

    elif name == "memory_working_list":
        return {"keys": list(_working.keys()), "count": len(_working)}

    elif name == "memory_working_clear":
        key = args.get("key")
        if key:
            removed = _working.pop(key, None)
            return {"cleared": key, "existed": removed is not None}
        _working.clear()
        return {"cleared": "all"}

    # ── TIER 2 ────────────────────────────────────────────────
    elif name == "memory_episode_save":
        conn = _get_db()
        tags = json.dumps(args.get("tags", []))
        conn.execute(
            "INSERT INTO episodes (timestamp, session_id, type, content, tags, importance) VALUES (?,?,?,?,?,?)",
            (datetime.now().isoformat(), args.get("session_id", "default"),
             args.get("type", "note"), args["content"], tags, args.get("importance", 5))
        )
        conn.commit()
        conn.close()
        return {"saved": True, "tier": 2, "type": args.get("type", "note")}

    elif name == "memory_episode_search":
        conn = _get_db()
        clauses, params = [], []
        if args.get("query"):
            clauses.append("content LIKE ?")
            params.append(f"%{args['query']}%")
        if args.get("type"):
            clauses.append("type = ?")
            params.append(args["type"])
        if args.get("date_from"):
            clauses.append("timestamp >= ?")
            params.append(args["date_from"])
        if args.get("date_to"):
            clauses.append("timestamp <= ?")
            params.append(args["date_to"])
        clauses.append("importance >= ?")
        params.append(args.get("min_importance", 1))
        where = " AND ".join(clauses) if clauses else "1=1"
        rows = conn.execute(
            f"SELECT id, timestamp, type, content, tags, importance FROM episodes WHERE {where} ORDER BY timestamp DESC LIMIT ?",
            params + [args.get("limit", 20)]
        ).fetchall()
        conn.close()
        return {"results": [{"id": r[0], "timestamp": r[1], "type": r[2],
                             "content": r[3], "tags": json.loads(r[4] or "[]"),
                             "importance": r[5]} for r in rows],
                "count": len(rows)}

    elif name == "memory_episode_recent":
        conn = _get_db()
        type_clause = "AND type = ?" if args.get("type") else ""
        params = [args.get("n", 10)]
        if args.get("type"):
            params = [args["type"], args.get("n", 10)]
        rows = conn.execute(
            f"SELECT id, timestamp, type, content, importance FROM episodes {type_clause} ORDER BY timestamp DESC LIMIT ?",
            params
        ).fetchall()
        conn.close()
        return {"recent": [{"id": r[0], "timestamp": r[1], "type": r[2],
                            "content": r[3], "importance": r[4]} for r in rows]}

    # ── TIER 3 ────────────────────────────────────────────────
    elif name == "memory_semantic_store":
        if not HAS_CHROMA:
            return {"error": "pip install chromadb"}
        col = _get_collection()
        doc_id = args.get("id") or hashlib.md5(args["text"].encode()).hexdigest()
        metadata = args.get("metadata", {})
        metadata["timestamp"] = datetime.now().isoformat()
        col.upsert(ids=[doc_id], documents=[args["text"]], metadatas=[metadata])
        return {"stored": True, "id": doc_id, "tier": 3}

    elif name == "memory_semantic_search":
        if not HAS_CHROMA:
            return {"error": "pip install chromadb"}
        col = _get_collection()
        where = args.get("filter")
        kwargs = {"query_texts": [args["query"]], "n_results": args.get("n_results", 5)}
        if where:
            kwargs["where"] = where
        results = col.query(**kwargs)
        items = []
        for i, doc in enumerate(results["documents"][0]):
            items.append({
                "text": doc,
                "id": results["ids"][0][i],
                "distance": results["distances"][0][i] if results.get("distances") else None,
                "metadata": results["metadatas"][0][i] if results.get("metadatas") else {}
            })
        return {"results": items, "query": args["query"]}

    elif name == "memory_semantic_delete":
        if not HAS_CHROMA:
            return {"error": "pip install chromadb"}
        _get_collection().delete(ids=[args["id"]])
        return {"deleted": args["id"]}

    # ── CROSS-TIER ────────────────────────────────────────────
    elif name == "memory_recall":
        query = args["query"]
        tiers = args.get("tiers", ["working", "episodic", "semantic"])
        limit = args.get("limit_per_tier", 3)
        results = {}
        if "working" in tiers:
            matches = {k: v for k, v in _working.items()
                      if query.lower() in str(k).lower() or query.lower() in str(v).lower()}
            results["working"] = list(matches.items())[:limit]
        if "episodic" in tiers:
            ep = await _dispatch("memory_episode_search", {"query": query, "limit": limit})
            results["episodic"] = ep.get("results", [])
        if "semantic" in tiers and HAS_CHROMA:
            sem = await _dispatch("memory_semantic_search", {"query": query, "n_results": limit})
            results["semantic"] = sem.get("results", [])
        return {"query": query, "recall": results}

    elif name == "memory_stats":
        conn = _get_db()
        ep_count = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
        ep_by_type = conn.execute("SELECT type, COUNT(*) FROM episodes GROUP BY type").fetchall()
        conn.close()
        sem_count = 0
        if HAS_CHROMA:
            sem_count = _get_collection().count()
        return {
            "working": {"count": len(_working), "tier": 1},
            "episodic": {"count": ep_count, "by_type": dict(ep_by_type), "tier": 2, "db": str(SQLITE_PATH)},
            "semantic": {"count": sem_count, "tier": 3, "chroma": CHROMA_PATH, "available": HAS_CHROMA}
        }

    return {"error": f"Unknown tool: {name}"}


async def main():
    async with stdio_server() as (reader, writer):
        await app.run(reader, writer, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
