import type { Currency, Period, PortfolioSummary, ReturnMethod } from "../lib/types";

const PERIODS: { key: Period; label: string }[] = [
  { key: "1m", label: "1M" },
  { key: "6m", label: "6M" },
  { key: "ytd", label: "YTD" },
  { key: "1y", label: "1Y" },
  { key: "3y", label: "3Y" },
  { key: "all", label: "ALL" },
];

const PERIOD_KEYS: Record<Period, string> = {
  "1m": "m1",
  "6m": "m6",
  ytd: "ytd",
  "1y": "y1",
  "3y": "y3",
  all: "all",
};

const METHODS: {
  key: ReturnMethod;
  label: string;
  title: string;
  body: string;
}[] = [
  {
    key: "xirr",
    label: "XIRR",
    title: "Money-weighted return",
    body:
      "Best for seeing the actual annualized return on your money, including the real impact of deposits and withdrawals.",
  },
  {
    key: "twr",
    label: "TWR",
    title: "Time-weighted return",
    body:
      "Best for evaluating the portfolio's underlying performance because it removes the effect of when cash moved in or out.",
  },
];

function fmtMoney(v: number | null | undefined): string {
  if (v === null || v === undefined) return "--";
  const sign = v < 0 ? "-" : "";
  return `${sign}$${Math.abs(v).toLocaleString("en-CA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "--";
  const sign = v > 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(2)}%`;
}

interface Props {
  summary: PortfolioSummary | undefined;
  currency: Currency;
  onCurrency: (c: Currency) => void;
  period: Period;
  onPeriod: (p: Period) => void;
  method: ReturnMethod;
  onMethod: (m: ReturnMethod) => void;
}

export default function PortfolioBalance({
  summary,
  currency,
  onCurrency,
  period,
  onPeriod,
  method,
  onMethod,
}: Props) {
  if (!summary) {
    return <div className="py-12 text-sm" style={{ color: "var(--ink-soft)" }}>Loading portfolio…</div>;
  }

  const ret = summary.returns[PERIOD_KEYS[period]];
  const retVal = ret ? ret[method] : null;
  const gain = retVal !== null && retVal !== undefined;
  const dayGain = (summary.total_change_today ?? 0) >= 0;

  return (
    <section>
      <div className="flex items-end justify-between">
        <div>
          <div className="font-display" style={{ fontSize: 56, lineHeight: 1.1 }}>
            {fmtMoney(summary.total_value)}
            <span className="ml-2" style={{ fontSize: 20 }}>{currency}</span>
          </div>
          <div className="mt-2 text-sm tnum" style={{ color: dayGain ? "var(--moss)" : "var(--brick)" }}>
            {fmtMoney(summary.total_change_today)} ({fmtPct(summary.total_change_today_pct)}) today
          </div>
          <div className="mt-1 text-sm tnum" style={{ color: "var(--ink-soft)" }}>
            Cash: {fmtMoney(summary.cash_total)}
          </div>
        </div>
        <div className="flex gap-1 rounded-full p-1" style={{ background: "color-mix(in srgb, var(--ink) 6%, transparent)" }}>
          {(["CAD", "USD"] as Currency[]).map((c) => (
            <button
              key={c}
              onClick={() => onCurrency(c)}
              className="rounded-full px-4 py-1 text-sm"
              style={{
                background: c === currency ? "var(--gold)" : "transparent",
                color: c === currency ? "var(--bg)" : "var(--ink-soft)",
              }}
            >
              {c}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-3">
        <div className="flex gap-1">
          {PERIODS.map((p) => (
            <button
              key={p.key}
              onClick={() => onPeriod(p.key)}
              className="rounded px-2.5 py-1 text-sm"
              style={{
                background: p.key === period ? "color-mix(in srgb, var(--gold) 18%, transparent)" : "transparent",
                color: p.key === period ? "var(--ink)" : "var(--ink-soft)",
                fontWeight: p.key === period ? 600 : 400,
              }}
            >
              {p.label}
            </button>
          ))}
        </div>

        <div className="flex gap-1">
          {METHODS.map((m) => (
            <div key={m.key} className="group relative">
              <button
                onClick={() => onMethod(m.key)}
                className="rounded px-2.5 py-1 text-sm"
                style={{
                  background: m.key === method ? "color-mix(in srgb, var(--gold) 18%, transparent)" : "transparent",
                  color: m.key === method ? "var(--ink)" : "var(--ink-soft)",
                  fontWeight: m.key === method ? 600 : 400,
                }}
              >
                {m.label}
              </button>
              <div
                className="pointer-events-none absolute left-1/2 top-full z-10 mt-2 hidden w-64 -translate-x-1/2 rounded p-3 text-left group-hover:block"
                style={{
                  background: "var(--bg)",
                  border: "1px solid color-mix(in srgb, var(--ink) 12%, transparent)",
                }}
              >
                <div className="text-xs" style={{ fontWeight: 600, color: "var(--ink)" }}>
                  {m.title}
                </div>
                <div className="mt-1 text-xs" style={{ color: "var(--ink-soft)", lineHeight: 1.4 }}>
                  {m.body}
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="text-2xl tnum" style={{ color: gain && (retVal ?? 0) >= 0 ? "var(--moss)" : "var(--brick)" }}>
          {fmtPct(retVal)}
        </div>
      </div>
    </section>
  );
}
