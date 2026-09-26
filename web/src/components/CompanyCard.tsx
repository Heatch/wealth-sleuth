import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fetchSecurityDetail, fetchSecurityHistory } from "../api/portfolio";
import type { Currency, Holding, Period } from "../lib/types";
import CountryFlag from "./CountryFlag";

interface Props {
  holding: Holding;
  currency: Currency;
  onClose: () => void;
  embedded?: boolean;
}

const PERIODS: { key: Period; label: string }[] = [
  { key: "1m", label: "1M" },
  { key: "6m", label: "6M" },
  { key: "ytd", label: "YTD" },
  { key: "1y", label: "1Y" },
  { key: "3y", label: "3Y" },
  { key: "all", label: "All" },
];

function fmtMoney(v: number | null | undefined, currency: string): string {
  if (v === null || v === undefined) return "--";
  const sign = v < 0 ? "-" : "";
  return `${sign}${currency === "USD" ? "$" : "$"}${Math.abs(v).toLocaleString("en-CA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtCompactMoney(v: number | null | undefined): string {
  if (v === null || v === undefined) return "--";
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 1_000_000_000_000) return `${sign}$${(abs / 1_000_000_000_000).toFixed(1)}T`;
  if (abs >= 1_000_000_000) return `${sign}$${(abs / 1_000_000_000).toFixed(1)}B`;
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(1)}K`;
  return `${sign}$${abs.toFixed(2)}`;
}

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "--";
  const sign = v > 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(2)}%`;
}

function fmtYield(v: number | null | undefined): string {
  // Dividend yields are always non-negative; no sign prefix.
  if (v === null || v === undefined) return "--";
  return `${(v * 100).toFixed(2)}%`;
}

function fmtRatio(v: number | null | undefined): string {
  if (v === null || v === undefined) return "--";
  return v.toFixed(2);
}

function fmtDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-CA", { month: "short", day: "numeric", year: "numeric" });
}

function fmtNumber(v: number | null | undefined): string {
  if (v === null || v === undefined) return "--";
  return v.toLocaleString("en-CA");
}

export default function CompanyCard({ holding, currency, onClose, embedded }: Props) {
  const [period, setPeriod] = useState<Period>("1y");

  const detailQ = useQuery({
    queryKey: ["security", holding.symbol],
    queryFn: () => fetchSecurityDetail(holding.symbol),
    staleTime: 300_000,
  });

  const historyQ = useQuery({
    queryKey: ["security-history", holding.symbol, period],
    queryFn: () => fetchSecurityHistory(holding.symbol, period),
    staleTime: 300_000,
  });

  const detail = detailQ.data;
  const series = historyQ.data?.series ?? [];

  const chartData = useMemo(() => {
    if (series.length === 0) return [];
    if (series.length <= 400) return series;
    const step = Math.ceil(series.length / 400);
    const sampled = series.filter((_, i) => i % step === 0);
    const last = series[series.length - 1];
    if (sampled[sampled.length - 1] !== last) sampled.push(last);
    return sampled;
  }, [series]);

  const firstClose = series[0]?.close ?? null;
  const lastClose = series[series.length - 1]?.close ?? null;
  const chartChange = firstClose && lastClose ? (lastClose - firstClose) / Math.abs(firstClose) : null;

  return (
    <div
      className={embedded ? "" : "mt-6"}
      style={{
        border: "1px solid color-mix(in srgb, var(--ink) 12%, transparent)",
        background: "color-mix(in srgb, var(--ink) 2%, var(--bg))",
      }}
    >
      <div className="flex items-start justify-between p-5">
        <div>
          <div className="flex items-center gap-2">
            <CountryFlag country={detail?.country ?? holding.country} size={20} />
            <h3 className="text-lg font-semibold" style={{ color: "var(--ink)" }}>
              {detail?.name || holding.name}
            </h3>
          </div>
          <div className="mt-1 flex items-center gap-3 text-sm" style={{ color: "var(--ink-soft)" }}>
            <code>{holding.symbol}</code>
            {detail?.exchange ? <span>{detail.exchange}</span> : null}
            {detail?.asset_class ? <span className="capitalize">{detail.asset_class}</span> : null}
          </div>
        </div>
        <button
          onClick={onClose}
          aria-label="Close company card"
          className="rounded p-1"
          style={{ color: "var(--ink-soft)", background: "color-mix(in srgb, var(--ink) 6%, transparent)" }}
        >
          <X size={16} />
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4 px-5 pb-5 md:grid-cols-4">
        <Stat label="Last price" value={fmtMoney(detail?.last_price ?? holding.current_price, holding.currency)} />
        <Stat label="Market cap" value={fmtCompactMoney(detail?.market_cap ?? holding.market_cap)} />
        <Stat label="P/E (trailing)" value={fmtRatio(detail?.trailing_pe ?? holding.trailing_pe)} />
        <Stat label="Div yield" value={fmtYield(detail?.dividend_yield ?? holding.dividend_yield)} />
        <Stat label="Sector" value={detail?.sector ?? holding.sector ?? "--"} />
        <Stat label="Industry" value={detail?.industry ?? holding.industry ?? "--"} />
        <Stat label="Country" value={detail?.country ?? holding.country ?? "--"} />
        <Stat label="Currency" value={holding.currency} />
      </div>

      <div className="px-5 pb-6">
        <div className="mb-3 flex items-center justify-between">
          <div className="text-sm" style={{ color: "var(--ink-soft)" }}>
            {series.length > 0 && chartChange !== null ? (
              <>
                {fmtDate(series[0].date)} — {fmtDate(series[series.length - 1].date)}:{" "}
                <span style={{ color: chartChange >= 0 ? "var(--moss)" : "var(--brick)" }} className="tnum">
                  {chartChange >= 0 ? "+" : ""}{(chartChange * 100).toFixed(2)}%
                </span>
              </>
            ) : (
              "Price history"
            )}
          </div>
          <div className="flex gap-1">
            {PERIODS.map((p) => (
              <button
                key={p.key}
                onClick={() => setPeriod(p.key)}
                className="px-2 py-0.5 text-xs"
                style={{
                  background:
                    period === p.key
                      ? "color-mix(in srgb, var(--gold) 22%, transparent)"
                      : "color-mix(in srgb, var(--ink) 6%, transparent)",
                  color: period === p.key ? "var(--ink)" : "var(--ink-soft)",
                }}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        <div style={{ width: "100%", height: 260 }}>
          {chartData.length > 0 ? (
            <ResponsiveContainer>
              <AreaChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="secFill" x1="0" y1="0" x2="0" y2="1">
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
                  tickFormatter={(v: number) => `$${v.toFixed(0)}`}
                  tick={{ fontSize: 12, fill: "var(--ink-soft)" }}
                  axisLine={false}
                  tickLine={false}
                  width={56}
                  domain={["auto", "auto"]}
                />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null;
                    const pt = payload[0].payload as { date: string; close: number };
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
                        <div>Close: {fmtMoney(pt.close, holding.currency)}</div>
                      </div>
                    );
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="close"
                  stroke="var(--gold)"
                  strokeWidth={2}
                  fill="url(#secFill)"
                  dot={false}
                  activeDot={{ r: 4, fill: "var(--gold)" }}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center text-sm" style={{ color: "var(--ink-soft)" }}>
              {historyQ.isLoading ? "Loading chart…" : "No price history available."}
            </div>
          )}
        </div>
      </div>

      <div
        className="grid gap-4 border-t px-5 py-5 md:grid-cols-3"
        style={{ borderColor: "color-mix(in srgb, var(--ink) 10%, transparent)" }}
      >
        <div>
          <div className="text-xs uppercase tracking-wide" style={{ color: "var(--ink-soft)" }}>Your position</div>
          <div className="mt-2 grid grid-cols-2 gap-y-2 text-sm">
            <div style={{ color: "var(--ink-soft)" }}>Shares</div>
            <div className="text-right">{holding.quantity.toLocaleString("en-CA")}</div>
            <div style={{ color: "var(--ink-soft)" }}>Avg cost</div>
            <div className="text-right">{fmtMoney(holding.avg_cost, holding.currency)}</div>
            <div style={{ color: "var(--ink-soft)" }}>Book cost</div>
            <div className="text-right">{fmtMoney(holding.book_cost, currency)}</div>
            <div style={{ color: "var(--ink-soft)" }}>Value</div>
            <div className="text-right">{fmtMoney(holding.current_value, currency)}</div>
            <div style={{ color: "var(--ink-soft)" }}>Weight</div>
            <div className="text-right">{holding.weight !== null ? `${(holding.weight * 100).toFixed(1)}%` : "--"}</div>
          </div>
        </div>

        <div>
          <div className="text-xs uppercase tracking-wide" style={{ color: "var(--ink-soft)" }}>Return</div>
          <div className="mt-2 grid grid-cols-2 gap-y-2 text-sm">
            <div style={{ color: "var(--ink-soft)" }}>Gain</div>
            <div className="text-right" style={{ color: (holding.gain ?? 0) >= 0 ? "var(--moss)" : "var(--brick)" }}>
              {fmtMoney(holding.gain, currency)}
            </div>
            <div style={{ color: "var(--ink-soft)" }}>Gain %</div>
            <div className="text-right" style={{ color: (holding.gain_pct ?? 0) >= 0 ? "var(--moss)" : "var(--brick)" }}>
              {fmtPct(holding.gain_pct)}
            </div>
          </div>
        </div>

        <div>
          <div className="text-xs uppercase tracking-wide" style={{ color: "var(--ink-soft)" }}>Fundamentals</div>
          <div className="mt-2 grid grid-cols-2 gap-y-2 text-sm">
            <div style={{ color: "var(--ink-soft)" }}>52W range</div>
            <div className="text-right">
              {detail?.fifty_two_week_low != null && detail?.fifty_two_week_high != null
                ? `${fmtCompactMoney(detail.fifty_two_week_low)} — ${fmtCompactMoney(detail.fifty_two_week_high)}`
                : "--"}
            </div>
            <div style={{ color: "var(--ink-soft)" }}>Forward P/E</div>
            <div className="text-right">{fmtRatio(detail?.forward_pe)}</div>
            <div style={{ color: "var(--ink-soft)" }}>Div rate</div>
            <div className="text-right">{fmtCompactMoney(detail?.dividend_rate)}</div>
            <div style={{ color: "var(--ink-soft)" }}>Beta</div>
            <div className="text-right">{fmtRatio(detail?.beta)}</div>
            <div style={{ color: "var(--ink-soft)" }}>EPS</div>
            <div className="text-right">{fmtRatio(detail?.eps)}</div>
            <div style={{ color: "var(--ink-soft)" }}>P/S</div>
            <div className="text-right">{fmtRatio(detail?.price_to_sales)}</div>
            <div style={{ color: "var(--ink-soft)" }}>P/B</div>
            <div className="text-right">{fmtRatio(detail?.price_to_book)}</div>
            <div style={{ color: "var(--ink-soft)" }}>Avg volume</div>
            <div className="text-right">{fmtNumber(detail?.average_volume)}</div>
          </div>
        </div>
      </div>

      {detail?.description ? (
        <div
          className="border-t px-5 py-4 text-sm leading-relaxed"
          style={{ borderColor: "color-mix(in srgb, var(--ink) 10%, transparent)", color: "var(--ink-soft)" }}
        >
          {detail.description}
        </div>
      ) : null}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide" style={{ color: "var(--ink-soft)" }}>{label}</div>
      <div className="mt-0.5 text-sm font-medium" style={{ color: "var(--ink)" }}>{value}</div>
    </div>
  );
}
