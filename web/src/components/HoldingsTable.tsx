import type { Holding, HoldingsTotals, HoldingSort, SortOrder } from "../lib/types";

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

function fmtQty(v: number): string {
  const t = v.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
  return t === "" ? "0" : t;
}

type Col = { key: HoldingSort | "shares"; label: string; numeric: boolean; sortable: boolean };
const COLS: Col[] = [
  { key: "name", label: "Name", numeric: false, sortable: true },
  { key: "symbol", label: "Symbol", numeric: false, sortable: true },
  { key: "shares", label: "Shares", numeric: true, sortable: true },
  { key: "value", label: "Value", numeric: true, sortable: true },
  { key: "gain", label: "Gain", numeric: true, sortable: true },
  { key: "gain_pct", label: "Gain %", numeric: true, sortable: true },
  { key: "book_cost", label: "Book cost", numeric: true, sortable: true },
  { key: "weight", label: "Weight", numeric: true, sortable: true },
];

interface Props {
  holdings: Holding[] | undefined;
  totals: HoldingsTotals | undefined;
  sort: HoldingSort;
  order: SortOrder;
  onSort: (s: HoldingSort) => void;
}

export default function HoldingsTable({ holdings, totals, sort, order, onSort }: Props) {
  if (!holdings) {
    return <div className="py-12 text-sm" style={{ color: "var(--ink-soft)" }}>Loading holdings…</div>;
  }
  if (holdings.length === 0) {
    return <div className="py-12 text-sm" style={{ color: "var(--ink-soft)" }}>No holdings yet.</div>;
  }
  return (
    <section className="mt-8">
      <h2 className="text-sm font-semibold" style={{ color: "var(--ink)" }}>Holdings</h2>
      <table className="mt-3 w-full text-sm tnum">
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
            return (
              <tr
                key={`${h.symbol}-${h.brokerage}-${h.account_type}`}
                className="transition-colors"
                style={{ borderBottom: "1px solid color-mix(in srgb, var(--ink) 8%, transparent)" }}
                onMouseEnter={(e) => { e.currentTarget.style.background = "color-mix(in srgb, var(--ink) 4%, transparent)"; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
              >
                <td className="py-2 pr-3">
                  <div>{h.name}</div>
                  <div className="text-xs" style={{ color: "var(--ink-soft)" }}>
                    {h.brokerage} · {h.account_type}
                  </div>
                </td>
                <td className="py-2 pr-3"><code>{h.symbol}</code></td>
                <td className="py-2 pr-3 text-right">{fmtQty(h.quantity)}</td>
                <td className="py-2 pr-3 text-right">
                  {h.current_value !== null && h.current_value !== undefined ? (
                    fmtMoney(h.current_value)
                  ) : (
                    <span className="animate-pulse" style={{ color: "var(--ink-soft)" }}>
                      Loading...
                    </span>
                  )}
                </td>
                <td className="py-2 pr-3 text-right" style={{ color: g >= 0 ? "var(--moss)" : "var(--brick)" }}>
                  {fmtMoney(h.gain)}
                </td>
                <td className="py-2 pr-3 text-right" style={{ color: g >= 0 ? "var(--moss)" : "var(--brick)" }}>
                  {fmtPct(h.gain_pct)}
                </td>
                <td className="py-2 pr-3 text-right">{fmtMoney(h.book_cost)}</td>
                <td className="py-2 text-right">
                  {h.weight !== null && h.weight !== undefined ? `${(h.weight * 100).toFixed(1)}%` : "--"}
                </td>
              </tr>
            );
          })}
        </tbody>
        {totals && (
          <tfoot>
            <tr>
              <td className="py-2 pr-3 font-semibold">Total</td>
              <td />
              <td />
              <td className="py-2 pr-3 text-right font-semibold">{fmtMoney(totals.current_value)}</td>
              <td className="py-2 pr-3 text-right font-semibold" style={{ color: totals.gain >= 0 ? "var(--moss)" : "var(--brick)" }}>
                {fmtMoney(totals.gain)}
              </td>
              <td className="py-2 pr-3 text-right font-semibold" style={{ color: totals.gain >= 0 ? "var(--moss)" : "var(--brick)" }}>
                {fmtPct(totals.gain_pct)}
              </td>
              <td className="py-2 pr-3 text-right font-semibold">{fmtMoney(totals.book_cost)}</td>
              <td />
            </tr>
          </tfoot>
        )}
      </table>
    </section>
  );
}

