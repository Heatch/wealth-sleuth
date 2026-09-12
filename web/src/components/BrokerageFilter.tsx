import { useEffect, useRef, useState } from "react";
import type { Account } from "../lib/types";
import { brokerageLabel } from "../lib/format";

interface Props {
  accounts: Account[] | undefined;
  selected: string[] | null;
  onChange: (ids: string[] | null) => void;
}

export default function BrokerageFilter({ accounts, selected, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const brokerages = [...new Set((accounts ?? []).map((a) => a.brokerage))].sort();
  const total = brokerages.length;
  const selCount = selected === null ? total : selected.length;
  const allSelected = selected === null || selCount === total;

  const label = allSelected ? "All Brokerages" : `${selCount} of ${total} Brokerages`;

  const holdingsFor = (b: string) =>
    (accounts ?? []).filter((a) => a.brokerage === b).reduce((n, a) => n + a.holding_count, 0);

  const isChecked = (b: string) =>
    selected === null ? true : selected.includes(b);

  const toggle = (b: string) => {
    if (selected === null) {
      onChange(brokerages.filter((x) => x !== b));
    } else if (selected.includes(b)) {
      const next = selected.filter((x) => x !== b);
      onChange(next.length === total ? null : next);
    } else {
      const next = [...selected, b];
      onChange(next.length === total ? null : next);
    }
  };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="rounded-full px-4 py-1 text-sm"
        style={{
          background: allSelected
            ? "color-mix(in srgb, var(--ink) 6%, transparent)"
            : "var(--gold)",
          color: allSelected ? "var(--ink-soft)" : "var(--bg)",
        }}
      >
        {label} ▾
      </button>
      {open ? (
        <div
          className="absolute left-0 z-10 mt-2 w-64 rounded p-2"
          style={{
            background: "var(--bg)",
            border: "1px solid color-mix(in srgb, var(--ink) 12%, transparent)",
          }}
        >
          <div className="flex gap-3 px-2 py-1 text-xs" style={{ color: "var(--ink-soft)" }}>
            <button onClick={() => onChange(null)} className="hover:underline">
              Select All
            </button>
            <button onClick={() => onChange([])} className="hover:underline">
              Clear All
            </button>
          </div>
          {brokerages.map((b) => {
            const n = holdingsFor(b);
            return (
              <label
                key={b}
                className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm"
                style={{ opacity: n > 0 ? 1 : 0.55, color: "var(--ink)" }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background =
                    "color-mix(in srgb, var(--ink) 4%, transparent)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "transparent";
                }}
              >
                <input
                  type="checkbox"
                  checked={isChecked(b)}
                  onChange={() => toggle(b)}
                  style={{ accentColor: "var(--gold)" }}
                />
                <span>{brokerageLabel(b)}</span>
                <span className="ml-auto text-xs" style={{ color: "var(--ink-soft)" }}>
                  {n > 0 ? `${n} holding${n === 1 ? "" : "s"}` : "0 holdings"}
                </span>
              </label>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
