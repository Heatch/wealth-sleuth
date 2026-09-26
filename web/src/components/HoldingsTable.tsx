import { Fragment } from "react";
import type { Currency, Holding, HoldingsTotals, HoldingSort, SortOrder } from "../lib/types";
import { accountLabel, brokerageLabel } from "../lib/format";
import CountryFlag from "./CountryFlag";
import CompanyCard from "./CompanyCard";

function fmtMoney(v: number | null | undefined): string {
  if (v === null || v === undefined) return "--";
  const sign = v < 0 ? "-" : "";
  return `${sign}$${Math.abs(v).toLocaleString("en-CA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
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

function fmtQty(v: number): string {
  const t = v.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
  return t === "" ? "0" : t;
}

function fmtRatio(v: number | null | undefined): string {
  if (v === null || v === undefined) return "--";
  return v.toFixed(2);
}

type Col = { key: HoldingSort | "shares"; label: string; numeric: boolean; sortable: boolean };
const COLS: Col[] = [
  { key: "name", label: "Name", numeric: false, sortable: true },
  { key: "symbol", label: "Symbol", numeric: false, sortable: true },
  { key: "shares", label: "Shares", numeric: true, sortable: true },
  { key: "last_price", label: "Last price", numeric: true, sortable: true },
  { key: "value", label: "Value", numeric: true, sortable: true },
  { key: "gain_pct", label: "Gain %", numeric: true, sortable: true },
  { key: "market_cap", label: "Market cap", numeric: true, sortable: true },
  { key: "trailing_pe", label: "P/E", numeric: true, sortable: true },
  { key: "dividend_yield", label: "Div yield", numeric: true, sortable: true },
  { key: "weight", label: "Weight", numeric: true, sortable: true },
];

interface Props {
  holdings: Holding[] | undefined;
  totals: HoldingsTotals | undefined;
  sort: HoldingSort;
  order: SortOrder;
  onSort: (s: HoldingSort) => void;
  currency: Currency;
  openCards: Record<string, Holding>;
  onToggleCard: (h: Holding) => void;
  onCloseCard: (symbol: string) => void;
}

export default function HoldingsTable({
  holdings,
  totals,
  sort,
  order,
  onSort,
  currency,
  openCards,
  onToggleCard,
  onCloseCard,
}: Props) {
  if (!holdings) {
    return <div className="py-12 text-sm" style={{ color: "var(--ink-soft)" }}>Loading holdings…</div>;
  }
  if (holdings.length === 0) {
    return <div className="py-12 text-sm" style={{ color: "var(--ink-soft)" }}>No holdings yet.</div>;
  }
  return (
    <section>
      <table className="w-full text-sm tnum">
        <thead>
          <tr style={{ borderBottom: "1px solid color-mix(in srgb, var(--ink) 12%, transparent)" }}>
            {COLS.map((c) => (
              <th
                key={c.key}
                onClick={c.sortable ? () => onSort(c.key as HoldingSort) : undefined}
                className={`${c.sortable ? "cursor-pointer" : ""} py-2 pr-3 font-medium ${c.numeric ? "text-right" : "text-left"}`}
                style={{ color: sort === c.key ? "var(--ink)" : "var(--ink-soft)" }}
              >
                {c.label}{c.sortable && sort === c.key ? (order === "desc" ? " ▼" : " ▲") : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {holdings.map((h) => {
            const g = h.gain ?? 0;
            const isOpen = !!openCards[h.symbol];
            const rowKey = `${h.symbol}-${h.brokerage}-${h.account_type}`;
            return (
              <Fragment key={rowKey}>
                <tr
                  className="cursor-pointer transition-colors"
                  style={{
                    borderBottom: "1px solid color-mix(in srgb, var(--ink) 8%, transparent)",
                    background: isOpen ? "color-mix(in srgb, var(--gold) 10%, transparent)" : "transparent",
                  }}
                  onClick={() => onToggleCard(h)}
                  onMouseEnter={(e) => { e.currentTarget.style.background = "color-mix(in srgb, var(--ink) 4%, transparent)"; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = isOpen ? "color-mix(in srgb, var(--gold) 10%, transparent)" : "transparent"; }}
                >
                  <td className="py-2 pr-3">
                    <div className="flex items-center gap-2">
                      <CountryFlag country={h.country} />
                      <span>{h.name}</span>
                    </div>
                    <div className="text-xs" style={{ color: "var(--ink-soft)" }}>
                      {brokerageLabel(h.brokerage)} · {accountLabel(h.account_type)} · {h.currency}
                    </div>
                  </td>
                  <td className="py-2 pr-3"><code>{h.symbol}</code></td>
                  <td className="py-2 pr-3 text-right">{fmtQty(h.quantity)}</td>
                  <td className="py-2 pr-3 text-right">{fmtMoney(h.current_price)}</td>
                  <td className="py-2 pr-3 text-right">
                    {h.current_value !== null && h.current_value !== undefined ? (
                      fmtMoney(h.current_value)
                    ) : (
                      <span className="animate-pulse" style={{ color: "var(--ink-soft)" }}>
                        Loading…
                      </span>
                    )}
                  </td>
                  <td className="py-2 pr-3 text-right" style={{ color: g >= 0 ? "var(--moss)" : "var(--brick)" }}>
                    {fmtPct(h.gain_pct)}
                  </td>
                  <td className="py-2 pr-3 text-right">{fmtCompactMoney(h.market_cap)}</td>
                  <td className="py-2 pr-3 text-right">{fmtRatio(h.trailing_pe)}</td>
                  <td className="py-2 pr-3 text-right">{fmtPct(h.dividend_yield)}</td>
                  <td className="py-2 text-right">
                    {h.weight !== null && h.weight !== undefined ? `${(h.weight * 100).toFixed(1)}%` : "--"}
                  </td>
                </tr>
                {isOpen && (
                  <tr
                    key={`card-${h.symbol}-${h.brokerage}-${h.account_type}`}
                    className="card-enter"
                    style={{ borderBottom: "1px solid color-mix(in srgb, var(--ink) 8%, transparent)" }}
                  >
                    <td colSpan={COLS.length} className="p-0">
                      <CompanyCard
                        holding={h}
                        currency={currency}
                        onClose={() => onCloseCard(h.symbol)}
                        embedded
                      />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
        {totals && (
          <tfoot>
            <tr>
              <td className="py-2 pr-3 font-semibold">Total</td>
              <td />
              <td />
              <td />
              <td className="py-2 pr-3 text-right font-semibold">{fmtMoney(totals.current_value)}</td>
              <td className="py-2 pr-3 text-right font-semibold" style={{ color: totals.gain >= 0 ? "var(--moss)" : "var(--brick)" }}>
                {fmtPct(totals.gain_pct)}
              </td>
              <td />
              <td />
              <td />
              <td />
            </tr>
          </tfoot>
        )}
      </table>
    </section>
  );
}
