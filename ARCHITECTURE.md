# Architecture

## What this is built with, and why

- **Preprocessing: Python (pyarrow + Pillow), no pandas dependency in the final pipeline.** The raw data is 1,243 small Parquet files (~6MB total) that need per-row transforms and per-match grouping — a one-time offline script is simpler and more debuggable than doing this in the browser, and it means the frontend never touches Parquet, binary-encoded columns, or Arrow at all.
- **Frontend: static HTML + Leaflet (`L.CRS.Simple`) + Leaflet.heat, no build step.** A Level Designer opens a URL — there's no backend to keep alive, no server cost, and Leaflet's non-geographic CRS mode is the standard, well-trodden tool for exactly this "world coordinates on a static image" problem (used across the PUBG/GTA/Rust map-tooling community).
- **Hosting: static file host (Vercel/Netlify/GitHub Pages).** Output of preprocessing is ~5.4MB of JSON — small enough to commit and serve directly, no database or API needed.

## Data flow

```
player_data/{day}/*.nakama-0  (1,243 Parquet files)
        │
        ▼  pipeline/preprocess.py
        │   - decode `event` bytes → string
        │   - classify user_id → human (UUID) or bot (numeric)
        │   - world (x,z) → pixel (px,py) via verified per-map transform
        │   - fix `ts` encoding bug → match-relative seconds
        │   - group rows by match_id, then by user_id within match
        ▼
data/{map_id}/{match_id}.json   (796 files, one per match)
data/index.json                 (filter index: map × date × match)
        │
        ▼  index.html  (fetch + Leaflet)
        │   - dropdowns filter index.json → pick a match file
        │   - render path (polyline) + event markers per player
        │   - timeline scrubber interpolates position at time t
        │   - heatmap layer over raw position points
        ▼
Level Designer's browser
```

## Coordinate mapping — verified, not assumed

The README states the transform and per-map `scale`/`origin` values, and gives one worked example. Rather than trust it blindly, I loaded the real dataset and validated it end-to-end before building anything on top:

1. **The formula is correct.** For all 89,104 rows across all 3 maps, `100%` of computed pixel coordinates land inside the map image bounds — no clipping, no out-of-range points.
2. **The README's claimed minimap size (1024×1024) is wrong for the actual asset files:**

   | Map | README claims | Actual measured size |
   |---|---|---|
   | AmbroseValley | 1024×1024 | **4320×4320** |
   | GrandRift | 1024×1024 | **2160×2158** (not even square) |
   | Lockdown | 1024×1024 | **9000×9000** |

   Fix: the pipeline reads each image's real dimensions with Pillow at runtime and uses `width`/`height` independently in the formula (`pixel_x = u * width`, `pixel_y = (1-v) * height`) instead of a hardcoded constant. This makes GrandRift's 2-pixel non-square asymmetry a non-issue rather than a hidden bug.
3. **Visual validation, per map:** rendered every player's full path over its real minimap in the viewer (see `index.html`) for all three maps. Paths trace roads and hug buildings exactly as expected; no axis flips or scale errors visible on any of the three maps, including the non-square GrandRift image.

**The transform itself** (from README, confirmed correct):
```
u = (x - origin_x) / scale
v = (z - origin_z) / scale
pixel_x = u * image_width
pixel_y = (1 - v) * image_height   # Y flip: world Z grows away from image top, pixels grow down
```
Only `x` and `z` are used for the 2D map; `y` is elevation and is carried through as metadata (useful for e.g. distinguishing multi-story positions later, not currently visualized).

## Assumptions / data issues found and how they were handled

| Issue | What we found | How handled |
|---|---|---|
| Minimap image size | README says 1024×1024; real files are much larger and GrandRift isn't square | Read actual image dimensions at runtime, never hardcode 1024 |
| `ts` column | Parquet types it `timestamp[ms]` and README calls it "match-relative elapsed time"; neither is right. The raw int64, decoded as Unix-epoch **seconds**, lands on real dates inside Feb 10–14 2026 (the dataset's actual collection window) — decoded as milliseconds (the declared type) it lands on 1970-01-21, which is nonsense | Read the raw int64 directly, treat as epoch seconds, then convert to match-relative seconds (`t - match_start`) for playback — sidesteps the mislabeling entirely since only relative ordering matters for the tool |
| Human/bot detection | Event name (`Position` vs `BotPosition` etc.) is **not reliable** — bot `user_id`s were found emitting plain `Position` and `Loot` events, not just `Bot*` events | Classify strictly by `user_id` format (UUID regex vs. numeric), exactly as the README's filename convention describes, and ignore event-name prefixes for this purpose |
| Multiple maps per match | Verified 0 matches reference more than one `map_id` — grouping by `match_id` alone is safe | No special handling needed |
| Missing/garbled rows | 0 nulls, 0 NaN/Inf in x/y/z across all 89,104 rows; all 1,243 files parsed without error | No filtering/cleanup step needed beyond decoding `event` bytes |

## Major tradeoffs

| Decision | Alternative considered | Why this way |
|---|---|---|
| Preprocess to static JSON, no backend | In-browser Parquet parsing (DuckDB-Wasm) | Isolates the risky coordinate/ts/bot-detection logic in one debuggable, testable offline script; keeps the frontend trivially simple and hosting free |
| Leaflet + CRS.Simple | deck.gl | Leaflet is lighter-weight and has the most direct precedent for exactly this use case (non-geographic image + point/path overlays); deck.gl's WebGL performance headroom isn't needed at this data scale (≤ a few thousand points per match) |
| One JSON file per match | One giant JSON for all matches | Keeps initial page load small; a Level Designer only ever looks at one match at a time |
| Precompute per-map aggregate heat points (`_aggregate.json`) in the pipeline | Fetch and concatenate all per-match files client-side | A single match has too few points to show a meaningful zone; precomputing once at build time avoids downloading hundreds of match files just to render one heatmap (AmbroseValley alone has 566 matches) |
