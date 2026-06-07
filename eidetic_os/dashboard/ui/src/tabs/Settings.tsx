import { useState } from "react";
import {
  Server,
  Database,
  FolderTree,
  Puzzle,
  Cpu,
  Sliders,
  Wifi,
  Loader2,
  CheckCircle2,
} from "lucide-react";
import { useApi, type Settings as SettingsT } from "@/lib/api";
import { Panel, PanelHeader, Pill, Spinner, Dot, fmt } from "@/components/kit";

type BackendProbe = {
  backends: { name: string; label: string; base_url: string; reachable: boolean; models: string[]; error: string | null }[];
  detected: string | null;
  forced: string | null;
};

export default function Settings() {
  const { data, loading } = useApi<SettingsT>("/api/settings");
  const [llm, setLlm] = useState<string | null>(null);
  const [vec, setVec] = useState<string | null>(null);
  const [probe, setProbe] = useState<BackendProbe | null>(null);
  const [probing, setProbing] = useState(false);

  if (loading || !data) return <Spinner />;

  const selectedLlm = llm ?? data.llm_forced ?? "lmstudio";
  const selectedVec = vec ?? data.vector_active;

  async function testBackends() {
    setProbing(true);
    try {
      const res = await fetch("/api/backends?timeout=1.5");
      if (!res.ok) throw new Error();
      setProbe(await res.json());
    } catch {
      // demo fallback
      setProbe({
        detected: "lmstudio",
        forced: null,
        backends: [
          { name: "lmstudio", label: "LM Studio", base_url: "http://localhost:5555", reachable: true, models: ["qwen2.5-coder-32b", "nomic-embed-text-v1.5"], error: null },
          { name: "ollama", label: "Ollama", base_url: "http://localhost:11434", reachable: false, models: [], error: "ConnectionError" },
          { name: "llamacpp", label: "llama.cpp", base_url: "http://localhost:8080", reachable: false, models: [], error: "ConnectionError" },
        ],
      });
    } finally {
      setProbing(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* LLM backend */}
        <Panel>
          <PanelHeader
            title="LLM backend"
            subtitle="OpenAI-compatible inference server"
            icon={Server}
            action={
              <button
                onClick={testBackends}
                className="inline-flex items-center gap-1.5 rounded-md border border-border/70 bg-secondary/30 px-2.5 py-1 text-[11px] font-medium hover:border-emerald-500/40 hover:text-emerald-300"
              >
                {probing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Wifi className="h-3 w-3" />}
                Test connection
              </button>
            }
          />
          <div className="space-y-2 p-5">
            {data.llm_backends.map((b) => {
              const p = probe?.backends.find((x) => x.name === b.name);
              const active = selectedLlm === b.name;
              return (
                <button
                  key={b.name}
                  onClick={() => setLlm(b.name)}
                  className={
                    "flex w-full items-center gap-3 rounded-lg border px-4 py-3 text-left transition-colors " +
                    (active
                      ? "border-emerald-500/40 bg-emerald-500/5"
                      : "border-border/60 bg-secondary/20 hover:border-border")
                  }
                >
                  <Cpu className={"h-4 w-4 " + (active ? "text-emerald-400" : "text-muted-foreground")} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">{b.label}</span>
                      {probe?.detected === b.name && <Pill tone="emerald">detected</Pill>}
                      {data.llm_forced === b.name && <Pill tone="sky">forced</Pill>}
                    </div>
                    <div className="mono text-[11px] text-muted-foreground">{b.default}</div>
                  </div>
                  {p && <Dot state={p.reachable ? "ok" : "fail"} />}
                  <span
                    className={
                      "flex h-4 w-4 items-center justify-center rounded-full border " +
                      (active ? "border-emerald-400 bg-emerald-400" : "border-border")
                    }
                  >
                    {active && <span className="h-1.5 w-1.5 rounded-full bg-emerald-950" />}
                  </span>
                </button>
              );
            })}
            {probe && (
              <div className="mt-2 rounded-lg border border-border/60 bg-secondary/10 p-3 text-[11px]">
                {probe.backends
                  .filter((b) => b.reachable && b.models.length)
                  .map((b) => (
                    <div key={b.name} className="flex items-start gap-2 py-0.5">
                      <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-emerald-400" />
                      <span className="text-muted-foreground">
                        <span className="text-foreground/80">{b.label}</span>:{" "}
                        {b.models.slice(0, 3).join(", ")}
                      </span>
                    </div>
                  ))}
              </div>
            )}
          </div>
        </Panel>

        {/* Vector backend */}
        <Panel>
          <PanelHeader title="Vector backend" subtitle="Pluggable vector storage" icon={Database} />
          <div className="space-y-2 p-5">
            {data.vector_backends.map((b) => {
              const active = selectedVec === b.name;
              return (
                <button
                  key={b.name}
                  onClick={() => setVec(b.name)}
                  className={
                    "flex w-full items-center gap-3 rounded-lg border px-4 py-3 text-left transition-colors " +
                    (active
                      ? "border-emerald-500/40 bg-emerald-500/5"
                      : "border-border/60 bg-secondary/20 hover:border-border")
                  }
                >
                  <Database className={"h-4 w-4 " + (active ? "text-emerald-400" : "text-muted-foreground")} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">{b.label}</span>
                      {b.builtin ? <Pill tone="emerald">built-in</Pill> : <Pill>extra</Pill>}
                      {b.name === data.vector_active && <Pill tone="sky">active</Pill>}
                    </div>
                  </div>
                  <span
                    className={
                      "flex h-4 w-4 items-center justify-center rounded-full border " +
                      (active ? "border-emerald-400 bg-emerald-400" : "border-border")
                    }
                  >
                    {active && <span className="h-1.5 w-1.5 rounded-full bg-emerald-950" />}
                  </span>
                </button>
              );
            })}
            <p className="pt-1 text-[11px] text-muted-foreground">
              Switch with{" "}
              <code className="mono text-foreground/70">eidetic migrate-vectors --to {selectedVec}</code>
            </p>
          </div>
        </Panel>
      </div>

      {/* Paths */}
      <Panel>
        <PanelHeader title="Paths & configuration" subtitle="Resolved from the environment" icon={FolderTree} />
        <div className="grid grid-cols-1 gap-px bg-border/40 md:grid-cols-2">
          <PathRow label="Vault path" value={data.vault_path ?? "VAULT_PATH not set"} env="VAULT_PATH" />
          <PathRow label="RAG directory" value={data.rag_dir ?? "$VAULT_PATH/.rag"} env="RAG_DIR" />
          <PathRow label="Config file" value={data.config_path || "~/.eidetic/config.yaml"} env="—" />
          <PathRow label="Active vector store" value={data.vector_active} env="VECTOR_BACKEND" />
        </div>
      </Panel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Memory params */}
        <Panel>
          <PanelHeader title="Memory parameters" subtitle="Decay & reinforcement tuning" icon={Sliders} />
          <div className="space-y-4 p-5">
            {Object.entries(data.memory_params).length === 0 ? (
              <p className="text-xs text-muted-foreground">Using built-in defaults.</p>
            ) : (
              Object.entries(data.memory_params).map(([k, v]) => (
                <div key={k}>
                  <div className="mb-1.5 flex items-center justify-between text-xs">
                    <span className="mono text-muted-foreground">{k}</span>
                    <span className="tnum font-medium">{v}</span>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary/60">
                    <div
                      className="h-full rounded-full bg-emerald-500/70"
                      style={{ width: `${Math.min(100, v * 100)}%` }}
                    />
                  </div>
                </div>
              ))
            )}
          </div>
        </Panel>

        {/* Extensions */}
        <Panel>
          <PanelHeader title="Extension manager" subtitle="Loaded domain extensions" icon={Puzzle} />
          <div className="p-5">
            {data.extensions.length === 0 ? (
              <p className="text-xs text-muted-foreground">No extensions discovered.</p>
            ) : (
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {data.extensions.map((e) => (
                  <div
                    key={e.name}
                    className="flex items-center gap-2.5 rounded-lg border border-border/60 bg-secondary/20 px-3 py-2.5"
                  >
                    <Dot state={e.loaded ? "ok" : "idle"} />
                    <span className="flex-1 text-sm font-medium capitalize">{e.name}</span>
                    <Pill tone={e.loaded ? "emerald" : "neutral"}>{e.loaded ? "loaded" : "off"}</Pill>
                  </div>
                ))}
              </div>
            )}
            <p className="mt-3 text-[11px] text-muted-foreground">
              {fmt(data.extensions.filter((e) => e.loaded).length)} of {fmt(data.extensions.length)} extensions active
            </p>
          </div>
        </Panel>
      </div>
    </div>
  );
}

function PathRow({ label, value, env }: { label: string; value: string; env: string }) {
  return (
    <div className="bg-card/60 p-4">
      <div className="flex items-center justify-between">
        <span className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</span>
        {env !== "—" && <code className="mono text-[10px] text-muted-foreground/60">{env}</code>}
      </div>
      <code className="mono mt-1.5 block truncate text-xs text-foreground/80" title={value}>
        {value}
      </code>
    </div>
  );
}
