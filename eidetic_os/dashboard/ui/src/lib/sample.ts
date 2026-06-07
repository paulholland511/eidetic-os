// Representative demo data — used ONLY when no Flask backend is reachable
// (e.g. the bundle opened straight from disk). When served by `eidetic
// dashboard`, every value below is replaced by live data from the Python core.

export const SAMPLE: Record<string, unknown> = {
  "/api/overview": {
    version: "5.0.0",
    python: "3.13.1",
    platform: "Darwin",
    uptime: "4.2h",
    vault_path: "~/Documents/Obsidian/Atlas",
    health: { overall: "ok", ok: 18, warn: 2, fail: 0, total: 20 },
    vectors: {
      available: true,
      chunks: 21484,
      files: 463,
      backend: "sqlite-vec (KNN)",
      db_size: "182.4 MB",
      last_embed: { iso: "2026-06-07 04:00 UTC", age: "11m ago", stale: false },
    },
    graph: { nodes: 463, edges: 1928, orphans: 17, avg_degree: 8.3 },
    memory: {
      total: 1342,
      tiers: { core: 47, recall: 486, archival: 809 },
      categories: {
        technical: 412,
        decision: 318,
        project: 244,
        preference: 186,
        person: 112,
        other: 70,
      },
    },
    backend: { forced: null, model: "qwen2.5-coder-32b", configured: "auto-detect" },
    chain: { intact: true, signer_available: true, total: 2841, verified: 2841 },
    recent_audit: [
      { action: "embed", status: "success", trigger: "scheduled", context: "nightly-rag-incremental · 38 files", timestamp: "2026-06-07 04:00:12" },
      { action: "consolidate", status: "success", trigger: "scheduled", context: "sleeptime · 4 sessions → 9 facts", timestamp: "2026-06-07 03:30:04" },
      { action: "verify", status: "success", trigger: "cli", context: "verify eidetic_os/rag.py", timestamp: "2026-06-07 01:12:55" },
      { action: "search", status: "success", trigger: "cli", context: "hybrid · kelly criterion sizing", timestamp: "2026-06-06 23:48:19" },
      { action: "commit", status: "success", trigger: "cli", context: "vault · 6 notes", timestamp: "2026-06-06 22:05:41" },
      { action: "email", status: "success", trigger: "scheduled", context: "atlas-daily-report-email", timestamp: "2026-06-06 18:00:08" },
      { action: "health", status: "warn", trigger: "scheduled", context: "weekly-system-health-check", timestamp: "2026-06-06 09:00:31" },
      { action: "embed", status: "success", trigger: "scheduled", context: "nightly-obsidian-index", timestamp: "2026-06-06 04:00:10" },
    ],
  },

  "/api/memory": {
    available: true,
    total: 1342,
    shown: 8,
    tiers: {
      counts: { core: 47, recall: 486, archival: 809 },
      sizes: { core: 4126, recall: 41892, archival: 73104 },
      limits: { core: 50, recall: 500, archival: null },
      total: 1342,
    },
    categories: [
      { name: "technical", count: 412 },
      { name: "decision", count: 318 },
      { name: "project", count: 244 },
      { name: "preference", count: 186 },
      { name: "person", count: 112 },
      { name: "other", count: 70 },
    ],
    relevance_buckets: [
      { range: "0.0", count: 31 },
      { range: "0.1", count: 64 },
      { range: "0.2", count: 102 },
      { range: "0.3", count: 158 },
      { range: "0.4", count: 187 },
      { range: "0.5", count: 203 },
      { range: "0.6", count: 178 },
      { range: "0.7", count: 142 },
      { range: "0.8", count: 161 },
      { range: "0.9", count: 116 },
    ],
    facts: [
      { id: 1287, fact: "Paul prefers `uv` over pip and `ruff` for linting on all Python 3.13 work.", source: "session/2026-05-30", category: "preference", tier: "core", confidence: 0.98, relevance: 0.97, access_count: 41, created_at: "2026-05-30 09:14:02", last_accessed: "2026-06-07 03:30:01" },
      { id: 1190, fact: "Eidetic OS vector store defaults to sqlite-vec; Valkey backend added in v5.0.", source: "wiki/architecture", category: "technical", tier: "core", confidence: 0.96, relevance: 0.95, access_count: 33, created_at: "2026-05-22 11:02:55", last_accessed: "2026-06-06 23:48:19" },
      { id: 1342, fact: "Crypto trading bot runs 5 strategies with Kelly Criterion position sizing.", source: "project/trading", category: "project", tier: "core", confidence: 0.94, relevance: 0.93, access_count: 28, created_at: "2026-06-01 16:40:10", last_accessed: "2026-06-06 23:48:19" },
      { id: 1301, fact: "Decision: audit trail uses Ed25519 signatures with a prev_hash chain (v5.0).", source: "session/2026-06-03", category: "decision", tier: "core", confidence: 0.97, relevance: 0.91, access_count: 19, created_at: "2026-06-03 18:04:11", last_accessed: "2026-06-07 01:12:55" },
      { id: 1255, fact: "Memory relevance decays as P(M) = e^(-λt)·(1 + βf); λ=0.05 default.", source: "wiki/memory-tiers", category: "technical", tier: "recall", confidence: 0.92, relevance: 0.78, access_count: 12, created_at: "2026-05-28 14:22:30", last_accessed: "2026-06-05 10:00:00" },
      { id: 1098, fact: "Skill Capital sources sub-$50M EV B2B SaaS deals.", source: "project/skill-capital", category: "project", tier: "recall", confidence: 0.9, relevance: 0.64, access_count: 8, created_at: "2026-05-12 08:11:00", last_accessed: "2026-06-02 12:30:00" },
      { id: 942, fact: "LM Studio runs at 192.168.50.120:5555 with nomic-embed-text-v1.5 embeddings.", source: "memory/infra", category: "technical", tier: "recall", confidence: 0.88, relevance: 0.52, access_count: 6, created_at: "2026-04-30 19:05:44", last_accessed: "2026-05-29 09:15:00" },
      { id: 503, fact: "JailbreakAI.co.uk focuses on adversarial LLM red-teaming.", source: "project/jailbreakai", category: "project", tier: "archival", confidence: 0.85, relevance: 0.29, access_count: 3, created_at: "2026-03-18 13:00:00", last_accessed: "2026-05-01 11:00:00" },
    ],
    hot: [
      { id: 1287, fact: "Paul prefers `uv` over pip and `ruff` for linting on all Python 3.13 work.", source: "session/2026-05-30", category: "preference", tier: "core", confidence: 0.98, relevance: 0.97, access_count: 41, created_at: "2026-05-30 09:14:02", last_accessed: "2026-06-07 03:30:01" },
      { id: 1190, fact: "Eidetic OS vector store defaults to sqlite-vec; Valkey backend added in v5.0.", source: "wiki/architecture", category: "technical", tier: "core", confidence: 0.96, relevance: 0.95, access_count: 33, created_at: "2026-05-22 11:02:55", last_accessed: "2026-06-06 23:48:19" },
      { id: 1342, fact: "Crypto trading bot runs 5 strategies with Kelly Criterion position sizing.", source: "project/trading", category: "project", tier: "core", confidence: 0.94, relevance: 0.93, access_count: 28, created_at: "2026-06-01 16:40:10", last_accessed: "2026-06-06 23:48:19" },
    ],
    stale: [
      { id: 503, fact: "JailbreakAI.co.uk focuses on adversarial LLM red-teaming.", source: "project/jailbreakai", category: "project", tier: "archival", confidence: 0.85, relevance: 0.29, access_count: 3, created_at: "2026-03-18 13:00:00", last_accessed: "2026-05-01 11:00:00" },
      { id: 318, fact: "Old dashboard ran on Flask templates at port 8501.", source: "memory/infra", category: "technical", tier: "archival", confidence: 0.7, relevance: 0.18, access_count: 1, created_at: "2026-02-02 10:00:00", last_accessed: "2026-03-15 10:00:00" },
    ],
    consolidation: [
      { timestamp: "2026-06-07 03:30:04", status: "success", changes: ["4 session(s)", "9 fact(s)", "1 contradiction(s)", "wrote 2026-06-07.md"], context: "sleeptime consolidation" },
      { timestamp: "2026-06-06 03:30:02", status: "success", changes: ["3 session(s)", "6 fact(s)", "wrote 2026-06-06.md"], context: "sleeptime consolidation" },
      { timestamp: "2026-06-05 03:30:05", status: "success", changes: ["5 session(s)", "11 fact(s)", "2 contradiction(s)", "wrote 2026-06-05.md"], context: "sleeptime consolidation" },
    ],
  },

  "/api/security": {
    signer_available: true,
    chain: {
      signer_available: true,
      total_entries: 2841,
      verified: 2841,
      unsigned: 0,
      tampered: 0,
      first_tampered_line: null,
      chain_intact: true,
      public_key: "MCowBQYDK2VwAyEAGb9ECWmEzf6FQbrBZ9w7lshQhqowtrbLDFw4rXAxZuE",
    },
    tiers: [
      { key: "syntax", label: "Syntax", desc: "AST parse — every file compiles" },
      { key: "imports", label: "Imports", desc: "No missing local modules" },
      { key: "tests", label: "Tests", desc: "pytest suite passes" },
      { key: "runtime", label: "Runtime", desc: "Entrypoint imports clean in sandbox" },
      { key: "diff", label: "Diff", desc: "Changes stay within declared scope" },
    ],
    gate_runs: [
      { timestamp: "2026-06-07 01:12:55", status: "success", context: "verify eidetic_os/rag.py", tiers: ["syntax: pass", "imports: pass", "tests: pass", "runtime: pass", "diff: pass"], error: null, duration: 4.21 },
      { timestamp: "2026-06-06 19:40:11", status: "success", context: "verify eidetic_os/facts.py", tiers: ["syntax: pass", "imports: pass", "tests: pass", "runtime: pass", "diff: pass"], error: null, duration: 3.88 },
      { timestamp: "2026-06-06 14:22:03", status: "error", context: "verify eidetic_os/vectordb.py", tiers: ["syntax: pass", "imports: pass", "tests: fail"], error: "gate failure: tests", duration: 6.02 },
      { timestamp: "2026-06-05 22:10:47", status: "success", context: "verify eidetic_os/audit_crypto.py", tiers: ["syntax: pass", "imports: pass", "tests: pass", "runtime: pass", "diff: pass"], error: null, duration: 5.14 },
      { timestamp: "2026-06-05 11:33:20", status: "success", context: "verify eidetic_os/memory_tiers.py", tiers: ["syntax: pass", "imports: pass", "tests: pass", "runtime: pass", "diff: pass"], error: null, duration: 3.41 },
    ],
  },

  "/api/pipelines": {
    summary: { total: 11, installed: 9, ok: 7, failed: 1 },
    tasks: [
      { slug: "nightly-rag-incremental", name: "Nightly RAG incremental", cadence: "daily 04:00", installed: true, state: "success", last_run: { timestamp: "2026-06-07 04:00:12", status: "success", state: "ok", trigger: "scheduled" } },
      { slug: "nightly-obsidian-index", name: "Nightly Obsidian index", cadence: "daily 04:00", installed: true, state: "success", last_run: { timestamp: "2026-06-07 04:00:10", status: "success", state: "ok", trigger: "scheduled" } },
      { slug: "morning-session-capture", name: "Morning session capture", cadence: "daily 08:00", installed: true, state: "success", last_run: { timestamp: "2026-06-07 08:00:03", status: "success", state: "ok", trigger: "scheduled" } },
      { slug: "atlas-daily-report-email", name: "Atlas daily report email", cadence: "daily 18:00", installed: true, state: "success", last_run: { timestamp: "2026-06-06 18:00:08", status: "success", state: "ok", trigger: "scheduled" } },
      { slug: "daily-trading-report", name: "Daily trading report", cadence: "daily 17:00", installed: true, state: "success", last_run: { timestamp: "2026-06-06 17:00:14", status: "success", state: "ok", trigger: "scheduled" } },
      { slug: "weekly-rag-full-reembed", name: "Weekly RAG full re-embed", cadence: "weekly Sun 03:00", installed: true, state: "success", last_run: { timestamp: "2026-06-01 03:00:55", status: "success", state: "ok", trigger: "scheduled" } },
      { slug: "weekly-system-health-check", name: "Weekly system health check", cadence: "weekly Mon 09:00", installed: true, state: "warning", last_run: { timestamp: "2026-06-06 09:00:31", status: "skipped", state: "warn", trigger: "scheduled" } },
      { slug: "friday-it-newsletter", name: "Friday IT newsletter", cadence: "weekly Fri 16:00", installed: true, state: "failed", last_run: { timestamp: "2026-06-06 16:00:09", status: "error", state: "fail", trigger: "scheduled" } },
      { slug: "weekly-digest-report", name: "Weekly digest report", cadence: "weekly Sun 19:00", installed: true, state: "success", last_run: { timestamp: "2026-06-01 19:00:22", status: "success", state: "ok", trigger: "scheduled" } },
      { slug: "inbox-triage-digest", name: "Inbox triage digest", cadence: "daily 07:30", installed: false, state: "disabled", last_run: null },
      { slug: "topic-research-brief", name: "Topic research brief", cadence: "on demand", installed: false, state: "disabled", last_run: null },
    ],
  },

  "/api/settings": {
    llm_backends: [
      { name: "lmstudio", label: "LM Studio", default: "http://localhost:5555" },
      { name: "ollama", label: "Ollama", default: "http://localhost:11434" },
      { name: "llamacpp", label: "llama.cpp", default: "http://localhost:8080" },
      { name: "openai-compatible", label: "OpenAI-compatible", default: "—" },
    ],
    llm_forced: null,
    vector_backends: [
      { name: "sqlite", label: "SQLite (sqlite-vec)", builtin: true },
      { name: "lancedb", label: "LanceDB", builtin: false },
      { name: "chromadb", label: "ChromaDB", builtin: false },
      { name: "valkey", label: "Valkey", builtin: false },
    ],
    vector_active: "sqlite",
    vault_path: "~/Documents/Obsidian/Atlas",
    rag_dir: "~/Documents/Obsidian/Atlas/.rag",
    config_path: "~/.eidetic/config.yaml",
    memory_params: {
      decay_lambda: 0.05,
      reinforcement_beta: 0.3,
      deactivation_threshold: 0.05,
    },
    extensions: [
      { name: "trading", loaded: true },
      { name: "voice", loaded: true },
      { name: "jobs", loaded: true },
    ],
  },

  "/api/skills": {
    install_root: "~/Documents/Obsidian/Atlas/.claude/skills",
    skills: [
      { slug: "autoresearch", name: "Autoresearch", description: "Autonomous web research → wiki notes in the vault.", cadence: "on demand", installed: true },
      { slug: "nightly-rag-incremental", name: "Nightly RAG incremental", description: "Incrementally embed changed vault notes overnight.", cadence: "daily 04:00", installed: true },
      { slug: "weekly-rag-full-reembed", name: "Weekly RAG full re-embed", description: "Rebuild the entire vector index weekly.", cadence: "weekly Sun 03:00", installed: true },
      { slug: "atlas-daily-report-email", name: "Atlas daily report email", description: "Compile and email the daily Atlas briefing.", cadence: "daily 18:00", installed: true },
      { slug: "daily-trading-report", name: "Daily trading report", description: "Summarise overnight strategy performance.", cadence: "daily 17:00", installed: true },
      { slug: "weekly-system-health-check", name: "Weekly system health check", description: "Run eidetic doctor and report regressions.", cadence: "weekly Mon 09:00", installed: true },
      { slug: "inbox-triage-digest", name: "Inbox triage digest", description: "Triage and summarise the morning inbox.", cadence: "daily 07:30", installed: false },
      { slug: "topic-research-brief", name: "Topic research brief", description: "Deep-dive research brief on a given topic.", cadence: "on demand", installed: false },
      { slug: "save-to-vault", name: "Save to vault", description: "Capture conversation highlights as wiki notes.", cadence: "on demand", installed: true },
      { slug: "wiki-search", name: "Wiki search", description: "Semantic RAG search over the Obsidian vault.", cadence: "on demand", installed: true },
      { slug: "friday-it-newsletter", name: "Friday IT newsletter", description: "Weekly IT/security newsletter for the team.", cadence: "weekly Fri 16:00", installed: true },
      { slug: "spreadsheet-analysis", name: "Spreadsheet analysis", description: "Analyse and chart .xlsx/.csv workbooks.", cadence: "on demand", installed: false },
    ],
    packs: [
      { name: "knowledge", description: "Vault indexing, search and capture automation.", skills: ["nightly-rag-incremental", "weekly-rag-full-reembed", "save-to-vault", "wiki-search"] },
      { name: "reporting", description: "Daily and weekly briefings, digests and newsletters.", skills: ["atlas-daily-report-email", "weekly-digest-report", "friday-it-newsletter"] },
      { name: "research", description: "Autonomous research and topic briefs.", skills: ["autoresearch", "topic-research-brief"] },
    ],
  },

  "/api/search": {
    ok: true,
    query: "",
    results: [],
  },

  "/api/graph": {
    available: true,
    types: [
      { type: "wiki", label: "Wiki", color: "#22c55e" },
      { type: "research", label: "Research", color: "#34d399" },
      { type: "session", label: "Session log", color: "#60a5fa" },
      { type: "source", label: "Source", color: "#fbbf24" },
      { type: "skill", label: "Skill", color: "#a78bfa" },
      { type: "memory", label: "Memory", color: "#f472b6" },
      { type: "note", label: "Note", color: "#94a3b8" },
    ],
    stats: { nodes: 48, edges: 92, orphans: 3, avg_degree: 3.8, truncated: 415 },
    nodes: [],
    edges: [],
  },
};

