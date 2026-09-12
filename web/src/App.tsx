import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Moon, Sun } from "lucide-react";
import { fetchHoldings, fetchHistory, fetchSummary, fetchStatus } from "./api/portfolio";
import type { Currency, HoldingSort, Period, ReturnMethod, SortOrder } from "./lib/types";
import HoldingsTable from "./components/HoldingsTable";
import PerformanceChart, { type ZoomRange } from "./components/PerformanceChart";
import PortfolioBalance from "./components/PortfolioBalance";
import StatusBanner from "./components/StatusBanner";

export default function App() {
  const [currency, setCurrency] = useState<Currency>("CAD");
  const [period, setPeriod] = useState<Period>("1y");
  const [method, setMethod] = useState<ReturnMethod>("twr");
  const [sort, setSort] = useState<HoldingSort>("value");
  const [order, setOrder] = useState<SortOrder>("desc");
  const [zoom, setZoom] = useState<ZoomRange | null>(null);
  const [dark, setDark] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    const saved = window.localStorage.getItem("pt-theme");
    if (saved) return saved === "dark";
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    window.localStorage.setItem("pt-theme", dark ? "dark" : "light");
  }, [dark]);

  const summaryQ = useQuery({
    queryKey: ["summary", currency],
    queryFn: () => fetchSummary(currency),
  });
  const historyQ = useQuery({
    queryKey: ["history", period, currency],
    queryFn: () => fetchHistory(period, currency),
  });
  const holdingsQ = useQuery({
    queryKey: ["holdings", currency, sort, order],
    queryFn: () => fetchHoldings(currency, sort, order),
  });
  const statusQ = useQuery({
    queryKey: ["status"],
    queryFn: fetchStatus,
    refetchInterval: 5000,
  });

  const handleSort = (s: HoldingSort) => {
    if (s === sort) {
      setOrder(order === "desc" ? "asc" : "desc");
    } else {
      setSort(s);
      setOrder("desc");
    }
  };

  const error = summaryQ.error || historyQ.error || holdingsQ.error;

  // Reset chart zoom whenever the underlying dataset changes
  const handlePeriod = (p: Period) => {
    setPeriod(p);
    setZoom(null);
  };
  const handleCurrency = (c: Currency) => {
    setCurrency(c);
    setZoom(null);
  };

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-6 flex justify-end">
        <button
          onClick={() => setDark(!dark)}
          aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
          className="rounded-full p-2"
          style={{ background: "color-mix(in srgb, var(--ink) 6%, transparent)", color: "var(--ink-soft)" }}
        >
          {dark ? <Sun size={16} /> : <Moon size={16} />}
        </button>
      </div>
      {error ? (
        <div className="rounded p-4 text-sm" style={{ background: "color-mix(in srgb, var(--brick) 10%, transparent)", color: "var(--brick)" }}>
          Could not reach the API. Is FastAPI running on port 8000?
          <div className="mt-1 text-xs">{String((error as Error).message || error)}</div>
        </div>
      ) : null}
      <StatusBanner status={statusQ.data} />
      <PortfolioBalance
        summary={summaryQ.data}
        currency={currency}
        onCurrency={handleCurrency}
        period={period}
        onPeriod={handlePeriod}
        method={method}
        onMethod={setMethod}
      />
      <PerformanceChart history={historyQ.data} zoom={zoom} onZoom={setZoom} />
      <HoldingsTable
        holdings={holdingsQ.data?.holdings}
        totals={holdingsQ.data?.totals}
        sort={sort}
        order={order}
        onSort={handleSort}
      />
      <div className="mt-8 text-xs" style={{ color: "var(--ink-soft)" }}>
        Prices via yfinance. Returns computed from full transaction history.
      </div>
    </div>
  );
}

