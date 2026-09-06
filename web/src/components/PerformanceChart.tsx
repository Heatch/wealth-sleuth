import { useMemo, useState } from "react";
import { Area, AreaChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { HistoryPoint, PortfolioHistory } from "../lib/types";

export interface ZoomRange {
  start: string;
  end: string;
}

interface Props {
  history: PortfolioHistory | undefined;
  zoom: ZoomRange | null;
  onZoom: (z: ZoomRange | null) => void;
}

function fmtMoney(v: number): string {
  return `$${v.toLocaleString("en-CA", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function fmtDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-CA", { month: "short", day: "numeric", year: "numeric" });
}

export function zoomedReturn(series: HistoryPoint[], zoom: ZoomRange | null): number | null {
  const pts = zoom
    ? series.filter((p) => p.date >= zoom.start && p.date <= zoom.end)
    : series;
  if (pts.length < 2) return null;
  const first = pts[0].value;
  const last = pts[pts.length - 1].value;
  if (!first) return null;
  return (last - first) / Math.abs(first);
}

export default function PerformanceChart({ history, zoom, onZoom }: Props) {
  const [refLeft, setRefLeft] = useState<string | null>(null);
  const [refRight, setRefRight] = useState<string | null>(null);

  const fullData = useMemo(() => history?.series ?? [], [history]);

  const data = useMemo(() => {
    let pts = fullData;
    if (zoom) {
      pts = pts.filter((p) => p.date >= zoom.start && p.date <= zoom.end);
    }
    if (pts.length <= 400) return pts;
    const step = Math.ceil(pts.length / 400);
    const sampled = pts.filter((_, i) => i % step === 0);
    const last = pts[pts.length - 1];
    if (sampled[sampled.length - 1] !== last) sampled.push(last);
    return sampled;
  }, [fullData, zoom]);

  if (!history || fullData.length === 0) {
    return <div className="py-12 text-sm" style={{ color: "var(--ink-soft)" }}>Loading chart…</div>;
  }

  function handleMouseDown(e: any) {
    if (e?.activeLabel) setRefLeft(String(e.activeLabel));
  }

  function handleMouseMove(e: any) {
    if (refLeft && e?.activeLabel) setRefRight(String(e.activeLabel));
  }

  function handleMouseUp() {
    if (refLeft && refRight && refLeft !== refRight) {
      const start = refLeft < refRight ? refLeft : refRight;
      const end = refLeft < refRight ? refRight : refLeft;
      onZoom({ start, end });
    }
    setRefLeft(null);
    setRefRight(null);
  }

  const zoomRet = zoomedReturn(fullData, zoom);

  return (
    <section className="mt-8">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-sm" style={{ color: "var(--ink-soft)" }}>
          {zoom ? (
            <>
              {fmtDate(zoom.start)} — {fmtDate(zoom.end)}:{" "}
              <span
                className="tnum"
                style={{ color: (zoomRet ?? 0) >= 0 ? "var(--moss)" : "var(--brick)" }}
              >
                {zoomRet !== null
                  ? `${zoomRet >= 0 ? "+" : ""}${(zoomRet * 100).toFixed(2)}%`
                  : "--"}
              </span>{" "}
              <span style={{ color: "var(--ink-soft)" }}>(drag selection)</span>
            </>
          ) : (
            "Drag over the chart to zoom into a period"
          )}
        </div>
        {zoom ? (
          <button
            onClick={() => onZoom(null)}
            className="rounded px-2.5 py-1 text-sm"
            style={{ color: "var(--gold)", fontWeight: 600 }}
          >
            Reset zoom
          </button>
        ) : null}
      </div>
      <div style={{ width: "100%", height: 320 }}>
        <ResponsiveContainer>
          <AreaChart
            data={data}
            margin={{ top: 8, right: 8, bottom: 0, left: 8 }}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            style={{ cursor: refLeft ? "crosshair" : "default" }}
          >
            <defs>
              <linearGradient id="pfFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--gold)" stopOpacity={0.12} />
                <stop offset="100%" stopColor="var(--gold)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="date"
              tickFormatter={(d: string) => {
                const [, m, day] = d.split("-");
                const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
                return `${months[Number(m) - 1]} ${Number(day)}`;
              }}
              tick={{ fontSize: 12, fill: "var(--ink-soft)" }}
              axisLine={false}
              tickLine={false}
              minTickGap={48}
            />
            <YAxis
              tickFormatter={(v: number) => `$${Math.round(v / 1000)}k`}
              tick={{ fontSize: 12, fill: "var(--ink-soft)" }}
              axisLine={false}
              tickLine={false}
              width={56}
              domain={["auto", "auto"]}
            />
            <Tooltip
              formatter={(value) => [fmtMoney(Number(value)), "Value"]}
              labelFormatter={(label) => fmtDate(String(label))}
              contentStyle={{
                background: "var(--bg)",
                border: "1px solid color-mix(in srgb, var(--ink) 12%, transparent)",
                borderRadius: 4,
                fontSize: 13,
              }}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke="var(--gold)"
              strokeWidth={2}
              fill="url(#pfFill)"
              dot={false}
              activeDot={{ r: 4, fill: "var(--gold)" }}
              isAnimationActive={false}
            />
            {refLeft && refRight ? (
              <ReferenceArea
                x1={refLeft}
                x2={refRight}
                strokeOpacity={0.3}
                fill="var(--gold)"
                fillOpacity={0.15}
              />
            ) : null}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

