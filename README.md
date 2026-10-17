# Tunnels Control Tower

A logistics control-tower dashboard for heavy-goods transport across the **Western Alps transalpine corridors** — the Fréjus axis (A43 / T4 / A32) and the Mont Blanc axis (A40 / TMB / A5 / RN205).

It answers one operational question for a refrigerated 5-axle semi-trailer: **when is each tunnel corridor closed over the next 30 days, and when is the next blocking window?** Traffic status is researched from official motorway and tunnel operators, normalised into a day-by-day JSON contract, and rendered as a 30-day rolling board with a 24-hour closure timeline per corridor.

> **Status:** functional prototype / baseline `v0.0.0`. See [`PROGRESS.md`](./PROGRESS.md) for the health audit, known technical debt, and roadmap.

## Key Features

- **30-day rolling board** — one row per day across both corridors, with the current day highlighted.
- **Quick Status bar** — the next imminent blocking window for each axis, at a glance.
- **24-hour Timeline Ribbon** — each day renders a proportional midnight-to-midnight strip (green = open, red = closed), so overnight closures are visible at a glance and carry over into the following morning.
- **Night-closure inference** — parses `21:00-06:00`-style windows (and `notturn` / `nuit` keywords) out of operator free text to reconstruct the early-morning closure span.
- **Micro-stop marking** — technical 45-minute construction windows (e.g. Fréjus Tube 1 works) highlighted separately from full closures.
- **Per-axis filtering** — All / Fréjus only / Mont Blanc only.
- **Full-text search** — across titles, details, micro-stops, dates and weekday names.
- **Responsive layout** — continuous table on desktop, stacked cards on mobile.
- **Status taxonomy** — `REGOLARE` · `RESTRIZIONE` · `BLOCCO_TOTALE` rendered as colour-coded badges.
- **Official source links** — SFTRF, SITAF, APRR, TMB-GEIE, ATMB, RAV S.p.A., SAV S.p.A., CCISS, Bison Futé.

## Tech Stack

