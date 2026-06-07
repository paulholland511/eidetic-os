// Data layer for the Eidetic OS control centre.
//
// Every tab fetches a small JSON endpoint served by the Flask backend
// (eidetic_os/dashboard/app.py). When the dashboard is opened as a standalone
// bundle (no backend reachable), the fetch falls back to representative SAMPLE
// data and the UI flags itself as running on demo data — so the artifact is
// always presentable, and always honest about which it is showing.

import { useEffect, useRef, useState } from "react";

export type FetchState<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
  demo: boolean;
  reload: () => void;
};

let LIVE_BACKEND: boolean | null = null;
const demoListeners = new Set<() => void>();

function setLive(value: boolean) {
  if (LIVE_BACKEND === value) return;
  LIVE_BACKEND = value;
  demoListeners.forEach((l) => l());
}

export function isDemo() {
  return LIVE_BACKEND === false;
}

// Reactive: components re-render the moment the first request resolves and we
// learn whether a live backend is present, so the Live/Demo badge is correct.
export function useDemo(): boolean {
  const [, force] = useState(0);
  useEffect(() => {
    const l = () => force((n) => n + 1);
    demoListeners.add(l);
    return () => {
      demoListeners.delete(l);
    };
  }, []);
  return LIVE_BACKEND === false;
}

async function getJSON<T>(path: string): Promise<{ data: T; demo: boolean }> {
  try {
    const res = await fetch(path, { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = (await res.json()) as T;
    setLive(true);
    return { data, demo: false };
  } catch {
    setLive(false);
    const data = SAMPLE[path.split("?")[0]] as T;
    return { data, demo: true };
  }
}

export function useApi<T>(path: string): FetchState<T> {
  const [state, setState] = useState<Omit<FetchState<T>, "reload">>({
    data: null,
    loading: true,
    error: null,
    demo: false,
  });
  const tick = useRef(0);
  const [, force] = useState(0);

  useEffect(() => {
    let alive = true;
    setState((s) => ({ ...s, loading: true }));
    getJSON<T>(path)
      .then(({ data, demo }) => {
        if (!alive) return;
        setState({ data, loading: false, error: null, demo });
      })
      .catch((e) => {
        if (!alive) return;
        setState({ data: null, loading: false, error: String(e), demo: false });
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, tick.current]);

  return {
    ...state,
    reload: () => {
      tick.current += 1;
      force((n) => n + 1);
    },
  };
}

export function postSearch(q: string, mode: string) {
  return getJSON<SearchResp>(
    `/api/search?q=${encodeURIComponent(q)}&mode=${mode}&top_k=8`,
  );
}

// ── Types ─────────────────────────────────────────────────────────────────────
export type Overview = {
  version: string;
  python: string;
  platform: string;
  uptime: string;
  vault_path: string | null;
  health: { overall: string; ok: number; warn: number; fail: number; total: number };
  vectors: {
    available: boolean;
    chunks: number;
    files: number;
    backend: string;
    db_size: string;
    last_embed: { iso: string; age: string; stale: boolean } | null;
  };
  graph: { nodes?: number; edges?: number; orphans?: number; avg_degree?: number };
  memory: { total: number; tiers: Record<string, number>; categories: Record<string, number> };
  backend: { forced: string | null; model: string | null; configured: string };
  chain: { intact: boolean; signer_available: boolean; total: number; verified: number };
  recent_audit: {
    action: string;
    status: string;
    trigger: string;
    context: string;
    timestamp: string;
  }[];
};

export type Fact = {
  id: number;
  fact: string;
  source: string;
  category: string;
  tier: string;
  confidence: number;
  relevance: number;
  access_count: number;
  created_at: string;
  last_accessed: string;
};

export type Memory = {
  available: boolean;
  reason?: string;
  total?: number;
  shown?: number;
  facts: Fact[];
  tiers: {
    counts: Record<string, number>;
    sizes: Record<string, number>;
    limits: Record<string, number | null>;
    total: number;
  };
  categories: { name: string; count: number }[];
  relevance_buckets: { range: string; count: number }[];
  hot: Fact[];
  stale: Fact[];
  consolidation?: { timestamp: string; status: string; changes: string[]; context: string }[];
};

export type SearchResp = {
  ok: boolean;
  query: string;
  mode?: string;
  error?: string;
  results: { file: string; heading: string; score: number; snippet: string }[];
};

export type GraphData = {
  available: boolean;
  reason?: string;
  nodes: { id: string; label: string; type: string; degree: number; in: number; out: number }[];
  edges: { source: string; target: string }[];
  types: { type: string; label: string; color: string }[];
  stats: { nodes: number; edges: number; orphans: number; avg_degree: number; truncated: number };
};

export type SkillsResp = {
  skills: { slug: string; name: string; description: string; cadence: string; installed: boolean }[];
  packs: { name: string; description: string; skills: string[] }[];
  install_root: string | null;
};

export type Security = {
  chain: {
    signer_available: boolean;
    total_entries: number;
    verified: number;
    unsigned: number;
    tampered: number;
    first_tampered_line: number | null;
    chain_intact: boolean;
    public_key: string | null;
  };
  gate_runs: {
    timestamp: string;
    status: string;
    context: string;
    tiers: string[];
    error: string | null;
    duration: number | null;
  }[];
  tiers: { key: string; label: string; desc: string }[];
  signer_available: boolean;
};

export type Pipelines = {
  tasks: {
    slug: string;
    name: string;
    cadence: string;
    installed: boolean;
    state: string;
    last_run: { timestamp: string; status: string; state: string; trigger: string } | null;
  }[];
  summary: { total: number; installed: number; ok: number; failed: number };
};

export type Settings = {
  llm_backends: { name: string; label: string; default: string }[];
  llm_forced: string | null;
  vector_backends: { name: string; label: string; builtin: boolean }[];
  vector_active: string;
  vault_path: string | null;
  rag_dir: string | null;
  config_path: string;
  memory_params: Record<string, number>;
  extensions: { name: string; loaded: boolean }[];
};

// ── Demo / fallback data (shown only when no backend is reachable) ─────────────
import { SAMPLE } from "./sample";
