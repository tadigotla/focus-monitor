## 1. Design tokens and stylesheet skeleton

- [x] 1.1 In [focusmonitor/dashboard.py](focusmonitor/dashboard.py), replace the existing `<style>` block with a new one that starts with a `:root { ... }` declaration listing every design token from the specs (color, spacing, radii, shadows, type scale, font family).
- [x] 1.2 Add a `@media (prefers-color-scheme: dark) { :root { ... } }` block that re-declares only the color tokens with dark-palette values.
- [x] 1.3 Pick Rize-adjacent light values: near-white backgrounds, soft neutral borders, slate text, muted blue-green accent (~`#4a9b8e` family), established score-bucket colors (green/amber/red but desaturated from the current values).
- [x] 1.4 Pick dark values that maintain 4.5:1 contrast against surfaces and don't reuse the current near-black `#0e0e12` — land somewhere closer to a soft charcoal so dark mode reads as "considered," not "inverted."
- [x] 1.5 Delete all hardcoded hex values from component CSS rules; every color reference SHALL go through `var(--color-*)`.
- [x] 1.6 Verify: search the stylesheet for `#` — the only matches should be inside the `:root` and `@media` blocks.

## 2. Layout and component CSS

- [x] 2.1 Write base layout CSS: centered max-width container (~1100px), `--space-*` driven gaps, semantic `<header>` / `<main>` / `<section>` targeting.
- [x] 2.2 Write the header rule: project name left (medium weight, muted color), date + range toggle right (smaller, muted).
- [x] 2.3 Write the card rule: white surface, `--radius-lg`, `--shadow-sm`, `--space-6` internal padding, subtle border via `--color-border`.
- [x] 2.4 Write the hero-row grid: two columns, 1fr 2fr (score card small, timeline wide), gap `--space-6`.
- [x] 2.5 Write the primary-row and secondary-row grids: two equal columns, gap `--space-6`, stacks to one column at ~1024px via a single media query.
- [x] 2.6 Write the big-number rule (score card): `--font-size-5xl`, `--font-weight-semibold`, `tabular-nums`, score-bucket color via a modifier class.
- [x] 2.7 Write the card-title rule: `--font-size-sm`, uppercase not required (drop the current uppercase/letterspaced treatment), muted color.
- [x] 2.8 Write the list-row rule for planned/discovered/apps: thin border-bottom only between rows, `--space-3` vertical padding, baseline alignment, tabular numbers on any numeric column.
- [x] 2.9 Write the empty-state rule: italic muted text, centered, `--space-4` padding.
- [x] 2.10 Keep focus rings on interactive elements — do NOT add `outline: none` anywhere.

## 3. Template migration to `string.Template`

- [x] 3.1 Import `string` at the top of [focusmonitor/dashboard.py](focusmonitor/dashboard.py).
- [x] 3.2 Wrap the HTML template string in `string.Template(...)` at module load; name the constant `DASHBOARD_TEMPLATE`.
- [x] 3.3 Rewrite every placeholder in the template from the bare `TOKEN_NAME` form to `$token_name` (snake_case), so `string.Template` recognizes them.
- [x] 3.4 In `build_dashboard`, build a substitution dict with every placeholder and call `DASHBOARD_TEMPLATE.substitute(subs)`. Do NOT use `safe_substitute` — let missing keys raise so the tests catch them.
- [x] 3.5 Delete the now-unused chain of `html.replace("NAME", value)` calls.
- [x] 3.6 Confirm no placeholder remains in the rendered page by grepping the returned string for `$` (should find only any `$` that is part of real content, not template syntax).

## 4. Render helpers

- [x] 4.1 Add module-level `render_header(range_key, date_str)` returning the header HTML fragment including the project name and the three-link time-range toggle; mark the active link with a `current` class.
- [x] 4.2 Add `render_score_card(score, bucket_class, label)` returning the score card fragment.
- [x] 4.3 Add `render_timeline(rows)` returning an inline `<svg>` element (see task group 5).
- [x] 4.4 Add `render_planned_card(planned_tasks, activity_rows)` returning the Planned Focus card fragment. For this change, the card is informational only (no add/edit buttons) — those arrive in Change 2. Each planned task shows a name and a bar whose fill reflects how much of today's activity matched it (derived from existing `activity_log.project_detected`).
- [x] 4.5 Move the existing `_render_discovered_html` rendering into a new `render_discovered_card(activities)` helper; update it to emit the new markup (no pills unless they survive the redesign, new row structure with name + meta + signals + seen line).
- [x] 4.6 Add `render_apps_card(top_apps)` returning the Top Apps card fragment with a tabular duration column.
- [x] 4.7 Add `render_nudges_card(nudge_rows)` returning the Recent Nudges card fragment.
- [x] 4.8 Confirm every helper HTML-escapes untrusted input via `html.escape` before interpolation. The activity name, window titles, and nudge text are the primary vectors.
- [x] 4.9 Confirm no `render_*` helper imports or invokes `sqlite3`.
- [x] 4.10 Refactor `build_dashboard` into a thin orchestrator: query SQLite once, parse JSON files, call each `render_*` in order, and substitute into the template.

## 5. Inline SVG timeline

