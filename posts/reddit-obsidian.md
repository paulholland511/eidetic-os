# Reddit — r/ObsidianMD

**Title:** I built a RAG pipeline that turns my Obsidian vault into a searchable AI knowledge base — open source

---

Like a lot of people here, my vault had become a graveyard — hundreds of notes I'd never find again unless I remembered the exact title. I wanted to be able to ask it questions and have it actually *understand* what I'd written, not just match keywords. So I built the tooling for that and open-sourced it. It's called Eidetic OS.

It works with **any** vault structure — top-level folders just carry meaning if you want them to. No plugin to install in Obsidian; it's a Python CLI that reads and writes plain markdown, so your vault stays portable.

**The bits Obsidian people will care about:**

**Semantic search over your notes.** It chunks every note on heading/paragraph boundaries (whole paragraphs up to a token budget, not blind character windows), embeds them via a *local* LLM into a SQLite vector store, and answers queries with hybrid retrieval — Okapi BM25 fused with vector ranking via Reciprocal Rank Fusion, then reranked by TF-IDF cosine. You can filter by folder, tag, note type, or date *before* the search runs:

```
eidetic search "kelly criterion sizing"
eidetic search "trading risk" --folder research --tag trading --top-k 10
eidetic search "kelly" --mode keyword          # BM25 only, no LLM needed
```

**Twice-daily auto-index.** A scheduled task re-embeds only the notes that changed since the last run, keeps your frontmatter schemas consistent, and auto-commits the vault with messages categorised by which folders changed. You wake up to a tidy, indexed vault.

**Session capture → wiki notes.** This is the part I use most. Every conversation I have with Claude gets written back into the vault as a searchable session-log note, and then indexed alongside everything else. So my AI conversations become part of my knowledge base instead of vanishing.

**Knowledge graph viewer.** It walks the vault, resolves your `[[wikilinks]]` into nodes/edges/backlinks, and renders a D3.js force-directed graph in the browser — zoom, pan, search, filter by note type, click through links and backlinks. Like Obsidian's graph but driven off the RAG layer, so "related notes" actually means semantically related.

Everything is **local-first** — the embeddings and graph live in a git-ignored `.rag/` folder and never leave your machine. The vault is the source of truth; everything derived is reproducible. No telemetry, no cloud, MIT licensed.

**GitHub:** https://github.com/paulholland511/atlas-os

You need a local embeddings model (LM Studio or Ollama with `nomic-embed-text` works out of the box). Without one, all the vault management still works — only the semantic search needs the endpoint.

Curious whether anyone else here has tried to build proper RAG over their vault, and what you landed on for chunking.
