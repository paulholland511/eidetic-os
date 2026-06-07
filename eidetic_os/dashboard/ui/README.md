# Eidetic OS — Control Centre (dashboard UI)

The enterprise dashboard single-page app: **React 18 + TypeScript + Tailwind +
shadcn/ui**, charted with **Recharts** and a **D3** force-directed knowledge
graph. It is bundled to a single self-contained HTML file and served by the
Flask app in `../app.py` at `/`, talking to the `/api/*` JSON endpoints.

Premium UI components were sourced via the 21st.dev **Magic MCP** and adapted to
the slate/zinc + emerald design system.

## Layout

```
src/
  App.tsx                   app shell — sidebar nav, top bar, tab routing
  lib/api.ts                typed fetch layer + reactive live/demo detection
  lib/sample.ts             representative demo data (used only with no backend)
  components/kit.tsx         shared primitives (StatCard, Panel, Sparkline, …)
  components/GraphView.tsx   D3 force-directed knowledge graph
  tabs/                     Overview, Memory, RagSearch, Skills, Security, Pipelines, Settings
```

When opened with a live backend (`eidetic dashboard`) every value is read from
the Python core; opened straight from disk it falls back to the demo data and
flags itself as such.

## Build

```bash
pnpm install
pnpm run build:bundle
```

`build:bundle` runs Parcel, inlines everything into `bundle.html`, then copies it
to `../static/dashboard.html` (the file Flask serves).

> **Note:** the binaries are invoked directly (`./node_modules/.bin/parcel`)
> rather than via `pnpm exec`, because pnpm v10+ aborts `pnpm exec` with a
> non-zero exit when a dependency's native build script is unapproved. Running
> the binary directly skips that pre-flight check; the native deps (lmdb,
> @swc/core, msgpackr) ship prebuilt binaries, so the build still works.

## Develop

```bash
pnpm run dev        # Vite dev server with hot reload (uses demo data)
```
