# Design System — MyTrade v1

> **Status:** Single Source of Truth for all visual decisions.
> Every UI file references this document. Changes here propagate to code via CSS variables.

---

## Branding

- **Name:** MyTrade
- **Wordmark:** "MyTrade" in Geist Semi-Bold, with gold accent on "Trade"
- **Tagline:** "AI-Powered Decision Support" (auth pages only)
- **Tone:** Competent, trustworthy, data-driven. Not playful, not corporate-cold.

---

## Color Palette

All colors as HSL values. Applied via CSS custom properties in `globals.css`.

| Token | Light Mode | Dark Mode | Usage |
|-------|-----------|-----------|-------|
| `--background` | `0 0% 99%` | `222 47% 6%` | Page background |
| `--foreground` | `222 47% 11%` | `210 20% 93%` | Primary text |
| `--card` | `0 0% 100%` | `222 47% 9%` | Card surfaces |
| `--card-foreground` | `222 47% 11%` | `210 20% 93%` | Card text |
| `--primary` | `222 47% 18%` | `210 20% 86%` | Deep navy / light text |
| `--primary-foreground` | `0 0% 100%` | `222 47% 11%` | Text on primary |
| `--accent` | `38 92% 50%` | `38 92% 55%` | Warm gold (CTAs, active nav) |
| `--accent-foreground` | `222 47% 11%` | `222 47% 11%` | Text on gold |
| `--muted` | `210 20% 96%` | `222 30% 14%` | Subtle backgrounds |
| `--muted-foreground` | `220 13% 46%` | `215 15% 55%` | Secondary text |
| `--border` | `220 13% 91%` | `222 30% 18%` | Borders, dividers |
| `--input` | `220 13% 91%` | `222 30% 18%` | Input borders |
| `--ring` | `222 47% 18%` | `38 92% 55%` | Focus rings (navy light / gold dark) |
| `--destructive` | `0 72% 51%` | `0 72% 60%` | Destructive actions |
| `--verified` | `152 60% 40%` | `152 60% 50%` | Green: verified, profit |
| `--disputed` | `0 72% 51%` | `0 72% 60%` | Red: disputed, loss |
| `--unverified` | `45 95% 48%` | `45 95% 53%` | Amber: unverified, warning |
| `--sidebar-background` | `222 47% 12%` | `222 47% 5%` | Dark navy sidebar (both modes) |
| `--sidebar-foreground` | `210 20% 86%` | `210 20% 86%` | Sidebar text (both modes) |
| `--sidebar-accent` | `38 92% 50%` | `38 92% 55%` | Gold active item |
| `--sidebar-accent-foreground` | `0 0% 100%` | `0 0% 100%` | Text on active item |
| `--sidebar-border` | `222 30% 18%` | `222 30% 12%` | Sidebar dividers |

> **Amber vs Gold:** `--unverified` (Hue 45) is distinct from `--accent` (Hue 38) so warning badges are never confused with CTA elements.

---

## Typography

- **Font stack:** Geist (sans) + Geist Mono (mono) — shipped via `geist` npm package
- **Loading:** `next/font/local` with `variable` option, applied as CSS custom properties

### Type Scale

| Token | Size/Line | Weight | Usage |
|-------|-----------|--------|-------|
| `h1` | 28px / 36px | Semi-Bold (600) | Page titles |
| `h2` | 22px / 28px | Semi-Bold (600) | Section headers |
| `h3` | 18px / 24px | Medium (500) | Card titles |
| `body` | 14px / 20px | Regular (400) | Default text |
| `caption` | 12px / 16px | Regular (400) | Timestamps, secondary |
| `mono` | 14px / 20px | Regular (400) | Financial data |

### Financial Numbers

- ALWAYS use Geist Mono (`font-mono`)
- ALWAYS `tabular-nums` for alignment
- ALWAYS right-aligned in tables
- Profit: green (`--verified`), Loss: red (`--disputed`)
- Percentages include `%` suffix, currencies include `$` prefix

---

## Spacing & Layout

| Property | Value |
|----------|-------|
| Page padding | 16px mobile, 24px desktop |
| Card padding | 16px inner |
| Card gap | 12px between cards |
| Sidebar width | 256px expanded, 48px icon-only |
| Bottom nav height | 56px, fixed |
| Max content width | 1200px (centered on wide screens) |
| Border radius (cards) | 8px (`rounded-lg`) |
| Border radius (buttons/inputs) | 6px (`rounded-md`) |
| Border radius (badges) | 9999px (`rounded-full`) |

### Breakpoints

| Name | Width | Behavior |
|------|-------|----------|
| Mobile | < 768px | Bottom nav, no sidebar, single column |
| Tablet/Desktop | ≥ 768px | Sidebar visible, multi-column |
| Wide | ≥ 1280px | Content centered at max-width |

---

## Component Patterns

### Cards
- Light: `shadow-sm`, no border emphasis
- Dark: `border` visible, no shadow
- Never use `shadow-lg` or `shadow-xl`

### Buttons
- **Primary:** Navy background + white text
- **Accent:** Gold background + navy text (CTAs)
- **Ghost:** Transparent, subtle hover
- **Destructive:** Red background (kill-switch, delete)

### Badges (Verification Status)
| Status | Color | Icon | Shape |
|--------|-------|------|-------|
| `verified` / `consistent` | Green (`--verified`) | CheckCircle | Pill |
| `unverified` | Amber (`--unverified`) | AlertTriangle | Pill |
| `disputed` | Red (`--disputed`) | XCircle | Pill |
| `manual_check` | Amber (`--unverified`) | Eye | Pill |

### Badges (Recommendation)
| Level | Color |
|-------|-------|
| STRONG BUY / BUY | Green |
| HOLD | Muted |
| SELL / STRONG SELL | Red |

### Inputs
- Subtle border, rounded-md
- Focus ring: navy (light mode), gold (dark mode)

### Tables
- Zebra striping on rows
- Sticky header
- Monospace numbers, right-aligned
- Sortable columns (Step 13+)

### Loading States
- Skeleton shimmer (rounded rect pulse)
- Cards: full card skeleton
- Tables: row-by-row skeleton
- Never use spinners

### Empty States
- Centered text with muted icon
- Actionable guidance ("Start your first analysis")

---

## Motion

| Trigger | Duration | Easing |
|---------|----------|--------|
| Hover, focus | 150ms | ease-out |
| Expand/collapse | 200ms | ease-out |
| Number change | opacity transition | ease-in-out |

- No bounce, no spring, no flashy animations.

---

## Icons

- **Set:** Lucide (ships with shadcn)
- **Sizes:** 16px inline, 20px nav, 24px page actions
- **Style:** Outline, `stroke-width: 1.75`

---

## Anti-Patterns (NEVER)

- No purple/blue gradients
- No Inter/Roboto font
- No `shadow-lg` or `shadow-xl` on cards
- No spinner/loading-circle (use skeletons)
- No emojis as status indicators
- No cookie-cutter card grids with no hierarchy
- No oversized padding with sparse data
- No generic dashboard templates

---

## Referenzen
- Frontend Design Skill: `.claude/skills/frontend-design`
- shadcn/ui: Component library (check MCP before custom)
- Lucide: Icon set