- [x] 5.1 Design the SVG layout: fixed height (~120px), full container width, one `<rect>` per time bucket. Decide on bucket size — round each `activity_log` row to the nearest 5-minute bucket, accumulating score into whichever bucket the row's timestamp falls into.
- [x] 5.2 Implement `_svg_timeline_rects(rows, range_key)` that returns the `<rect>` elements as a string, colored by score bucket via `fill="var(--color-score-good|mid|bad)"`.
- [x] 5.3 Implement `_svg_timeline_hour_labels(range_key)` that emits `<text>` labels for hour ticks under the rects. For `today`/`yesterday`, label every 2 hours; for `7d`, label days instead of hours.
- [x] 5.4 Wrap both in an `<svg viewBox="...">` container in `render_timeline(rows, range_key)`.
- [x] 5.5 Handle the empty-data case: if `rows` is empty, `render_timeline` returns the empty-state fragment (italic muted message) rather than an empty SVG.
- [x] 5.6 Verify the rendered SVG contains no `<script>` elements and no `on*` event attributes (purely declarative markup).

## 6. Time-range toggle wiring

- [x] 6.1 In `DashboardHandler.do_GET`, parse the `range` query parameter from `self.path` using `urllib.parse.urlsplit` + `parse_qs`. Accept `today`, `yesterday`, `7d`; anything else falls back to `today`.
- [x] 6.2 Pass the resolved `range_key` to `build_dashboard(refresh_sec, range_key)` as a new arg.
- [x] 6.3 In `build_dashboard`, compute the date range (start and end dates as strings) from `range_key` and use them to parameterize the existing SQLite queries that currently hardcode `today = datetime.now().strftime("%Y-%m-%d")`.
- [x] 6.4 Verify: opening `/`, `/?range=today`, `/?range=yesterday`, `/?range=7d`, and `/?range=garbage` all return 200 and render without crashing. The garbage value renders as Today.

## 7. Accessibility baseline

- [x] 7.1 Use `<header>`, `<main>`, `<section>` where appropriate. Give each `<section>` a unique `<h2>` or an `aria-label`.
- [x] 7.2 Add `aria-label="Average focus score"` to the score card's big-number element.
- [x] 7.3 Add `aria-label="Time range"` to the toggle container; mark the current link with `aria-current="page"`.
- [x] 7.4 Check contrast ratios in both light and dark with a contrast tool or eyeball check — every body-text / surface pair must be at least 4.5:1. Adjust tokens if anything falls short.
- [x] 7.5 Do NOT remove default focus rings. Do NOT set `outline: none`.

## 8. Tests (structural)

- [x] 8.1 Create `test_dashboard_render.py` at the repo root following the `python3 test_*.py` convention.
- [x] 8.2 Test: `render_header("today", "Apr 12")` returns a fragment containing the project name, the three toggle links, and an `aria-current="page"` on the Today link.
- [x] 8.3 Test: `render_score_card(82, "good", ...)` returns a fragment containing `82` and the `good` score-bucket class.
- [x] 8.4 Test: `render_timeline([])` returns an empty-state fragment, not a bare `<svg>`.
- [x] 8.5 Test: `render_timeline(fake_rows)` returns a fragment containing at least one `<rect>` with a `fill` referencing a score-bucket CSS variable.
- [x] 8.6 Test: `render_discovered_card(...)` with an activity name containing `<script>` returns an escaped fragment (no raw `<script>`).
- [x] 8.7 Test: `render_discovered_card([])` returns the empty-state fragment.
- [x] 8.8 Test: `render_apps_card([("VS Code", 9000), ("Chrome", 2000)])` returns a fragment where each app name and duration appears.
- [x] 8.9 Test: calling `build_dashboard()` with a fresh temporary SQLite DB returns an HTML string with no unresolved `$placeholder` tokens and no literal `PLACEHOLDER_NAME` leftovers.
- [x] 8.10 Test: calling `build_dashboard()` twice does not raise (sanity check that template substitution is deterministic).
- [x] 8.11 Run all repo-root `test_*.py` files via `python3` to confirm no regressions across existing tests.

## 9. Smoke test (manual, end-to-end)

- [x] 9.1 Start the dashboard server locally via `python3 cli.py run` (or reload the launchd agent via `launchctl kickstart -k gui/$UID/com.focusmonitor.agent`).
- [x] 9.2 Open `http://localhost:9876/` in the user's default browser and visually confirm the header, score card, timeline, planned, discovered, apps, and nudges zones all render.
- [x] 9.3 Cross-reference the numeric values against a parallel run of the current version (either from memory or a git-stashed version) — focus score, analysis count, top apps, discovered count must match within expected variance for the refresh window.
- [x] 9.4 Click the time-range toggle and verify Yesterday and Last 7 days re-query without error.
- [x] 9.5 Flip macOS System Settings → Appearance to Dark, refresh the page, and confirm the dark palette applies via `prefers-color-scheme`. Check that nothing is unreadable.
- [x] 9.6 Disable JavaScript in the browser (or open a curl-only view) and confirm the page still renders fully — no feature is JS-gated.

## 10. Privacy verification

- [x] 10.1 Run the `privacy-review` skill over the diff — expect "no findings" across all four categories.
- [x] 10.2 Grep the new stylesheet and template for `https://`, `http://`, `fonts.googleapis`, `googleapis`, `cdnjs`, `@font-face` — none should appear outside of documentation comments.
- [x] 10.3 Confirm no new Python packages were added (no changes to `requirements.txt` / `setup.py` / `pyproject.toml` dependencies).
- [x] 10.4 Confirm `127.0.0.1` binding is unchanged in `start_dashboard_server`.

## 11. Archive

- [x] 11.1 After implementation, tests, and smoke test pass, run the `openspec-archive-change` skill to fold the delta into `openspec/specs/dashboard-server/spec.md` and move this change to `openspec/changes/archive/`.
