# M4ST → ANTIGRAVITY FULL MIGRATION GUIDE
## v6.0 | April 2026

> **Historical migration reference.** This guide covers the April 2026 setup. The launcher and MCP bundle are retained for reference. They use older client settings and include broad local capabilities. Review them in an isolated workspace before using any component, and keep your existing client config and credentials in place.

For an actively reviewed starting point, see [OpenWork](https://github.com/m4stanuj/openwork) for inspecting IDE config changes and [MAST](https://github.com/m4stanuj/MAST) for the current integration overview.

---

## WHAT THIS DOES

M4ST ka pura backend Antigravity IDE ke andar shift hota hai.

```
BEFORE (M4ST standalone):
  Flask/SocketIO server → Custom UI → Tools

AFTER (Antigravity + M4ST layer):
  Antigravity IDE → MCP Servers → Same tools, same memory, same persona
```

M4ST ka kuch bhi lose nahi hota. Sab kuch MCP ke through Antigravity ko milta hai.

---

## PACKAGE STRUCTURE

```
antigravity_migration/
├── SOUL.md                    ← M4ST personality/identity for Antigravity
├── config/
│   ├── opencode.jsonc         ← 21-provider LLM fallback config
│   └── .env.example           ← API keys template
├── mcps/
│   ├── mcp_system.py          ← PC control + file ops + shell (60+ tools)
│   ├── mcp_memory.py          ← 3-tier memory (working/episodic/semantic)
│   ├── mcp_vision.py          ← DPI-aware screenshot + Qwen3-VL vision
│   ├── mcp_browser.py         ← CDP browser control (Playwright)
│   └── mcp_web.py             ← Search + scrape + research
└── scripts/
    └── start_antigravity.ps1  ← One-click Windows startup
```

---

## SETUP — STEP BY STEP

### Step 1 — Create Antigravity config dir

```powershell
mkdir $env:USERPROFILE\.antigravity\mcps -Force
mkdir $env:USERPROFILE\.m4st\memory -Force
mkdir $env:USERPROFILE\.m4st\screenshots -Force
mkdir $env:USERPROFILE\.m4st\models -Force
```

### Step 2 — Copy files

```powershell
# SOUL.md
Copy-Item SOUL.md "$env:USERPROFILE\.antigravity\SOUL.md"

# Config
Copy-Item config\opencode.jsonc "$env:USERPROFILE\.antigravity\opencode.jsonc"
Copy-Item config\.env.example "$env:USERPROFILE\.antigravity\.env"

# MCP servers
Copy-Item mcps\*.py "$env:USERPROFILE\.antigravity\mcps\"
```

### Step 3 — Fill in API keys

```powershell
notepad $env:USERPROFILE\.antigravity\.env
```

Fill in at minimum:
- `GROQ_API_KEY` — primary provider (free, fast)
- `DEEPSEEK_API_KEY` — code tasks
- `ANTHROPIC_API_KEY` — final fallback

### Step 4 — Install Python dependencies

```powershell
cd $env:USERPROFILE\.antigravity
python -m venv venv
.\venv\Scripts\pip install mcp httpx playwright pyautogui pyperclip pygetwindow pillow chromadb scrapling
.\venv\Scripts\playwright install chromium
```

### Step 5 — Download Qwen3-VL (optional but recommended)

For local vision (screenshots, OCR, UI element finding):

```powershell
# Download from HuggingFace
cd $env:USERPROFILE\.m4st\models

# Model: ~5GB
# Get from: https://huggingface.co/Qwen/Qwen3-VL-7B-GGUF
# File: qwen3-vl-7b-q4_k_m.gguf + qwen3-vl-7b-mmproj.gguf
```

### Step 6 — Link config to Antigravity

Antigravity looks for config in these locations (try each):

```
~/.antigravity/opencode.jsonc   ← Primary (already placed here)
~/.opencode/config.json          ← OpenCode fallback
.antigravity/ (workspace root)   ← Per-project override
```

If Antigravity has a "Custom Instructions" or "System Prompt" setting:
- Point it to: `~/.antigravity/SOUL.md`
- Or paste the SOUL.md content directly

### Step 7 — Run startup script

```powershell
.\scripts\start_antigravity.ps1
```

Or right-click the .ps1 file → "Run with PowerShell"

---

## MCP TOOL COVERAGE

| Category         | Server           | Tools | Replaces |
|-----------------|-----------------|-------|----------|
| Shell/Process    | mcp_system.py    | 15    | M4ST shell tools |
| File Operations  | mcp_system.py    | 20    | M4ST file tools |
| PC Control       | mcp_system.py    | 15    | M4ST Windows tools |
| Browser          | mcp_browser.py   | 16    | M4ST + Tandem CDP |
| Memory T1        | mcp_memory.py    | 4     | M4ST working memory |
| Memory T2        | mcp_memory.py    | 3     | M4ST episodic memory |
| Memory T3        | mcp_memory.py    | 3     | M4ST semantic/ChromaDB |
| Vision           | mcp_vision.py    | 7     | M4ST vision pipeline |
| Web Research     | mcp_web.py       | 8     | M4ST web tools |

**Total: ~91 tools** directly ported. Remaining M4ST tools (code analysis, git, notification chains, etc.) are native to Antigravity/VS Code.

---

## LLM PROVIDER FALLBACK CHAIN

```
groq/llama-3.3-70b          → [1] PRIMARY  (fastest, free)
groq/llama-3.1-8b           → [2] fast tasks
cerebras/llama-4-scout      → [3] fast alternative
cerebras/llama3.1-70b       → [4] smart + fast
openrouter/qwen3-235b:free  → [5] top quality free
openrouter/llama-4:free     → [6] meta free
openrouter/mai-ds-r1:free   → [7] reasoning free
deepseek/deepseek-chat      → [8] smart + cheap
gemini/2.0-flash            → [9] long context (1M tokens)
together/qwen3-235b         → [10] quality
groq/qwen-qwq-32b           → [11] reasoning
groq/deepseek-r1-70b        → [12] reasoning alt
mistral/codestral           → [13] code specialist
cohere/command-r7b          → [14] RAG tasks
claude-haiku-4-5            → [15] premium haiku
claude-sonnet-4-6           → [16] premium smart
gpt-4o-mini                 → [17] openai fallback
gemini-2.5-pro              → [18] premium long ctx
together/deepseek-r1        → [19] deep reasoning
ollama/qwen3:8b             → [20] LOCAL offline
llamacpp/josiefied-qwen3    → [21] LOCAL uncensored
```

---

## TASK-BASED ROUTING

| Task Type    | Model |
|-------------|-------|
| Code gen     | deepseek/deepseek-coder |
| Fast/simple  | groq/llama-3.1-8b-instant |
| Reasoning    | groq/deepseek-r1-distill-70b |
| Vision       | llamacpp/qwen3-vl-7b (local) |
| Long context | gemini/gemini-2.0-flash |
| Private      | llamacpp/josiefied-qwen3-8b |
| Default      | groq/llama-3.3-70b-versatile |

---

## MEMORY SYSTEM

```
TIER 1 — Working (in-memory dict)
  → session state, recent results, active task
  → Tools: memory_working_set/get/list/clear

TIER 2 — Episodic (SQLite at ~/.m4st/memory/episodic.db)
  → conversations, tasks, decisions, errors, insights
  → Tools: memory_episode_save/search/recent

TIER 3 — Semantic (ChromaDB at ~/.m4st/memory/semantic/)
  → long-term knowledge, vector search
  → Tools: memory_semantic_store/search/delete

Cross-tier:
  → memory_recall(query) — searches all tiers automatically
  → memory_stats() — shows counts + disk usage
```

---

## WHAT STAYS WITH M4ST

Some M4ST v6 features are already native to Antigravity and don't need porting:

- **Code editing** — Antigravity's core strength
- **Git operations** — Built-in VS Code git
- **Terminal** — Integrated terminal (use shell_run for MCP access)
- **File tree** — VS Code explorer
- **Extensions** — All VS Code extensions work

The MCP layer fills in the gaps: memory, vision, PC control, browser.

---

## TROUBLESHOOTING

**MCP server not starting:**
```powershell
# Test manually
$env:USERPROFILE\.antigravity\venv\Scripts\python.exe `
  $env:USERPROFILE\.antigravity\mcps\mcp_system.py
# Should show no output (waiting for stdio)
```

**Vision not working:**
```powershell
# Check llama-server
curl http://localhost:8080/health
# Should return {"status":"ok"}
```

**Memory errors:**
```powershell
# ChromaDB needs reset sometimes
Remove-Item "$env:USERPROFILE\.m4st\memory\semantic\" -Recurse -Force
```

**Provider auth errors:**
```powershell
# Verify keys loaded
$env:GROQ_API_KEY  # Should show your key
```

---

## BUILD FAST. SHIP. ITERATE. 👽🤙
