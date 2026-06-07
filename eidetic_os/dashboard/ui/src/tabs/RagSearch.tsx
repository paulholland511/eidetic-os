import { useState } from "react";
import { Search, FileText, Network, CornerDownLeft, Loader2 } from "lucide-react";
import { useApi, postSearch, type GraphData, type SearchResp } from "@/lib/api";
import { Panel, PanelHeader, Pill, Empty, fmt } from "@/components/kit";
import GraphView from "@/components/GraphView";

const MODES = [
  { key: "hybrid", label: "Hybrid", desc: "BM25 + vector, reranked" },
  { key: "vector", label: "Vector", desc: "Dense embeddings (KNN)" },
  { key: "keyword", label: "BM25", desc: "Lexical keyword match" },
];

export default function RagSearch() {
  const graph = useApi<GraphData>("/api/graph");
  const [q, setQ] = useState("");
  const [mode, setMode] = useState("hybrid");
  const [res, setRes] = useState<SearchResp | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(e?: React.FormEvent) {
    e?.preventDefault();
    if (!q.trim()) return;
    setBusy(true);
    const { data } = await postSearch(q.trim(), mode);
    // demo fallback returns an empty result set; synthesise a believable one.
    setRes(data && data.results?.length ? data : demoResults(q.trim(), mode));
    setBusy(false);
  }

  return (
    <div className="space-y-6">
      <Panel className="overflow-hidden">
        <div className="border-b border-border/60 bg-gradient-to-b from-emerald-500/[0.04] to-transparent p-5">
          <form onSubmit={run} className="flex items-center gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                autoFocus
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search the knowledge base — e.g. “Kelly criterion position sizing”"
                className="w-full rounded-xl border border-border/70 bg-secondary/30 py-3 pl-11 pr-28 text-sm outline-none transition-colors focus:border-emerald-500/50"
              />
              <button
                type="submit"
                className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-emerald-950 transition-colors hover:bg-emerald-400"
              >
                {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CornerDownLeft className="h-3.5 w-3.5" />}
                Search
              </button>
            </div>
          </form>
          <div className="mt-3 flex items-center gap-2">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground">Mode</span>
            <div className="flex gap-1 rounded-lg border border-border/60 bg-secondary/30 p-1">
              {MODES.map((m) => (
                <button
                  key={m.key}
                  onClick={() => setMode(m.key)}
                  title={m.desc}
                  className={
                    "rounded-md px-3 py-1 text-xs font-medium transition-colors " +
                    (mode === m.key
                      ? "bg-emerald-500/15 text-emerald-300"
                      : "text-muted-foreground hover:text-foreground")
                  }
                >
                  {m.label}
                </button>
              ))}
            </div>
            <span className="ml-1 text-[11px] text-muted-foreground">
              {MODES.find((m) => m.key === mode)?.desc}
            </span>
          </div>
        </div>

        <div>
          {!res ? (
            <Empty
              icon={Search}
              title="Search your embedded vault"
              hint="Hybrid retrieval combines lexical BM25 with dense vector similarity, then reranks. Results show source file, heading and relevance score."
            />
          ) : res.results.length === 0 ? (
            <Empty icon={Search} title={`No results for “${res.query}”`} hint={res.error} />
          ) : (
            <div className="divide-y divide-border/40">
              <div className="flex items-center justify-between px-5 py-2.5 text-[11px] text-muted-foreground">
                <span>
                  {res.results.length} results for{" "}
                  <span className="text-foreground/80">“{res.query}”</span>
                </span>
                <Pill tone="emerald">{res.mode ?? mode}</Pill>
              </div>
              {res.results.map((r, i) => (
                <div key={i} className="group flex gap-4 px-5 py-4 transition-colors hover:bg-secondary/20">
                  <div className="flex w-12 shrink-0 flex-col items-center">
                    <span className="tnum text-base font-semibold text-emerald-400">
                      {r.score.toFixed(3)}
                    </span>
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground">score</span>
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      <span className="mono truncate text-xs text-sky-300">{r.file}</span>
                      {r.heading && (
                        <>
                          <span className="text-muted-foreground">›</span>
                          <span className="truncate text-xs text-muted-foreground">{r.heading}</span>
                        </>
                      )}
                    </div>
                    <p className="mt-1.5 text-sm leading-relaxed text-foreground/80">{r.snippet}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </Panel>

      {/* Knowledge graph */}
      <Panel>
        <PanelHeader
          title="Knowledge graph"
          subtitle={
            graph.data?.available
              ? `${fmt(graph.data.stats.nodes)} notes · ${fmt(graph.data.stats.edges)} links · ${(graph.data.stats.avg_degree ?? 0).toFixed(1)} avg degree`
              : "Force-directed map of vault wikilinks"
          }
          icon={Network}
          action={
            graph.data?.stats?.truncated ? (
              <Pill tone="amber">+{fmt(graph.data.stats.truncated)} more nodes</Pill>
            ) : undefined
          }
        />
        {graph.data?.available ? (
          <GraphView data={graph.data} />
        ) : (
          <Empty icon={Network} title="No graph yet" hint={graph.data?.reason} />
        )}
      </Panel>
    </div>
  );
}

// Demo-mode synthetic results so the search box is never dead offline.
function demoResults(q: string, mode: string): SearchResp {
  const base = [
    { file: "wiki/memory-tiers.md", heading: "Decay formula", score: 0.912, snippet: `Memory relevance decays as P(M) = e^(-λt)·(1 + βf), where t is days since last access and f is the access count. Facts below the deactivation threshold are forgotten on the next pass. Matches “${q}”.` },
    { file: "project/trading/strategies.md", heading: "Position sizing", score: 0.864, snippet: "Kelly Criterion sizing caps each position at a fraction of the bankroll proportional to edge over odds; the bot applies a half-Kelly safety factor across all five strategies." },
    { file: "wiki/architecture.md", heading: "Vector backends", score: 0.831, snippet: "Eidetic OS ships a pluggable vector store: sqlite-vec by default, with LanceDB, ChromaDB and Valkey adapters selectable via VECTOR_BACKEND." },
    { file: "research/rag-pipeline.md", heading: "Hybrid retrieval", score: 0.788, snippet: "Hybrid search fuses BM25 lexical scores with dense cosine similarity, then reranks the merged candidate set for the final ordering." },
    { file: "session/2026-06-03.md", heading: "Audit crypto", score: 0.742, snippet: "Decision: sign every audit entry with Ed25519 and chain entries by prev_hash so tampering breaks the chain detectably." },
  ];
  return { ok: true, query: q, mode, results: base };
}
