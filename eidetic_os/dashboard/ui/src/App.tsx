import { useState } from "react";
import {
  LayoutDashboard,
  BrainCircuit,
  Search,
  Boxes,
  ShieldCheck,
  GitBranch,
  Settings as SettingsIcon,
  Mountain,
  Circle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useDemo } from "@/lib/api";
import Overview from "@/tabs/Overview";
import Memory from "@/tabs/Memory";
import RagSearch from "@/tabs/RagSearch";
import Skills from "@/tabs/Skills";
import Security from "@/tabs/Security";
import Pipelines from "@/tabs/Pipelines";
import Settings from "@/tabs/Settings";

export type TabKey =
  | "overview"
  | "memory"
  | "search"
  | "skills"
  | "security"
  | "pipelines"
  | "settings";

const NAV: {
  group: string;
  items: { key: TabKey; label: string; icon: typeof Circle; desc: string }[];
}[] = [
  {
    group: "Operate",
    items: [
      { key: "overview", label: "Overview", icon: LayoutDashboard, desc: "System health at a glance" },
      { key: "pipelines", label: "Pipelines", icon: GitBranch, desc: "Scheduled automations" },
    ],
  },
  {
    group: "Knowledge",
    items: [
      { key: "memory", label: "Memory", icon: BrainCircuit, desc: "The fact store & tiers" },
      { key: "search", label: "RAG Search", icon: Search, desc: "Query the knowledge base" },
    ],
  },
  {
    group: "Platform",
    items: [
      { key: "skills", label: "Skills", icon: Boxes, desc: "Marketplace & MCP" },
      { key: "security", label: "Security", icon: ShieldCheck, desc: "Verification & audit" },
      { key: "settings", label: "Settings", icon: SettingsIcon, desc: "Backends & config" },
    ],
  },
];

const TITLES: Record<TabKey, { title: string; sub: string }> = {
  overview: { title: "Overview", sub: "System health, memory and knowledge at a glance" },
  memory: { title: "Memory", sub: "Fact store, tiers, decay and consolidation" },
  search: { title: "RAG Search", sub: "Hybrid retrieval over the embedded vault" },
  skills: { title: "Skills", sub: "Installable agent skills and MCP servers" },
  security: { title: "Security", sub: "GROUND verification gates and cryptographic audit" },
  pipelines: { title: "Pipelines", sub: "Scheduled tasks, cadence and run history" },
  settings: { title: "Settings", sub: "LLM / vector backends, paths and parameters" },
};

export default function App() {
  const [tab, setTab] = useState<TabKey>("overview");
  const demo = useDemo();

  return (
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      {/* Sidebar */}
      <aside className="flex w-64 shrink-0 flex-col border-r border-border/70 bg-[#0a0c10]">
        <div className="flex h-16 items-center gap-2.5 border-b border-border/70 px-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-400/90 to-emerald-600 text-emerald-950 shadow-lg shadow-emerald-500/20">
            <Mountain className="h-5 w-5" strokeWidth={2.5} />
          </div>
          <div className="leading-tight">
            <div className="text-sm font-semibold tracking-tight">Eidetic OS</div>
            <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
              Control Centre
            </div>
          </div>
        </div>

        <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-5">
          {NAV.map((section) => (
            <div key={section.group}>
              <div className="px-2 pb-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/70">
                {section.group}
              </div>
              <div className="space-y-0.5">
                {section.items.map((item) => {
                  const active = tab === item.key;
                  const Icon = item.icon;
                  return (
                    <button
                      key={item.key}
                      onClick={() => setTab(item.key)}
                      title={item.desc}
                      className={cn(
                        "group flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm transition-colors",
                        active
                          ? "bg-emerald-500/10 text-foreground"
                          : "text-muted-foreground hover:bg-secondary/40 hover:text-foreground",
                      )}
                    >
                      <Icon
                        className={cn(
                          "h-4 w-4 shrink-0",
                          active
                            ? "text-emerald-400"
                            : "text-muted-foreground group-hover:text-foreground",
                        )}
                      />
                      <span className="font-medium">{item.label}</span>
                      {active && (
                        <span className="ml-auto h-1.5 w-1.5 rounded-full bg-emerald-400" />
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        <div className="border-t border-border/70 p-4">
          <div className="flex items-center gap-2 rounded-lg border border-border/60 bg-card/40 px-3 py-2">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
            </span>
            <span className="text-[11px] text-muted-foreground">
              {demo ? "Demo data" : "Live · local-first"}
            </span>
          </div>
        </div>
      </aside>

      {/* Main */}
      <main className="flex flex-1 flex-col overflow-hidden">
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-border/70 bg-[#0a0c10]/80 px-7 backdrop-blur">
          <div>
            <h1 className="text-lg font-semibold tracking-tight">{TITLES[tab].title}</h1>
            <p className="text-xs text-muted-foreground">{TITLES[tab].sub}</p>
          </div>
          <div className="flex items-center gap-3">
            {demo && (
              <span className="hidden items-center gap-1.5 rounded-md border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-[11px] font-medium text-amber-300 sm:inline-flex">
                <Circle className="h-2 w-2 fill-amber-400 text-amber-400" />
                Demo data — run <code className="mono">eidetic dashboard</code> for live
              </span>
            )}
            <span className="rounded-md border border-border/70 bg-card/40 px-2.5 py-1 text-[11px] text-muted-foreground mono">
              v5.0.0
            </span>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto bg-grid">
          <div className="mx-auto max-w-[1400px] px-7 py-7">
            {tab === "overview" && <Overview onNavigate={setTab} />}
            {tab === "memory" && <Memory />}
            {tab === "search" && <RagSearch />}
            {tab === "skills" && <Skills />}
            {tab === "security" && <Security />}
            {tab === "pipelines" && <Pipelines />}
            {tab === "settings" && <Settings />}
          </div>
        </div>
      </main>
    </div>
  );
}
