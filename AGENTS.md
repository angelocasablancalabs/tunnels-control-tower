# AGENTS.md — Operational Constitution

Contract for AI coding agents working in **tunnels-control-tower**. Read this file first, then `PROGRESS.md` (state of the world) and `README.md` (architecture).

**Project shape:** static React 19 + Vite 8 SPA. No backend, no database, no auth. UI language is **Italian** — keep all user-facing strings Italian. Data arrives as a committed static JSON contract (`public/traffic_data.json`) produced offline by `fetch_traffic.py` (Python + Gemini API). There is currently **no test runner and no type-checker**.

---

## 1. Operational Commands

| Task | Command | Verified |
| --- | --- | --- |
| Install deps | `npm ci` (clean checkout) / `npm install` | ✅ |
| Dev server | `npm run dev` | ✅ |
| Production build | `npm run build` | ✅ passes |
| Lint | `npm run lint` | ⚠️ **currently fails** — see §3.1 |
| Analyze build output | `npm run preview` | ✅ |
| Refresh traffic data | `python fetch_traffic.py` | requires `GEMINI_API_KEY` |
| Test | **does not exist** | 🚫 do not claim tests pass |
| Typecheck | **does not exist** | 🚫 no TS/`tsc` configured |
| Runtime | **Node** `^20.19.0 || ^22.13.0 || >=24` (verified on **v24.19.0**, npm 11.17.0) | ✅ |

> ⚠️ The runtime floor is a **hard** requirement, not a preference: Vite 8 refuses to run on Node 20.0–20.18. Node 24 is the active LTS until **2026-10-28**, then enters maintenance (**EOL 2028-04-30**). Do not quote "Node >= 20" (see §4.8).

A task is not complete until `npm run lint` and `npm run build` have both been run and their exact output reported.

---

## 2. Zero Unintended Regressions (Safety Clause)

> **Strictly preserve existing business logic and behavior UNLESS explicitly instructed to refactor, upgrade, or remove. Isolate all changes to minimize blast radius on unrelated modules.**

- The timeline/closure inference in `src/App.jsx` (`detectNightClosure`, `getDaySegments`, `norm`, `formatDateIT`) is **load-bearing business logic**. Do not "simplify" it as a side effect of an unrelated change.
- Keep `base: './'` in `vite.config.js`; the build depends on relative asset URLs.
- Do not reformat, reorder or restyle untouched code. No drive-by cleanups.
- Never edit `public/traffic_data.json` by hand as a substitute for fixing the pipeline.

---

## 3. Surgical Modification Protocol

- **Full-file rewrites are strictly prohibited for incremental changes.** Use targeted search-and-replace edits on the smallest possible block.
- Read a file before editing it. Change one concern per edit.
- `src/App.jsx` is a single ~560-line component; extend it surgically rather than restructuring it opportunistically.

### 3.1 Known broken baseline (fix-forward, do not copy)

`npm run lint` fails with `'React' is defined but never used` at `src/App.jsx:1`. The default `React` import is a pre-React-17 JSX-transform leftover. Fix it by removing the unused default import while **keeping the named imports** (`useState`, `useEffect`). Do not reintroduce the pattern elsewhere.

---

## 4. Anti-Obsolescence Propagation Rule

> **Never replicate, propagate, or extend deprecated patterns or obsolete libraries identified in this project. Any newly written code MUST target current framework standards.**

Hard prohibitions derived from the audit. **Re-verified against live registries and vendor documentation on 2026-10-16** (items 8–11) — treat these as current standards, not as folklore:

