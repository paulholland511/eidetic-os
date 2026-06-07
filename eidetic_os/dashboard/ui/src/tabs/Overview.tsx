import {
  Database,
  FileText,
  BrainCircuit,
  ShieldCheck,
  Activity,
  Network,
  Zap,
  Search as SearchIcon,
  Stethoscope,
  Layers,
  Clock,
  Server,
  ArrowUpRight,
} from "lucide-react";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  Tooltip,
} from "recharts";
import { useApi, type Overview as OverviewT } from "@/lib/api";
import type { TabKey } from "@/App";
import { Panel, PanelHeader, StatCard, Dot, Pill, Spinner, Empty, fmt } from "@/components/kit";

const TIER_COLORS: Record<string, string> = {
  core: "#34d399",
  recall: "#38bdf8",
  archival: "#64748b",
};
const CAT_COLOR = "#34d399";

export default function Overview({ onNavigate }: { onNavigate: (t: TabKey) => void }) {
  const { data, loading } = useApi<OverviewT>("/api/overview");
  if (loading || !data) return <Spinner />;

  const tierData = Object.entries(data.memory.tiers).map(([name, value]) => ({
    name,
    value,
  }));
  const catData = Object.entries(data.memory.categories)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);

  const healthIconClass =
    data.health.overall === "ok"
      ? "text-emerald-400"
      : data.health.overall === "fail"
        ? "text-rose-400"
        : "text-amber-400";

  return (
    <div className="space-y-6">
      {/* KPI row */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Vector chunks"
          value={fmt(data.vectors.chunks)}
          icon={Database}
          accent="emerald"
          hint={`${fmt(data.vectors.files)} files · ${data.vectors.db_size}`}
          spark={[12, 15, 14, 18, 22, 21, 26, 24, 28]}
        />
        <StatCard
          label="Active facts"
          value={fmt(data.memory.total)}
          icon={BrainCircuit}
          accent="sky"
          hint={`${data.memory.tiers.core ?? 0} core · ${data.memory.tiers.recall ?? 0} recall`}
          spark={[8, 9, 11, 10, 13, 15, 14, 17, 19]}
        />
        <StatCard
          label="Knowledge graph"
          value={fmt(data.graph.nodes)}
          unit="nodes"
          icon={Network}
          accent="violet"
          hint={`${fmt(data.graph.edges)} edges · ${(data.graph.avg_degree ?? 0).toFixed(1)} avg`}
        />
        <StatCard
          label="Audit chain"
          value={data.chain.intact ? "Intact" : "Broken"}
          icon={ShieldCheck}
          state={data.chain.intact ? "ok" : "fail"}
          hint={`${fmt(data.chain.verified)}/${fmt(data.chain.total)} signed`}
        />
      </div>

      {/* Status strip */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel className="p-5">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              System health
            </span>
            <Activity className={`h-4 w-4 ${healthIconClass}`} />
          </div>
          <div className="mt-3 flex items-end gap-2">
            <span className="text-2xl font-semibold capitalize">{data.health.overall}</span>
            <span className="mb-1 text-xs text-muted-foreground">
              {data.health.ok}/{data.health.total} checks pass
            </span>
          </div>
          <div className="mt-4 flex gap-1.5">
            {Array.from({ length: data.health.total || 20 }).map((_, i) => {
              const tone =
                i < data.health.ok
                  ? "bg-emerald-400"
                  : i < data.health.ok + data.health.warn
                    ? "bg-amber-400"
                    : "bg-rose-500";
              return <span key={i} className={`h-6 flex-1 rounded-sm ${tone} opacity-90`} />;
            })}
          </div>
          <div className="mt-3 flex items-center gap-4 text-[11px] text-muted-foreground">
            <span className="flex items-center gap-1.5"><Dot state="ok" /> {data.health.ok} ok</span>
            <span className="flex items-center gap-1.5"><Dot state="warn" /> {data.health.warn} warn</span>
            <span className="flex items-center gap-1.5"><Dot state="fail" /> {data.health.fail} fail</span>
          </div>
        </Panel>

        <Panel className="p-5">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              LLM backend
            </span>
            <Server className="h-4 w-4 text-emerald-400" />
          </div>
          <div className="mt-3 flex items-center gap-2">
            <Dot state="ok" pulse />
            <span className="text-lg font-semibold">{data.backend.model ?? "auto-detected"}</span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Selection: <span className="text-foreground/80">{data.backend.configured}</span>
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Pill tone="emerald">OpenAI-compatible</Pill>
            <Pill>local-first</Pill>
            <Pill tone="sky">embeddings ready</Pill>
          </div>
        </Panel>

        <Panel className="p-5">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              RAG pipeline
            </span>
            <Zap className="h-4 w-4 text-amber-400" />
          </div>
          <div className="mt-3 flex items-center gap-2">
            <Dot state={data.vectors.last_embed?.stale ? "warn" : "ok"} />
            <span className="text-lg font-semibold">
              {data.vectors.last_embed ? data.vectors.last_embed.age : "no index"}
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Last embed · {data.vectors.backend}
          </p>
          <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
            <div className="rounded-lg border border-border/60 bg-secondary/30 px-3 py-2">
              <div className="tnum text-base font-semibold">{fmt(data.vectors.chunks)}</div>
              <div className="text-[11px] text-muted-foreground">chunks indexed</div>
            </div>
            <div className="rounded-lg border border-border/60 bg-secondary/30 px-3 py-2">
              <div className="tnum text-base font-semibold">{data.vectors.db_size}</div>
              <div className="text-[11px] text-muted-foreground">store size</div>
            </div>
          </div>
        </Panel>
      </div>

      {/* Charts + activity */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel>
          <PanelHeader title="Memory tiers" subtitle="Active facts by tier" icon={Layers} />
          <div className="flex items-center gap-4 p-5">
            <div className="relative h-40 w-40 shrink-0">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={tierData}
                    dataKey="value"
                    innerRadius={48}
                    outerRadius={72}
                    paddingAngle={3}
                    stroke="none"
                    isAnimationActive={false}
                  >
                    {tierData.map((t) => (
                      <Cell key={t.name} fill={TIER_COLORS[t.name] ?? "#64748b"} />
                    ))}
                  </Pie>
                  <Tooltip content={<ChartTip />} />
                </PieChart>
              </ResponsiveContainer>
              <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                <span className="tnum text-xl font-semibold">{fmt(data.memory.total)}</span>
                <span className="text-[10px] uppercase tracking-wider text-muted-foreground">facts</span>
              </div>
            </div>
            <div className="flex-1 space-y-2.5">
              {tierData.map((t) => (
                <div key={t.name} className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2 capitalize">
                    <span
                      className="h-2.5 w-2.5 rounded-sm"
                      style={{ background: TIER_COLORS[t.name] ?? "#64748b" }}
                    />
                    {t.name}
                  </span>
                  <span className="tnum font-medium text-muted-foreground">{fmt(t.value)}</span>
                </div>
              ))}
            </div>
          </div>
        </Panel>

        <Panel className="lg:col-span-2">
          <PanelHeader title="Facts by category" subtitle="Distribution across the store" icon={FileText} />
          <div className="h-[208px] p-4 pr-5">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={catData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <XAxis
                  dataKey="name"
                  tick={{ fill: "#94a3b8", fontSize: 11 }}
                  tickLine={false}
                  axisLine={{ stroke: "#1f2937" }}
                />
                <Tooltip cursor={{ fill: "#ffffff08" }} content={<ChartTip />} />
                <Bar dataKey="value" radius={[4, 4, 0, 0]} fill={CAT_COLOR} maxBarSize={48} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      {/* Activity + quick actions */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel className="lg:col-span-2">
          <PanelHeader
            title="Recent activity"
            subtitle="Latest entries from the cryptographic audit trail"
            icon={Clock}
            action={
              <button
                onClick={() => onNavigate("security")}
                className="flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300"
              >
                Audit trail <ArrowUpRight className="h-3 w-3" />
              </button>
            }
          />
          <div className="divide-y divide-border/50">
            {data.recent_audit.length === 0 ? (
              <Empty icon={Clock} title="No activity yet" />
            ) : (
              data.recent_audit.map((e, i) => (
                <div key={i} className="flex items-center gap-3 px-5 py-2.5 text-sm">
                  <Dot state={e.status} />
                  <span className="w-20 shrink-0 font-medium capitalize">{e.action}</span>
                  <span className="flex-1 truncate text-muted-foreground">{e.context}</span>
                  <Pill tone={e.trigger === "scheduled" ? "sky" : "neutral"}>{e.trigger}</Pill>
                  <span className="mono w-32 shrink-0 text-right text-[11px] text-muted-foreground">
                    {e.timestamp}
                  </span>
                </div>
              ))
            )}
          </div>
        </Panel>

        <Panel>
          <PanelHeader title="Quick actions" subtitle="Common operations" icon={Zap} />
          <div className="grid grid-cols-2 gap-3 p-5">
            {[
              { label: "Embed vault", icon: Database, cmd: "eidetic embed --full", go: () => onNavigate("search") },
              { label: "RAG search", icon: SearchIcon, cmd: "eidetic search", go: () => onNavigate("search") },
              { label: "Doctor", icon: Stethoscope, cmd: "eidetic doctor", go: () => onNavigate("settings") },
              { label: "Consolidate", icon: BrainCircuit, cmd: "eidetic memory compact", go: () => onNavigate("memory") },
            ].map((a) => {
              const Icon = a.icon;
              return (
                <button
                  key={a.label}
                  onClick={a.go}
                  className="group flex flex-col items-start gap-2 rounded-lg border border-border/60 bg-secondary/20 p-3 text-left transition-colors hover:border-emerald-500/40 hover:bg-emerald-500/5"
                >
                  <Icon className="h-4 w-4 text-emerald-400" />
                  <span className="text-sm font-medium">{a.label}</span>
                  <code className="mono text-[10px] text-muted-foreground">{a.cmd}</code>
                </button>
              );
            })}
          </div>
          <div className="px-5 pb-5">
            <div className="rounded-lg border border-border/60 bg-secondary/20 p-3">
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">Uptime</span>
                <span className="tnum font-medium">{data.uptime}</span>
              </div>
              <div className="mt-2 flex items-center justify-between text-xs">
                <span className="text-muted-foreground">Python</span>
                <span className="mono">{data.python}</span>
              </div>
              <div className="mt-2 flex items-center justify-between text-xs">
                <span className="text-muted-foreground">Vault</span>
                <span className="mono max-w-[140px] truncate" title={data.vault_path ?? ""}>
                  {data.vault_path ?? "not set"}
                </span>
              </div>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}

function ChartTip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-border bg-popover px-3 py-2 text-xs shadow-xl">
      <div className="font-medium capitalize">{payload[0].payload.name ?? label}</div>
      <div className="tnum text-muted-foreground">{payload[0].value.toLocaleString()} facts</div>
    </div>
  );
}
