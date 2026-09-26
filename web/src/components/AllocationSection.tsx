import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import type { AllocationDimension, AllocationFilter, Holding } from "../lib/types";

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
  activeValue: string | null;
  onSlice: (dimension: AllocationDimension, value: string) => void;
}

function AllocationPie({ title, data, dimension, activeValue, onSlice }: PieProps) {
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
                opacity={activeValue === null || activeValue === entry.name ? 1 : 0.35}
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
  filter: AllocationFilter | null;
  onFilter: (filter: AllocationFilter | null) => void;
}

export default function AllocationSection({ holdings, filter, onFilter }: Props) {
  const sectorData = groupBy(holdings ?? [], "sector");
  const countryData = groupBy(holdings ?? [], "country");

  const handleSlice = (dimension: AllocationDimension, value: string) => {
    if (filter && filter.dimension === dimension && filter.value === value) {
      onFilter(null);
      return;
    }
    onFilter({ dimension, value });
  };

  return (
    <div>
      {filter && (
        <div className="mb-4 flex items-center gap-3 text-sm">
          <span style={{ color: "var(--ink-soft)" }}>
            Filtered by{" "}
            <span style={{ color: "var(--ink)", fontWeight: 600 }}>
              {filter.dimension === "sector" ? "Sector" : "Country"}
            </span>
            : {filter.value}
          </span>
          <button
            onClick={() => onFilter(null)}
            className="rounded px-2 py-0.5 text-xs"
            style={{ background: "color-mix(in srgb, var(--gold) 18%, transparent)", color: "var(--ink)" }}
          >
            Clear
          </button>
        </div>
      )}
      <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
        <AllocationPie
          title="By Sector"
          data={sectorData}
          dimension="sector"
          activeValue={filter?.dimension === "sector" ? filter.value : null}
          onSlice={handleSlice}
        />
        <AllocationPie
          title="By Country"
          data={countryData}
          dimension="country"
          activeValue={filter?.dimension === "country" ? filter.value : null}
          onSlice={handleSlice}
        />
      </div>
    </div>
  );
}
