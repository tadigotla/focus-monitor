## Why

The current dashboard at [focusmonitor/dashboard.py](focusmonitor/dashboard.py) looks like a developer's debug panel — dark theme, mono-font headings, dense grid of stats, visibly mid-fidelity. It works, but it doesn't feel like a tool the user wants to open every morning. The user wants focus-monitor to feel like a product they'd pay for if it were a paid app: specifically, something visually in the family of Rize (https://rize.io — personal time tracker, similar domain, light-first design, airy, intentional, information-dense without feeling cramped).

This change is the first of a planned two-step redesign:

1. **`redesign-dashboard-visual`** (this change) — purely visual. Same content, same endpoints, same auto-refresh, same read-only posture. New design system, new layout, new feel.
2. **`add-dashboard-plan-management`** (next change, scoped separately) — adds write endpoints (CSRF-hardened) and inline plan-management UI built on top of this change's visual system.

Splitting visual from functional gives us independent review surfaces and an incrementally useful result: even if the plan-management work never ships, the user gets a dashboard that's genuinely nice to look at. The risk shape is also radically different — a reskin touches HTML/CSS only and is trivially reversible; write endpoints cross a security boundary and require careful CSRF/Origin hardening. Landing them together would conflate two risk profiles in one review.

## What Changes

- **Complete visual redesign** of the dashboard in the style of Rize's daily summary view: light theme by default, generous whitespace, system font stack, single accent color used sparingly, rounded corners with subtle shadows, soft/neutral palette.
- **New layout.** Single screen, no sidebar/nav:
  - Header row: "Focus Monitor" branding left, current date + time-range toggle right (Today / Yesterday / Last 7 days — toggle is wired to existing data, no new queries beyond date scoping).
  - Hero row: large focus-score card (big number + delta vs yesterday) + today's timeline strip.
  - Secondary row: Planned Focus card + Discovered Activities card.
  - Tertiary row: Top Apps card + Recent Nudges card.
- **Design tokens as CSS custom properties.** Colors, spacing, radii, type scale, shadows all declared as `--color-*`, `--space-*`, etc. at the top of the stylesheet so the dark variant and any future theming can override them in one place.
- **Dark mode via `prefers-color-scheme`** only — no manual toggle. Light is the default, dark overrides the custom properties. No separate template, no branching logic.
- **System font stack** only (`-apple-system, 'SF Pro Text', 'Inter', system-ui, sans-serif`) with `tabular-nums` for numeric displays. No web fonts, no Google Fonts (that would be a network egress and break the privacy invariant).
- **Inline SVG timeline strip.** Replace the current text-list "Timeline" section with a compact horizontal strip (one segment per ~5-minute block, colored by focus score bucket). Rendered server-side as SVG; no JS, no chart library.
- **Internal refactor (small, scoped):**
  - Switch from `html.replace("PLACEHOLDER", value)` to `string.Template` with named placeholders (stdlib — no new dep).
  - Split `build_dashboard()` into smaller `render_*` helpers (`render_header`, `render_score_card`, `render_timeline`, `render_planned`, `render_discovered`, `render_apps`, `render_nudges`). Keep everything in `dashboard.py` — no premature module split.
- **Preserve all existing read endpoints and auto-refresh behavior** exactly as they are today. No changes to `DashboardHandler`, `start_dashboard_server`, port binding, or refresh-meta-tag semantics.

## Capabilities

### New Capabilities
<!-- None — no new capability is introduced; this is a visual-only modification of an existing one. -->

### Modified Capabilities
- `dashboard-server`: the existing capability already covers "dashboard served over HTTP," "auto-refresh," "discovered activities section," and "local-only binding." This change adds new requirements covering the design system, the layout structure, the light-theme-first visual language, the inline SVG timeline, the time-range toggle, and the font/accessibility baseline. The existing requirements around HTTP serving, refresh, discovered activities, and loopback binding are **preserved unchanged** — only the rendered HTML/CSS is new.

## Impact

- **Code:** [focusmonitor/dashboard.py](focusmonitor/dashboard.py) — the only file meaningfully changed. ~300 net-new lines of HTML/CSS + ~100 lines of Python refactoring. No new files, no new directories.
- **Data:** None. No schema changes, no config keys added, no new files in `~/.focus-monitor/`.
- **Runtime deps:** None. Still Python standard library only. `string.Template` is stdlib; SVG is just strings.
- **External deps / network:** None. No web fonts, no CDN, no npm, no new packages. System fonts only. The network policy in CLAUDE.md is preserved.
- **Privacy posture:** Unchanged. This is a read-only visual redesign of a localhost-only server. No new write endpoints, no new data storage, no new outbound traffic.
- **Tests:** The existing `test_*.py` suite at the repo root does not currently cover the dashboard HTML. This change will add a small `test_dashboard_render.py` that exercises the new `render_*` helpers to verify structural assertions (key sections present, no unresolved template placeholders, empty-state rendering works). No framework — `python3 test_dashboard_render.py` like the rest of the suite.
- **Backwards compatibility:** No user-facing compatibility surface. The user sees a new-looking page on next refresh. No URL changes, no config keys to migrate, no data format changes.
- **Follow-up:** `add-dashboard-plan-management` will depend on the design tokens, card layout, and `render_*` helpers introduced here. That change is scoped separately and does not ship with this one.