1. **No `import React from 'react'` for JSX.** React 19 + `@vitejs/plugin-react` use the automatic JSX runtime. Import only the named hooks/APIs you actually use (`import { useState } from 'react'`).
2. **Do not wire up PostCSS or `autoprefixer`.** Tailwind CSS v4 via `@tailwindcss/vite` handles vendor prefixing internally; the installed `postcss` and `autoprefixer` packages are unused legacy carry-over. Do not add a `postcss.config.js`, and do not import Tailwind via `@tailwind`/`@apply`-era directives. Use `@import "tailwindcss";` and `@theme` in `src/index.css`.
3. **Never extend the static `public/traffic_data.json` contract as an integration mechanism.** It is an offline, unreviewed LLM snapshot. Do not hand-edit it, do not treat it as a live data source, and do not introduce runtime fetching of third-party APIs. Any new corridor metric must first be added to the `fetch_traffic.py` prompt **and** schema-validated before the UI consumes it.
4. **Do not add state-management or routing libraries** (Redux, Zustand, Jotai, React Router, TanStack Router, …). This app is a single view over one JSON document; `useState` is the correct scope. Introducing them is a unilateral architecture change (§6 ASK FIRST).
5. **Do not create class components or legacy lifecycle hooks** (`componentDidMount`, `UNSAFE_*`). Function components + hooks only.
6. Do not commit `dist/`, generated assets, or secrets.
7. **Never write a real Tailwind class name into prose, docs or commit messages.** `DO NOT USE` literal utility names such as a `bg-<colour>-<shade>` or `rotate-<deg>` token in `README.md`, `PROGRESS.md`, `AGENTS.md` or any other tracked file → `USE` a neutral description (e.g. "a background-colour utility"), or break the token (`bg-` + `fuchsia-700`). **Why this is a hard rule and not a style preference:** Tailwind CSS v4 auto-detects sources across the project root and scans `**/*.md`, so a class name written in documentation **generates real CSS in the production bundle**. This was observed live on 2026-10-16: documenting a Tailwind experiment inside `PROGRESS.md` inflated the bundle from 23,118 to 23,244 bytes. `npm run build` is the detector — if the CSS size or hash moves after a docs-only edit, grep the docs for utility tokens.
8. **Never run or `npm install` on an unsupported Node runtime, and never re-state the floor as ">= 20".** `DO NOT USE` Node `20.0.0`–`20.18.x` (or any interpreter outside `^20.19.0 || ^22.13.0 || >=24`) → `USE` a runtime inside that range; the current verified target is **Node 24.19.0**. The range is not a preference: `vite@8.3.4` and `@vitejs/plugin-react@6.1.2` declare `node ^20.19.0 || >=22.12.0`, and `eslint@10.13.0` declares `node ^20.19.0 || ^22.13.0 || >=24`. Quoting "Node >= 20" is **forbidden** because Node 20.0–20.18 satisfies it while violating every dependency range. If a change needs a different floor, ask first — do not widen or narrow it unilaterally.
9. **Do not copy the deprecated Gemini API surface into any new Python code.** `DO NOT USE` `client.models.generate_content(...)` / `types.GenerateContentConfig` / `response.text` for **newly written** pipeline code → `USE` the **Interactions API** (`client.interactions.create(model=..., input=...)`, read `.output_text`). Google's live guidance: *"The Interactions API is our simplest and best way to build with Gemini models and agents. While `generateContent` remains fully supported, we recommend the Interactions API for all new development."* The **existing** call in `fetch_traffic.py` (lines 75–86) is **still fully supported and working** — do **not** rewrite it speculatively; fold the migration into R-4/R-9 in `PROGRESS.md`, and read the *Interactions breaking changes (May 2026)* notice first.
10. **Do not change the model ID, and do not downgrade it.** `DO NOT USE` `gemini-2.5-*` or `gemini-2.0-*` (the 2.x families are capacity-limited to pre-existing users and 2.0 is shut down), and do not introduce floating `-latest` aliases. `USE` **`gemini-3.8-flash`**, live-verified on 2026-10-16 as **Stable with no announced shutdown date**. Note that `gemini-4-argon` now exists as a newer flagship — adopting it is an **ASK FIRST** decision (cost/behaviour change), not a drive-by edit.
11. **Never let a dependency claim live in prose only.** `DO NOT USE` "the version in `package.json`" or a README table as the authority on what runs → `USE` the resolved lockfile / `npm ls --depth=0` output as ground truth, and re-verify against the live registry before asserting currency. `package.json` floors in this repo lag the resolved pins (TD-16), so the manifest is **not** evidence.

---

## 5. Boundaries

### ALWAYS
- Run `npm run lint` and `npm run build` before marking any task complete; report exact results.
- Append a dated session entry to `PROGRESS.md` (see §7) recording what changed and the verification output.
- Preserve the existing `public/traffic_data.json` field names when touching the UI.
- Guard new UI reads against the existing untrusted-data shape (the file is model-generated; fields can be missing). Defensive optional chaining is the established pattern — follow it.

### ASK FIRST
- Installing, upgrading or removing any dependency.
- Changing the `public/traffic_data.json` schema, or modifying database schemas (none exist today).
- Introducing breaking API changes, or any change to build/deploy configuration.
- Rewriting git history, force-pushing, or touching the repository remote.

### NEVER
- Commit secrets, API keys or `.env` files. `GEMINI_API_KEY` must never appear in source, fixtures, logs, or commits.
- Perform unauthorized mass refactors, repo-wide renames, or reformatting sweeps.
- Include fabricated sample data in `public/traffic_data.json` and present it as real traffic information. This dashboard informs real dispatch decisions.
- Delete the `src/assets/` scaffold files without explicit instruction (removal is tracked debt, not an implicit licence).

---

## 6. Escalation

Stop and ask when: a requested change conflicts with §4; a fix requires a dependency or schema change; or the baseline build/lint behaviour differs from §1. When in doubt, prefer the smaller, reversible change.

---

## 7. Session Log Format

Append to `PROGRESS.md` under **Last Session Notes**:

```
### YYYY-MM-DD — <short title>
- Changed: <files + one-line rationale each>
- Verified: `npm run lint` → <result>; `npm run build` → <result>
- Debt touched: <IDs from the inventory, or "none">
- Blocked / needs decision: <items, or "none">
```
