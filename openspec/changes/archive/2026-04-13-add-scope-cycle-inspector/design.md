## Context

The Scope API (Phase 2) exposes analysis cycles, traces, corrections, and sessions as JSON endpoints on `127.0.0.1:9877`. This change builds the React frontend that consumes those endpoints and renders the Cycle Inspector — the primary "why did the model decide this" view.

## Goals / Non-Goals

**Goals:**
- Build an interactive Cycle Inspector that shows the full input/output of any analysis cycle
- Make prompt text readable with collapsible sections and visual structure
- Show Pass 1 artifacts as cards with clear field labels
- Visualize evidence with weight-based styling
- Show timing breakdown for performance awareness
- Show corrections inline when they exist
- Keep the UI lightweight — no heavy framework, CSS-only styling

**Non-Goals:**
- Learning Curves view (Phase 4)
- Editing/correcting from Scope (Scope is read-only — corrections happen in the Pulse dashboard)
- Screenshot image display (screenshots may be cleaned up; show paths and "unavailable" placeholder)
- Mobile responsiveness (this is a desktop developer tool)
- Production build/deployment (dev server is fine for single-user local use)

## Decisions

### D1. React + Vite + TypeScript, minimal deps

**Decision:** Use React 18+ with Vite as the build tool and TypeScript for type safety. No UI framework (no Tailwind, no Material UI, no Chakra). CSS custom properties for theming, following Pulse's design token pattern.

**Why:** React gives component composition and state management for the interactive inspector. Vite gives instant HMR. TypeScript catches API contract drift at compile time. No UI framework because: the component count is small (~10), the layout is straightforward (sidebar + main panel), and adding a framework triples `node_modules` size for marginal benefit.

### D2. API client with TypeScript types mirroring the JSON schema

**Decision:** `src/api/client.ts` defines TypeScript interfaces for every API response shape (`Cycle`, `CycleTrace`, `Correction`, etc.) and exports typed fetch functions (`fetchCycles`, `fetchCycleTrace`, etc.).

**Why:** The API returns untyped JSON. Defining the expected shape in TypeScript means the compiler catches field name typos and missing null checks in components. If the API schema changes, the type errors surface immediately.

### D3. Collapsible prompt viewer with section highlighting

**Decision:** The PromptViewer component renders the full Pass 2 prompt with visual section breaks (App usage, Window titles, Planned tasks, Screenshot artifacts, Corrections, History) and a collapse/expand toggle. Sections are identified by the `## ` markdown headers in the prompt text.

**Why:** The Pass 2 prompt is 1-4 KB of dense text. Showing it all at once is overwhelming. Collapsible sections let the user focus on the part that matters for a given investigation ("why did it match this task?" → expand the Planned tasks and Screenshot artifacts sections).

### D4. Sidebar shows cycles as a compact list with visual indicators

**Decision:** Left sidebar shows a scrollable list of cycles for the selected day. Each entry shows: time (HH:MM), focus score as a colored dot (green ≥80, yellow ≥50, red <50), task name (truncated), and a correction indicator (pencil icon if corrected).

**Why:** The user's workflow is: scan the day's cycles, spot one that looks interesting (low score, unexpected task, correction), click to inspect. The sidebar needs to be scannable, not detailed.

### D5. Vite proxy for API calls

**Decision:** `vite.config.ts` configures a dev server proxy: requests to `/api/*` are forwarded to `http://127.0.0.1:9877`. The React code fetches from `/api/...` (relative URLs).

**Why:** Avoids CORS complexity during development. The browser sees one origin (`localhost:5173`), and Vite transparently proxies API calls to the backend. In a hypothetical production build, the API server could serve the static files directly — but for v1, the dev server is fine.

## Component Architecture

```
App
├── DatePicker               — select which day to view
├── CycleList (sidebar)      — scrollable list of cycles
│   └── CycleListItem        — one row: time, score dot, task
└── CycleInspector (main)    — selected cycle detail
    ├── InputsPanel
    │   ├── ArtifactCard[]   — one per screenshot from Pass 1
    │   ├── ContextSummary   — AW apps, titles, planned tasks, few-shot count
    │   └── PromptViewer     — collapsible, section-highlighted prompt text
    ├── OutputPanel
    │   ├── TaskHeader       — task name + ConfidenceBadge × 2
    │   ├── EvidenceList     — signal + weight badge per entry
    │   └── RawResponseToggle — expand to see raw JSON
    └── MetaPanel
        ├── TimingBar        — Pass 1 total + Pass 2 bar chart
        ├── RetryIndicator   — "0 retries" or "2 retries (parse failed)"
        └── CorrectionBadge  — "✓ confirmed" or "✏️ corrected → X"
```

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| **npm install reaches the network.** | One-time dev-machine action, same class as `pip install -r requirements-dev.txt`. Documented in CLAUDE.md. The privacy hook blocks npm in CI/runtime contexts. |
| **node_modules bloat in repo.** | `.gitignore` already updated in Phase 2 to exclude `scope/ui/node_modules/` and `scope/ui/dist/`. |
| **UI looks rough without a design framework.** | CSS custom properties + a small amount of hand-written CSS. This is a developer learning tool, not a product UI. Function over form. |
| **Privacy.** | No new data exposure. The UI reads from the Scope API which reads from the local SQLite DB. Vite dev server binds to localhost. No analytics, no telemetry, no external fonts or CDN resources. |
