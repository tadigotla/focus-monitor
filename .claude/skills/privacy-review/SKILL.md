---
name: privacy-review
description: Audit a diff or file set for privacy regressions against focus-monitor's local-only invariant. Trigger before committing any change that touches network, screenshots, storage paths, or dependencies.
---

# privacy-review

focus-monitor's entire value proposition is that nothing leaves the user's Mac.
This skill is a mechanical pass over a diff (or a set of files) to catch the
regressions that would silently break that promise. It is not a substitute for
reading the code — it is a checklist that makes the easy-to-miss categories
loud.

## When to trigger

Run this before committing any change that:

- Touches any module that speaks to the outside world (`activitywatch.py`,
  `ollama.py`, `dashboard.py`, `screenshots.py`).
- Adds or modifies imports in any file under `focusmonitor/`.
- Changes `config.py`, `config.json` defaults, or `setup.py` dependencies.
- Is described by its author as "I'll just pull in a quick library."
- Is a large refactor across more than ~5 files.

If in doubt, run it.

## What to check

Do all four checks. For each, list matches with `file:line` references, or
state "no findings" explicitly. Do not silently skip a category.

### 1. Non-localhost URLs in strings

Scan added/modified lines for string literals matching `https?://` where the
host is not `localhost`, `127.0.0.1`, or `::1`. Report every match.

Common false positives (flag but do not fail on these): URLs in docstrings or
comments that document upstream projects (e.g., a link to ActivityWatch's
GitHub). Call them out so the human can decide.

### 2. New outbound-HTTP imports

Check whether any of these modules have been newly imported in a file that
did not previously import them:

- `requests`
- `httpx`
- `urllib3`
- `aiohttp`
- `urllib.request` / `urllib.urlopen`
- `http.client`
- `socket` used with `connect` against a non-loopback address

An import alone is not proof of a regression (the module may only be used
against localhost), but every new import in this list is a finding to
surface.

### 3. Screenshot retention regressions

The invariant: screenshots in `~/.focus-monitor/screenshots/` must be deleted
after `screenshot_keep_hours` (default 48). Flag:

- Any change to `cleanup.py` that removes or weakens the retention cutoff.
- Any change to the `screenshot_keep_hours` default in `config.py` that
  increases it significantly (>7 days) without an accompanying note.
- Any new code path that writes screenshots outside
  `~/.focus-monitor/screenshots/`, bypassing cleanup.

### 4. 127.0.0.1 / loopback bind regressions

The dashboard and any other HTTP server in the project must bind to
`127.0.0.1`, never `0.0.0.0` or a public interface. Flag:

- Any `host=` or `bind=` argument changed from `127.0.0.1` (or `localhost`)
  to `0.0.0.0`, `""`, or an explicit external address.
- Any new server in the project whose bind address is not explicitly
  loopback.
- Any firewall or macOS network configuration hints added to the repo that
  imply external access.

### 5. Write endpoint hardening

The dashboard has a read-only surface *and* a plan-management write surface.
The read surface is safe without auth because it only serves data the user
could already read. The write surface is *only* safe because every mutation
passes through a single `_mutate()` choke-point that validates:

- the `Host` header (defends against DNS rebinding),
- the `Origin` header (defends against cross-origin browser POSTs),
- a per-request CSRF token from the in-memory `_csrf_tokens` store.

A change that bypasses this choke-point, relaxes it, or adds a new mutation
path without routing through it is a **P0 finding**, not a style nit. Flag:

- Any new method on `DashboardHandler` other than `do_GET` / `do_POST` that
  reads from `self.rfile` or mutates on-disk state.
- Any new entry in `_POST_ROUTES` whose handler does not call `_mutate(...)`
  before touching files.
- Any code path inside an existing `_handle_*` method that writes to
  `planned_tasks.json` / `discovered_activities.json` / the DB / the
  filesystem *before* the `_mutate` call.
- Any weakening of the `Host` check (e.g., accepting `*.localhost`, allowing
  an empty Host, reading the Host from a user-controllable source like
  `X-Forwarded-Host`).
- Any weakening of the `Origin` check (e.g., allowing mismatched origins,
  unconditionally accepting missing Origin when `Referer` is present).
- Any new `Access-Control-Allow-*` header, any CORS-related logic, any
  addition of `allow_origin` / `*` wildcarding.
- Any new cookie-based auth, session storage, or long-lived token scheme
  (the design deliberately keeps CSRF tokens as the *only* mutation-auth
  mechanism).
- Any change to `_issue_csrf_token` or `_consume_csrf_token` that removes
  the single-use semantics, extends the TTL past 1 hour without a comment
  explaining why, or skips the `_csrf_lock` acquisition.
- Any `http://` or `https://` URL referencing `htmx`, `unpkg`, `cdnjs`,
  `jsdelivr`, or any other CDN outside of `focusmonitor/static/PROVENANCE.md`
  and its surrounding documentation comments. Vendored libraries come from
  committed files, not runtime fetches.
- Any new file under `focusmonitor/static/` that is not listed in
  `PROVENANCE.md` with a name, upstream URL, version, fetch date, and
  SHA256.
- Any new name added to `STATIC_ALLOWLIST` without a matching `PROVENANCE.md`
  entry.
- Any `os.path.join(STATIC_DIR, user_input)` or similar pattern that builds
  a file path from the request. The allowlist-lookup is the entire
  path-resolution story; introducing path concatenation invites traversal.

## How to invoke

Ask me: "Run privacy-review on this diff" (with the diff pasted or after a
`git diff`), or "Run privacy-review on `focusmonitor/ollama.py`".

## Report format

```
# privacy-review report

## 1. Non-localhost URLs
- focusmonitor/foo.py:42 — "https://api.example.com/v1" (added)
- (or: no findings)

## 2. New outbound-HTTP imports
- focusmonitor/bar.py:3 — `import httpx` (new in this file)
- (or: no findings)

## 3. Screenshot retention
- (or: no findings)

## 4. Loopback bind addresses
- focusmonitor/dashboard.py:88 — host="0.0.0.0" (was "127.0.0.1")
- (or: no findings)

## 5. Write endpoint hardening
- focusmonitor/dashboard.py:340 — new _handle_foo does not call _mutate() (P0)
- (or: no findings)

## Summary
<one-sentence verdict: "safe to commit" / "N findings need review">
```

## What this skill does NOT do

- It does not run the code or the tests. For tests, use `test-focusmonitor`.
- It does not replace `CLAUDE.md`'s network policy — it enforces it
  mechanically after the fact.
- It does not block commits. A human decides what to do with the findings.
