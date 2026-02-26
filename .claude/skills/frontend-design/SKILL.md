---
name: frontend-design
description: 'Create distinctive, production-grade frontend interfaces for the MyTrade investment dashboard. Activates automatically for UI work. Enforces premium aesthetic, avoids AI slop.'
---
# Frontend Design Skill — MyTrade

Create distinctive, production-grade frontend interfaces that avoid generic "AI slop" aesthetics.
This skill activates automatically when building UI components, pages, or dashboard elements.

## Before Coding: Design Direction

1. **Purpose:** What does this interface element do? (Analysis display? Trade plan? Portfolio view?)
2. **Context:** This is a financial dashboard for a single sophisticated user
3. **Aesthetic:** Premium fintech — think Bloomberg Terminal meets Apple simplicity

## MyTrade Design System

### Typography
- Display/Headers: Use a distinctive serif or geometric sans (NOT Inter, NOT Roboto, NOT Arial)
- Body: Clean, highly readable sans-serif with good number rendering
- Monospace: For financial data, prices, percentages — use a proper monospace with tabular figures
- Financial numbers ALWAYS use tabular figures and right-alignment

### Color Palette
- **Primary:** Deep navy/charcoal as base (trust, authority)
- **Accent:** Warm gold or teal (premium, not generic blue)
- **Semantic:** Green = verified/profit, Red = disputed/loss, Amber = warning/unverified
- **AVOID:** Purple gradients, bright blue CTAs, rainbow dashboards
- Use CSS variables: `--color-primary`, `--color-accent`, `--color-verified`, etc.

### Verification Status (Critical for this app)
```
verified/consistent  → Green badge + solid icon    (✓ Tier A confirmed)
unverified           → Amber badge + outline icon  (⚠ Single source)
disputed             → Red badge + alert icon      (✗ >5% deviation)
manual_check         → Amber badge + eye icon      (👁 Needs human review)
```

### Layout Principles
- Data density is welcome — this is a power-user tool, not a consumer app
- Use card-based layouts with subtle elevation (shadow-sm, not shadow-lg)
- Generous padding inside cards, tight spacing between related cards
- Sidebar navigation (collapsible) + main content area
- Financial data tables: zebra striping, sticky headers, sortable columns

### Motion & Interaction
- Subtle transitions (150-200ms) for state changes
- Loading skeletons for data fetches (not spinners)
- Smooth number animations for real-time data updates
- NO flashy animations, NO bounce effects — this is finance, not a game

### shadcn/ui Component Priority
Before building custom, check shadcn MCP for:
- Table, DataTable (financial data)
- Card (analysis panels)
- Badge (verification status)
- Alert (kill-switch warnings, policy violations)
- Sheet (trade detail sidepanel)
- Tabs (analysis sections)
- Command (quick actions)
- Chart (portfolio visualization — use Recharts via shadcn)

### Dark Mode
- Default: Light mode with dark mode toggle
- Dark mode: True dark (#0a0a0b), not gray (#1a1a1a)
- Financial charts must be readable in both modes
- Use Tailwind `dark:` classes consistently

## Implementation Checklist
- [ ] CSS variables for all colors (theming)
- [ ] Responsive (desktop-first, mobile-functional)
- [ ] Loading states for all async data
- [ ] Error states with actionable messages
- [ ] Empty states with helpful guidance
- [ ] Verification badges on all financial numbers
- [ ] No hardcoded colors — everything via CSS variables or Tailwind config

## Anti-Patterns (AVOID)
- ❌ Generic dashboard templates
- ❌ Inter font everywhere
- ❌ Purple/blue gradient headers
- ❌ Oversized padding with sparse data
- ❌ Emojis as status indicators in production UI
- ❌ Cookie-cutter card grids with no hierarchy
- ❌ Spinners instead of skeletons
- ❌ Alert dialogs for non-critical information

Remember: This is a financial tool for a sophisticated user. Every pixel should convey
competence, trust, and clarity. Claude is capable of extraordinary design work.
