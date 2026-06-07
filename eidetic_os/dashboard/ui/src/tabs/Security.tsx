import {
  ShieldCheck,
  KeyRound,
  Link2,
  FileCheck2,
  CircleCheck,
  CircleX,
  CircleDot,
  Fingerprint,
  ScanLine,
} from "lucide-react";
import { useApi, type Security as SecurityT } from "@/lib/api";
import { Panel, PanelHeader, Pill, Spinner, Empty, Dot, fmt } from "@/components/kit";

const GATE_ICON: Record<string, typeof CircleCheck> = {
  syntax: ScanLine,
  imports: Link2,
  tests: FileCheck2,
  runtime: CircleDot,
  diff: ShieldCheck,
};

export default function Security() {
  const { data, loading } = useApi<SecurityT>("/api/security");
  if (loading || !data) return <Spinner />;

  const c = data.chain;
  const intact = c.chain_intact;
  const coverage = c.total_entries ? Math.round((c.verified / c.total_entries) * 100) : 0;

  // Aggregate per-tier pass rate from recent gate runs for the pipeline diagram.
  const tierStats = data.tiers.map((t) => {
    let pass = 0;
    let total = 0;
    for (const run of data.gate_runs) {
      const entry = run.tiers.find((x) => x.startsWith(t.key));
      if (entry) {
        total++;
        if (entry.includes("pass")) pass++;
      }
    }
    return { ...t, pass, total };
  });

  return (
    <div className="space-y-6">
      {/* Chain integrity banner */}
      <Panel
        className={
          "relative overflow-hidden p-6 " +
          (intact ? "glow-emerald" : "")
        }
      >
        <div className="flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-4">
            <div
              className={
                "flex h-14 w-14 items-center justify-center rounded-2xl border " +
                (intact
                  ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
                  : "border-rose-500/40 bg-rose-500/10 text-rose-400")
              }
            >
              <Fingerprint className="h-7 w-7" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-lg font-semibold">
                  Hash chain {intact ? "intact" : "broken"}
                </h3>
                <Dot state={intact ? "ok" : "fail"} pulse={intact} />
              </div>
              <p className="mt-0.5 text-sm text-muted-foreground">
                {data.signer_available
                  ? `Ed25519 signed · ${fmt(c.verified)} of ${fmt(c.total_entries)} entries verified, linked by prev_hash`
                  : "Audit signing not configured — entries are unsigned"}
              </p>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3 md:gap-5">
            <ChainStat label="Verified" value={fmt(c.verified)} tone="emerald" />
            <ChainStat label="Unsigned" value={fmt(c.unsigned)} tone={c.unsigned ? "amber" : "neutral"} />
            <ChainStat label="Tampered" value={fmt(c.tampered)} tone={c.tampered ? "rose" : "neutral"} />
          </div>
        </div>
        <div className="mt-5">
          <div className="mb-1.5 flex items-center justify-between text-[11px] text-muted-foreground">
            <span>Signature coverage</span>
            <span className="tnum">{coverage}%</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-secondary/60">
            <div
              className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-emerald-400"
              style={{ width: `${coverage}%` }}
            />
          </div>
        </div>
        {c.public_key && (
          <div className="mt-4 flex items-center gap-2 rounded-lg border border-border/60 bg-secondary/20 px-3 py-2">
            <KeyRound className="h-3.5 w-3.5 shrink-0 text-emerald-400" />
            <span className="text-[11px] text-muted-foreground">Public key</span>
            <code className="mono truncate text-[11px] text-foreground/70">{c.public_key}</code>
          </div>
        )}
      </Panel>

      {/* GROUND pipeline */}
      <Panel>
        <PanelHeader
          title="GROUND verification pipeline"
          subtitle="Five gates run in order; a blocking failure halts the rest"
          icon={ShieldCheck}
        />
        <div className="grid grid-cols-1 gap-px bg-border/40 sm:grid-cols-3 lg:grid-cols-5">
          {tierStats.map((t, i) => {
            const Icon = GATE_ICON[t.key] ?? CircleCheck;
            const rate = t.total ? Math.round((t.pass / t.total) * 100) : 100;
            const allPass = t.pass === t.total;
            return (
              <div key={t.key} className="relative bg-card/60 p-5">
                <div className="absolute right-4 top-4 mono text-xs text-muted-foreground/50">
                  {i + 1}
                </div>
                <div
                  className={
                    "flex h-9 w-9 items-center justify-center rounded-lg border " +
                    (allPass
                      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
                      : "border-amber-500/30 bg-amber-500/10 text-amber-400")
                  }
                >
                  <Icon className="h-4 w-4" />
                </div>
                <h4 className="mt-3 text-sm font-semibold">{t.label}</h4>
                <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{t.desc}</p>
                <div className="mt-3 flex items-center justify-between">
                  <span className="tnum text-[11px] text-muted-foreground">
                    {t.pass}/{t.total || 0} pass
                  </span>
                  <span
                    className={
                      "tnum text-xs font-semibold " +
                      (allPass ? "text-emerald-400" : "text-amber-400")
                    }
                  >
                    {rate}%
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </Panel>

      {/* Gate run history */}
      <Panel>
        <PanelHeader
          title="Verification history"
          subtitle="Recent GROUND pipeline runs from the audit trail"
          icon={FileCheck2}
        />
        {data.gate_runs.length === 0 ? (
          <Empty icon={FileCheck2} title="No verification runs recorded yet" />
        ) : (
          <div className="divide-y divide-border/40">
            {data.gate_runs.map((run, i) => (
              <div key={i} className="px-5 py-3.5">
                <div className="flex items-center gap-3">
                  <Dot state={run.status} />
                  <code className="mono flex-1 truncate text-xs text-foreground/80">{run.context}</code>
                  {run.duration != null && (
                    <span className="tnum text-[11px] text-muted-foreground">{run.duration.toFixed(2)}s</span>
                  )}
                  <span className="mono w-32 shrink-0 text-right text-[11px] text-muted-foreground">
                    {run.timestamp}
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5 pl-5">
                  {run.tiers.map((tier, j) => {
                    const pass = tier.includes("pass");
                    const name = tier.split(":")[0];
                    return (
                      <span
                        key={j}
                        className={
                          "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-medium " +
                          (pass
                            ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-300"
                            : "border-rose-500/25 bg-rose-500/10 text-rose-300")
                        }
                      >
                        {pass ? <CircleCheck className="h-2.5 w-2.5" /> : <CircleX className="h-2.5 w-2.5" />}
                        {name}
                      </span>
                    );
                  })}
                  {run.error && <Pill tone="rose">{run.error}</Pill>}
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

function ChainStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "emerald" | "amber" | "rose" | "neutral";
}) {
  const tones: Record<string, string> = {
    emerald: "text-emerald-400",
    amber: "text-amber-400",
    rose: "text-rose-400",
    neutral: "text-foreground",
  };
  return (
    <div className="text-center md:text-right">
      <div className={"tnum text-xl font-semibold " + tones[tone]}>{value}</div>
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</div>
    </div>
  );
}
