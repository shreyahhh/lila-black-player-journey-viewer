# LILA BLACK — Player Journey Visualization Tool

A browser-based tool for the Level Design team to explore player behavior on LILA BLACK's maps: movement paths, kills/deaths/loot/storm events, human-vs-bot distinction, match playback, and heatmaps (traffic, kill zones, death zones — aggregated across all matches on a map).

**Live demo:** https://shreyahhh.github.io/lila-black-player-journey-viewer/

## Tech stack

- **Preprocessing:** Python 3, `pyarrow` (read Parquet), `Pillow` (read real minimap dimensions) — no `pandas` dependency
- **Frontend:** static HTML/JS, [Leaflet](https://leafletjs.com/) (`L.CRS.Simple` for the non-geographic minimap coordinate system) + [Leaflet.heat](https://github.com/Leaflet/Leaflet.heat) — no build step, no framework
- **Hosting:** static site (GitHub Pages) — the whole app is `index.html` + `minimaps/` + `data/`, no server, no database, no env vars

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install pyarrow pillow

# Regenerate data/ from the raw parquet files
cd pipeline
python preprocess.py --src "<path to player_data/player_data>" --out "../data"
```

No environment variables are required — everything is static files.

## Running locally

```bash
# from the repo root
python -m http.server 8000
# open http://localhost:8000/
```

(A plain `file://` open won't work because the viewer `fetch()`s JSON — needs to be served over HTTP.)

## Deploying

100% static — drag the repo root onto Vercel/Netlify, or serve directly via GitHub Pages (Settings → Pages → deploy from `main` / root). No build step, no config.

## Project structure

```
├── index.html             # the tool itself
├── minimaps/              # minimap images (AmbroseValley, GrandRift, Lockdown)
├── pipeline/
│   └── preprocess.py      # raw parquet -> data/*.json (coordinate transform, ts fix, bot/human tagging)
├── data/                   # generated: one JSON per match + index.json + per-map _aggregate.json (do not hand-edit)
├── README.md                (this file)
├── ARCHITECTURE.md           # data flow, coordinate mapping walkthrough, assumptions, tradeoffs
└── INSIGHTS.md               # data-driven findings for the level design team
```
