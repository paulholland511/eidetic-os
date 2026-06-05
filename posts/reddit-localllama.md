# Reddit — r/LocalLLaMA

**Title:** Eidetic OS — personal AI OS with pluggable local LLM backends (LM Studio, Ollama, llama.cpp)

---

I built a personal "AI operating system" around my local models and open-sourced it. The whole thing is designed so your own local inference stack is the default, not an afterthought — no API keys needed for the core features, nothing leaves the box unless you explicitly wire up an external endpoint.

**The local-LLM angle:**

- **Backend auto-detection.** It probes for LM Studio, Ollama, llama.cpp, and any custom OpenAI-compatible endpoint (in that order) and just uses whatever's reachable. Force one with `EIDETIC_LLM_BACKEND=ollama`. Inspect with `eidetic backends` / `eidetic backends test`.
- **Two roles, two models.** Embeddings run against `nomic-embed-text`; chat/reasoning runs against whatever you've got loaded (qwen has been my daily driver). Both are just OpenAI-compatible calls to your local server, so swap in anything.
- **Everything local by default.** Embeddings, the vector store, and the knowledge graph all live on disk. No telemetry, ever. The only external calls are ones you turn on yourself (e.g. SMTP for email reports).
- **Dashboard shows backend health.** The Flask dashboard has a live panel for which backend is up and whether inference/embeddings are responding, alongside vector-store stats and RAG search.

**What it does with your local models:** it builds a RAG knowledge base over a folder of markdown — semantic chunking, embed via your endpoint into a SQLite vector store (sqlite-vec KNN, NumPy cosine fallback), then hybrid retrieval at query time (BM25 + vector fused with Reciprocal Rank Fusion, reranked by TF-IDF). It also captures every Claude conversation back into the vault and indexes it, so your local search gets richer over time. There's an embedding cache keyed by `(model, text)` so a full re-embed skips anything unchanged — handy when you're iterating on chunking against a slow local model.

Degrades gracefully: with no LLM running at all, the vault management, git automation, and keyword (BM25-only) search still work — only semantic search and the trading module need an endpoint.

```bash
pip install eidetic-os
eidetic backends            # see what's reachable
eidetic embed --full        # build the vector store
eidetic search "kelly criterion" --mode vector
```

**GitHub (MIT):** https://github.com/paulholland511/atlas-os

v3.0 is adding a pluggable `VectorBackend` interface — sqlite-vec stays the zero-config default, with LanceDB (zero-copy disk queries) and ChromaDB as options, plus documented benchmarks at 1K/10K/100K chunks. Interested in what backends/embedding models people here are running for vault-scale RAG.
