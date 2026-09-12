import { useEffect, useRef, useState } from "react";
import type { Account } from "../lib/types";
import { accountLabel } from "../lib/format";

interface Props {
  accounts: Account[] | undefined;
  selected: string[] | null;
  onChange: (ids: string[] | null) => void;
}

export interface TypeCurrency {
  key: string;
  account_type: string;
  currency: string;
  label: string;
}

export function typeCurrencyCombos(accounts: Account[]): TypeCurrency[] {
  const seen = new Map<string, TypeCurrency>();
  for (const a of accounts) {
    const key = `${a.account_type}__${a.currency}`;
    if (!seen.has(key)) {
      seen.set(key, {
        key,
        account_type: a.account_type,
        currency: a.currency,
        label: `${accountLabel(a.account_type)} ${a.currency}`,
      });
    }
  }
  return [...seen.values()].sort((x, y) => x.label.localeCompare(y.label));
}

export default function AccountTypeFilter({ accounts, selected, onChange }: Props) {
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

  const combos = typeCurrencyCombos(accounts ?? []);
  const total = combos.length;
  const selCount = selected === null ? total : selected.length;
  const allSelected = selected === null || selCount === total;

  const label = allSelected ? "All Types" : `${selCount} of ${total} Types`;

  const holdingsFor = (key: string) =>
    (accounts ?? [])
      .filter((a) => `${a.account_type}__${a.currency}` === key)
      .reduce((n, a) => n + a.holding_count, 0);

  const isChecked = (key: string) =>
    selected === null ? true : selected.includes(key);

  const toggle = (key: string) => {
    if (selected === null) {
      onChange(combos.map((c) => c.key).filter((x) => x !== key));
    } else if (selected.includes(key)) {
      const next = selected.filter((x) => x !== key);
      onChange(next.length === total ? null : next);
    } else {
      const next = [...selected, key];
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
          {combos.map((c) => {
            const n = holdingsFor(c.key);
            return (
              <label
                key={c.key}
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
                  checked={isChecked(c.key)}
                  onChange={() => toggle(c.key)}
                  style={{ accentColor: "var(--gold)" }}
                />
                <span>{c.label}</span>
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
