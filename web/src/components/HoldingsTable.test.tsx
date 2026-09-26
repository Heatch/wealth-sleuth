import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import HoldingsTable from "./HoldingsTable";
import type { Holding, HoldingsTotals } from "../lib/types";

function makeHolding(overrides: Partial<Holding> = {}): Holding {
  return {
    symbol: "RY",
    name: "Royal Bank",
    brokerage: "disnat",
    account_type: "tfsa",
    asset_class: "stock",
    sector: "Financial Services",
    industry: "Banks",
    country: "Canada",
    currency: "CAD",
    quantity: 10,
    avg_cost: 100,
    book_cost: 1000,
    current_price: 110,
    current_value: 1100,
    market_cap: 100000000,
    trailing_pe: 12.5,
    dividend_yield: 0.04,
    gain: 100,
    gain_pct: 0.1,
    weight: 0.5,
    day_change: null,
    day_change_pct: null,
    ...overrides,
  };
}

const totals: HoldingsTotals = {
  book_cost: 1000,
  current_value: 1100,
  gain: 100,
  gain_pct: 0.1,
};

function countCells(html: string, section: "tbody" | "tfoot" | "thead"): number[] {
  const sectionHtml = html.split(`<${section}>`)[1]?.split(`</${section}>`)[0] ?? "";
  const rows = sectionHtml.split("<tr").slice(1);
  return rows.map((r) => {
    const cells = r.match(/<(td|th)[\s>]/g) ?? [];
    return cells.length;
  });
}

describe("HoldingsTable column alignment", () => {
  it("renders the same number of cells in every row as there are headers", () => {
    const html = renderToStaticMarkup(
      <HoldingsTable
        holdings={[makeHolding(), makeHolding({ symbol: "TD", name: "TD Bank" })]}
        totals={totals}
        sort="value"
        order="desc"
        onSort={() => {}}
        currency="CAD"
        openCards={{}}
        onToggleCard={() => {}}
        onCloseCard={() => {}}
      />
    );
    const headers = countCells(html, "thead");
    const body = countCells(html, "tbody");
    const foot = countCells(html, "tfoot");
    expect(headers).toHaveLength(1);
    expect(body).toHaveLength(2);
    expect(foot).toHaveLength(1);
    for (const n of body) {
      expect(n).toBe(headers[0]);
    }
    expect(foot[0]).toBe(headers[0]);
  });

  it("uses the redesigned column set with gain amount and no sector/country columns", () => {
    const html = renderToStaticMarkup(
      <HoldingsTable
        holdings={[makeHolding({ gain: 123.45 })]}
        totals={totals}
        sort="value"
        order="desc"
        onSort={() => {}}
        currency="CAD"
        openCards={{}}
        onToggleCard={() => {}}
        onCloseCard={() => {}}
      />
    );
    const thead = html.split("<thead>")[1]?.split("</thead>")[0] ?? "";
    for (const label of ["Name", "Symbol", "Shares", "Last price", "Value", "Gain", "Gain %", "Market cap", "P/E", "Div yield", "Weight"]) {
      expect(thead).toContain(label);
    }
    expect(thead).not.toContain("Sector");
    expect(thead).not.toContain("Country");
    // Gain amount renders as money (no percent sign).
    expect(html).toContain("$123.45");
  });

  it("formats dividend yield without a plus sign", () => {
    const html = renderToStaticMarkup(
      <HoldingsTable
        holdings={[makeHolding({ dividend_yield: 0.0099 })]}
        totals={totals}
        sort="value"
        order="desc"
        onSort={() => {}}
        currency="CAD"
        openCards={{}}
        onToggleCard={() => {}}
        onCloseCard={() => {}}
      />
    );
    expect(html).toContain("0.99%");
    expect(html).not.toContain("+0.99%");
  });
});
