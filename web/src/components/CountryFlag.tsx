import * as FlagIcons from "country-flag-icons/react/3x2";

interface Props {
  country: string | null | undefined;
  size?: number;
}

// Map common full country names (as stored in the DB / returned by yfinance)
// to ISO 3166-1 alpha-2 codes used by country-flag-icons.
const NAME_TO_CODE: Record<string, string> = {
  canada: "CA",
  "united states": "US",
  "united states of america": "US",
  usa: "US",
  "united kingdom": "GB",
  uk: "GB",
  germany: "DE",
  france: "FR",
  japan: "JP",
  china: "CN",
  australia: "AU",
  switzerland: "CH",
  india: "IN",
  brazil: "BR",
  mexico: "MX",
  italy: "IT",
  spain: "ES",
  netherlands: "NL",
  sweden: "SE",
  norway: "NO",
  denmark: "DK",
  finland: "FI",
  ireland: "IE",
  belgium: "BE",
  austria: "AT",
  singapore: "SG",
  "hong kong": "HK",
  "south korea": "KR",
  "south africa": "ZA",
  russia: "RU",
  israel: "IL",
  "new zealand": "NZ",
  taiwan: "TW",
  poland: "PL",
  turkey: "TR",
  thailand: "TH",
  indonesia: "ID",
  malaysia: "MY",
  philippines: "PH",
  portugal: "PT",
  greece: "GR",
  czechia: "CZ",
  hungary: "HU",
  romania: "RO",
  chile: "CL",
  colombia: "CO",
  peru: "PE",
  argentina: "AR",
  egypt: "EG",
  nigeria: "NG",
  kenya: "KE",
  morocco: "MA",
  pakistan: "PK",
  bangladesh: "BD",
  vietnam: "VN",
  uae: "AE",
  "united arab emirates": "AE",
  "saudi arabia": "SA",
  qatar: "QA",
  kuwait: "KW",
  bahrain: "BH",
  oman: "OM",
  jordan: "JO",
  lebanon: "LB",
  cyprus: "CY",
  malta: "MT",
  luxembourg: "LU",
  slovakia: "SK",
  slovenia: "SI",
  croatia: "HR",
  bulgaria: "BG",
  serbia: "RS",
  ukraine: "UA",
  kazakhstan: "KZ",
  global: "UN",
  international: "UN",
  worldwide: "UN",
};

function resolveCode(country: string | null | undefined): string | null {
  if (!country) return null;
  const normalized = country.trim().toLowerCase();
  if (NAME_TO_CODE[normalized]) return NAME_TO_CODE[normalized];
  // Already a 2-letter ISO code?
  if (/^[a-zA-Z]{2}$/.test(country.trim())) return country.trim().toUpperCase();
  return null;
}

function FallbackFlag({ code, size }: { code: string; size: number }) {
  const h = Math.round((size * 2) / 3);
  return (
    <svg
      width={size}
      height={h}
      viewBox="0 0 18 12"
      className="shrink-0"
      aria-label={code}
      role="img"
    >
      <rect x="0" y="0" width="18" height="12" fill="color-mix(in srgb, var(--ink) 14%, transparent)" />
      <text
        x="9"
        y="9"
        textAnchor="middle"
        fill="var(--ink-soft)"
        fontSize="6"
        fontWeight="600"
        fontFamily="system-ui, sans-serif"
      >
        {code}
      </text>
    </svg>
  );
}

export default function CountryFlag({ country, size = 16 }: Props) {
  const code = resolveCode(country);
  if (!code) {
    return <FallbackFlag code="??" size={size} />;
  }
  const FlagComponent = (FlagIcons as Record<string, React.ComponentType<any> | undefined>)[code];
  if (!FlagComponent) {
    return <FallbackFlag code={code} size={size} />;
  }
  // country-flag-icons 3:2 flags use viewBox "0 0 513 342", so height is 2/3
  // of width. Setting both explicitly avoids any SVG stretching/distortion.
  const h = Math.round((size * 2) / 3);
  return (
    <FlagComponent
      width={size}
      height={h}
      style={{ display: "inline-block", flexShrink: 0, filter: "saturate(0.88) contrast(0.95)" }}
      aria-label={country || code}
      title={country || code}
    />
  );
}
