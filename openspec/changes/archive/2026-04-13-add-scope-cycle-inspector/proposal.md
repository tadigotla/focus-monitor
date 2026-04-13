## Why

Phases 1 and 2 established the data pipeline (trace logging) and the API layer (Scope API). But data in a JSON API is not learning — you need to *see* it to build intuition about how the AI makes decisions. The Cycle Inspector is the core learning view: for any analysis cycle, it shows exactly what went into the model, what came out, and how long it took.

This is where "understanding why the model makes specific classification decisions" becomes concrete: you can read the full prompt, see the structured artifacts the model extracted from each screenshot, trace each evidence signal back to an artifact, and compare the model's confidence with any corrections the user made.

## What Changes

- **New React + Vite application** in `scope/ui/` with TypeScript.
- **Cycle Inspector view** as the main (and initially only) view:
  - Left sidebar: scrollable list of cycles for a selected day, color-coded by focus score
  - Main panel: INPUTS section (Pass 1 artifacts, AW context, planned tasks, few-shot corrections, full prompt), OUTPUT section (task, evidence, confidence, focus score, raw response), META section (timing breakdown, parse retries, correction status)
  - Navigation between cycles (prev/next)
  - Date picker to switch days
- **Vite dev server** proxies `/api` requests to the Scope API on `:9877`
- **No new Pulse code changes** — this is entirely within `scope/ui/`

## Capabilities

### New Capabilities
- `scope-cycle-inspector`: Interactive React UI for inspecting the full input/output of any analysis cycle, including prompts, artifacts, evidence, confidence, timing, and corrections.

## Impact

**New code (scope/ui/):**
- `package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`
- `src/main.tsx`, `src/App.tsx`
- `src/api/client.ts` — typed fetch wrapper for the Scope API
- `src/components/` — CycleList, CycleInspector, PromptViewer, ArtifactCard, EvidenceList, ConfidenceBadge, TimingBar, CorrectionBadge
- `src/styles/index.css`

**Modified code:**
- None in Pulse. This change is entirely additive in `scope/ui/`.

**Dependencies (npm, dev-only):**
- `react`, `react-dom`, `@types/react`, `@types/react-dom`
- `vite`, `@vitejs/plugin-react`
- `typescript`
- No UI framework (no Tailwind, no MUI) — CSS-only styling to start

**Network:** `npm install` is a one-time dev-machine setup action (same class as `pip install -r requirements-dev.txt`). After install, everything runs locally. Vite dev server binds to `localhost:5173`. No runtime outbound calls.

**Privacy:** No new data exposure. The UI reads from the Scope API which reads from the local SQLite DB. Everything stays on `127.0.0.1`.
