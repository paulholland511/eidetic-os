// Shared display primitives for the control centre. Hand-built to a consistent
// dark/emerald system so every tab feels like one product.

import * as React from "react";
import { cn } from "@/lib/utils";

// ── Status dot ────────────────────────────────────────────────────────────────
const DOT: Record<string, string> = {
  ok: "bg-emerald-400",
  success: "bg-emerald-400",
  warn: "bg-amber-400",
  warning: "bg-amber-400",
  skipped: "bg-amber-400",
  fail: "bg-rose-500",
  failed: "bg-rose-500",
  error: "bg-rose-500",
  idle: "bg-zinc-500",
  disabled: "bg-zinc-600",
};

export function Dot({ state, pulse }: { state: string; pulse?: boolean }) {
  return (
    <span className="relative inline-flex h-2.5 w-2.5">
      {pulse && (
        <span
          className={cn(
            "absolute inline-flex h-full w-full rounded-full opacity-60 animate-ping",
            DOT[state] ?? "bg-zinc-500",
          )}
        />
      )}
      <span
        className={cn(
          "relative inline-flex h-2.5 w-2.5 rounded-full",
          DOT[state] ?? "bg-zinc-500",
        )}
      />
    </span>
  );
}

// ── Panel / section card ──────────────────────────────────────────────────────
export function Panel({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border border-border/70 bg-card/60 ring-soft backdrop-blur-sm",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function PanelHeader({
  title,
  subtitle,
  icon: Icon,
  action,
}: {
  title: string;
  subtitle?: string;
  icon?: React.ComponentType<{ className?: string }>;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border/60 px-5 py-4">
      <div className="flex items-start gap-3">
        {Icon && (
          <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-lg border border-border/70 bg-secondary/40 text-emerald-400">
            <Icon className="h-4 w-4" />
          </div>
        )}
        <div>
          <h3 className="text-sm font-semibold tracking-tight text-foreground">
            {title}
          </h3>
          {subtitle && (
            <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>
          )}
        </div>
      </div>
      {action}
    </div>
  );
}

// ── KPI stat card with optional sparkline + delta ─────────────────────────────
export function StatCard({
  label,
  value,
  unit,
  delta,
  hint,
  icon: Icon,
  spark,
  accent = "emerald",
  state,
}: {
  label: string;
  value: React.ReactNode;
  unit?: string;
  delta?: { value: string; up?: boolean };
  hint?: string;
  icon?: React.ComponentType<{ className?: string }>;
  spark?: number[];
  accent?: "emerald" | "sky" | "amber" | "violet" | "rose";
  state?: string;
}) {
  const accents: Record<string, string> = {
    emerald: "text-emerald-400",
    sky: "text-sky-400",
    amber: "text-amber-400",
    violet: "text-violet-400",
    rose: "text-rose-400",
  };
  const stroke: Record<string, string> = {
    emerald: "#34d399",
    sky: "#38bdf8",
    amber: "#fbbf24",
    violet: "#a78bfa",
    rose: "#fb7185",
  };
  return (
    <Panel className="group relative overflow-hidden p-5 transition-colors hover:border-border">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          {label}
        </span>
        {state ? (
          <Dot state={state} pulse={state === "ok" || state === "success"} />
        ) : (
          Icon && <Icon className={cn("h-4 w-4", accents[accent])} />
        )}
      </div>
      <div className="mt-3 flex items-end gap-1.5">
        <span className="tnum text-2xl font-semibold leading-none tracking-tight text-foreground">
          {value}
        </span>
        {unit && (
          <span className="mb-0.5 text-xs font-medium text-muted-foreground">
            {unit}
          </span>
        )}
      </div>
      <div className="mt-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {delta && (
            <span
              className={cn(
                "tnum text-[11px] font-semibold",
                delta.up ? "text-emerald-400" : "text-rose-400",
              )}
            >
              {delta.up ? "▲" : "▼"} {delta.value}
            </span>
          )}
          {hint && <span className="text-[11px] text-muted-foreground">{hint}</span>}
        </div>
        {spark && spark.length > 1 && (
          <Sparkline data={spark} stroke={stroke[accent]} />
        )}
      </div>
    </Panel>
  );
}

// ── Inline SVG sparkline ──────────────────────────────────────────────────────
export function Sparkline({
  data,
  stroke = "#34d399",
  width = 84,
  height = 26,
}: {
  data: number[];
  stroke?: string;
  width?: number;
  height?: number;
}) {
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const step = width / (data.length - 1);
  const pts = data.map((d, i) => {
    const x = i * step;
    const y = height - ((d - min) / range) * (height - 4) - 2;
    return [x, y] as const;
  });
  const line = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const area = `${line} L${width},${height} L0,${height} Z`;
  const id = React.useId();
  return (
    <svg width={width} height={height} className="overflow-visible">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.25" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke={stroke} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r="2" fill={stroke} />
    </svg>
  );
}

// ── Badge / pill ──────────────────────────────────────────────────────────────
export function Pill({
  children,
  tone = "neutral",
  className,
}: {
  children: React.ReactNode;
  tone?: "neutral" | "emerald" | "amber" | "rose" | "sky" | "violet";
  className?: string;
}) {
  const tones: Record<string, string> = {
    neutral: "border-border/70 bg-secondary/50 text-muted-foreground",
    emerald: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
    amber: "border-amber-500/30 bg-amber-500/10 text-amber-300",
    rose: "border-rose-500/30 bg-rose-500/10 text-rose-300",
    sky: "border-sky-500/30 bg-sky-500/10 text-sky-300",
    violet: "border-violet-500/30 bg-violet-500/10 text-violet-300",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────
export function Empty({
  icon: Icon,
  title,
  hint,
}: {
  icon?: React.ComponentType<{ className?: string }>;
  title: string;
  hint?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      {Icon && (
        <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl border border-border/70 bg-secondary/30 text-muted-foreground">
          <Icon className="h-5 w-5" />
        </div>
      )}
      <p className="text-sm font-medium text-foreground/80">{title}</p>
      {hint && <p className="mt-1 max-w-sm text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

// ── Thin labelled progress meter ──────────────────────────────────────────────
export function Meter({
  value,
  max,
  color = "#34d399",
}: {
  value: number;
  max: number;
  color?: string;
}) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary/60">
      <div
        className="h-full rounded-full transition-all"
        style={{ width: `${pct}%`, background: color }}
      />
    </div>
  );
}

export function Spinner() {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-border border-t-emerald-400" />
    </div>
  );
}

export const fmt = (n: number | undefined) =>
  (n ?? 0).toLocaleString("en-US");
