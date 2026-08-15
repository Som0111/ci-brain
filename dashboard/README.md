# CI Brain Dashboard

React + TypeScript + Vite. Renders real data from the CI Brain API — no mock data anywhere.

## Run it

```
npm install
npm run dev
```

Opens at `http://localhost:5173`, pointing at `http://localhost:8000` by default. To point at
a different API (e.g. the deployed Render instance), copy `.env.example` to `.env.local` and
set `VITE_API_BASE`.

The backend must have CORS enabled (it does — see `app/main.py`) and at least one repo with
ingested run data, or the dashboard will just show empty states.

## Views

- **Run history** — `GET /repos/{id}/runs`
- **Flaky tests** — `GET /repos/{id}/flakiness`
- **Impact analysis** — interactive: enter changed files, calls `POST /repos/{id}/impact`
- **Benchmark** — `GET /benchmark`, a committed snapshot of Phase 4's real measured results
  (grouped bar chart + table, see `src/pages/Benchmark.tsx` for why test-count and wall-clock
  reduction are shown as separate series rather than one number)

## Design notes

Chart colors follow a validated categorical palette (see the project's `dataviz` design
process) - light/dark mode both pass CVD-safety and contrast checks via
`scripts/validate_palette.js` in that skill. One color (aqua, series 3) sits below 3:1
contrast on the light surface by design, which is why the benchmark page always ships a table
view alongside the chart rather than relying on the chart alone.

Two oxlint rules (`react-hooks/exhaustive-deps`, `react/only-export-components`) are disabled
project-wide in `.oxlintrc.json` - both fire on legitimate small-project patterns (a generic
data-fetching hook with an explicit deps array; a context+provider pair in one file) rather
than real bugs. See `HUMAN_GUIDE.md` at the repo root for the full reasoning.
