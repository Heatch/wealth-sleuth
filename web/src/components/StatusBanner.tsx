interface GapStatus {
  has_gaps: boolean;
  gaps: {
    missing: number[];
    stale: Array<{ id: number; last_date: string }>;
    fx_stale: boolean;
    today: string;
  };
}

interface Props {
  status: GapStatus | undefined;
}

export default function StatusBanner({ status }: Props) {
  if (!status?.has_gaps) return null;

  const total =
    (status.gaps?.missing?.length || 0) + (status.gaps?.stale?.length || 0);

  return (
    <div
      className="mb-4 rounded p-3 text-sm"
      style={{
        background: "color-mix(in srgb, var(--gold) 10%, transparent)",
        color: "var(--ink)",
      }}
    >
      Fetching price data for {total} securit{total === 1 ? "y" : "ies"}...
      <span className="ml-1 animate-pulse">●</span>
    </div>
  );
}
