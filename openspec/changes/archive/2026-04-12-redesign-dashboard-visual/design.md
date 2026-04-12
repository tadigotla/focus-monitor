## Context

Today's dashboard ([focusmonitor/dashboard.py](focusmonitor/dashboard.py), 427 lines) is a single Python file with an inline `HTML_TEMPLATE = """..."""` string and a `build_dashboard()` function that does string-level `html.replace("PLACEHOLDER", value)` substitutions. It serves a dark theme with DM Sans / JetBrains Mono font declarations (which quietly fall back to system fonts since no web fonts are actually loaded), a four-card top grid (focus score, analyses, nudges, top apps), a linear timeline list, a discovered-activities section, and a recent-nudges section. It works, but it reads as a developer debug view, not a daily-use tool.

The user explicitly wants it to look and feel like Rize (https://rize.io — personal time-tracker, paid product, closest peer in domain and single-user focus): light theme first, airy, soft neutrals, single accent color used sparingly, system fonts, intentional information density. This is the first of a two-step redesign; the second step (`add-dashboard-plan-management`) will add CSRF-hardened write endpoints and HTMX-backed inline forms for plan management, built *on top of* the design system this change introduces.

The two steps are deliberately separated because they have very different risk profiles: a visual reskin is trivially reversible and touches only HTML/CSS, whereas write endpoints cross a security boundary and require real hardening. Landing them together would produce one diff with two unrelated review axes. Landing them separately means Change 1 ships the entire visual win even if Change 2 is delayed or scoped down.

This design document covers Change 1 only. Change 2 is referenced where it affects decisions (e.g., naming of render helpers that Change 2 will reuse) but is otherwise out of scope.

## Goals / Non-Goals

**Goals:**

- Reskin the dashboard in the visual language of Rize's daily summary: light theme, airy, neutral surfaces, single muted accent, soft shadows, generous whitespace, tabular numbers, system fonts.
- Introduce a design-tokens layer (CSS custom properties) so colors, spacing, radii, type scale, and shadows can be overridden in one place — for the dark variant now, and for any future theming.
- Introduce dark mode as a `prefers-color-scheme: dark` override of the same custom properties. No manual toggle, no new config key, no dual templates.
- Replace the fragile `html.replace(...)` placeholder pattern with `string.Template` (stdlib, no new deps), and split `build_dashboard()` into small `render_*` helpers so Change 2 can reuse them when it swaps cards for HTMX endpoints.
- Replace the text-list "Timeline" section with an inline-SVG horizontal timeline strip, rendered server-side, colored by focus-score buckets.
- Preserve every existing read behavior exactly as it is today: port binding, auto-refresh, empty-state handling, discovered-activities rendering, nudge rendering, score-bucket coloring semantics. If a user can't tell the data is the same, the change is broken.
- Keep everything in `focusmonitor/dashboard.py`. No new files, no premature module split, no new directories.
- Maintain strict stdlib-only posture. No web fonts, no CDN, no new Python packages, no `pip install` anything.

**Non-Goals:**

- **No write endpoints.** Everything stays read-only. Plan management is Change 2.
- **No HTMX.** Change 2 introduces it. Change 1 does not load any JavaScript.
- **No charts beyond the timeline strip.** No Chart.js, no sparklines on the score card, no histograms. The timeline SVG is the only dynamic visual. Sparklines are a tempting follow-up but not in scope.
- **No framework.** No Alpine, no Preact, no React, no build step. Python emits HTML, browser renders it. That's the stack.
- **No component model beyond "a function that returns a string fragment."** If `render_*` grows teeth, we'll introduce structure. Not yet.
- **No accessibility audit.** Baseline only: semantic HTML (`<header>`, `<main>`, `<section>`, `<h1>`/`<h2>`), keyboard focus rings that aren't removed, color contrast good enough to pass a rough eyeball check. Full WCAG AA compliance is a separate initiative.
- **No mobile layout.** Desktop-first. The grid collapses gracefully down to ~1024px; below that is out of scope — the dashboard is something you open on your Mac, not your phone.
- **No i18n, no RTL.** English only, LTR only.
- **No new config keys.** The dashboard reads the same `dashboard_port` and `dashboard_refresh_sec` it reads today.
- **No time-range math beyond existing queries.** The "Today / Yesterday / Last 7 days" toggle is scoped such that the default view is Today (what the current dashboard shows). The other two options re-scope the SQLite queries by date. No multi-day aggregation that doesn't already exist — if the current code path can't produce it with one more parameter, it's out of scope for this change.
- **No accessibility for screen readers beyond `aria-label` on the score card and the toggle.** We'll do the obvious things, not the exhaustive things.
- **No tests for pixel-level rendering.** Visual QA is eyeball-based; only *structural* rendering (key sections present, placeholders resolved, empty-state markup) is covered by automated tests.

## Decisions

### Decision 1: Light theme as default, dark via `prefers-color-scheme`

**Chosen:** CSS custom properties declared in `:root` with the light palette. A `@media (prefers-color-scheme: dark)` block overrides the same properties with dark values. All component CSS references `var(--color-*)` — never hardcoded hex.

**Why:** Rize is light-first, the user explicitly confirmed light default. Dark users get a readable fallback automatically without a separate template or a config key. One source of truth for both themes. Zero runtime logic — the browser picks the palette based on OS setting and applies it at parse time.

**Alternatives considered:**

- **Manual toggle with a `theme` config key and `<button>` in the header.** More flexible but introduces state that has to live somewhere (localStorage? config file? server-side?), and a toggle with a persistence question is a surprising amount of work for what's essentially an OS preference. Deferred until someone asks.
- **Dark theme only, reused from the current file.** Was the status quo. User explicitly rejected it.
- **A light/dark toggle sent via `Cookie` header.** Same problem as the toggle, plus cookies are net-new surface area for a read-only server.

### Decision 2: CSS custom properties as the design-tokens layer

**Chosen:** all colors, spacing, radii, font sizes, font weights, and shadows declared as `--token-*` variables in a single `:root` block at the top of the `<style>` section. Component rules use `var(--...)` exclusively. The dark-mode block is the only other place tokens are set.

**Why:**

- One place to change a color and see it everywhere.
- Dark mode is implemented as property re-declaration, which is cheap and correct.
- Change 2 (plan management) can reuse the tokens for form styles without re-discovering them.
- No preprocessor (Sass/Less) needed — custom properties are native CSS and supported by every browser the user could plausibly have.

**Token categories** (full list is in specs/dashboard-server/spec.md):

```
--color-bg, --color-surface, --color-surface-raised,
--color-border, --color-text, --color-text-muted, --color-text-subtle,
--color-accent, --color-accent-hover,
--color-score-good, --color-score-mid, --color-score-bad,
--color-distraction, --color-planned,

--space-1 .. --space-8   (4px base unit, geometric)
--radius-sm/md/lg        (4 / 8 / 12 px)
--shadow-sm/md           (1-2px subtle, neutral tint)
--font-size-xs .. --font-size-5xl
--font-weight-regular/medium/semibold
--font-family-sans       (system stack)
```

**Alternatives considered:**

- **Tailwind.** Requires a build step. Rejected — that moves us to Option B/C from the exploration and fundamentally changes what kind of project this is.
- **Sass with variables.** Requires compiling. Same objection.
- **Inline color values.** What we have today. The reason we're moving away from it.

### Decision 3: `string.Template` over `html.replace()` chains

**Chosen:** switch the top-level `build_dashboard()` to use `string.Template` (from `string` in the stdlib) with `$name` placeholders. The HTML template becomes a `Template` instance at module load. Substitution is a single `template.substitute({...})` call with a dict produced by the `render_*` helpers.

**Why:**

- Named placeholders over positional `replace()` chains — less fragile when adding a new card.
- Stdlib, no new runtime dep, no performance question.
- Forces us to list every placeholder name up front, so missing values fail fast at substitution time with a readable error rather than quietly leaving a literal `TOP_APPS_HTML` in the page.
- `string.Template` is deliberately simple — no logic in templates, no loops, no conditionals. Logic stays in Python. This matches the current style and keeps the template readable.

**Alternatives considered:**

- **Jinja2.** Would give us loops, conditionals, filters, template inheritance. Tempting but it's a new third-party dep (via `pip install`) which conflicts with the stdlib-first stance in CLAUDE.md. Not justified for a single-file, single-page dashboard.
- **f-strings at render time.** Tempting for small fragments but ugly for a 200-line HTML blob, and easy to accidentally inject data without escaping. Keeping a strict `string.Template` boundary around the shell, and building fragments via small helper functions that HTML-escape their inputs, is safer.
- **Keep `html.replace()`.** The thing we're moving away from.

### Decision 4: Split `build_dashboard` into `render_*` helpers — but keep one file

**Chosen:** extract card-level rendering into module-level helpers: `render_header`, `render_score_card`, `render_timeline`, `render_planned_card`, `render_discovered_card`, `render_apps_card`, `render_nudges_card`. Each takes typed inputs (already-queried DB rows, parsed JSON, etc.) and returns an HTML fragment string. `build_dashboard` becomes a thin orchestrator that queries the DB once, calls each `render_*` in order, and substitutes the fragments into the template.

Keep everything in one file. No `focusmonitor/dashboard/` subpackage. No `templates/` directory.

**Why:**

- Each helper is independently testable (structural assertions on the returned fragment).
- Change 2 will replace `render_planned_card` and `render_discovered_card` with HTMX-driven variants. Having them as named functions makes that a surgical swap rather than a rewrite of the monolith.
- The file will grow to ~700-800 lines. That is still comfortably readable for a single-maintainer project and does not justify a directory split.
- Keeping it in one file means the privacy-review skill can see the entire dashboard surface at a glance.

**Alternatives considered:**

- **Premature package split (`focusmonitor/dashboard/__init__.py`, `server.py`, `templates.py`, `render.py`).** Would be overkill for this file size and make the diff harder to review. Revisit if the file grows past ~1200 lines.
- **A single monolithic `build_dashboard` (status quo).** Doesn't scale to Change 2 and makes testing harder.

### Decision 5: Inline SVG timeline strip, server-rendered

**Chosen:** a horizontal SVG strip (~100px tall, full container width) where each ~5-minute time bucket is rendered as a colored `<rect>` whose fill comes from the focus-score bucket (`--color-score-good / mid / bad`). Hour tick marks and labels rendered below. No interactivity; hover tooltips are a potential Change 2 addition.

**Why:**

- SVG is just text. No library needed. Python emits it as a string.
- Server-rendered means no client JS, no CDN dependency, no build step.
- Matches the existing rendering model (Python → HTML string → browser). No architectural surprise.
- Rize's timeline strip is one of its most visually distinctive elements and a cheap way to signal "this is the new version."
- Rounding each tick to a 5-minute bucket keeps the SVG DOM small (max ~288 rects per day) and readable.

**Alternatives considered:**

- **Canvas with JS.** Requires JS, requires a drawing pass in the browser, not server-inspectable. Rejected.
- **Chart.js timeline.** Requires a CDN script (network egress → privacy break) or a vendored JS file (unnecessary complexity for what a dozen lines of SVG can do). Rejected.
- **Keep the current text list.** Doesn't match the Rize aesthetic; not a real choice given the stated goal.

### Decision 6: Time-range toggle scoped to existing data paths

**Chosen:** a simple `<div>` of three links (`?range=today`, `?range=yesterday`, `?range=7d`) in the header. The dashboard server handler reads the `range` query param, converts it to a date range, and parameterizes the existing SQLite queries by date instead of the hardcoded `today = datetime.now().strftime("%Y-%m-%d")`. "Today" is the default when no range is specified (matches current behavior).

**Why:**

- Links over a `<select>` or JS-driven control: zero JS, works with the auto-refresh meta-tag, browser history works natively, bookmarkable.
- Reuses the existing date-scoped queries — no new aggregation logic.
- Preserves the "open, glance, close" cadence of the dashboard: the toggle is one click, not a modal or a date picker.

**Alternatives considered:**

- **Date picker.** Overkill for a single-user daily tool.
- **7d aggregation that isn't just three daily queries back-to-back.** Feature creep; out of scope.
- **No toggle at all.** Possible, and we could ship without it. But it's ~20 lines of code and a meaningful UX win, so including it while the area is already being touched is cheaper than doing it as a follow-up.

### Decision 7: System font stack, no web fonts

**Chosen:** `font-family: -apple-system, 'SF Pro Text', 'Inter', system-ui, sans-serif;` on `body`, with `font-feature-settings: "tnum"` (or `font-variant-numeric: tabular-nums`) on any element displaying numbers so columns align.

**Why:**

- The project is macOS-first. `-apple-system` resolves to SF Pro on every supported OS version. Rize itself uses Inter on the web, which sits next in the stack as a fallback if the user has it installed.
- No Google Fonts, no self-hosted webfont files. Google Fonts is a network fetch to `fonts.googleapis.com`, which breaks the privacy invariant. Self-hosting means vendoring font files (KBs of binary) into the repo for a feature that system fonts already handle well.
- The current template declares `'DM Sans'` and `'JetBrains Mono'` but never loads them — they silently fall back today. This change makes the fallback explicit.

**Alternatives considered:**

- **Load Inter via Google Fonts.** Breaks CLAUDE.md network policy. Hard no.
- **Vendor Inter locally.** Could be done but adds ~200KB of binary files to the repo for a marginal aesthetic gain over SF Pro on Mac. Deferred until someone argues it's essential.
- **Keep the (broken) DM Sans declaration.** Pointless.

### Decision 8: Semantic HTML baseline, no full a11y pass

**Chosen:** use `<header>`, `<main>`, `<section>`, `<h1>`, `<h2>`, `<nav>` where they fit. Preserve default focus rings (do not `outline: none`). Give the score card and the time-range toggle `aria-label` attributes so screen readers get a meaningful name. Ensure text-on-surface contrast ratio is at least 4.5:1 (WCAG AA normal text) by eyeballing against a contrast checker during design.

Do not attempt a full WCAG audit, do not add `role` attributes beyond defaults, do not add skip links, do not add ARIA live regions. Those are deferred.

**Why:** getting the baseline right is cheap (it's just using the right HTML tags); getting WCAG AA perfect is expensive and is its own initiative. The cheap wins are in scope; the deep audit is not.

## Risks / Trade-offs

- **Risk: Rize's exact palette is proprietary and we're eyeballing it.** The goal is "in the family of Rize," not "pixel-identical to Rize." We pick neutral, Rize-adjacent tokens and accept that a designer could improve them later. → **Mitigation:** design tokens make any later palette update a single-file edit.

- **Risk: The visual refactor accidentally changes what data is shown.** The whole point is "same data, new look" — if a number is wrong after the redesign, trust in the change collapses. → **Mitigation:** (a) each `render_*` helper has a structural test that asserts the key data fields end up in the rendered fragment; (b) a manual smoke-test task in tasks.md requires running the dashboard before and after and visually confirming the focus score, app names, nudge count, and discovered entries are unchanged.

- **Risk: Dark mode looks worse than light mode because we spent all our design budget on the light version.** Acceptable — light is the default and the primary target. Dark is a "not broken" fallback via `prefers-color-scheme`, not a fully-designed second theme. → **Mitigation:** document that dark is best-effort; do a 2-minute eyeball pass to ensure no unreadable contrast combinations, nothing more.

- **Risk: The SVG timeline is slower to render / larger to serve than the current text list.** At ~288 rects/day it should be ~5KB of string-templated SVG, well within any reasonable page budget. → **Mitigation:** measure the built-HTML size before and after in the smoke test; if the new page is >100KB for a typical day, reconsider.

- **Risk: `string.Template` substitution is stricter than `html.replace()` — missing placeholders will raise.** That's actually a feature (we want them to fail loudly), but a sloppy refactor could ship a dashboard that 500s on load. → **Mitigation:** the test suite covers every placeholder in the new template and catches missing keys via `KeyError` or `template.substitute`'s built-in behavior before ship.

- **Risk: Change 2 reveals that the tokens or helper signatures we chose here don't fit the plan-management UI.** If we get the helper boundaries wrong, Change 2 has to rewrite them, wasting the extraction effort. → **Mitigation:** the render helper signatures are chosen with Change 2 in mind — they take already-loaded data (not raw DB cursors), and they return string fragments (not Response objects), so Change 2 can wrap them in HTMX-swap endpoints without reshaping them. If we got this wrong, we pay in Change 2, not here.

- **Privacy trade-off:** None. No new external calls, no new runtime deps, no new data written anywhere, no new network surface. System fonts instead of web fonts is a strict privacy *improvement* over the status quo (which declares `'DM Sans'` and would have been an egress risk if anyone ever added a `@font-face`). Recording this explicitly per the design-phase privacy rule: this change is net-negative on outbound surface, meaning strictly better.

- **Trade-off: Ships without the management features.** The user has to wait for Change 2 to actually click "Promote" on a discovery. That's the whole point of the split. Acceptable because Change 1 alone is already worth shipping (dashboard looks better) and because conflating the two into one change would be unreviewable.
