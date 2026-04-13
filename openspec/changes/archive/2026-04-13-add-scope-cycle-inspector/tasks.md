## 1. Project scaffold

- [x] 1.1 Initialize the Vite + React + TypeScript project in `scope/ui/` using `npm create vite@latest` (or manually create `package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`).
- [x] 1.2 Add minimal dependencies: `react`, `react-dom`, `@types/react`, `@types/react-dom`, `typescript`, `vite`, `@vitejs/plugin-react`.
- [x] 1.3 Configure `vite.config.ts` with the `/api` proxy to `http://127.0.0.1:9877`.
- [x] 1.4 Create `src/main.tsx` with React root mount and `src/App.tsx` with a placeholder layout.
- [x] 1.5 Create `src/styles/index.css` with CSS custom properties for colors, spacing, and typography (follow Pulse's design token pattern where sensible — dark/light mode via `prefers-color-scheme`).
- [ ] 1.6 Verify the dev server starts with `npm run dev` and renders the placeholder.

## 2. API client

- [x] 2.1 Create `src/api/types.ts` with TypeScript interfaces: `Cycle`, `CycleDetail`, `CycleTrace`, `Artifact`, `Evidence`, `Correction`, `Session`.
- [x] 2.2 Create `src/api/client.ts` with typed fetch functions: `fetchCycles(date, limit?, offset?)`, `fetchCycle(id)`, `fetchCycleTrace(id)`, `fetchCycleCorrections(id)`, `fetchCorrections(limit?, offset?)`.
- [x] 2.3 Add error handling: on non-2xx responses, throw a typed error with the status and message.

## 3. Cycle list sidebar

- [x] 3.1 Create `src/components/CycleList.tsx` — fetches cycles for the selected date, renders a scrollable list.
- [x] 3.2 Create `src/components/CycleListItem.tsx` — renders one row: time (HH:MM), focus score colored dot (green ≥80, yellow ≥50, red <50), truncated task name, correction indicator icon.
- [x] 3.3 Highlight the currently selected cycle in the list.
- [x] 3.4 Add a date picker input at the top of the sidebar to switch days (native `<input type="date">`).

## 4. Cycle Inspector — Inputs panel

- [x] 4.1 Create `src/components/CycleInspector.tsx` — fetches cycle detail and trace when a cycle is selected, renders three panels (Inputs, Output, Meta).
- [x] 4.2 Create `src/components/ArtifactCard.tsx` — renders one Pass 1 artifact with labeled fields (app, workspace, active_file, terminal_cwd, browser_url, browser_tab_titles, one_line_action). Null fields are omitted.
- [x] 4.3 Render the list of ArtifactCards from `trace.pass1_responses` (parsed JSON). Show screenshot path below each card.
- [x] 4.4 Create `src/components/ContextSummary.tsx` — renders AW app usage, window titles, planned tasks, and few-shot correction count in a compact format. Data comes from the cycle detail's `raw_response` fields.
- [x] 4.5 Create `src/components/PromptViewer.tsx` — renders the full Pass 2 prompt text with: collapse/expand toggle, section headers highlighted (identify `## ` markers), monospace font, word wrap.

## 5. Cycle Inspector — Output panel

- [x] 5.1 Render task name with `ConfidenceBadge` components for `name_confidence` and `boundary_confidence`.
- [x] 5.2 Create `src/components/ConfidenceBadge.tsx` — visual indicator: filled segments for high (3/3), medium (2/3), low (1/3). Color-coded green/yellow/red.
- [x] 5.3 Create `src/components/EvidenceList.tsx` — renders evidence array as a list with signal text and weight badge (strong/medium/weak styled differently).
- [x] 5.4 Show focus score, projects, planned_match, distractions from the cycle detail.
- [x] 5.5 Add a collapsible "Raw response" section showing the full JSON.

## 6. Cycle Inspector — Meta panel

- [x] 6.1 Create `src/components/TimingBar.tsx` — horizontal stacked bar showing Pass 1 total time vs Pass 2 time. Label each segment with milliseconds.
- [x] 6.2 Show parse retry count (0 = green "no retries", >0 = yellow with count).
- [x] 6.3 Create `src/components/CorrectionBadge.tsx` — if corrections exist for this cycle, show the correction: "confirmed" (green) or "corrected -> [user_task] ([user_kind])" (orange). Link to correction details.

## 7. Navigation and layout

- [x] 7.1 Wire prev/next cycle navigation buttons in the inspector header.
- [x] 7.2 Implement the two-panel layout: fixed-width sidebar (280px) + flexible main panel. Sidebar scrolls independently.
- [x] 7.3 Show a loading state while fetching cycle detail/trace.
- [x] 7.4 Show an empty state when no cycles exist for the selected date.

## 8. Verification

- [ ] 8.1 Start the Scope API (`python scope_api.py`), start Vite (`cd scope/ui && npm run dev`), open `http://localhost:5173`.
- [ ] 8.2 Verify: cycle list loads for today, clicking a cycle shows the inspector, prompt text is expandable, artifacts render correctly, evidence and confidence badges display.
- [ ] 8.3 Verify: navigating between cycles updates all panels.
- [ ] 8.4 Verify: date picker switches days and reloads the cycle list.
- [ ] 8.5 Verify: empty state displays when no data exists.
- [x] 8.6 Run the `privacy-review` skill against the full diff. Confirm no external CDN, no analytics, no telemetry, no non-localhost URLs in the React code.
