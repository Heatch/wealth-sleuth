# Portfolio Tracker — Style Guide

A modern, minimal, free-flowing visual language for a personal portfolio
tracker. Built to feel calm and precise — like a well-kept ledger, not a
SaaS dashboard. Every rule below exists to answer one question: *does this
help someone read their numbers faster and trust them more?*

---

## 1. Color

Six named colors. No others should be introduced without a reason.

| Token | Hex | Light role | Dark role |
|---|---|---|---|
| `--bg` | `#efefed` (light) / `#161615` (dark) | Page canvas | Page canvas |
| `--ink` | `#181818` (light) / `#efefed` (dark) | Primary text | Primary text |
| `--ink-soft` | `#6f6e6b` (light) / `#9b9a96` (dark) | Secondary text, labels, timestamps | same role |
| `--gold` | `#b8863c` (light) / `#d3a35c` (dark) | Brand accent — active nav, focus ring, primary buttons, the hero sparkline | same role |
| `--moss` | `#4c7a52` (light) / `#71a877` (dark) | **Gains only.** Never decorative. | same role |
| `--brick` | `#a1483f` (light) / `#c97364` (dark) | **Losses only.** Never decorative. | same role |

**Rules:**
- Gold is the *only* color used for interactive/brand emphasis. Moss and
  brick are reserved strictly for numeric direction (up/down) — never use
  them for buttons, links, or nav state, or the eye stops trusting them as
  signals.
- No pure black and no pure white anywhere, in either mode.
- No gradients as decoration. A gradient may only appear as a chart fill
  (e.g. fading to transparent under a line), never on a background, card,
  or button.
- No shadows. Depth is expressed with a ~4–6% tone shift, never
  `box-shadow`.

## 2. Type

Two typefaces, doing clearly different jobs — not one for headings and one
for body "because that's how it's done," but because numbers and prose
need different treatment.

- **Fraunces** (serif, variable optical size) — reserved *only* for large
  standalone figures: the hero portfolio total, and section totals.
  Nowhere else. It should feel rare, not decorative.
- **Archivo** (grotesk) — everything else: nav, labels, body copy, table
  content. Use `font-variant-numeric: tabular-nums` anywhere numbers stack
  vertically (holdings list, tables) so digits align.

**Scale** (desktop):

| Use | Size | Weight | Family |
|---|---|---|---|
| Hero total | 56px | 400, italic-optical | Fraunces |
| Section total | 28px | 400 | Fraunces |
| Section heading | 15px | 600 | Archivo |
| Body / table | 14px | 400–500 | Archivo |
| Micro-label | 12px | 500 | Archivo |

**Avoid:** all-caps labels, tracked-out eyebrow text above headings,
bolding/italicizing a single word inside a sentence for "punch," middle-dot
separated meta strings (`A · B · C`), arrows appended to button labels
(`View →`).

## 3. Spacing & shape

- Spacing scale: `4 · 8 · 12 · 20 · 32 · 48 · 72px`. Nothing outside it.
- Radius scale: `0` (default — most things have square corners), `4px`
  (small interactive elements), `999px` (pills — toggle switch, tags).
  Nothing gets an arbitrary 12–16px "SaaS card" radius.
- **No card grid.** Content lives directly on the canvas, separated by
  whitespace and tone, not by boxes with borders and shadows around every
  section.
- Where a hairline is genuinely useful (rarely), use `--ink` at 8% opacity,
  1px, and only on one edge — never a full boxed border.

## 4. Motion

One deliberate moment, not motion on everything:
- Charts draw themselves in on first load (stroke animates from 0 to full
  length over ~900ms, ease-out). This happens once.
- Hover/interaction feedback (row highlight, toggle) is instant or near
  ("120ms ease"), not a fade-and-slide.
- Respect `prefers-reduced-motion`: skip the draw-in, keep hover instant.

## 5. Charts

Hand-built SVG, not a stock chart-library look:
- Lines: smooth cubic bezier curves, single stroke color (usually gold),
  1.5–2px weight, no point markers.
- Area fills: a single color fading to transparent, ~12% max opacity.
- Allocation: a stroke-based donut (arcs via `stroke-dasharray`) with
  **rounded line caps** — soft, not a hard-edged pie.
- No gridlines. No legends when a direct label will do. Axis labels are
  minimal and only where genuinely needed to read the chart.

## 6. Voice

- Buttons say what they do: "Add holding," not "Submit."
- Empty states are an invitation, not an apology: "No holdings yet — add
  your first one." Never "Oops, nothing here!"
- Numbers speak for themselves. Don't caption a chart that already has an
  axis; don't label a section "Overview" above content that's obviously an
  overview.

## 7. Suggested libraries (free, React)

| Need | Pick | Why |
|---|---|---|
| Unstyled accessible components (dialogs, dropdowns, popovers, tooltips) | **Radix Primitives** or **shadcn/ui** (built on Radix) | Ships behavior, not opinionated visuals — you skin it with the tokens above instead of fighting a default theme. |
| Charts | **visx** (D3 primitives for React) if you want the hand-built look above; **Recharts** if you want to ship faster and are OK restyling its defaults | visx gives full control over curve, cap style, and fill — closer to section 5. Recharts is quicker but reads more "default dashboard" out of the box. |
| Icons | **Lucide** (if you want icons at all) | Simple line icons, no filled/duotone style. Consider skipping icons in nav entirely — text + the gold accent is enough, per this guide's minimal-lines approach. |
| Animation | **Motion (Framer Motion)**, used sparingly per section 4 | Don't add it to every hover — reserve it for the one load-in moment. |

## 8. What to avoid (current "AI-generated" tells)

Keeping this list visible so future changes don't drift back toward it:
1. Warm cream background + high-contrast serif headline + terracotta
   accent (`#D97757`-adjacent). This guide deliberately uses a cooler grey
   canvas and gold instead of clay/terracotta.
2. Near-black background with one neon accent.
3. Identical rounded cards, all with the same soft grey shadow.
4. Tracked-out ALL-CAPS eyebrows, middle-dot meta strings, `→` on every
   button, monospace for small data labels.
5. Fade-and-slide-up entrance on every section, hover-lift on every card.
