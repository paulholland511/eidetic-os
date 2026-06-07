import { useMemo, useState } from "react";
import {
  BrainCircuit,
  Search,
  Flame,
  Snowflake,
  Layers,
  TrendingDown,
  Moon,
  ChevronRight,
} from "lucide-react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { useApi, type Memory as MemoryT, type Fact } from "@/lib/api";
import { Panel, PanelHeader, Dot, Pill, Spinner, Empty, Meter, fmt } from "@/components/kit";

const TIER_META: Record<string, { color: string; label: string }> = {
  core: { color: "#34d399", label: "Core" },
  recall: { color: "#38bdf8", label: "Recall" },
  archival: { color: "#64748b", label: "Archival" },
};

const CAT_TONE: Record<string, "emerald" | "sky" | "amber" | "violet" | "rose" | "neutral"> = {
  technical: "sky",
  decision: "emerald",
  project: "violet",
  preference: "amber",
  person: "rose",
  other: "neutral",
};

export default function Memory() {
  const { data, loading } = useApi<MemoryT>("/api/memory");
  const [q, setQ] = useState("");
  const [cat, setCat] = useState<string>("");

  const facts = useMemo(() => {
    if (!data) return [];
    const ql = q.toLowerCase();
    return data.facts.filter(
      (f) =>
        (!cat || f.category === cat) &&
        (!ql || f.fact.toLowerCase().includes(ql) || f.source.toLowerCase().includes(ql)),
    );
  }, [data, q, cat]);

  if (loading || !data) return <Spinner />;
  if (!data.available)
    return (
      <Panel>
        <Empty icon={BrainCircuit} title="No memory captured yet" hint={data.reason} />
      </Panel>
    );

  const tiers = data.tiers;

  return (
    <div className="space-y-6">
      {/* Tier strip */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {Object.entries(TIER_META).map(([key, meta]) => {
          const count = tiers.counts[key] ?? 0;
          const limit = tiers.limits[key];
          const size = tiers.sizes[key] ?? 0;
          return (
            <Panel key={key} className="p-5">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-sm font-medium">
                  <span className="h-2.5 w-2.5 rounded-sm" style={{ background: meta.color }} />
                  {meta.label}
                </span>
                <span className="text-[11px] text-muted-foreground">
                  {limit ? `limit ${fmt(limit)}` : "unbounded"}
                </span>
              </div>
              <div className="mt-3 flex items-end gap-1.5">
                <span className="tnum text-2xl font-semibold">{fmt(count)}</span>
                <span className="mb-0.5 text-xs text-muted-foreground">facts</span>
              </div>
              <div className="mt-3">
                <Meter value={count} max={limit ?? count || 1} color={meta.color} />
              </div>
              <div className="mt-2 flex justify-between text-[11px] text-muted-foreground">
                <span>{(size / 1024).toFixed(1)} KB context</span>
                <span className="tnum">
                  {limit ? `${Math.round((count / limit) * 100)}% full` : "cold storage"}
                </span>
              </div>
            </Panel>
          );
        })}
      </div>

      {/* Decay + categories */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel className="lg:col-span-2">
          <PanelHeader
            title="Relevance distribution"
            subtitle="P(M) = e^(-λt)·(1 + βf) — facts grouped by decayed relevance"
            icon={TrendingDown}
          />
          <div className="h-[220px] p-4">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data.relevance_buckets} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
                <defs>
                  <linearGradient id="relGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#34d399" stopOpacity={0.55} />
                    <stop offset="100%" stopColor="#34d399" stopOpacity={0.04} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" vertical={false} />
                <XAxis dataKey="range" tick={{ fill: "#94a3b8", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "#1f2937" }} />
                <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} tickLine={false} axisLine={false} width={36} allowDecimals={false} />
                <Tooltip content={<RelTip />} cursor={{ stroke: "#34d399", strokeOpacity: 0.3 }} />
                <Area
                  type="monotone"
                  dataKey="count"
                  stroke="#34d399"
                  strokeWidth={2.5}
                  fill="url(#relGrad)"
                  isAnimationActive={false}
                  dot={{ r: 2.5, fill: "#34d399", strokeWidth: 0 }}
                  activeDot={{ r: 4 }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel>
          <PanelHeader title="Categories" subtitle="Active facts by type" icon={Layers} />
          <div className="space-y-3 p-5">
            {data.categories.map((c) => {
              const top = data.categories[0]?.count || 1;
              return (
                <div key={c.name}>
                  <div className="mb-1 flex items-center justify-between text-xs">
                    <span className="capitalize">{c.name}</span>
                    <span className="tnum text-muted-foreground">{fmt(c.count)}</span>
                  </div>
                  <Meter value={c.count} max={top} color="#34d399" />
                </div>
              );
            })}
          </div>
        </Panel>
      </div>

      {/* Fact browser */}
      <Panel>
        <PanelHeader
          title="Fact store"
          subtitle={`${fmt(data.total)} active facts · showing ${facts.length}`}
          icon={BrainCircuit}
          action={
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Filter facts…"
                  className="w-48 rounded-lg border border-border/70 bg-secondary/30 py-1.5 pl-8 pr-3 text-xs outline-none focus:border-emerald-500/50"
                />
              </div>
            </div>
          }
        />
        <div className="flex flex-wrap gap-1.5 border-b border-border/50 px-5 py-3">
          <CatChip active={cat === ""} onClick={() => setCat("")} label="all" />
          {data.categories.map((c) => (
            <CatChip key={c.name} active={cat === c.name} onClick={() => setCat(c.name)} label={c.name} count={c.count} />
          ))}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/50 text-left text-[11px] uppercase tracking-wider text-muted-foreground">
                <th className="px-5 py-2.5 font-medium">Fact</th>
                <th className="px-3 py-2.5 font-medium">Category</th>
                <th className="px-3 py-2.5 font-medium">Tier</th>
                <th className="px-3 py-2.5 text-right font-medium">Relevance</th>
                <th className="px-3 py-2.5 text-right font-medium">Conf.</th>
                <th className="px-5 py-2.5 text-right font-medium">Hits</th>
              </tr>
            </thead>
            <tbody>
              {facts.length === 0 ? (
                <tr>
                  <td colSpan={6}>
                    <Empty icon={Search} title="No matching facts" />
                  </td>
                </tr>
              ) : (
                facts.map((f) => (
                  <tr key={f.id} className="border-b border-border/30 transition-colors hover:bg-secondary/20">
                    <td className="max-w-md px-5 py-3">
                      <div className="truncate font-medium text-foreground/90" title={f.fact}>
                        {f.fact}
                      </div>
                      <div className="mono mt-0.5 text-[11px] text-muted-foreground">{f.source}</div>
                    </td>
                    <td className="px-3 py-3">
                      <Pill tone={CAT_TONE[f.category] ?? "neutral"}>{f.category}</Pill>
                    </td>
                    <td className="px-3 py-3">
                      <span className="flex items-center gap-1.5 text-xs capitalize">
                        <span
                          className="h-2 w-2 rounded-sm"
                          style={{ background: TIER_META[f.tier]?.color ?? "#64748b" }}
                        />
                        {f.tier}
                      </span>
                    </td>
                    <td className="px-3 py-3 text-right">
                      <RelevanceCell value={f.relevance} />
                    </td>
                    <td className="tnum px-3 py-3 text-right text-muted-foreground">
                      {(f.confidence * 100).toFixed(0)}%
                    </td>
                    <td className="tnum px-5 py-3 text-right text-muted-foreground">{f.access_count}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      {/* Hot / stale / consolidation */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel>
          <PanelHeader title="Hottest facts" subtitle="Most reinforced" icon={Flame} />
          <FactList facts={data.hot} accent="#fb923c" />
        </Panel>
        <Panel>
          <PanelHeader title="Decaying" subtitle="Approaching deactivation" icon={Snowflake} />
          <FactList facts={data.stale} accent="#64748b" />
        </Panel>
        <Panel>
          <PanelHeader title="Sleeptime consolidation" subtitle="Recent compaction passes" icon={Moon} />
          <div className="divide-y divide-border/40">
            {(data.consolidation ?? []).length === 0 ? (
              <Empty icon={Moon} title="No consolidation runs yet" />
            ) : (
              (data.consolidation ?? []).map((c, i) => (
                <div key={i} className="px-5 py-3">
                  <div className="flex items-center justify-between">
                    <span className="mono text-[11px] text-muted-foreground">{c.timestamp}</span>
                    <Dot state={c.status} />
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {c.changes.map((ch, j) => (
                      <Pill key={j}>{ch}</Pill>
                    ))}
                  </div>
                </div>
              ))
            )}
          </div>
        </Panel>
      </div>
    </div>
  );
}

function CatChip({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count?: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={
        "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium capitalize transition-colors " +
        (active
          ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
          : "border-border/60 bg-secondary/20 text-muted-foreground hover:text-foreground")
      }
    >
      {label}
      {count != null && <span className="tnum text-[10px] opacity-70">{count}</span>}
    </button>
  );
}

function RelevanceCell({ value }: { value: number }) {
  const pct = Math.min(100, value * 100);
  const color = value > 0.7 ? "#34d399" : value > 0.35 ? "#fbbf24" : "#64748b";
  return (
    <div className="flex items-center justify-end gap-2">
      <div className="h-1.5 w-14 overflow-hidden rounded-full bg-secondary/60">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="tnum w-9 text-right text-xs text-muted-foreground">{value.toFixed(2)}</span>
    </div>
  );
}

function FactList({ facts, accent }: { facts: Fact[]; accent: string }) {
  if (facts.length === 0) return <Empty icon={Flame} title="Nothing here yet" />;
  return (
    <div className="divide-y divide-border/40">
      {facts.map((f) => (
        <div key={f.id} className="flex items-start gap-3 px-5 py-3">
          <ChevronRight className="mt-0.5 h-3.5 w-3.5 shrink-0" style={{ color: accent }} />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm text-foreground/90" title={f.fact}>
              {f.fact}
            </p>
            <div className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground">
              <span className="mono">{f.source}</span>
              <span>·</span>
              <span className="tnum">{f.access_count} hits</span>
              <span>·</span>
              <span className="tnum">rel {f.relevance.toFixed(2)}</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function RelTip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-border bg-popover px-3 py-2 text-xs shadow-xl">
      <div className="font-medium">relevance ≈ {label}</div>
      <div className="tnum text-muted-foreground">{payload[0].value} facts</div>
    </div>
  );
}
