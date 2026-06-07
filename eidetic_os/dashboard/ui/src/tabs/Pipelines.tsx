import {
  GitBranch,
  Play,
  Clock,
  CheckCircle2,
  XCircle,
  PauseCircle,
  CalendarClock,
} from "lucide-react";
import { useApi, type Pipelines as PipelinesT } from "@/lib/api";
import { Panel, PanelHeader, StatCard, Dot, Pill, Spinner, Empty } from "@/components/kit";

const STATE_META: Record<string, { label: string; tone: "emerald" | "amber" | "rose" | "neutral" }> = {
  success: { label: "healthy", tone: "emerald" },
  warning: { label: "warning", tone: "amber" },
  failed: { label: "failed", tone: "rose" },
  idle: { label: "idle", tone: "neutral" },
  disabled: { label: "disabled", tone: "neutral" },
};

export default function Pipelines() {
  const { data, loading } = useApi<PipelinesT>("/api/pipelines");
  if (loading || !data) return <Spinner />;

  const s = data.summary;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Pipelines" value={s.total} icon={GitBranch} accent="emerald" hint={`${s.installed} installed`} />
        <StatCard label="Healthy" value={s.ok} icon={CheckCircle2} accent="emerald" state="ok" />
        <StatCard label="Failing" value={s.failed} icon={XCircle} accent="rose" state={s.failed ? "fail" : "ok"} />
        <StatCard label="Disabled" value={s.total - s.installed} icon={PauseCircle} accent="amber" />
      </div>

      <Panel>
        <PanelHeader
          title="Scheduled automations"
          subtitle="Cron-driven skills with cadence, last run and status"
          icon={CalendarClock}
        />
        {data.tasks.length === 0 ? (
          <Empty icon={GitBranch} title="No scheduled tasks" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/50 text-left text-[11px] uppercase tracking-wider text-muted-foreground">
                  <th className="px-5 py-2.5 font-medium">Pipeline</th>
                  <th className="px-3 py-2.5 font-medium">Status</th>
                  <th className="px-3 py-2.5 font-medium">Schedule</th>
                  <th className="px-3 py-2.5 font-medium">Last run</th>
                  <th className="px-3 py-2.5 font-medium">Trigger</th>
                  <th className="px-5 py-2.5 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {data.tasks.map((t) => {
                  const meta = STATE_META[t.state] ?? STATE_META.idle;
                  return (
                    <tr key={t.slug} className="border-b border-border/30 transition-colors hover:bg-secondary/20">
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-2.5">
                          <Dot state={t.state} pulse={t.state === "success"} />
                          <div>
                            <div className="font-medium">{t.name}</div>
                            <div className="mono text-[11px] text-muted-foreground">{t.slug}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-3 py-3">
                        <Pill tone={meta.tone}>{meta.label}</Pill>
                      </td>
                      <td className="px-3 py-3">
                        <span className="mono flex items-center gap-1.5 text-xs text-muted-foreground">
                          <Clock className="h-3 w-3" />
                          {t.cadence}
                        </span>
                      </td>
                      <td className="px-3 py-3">
                        {t.last_run ? (
                          <span className="mono text-[11px] text-muted-foreground">{t.last_run.timestamp}</span>
                        ) : (
                          <span className="text-[11px] text-muted-foreground/60">never</span>
                        )}
                      </td>
                      <td className="px-3 py-3">
                        {t.last_run ? (
                          <Pill tone={t.last_run.trigger === "scheduled" ? "sky" : "neutral"}>
                            {t.last_run.trigger}
                          </Pill>
                        ) : (
                          <span className="text-muted-foreground/50">—</span>
                        )}
                      </td>
                      <td className="px-5 py-3 text-right">
                        <button
                          disabled={!t.installed}
                          className="inline-flex items-center gap-1 rounded-md border border-border/70 bg-secondary/30 px-2.5 py-1 text-[11px] font-medium transition-colors hover:border-emerald-500/40 hover:text-emerald-300 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          <Play className="h-3 w-3" /> Run now
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
