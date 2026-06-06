# Reddit — r/AI_agents

**Title:** I built an open-source personal AI OS on Claude Cowork — it runs my job search, trading research, and knowledge vault autonomously

---

I've been quietly building this for a few weeks and finally cleaned it up enough to open-source it. It's called **Eidetic OS** — a "personal operating system" that sits on top of Claude Cowork and turns it from a stateless chatbot into something that remembers everything and does real work while I'm away.

The problem I kept hitting: Claude is brilliant but forgets everything between sessions. Close the tab and last week's research, yesterday's planning, the reasoning behind a decision — all gone. Eidetic OS is the config layer that fixes that.

**What it actually does for me, day to day:**

- **Session capture** — every conversation I have in Cowork gets folded back into my markdown vault as a searchable note, twice a day. Summary, key actions taken, files touched. Nothing is lost between sessions.
- **RAG search over everything** — months later I can ask "what did we decide about X?" and get the real answer, retrieved by *meaning*, not keyword. Conversations, research, code reviews — all indexed into the same store.
- **Trading research** — a local-first multi-agent market-research module writes briefings straight into the vault (not financial advice, obviously).
- **Job tracker updates** — a scheduled skill scans email each morning for application updates and edits the tracker for me.
- **Email briefings** — I wake up to an indexed vault, a committed git history, and a briefing in my inbox, all done overnight.

**Tech stack:**

- Python 3.11+, CLI-first (`eidetic <command>`)
- **SQLite vector store** (`sqlite-vec` KNN, NumPy cosine fallback) — scales way past a single JSON file
- **Hybrid retrieval**: Okapi BM25 + vector ranking fused with Reciprocal Rank Fusion, then reranked by TF-IDF cosine. Semantic chunking on heading/paragraph boundaries, embedding cache keyed by `(model, text)`.
- **Pluggable local LLM backends** — auto-detects LM Studio, Ollama, llama.cpp, or any OpenAI-compatible endpoint. No API keys needed for the core.
- **Flask dashboard** with seven live panels (health, audit, tasks, skills, knowledge graph, vector stats, RAG search)
- **160+ skills catalogue**, installable with one command
- D3.js force-directed knowledge graph viewer
- Append-only JSONL audit trail (every autonomous action logged), 400+ tests, CI/CD

The whole thing is local-first by default — notes, embeddings, and the knowledge graph never leave my machine unless I explicitly wire up an external endpoint. No telemetry. The "database" is a folder of markdown, the "API" is small inspectable Python scripts, and history is plain git. All diffable, portable, yours.

**GitHub (MIT, demo GIF in the README):** https://github.com/paulholland511/eidetic-os

`pip install eidetic-os` (or `pipx` / `uv tool install`).

**What's next (v3.0):** an extension architecture splitting a lean core from the domain verticals, making the skill framework speak **MCP** (each skill an MCP server, usable from any MCP host), a security gate that runs AST static analysis + a sandboxed runtime on community skills before install, git-sync hardening, and a pluggable vector backend (LanceDB / ChromaDB alongside sqlite-vec).

Happy to go deep on any of it — the hybrid search, the session-capture pipeline, the local-LLM auto-detection, whatever. AMA.
