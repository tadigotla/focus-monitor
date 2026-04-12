# Vendored static assets — provenance

This directory contains third-party static files that are **committed to the
repository** rather than fetched at runtime. focus-monitor's network policy
(see [CLAUDE.md](../../CLAUDE.md)) forbids any outbound network call except to
`localhost` / `127.0.0.1`, which means CDN hosting of JS libraries is not
permitted. Each file here has a single, auditable upstream source.

## htmx.min.js

- **Upstream:** https://unpkg.com/htmx.org@1.9.12/dist/htmx.min.js
- **Project:** https://htmx.org (BSD Zero-Clause License)
- **Pinned version:** 1.9.12
- **Fetch date:** 2026-04-12
- **Size:** 48101 bytes
- **SHA256:** `449317ade7881e949510db614991e195c3a099c4c791c24dacec55f9f4a2a452`

Used by the dashboard's plan-management UI to handle form submission and
partial-HTML swaps without a custom JavaScript build. Served locally from
`http://localhost:<dashboard_port>/static/htmx.min.js` by the dashboard
server, via an allowlisted static-file route. No other route serves files
from this directory.

### Updating

Treat version bumps as a deliberate, reviewable change:

1. Fetch the new file (requires a one-off network-policy exception; announce
   in chat before running).
2. Update this file with the new version, date, size, and SHA256.
3. Run the full test suite and the `privacy-review` skill.
4. Commit the new `htmx.min.js` and this file in the same commit.

Do not fetch at install time, at runtime, or via any form of automation that
hides the source from review.
