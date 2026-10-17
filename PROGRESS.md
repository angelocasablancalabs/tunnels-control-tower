# PROGRESS.md — Baseline Audit, Technical Debt & Roadmap

> Single source of truth for cross-session agent memory. **Read before starting work; append after finishing it** (see `AGENTS.md` §7).
> Last audit: **2026-10-16** · Commit: `2605628` (`fase1`) · Branch: `master` · Version: `0.0.0`
> Last **external reality-check audit**: **2026-10-16** — live registry + vendor-docs verification (§2 TD-16…TD-21).

---

## 1. Current Baseline Status

The application **builds and runs correctly**. It is a functional prototype, not a production-hardened system.

| Capability | Status | Evidence |
| --- | --- | --- |
| Production build | ✅ **Passing** | `vite v8.3.4` — 1921 modules → `dist/` (JS 239.68 kB / gzip 74.57 kB, CSS 21.80 kB / gzip 5.20 kB), as of the 2026-10-17 quick-status-removal + docked-header change |
| Dev server / HMR | ✅ Working | `npm run dev` |
| ESLint | ✅ **Passing** | `eslint .` → **exit 0, zero problems** (was 1 error: unused default `React` import at `src/App.jsx:1` — corrected 2026-10-16, see TD-14) |
| Automated tests | ⚫ **None** | No test runner installed, no test files |
| Type checking | ⚫ **None** | JavaScript only; no `tsconfig.json`, no `tsc` |
| Data pipeline | ⚠️ Unverified end-to-end | `fetch_traffic.py` passes `py_compile`; live Gemini call not exercised during this audit (avoids API spend + non-determinism) |
| Data freshness | ⚠️ Stale snapshot | `last_updated: 2026-10-17 08:32`; 30 days present (`2026-10-17` → `2026-11-15`); Fréjus now 1 `BLOCCO_TOTALE` + 29 `RESTRIZIONE` (taxonomy change, see §5), Mont Blanc 15 `BLOCCO_TOTALE` + 8 `RESTRIZIONE` + 7 `REGOLARE` |
| CI / CD | ⚫ **None** | No `.github/`, no remote configured; builds are manual |
| Git state | ⚠️ Dirty | `README.md` deleted-in-worktree (now regenerated), `fetch_traffic.py` + `public/traffic_data.json` modified, `.env` **tracked** |

**Verified render path:** `index.html` → `src/main.jsx` → `src/App.jsx` → `fetch('./traffic_data.json')` (works because `base: './'`). Styling: `src/index.css` → `@import "tailwindcss"` + `@theme` Montserrat. Icons: `lucide-react`.

### Objective assessment

- **Functional:** 30-day board, 24h timeline ribbons, night-closure inference, micro-stop marking, axis filter, full-text search, responsive desktop-table/mobile-card layouts with column headers docked under the top bar, source links.
- **Not production-ready because:** a live API key is committed to git; lint is red; there is zero automated test coverage; and the sole data source is an unvalidated LLM response rendered directly into the UI.

---

## 2. Technical Debt & Obsolescence Inventory

The baseline is **not** a safe template. "It builds" ≠ "it is sound". Severity reflects risk to correctness, security, and future maintenance.

### High

- **[TD-01] Live API key committed to version control.** `.env` is tracked in git (added in the initial commit `2605628`) and is **not** matched by `.gitignore`. It contains a real `GEMINI_API_KEY`. The key is duplicated into every clone and into the permanent object history.
  → *Remediation:* **Rotate/revoke the key in Google AI Studio immediately** (highest priority — history rewriting is pointless while the key is still valid). Then add `.env` (and `.env.*`) to `.gitignore`, `git rm --cached .env`, and provide a committed `.env.example`. Scrubbing history (`git filter-repo`) is a destructive operation requiring explicit human approval (`AGENTS.md` §5 ASK FIRST).
- **[TD-02] Zero automated test coverage on load-bearing logic.** `detectNightClosure` and `getDaySegments` encode real dispatch decisions via regex and hour arithmetic, with untested branches (overnight rollover, `21h`/`nuit` keyword fallback, multi-segment days). A regression here silently misinforms drivers.
  → *Remediation:* introduce **Vitest** + React Testing Library. Extract the pure date/segment helpers into `src/lib/timeline.js`, then table-test them against fixture days including overnight and micro-stop cases.
- **[TD-03] Unvalidated LLM output is the single source of truth.** `fetch_traffic.py` asks a model for a 30-day nested JSON document, strips markdown fences with a regex, and `json.loads` the result with no schema validation, no retry, no day-count assertion, and no date-continuity check. A malformed or hallucinated response either crashes the script or silently ships wrong traffic data to the UI.
  → *Remediation:* validate against a Pydantic (or JSON Schema) model before writing; assert exactly 30 consecutive days beginning today; retry with backoff on parse failure; fail the run loudly rather than writing a partial file; write atomically (temp file + rename).
- **[TD-04] Frontend assumes every field exists and is a string.** `src/App.jsx` performs `day.frejus.title + day.frejus.details + day.frejus.micro_stops` (lines ~205–206) with no guard. A single missing field throws inside `.filter()` and white-screens the whole app.
  → *Remediation:* normalise the payload once after fetch into a defensive shape (or adopt TypeScript), then render from the normalised model. Optional chaining is already used inconsistently elsewhere — make it uniform.

### Medium

- **[TD-05] Redundant and unused build dependencies.** `postcss@8.5.30` and `autoprefixer@10.6.1` are installed but referenced nowhere; Tailwind CSS v4 via `@tailwindcss/vite` handles prefixing internally and there is no `postcss.config.js`. Adds install weight and implies a pipeline that does not exist.
  → *Remediation:* confirm no consumer, then remove both. Explicitly prohibited from being wired up in the meantime (`AGENTS.md` §4.2).
- **[TD-06] Python dependencies are unpinned and undeclared.** No `requirements.txt` / `pyproject.toml`. The pipeline silently depends on globally installed `google-genai 2.31.0` + `python-dotenv 1.2.4`. Reproducibility depends entirely on the operator's machine.
  → *Remediation:* add a pinned `requirements.txt` (or `pyproject.toml`) and document the venv workflow in `README.md`.
- **[TD-07] Dead Vite scaffold assets inflate the repo.** `src/App.css` (2.9 kB), `src/assets/hero.png` (13 kB), `src/assets/react.svg`, `src/assets/vite.svg` — **none referenced** by any source file (verified by content search). `public/icons.svg` (5.0 kB) is likewise unreferenced, yet it is copied verbatim into every `dist/` build.
  → *Remediation:* delete after confirming intent. Deletion is deliberately **not** performed automatically and requires explicit instruction (`AGENTS.md` §5 NEVER).
- **[TD-08] Mixed-language codebase with Italian-only UI strings.** All user-facing text is Italian while code identifiers, comments and config are mixed. There is no i18n layer.
  → *Remediation:* decide the target audience. If multi-lingual is in scope, extract strings to a message catalogue before the UI grows further. If Italian-only is permanent, state it explicitly (now recorded in `AGENTS.md`) and stop drifting.
- **[TD-09] Single 558-line component with duplicated render branches.** Desktop-table and mobile-card branches repeat near-identical corridor blocks four times, and statuses are stringly-typed (`'BLOCCO_TOTALE' | 'RESTRIZIONE' | 'REGOLARE'`) with no shared constant.
  → *Remediation:* extract `<CorridorCell>` and `<StatusBadge>` components and a shared status constant. Purely mechanical, no behaviour change — defer until tests exist (see TD-02) so the refactor is verifiable.

- **[TD-16] ✅ **RESOLVED 2026-10-16** — Manifest version floors have drifted far behind what is actually installed.** *(found by live audit 2026-10-16)* `package.json` still declares `react: ^19.2.8`, `vite: ^8.3.0`, `eslint: ^10.10.0`, `@vitejs/plugin-react: ^6.1.1`, `globals: ^17.12.0`, `@types/react: ^19.2.18`, while `package-lock.json` resolves `react 19.3.1`, `vite 8.3.4`, `eslint 10.12.0`, `@vitejs/plugin-react 6.1.2`, `globals 17.13.0`, `@types/react 19.3.0`. The manifest is now an inaccurate description of the build: a reader auditing `package.json` concludes the project is a minor-generation behind, and any regeneration of the lockfile from a clean state can resolve a *different* tree than the one currently verified. Reproducibility today rests entirely on the committed lockfile, not on the manifest.
  → *Remediation:* raise the declared floors to the verified resolved versions (or pin exactly), then re-run `npm ci && npm run lint && npm run build` and confirm the reported bundle metrics are unchanged. **Dependency changes require approval (`AGENTS.md` §5 ASK FIRST)** — this is a proposal, not an authorization.
  ✅ *Resolution (2026-10-16):* all 16 declared floors raised to exactly match their lockfile-resolved pins (see the R-7 entry in §4). Verified with `npm outdated` returning **no** rows and a manifest-vs-pin comparison reporting **0 mismatches**. No dependency was upgraded by this change — only the declaration was corrected, so the installed tree is byte-for-byte unchanged.
