import { useMemo } from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { PortfolioHistory } from "../lib/types";

interface Props {
  history: PortfolioHistory | undefined;
}

function fmtMoney(v: number): string {
  return `$${v.toLocaleString("en-CA", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function fmtDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-CA", { month: "short", day: "numeric", year: "numeric" });
}

export default function PerformanceChart({ history }: Props) {
  const data = useMemo(() => {
    if (!history) return [];
    // Downsample to at most ~400 points for rendering performance
    const pts = history.series;
    if (pts.length <= 400) return pts;
    const step = Math.ceil(pts.length / 400);
    const sampled = pts.filter((_, i) => i % step === 0);
    const last = pts[pts.length - 1];
    if (sampled[sampled.length - 1] !== last) sampled.push(last);
    return sampled;
  }, [history]);

  if (!history || data.length === 0) {
    return <div className="py-12 text-sm" style={{ color: "var(--ink-soft)" }}>Loading chart…</div>;
  }

  return (
    <section className="mt-8">
      <div style={{ width: "100%", height: 320 }}>
        <ResponsiveContainer>
          <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
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
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