// Build a small synthetic graph for the demo viewer so it isn't empty offline.
(function seedGraph() {
  const g = SAMPLE["/api/graph"] as {
    nodes: unknown[];
    edges: unknown[];
    types: { type: string }[];
  };
  const types = g.types.map((t) => t.type);
  const labels = [
    "architecture", "memory-tiers", "rag-pipeline", "audit-crypto", "verify-ground",
    "vector-backends", "valkey", "sleeptime", "kelly-criterion", "trading-bot",
    "skill-capital", "jailbreakai", "obsidian-vault", "embeddings", "lm-studio",
    "decay-formula", "fact-store", "consolidation", "dashboard", "mcp-server",
    "extensions", "marketplace", "git-sync", "doctor", "scheduled-tasks",
    "session-2026-06-07", "session-2026-06-06", "source-letta-ade", "source-open-webui",
    "research-rag", "research-memory", "skill-autoresearch", "skill-wiki-search",
    "preferences", "infra", "security-model", "hash-chain", "ed25519",
    "bm25", "hybrid-search", "reranker", "frontmatter", "filelock", "netio",
    "sandbox", "packs", "channels", "migration",
  ];
  const nodes = labels.map((label, i) => ({
    id: label,
    label,
    type: types[i % types.length],
    degree: 0,
    in: 0,
    out: 0,
  }));
  const edges: { source: string; target: string }[] = [];
  for (let i = 0; i < nodes.length; i++) {
    const links = 1 + (i % 3);
    for (let k = 1; k <= links; k++) {
      const j = (i + k * 3 + 1) % nodes.length;
      if (j === i) continue;
      edges.push({ source: nodes[i].id, target: nodes[j].id });
      nodes[i].degree++;
      nodes[j].degree++;
      nodes[i].out++;
      nodes[j].in++;
    }
  }
  g.nodes = nodes;
  g.edges = edges;
})();
