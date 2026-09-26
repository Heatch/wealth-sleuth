import { useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Line,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type {
  BenchmarksHistoryResponse,
  PortfolioHistory,
  ReturnMethod,
} from "../lib/types";

export interface ZoomRange {
  start: string;
  end: string;
}

interface Props {
  history: PortfolioHistory | undefined;
  benchmarks: BenchmarksHistoryResponse | undefined;
  zoom: ZoomRange | null;
  onZoom: (z: ZoomRange | null) => void;
  method: ReturnMethod;
}

function fmtMoney(v: number): string {
  return `$${v.toLocaleString("en-CA", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function fmtDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-CA", { month: "short", day: "numeric", year: "numeric" });
}

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "--";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(2)}%`;
}

const BENCHMARK_COLORS: Record<string, string> = {
  SPY: "var(--moss)",
  "XIU.TO": "var(--brick)",
  QQQ: "#5b8cd4",
};

interface MergedPoint {
  date: string;
  portfolio: number | null;
  return_xirr?: number | null;
  return_twr?: number | null;
  net_deposits?: number | null;
  [key: `benchmark_${string}`]: number | null | undefined;
  [key: `return_xirr_${string}`]: number | null | undefined;
  [key: `return_twr_${string}`]: number | null | undefined;
}

export function mergeData(
  history: PortfolioHistory | undefined,
  benchmarks: BenchmarksHistoryResponse | undefined,
): MergedPoint[] {
  const byDate = new Map<string, MergedPoint>();

  for (const pt of history?.series ?? []) {
    byDate.set(pt.date, {
      date: pt.date,
      portfolio: pt.value,
      return_xirr: pt.return_xirr,
      return_twr: pt.return_twr,
      net_deposits: pt.net_deposits,
    });
  }

  if (benchmarks?.benchmarks) {
    for (const [symbol, bench] of Object.entries(benchmarks.benchmarks)) {
      for (const pt of bench.series) {
        const existing = byDate.get(pt.date);
        if (existing) {
          existing[`benchmark_${symbol}`] = pt.value;
          existing[`return_xirr_${symbol}`] = pt.return_xirr;
          existing[`return_twr_${symbol}`] = pt.return_twr;
        } else {
          byDate.set(pt.date, {
            date: pt.date,
            portfolio: null,
            [`benchmark_${symbol}`]: pt.value,
            [`return_xirr_${symbol}`]: pt.return_xirr,
            [`return_twr_${symbol}`]: pt.return_twr,
          } as MergedPoint);
        }
      }
    }
  }

  return Array.from(byDate.values()).sort((a, b) => (a.date < b.date ? -1 : 1));
}

function seriesReturn(
  data: MergedPoint[],
  zoom: ZoomRange | null,
  dataKey: string,
): number | null {
  const pts = zoom ? data.filter((p) => p.date >= zoom.start && p.date <= zoom.end) : data;
  const values = pts.map((p) => p[dataKey as keyof MergedPoint] as number | null).filter((v) => v !== null && v !== undefined);
  if (values.length < 2) return null;
  const first = values[0];
  const last = values[values.length - 1];
  if (!first) return null;
  return (last - first) / Math.abs(first);
}

function returnForPoint(pt: MergedPoint, method: ReturnMethod, suffix: string): number | null | undefined {
  if (suffix === "") {
    return method === "xirr" ? pt.return_xirr : pt.return_twr;
  }
  const key = method === "xirr" ? (`return_xirr_${suffix}` as keyof MergedPoint) : (`return_twr_${suffix}` as keyof MergedPoint);
  return pt[key] as number | null | undefined;
}

export default function PerformanceChart({ history, benchmarks, zoom, onZoom, method }: Props) {
  const [refLeft, setRefLeft] = useState<string | null>(null);
  const [refRight, setRefRight] = useState<string | null>(null);

  const fullData = useMemo(() => mergeData(history, benchmarks), [history, benchmarks]);
  const activeBenchmarks = useMemo(
    () => (benchmarks ? Object.keys(benchmarks.benchmarks) : []),
    [benchmarks],
  );

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

  const portfolioZoomRet = seriesReturn(fullData, zoom, "portfolio");

  return (
    <section className="mt-8">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-sm" style={{ color: "var(--ink-soft)" }}>
          {zoom ? (
            <>
              {fmtDate(zoom.start)} — {fmtDate(zoom.end)}
              <span style={{ color: "var(--ink-soft)" }}> · value change </span>
              <span
                className="tnum"
                style={{ color: (portfolioZoomRet ?? 0) >= 0 ? "var(--moss)" : "var(--brick)" }}
              >
                {fmtPct(portfolioZoomRet)}
              </span>
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
              content={({ active, payload, label }) => {
                if (!active || !payload?.length) return null;
                const pt = payload[0].payload as MergedPoint;
                return (
                  <div
                    style={{
                      background: "var(--bg)",
                      border: "1px solid color-mix(in srgb, var(--ink) 12%, transparent)",
                      borderRadius: 4,
                      fontSize: 13,
                      padding: "8px 12px",
                    }}
                  >
                    <div style={{ marginBottom: 4 }}>{fmtDate(String(label))}</div>
                    {payload.map((item) => {
                      const key = String(item.dataKey);
                      const isPortfolio = key === "portfolio";
                      const symbol = isPortfolio ? "" : key.replace("benchmark_", "");
                      const xirr = returnForPoint(pt, "xirr", symbol);
                      const twr = returnForPoint(pt, "twr", symbol);
                      const color = item.color || "var(--gold)";
                      const name = isPortfolio ? "Portfolio" : benchmarks?.benchmarks[symbol]?.display || symbol;
                      return (
                        <div key={key} style={{ marginBottom: 4 }}>
                          <div>
                            <span style={{ color }}>●</span>{" "}
                            <span style={{ fontWeight: 600 }}>{name}</span>: {fmtMoney(Number(item.value))}
                          </div>
                          <div className="tnum" style={{ marginLeft: 14, color: "var(--ink-soft)" }}>
                            <span style={{ fontWeight: method === "xirr" ? 600 : 400, color: "var(--ink)" }}>
                              XIRR {fmtPct(xirr)}
                            </span>
                            {" · "}
                            <span style={{ fontWeight: method === "twr" ? 600 : 400, color: "var(--ink)" }}>
                              TWR {fmtPct(twr)}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                    {pt.net_deposits !== null &&
                      pt.net_deposits !== undefined &&
                      Math.abs(pt.net_deposits) > 0.005 && (
                        <div style={{ marginTop: 4, color: "var(--ink-soft)" }}>
                          Net deposits: {fmtMoney(pt.net_deposits)}
                        </div>
                      )}
                  </div>
                );
              }}
            />
            <Area
              type="monotone"
              dataKey="portfolio"
              stroke="var(--gold)"
              strokeWidth={2}
              fill="url(#pfFill)"
              dot={false}
              activeDot={{ r: 4, fill: "var(--gold)" }}
              isAnimationActive={false}
              connectNulls={false}
            />
            {activeBenchmarks.map((symbol) => (
              <Line
                key={symbol}
                type="monotone"
                dataKey={`benchmark_${symbol}`}
                stroke={BENCHMARK_COLORS[symbol] || "#888"}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
                isAnimationActive={false}
                connectNulls={false}
              />
            ))}
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
