import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Moon, Sun } from "lucide-react";
import {
  fetchAccounts,
  fetchHoldings,
  fetchHistory,
  fetchSummary,
  fetchStatus,
} from "./api/portfolio";
import type { AllocationFilter, Currency, Holding, HoldingSort, Period, ReturnMethod, SortOrder } from "./lib/types";
import AccountTypeFilter from "./components/AccountTypeFilter";
import AllocationSection from "./components/AllocationSection";
import BrokerageFilter from "./components/BrokerageFilter";
import CollapsibleSection from "./components/CollapsibleSection";
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
  const [allocationFilter, setAllocationFilter] = useState<AllocationFilter | null>(null);
  const [holdingsOpen, setHoldingsOpen] = useState(true);
  const [allocationOpen, setAllocationOpen] = useState(true);
  const [openCards, setOpenCards] = useState<Record<string, Holding>>({});
  const [selectedBrokerages, setSelectedBrokerages] = useState<string[] | null>(() => {
    if (typeof window === "undefined") return null;
    try {
      const saved = window.localStorage.getItem("pt-brokerages");
      return saved ? (JSON.parse(saved) as string[]) : null;
    } catch {
      return null;
    }
  });
  const [selectedTypes, setSelectedTypes] = useState<string[] | null>(() => {
    if (typeof window === "undefined") return null;
    try {
      const saved = window.localStorage.getItem("pt-types");
      if (!saved) return null;
      const parsed = JSON.parse(saved) as string[];
      // Migrate old plain-type format (["tfsa"]) to composite keys
      // (["tfsa__CAD"]); unknown entries reset to All.
      if (parsed.some((x) => !x.includes("__"))) return null;
      return parsed;
    } catch {
      return null;
    }
  });
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

  useEffect(() => {
    window.localStorage.setItem("pt-brokerages", JSON.stringify(selectedBrokerages));
  }, [selectedBrokerages]);
  useEffect(() => {
    window.localStorage.setItem("pt-types", JSON.stringify(selectedTypes));
  }, [selectedTypes]);

  const accountsQ = useQuery({
    queryKey: ["accounts"],
    queryFn: fetchAccounts,
    staleTime: 3600_000,
  });

  // Derive selected account IDs from the two dimension filters.
  // null = all accounts (no filtering).
  const selectedAccounts: number[] | null = useMemo(() => {
    const list = accountsQ.data?.accounts;
    if (!list) return null;
    if (selectedBrokerages === null && selectedTypes === null) return null;
    const filtered = list.filter((a) => {
      const brkOk = selectedBrokerages === null || selectedBrokerages.includes(a.brokerage);
      const typOk =
        selectedTypes === null ||
        selectedTypes.includes(`${a.account_type}__${a.currency}`);
      return brkOk && typOk;
    });
    if (filtered.length === list.length) return null;
    return filtered.map((a) => a.id);
  }, [accountsQ.data, selectedBrokerages, selectedTypes]);

  const holdingsQ = useQuery({
    queryKey: ["holdings", currency, sort, order, selectedAccounts],
    queryFn: () => fetchHoldings(currency, sort, order, selectedAccounts ?? undefined),
  });

  const filteredHoldings = useMemo(() => {
    const all = holdingsQ.data?.holdings ?? [];
    if (!allocationFilter) return all;
    return all.filter((h) => (h[allocationFilter.dimension] ?? "Unknown") === allocationFilter.value);
  }, [holdingsQ.data, allocationFilter]);

  const filteredTotals = useMemo(() => {
    if (!filteredHoldings.length) return undefined;
    const totalValue = filteredHoldings.reduce((s, h) => s + (h.current_value ?? 0), 0);
    const totalBook = filteredHoldings.reduce((s, h) => s + h.book_cost, 0);
    return {
      book_cost: totalBook,
      current_value: totalValue,
      gain: totalValue - totalBook,
      gain_pct: totalBook ? (totalValue - totalBook) / Math.abs(totalBook) : null,
    };
  }, [filteredHoldings]);

  const sliceSymbols = useMemo(() => {
    if (!allocationFilter || !filteredHoldings.length) return undefined;
    return Array.from(new Set(filteredHoldings.map((h) => h.symbol)));
  }, [allocationFilter, filteredHoldings]);

  const summaryQ = useQuery({
    queryKey: ["summary", currency, selectedAccounts, sliceSymbols],
    queryFn: () => fetchSummary(currency, selectedAccounts ?? undefined, sliceSymbols),
  });
  const historyQ = useQuery({
    queryKey: ["history", period, currency, selectedAccounts, sliceSymbols],
    queryFn: () => fetchHistory(period, currency, selectedAccounts ?? undefined, sliceSymbols),
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

  const sameHolding = (a: Holding, b: Holding) =>
    a.symbol === b.symbol && a.brokerage === b.brokerage && a.account_type === b.account_type;

  const handleToggleCard = (h: Holding) => {
    setOpenCards((prev) => {
      const next = { ...prev };
      if (next[h.symbol] && sameHolding(next[h.symbol], h)) {
        delete next[h.symbol];
      } else {
        next[h.symbol] = h;
      }
      return next;
    });
  };

  const handleCloseCard = (symbol: string) => {
    setOpenCards((prev) => {
      const next = { ...prev };
      delete next[symbol];
      return next;
    });
  };

  const error = summaryQ.error || historyQ.error || holdingsQ.error;

  // Reset chart zoom and allocation filter whenever the underlying dataset changes
  const handlePeriod = (p: Period) => {
    setPeriod(p);
    setZoom(null);
  };
  const handleCurrency = (c: Currency) => {
    setCurrency(c);
    setZoom(null);
    setAllocationFilter(null);
    setOpenCards({});
  };
  const handleBrokerages = (ids: string[] | null) => {
    setSelectedBrokerages(ids);
    setZoom(null);
    setAllocationFilter(null);
    setOpenCards({});
  };
  const handleTypes = (ids: string[] | null) => {
    setSelectedTypes(ids);
    setZoom(null);
    setAllocationFilter(null);
    setOpenCards({});
  };
  const handleAllocationFilter = (f: AllocationFilter | null) => {
    setAllocationFilter(f);
    setZoom(null);
    setOpenCards({});
  };

  const nothingSelected = selectedAccounts !== null && selectedAccounts.length === 0;

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BrokerageFilter
            accounts={accountsQ.data?.accounts}
            selected={selectedBrokerages}
            onChange={handleBrokerages}
            typeFilter={selectedTypes}
          />
          <AccountTypeFilter
            accounts={accountsQ.data?.accounts}
            selected={selectedTypes}
            onChange={handleTypes}
            brokerageFilter={selectedBrokerages}
          />
        </div>
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
      {nothingSelected ? (
        <div className="py-12 text-sm" style={{ color: "var(--ink-soft)" }}>
          Select accounts above to view portfolio data.
        </div>
      ) : allocationFilter && filteredHoldings.length === 0 ? (
        <div className="py-12 text-sm" style={{ color: "var(--ink-soft)" }}>
          No holdings match the selected allocation filter.
          <button
            onClick={() => setAllocationFilter(null)}
            className="ml-3 rounded px-2 py-0.5 text-xs"
            style={{ background: "color-mix(in srgb, var(--gold) 18%, transparent)", color: "var(--ink)" }}
          >
            Clear
          </button>
        </div>
      ) : (
        <>
          <PortfolioBalance
            summary={summaryQ.data}
            currency={currency}
            onCurrency={handleCurrency}
            period={period}
            onPeriod={handlePeriod}
            method={method}
            onMethod={setMethod}
          />
          <PerformanceChart history={historyQ.data} zoom={zoom} onZoom={setZoom} method={method} />
          <CollapsibleSection title="Holdings" open={holdingsOpen} onToggle={() => setHoldingsOpen((o) => !o)}>
            <HoldingsTable
              holdings={holdingsQ.isLoading ? undefined : filteredHoldings}
              totals={holdingsQ.isLoading ? undefined : filteredTotals}
              sort={sort}
              order={order}
              onSort={handleSort}
              currency={currency}
              openCards={openCards}
              onToggleCard={handleToggleCard}
              onCloseCard={handleCloseCard}
            />
          </CollapsibleSection>
        </>
      )}
      {!nothingSelected && (
        <CollapsibleSection title="Allocation" open={allocationOpen} onToggle={() => setAllocationOpen((o) => !o)}>
          <AllocationSection
            holdings={holdingsQ.data?.holdings}
            filter={allocationFilter}
            onFilter={handleAllocationFilter}
          />
        </CollapsibleSection>
      )}
      <div className="mt-8 text-xs" style={{ color: "var(--ink-soft)" }}>
        Prices via yfinance. Returns computed from full transaction history.
      </div>
    </div>
  );
}