| Layer | Technology | Version (installed) |
| --- | --- | --- |
| UI runtime | [React](https://react.dev) | 19.3.1 |
| UI runtime | [React DOM](https://react.dev) | 19.3.1 |
| Build tool / dev server | [Vite](https://vite.dev) | 8.3.4 |
| React integration | [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react) (Oxc) | 6.1.2 |
| Styling | [Tailwind CSS](https://tailwindcss.com) | 4.3.3 |
| Styling | [@tailwindcss/vite](https://tailwindcss.com/docs/installation/using-vite) | 4.3.3 |
| Icons | [lucide-react](https://lucide.dev) | 1.58.0 |
| Linting | [ESLint](https://eslint.org) (flat config) | 10.13.0 |
| Linting | [eslint-plugin-react-hooks](https://www.npmjs.com/package/eslint-plugin-react-hooks) | 7.1.1 |
| Linting | [eslint-plugin-react-refresh](https://www.npmjs.com/package/eslint-plugin-react-refresh) | 0.5.7 |
| Data pipeline | [Python](https://www.python.org) | 3.14.0 |
| Data pipeline | [google-genai](https://googleapis.github.io/python-genai/) (Gemini API) | 2.31.0 |
| Data pipeline | [python-dotenv](https://pypi.org/project/python-dotenv/) | 1.2.4 |

There is **no backend, no database and no authentication**. The application is a fully static client-side bundle.

> **On these version numbers:** they are the versions **actually resolved in `package-lock.json` / installed**, verified live on **2026-10-16**. They are *not* read from the `^` ranges in `package.json`, which lag behind the resolved pins (see **TD-16** in [`PROGRESS.md`](./PROGRESS.md)).
> **Live currency check (2026-10-16):** every npm dependency above is at the latest published version — `npm outdated` reports **no** rows (ESLint was bumped `10.12.0` → `10.13.0` under **TD-18**/R-7). Both Python packages are at PyPI-latest and now install into the isolated `.venv` (**TD-20**).

## Architecture

```
fetch_traffic.py                 Offline data-collection script (run manually)
        │  Gemini 3.8 Flash + Google Search grounding
        ▼
public/traffic_data.json         Static data contract, committed to the repo
        │  fetch('./traffic_data.json')  ← relative path, resolved against base
        ▼
src/App.jsx                      Dashboard: filters, timeline math, desktop table + mobile cards
```

Operator emblems live in `public/logos/` (`sftrf.png`, `tmb.png`). `src/App.jsx` references
them with relative `./logos/...` URLs, so Vite copies them verbatim into `dist/logos/` and
the same path works in dev and on GitHub Pages.

### Data contract (`public/traffic_data.json`)

```jsonc
{
  "last_updated": "YYYY-MM-DD HH:mm",
  "quick_status": {
    "frejus_next_block": "string",
    "monte_bianco_next_block": "string"
  },
  "days": [
    {
      "date": "YYYY-MM-DD",
      "day_name": "Venerdì",
      "is_today": true,
      "frejus":       { "status": "REGOLARE|RESTRIZIONE|BLOCCO_TOTALE",
                        "title": "string", "details": "string", "micro_stops": "string" },
      "monte_bianco": { "status": "REGOLARE|RESTRIZIONE|BLOCCO_TOTALE",
                        "title": "string", "details": "string", "micro_stops": "string" }
    }
  ]
}
```

## Prerequisites

- **Node.js** `^20.19.0 || ^22.13.0 || >=24` — verified on **v24.19.0** — and **npm** ≥ 10 (verified on **11.17.0**).
  — This is a **hard floor, not a preference.** Vite 8 and `@vitejs/plugin-react` require `^20.19.0 || >=22.12.0`, and ESLint 10 requires `^20.19.0 || ^22.13.0 || >=24`. **Node 20.0–20.18 will not work** → use Node 20.19+, 22.13+ or 24+.
  — **Lifecycle:** Node 24 is the active LTS and is supported until **2028-04-30**; it moves to maintenance once Node 26 becomes LTS on **2026-10-28**. No EOL exposure today. *(Verified 2026-10-16 against the official [Node release schedule](https://github.com/nodejs/Release).)*
- **Python** ≥ 3.10 (verified on **3.14.0**, the current stable line) — only needed to refresh the traffic data.

## Quickstart

```bash
# 0. Confirm you are on a supported Node runtime (see Prerequisites).
#    Node 20.0-20.18 will fail inside Vite. `nvm use` reads .nvmrc (24);
#    `engine-strict` in .npmrc makes npm reject an unsupported runtime.
#    Expected range: ^20.19.0 || ^22.13.0 || >=24
node --version

# 1. Install frontend dependencies (use `npm ci` on a clean checkout)
npm install

# 2. Start the dev server
npm run dev
```

The dashboard reads the committed `public/traffic_data.json`, so no API key is required to run the UI.

### Refreshing the traffic data (optional)

The data pipeline calls the Gemini API with Google Search grounding. It requires a `GEMINI_API_KEY`.

```bash
# 1. Create a .env file in the repository root
GEMINI_API_KEY=your_key_here

# 2. Install the pinned Python dependencies into a DEDICATED virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
python -m pip install -r requirements.txt

# 3. Regenerate public/traffic_data.json
python fetch_traffic.py
```

> ⚠️ **Never commit `.env`.** The key must be treated as a secret and rotated if it is ever exposed.
>
> ⚠️ **Always use the `.venv` above.** It pins `google-genai==2.31.0` and `python-dotenv==1.2.4` (TD-20); the shared global `Python314` site-packages belongs to unrelated projects and drifts independently. CI installs the same pinned `requirements.txt` and injects `GEMINI_API_KEY` from repository secrets, so no `.env` is needed there.

## Available Scripts

| Command | Description |
| --- | --- |
| `npm run dev` | Start the Vite dev server with HMR |
| `npm run build` | Production build into `dist/` |
| `npm run preview` | Serve the production build locally |
| `npm run lint` | Run ESLint across the repository |
| `python fetch_traffic.py` | Regenerate `public/traffic_data.json` |

> There is **no test runner and no type-checker** configured in this repository. Both are tracked as debt in [`PROGRESS.md`](./PROGRESS.md).

## Deployment

`vite.config.js` sets `base: './'` so the build emits relative asset URLs, which makes `dist/` deployable to a static host at any sub-path (e.g. GitHub Pages).

Deployment is automated by [`.github/workflows/deploy.yml`](./.github/workflows/deploy.yml). A single job runs five times a day (fixed UTC crons covering the Italian dispatch windows) and on manual `workflow_dispatch`:

1. installs `requirements.txt`, then regenerates `public/traffic_data.json` with `GEMINI_API_KEY` injected from repository secrets (`TZ=Europe/Rome`, so `last_updated` stays Italian local time);
2. commits the fresh snapshot back to the branch as `github-actions[bot]` (`[skip ci]`), so git history records the real data over time;
3. runs `npm ci`, `npm run lint` and `npm run build`;
4. publishes `dist/` through the official Pages actions (`configure-pages`, `upload-pages-artifact`, `deploy-pages`).

### One-off setup (GitHub UI)

- **Settings → Pages → Build and deployment → Source: GitHub Actions.** `configure-pages` fails if Pages is still on "Deploy from a branch".
- **Settings → Secrets and variables → Actions → New repository secret:** `GEMINI_API_KEY`.
- The repository should be **public** to stay within the free Actions-minutes and Pages tiers.
- Leave the `github-pages` environment without required reviewers, or scheduled runs will queue instead of deploying.
- The workflow must be on the **default branch** (`main`) before the schedule fires or the *Run workflow* button appears.

> **DST caveat:** the crons are fixed UTC. Italy is UTC+1 in winter (CET) and UTC+2 in summer (CEST), so every run fires one hour later in local time from late March to late October.

## Project Governance

- [`AGENTS.md`](./AGENTS.md) — operational contract for AI coding agents working in this repository.
- [`PROGRESS.md`](./PROGRESS.md) — baseline health audit, technical-debt inventory, and roadmap.

## Data Sources

All traffic information is derived from official operator publications. This project is an independent aggregator and is not affiliated with any operator.

| Operator | Corridor | Source |
| --- | --- | --- |
| SFTRF | Fréjus / A43 | <https://www.sftrf.fr> |
| SITAF | T4 / A32 | <https://www.sitaf.it> |
| APRR | A43 (France) | <https://www.aprr.fr> |
| TMB-GEIE | Mont Blanc | <https://www.tunnelmb.net/it-IT/interruzioni-e-previsioni> |
| ATMB | A40 / RN205 | <https://www.atmb.com> |
| RAV S.p.A. | A5 (Aosta - Mont Blanc) | <https://www.ravspa.it> |
| SAV S.p.A. | A5 (Quincinetto - Aosta) | <https://www.sav-a5.it> |
| CCISS | Italy (national emergency) | <https://www.cciss.it> |
| Bison Futé | France (national emergency) | <https://www.bison-fute.gouv.fr> |

## License

No license file is currently present. Until one is added, this repository is **all rights reserved** by default.