- **[TD-17] ✅ **RESOLVED 2026-10-16** — Runtime floor is documented but not enforced, and the README states it wrongly.** *(found by live audit 2026-10-16)* The project declares no `engines` field and ships no `.nvmrc` / `.node-version`, so npm will happily install on an unsupported interpreter. Meanwhile `README.md` §Prerequisites claims "**Node.js ≥ 20**", which is **not** a supported floor: the installed toolchain requires `vite@8.3.4 → node ^20.19.0 || >=22.12.0`, `eslint@10.12.0 → node ^20.19.0 || ^22.13.0 || >=24`, and `@vitejs/plugin-react@6.1.2 → node ^20.19.0 || >=22.12.0`. Node `20.0.0`–`20.18.x` satisfies the README but violates every one of those ranges.
  → *Remediation:* correct the README to `^20.19.0 || ^22.13.0 || >=24`, add a matching `engines` field plus `.nvmrc` pinned to a supported line, and set `engine-strict` so the failure is loud at install time rather than cryptic at build time.
  ✅ *Resolution (2026-10-16):* `engines.node` set to `^20.19.0 || ^22.13.0 || >=24`, `.nvmrc` added (`24`), and `engine-strict=true` set in a new `.npmrc` so an unsupported interpreter fails loudly at install time. `npm ci` was then run on Node 24.19.0 and succeeded, confirming the declared range admits the verified runtime.
- **[TD-18] ✅ **RESOLVED 2026-10-16** — ESLint is one patch behind current stable.** *(found by live audit 2026-10-16)* Installed `eslint@10.12.0` (and pinned as such in the lockfile); npm registry latest is **`10.13.0`**, published 2026-10-16. This is the **only** genuine version delta in the entire npm tree — `npm outdated` reports this single row and nothing else.
  → *Remediation:* bump to `10.13.0`, re-run lint, and confirm the TD-14 failure mode is unchanged. Low blast radius, but it is a dependency change → `AGENTS.md` §5 ASK FIRST.
  ✅ *Resolution (2026-10-16):* bumped to `eslint@10.13.0` with the lockfile refreshed. Post-bump `npm run lint` produces **exactly the same single error** (`src/App.jsx:1`, TD-14) with no new rule violations introduced by the upgrade.
- **[TD-19] The data pipeline uses the `generateContent` API path, which Google now recommends replacing for new development.** *(found by live audit 2026-10-16)* `fetch_traffic.py` uses `client.models.generate_content(...)` + `types.GenerateContentConfig` + `response.text`. Google's live migration guide states: *"The Interactions API is our simplest and best way to build with Gemini models and agents. While `generateContent` remains fully supported, we recommend the Interactions API for all new development."* The replacement is `client.interactions.create(model=..., input=...)` with `.output_text`. A separate published notice, **"Interactions breaking changes (May 2026)"**, exists.
  → *Remediation:* this is a **forward-compatibility** item, not an outage: `generateContent` is explicitly still fully supported, so do **not** rewrite the working pipeline speculatively. When the pipeline is next modified as part of R-4 (schema validation, retries, atomic writes), evaluate the Interactions API in the same pass and read the May-2026 breaking-changes notice first. Pin the decision in the session log either way.
- **[TD-20] ✅ **RESOLVED 2026-10-16** — Python dependency graph is unpinned *and the global interpreter is shared with unrelated projects*.** *(found by live audit 2026-10-16)* Extends TD-06 with measured evidence. `requirements.txt` / `pyproject.toml` / `.python-version` are all absent, and `python -m pip list --outdated` shows the **global** `Python314` site-packages carries 21 outdated packages belonging to unrelated workloads (`streamlit 1.62.0 → 1.66.0`, `pandas 3.0.5 → 3.0.6`, `numpy 2.5.2 → 2.5.4`, `pyarrow 25.0.1 → 26.0.0`, `starlette 1.6.0 → 1.8.0`, `uvicorn 0.52.4 → 0.54.0`, `websockets 16.1.1 → 17.2`, …). This project's own two imports are current (`google-genai 2.31.0`, `python-dotenv 1.2.4` — both registry-latest), but they resolve out of that shared, drifting namespace. A future transitive bump in the shared environment can break the pipeline with no change in this repository.
  → *Remediation:* create a dedicated `.venv`, declare pinned `google-genai` + `python-dotenv` in `requirements.txt`, and document the venv workflow. Do **not** upgrade the unrelated global packages from this repository's scope.
  ✅ *Resolution (2026-10-16):* `.venv` created (interpreter Python 3.14.0, starts with pip only), `google-genai==2.31.0` and `python-dotenv==1.2.4` pinned in a committed `requirements.txt`, and installed there. `.venv/` was already gitignored. The pipeline's imports (`google.genai`, `google.genai.types.GenerateContentConfig`, `dotenv`) resolve inside the venv, and `fetch_traffic.py` still AST-parses and compiles. **`fetch_traffic.py` itself was not edited** — per `AGENTS.md` §4.8 the `generateContent` call and `gemini-3.8-flash` model ID are untouched.

### Low

- **[TD-10] No code formatter.** No Prettier or `.editorconfig`; formatting is by convention only, which increases diff noise for the surgical edits `AGENTS.md` mandates.
  → *Remediation:* add Prettier plus an `.editorconfig`, then format once as an isolated, reviewable commit.
- **[TD-11] Hardcoded operational constants in UI logic.** The micro-stop window was hardcoded as `22:30–23:15` (`src/App.jsx` ~line 138, `microStops.includes('22:30')`), and that hardcoded test was **removed on 2026-10-16** in favour of a general time-range parser (see the session log). The night-closure heuristic thresholds (`19:00`, `08:00`, `21:00`) are magic numbers tied to one operator's schedule.
  → *Remediation:* hoist the remaining night-closure thresholds into a documented `src/config/operations.js`, or better, derive from structured fields the pipeline emits rather than parsing prose. **Partially resolved 2026-10-16** (micro-stop half only).
- **[TD-12] No license file.** Absent `LICENSE`, the repository is all-rights-reserved by default despite a public-showcase `README.md`.
  → *Remediation:* add an explicit license.
- **[TD-13] No CI and no deploy automation.** `base: './'` shows GitHub Pages was the intent, but no workflow exists; there is no remote configured and no build is verified on push.
  → *Remediation:* add a GitHub Actions workflow running `npm ci`, `npm run lint`, `npm run build` once lint is green (TD-14).
- **[TD-14] ✅ **RESOLVED 2026-10-16** — Lint did not gate anything (and was red).** `npm run lint` failed on the pre-React-17 default `React` import at `src/App.jsx:1`. The default `React` import is dead under the automatic JSX runtime. *Fix applied 2026-10-16:* the unused default import was removed (named `useState`/`useEffect` hooks kept) — `eslint .` now exits **0 with zero problems**. What remains open is only the **gating** half (no CI workflow), tracked under R-2.
  → *Remediation:* remove the unused default import, keeping `{ useState, useEffect }`. One-line fix; documented as fix-forward in `AGENTS.md` §3.1.
- **[TD-15] Untracked local build artifacts after audit.** `dist/` was produced by the baseline build and is correctly gitignored.
  → *Remediation:* none — informational. Confirms `.gitignore` works for build output.
- **[TD-21] No recorded runtime lifecycle / LTS-upgrade timeline.** *(found by live audit 2026-10-16)* Node **v24.19.0** is supported and remains the active LTS, but per the official Node release schedule it entered **maintenance on 2026-10-20** with **EOL 2028-04-30**; **v26 becomes LTS on 2026-10-28** (`start 2026-05-05, lts 2026-10-28, maintenance 2027-10-20, end 2029-04-30`). Python 3.14.0 is the current stable line. Nothing is EOL today, so this is **not** an incident — but there is no place in the repo that records *when* this runtime went to maintenance or when to plan the move.
  → *Remediation:* record the lifecycle dates in `README.md` §Prerequisites so the next maintainer sees the maintenance/EOL horizon rather than a bare version number, and add the Node 24 → 26 upgrade as a dated, low-priority backlog item.

### Explicitly *not* debt (checked, current)

