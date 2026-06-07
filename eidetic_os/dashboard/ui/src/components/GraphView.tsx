import { useEffect, useRef, useState } from "react";
import {
  forceSimulation,
  forceManyBody,
  forceLink,
  forceCenter,
  forceCollide,
  type Simulation,
} from "d3-force";
import type { GraphData } from "@/lib/api";

type SimNode = {
  id: string;
  label: string;
  type: string;
  degree: number;
  x?: number;
  y?: number;
  fx?: number | null;
  fy?: number | null;
};
type SimLink = { source: SimNode | string; target: SimNode | string };

export default function GraphView({ data }: { data: GraphData }) {
  const ref = useRef<SVGSVGElement | null>(null);
  const [size, setSize] = useState({ w: 800, h: 420 });
  const [hover, setHover] = useState<string | null>(null);
  const colorByType: Record<string, string> = Object.fromEntries(
    data.types.map((t) => [t.type, t.color]),
  );

  const [nodes, setNodes] = useState<SimNode[]>([]);
  const [links, setLinks] = useState<SimLink[]>([]);
  const simRef = useRef<Simulation<SimNode, undefined> | null>(null);

  // Responsive sizing.
  useEffect(() => {
    const el = ref.current?.parentElement;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0].contentRect;
      setSize({ w: Math.max(360, r.width), h: 440 });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Build & run the force simulation.
  useEffect(() => {
    const ns: SimNode[] = data.nodes.map((n) => ({ ...n }));
    const byId = new Map(ns.map((n) => [n.id, n]));
    const ls: SimLink[] = data.edges
      .filter((e) => byId.has(e.source) && byId.has(e.target))
      .map((e) => ({ source: byId.get(e.source)!, target: byId.get(e.target)! }));

    const sim = forceSimulation<SimNode>(ns)
      .force("charge", forceManyBody().strength(-160))
      .force("link", forceLink<SimNode, SimLink>(ls).id((d) => d.id).distance(64).strength(0.5))
      .force("center", forceCenter(size.w / 2, size.h / 2))
      .force("collide", forceCollide<SimNode>((d) => 6 + Math.sqrt(d.degree) * 2.2))
      .alpha(1)
      .alphaDecay(0.028);

    sim.on("tick", () => {
      setNodes([...ns]);
      setLinks([...ls]);
    });
    simRef.current = sim;
    return () => {
      sim.stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, size.w, size.h]);

  const radius = (d: SimNode) => 4 + Math.sqrt(d.degree) * 1.8;

  return (
    <div className="relative">
      <svg ref={ref} width="100%" height={size.h} viewBox={`0 0 ${size.w} ${size.h}`}>
        <g>
          {links.map((l, i) => {
            const s = l.source as SimNode;
            const t = l.target as SimNode;
            const lit = hover && (s.id === hover || t.id === hover);
            return (
              <line
                key={i}
                x1={s.x}
                y1={s.y}
                x2={t.x}
                y2={t.y}
                stroke={lit ? "#34d399" : "#ffffff"}
                strokeOpacity={lit ? 0.5 : 0.07}
                strokeWidth={lit ? 1.4 : 1}
              />
            );
          })}
        </g>
        <g>
          {nodes.map((n) => {
            const lit = hover === n.id;
            return (
              <g
                key={n.id}
                transform={`translate(${n.x ?? 0},${n.y ?? 0})`}
                onMouseEnter={() => setHover(n.id)}
                onMouseLeave={() => setHover(null)}
                style={{ cursor: "pointer" }}
              >
                <circle
                  r={radius(n) + (lit ? 2 : 0)}
                  fill={colorByType[n.type] ?? "#94a3b8"}
                  stroke={lit ? "#fff" : "#0a0c10"}
                  strokeWidth={lit ? 1.5 : 1}
                  fillOpacity={hover && !lit ? 0.4 : 1}
                />
                {(lit || n.degree > 6) && (
                  <text
                    x={radius(n) + 4}
                    y={3}
                    fontSize={10}
                    fill={lit ? "#e5e7eb" : "#7d8694"}
                    style={{ pointerEvents: "none" }}
                  >
                    {n.label}
                  </text>
                )}
              </g>
            );
          })}
        </g>
      </svg>

      {/* Legend */}
      <div className="pointer-events-none absolute left-3 top-3 flex flex-wrap gap-x-3 gap-y-1.5">
        {data.types.map((t) => (
          <span key={t.type} className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: t.color }} />
            {t.label}
          </span>
        ))}
      </div>
    </div>
  );
}
