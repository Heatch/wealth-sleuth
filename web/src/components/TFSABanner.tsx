import { useQuery } from "@tanstack/react-query";
import { Info } from "lucide-react";
import { fetchTfsaSummary } from "../api/portfolio";
import type { TfsaSummary as TfsaSummaryType } from "../lib/types";

interface Props {
  birthYear: number;
  onBirthYear: (year: number) => void;
  accountIds?: number[] | null;
}

function fmtMoney(v: number): string {
  const sign = v < 0 ? "-" : "";
  return `${sign}$${Math.abs(v).toLocaleString("en-CA", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

export default function TFSABanner({ birthYear, onBirthYear, accountIds }: Props) {
  const summaryQ = useQuery<TfsaSummaryType>({
    queryKey: ["tfsa", birthYear, accountIds],
    queryFn: () => fetchTfsaSummary(birthYear, accountIds),
    staleTime: 300_000,
  });

  const s = summaryQ.data;
  if (!s) {
    return (
      <div
        className="mb-6 rounded p-4 text-sm"
        style={{
          background: "color-mix(in srgb, var(--gold) 10%, transparent)",
          border: "1px solid color-mix(in srgb, var(--gold) 25%, transparent)",
          color: "var(--ink)",
        }}
      >
        Loading TFSA room…
      </div>
    );
  }

  const isOver = s.remaining_room < 0;
  const barPct = Math.min(100, Math.max(0, s.pct_used * 100));

  return (
    <div
      className="mb-6 rounded-lg p-5"
      style={{
        background: "color-mix(in srgb, var(--gold) 10%, transparent)",
        border: "1px solid color-mix(in srgb, var(--gold) 28%, transparent)",
      }}
    >
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <Info size={18} style={{ color: "var(--gold)" }} />
          <h3 className="text-sm font-semibold" style={{ color: "var(--ink)" }}>
            TFSA Contribution Room — {s.current_year}
          </h3>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <label htmlFor="birth-year" style={{ color: "var(--ink-soft)" }}>
            Birth year
          </label>
          <input
            id="birth-year"
            type="number"
            min={1900}
            max={2100}
            value={birthYear}
            onChange={(e) => {
              const y = parseInt(e.target.value, 10);
              if (!Number.isNaN(y)) onBirthYear(y);
            }}
            className="w-20 rounded px-2 py-1 text-right text-sm"
            style={{
              background: "var(--bg)",
              color: "var(--ink)",
              border: "1px solid color-mix(in srgb, var(--ink) 16%, transparent)",
            }}
          />
          <span className="text-xs" style={{ color: "var(--ink-soft)" }}>
            (turned 18 in {s.year_turned_18})
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Lifetime contributions" value={fmtMoney(s.lifetime_contributions)} />
        <Stat label="Total available room" value={fmtMoney(s.total_room)} />
        <Stat
          label="Remaining room"
          value={fmtMoney(s.remaining_room)}
          valueColor={isOver ? "var(--brick)" : "var(--moss)"}
        />
        <Stat label="Room used" value={`${(s.pct_used * 100).toFixed(1)}%`} />
      </div>

      <div className="mt-4">
        <div
          className="h-2 w-full overflow-hidden rounded-full"
          style={{ background: "color-mix(in srgb, var(--ink) 10%, transparent)" }}
        >
          <div
            className="h-full transition-all duration-500"
            style={{
              width: `${barPct}%`,
              background: isOver ? "var(--brick)" : "var(--gold)",
            }}
          />
        </div>
        <div className="mt-1 flex justify-between text-xs" style={{ color: "var(--ink-soft)" }}>
          <span>
            {isOver
              ? `Over-contributed by ${fmtMoney(Math.abs(s.remaining_room))}`
              : `${fmtMoney(s.remaining_room)} left`}
          </span>
          <span>
            Annual room since {s.first_contribution_year}: {fmtMoney(s.cumulative_room)}
            {s.withdrawal_room > 0 && ` + ${fmtMoney(s.withdrawal_room)} from past withdrawals`}
          </span>
        </div>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  valueColor,
}: {
  label: string;
  value: string;
  valueColor?: string;
}) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide" style={{ color: "var(--ink-soft)" }}>
        {label}
      </div>
      <div
        className="mt-0.5 text-lg font-semibold tnum"
        style={{ color: valueColor || "var(--ink)" }}
      >
        {value}
      </div>
    </div>
  );
}
