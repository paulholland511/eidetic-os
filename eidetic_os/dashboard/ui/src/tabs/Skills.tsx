import { useMemo, useState } from "react";
import {
  Boxes,
  Package,
  Plug,
  CheckCircle2,
  Download,
  Play,
  Search,
  Brain,
  Database,
  Mail,
  ShieldAlert,
  LineChart,
  Sparkles,
} from "lucide-react";
import { useApi, type SkillsResp } from "@/lib/api";
import { Panel, PanelHeader, Pill, Spinner, Empty, Dot, fmt } from "@/components/kit";

type Cat = { key: string; label: string; icon: typeof Boxes; match: (s: string) => boolean };

const CATS: Cat[] = [
  { key: "knowledge", label: "Knowledge", icon: Database, match: (s) => /rag|index|embed|vault|search|wiki|save/.test(s) },
  { key: "research", label: "Research", icon: Brain, match: (s) => /research|brief|topic/.test(s) },
  { key: "reporting", label: "Reporting", icon: Mail, match: (s) => /report|email|newsletter|digest/.test(s) },
  { key: "trading", label: "Finance", icon: LineChart, match: (s) => /trad|financ|spreadsheet/.test(s) },
  { key: "security", label: "Security", icon: ShieldAlert, match: (s) => /security|health|audit|verify/.test(s) },
  { key: "other", label: "Other", icon: Sparkles, match: () => true },
];

const MCP_SERVERS = [
  { name: "magic", label: "21st.dev Magic", desc: "Premium UI components", reachable: true },
  { name: "eidetic", label: "Eidetic MCP", desc: "Memory, RAG & skills over MCP", reachable: true },
  { name: "obsidian", label: "Obsidian REST", desc: "Vault read/write API", reachable: true },
];

function categorise(skill: { slug: string; description: string }): string {
  const hay = `${skill.slug} ${skill.description}`.toLowerCase();
  for (const c of CATS) if (c.key !== "other" && c.match(hay)) return c.key;
  return "other";
}

export default function Skills() {
  const { data, loading } = useApi<SkillsResp>("/api/skills");
  const [active, setActive] = useState("all");

  const grouped = useMemo(() => {
    const g: Record<string, SkillsResp["skills"]> = {};
    (data?.skills ?? []).forEach((s) => {
      const c = categorise(s);
      (g[c] ??= []).push(s);
    });
    return g;
  }, [data]);

  if (loading || !data) return <Spinner />;

  const total = data.skills.length;
  const installed = data.skills.filter((s) => s.installed).length;
  const cats = CATS.filter((c) => (grouped[c.key] ?? []).length > 0);
  const shown = active === "all" ? data.skills : grouped[active] ?? [];

  return (
    <div className="space-y-6">
      {/* Header stats + MCP */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel className="p-5 lg:col-span-2">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold">Skill marketplace</h3>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {fmt(total)} skills · {fmt(installed)} installed · {fmt(data.packs.length)} packs
              </p>
            </div>
            <Package className="h-5 w-5 text-emerald-400" />
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <CatBtn label="All" count={total} active={active === "all"} onClick={() => setActive("all")} icon={Boxes} />
            {cats.map((c) => (
              <CatBtn
                key={c.key}
                label={c.label}
                count={(grouped[c.key] ?? []).length}
                active={active === c.key}
                onClick={() => setActive(c.key)}
                icon={c.icon}
              />
            ))}
          </div>
        </Panel>

        <Panel>
          <PanelHeader title="MCP servers" subtitle="Connected tool providers" icon={Plug} />
          <div className="divide-y divide-border/40">
            {MCP_SERVERS.map((m) => (
              <div key={m.name} className="flex items-center gap-3 px-5 py-3">
                <Dot state={m.reachable ? "ok" : "fail"} pulse={m.reachable} />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium">{m.label}</div>
                  <div className="truncate text-[11px] text-muted-foreground">{m.desc}</div>
                </div>
                <Pill tone={m.reachable ? "emerald" : "rose"}>{m.reachable ? "online" : "down"}</Pill>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      {/* Skill grid */}
      {shown.length === 0 ? (
        <Panel>
          <Empty icon={Search} title="No skills in this category" />
        </Panel>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {shown.map((s) => (
            <SkillCard key={s.slug} skill={s} />
          ))}
        </div>
      )}

      {/* Packs */}
      <Panel>
        <PanelHeader title="Curated packs" subtitle="Install a bundle of related skills" icon={Boxes} />
        <div className="grid grid-cols-1 gap-px bg-border/40 md:grid-cols-3">
          {data.packs.map((p) => (
            <div key={p.name} className="bg-card/60 p-5">
              <div className="flex items-center justify-between">
                <span className="font-medium capitalize">{p.name}</span>
                <Pill>{p.skills.length} skills</Pill>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">{p.description}</p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {p.skills.slice(0, 4).map((sk) => (
                  <span key={sk} className="mono rounded bg-secondary/40 px-1.5 py-0.5 text-[10px] text-muted-foreground">
                    {sk}
                  </span>
                ))}
              </div>
              <button className="mt-4 flex w-full items-center justify-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 py-2 text-xs font-semibold text-emerald-300 transition-colors hover:bg-emerald-500/20">
                <Download className="h-3.5 w-3.5" /> Install pack
              </button>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function CatBtn({
  label,
  count,
  active,
  onClick,
  icon: Icon,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
  icon: typeof Boxes;
}) {
  return (
    <button
      onClick={onClick}
      className={
        "inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors " +
        (active
          ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
          : "border-border/60 bg-secondary/20 text-muted-foreground hover:text-foreground")
      }
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
      <span className="tnum rounded bg-background/40 px-1.5 text-[10px]">{count}</span>
    </button>
  );
}

function SkillCard({ skill }: { skill: SkillsResp["skills"][number] }) {
  return (
    <Panel className="flex flex-col p-5 transition-colors hover:border-border">
      <div className="flex items-start justify-between gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-border/70 bg-secondary/40 text-emerald-400">
          <Boxes className="h-4 w-4" />
        </div>
        {skill.installed ? (
          <Pill tone="emerald">
            <CheckCircle2 className="h-3 w-3" /> installed
          </Pill>
        ) : (
          <Pill>available</Pill>
        )}
      </div>
      <h4 className="mt-3 text-sm font-semibold">{skill.name}</h4>
      <p className="mt-1 line-clamp-2 flex-1 text-xs leading-relaxed text-muted-foreground">
        {skill.description}
      </p>
      <div className="mt-3 flex items-center justify-between">
        <span className="mono text-[10px] text-muted-foreground">{skill.cadence}</span>
        <div className="flex gap-1.5">
          {skill.installed ? (
            <button className="flex items-center gap-1 rounded-md border border-border/70 bg-secondary/30 px-2.5 py-1 text-[11px] font-medium hover:border-emerald-500/40 hover:text-emerald-300">
              <Play className="h-3 w-3" /> Run
            </button>
          ) : (
            <button className="flex items-center gap-1 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-medium text-emerald-300 hover:bg-emerald-500/20">
              <Download className="h-3 w-3" /> Install
            </button>
          )}
        </div>
      </div>
    </Panel>
  );
}