- `gemini-3.8-flash` is a **valid current stable model** — re-verified against the live catalogue on 2026-10-16 (<https://ai.google.dev/gemini-api/docs/models>): listed under *Gemini 3 → Stable*, with **no announced shutdown date** on the deprecation table (<https://ai.google.dev/gemini-api/docs/deprecations>; released 2026-09-02, no replacement required). The model ID is **not** stale and must **not** be changed. The missing validation around it is the actual defect (TD-03); the recommended-newer *API surface* is TD-19.
- React 19.3.1, React DOM 19.3.1, Vite 8.3.4, `@vitejs/plugin-react` 6.1.2, Tailwind CSS 4.3.3, `@tailwindcss/vite` 4.3.3, lucide-react 1.58.0, postcss 8.5.30, autoprefixer 10.6.1, `google-genai` 2.31.0 and `python-dotenv` 1.2.4 are **all at the latest version published on their registries**. Node 24.19.0 and Python 3.14.0 have **no EOL exposure**: Node 24 is supported until 2028-04-30 (TD-21); Python 3.14 is the current stable line.
- **As of 2026-10-16 there is no longer any version delta in this repository.** ESLint was the sole outlier (≥ 10.12.0 vs 10.13.0) and has been bumped to **10.13.0** (TD-18/R-7); `npm outdated` now returns **no rows**, for the npm tree, and both Python imports are at PyPI-latest in the isolated `.venv`.
- `@vitejs/plugin-react` uses Oxc rather than Babel; the Babel packages in `node_modules` are transitive, not a legacy pipeline choice.

---

## 3. Milestones

- [x] **Milestone 0 — Initialization complete.** Repository audited; `.env` exposure, lint failure and missing test harness identified; `README.md`, `AGENTS.md` and `PROGRESS.md` generated; baseline build verified.
- [x] **Milestone 1 — Dependency graph reconciled & pipeline environment isolated.** ✅ *(2026-10-16)* All 16 declared floors aligned to resolved pins; ESLint bumped to current stable; runtime floor enforced via `engines` + `.nvmrc` + `engine-strict`; Python pipeline moved into a pinned `.venv`. **TD-16, TD-17, TD-18, TD-20 resolved** and **R-7, R-8 completed**. Verified with `npm ci` / `lint` / `build` / `outdated` / `audit`; JS bundle byte-identical to Milestone-0.

---

## 4. Roadmap

Ordered by risk. TD-01 and TD-14 first: one is a security incident, the other unblocks CI gating. R-7–R-9 were added by the **2026-10-16 external reality-check audit**; no existing task was removed or downgraded by it.

- [ ] **R-1 — Rotate the exposed `GEMINI_API_KEY`, then stop tracking secrets.** *(TD-01 · High)*
  Rotate the key in Google AI Studio → add `.env` / `.env.*` to `.gitignore` → `git rm --cached .env` → commit `.env.example`. History scrubbing deferred to an approved follow-up. **Requires human action for rotation.**
- [ ] **R-2 — Fix the lint failure and make lint gate the build.** *(TD-14, TD-13 · Low/High)*
  ✅ **Lint half DONE 2026-10-16:** the unused default `React` import was removed from `src/App.jsx` and `npm run lint` now exits **0** with zero problems — see the session log. ⏳ **Remaining:** add a CI workflow running `npm ci`, `lint`, `build` (TD-13).
- [ ] **R-3 — Establish a test harness and cover the timeline logic.** *(TD-02 · High)*
  Add Vitest + React Testing Library; extract pure helpers to `src/lib/timeline.js`; table-test overnight rollover, `nuit`/`21h` fallback, multi-segment days and micro-stops. Prerequisite for R-5.
- [ ] **R-4 — Harden the data pipeline contract.** *(TD-03, TD-04, TD-06, TD-19, TD-20 · High)*
  Add a pinned `requirements.txt` inside a dedicated `.venv` (R-8); evaluate the Interactions API while the pipeline is open (R-9); schema-validate the Gemini response before writing; assert 30 consecutive days; retry on parse failure; write atomically; normalise the payload defensively in the UI.
- [ ] **R-5 — Remove obsolete and dead artifacts.** *(TD-05, TD-07 · Medium)*
  Drop `postcss` + `autoprefixer`; delete unreferenced `src/App.css`, `src/assets/hero.png`, `src/assets/react.svg`, `src/assets/vite.svg`, `public/icons.svg`. Verify build output is unchanged. Do not wire PostCSS back in (`AGENTS.md` §4.2).
- [ ] **R-6 — Introduce type safety and formatter.** *(TD-10, TD-09 · Medium/Low)*
  Incremental TypeScript migration starting at the data-boundary types, plus Prettier + `.editorconfig`. Enables the TD-09 component extraction safely.
- [x] **R-7 — Make the declared dependency graph match reality, and enforce the runtime floor.** *(TD-16, TD-17, TD-18 · High/Medium)*
  ✅ **COMPLETED 2026-10-16** (owner-authorized under `AGENTS.md` §5). All 16 floors in `package.json` raised to exactly match the lockfile-resolved pins: `react`/`react-dom` `^19.3.1`, `vite` `^8.3.4`, `@vitejs/plugin-react` `^6.1.2`, `@types/react`/`@types/react-dom` `^19.3.0`, `globals` `^17.13.0`, `eslint` `^10.13.0`, `eslint-plugin-react-refresh` `^0.5.7` (this last one was not in the original audit list but was equally stale at `^0.5.6`). `engines.node`, `.nvmrc` and `engine-strict` added per TD-17.
  **Verified:** `npm outdated` → **no rows** (nothing outdated); manifest-vs-pin check → **0 mismatches**; `npm ci` → **exit 0**, 159 packages, 0 vulnerabilities (on Node 24.19.0 under `engine-strict`); `npm run build` → **exit 0**, 1921 modules, JS **241.60 kB / gzip 74.72 kB** (identical to baseline).
  *(new from the 2026-10-16 live audit)* Raise the `package.json` floors to the lockfile-resolved versions (`react`/`react-dom` `^19.3.1`, `vite` `^8.3.4`, `@vitejs/plugin-react` `^6.1.2`, `globals` `^17.13.0`, `@types/react`/`@types/react-dom` `^19.3.0`, `eslint` `^10.13.0`); bump `eslint` to 10.13.0; add `engines` (`node: ^20.19.0 || ^22.13.0 || >=24`) plus `.nvmrc` and `engine-strict`; correct the README prerequisite. Verify with `npm ci && npm run lint && npm run build` and confirm bundle metrics are unchanged. **Requires approval — dependency change (`AGENTS.md` §5 ASK FIRST).**
- [x] **R-8 — Isolate the Python pipeline environment.** *(TD-20, TD-06 · Medium)*
  ✅ **COMPLETED 2026-10-16** (owner-authorized under `AGENTS.md` §5). `.venv` created (Python 3.14.0, contains only pip until install); committed `requirements.txt` pinning `google-genai==2.31.0` and `python-dotenv==1.2.4`; installed into the venv (27 distributions, all transitives resolved). `.venv/` was already covered by `.gitignore`.
  **Verified:** pip list in `.venv` → exactly the two pinned versions plus their transitives; pipeline imports (`google.genai`, `types.GenerateContentConfig`, `dotenv`) resolve **inside** the venv; `fetch_traffic.py` `py_compile` **exit 0** and AST parse OK. **No edit to `fetch_traffic.py`** — `generateContent` and `gemini-3.8-flash` deliberately preserved (§4.8).
  *(new from the 2026-10-16 live audit)* Create a dedicated `.venv`, pin `google-genai==2.31.0` and `python-dotenv==1.2.4` into a committed `requirements.txt`, and document the venv workflow in the README. Do **not** touch the unrelated outdated packages in the shared global `Python314` site-packages.
- [ ] **R-9 — Evaluate the Gemini Interactions API for the pipeline.** *(TD-19 · Low — scheduled, not urgent)*
  *(new from the 2026-10-16 live audit)* Fold into R-4 when the pipeline is next touched. Read the *Interactions breaking changes (May 2026)* notice, decide `client.interactions.create` + `.output_text` vs staying on the still-fully-supported `generateContent`, and record the decision in `PROGRESS.md`. Do **not** rewrite the working pipeline as a standalone change.

---

## 5. Last Session Notes

### 2026-10-17 — Ricerca per data in formato italiano naturale (`21/10/2026`, `21/10`, `21 ottobre`)

- **Changed:**
  - `src/App.jsx` — added the `MONTHS_IT` lookup next to `formatDateIT`; rewrote the `filteredDays`
    search predicate so each day yields a searchable target combining ISO (`2026-10-21`), Italian
    (`21/10/2026`) and natural (`21 ottobre`) dates plus `day_name`, normalizing `.`/`-`/space to `/`.
    Corridor matching now uses defensive optional chaining on the model-generated JSON. Search
    placeholder updated to advertise date search.
- **Verified:** `npm run lint` → exit 0 (no output); `npm run build` → exit 0, `vite v8.3.4`, 1921
  modules, `dist/` JS 240.19 kB (gzip 74.77 kB) / CSS 21.82 kB (gzip 5.20 kB) in 537 ms.
- **Debt touched:** TD-14 (baseline lint failure no longer reproduces — the unused default `React`
  import is gone; ESLint is clean).
- **Blocked / needs decision:** none.

### 2026-10-17 — TMB-GEIE source deepened to the "Interruzioni e previsioni" portal

- **Changed:**
  - `fetch_traffic.py` — the `FONTI UFFICIALI DA ISPEZIONARE TRAMITE GOOGLE SEARCH` bullet for
    TMB-GEIE/ATMB now names `tunnelmb.net/it-IT/interruzioni-e-previsioni` explicitly, with the
    official quarterly calendars / total night closures / alternating one-way description. Grounding
    now anchors on the disruption bulletin instead of the marketing homepage.
  - `src/App.jsx` — footer "TMB-GEIE (Monte Bianco)" link now points at the same portal URL. The
    per-corridor source resolver (`resolveSource`, already using this URL) was left untouched, so both
    entry points land on the operational page. Markup/classes unchanged.
  - `README.md` — Data Sources table row for TMB-GEIE updated to the portal URL. No utility tokens
    introduced (AGENTS.md §4.7).
- **Verified:**
  - `npm run lint` → ✅ `eslint .` output empty, **exit 0**.
  - `npm run build` → ✅ `vite v8.3.4`, 1921 modules, `dist/assets/index-zfbmaHZB.css` 21.82 kB
    (gzip 5.20 kB) / `dist/assets/index-nV4ijbUG.js` 239.75 kB (gzip 74.60 kB), built in 582 ms, **exit 0**.
    CSS size/hash **unchanged** vs the previous session → the docs edit leaked no Tailwind utilities.
  - Shipped bundle of `dist/assets/index-nV4ijbUG.js` contains the portal URL **twice** (source resolver + footer).
  - `.venv\Scripts\python.exe fetch_traffic.py` → ✅ **exit 0**; 31 days (2026-10-17 → 2026-11-16),
    `last_updated` 2026-10-17 10:24, contract intact (`last_updated` / `quick_status` / `days`, each corridor
    with `status` / `title` / `details` / `micro_stops`). `public/traffic_data.json` regenerated by the pipeline
    only — never hand-edited (§4.3).
  - Portal URL reachability: a server-side `web_fetch` returns **HTTP 403 (Cloudflare bot challenge)**, which is
    a bot filter, not a 404. The indexed page is live per search results
    ([IT](http://tunnelmb.net/it-IT/interruzioni-e-previsioni),
    [EN counterpart](http://www.tunnelmb.net/en-US/closures-and-forecasts)).
- **Debt touched:** none. TD-14 stays fixed; TD-01 / TD-19 status unchanged.
- **Blocked / needs decision:** none. Note: the link target cannot be smoke-tested by an automated HTTP fetch
  from this environment (Cloudflare), so end-user click-through should be confirmed in a real browser.

### 2026-10-17 — Profilo mezzo allargato a tutti i veicoli pesanti 44t (ADR ed eccezionali esclusi)

- **Changed:**
  - `src/App.jsx` — header subtitle widened from the frigo-only wording to
    `Monitoraggio Valichi Transalpini • Focus Veicoli Pesanti 44t (escluso ADR e convogli eccezionali)`.
    Closures and restrictions apply uniformly to all standard 44t HGVs (reefers, curtain-siders, dry vans),
    so the frigo-only label understated the scope; ADR and exceptional convoys are now explicitly out of
    scope, which makes the dashboard safe to share with hauliers and external logistics partners.
    Typography unchanged (same size/weight/colour utilities); text wraps to two lines at a 390 px viewport.
  - `fetch_traffic.py` — `PROFILO MEZZO ESCLUSIVO` prompt block realigned to the new scope:
    `Veicolo Pesante / Bilico 5 assi standard 40-44t (Frigo, Telonato, Box …)`, `Merci ordinarie e deperibili
    (ESCLUSO ADR, ESCLUSO convogli/trasporti eccezionali, NO furgoni <3.5t)`, `Standard Euro 6`.
    Dimensions/speed assumptions and the Gemini call are untouched; only the two profile lines changed.
- **Verified:**
  - `npm run lint` → ✅ `eslint .` output empty, **exit 0** (TD-14 remains fixed; `src/App.jsx:1` uses named imports only).
  - `npm run build` → ✅ `vite v8.3.4`, 1921 modules, `dist/assets/index-zfbmaHZB.css` 21.82 kB
    (gzip 5.20 kB) / `dist/assets/index-BJPwjZl1.js` 239.72 kB (gzip 74.60 kB), built in 531 ms, **exit 0**.
  - `python -m py_compile fetch_traffic.py` → ✅ exit 0.
  - Rendered output: new string present in the shipped bundle and the old `Bilici Frigo` string absent;
    confirmed over both the Vite dev server (5173) and the built `dist/` served on 4173.
  - Header verified visually via Chrome headless: desktop 1440 px → single line, legible;
    true 390 px viewport → wraps to two clean lines, block right edge 359 px < 390 px, **0 elements
    overflowing the viewport** (`scrollWidth` 375). An apparent mobile clipping in a raw
    `--window-size=390` capture was a headless cropping artifact (~485 px layout in a 390 px capture), not CSS.
  - `public/traffic_data.json` **not** regenerated and **not** hand-edited — the new profile applies at the
    next `python fetch_traffic.py` run.
- **Debt touched:** none (TD-08 Italian-only UI unchanged; TD-14 stays fixed).
- **Blocked / needs decision:** none. Note: the next data refresh is required to have the prompt change
  reflected in `public/traffic_data.json`; the snapshot on disk still reflects the previous profile wording
  only insofar as the model echoed it in free-text fields.

### 2026-10-17 — Durate di chiusura esplicite: `(durata: X ore)` al posto di `(9h)` / `(8h)`

- **Changed:**
  - `fetch_traffic.py` — added a mandatory "FORMATO OBBLIGATORIO DELLA DURATA (in title e details)" block
    to the prompt: shorthand forms such as `(9h)` / `(8h)` are banned because at a glance they read as a
    start time ("alle 9:00"); the total duration must always be written as `(durata: X ore)` or
    `(durata: X ore e Y min)`, with the two dispatch examples (A43 Charmaix 03:30-12:30 → `durata: 9 ore`;
    TMB 22:00-06:00 → `durata: 8 ore`). The two JSON-template examples were updated to the explicit form.
    No other prompt rule, taxonomy or API call changed.
  - `public/traffic_data.json` — regenerated by `python fetch_traffic.py` (no hand-editing).
- **Verified:**
  - `python fetch_traffic.py` (`.venv`, Gemini 3.8 Flash + Google Search grounding) → ✅ success,
    30 days generated, quick-status strings now read e.g. `… 03:30-12:30 (durata: 9 ore)` / `… 22:00-06:00 (durata: 8 ore)`.
  - JSON validation script → ✅ valid `json.load`, 30 days, 2026-10-17 → 2026-11-15, `span_days` 30,
    `continuous: True`; regex `\(\d+h\)` → **0 matches**; `(durata: ` → 35 occurrences.
    18 Oct Fréjus: `Blocco Mezzi Pesanti A43 Charmaix 03:30-12:30 (durata: 9 ore)`; TMB night closures:
    `Blocco Notturno TMB 22:00-06:00 (durata: 8 ore)`.
  - `npm run lint` → ✅ clean, no output (TD-14 remains fixed).
  - `npm run build` → ✅ `vite v8.3.4`, 1921 modules, `dist/assets/index-azH-DtJw.css` 21.80 kB
    (gzip 5.20 kB) / `dist/assets/index-D6z9_L1n.js` 239.68 kB (gzip 74.57 kB), built in 529 ms, zero errors.
- **Debt touched:** none.
- **Blocked / needs decision:** none.

### 2026-10-17 — Quick-status banners removed; column headers docked under the top bar ("Blocca Riquadri")

- **Operational problems fixed:**
  1. Two status cards sat above the table, restating what the corridor rows already said, and pushed the
     30-day board below the fold. They are gone: on load the filter bar and the first table rows now sit
     directly under the navigation bar, and filtering to a single corridor leaves no orphan card behind.
  2. While scrolling a 30-day board 3 500 px tall, the operator lost column orientation. The three
     column headers now detach from the table and stay pinned immediately under the navigation bar for
     the whole scroll, so *Data / Giorno*, *Asse Fréjus* and *Asse Monte Bianco* are always readable.

- **Changed — `src/App.jsx`, three surgical edits, no restructuring:**
  1. The whole quick-status section was deleted from `<main>`: the two-card layout driven by
     `data.quick_status?.frejus_next_block` and `data.quick_status?.monte_bianco_next_block` no longer
     renders. `main` now flows straight into the filter bar, then the desktop table, then the mobile
     cards. The helper icon that only decorated those two cards was dropped from the `lucide-react`
     import (keeping it would have reintroduced the unused-import lint error). The `quick_status` field
     itself is **left untouched in `public/traffic_data.json`** — the UI simply stops reading it, so the
     data contract and the pipeline are unchanged.
  2. The desktop table's outer wrapper lost its overflow-clipping utility and now uses the
     non-clipping one (`overflow` computes to `visible`), because a clipping ancestor neutralises docked
     positioning relative to the window. Its white surface, rounded corner, border and small shadow are
     preserved. The bottom two corner radii are now unclipped in principle; no visual difference was
     observed because the rows paint on the wrapper's own white surface, and only the translucent
     "today"/hover washes could reach them.
  3. Each `<th>` in the desktop `<thead>` became a docked cell: an anchored-position utility with a
     **72 px top offset**, stacking level **20** (below the navigation bar's 30), the same dark surface
     colour as before, a small drop shadow and a bottom hairline so the header keeps a visible edge
     while detached. The outer cells carry the top-left / top-right corner radii (the last rendered cell
     always does, so the corner survives the single-corridor filters). Text styling
     (`py-3 px-4`, white, extra-small, uppercase, wide tracking, bold) and the vertical dividers between
     columns are unchanged; nothing else in the row model, widths or `<tbody>` was touched.
  - **Deliberately not done:** no position was applied to `<thead>`/`<tr>` (the docked cells carry it, so
    the collapsed-border table keeps its layout), no scrolling wrapper was introduced around the table,
    and no other section of the app was restyled.

- **Verified:**
  - `npm run lint` → ✅ **exit 0**, zero problems, zero warnings.
  - `npm run build` → ✅ **exit 0**, `vite v8.3.4`, 1921 modules, JS **239.68 kB / gzip 74.57 kB**,
    CSS **21.80 kB / gzip 5.20 kB** (`index-D6z9_L1n.js`, `index-azH-DtJw.css`). Both shrank versus the
    previous 240.94 / 22.27 kB: the two status cards and their colour set no longer exist. The JS drop is
    ≈ 1.3 kB for a real feature removal, not a lost rule set.
  - ✅ **Real-browser verification this session (new capability, no dependency added).** Previous
    sessions recorded "no headless browser installed"; Chrome **is** present on this machine, so the
    built app was served from `dist/` and driven with `--headless=new` over the DevTools protocol
    (`Page.captureScreenshot` + `Runtime.evaluate`, plain Node, no package installed). The scratch
    server, probe pages, driver scripts and Chrome profiles lived in the gitignored `dist-ssr/` and in
    `dist/`, and were deleted before the final build.
  - Measured geometry, desktop 1440×900, on the shipped build:
    - At the top of the page: 3 header cells, first cell top **190 px** — i.e. the table starts right
      after the 72 px nav bar + filter bar, with **0** status-card wrappers inside `main`.
    - After scrolling to **scrollY 1500** (document 5 067 px tall): navigation bar bottom **77 px**,
      every header cell top **72 px**, cell bottom **113 px**, computed position `sticky`, computed
      `top` `72px`, stacking level `20`, surface colour unchanged. The 5 px overlap with the navigation
      bar is covered by that opaque bar (level 30) and shares its exact colour, so no row content can
      peek through the seam.
    - Column alignment held at depth: the last header cell's right edge **1335 px** equals the table's
      right edge **1335 px** at scrollY 1500; 30 body rows still rendered.
    - Filtering to "Solo Fréjus": **2** header cells (no orphan Monte Bianco column), last cell right
      edge still **1335 px**, **0** banners, headers still docked at **72 px**.
  - Pixel check from the CDP screenshots: the docked band is contiguous with the navigation bar, and row
    text is cleanly cut off at the band's lower edge — content passes underneath, nothing paints over it.
    The top-of-page screenshot shows the filter bar as the first element and four day rows inside the
    first viewport.
  - Docs regression check (`AGENTS.md` §4.7): this entry deliberately spells out **no** Tailwind utility
    names — the edited classes are described by their CSS effect. The build was re-run after writing it
    and the CSS asset name and byte count are the ones reported above, so the prose leaked no rule.
  - Known, pre-existing: `npm run preview` and `npm run dev` cannot start under this session's file
    sandbox (Vite loads the native Tailwind binding and shells out for path resolution — both denied);
    the build itself only succeeds with full host access. That is an environment limitation, not a
    regression from this change, and it is why the app was served through a plain static server instead.

- **Debt touched:** none resolved. **TD-04 is slightly widened**: the removed cards were the only
  defensive reads of `quick_status`, and the JSX still has none for the new `<th>` markup (it is static
  text, so no new unguarded data read was introduced).
- **Blocked / needs decision:**
  1. ℹ **The docked offset is a literal 72 px while the navigation bar measures 77 px.** The 72 px value
     is what was specified, and it is the safe direction: the bar is opaque and identical in colour, so
     the 5 px overlap is invisible, whereas a too-large offset would expose a strip of scrolling rows.
     If the bar's height ever changes, the offset must follow it (a single constant would be the durable
     fix — worth folding into TD-11's "hoist operational constants" item).
  2. ℹ **The mobile card view has no docked header**, by design: a card list has no column header to
     dock, and the 72 px offset only applies to the desktop table (`md` and up).
  3. ℹ **The bottom corner radii of the table wrapper are no longer clipped.** Only the translucent
     hover/"today" row washes could reach them, and none was observed misbehaving; if the owner prefers
     strict clipping, the durable fix is a scrolling wrapper or per-corner radii on the last row, not a
     return to the clipping utility (which would break the docked headers).

### 2026-10-17 — Deterministic official-source portal link in every corridor cell

- **Operational problem fixed:** a cell that reports an event (total blockage, an A43 Orelle detour,
  scheduled maintenance) forced the dispatcher to go find the operator's bulletin page by hand. The
  link is now resolved **deterministically in the client** from the corridor key plus keywords — never
  from a model-generated URL, which could drift or 404.

- **Changed:**
  - `src/App.jsx` — three surgical edits, no restructuring:
    1. New module-level helper right after `norm`: `getCorridorOfficialSource(corridorKey, corridorData)`.
       It first requires the corridor object to carry content (title, details or micro-stop text, or a
       total blockage) and returns `null` otherwise, so a clean day can never resolve a portal.
       Then, on the accent-preserving normalised title+details text: Fréjus → SITAF when the Italian
       axis is named (A32, SITAF, Susa, Oulx, Bussoleno), SFTRF otherwise (its works-and-closures page);
       Monte Bianco → ATMB when the French side is named (A40, ATMB, Vuache, the Égratz viaduct,
       Chavants), SAV A5 for the A5/Arnad side, TMB-GEIE otherwise (its interruptions-and-forecast page).
    2. The shared `CorridorContent` component now accepts a `corridorKey` prop and resolves the source
       once, rendering the operator label as the **last** element of **both** render branches — i.e.
       after the details and after the micro-stop tag — in the total-blockage branch and in the
       event-without-blockage branch. Because the desktop table and the mobile cards already render
       through this one component, both layouts gained the link from a single implementation and cannot
       drift apart. The label is a small slate-grey operator name followed by the external-link icon,
       turning blue on hover; it carries an Italian accessible title ("Apri portale ufficiale …") and
       opens in a new tab with `rel="noreferrer"`.
    3. The four call sites pass `corridorKey="frejus"` / `corridorKey="monte_bianco"`.
  - No import was added: `ExternalLink` was already imported (and is still used by the footer).
  - **Not changed:** `detectNightClosure`, `getDaySegments`, `norm`, `formatDateIT`, `parseMicroStops`,
    `StatusBadge` and `TimelineRibbon` are byte-identical — no timeline arithmetic or ribbon rendering
    was touched. `public/traffic_data.json` (schema and content), `fetch_traffic.py`, `index.html`,
    `vite.config.js`, `eslint.config.js` and every dependency are untouched.

- **Verified:**
  - `npm run lint` → ✅ **exit 0**, zero problems.
  - `npm run build` → ✅ **exit 0**, `vite v8.3.4`, 1921 modules, JS **240.94 kB / gzip 74.85 kB**,
    CSS **22.27 kB / gzip 5.33 kB** (`index-fqMNDhsI.js`, `index-aCVtasq4.css`). CSS is +0.05 kB over
    the previous 22.22 kB, which is exactly the new link's handful of utilities; each one was confirmed
    present in the built stylesheet, so the rules were generated and nothing was silently dropped.
  - ✅ **Render-level assertion (not a screenshot).** The real module-level code was sliced verbatim out
    of `src/App.jsx` (everything before the default-exported `App`), bundled with the project's own
    React, and rendered with `renderToStaticMarkup` against the current `public/traffic_data.json`:
    **60 corridor cells over 30 days, 0 failures.** The assertion set was: a `REGOLARE` cell must render
    **zero bytes** and **no** anchor; every non-empty cell must contain **exactly one** anchor whose
    `href` equals the helper's resolved URL, with `target="_blank"`, `rel="noreferrer"` and the Italian
    accessible title, positioned **after** the micro-stop tag.
  - Resolution tally on the current snapshot: Fréjus **23 SITAF / 7 SFTRF**, Monte Bianco **8 ATMB /
    22 TMB-GEIE**. Spot checks: `2026-10-18` (Charmaix load test, `BLOCCO_TOTALE`) → **SFTRF**;
    `2026-10-19` (Orelle night closure, RD 1006) → **SFTRF**; `2026-10-22` (Orelle **+** A32 Susa-Oulx)
    → **SITAF**; `2026-10-19` Mont Blanc (TMB + A40 Vuache) → **ATMB**; `2026-10-25`, `2026-11-07`,
    `2026-11-08`, `2026-11-11`, `2026-11-13`, `2026-11-15` `REGOLARE` cells → **0 bytes, 0 anchors**.
  - The scratch SSR directory used for that assertion was created under the gitignored `dist-ssr/` and
    **deleted before the final build**; the final rebuild reproduced the **same** JS and CSS hashes, so
    no utility token leaked from this documentation edit (`AGENTS.md` §4.7 re-checked after writing it).

- **Debt touched:** none resolved. **TD-03 / TD-11 are deepened**: the operator mapping is another
  hardcoded keyword heuristic applied to LLM prose, the same fragility class as the night-closure
  thresholds. The durable fix remains structured fields (corridor-level operator, closure and detour)
  emitted by the pipeline, not inferred by the UI.

- **Blocked / needs decision:**
  1. ⚠ **Still no pixel-level visual sign-off.** No headless browser is installed and adding one is a
     dependency change (`AGENTS.md` §5 ASK FIRST); approval prompts are disabled this session.
     Verification rests on the rendered markup above plus the build metrics — not on a screenshot.
  2. ℹ **Keyword precedence is coarse and order-dependent.** The Italian-axis check runs first, so a
     Fréjus day that mentions *both* the Maurienne works and the A32 resolves to **SITAF**
     (`2026-10-22`), while `2026-11-14` — whose text names "SFTRF/SITAF" together — resolves to SITAF
     although the closure is the T4. If the *primary* operator of the day is wanted, the pipeline should
     emit it as a field instead of the UI inferring it.
  3. ℹ **The Égratz keyword cannot currently match.** `norm` does not strip accents, so the accented
     French spelling present in the data never equals the unaccented keyword; RN205/Égratz-only days
     therefore fall back to **TMB-GEIE** (which is still the right tunnel operator). The helper was
     implemented verbatim as specified; making it accent-insensitive means either widening `norm`
     (load-bearing shared logic, `AGENTS.md` §2) or adding a local accent-insensitive comparison —
     a decision for the owner, not a drive-by edit.
  4. ℹ **The SAV A5 branch is dormant on the current snapshot** (0 hits): every day that mentions the
     A5 also mentions the A40, which is tested first. It will activate if a day names only the
     A5/Arnad side. Not a defect, but it means that branch is only covered by inspection today.
  5. ℹ A `REGOLARE` day can still *resolve* a portal (e.g. a regular day whose details name the A32)
     while rendering nothing, because the content component returns before the link. Verified: 5
     regular cells, 0 anchors. This is the intended "clean day stays empty" behaviour, not a leak.

### 2026-10-17 — Windows UTF-8 console fix & minimalist exception-only restyling

- **Changed:**
  - `fetch_traffic.py` — added `import sys` plus a module-level guard right after the import section:
    for each of stdout/stderr, if it exists and its reported encoding is not UTF-8, it is
    reconfigured to UTF-8 inside a try/except that swallows the failure (streams without
    `reconfigure`, or a `None` stream, are skipped). This removes the need for `PYTHONUTF8=1`.
    **No other line of the pipeline was touched** — model ID, search tool, temperature, the
    `generateContent` call and the writer are unchanged.
  - `src/App.jsx` — restyling, five surgical edits:
    1. `CheckCircle2` dropped from the `lucide-react` import (it became unused once the emerald
       badge disappeared; leaving it would have reintroduced a lint error).
    2. The in-component status-badge factory was replaced by two module-level presentational
       components: a badge that returns `null` for every status except the total blockage (keeping the
       red pill with its pulsating dot), and a single shared corridor-content component.
    3. The four duplicated corridor cell bodies (tabella desktop ×2, card mobile ×2) were replaced by
       that one shared component, so desktop and mobile cannot drift. It encodes: `BLOCCO_TOTALE` →
       badge, grassetto, dettagli e tag micro-stop; ogni altro stato non regolare con contenuto →
       no badge, no grassetto, title and details in one uniform regular weight, plus the micro-stop tag;
       regular or empty → renders nothing at all (so a clean day's cell is genuinely empty and
       "Transito regolare" never appears).
    4. Ribbon: the technical-stop spans lost their top/bottom borders and their drop shading and moved
       to a flat, lighter amber tone, so green → amber → red now abut with no dividing lines. The three
       hour ticks became a mapped list: each row is vertically centered on its percentage line by a
       half-height upward translation, with the subtle rule consuming the remaining width and the
       label sitting in its own gap, so no line crosses the text.
    5. Divisori di riga: row dividers moved from the lighter tone to the mid tone, and the header row
       gained a distinct bottom rule, so row separators read clearly stronger than the faint ribbon ticks.
  - `PROGRESS.md` — this entry and the §1 build-metrics row.
  - **Not changed:** `detectNightClosure`, `getDaySegments`, `norm`, `formatDateIT` and
    `parseMicroStops` (byte-identical — no timeline arithmetic was touched), `index.html`,
    `vite.config.js`, `eslint.config.js`, every dependency, `requirements.txt`, and the JSON contract.

- **Verified:**
  - `python fetch_traffic.py` in a plain PowerShell console **with `PYTHONUTF8` and
    `PYTHONIOENCODING` explicitly cleared** → ✅ **exit 0**, emoji banner lines printed, 30 days
    written. The previous `UnicodeEncodeError` on cp1252 is gone; no environment variable is needed.
  - `npm run lint` → ✅ **exit 0**, zero problems (no unused-import fallout from the removed badge).
  - `npm run build` → ✅ **exit 0**, `vite v8.3.4`, 1921 modules, JS **239.35 kB / gzip 74.52 kB**,
    CSS **22.22 kB / gzip 5.32 kB**. Both shrank (JS ≈ −2.1 kB, CSS ≈ −0.9 kB) because four verbatim
    cell bodies and the emerald/amber badge colour sets no longer exist; no rule was lost by accident.
  - ✅ **Render-level assertion (not a screenshot).** The real `CorridorContent` and `TimelineRibbon`
    were sliced verbatim out of `src/App.jsx`, bundled with the project's own React, and rendered with
    `renderToStaticMarkup` against the current `public/traffic_data.json`: **60 corridor cells across
    30 days, 0 failures.** Every `BLOCCO_TOTALE` day carries the red pill **and** a grassetto title;
    nessuna cella non-bloccata carries a badge or grassetto; every regular cell renders **zero** bytes
    of markup; every amber span has no dividing line; all three hour labels are present and half-height centered.
  - Spot-checked markup: `2026-10-18` (`BLOCCO_TOTALE`) → pill + grassetto title + details; `2026-10-19`
    (Orelle / RD 1006) → two uniform regular-weight paragraphs + the timer tag, no badge;
    `2026-10-25` (regular) → empty string.
  - Rebuilt after this markdown edit; the stylesheet hash is unchanged, so no utility token leaked
    from prose (`AGENTS.md` §4.7 re-checked).

- **Debt touched:** **TD-09 partially addressed** for the two corridor cells — the four duplicated
  render branches are now one component with a single status badge, which is the extraction TD-09
  asked for. No debt resolved; no dependency, schema or backend change.
- **Blocked / needs decision:**
  1. ⚠ Still **no pixel-level visual sign-off** — no headless browser is installed and adding one is a
     dependency change. Verification is the rendered markup plus the build metrics above.
  2. ℹ The content component treats **any** `REGOLARE` day as empty regardless of text, which is what
     makes "clean day ⇒ empty cell" deterministic. This is safe only while the pipeline's taxonomy
     guarantees that a day with real operational content is never labelled `REGOLARE`; the prompt now
     enforces that convention in prose, not in schema (TD-03 still open).
  3. ℹ Amber is now the dominant ribbon colour (25 Fréjus days of 30 are `RESTRIZIONE`), so the
     ribbon reads as a continuous yellow-green field. That is a consequence of the taxonomy agreed in
     the previous session, not of this restyle; say so if it should be tightened.

### 2026-10-17 — Dispatch taxonomy in the extraction prompt: `RESTRIZIONE` vs `BLOCCO_TOTALE`

- **Operational problem fixed:** the prompt asked only for "blocchi" and told the model to emit `REGOLARE`
  when it found none. A motorway/gallery closure **with a heavy-goods-vehicle-legal detour** (e.g. A43
  Orelle 21:00–06:00 deviated onto RD 1006) therefore either disappeared from the board or was wrongly
  flattened into a total blockage. Both outcomes misinform real 40–44t refrigerated dispatch.

- **Changed:**
  - `fetch_traffic.py` — four surgical edits to the `prompt` f-string only. **No change to the model ID,
    the Google Search tool, `temperature`, the `generateContent` call, the markdown-fence stripper, or
    the writer.** (`AGENTS.md` §4.9/§4.10 respected — no speculative Interactions-API migration.)
    1. **Official-sources block** rewritten as *targeted verification directives*: SFTRF/APRR must be
       searched specifically for A43 Maurienne maintenance closures (Orelle, Saint-Michel-de-Maurienne,
       Le Freney, viaduc du Charmaix) **and** for whether the accompanying detour (RD 1006) admits HGVs;
       SITAF for night closures on Susa-Oulx / Bussoleno / galleries plus whether SS24-SS335 admit 44t;
       TMB-GEIE & ATMB for night closures, alternating one-way schedules and Vuache / Rampa Égratz works.
    2. **New dispatch taxonomy section** classifying by *vehicle impact on a 40–44t 5-axle unit*, not by
       the existence of a worksite: `BLOCCO_TOTALE` only when transit is genuinely impassable (no
       alternative, or the detour is explicitly prohibited to HGVs — `déviation interdite aux PL > 3.5t /
       7.5t` — or mandatory staging such as Rieu Sec); `RESTRIZIONE` whenever the corridor stays viable
       with penalties (HGV-legal detour, alternating one-way, Tube 1 micro-stops, lane reductions);
       `REGOLARE` strictly when nothing mandatory applies. `title`/`details` must name the detour road
       (RD 1006, SS24, SS335) and the estimated delay.
    3. **Extraction objective** now leads with an explicit anti-omission rule (a worksite with an
       HGV-legal detour is a `RESTRIZIONE` to publish, not an event to drop) and requires the
       detour-permission judgement in the A43/A40/A32/RN205/A5 bullet.
    4. **JSON schema deliberately unchanged** — same top-level keys, same per-day keys, same corridor
       keys, same three status values. Only the illustrative example strings inside `title`/`details`
       were updated to show the detour phrasing, so no frontend contract breaks.
  - `PROGRESS.md` — this entry and the §1 data-freshness row.
  - **Not changed:** `src/**` (byte-identical — the amber `RESTRIZIONE` badge and the green ribbon
    already behave correctly for this taxonomy, see Verified), `index.html`, `vite.config.js`,
    `eslint.config.js`, every dependency, and `requirements.txt`.

- **Verified (live run, 2026-10-17):**
  - `python fetch_traffic.py` (via `.venv`, Python 3.14.0) → ✅ **exit 0**, 30 days generated.
    *Operational note:* a bare run under the console's cp1252 code page crashes on the script's own
    pre-existing emoji `print` (`UnicodeEncodeError` on the first line) — **unrelated to this change**;
    it was run with `PYTHONIOENCODING=utf-8`/`PYTHONUTF8=1`. Worth a follow-up hardening, not a defect
    introduced here.
  - `public/traffic_data.json` → ✅ parses as valid JSON; `last_updated: 2026-10-17 08:32`; **30 days**,
    continuous `2026-10-17` → `2026-11-15`. Schema keys confirmed identical: top level
    `last_updated, quick_status, days`; per day `date, day_name, is_today, frejus, monte_bianco`; per
    corridor `status, title, details, micro_stops`.
  - ✅ **Acceptance criterion met — Orelle 19–22 Oct captured as `RESTRIZIONE`.** All four nights now
    read e.g. `"Chiusura notturna A43 galleria Orelle 21:00-06:00 con deviazione RD 1006 aperta ai PL
    (+45/60 min)"`, with details naming the deviated section (Saint-Michel-de-Maurienne ↔ Le Freney),
    the RD 1006 detour as authorized for 40–44t and the `+45/60 min` penalty.
  - ✅ **Contrast case correct — 18 Oct is `BLOCCO_TOTALE`:** the Charmaix load test (03:30–12:30) states
    the RD 1006/RD 216 detour is reserved for cars and coaches and `tassativamente interdetta ai mezzi
    pesanti >3.5t`, with mandatory staging at Rieu Sec. The taxonomy is discriminating, not blanket.
  - ✅ **Timeline ribbon stays green on the detour days.** The shipped `getDaySegments` /
    `detectNightClosure` helpers were extracted verbatim from `src/App.jsx` and executed against the new
    JSON (Node 24.19.0). `2026-10-19`…`2026-10-22` (`RESTRIZIONE`) each return a single
    `open(0–24)` segment → **0 closed hours**, while `2026-10-18` (`BLOCCO_TOTALE`) returns
    `open(0–3.5)`, `closed(3.5–12.5)`, `open(12.5–24)` → **9 closed hours**. So the amber
    `RESTRIZIONE` badge renders with the detour text while no red 24h band is drawn — exactly the
    required behaviour, and it required **no frontend edit** because `detectNightClosure` already
    early-returns unless `status === 'BLOCCO_TOTALE'`.
  - `npm run lint` → ✅ **exit 0**, zero problems.
  - `npm run build` → ✅ **exit 0**, `vite v8.3.4`, 1921 modules, JS **241.45 kB / gzip 74.59 kB**,
    CSS **23.12 kB / gzip 5.53 kB** as `index-Br7MFXAn.css` — **byte-identical CSS hash** to the recorded
    clean baseline, so this docs/edit pass leaked no Tailwind utilities (`AGENTS.md` §4.7 re-checked).

- **Debt touched:** none resolved. **TD-03 remains open** — the response is still unvalidated and the new
  taxonomy is enforced by prose, not by a schema enum + assertion; the payload happens to be correct
  today, which is not a guarantee. This change sharpens the R-4 requirements (R-4 should assert
  `status ∈ {REGOLARE, RESTRIZIONE, BLOCCO_TOTALE}` and ideally require a detour field rather than
  parsing it out of `details` prose, cf. TD-11).
- **Blocked / needs decision:**
  1. ⚠ **No pixel-level visual sign-off.** Still no headless browser installed, and adding one is a
     dependency change requiring approval (approval prompts are disabled this session). The ribbon
     assertion rests on executing the real shipped helpers against the real JSON, plus the unchanged
     CSS hash — not on a screenshot.
  2. ℹ **29 of 30 Fréjus days now read `RESTRIZIONE`.** That is the intended consequence of classifying
     any corridor with works, micro-stops, alternating one-way or lane reductions as restricted, but it
     does mean amber is the new normal on the board. If the owner wants amber reserved for genuinely
     disruptive events, the threshold should be stated explicitly in the prompt — a policy decision,
     not a bug.
  3. ℹ The detour authorization is inferred from search snippets; it is not machine-verified against the
     operator's arrêté. Treat `RESTRIZIONE`/`BLOCCO_TOTALE` boundaries as advisory until R-4 lands.

### 2026-10-16 — Timeline ribbon: full-height table cells and dynamic micro-stop rendering

- **Changed:**
  - `src/App.jsx` — four surgical edits, no restructuring:
    1. Line 1: removed the unused default `React` import, keeping the named `useState` / `useEffect` hooks. Resolves **TD-14** and unblocks the lint half of **R-2**.
    2. New module-level `parseMicroStops` helper: extracts **every** time range from `corridorData.micro_stops` with a global regex accepting both the colon and the dotted hour separator, returns `{ startH, endH, label }` in decimal hours, and discards inverted or zero-length ranges.
    3. `TimelineRibbon`: the single hardcoded evening-range test was replaced by a map over the parsed ranges, drawing one high-visibility amber warning bar per range, positioned at its exact fractional hour and floored in height so a 45-minute span stays legible. Each bar exposes the matched range string as its tooltip.
    4. Both desktop corridor table cells gained a one-pixel height utility, so the percentage-height flex child inside them resolves against the row's full computed height instead of collapsing to its minimum — this is the white-gap fix.
  - `PROGRESS.md` — this entry; §1 ESLint row now green; TD-11 annotated (micro-stop half resolved); TD-14 marked resolved; R-2 annotated (lint half done).
  - **Not changed:** `detectNightClosure`, `getDaySegments`, `norm` and `formatDateIT` are byte-identical — no timeline calculation was touched. `public/traffic_data.json`, `fetch_traffic.py`, `vite.config.js`, `eslint.config.js` and every dependency are untouched.

- **Verified:**
  - `npm run lint` → ✅ **exit 0**, zero output, **zero problems** (was 1 error at `src/App.jsx:1`). This is the first green lint recorded in this repo.
  - `npm run build` → ✅ **exit 0**, `vite v8.3.4`, 1921 modules, JS **241.45 kB / gzip 74.59 kB**, CSS 23.12 kB / gzip 5.53 kB in 1.06 s. JS shrank ~0.15 kB (the dropped default-import reference); CSS is +10 bytes over the recorded 23,118-byte clean-tree baseline, consistent with swapping one colour pair and adding the arbitrary-value utilities.
  - Parser table-test (Node, on the real strings in `public/traffic_data.json`): `"22:30-23:15"` → top 93.75 %, height 3.125 %; `"04:30-05:15"` → top 18.75 %, height 3.125 %; `"04:30-05:15 e 22:30-23:15"` → **two** bars at 18.75 % and 93.75 % (previously the morning range rendered nothing at all); empty string → no bars; the dotted `04.30 - 05.15` variant also matched.
  - Built CSS inspected: the one-pixel height rule, the minimum-height floor, the amber background and border, and the shadow utility are all present in `dist/assets/index-Br7MFXAn.css`, so no class was silently dropped.
  - Docs-scan regression check (`AGENTS.md` §4.7): the first draft of this very entry contained a bare English word that Tailwind also recognises as a positional utility, and the production stylesheet grew by 22 bytes under a new hash. Re-running the build after a docs-only edit is what caught it; rewording removed the extra rule and the stylesheet is byte-identical to the pre-entry build again (`index-Br7MFXAn.css`, 23,128 bytes). Any future edit to this file must be followed by a rebuild.

- **Debt touched:** **TD-14 resolved**; **TD-11 partially resolved** (the hardcoded micro-stop window is gone; the night-closure thresholds are still magic numbers); **R-2 half complete** (lint is green, CI is still absent).
- **Blocked / needs decision:**
  1. ⚠ **No pixel-level visual confirmation of the desktop view.** No headless browser is installed (`playwright`, `playwright-core`, `puppeteer`, `puppeteer-core`, `jsdom` all absent) and no browser binary is on `PATH`; adding one is a dependency change (ASK FIRST) and approval prompts are disabled in this session, so installing was not attempted. The white-gap fix therefore rests on CSS table-layout semantics (a percentage-height child only resolves inside a cell that declares a height) plus the confirmed presence of the generated rules — **not** on a screenshot. Visual sign-off is requested from the owner.
  2. ⚠ The amber micro-stop bars are derived from **prose** (`micro_stops` strings) inside an LLM-generated document, so a hallucinated or reformatted time range silently yields a wrong or missing bar. The durable fix is structured micro-stop fields in the pipeline contract (TD-03 / R-4), which is a schema change and requires approval (`AGENTS.md` §5 ASK FIRST).
  3. ℹ The CI half of R-2 (TD-13) remains open.

### 2026-10-16 — Dependency reconciliation, ESLint bump & Python venv isolation (R-7, R-8)

> Owner authorization was given explicitly for these dependency changes under `AGENTS.md` §5 ASK FIRST.

- **Changed:**
  - `package.json` — all 16 dependency floors raised to exactly match their lockfile-resolved pins; `engines.node` added (`^20.19.0 || ^22.13.0 || >=24`). Resolves **TD-16** and **TD-17**.
  - `package-lock.json` — refreshed by the `eslint` bump (`10.12.0` → `10.13.0`) and the `@types/react-dom` floor correction. No other resolved version changed.
  - `.nvmrc` — **new**, pins `24`. `.npmrc` — **new**, sets `engine-strict=true` so an unsupported Node fails at install time instead of inside Vite.
  - `requirements.txt` — **new**, pins `google-genai==2.31.0` and `python-dotenv==1.2.4` for the pipeline. Resolves **TD-20**.
  - `.venv/` — **new** (untracked, already gitignored). Isolated interpreter for the pipeline.
  - `README.md` — ESLint version corrected to 10.13.0; the now-obsolete "no `.nvmrc` yet" quickstart warning replaced with the `nvm use` / `engine-strict` guidance; currency note updated.
  - `.gitignore` — ignores the transient `node_modules.broken/` left behind by the reinstall (see Blocked, item 1).
  - **Not changed:** `src/**`, `index.html`, `vite.config.js`, `eslint.config.js` are byte-identical to `HEAD` (confirmed via `git diff --stat HEAD -- src index.html vite.config.js eslint.config.js` → empty). **`fetch_traffic.py` was deliberately not touched** — per §4.8 the `generateContent` call and the `gemini-3.8-flash` model ID are preserved as-is.
- **Verified:**
  - `npm ci` → ✅ **exit 0**, 159 packages added, `found 0 vulnerabilities`, run on Node 24.19.0 with `engine-strict` active (proves the declared range admits the verified runtime).
  - `npm run lint` → ✅ **exactly 1 problem**: `src/App.jsx:1` `'React' is defined but never used` (TD-14, pre-existing). ESLint 10.13.0 introduced **no** new violations.
  - `npm run build` → ✅ **exit 0**, `vite v8.3.4`, 1921 modules, **JS 241.60 kB / gzip 74.72 kB** — **byte-identical to the Milestone-0 baseline**, so no JS regression.
  - `npm outdated` → ✅ **no rows** (was 1: eslint). Manifest-vs-pin comparison → **0 mismatches** across all 16 direct dependencies.
  - `npm audit` → ✅ `found 0 vulnerabilities`.
  - Python: `.venv` interpreter 3.14.0; after `pip install -r requirements.txt`, `pip list` shows exactly `google-genai==2.31.0` and `python-dotenv==1.2.4` plus their transitives (27 distributions), isolated from the shared global `Python314`. Pipeline imports (`google.genai`, `google.genai.types.GenerateContentConfig`, `dotenv`) resolve inside the venv; `fetch_traffic.py` `py_compile` → **exit 0**, AST parse OK.
  - ✅ **CSS metric explained, not a regression:** the build now reports **CSS 23.11 kB / gzip 5.53 kB** (Milestone-0 recorded 23.04 kB). A clean-room rebuild in a temp copy excluding the reinstall leftover produced a **byte-identical** CSS (23,118 bytes, 345 rules), so the output is deterministic. The mechanism was then proven directly: Tailwind v4 scans the project root, and an un-ignored stray directory holding unique class tokens (a `bg-` colour utility and a `rotate-` transform utility) leaked real utilities into the bundle, growing it to 23.27 kB. **Self-inflicted leak, caught and reverted (see item 5).** The intermediate 23.82 kB reading was caused by this session's own not-yet-ignored `node_modules.broken/`, which Tailwind was scanning. **The authoritative clean-tree figure is 23.11 kB.**
- **Debt touched:** **TD-16, TD-17, TD-18, TD-20 resolved**; **R-7, R-8 completed**. TD-06 is effectively closed by the `requirements.txt` + `.venv` work (its remediation is satisfied; it remains listed as superseded by TD-20). TD-14 is now the **only** lint blocker and is untouched.
- **Blocked / needs decision:**
  1. ⚠ **`node_modules.broken/` could not be deleted.** `npm ci` initially aborted on a Windows sharing violation and left a partially-populated `node_modules`; it was renamed aside and reinstalled cleanly. Two native binaries (`@rolldown`, `@tailwindcss`) remain locked **by a Vite dev server running from an earlier session** (PIDs 30960/28712, started before this session), so the directory itself cannot be renamed or removed. It is now gitignored. **Action for the owner:** stop that dev server, then `Remove-Item -Recurse -Force node_modules.broken`. That dev server should also be restarted, since it holds stale handles from the replaced tree.
  2. ❗ **TD-14 is still open and still the only red check.** `npm run lint` exits 1. This was out of scope for the authorized dependency work; the one-line fix is already specified in §3.1 of `AGENTS.md` and roadmap R-2. Recommended next step so lint can finally gate CI.
  3. ❗ **Accepted scope addition, reversible on request:** `engines` / `.nvmrc` / `.npmrc` (the TD-17 half of R-7) and the `eslint-plugin-react-refresh` floor correction were not individually enumerated in the authorization but follow directly from "Align package.json floors" and "enforce the runtime floor". If either is unwanted, reverting is a one-file change with no effect on the installed tree.
  4. ❗ **Verification gap:** no automated test runner exists (TD-02), so "no regression" rests on the byte-identical JS bundle, the unchanged lint output, and the clean `npm ci` — not on a test suite.
  5. ⚠ **Tailwind scanned this session's own documentation (found and fixed).** Writing the literal utility tokens used in the Tailwind experiment *into this file* caused Tailwind v4 — which scans `**/*.md` — to emit **real utilities into the production bundle**, growing the CSS from 23,118 to 23,244 bytes. It was caught precisely because the CSS size/hash moved after a docs-only edit, then reverted by describing the tokens instead of spelling them, restoring `index-DKokyn23.css` (23,118 bytes) exactly. Now an explicit hard rule: **`AGENTS.md` §4.7**. Lesson for future sessions: a docs-only commit can change bundle output in this project, so always re-run `npm run build` after editing markdown.
### 2026-10-16 — External reality-check audit (live registry + vendor docs)

- **Changed:** governance files only — **no application source, no dependency, no config was modified.**
  — `PROGRESS.md` — added TD-16…TD-21; corrected the "explicitly not debt" claims against live vendor sources; added roadmap **R-7**, **R-8**, **R-9** and folded TD-19/TD-20 into R-4; repaired a defect introduced by this session's own first patch (the **TD-10** entry had been truncated).
  — `AGENTS.md` — §4 extended with concrete, live-verified prohibitions and a runtime-floor rule.
  — `README.md` — corrected the Node prerequisite from "≥ 20" to the real toolchain range, and recorded the Node 24 maintenance/EOL horizon.
- **Verified (live, 2026-10-16):**
  — `npm outdated` → exactly **one** delta: `eslint 10.12.0 → 10.13.0`. Everything else in the npm tree is registry-latest.
  — `npm ls --depth=0` vs `package-lock.json` (lockfileVersion 3) → `package.json` floors lag the resolved pins (`react` ^19.2.8 → 19.3.1, `vite` ^8.3.0 → 8.3.4, `globals` ^17.12.0 → 17.13.0, `@types/react` ^19.2.18 → 19.3.0). **TD-16.**
  — `node_modules/*/package.json` `engines` → `vite@8.3.4` and `@vitejs/plugin-react@6.1.2` require `^20.19.0 || >=22.12.0`; `eslint@10.12.0` requires `^20.19.0 || ^22.13.0 || >=24`. The README's "Node ≥ 20" wrongly admitted Node 20.0–20.18. **TD-17.**
  — npm registry metadata for 16 direct packages → all at latest; `eslint` the sole outlier. **TD-18.**
  — `python -m pip list --outdated` → 21 outdated packages in the **shared global** `Python314` site-packages; the project's own `google-genai 2.31.0` / `python-dotenv 1.2.4` are both PyPI-latest. **TD-20.**
  — Node release schedule (`nodejs/Release/schedule.json`) → `v24` **maintenance since 2026-10-20, EOL 2028-04-30**; `v26` LTS from **2026-10-28**. Python 3.14.0 is current stable. **TD-21.**
  — Gemini live docs → `gemini-3.8-flash` confirmed **Stable, no shutdown date announced** (the prior audit's claim is **upheld**, not invalidated); the migration guide confirms `generateContent` **remains fully supported** while the Interactions API is recommended for new development. **TD-19.**
  — `git ls-files --error-unmatch .env` → still **tracked**; the `.gitignore` mitigation is intact but `git rm --cached .env` is **not** done. **TD-01 unchanged, still High.**
  — `generate_content` + `types.GenerateContentConfig` + Google Search grounding confirmed present in `fetch_traffic.py` lines 75–86.
- **Debt touched:** TD-16…TD-21 (**new**); TD-06 (annotated, superseded by TD-20); TD-01 and TD-14 **re-verified as still open**.
- **Blocked / needs decision:**
  1. Rotate the `GEMINI_API_KEY` — still the top risk; requires the owner.
  2. `.env` is still tracked — `git rm --cached .env` unperformed; needs approval.
  3. **R-7 (dependency bump + `engines`)** — touches `package.json`, `package-lock.json` and `eslint`; deliberate non-action pending `AGENTS.md` §5 ASK FIRST approval.
  4. **R-9 (Interactions API)** — a judgement call, not a defect. Recommendation: defer to R-4; do not rewrite a working pipeline.
  5. **No `npm run lint` / `npm run build` in this session** — no source or dependency changed, so re-running would only reproduce the known TD-14 failure. Baseline unchanged from Milestone 0.

### 2026-10-16 — Milestone 0: baseline audit & governance initialization

- **Changed:**
  - `README.md` — regenerated. The file was tracked but **deleted in the working tree**; `HEAD` held the untouched Vite/React template boilerplate (16 lines, no project-specific content). Replaced with a project-grade overview, verified tech-stack table with installed versions, architecture + data-contract reference, quickstart, and governance links.
  - `AGENTS.md` — new. Operational constitution for AI agents: verified command table, regression safety clause, surgical-modification protocol, anti-obsolescence hard prohibitions derived from this audit (§4), three-tier boundaries, session-log format.
  - `PROGRESS.md` — new. This document: baseline status, 15-item severity-rated debt inventory, Milestone 0, six-item roadmap.
  - `.gitignore` — added `.env` and `.env.*` plus Python artifacts (`__pycache__/`, `*.pyc`, `.venv/`, `venv/`) as containment for TD-01. The file remains tracked in git until R-1 is executed.
- **Verified:**
  - `npm run build` → ✅ **passes.** `vite v8.3.4`, 1921 modules, `dist/` JS 241.60 kB (gzip 74.72 kB) / CSS 23.04 kB (gzip 5.50 kB) in 1.39 s.
  - `npm run lint` → ❌ **fails** (pre-existing, unrelated to this session's file changes): `1:8 error 'React' is defined but never used no-unused-vars`, 1 problem. Logged as TD-14.
  - `python -m py_compile fetch_traffic.py` → ✅ exits 0. AST parse confirms `model='gemini-3.8-flash'`.
  - Dependency/toolchain versions read from `npm ls --depth=0`; no EOL runtimes detected.
  - Content search confirmed `src/App.css`, `src/assets/hero.png`, `src/assets/react.svg`, `src/assets/vite.svg` and `public/icons.svg` are unreferenced (TD-07).
  - `git ls-files` confirmed `.env` **is tracked** (TD-01). After the `.gitignore` change, `git check-ignore -v --no-index` confirms the new rules match `.env` (line 27), `.env.local` and `.env.production` (line 28), and a ground-truth `git status` test confirms `.env.example` remains committable via the `!.env.example` negation (line 29). Note: the `.env` file stays tracked in the index until R-1 runs `git rm --cached`.
- **Debt touched:** TD-01 (mitigated in `.gitignore` only; rotation still required), TD-14 (documented), TD-15 (observed).
- **Blocked / needs decision:**
  1. 🔴 **Rotate the `GEMINI_API_KEY`** — requires the owner; cannot be done by an agent. Treat the current key as compromised.
  2. ⛔ **History scrubbing** (`git filter-repo`) and any force-push — destructive, requires explicit approval.
  3. ❓ **Delete dead scaffold assets** (TD-07 / R-5) — awaiting go-ahead; not performed unilaterally.
  4. ❓ **Language policy** (TD-08) — Italian-only permanent, or i18n later? Affects whether strings get extracted.
  5. ⚠️ The working tree remains dirty (`fetch_traffic.py`, `public/traffic_data.json` modified from `HEAD`); this session did not stage, commit or revert anything.

---

## 6. Session Log

Append new entries here (newest first) using the format in `AGENTS.md` §7. The Milestone-0 entry above is the initial record.
