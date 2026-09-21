# LILA BLACK - Player Journey Visualization Tool

A browser-based tool for the Level Design team to explore player behavior on LILA BLACK's maps: movement paths, kills/deaths/loot/storm events, human-vs-bot distinction, match playback, and heatmaps (traffic, kill zones, death zones - aggregated across all matches on a map).

**Live demo:** https://shreyahhh.github.io/lila-black-player-journey-viewer/ - lands on a landing page with a big "Open the Map Viewer" button, plus an in-app **Documentation** page (also linked from the top-right of the viewer itself).

## How to use it (feature walkthrough)

0. **Landing page** (`index.html`) - a hero page introducing the tool with one obvious call to action: **Open the Map Viewer**. Also links to the in-app documentation page.
1. **Map** - pick one of the 3 maps (AmbroseValley, GrandRift, Lockdown). Loads that map's real minimap image.
2. **Date** - narrows to matches played on that day (only dates that actually have matches for the selected map are listed).
3. **Match** - pick a specific match; the dropdown label shows `<match id>  (Xh/Yb, Zs)` - human count, bot count, duration - so you can spot an interesting match (e.g. lots of bots, or a long match) without opening it first.
4. **Map view** - every player/bot's full movement path is drawn immediately: **blue = human, gray = bot**. Colored dots mark discrete events - hover any dot for a tooltip (event type + human/bot + id):
   - 🟢 green = kill, 🔴 red = death/killed, 🟣 purple = storm death, 🟡 yellow = loot pickup
5. **Timeline (bottom bar)** - drag the scrubber to jump to any point in the match, or hit ▶ to play it back (speed adjustable: 1x/2x/5x/10x). White-bordered circles show each player's live position at the current timestamp, interpolated between their recorded samples.
6. **Heatmap dropdown** - five modes:
   - **Off** / **This match (positions)** - just the currently-loaded match's movement density
   - **All matches on map - traffic / kill zones / death zones** - aggregated across *every* match ever played on that map, precomputed by the pipeline. This is the view that actually answers "where do fights happen" / "where do people die" / "which areas get ignored" - a single match is too sparse to show a real pattern.

## Tech stack

- **Preprocessing:** Python 3, `pyarrow` (read Parquet), `Pillow` (read real minimap dimensions) - no `pandas` dependency
- **Frontend:** static HTML/JS, [Leaflet](https://leafletjs.com/) (`L.CRS.Simple` for the non-geographic minimap coordinate system) + [Leaflet.heat](https://github.com/Leaflet/Leaflet.heat) - no build step, no framework
- **Hosting:** static site (GitHub Pages) - the whole app is `index.html` (landing) + `viewer.html` (the tool) + `docs.html` (documentation) + `minimaps/` + `data/`, no server, no database, no env vars

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install pyarrow pillow

# Regenerate data/ from the raw parquet files
cd pipeline
python preprocess.py --src "<path to player_data/player_data>" --out "../data"
```

No environment variables are required - everything is static files.

## Running locally

```bash
# from the repo root
python -m http.server 8000
# open http://localhost:8000/          -> landing page
# open http://localhost:8000/viewer.html -> the tool directly
# open http://localhost:8000/docs.html   -> documentation
```

(A plain `file://` open won't work because the viewer `fetch()`s JSON - needs to be served over HTTP.)

## Deploying

100% static - drag the repo root onto Vercel/Netlify, or serve directly via GitHub Pages (Settings → Pages → deploy from `main` / root). No build step, no config.

## Project structure

```
├── index.html             # landing page (hero + "Open the Map Viewer" CTA)
├── viewer.html            # the tool itself
├── docs.html              # in-app documentation page
├── minimaps/              # minimap images (AmbroseValley, GrandRift, Lockdown)
├── assets/                # LILA Games logo, favicon, hero background
├── pipeline/
│   └── preprocess.py      # raw parquet -> data/*.json (coordinate transform, ts fix, bot/human tagging)
├── data/                   # generated: one JSON per match + index.json + per-map _aggregate.json (do not hand-edit)
├── README.md                (this file)
├── ARCHITECTURE.md           # data flow, coordinate mapping walkthrough, assumptions, tradeoffs
├── INSIGHTS.md               # data-driven findings for the level design team
├── DOCS.md                   # extended docs: tech stack rationale, product decisions, production roadmap
└── RESEARCH.md               # pre-build research notes on approaches/libraries considered
```

See [DOCS.md](DOCS.md) for the fuller picture - tech stack rationale, product decision reasoning, and what would change if this became a permanent production tool.
