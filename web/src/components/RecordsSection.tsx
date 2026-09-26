import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchRecords, type RecordSort } from "../api/portfolio";
import CountryFlag from "./CountryFlag";

function fmtMoney(v: number): string {
  const sign = v < 0 ? "-" : "";
  return `${sign}$${Math.abs(v).toLocaleString("en-CA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtPct(v: number): string {
  const sign = v > 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(2)}%`;
}

function fmtQty(v: number): string {
  const t = v.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
  return t === "" ? "0" : t;
}

function fmtPrice(v: number | null | undefined): string {
  if (v === null || v === undefined) return "--";
  return `$${v.toFixed(2)}`;
}

function fmtDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-CA", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default function RecordsSection() {
  const [sort, setSort] = useState<RecordSort>("pct");
  const recordsQ = useQuery({
    queryKey: ["records", sort],
    queryFn: () => fetchRecords(sort),
    staleTime: 300_000,
  });

  const data = recordsQ.data;

  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <span className="text-sm" style={{ color: "var(--ink-soft)" }}>Sort by</span>
        <button
          onClick={() => setSort("pct")}
          className="rounded px-2 py-1 text-xs"
          style={{
            background: sort === "pct" ? "color-mix(in srgb, var(--gold) 22%, transparent)" : "color-mix(in srgb, var(--ink) 6%, transparent)",
            color: sort === "pct" ? "var(--ink)" : "var(--ink-soft)",
          }}
        >
          Return %
        </button>
        <button
          onClick={() => setSort("amount")}
          className="rounded px-2 py-1 text-xs"
          style={{
            background: sort === "amount" ? "color-mix(in srgb, var(--gold) 22%, transparent)" : "color-mix(in srgb, var(--ink) 6%, transparent)",
            color: sort === "amount" ? "var(--ink)" : "var(--ink-soft)",
          }}
        >
          $ Amount
        </button>
      </div>

      {recordsQ.isLoading ? (
        <div className="py-8 text-sm" style={{ color: "var(--ink-soft)" }}>Loading records…</div>
      ) : !data ? (
        <div className="py-8 text-sm" style={{ color: "var(--ink-soft)" }}>No records available.</div>
      ) : (
        <div className="grid gap-6 md:grid-cols-2">
          <RecordList title="Best performers" records={data.best} variant="best" sort={sort} />
          <RecordList title="Worst performers" records={data.worst} variant="worst" sort={sort} />
        </div>
      )}
    </div>
  );
}

function RecordList({
  title,
  records,
  variant,
  sort,
}: {
  title: string;
  records: import("../lib/types").TradeRecord[];
  variant: "best" | "worst";
  sort: RecordSort;
}) {
  return (
    <div>
      <h4 className="mb-2 text-sm font-medium" style={{ color: "var(--ink)" }}>{title}</h4>
      <div className="space-y-2">
        {records.map((r, i) => {
          const primary = sort === "pct" ? r.gain_pct_cad : r.gain_amount_cad;
          return (
            <div
              key={`${variant}-${r.security_id}-${r.account_id}-${r.buy_date}-${i}`}
              className="rounded p-3"
              style={{ background: "color-mix(in srgb, var(--ink) 4%, transparent)" }}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <CountryFlag country={r.country} size={14} />
                    <span className="truncate text-sm font-medium" style={{ color: "var(--ink)" }}>
                      {r.name || r.symbol}
                    </span>
                    {r.is_open && (
                      <span
                        className="rounded px-1.5 py-0 text-[10px] uppercase tracking-wide"
                        style={{
                          background: "color-mix(in srgb, var(--gold) 20%, transparent)",
                          color: "var(--ink)",
                        }}
                      >
                        Open
                      </span>
                    )}
                  </div>
                  <div className="mt-0.5 flex flex-wrap gap-x-3 text-xs" style={{ color: "var(--ink-soft)" }}>
                    <code>{r.symbol}</code>
                    <span className="capitalize">{r.brokerage}</span>
                    <span className="uppercase">{r.account_type}</span>
                    {r.sector ? <span>{r.sector}</span> : null}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-semibold tnum" style={{ color: primary >= 0 ? "var(--moss)" : "var(--brick)" }}>
                    {sort === "pct" ? fmtPct(primary) : fmtMoney(primary)}
                  </div>
                  <div className="text-xs tnum" style={{ color: "var(--ink-soft)" }}>
                    {sort === "pct" ? fmtMoney(r.gain_amount_cad) : fmtPct(r.gain_pct_cad)}
                  </div>
                </div>
              </div>

              <div className="mt-2 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
                <div>
                  <div style={{ color: "var(--ink-soft)" }}>First bought</div>
                  <div style={{ color: "var(--ink)" }}>{fmtDate(r.buy_date)}</div>
                </div>
                <div>
                  <div style={{ color: "var(--ink-soft)" }}>{r.is_open ? "Current" : "Last sold"}</div>
                  <div style={{ color: "var(--ink)" }}>
                    {r.sell_date ? fmtDate(r.sell_date) : "Holding"}
                  </div>
                </div>
                <div>
                  <div style={{ color: "var(--ink-soft)" }}>Held (weighted)</div>
                  <div style={{ color: "var(--ink)" }}>{r.duration_label}</div>
                </div>
                <div>
                  <div style={{ color: "var(--ink-soft)" }}>Quantity</div>
                  <div style={{ color: "var(--ink)" }}>{fmtQty(r.quantity)}</div>
                </div>
              </div>

              <div className="mt-2 grid grid-cols-3 gap-2 text-xs">
                <div>
                  <div style={{ color: "var(--ink-soft)" }}>Avg buy</div>
                  <div className="tnum" style={{ color: "var(--ink)" }}>{fmtPrice(r.buy_price)}</div>
                </div>
                <div>
                  <div style={{ color: "var(--ink-soft)" }}>{r.is_open ? "Last price" : "Avg sell"}</div>
                  <div className="tnum" style={{ color: "var(--ink)" }}>{fmtPrice(r.sell_price)}</div>
                </div>
                <div>
                  <div style={{ color: "var(--ink-soft)" }}>Cost / Value</div>
                  <div className="tnum" style={{ color: "var(--ink)" }}>
                    {fmtMoney(r.cost_basis)} / {fmtMoney(r.proceeds_or_value)}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
