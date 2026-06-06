# Hacker News — Show HN

**Title:** Show HN: Eidetic OS – Open-source personal AI operating system (Python, local LLMs)

**URL:** https://github.com/paulholland511/eidetic-os

---

Eidetic OS is a configuration layer that turns Claude Cowork into a persistent, local-first system over a folder of markdown. The core idea is knowledge persistence: stock Claude forgets everything between sessions, so Eidetic captures every conversation back into a vault as a searchable note (twice daily by default), indexes it, and lets you retrieve it by meaning months later. The "database" is plain markdown, the "API" is a set of small inspectable Python scripts, and history is plain git — all diffable, portable, and yours.

The retrieval side is a local RAG pipeline: notes are chunked on heading/paragraph boundaries, embedded via your own OpenAI-compatible LLM, and stored in a SQLite vector store (sqlite-vec KNN index, with a NumPy cosine fallback when the extension isn't installed). Queries use hybrid search — Okapi BM25 fused with vector ranking via Reciprocal Rank Fusion, then reranked by TF-IDF cosine — with metadata filtering by folder/tag/type/date before the vector search. There's also a wikilink knowledge graph with a D3 viewer, a Flask dashboard, scheduled autonomous tasks, and an append-only JSONL audit trail logging every action.

It's deliberately local-first and pluggable: it auto-detects LM Studio, Ollama, llama.cpp, or any OpenAI-compatible endpoint, ships with no credentials or PII (everything is a template you point at your own vault and LLM), and makes no external calls unless you explicitly wire one up. No telemetry. MIT licensed, 400+ tests, on PyPI (`pip install eidetic-os`). Next up is an extension architecture, MCP-native skills, and a sandboxed security gate for community code. Feedback welcome, especially on the retrieval design.
