// Display label formatting. The database stores lowercase identifiers;
// these map them to human-readable labels. Unknown values fall back to
// title-casing so new brokerages / account types render sensibly.

const BROKERAGE_LABELS: Record<string, string> = {
  wealthsimple: "Wealthsimple",
  disnat: "Disnat",
  qtrade: "QTrade",
};

const ACCOUNT_LABELS: Record<string, string> = {
  tfsa: "TFSA",
  non_reg: "Non-Reg",
  rrsp: "RRSP",
  resp: "RESP",
  fhsa: "FHSA",
  margin: "Margin",
  general: "General",
};

export function brokerageLabel(id: string): string {
  return (
    BROKERAGE_LABELS[id] ?? id.charAt(0).toUpperCase() + id.slice(1)
  );
}

export function accountLabel(id: string): string {
  if (ACCOUNT_LABELS[id]) return ACCOUNT_LABELS[id];
  return id
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join("-");
}
