import type { AllocationDimension, AllocationFilter, Holding } from "./types";

export const ALLOCATION_DIMENSIONS: AllocationDimension[] = ["sector", "country"];

/**
 * Test whether a holding matches every active allocation filter.
 *
 * Multiple values within the same dimension are OR-ed (e.g. two selected
 * sectors both pass). Values across different dimensions are AND-ed (e.g.
 * selecting a sector and a country requires both to match).
 */
export function matchesAllocationFilters(
  holding: Holding,
  filters: AllocationFilter[]
): boolean {
  if (!filters.length) return true;

  const byDimension: Record<AllocationDimension, Set<string>> = {
    sector: new Set(),
    country: new Set(),
  };

  for (const f of filters) {
    byDimension[f.dimension].add(f.value);
  }

  for (const dim of ALLOCATION_DIMENSIONS) {
    const allowed = byDimension[dim];
    if (!allowed.size) continue;
    const value = holding[dim] ?? "Unknown";
    if (!allowed.has(value)) return false;
  }

  return true;
}

/**
 * Toggle a filter value in a list. Returns a new list.
 */
export function toggleAllocationFilter(
  filters: AllocationFilter[],
  dimension: AllocationDimension,
  value: string
): AllocationFilter[] {
  const idx = filters.findIndex((f) => f.dimension === dimension && f.value === value);
  if (idx >= 0) {
    return [...filters.slice(0, idx), ...filters.slice(idx + 1)];
  }
  return [...filters, { dimension, value }];
}
