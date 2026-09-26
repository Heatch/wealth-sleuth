import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import type { AllocationDimension, AllocationFilter, Holding } from "../lib/types";
import { toggleAllocationFilter } from "../lib/allocation";

const PALETTE = [
  "var(--gold)",
  "var(--moss)",
  "var(--brick)",
  "#8c8c8c",
  "#d3a35c",
  "#71a877",
  "#c97364",
  "#6f6e6b",
  "#b8863c",
  "#4c7a52",
  "#a1483f",
  "#9b9a96",
];

function fmtMoney(v: number): string {
  return `$${v.toLocaleString("en-CA", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function groupBy(holdings: Holding[], key: AllocationDimension) {
  const map = new Map<string, number>();
  for (const h of holdings) {
    if (!h.current_value) continue;
    const val = h[key] ?? "Unknown";
    map.set(val, (map.get(val) || 0) + h.current_value);
  }
  return Array.from(map.entries())
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);
}

interface PieProps {
  title: string;
  data: { name: string; value: number }[];
  dimension: AllocationDimension;
  activeValues: Set<string>;
  onSlice: (dimension: AllocationDimension, value: string) => void;
}

function AllocationPie({ title, data, dimension, activeValues, onSlice }: PieProps) {
  if (!data.length) {
    return (
      <div className="flex flex-col" style={{ height: 220 }}>
        <div className="mb-2 text-xs font-medium" style={{ color: "var(--ink-soft)" }}>{title}</div>
        <div className="flex-1 text-xs" style={{ color: "var(--ink-soft)" }}>No data</div>
      </div>
    );
  }

  const total = data.reduce((s, d) => s + d.value, 0);

  return (
    <div className="flex flex-col" style={{ height: 280 }}>
      <div className="mb-2 text-xs font-medium" style={{ color: "var(--ink-soft)" }}>{title}</div>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            cx="50%"
            cy="50%"
            innerRadius={50}
            outerRadius={80}
            paddingAngle={2}
            onClick={(entry: any) => {
              const value = entry?.name;
              if (value) onSlice(dimension, String(value));
            }}
            style={{ cursor: "pointer" }}
          >
            {data.map((entry, index) => (
              <Cell
                key={`cell-${dimension}-${entry.name}`}
                fill={PALETTE[index % PALETTE.length]}
                stroke="none"
                opacity={activeValues.size === 0 || activeValues.has(entry.name) ? 1 : 0.35}
              />
            ))}
          </Pie>
          <Tooltip
            formatter={(value: any, name: any) => {
              const num = typeof value === "number" ? value : 0;
              const pct = total ? (num / total) * 100 : 0;
              return [`${fmtMoney(num)} (${pct.toFixed(1)}%)`, name];
            }}
            contentStyle={{
              background: "var(--bg)",
              border: "1px solid color-mix(in srgb, var(--ink) 12%, transparent)",
              borderRadius: 4,
              fontSize: 12,
            }}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

interface Props {
  holdings: Holding[] | undefined;
  filters: AllocationFilter[];
  onFilters: (filters: AllocationFilter[]) => void;
}

export default function AllocationSection({ holdings, filters, onFilters }: Props) {
  const sectorData = groupBy(holdings ?? [], "sector");
  const countryData = groupBy(holdings ?? [], "country");

  const activeByDimension = (dim: AllocationDimension) =>
    new Set(filters.filter((f) => f.dimension === dim).map((f) => f.value));

  const handleSlice = (dimension: AllocationDimension, value: string) => {
    onFilters(toggleAllocationFilter(filters, dimension, value));
  };

  return (
    <div>
      {filters.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
          <span style={{ color: "var(--ink-soft)" }}>Filtered by</span>
          {filters.map((f) => (
            <span
              key={`${f.dimension}-${f.value}`}
              className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs"
              style={{ background: "color-mix(in srgb, var(--gold) 18%, transparent)", color: "var(--ink)" }}
            >
              <span style={{ fontWeight: 600 }}>{f.dimension === "sector" ? "Sector" : "Country"}</span>
              : {f.value}
              <button
                onClick={() => handleSlice(f.dimension, f.value)}
                aria-label={`Remove ${f.dimension} ${f.value}`}
                className="ml-1 leading-none"
              >
                ×
              </button>
            </span>
          ))}
          <button
            onClick={() => onFilters([])}
            className="rounded px-2 py-0.5 text-xs"
            style={{ background: "color-mix(in srgb, var(--brick) 12%, transparent)", color: "var(--brick)" }}
          >
            Clear all
          </button>
        </div>
      )}
      <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
        <AllocationPie
          title="By Sector"
          data={sectorData}
          dimension="sector"
          activeValues={activeByDimension("sector")}
          onSlice={handleSlice}
        />
        <AllocationPie
          title="By Country"
          data={countryData}
          dimension="country"
          activeValues={activeByDimension("country")}
          onSlice={handleSlice}
        />
      </div>
    </div>
  );
}
