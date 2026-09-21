# Research: Player Journey Visualization Tool (LILA Games take-home)

Working reference doc for approach selection. Not application code. Written before `player_data.zip` is extracted, so data-handling guidance is technique-focused, not schema-specific.

---

## Executive Summary / Recommendation

**Recommended stack: Option B - Python preprocessing (polars/DuckDB) → static JSON/Arrow files + a Next.js/vanilla-JS frontend using Leaflet (`L.CRS.Simple`) or deck.gl, deployed on Vercel or Netlify.**

Why, given 10-15 hours over 5 days and "must actually work + be polished":

- **Preprocessing offline (not in-browser) removes the single biggest risk**: parquet quirks (byte-encoded columns, timestamp formats, schema surprises) are debugged once, interactively, in a notebook/script - not inside a fragile in-browser WASM pipeline you're also trying to ship. In-browser DuckDB-wasm/parquet-wasm is genuinely cool but is extra surface area for a 5-day deadline; save it as a stretch goal, not the load-bearing path.
- **A real frontend framework + Canvas/WebGL rendering (Leaflet or deck.gl)** gives you smooth pan/zoom, image-overlay coordinate mapping "for free" (CRS.Simple), and the playback scrubber UX evaluators expect - much harder to get sleek in Streamlit.
- **Static JSON/newline-delimited-JSON output is trivially hostable** on Vercel/Netlify's CDN with no backend, no database, no cold starts, and no serverless payload-size ceiling (that ceiling - ~4.5MB on Vercel functions - only matters if you route data *through* a function; static files bypass it entirely).
- Streamlit (Option C) is faster to get *something* on screen, but custom pixel-precise map overlays + a smooth scrubbed timeline + heatmaps that don't re-render janky is a fight against the framework's rerun-on-every-interaction model. It's a reasonable fallback if time runs short, not the primary bet.

If the candidate is meaningfully more comfortable in Python than JS/React, Option C is a legitimate, lower-risk alternative - see the comparison table for the honest tradeoffs either way.

---

## 1. Overall Architecture Patterns

### 1a. Pure frontend SPA + preprocessed data + Canvas/WebGL
Data is transformed once (Python script or a tiny build step) into compact JSON/Arrow/GeoJSON-like files, checked into the repo or generated at build time, then a React/Next.js or vanilla JS app renders everything client-side with Canvas or WebGL (Leaflet, deck.gl, PixiJS).

- **Pros**: fastest perceived performance (no server round-trips after load), simplest hosting (pure static + CDN), best for smooth pan/zoom/scrub interactions, easiest to make "feel" polished.
- **Cons**: all data must fit in a browser-reasonable payload (tens of MB, ideally compressed); any change to filtering logic that needs raw-row access requires either shipping more data or a light API.
- **Best when**: dataset can be aggregated/downsampled/split into per-map-per-day chunks that are each individually small, which is very plausible for 5 days of one game.

### 1b. Python data-app frameworks (Streamlit / Dash / Panel / Gradio)
Single Python process renders UI + does the data work, using pandas/polars/duckdb directly against parquet.

- **Streamlit**: `st.pydeck_chart` (wraps deck.gl!) and `st.plotly_chart` (Plotly `go.Scattermapbox`/`go.Image` layering) are the two realistic paths to a custom minimap overlay. Community reports (see §3/§5 sources) show recurring friction: Plotly's mapbox/maplibre map layers have had version-specific breakage with Streamlit's rerun cycle, zoom/pan can lose markers, and there's no native scrubber widget - you'd build one from `st.slider` + `st.session_state` and manually re-render each frame, which reruns the whole script per frame and can feel sluggish for smooth animation.
  - `st.pydeck_chart` is actually a strong option since it gives you real deck.gl layers (ScatterplotLayer, HeatmapLayer, PathLayer) inside Streamlit - this narrows the gap with Option A considerably and is worth knowing about even in a Python-first plan.
- **Dash** (Plotly's own app framework) has finer callback control than Streamlit (no full-script rerun), making smooth scrubbers more achievable, at the cost of more boilerplate.
- **Panel** (HoloViz) is more flexible for custom layouts and works well with Bokeh/HoloViews plus a `param`-driven reactive model; steeper learning curve if unfamiliar.
- **Gradio** is optimized for ML demos (input → output), weakest fit here - not recommended.
- **Known limitation across all of these for custom image overlays**: none has a built-in "put arbitrary image as basemap with linear/CRS.Simple coordinate mapping" primitive as clean as Leaflet's; you're either abusing a geospatial map component (Mapbox/Plotly Scattermapbox needs fake lat/lon) or drawing on a Plotly `Image` trace + scatter overlay (workable, and actually a fairly clean approach - see §3).

### 1c. Full-stack: lightweight backend + static frontend
FastAPI/Node/Express serves processed/queried data (e.g., DuckDB running server-side over the parquet, or precomputed JSON with query params for filters) to a separate frontend.

- **Pros**: enables true server-side filtering/aggregation without shipping all data to the browser; good if the dataset turns out to be large (multi-GB) or if filters need to combine dimensions that make static pre-splitting combinatorially large.
- **Cons**: more moving parts to build AND deploy in 5 days; needs a host with a real backend (Railway/Render/Fly.io) since Vercel/Netlify serverless functions are optimized for short stateless calls (Vercel function payload cap ~4.5MB request/response body - fine for query results, not for shipping the whole dataset); adds latency per filter change unless you cache aggressively.
- **Best when**: data doesn't compress down to a browser-friendly size, or you want live DuckDB SQL queries per filter (e.g. DuckDB running server-side directly against the parquet files, which is quite elegant and easy to write, just needs a persistent server not a static host).

### 1d. In-browser parquet parsing vs. server/build-time preprocessing
- **In-browser (DuckDB-Wasm, parquet-wasm, hyparquet/Apache Arrow JS)**: no backend needed, user's browser does the SQL/columnar work directly against parquet (even via HTTP range requests against remote files, avoiding full download). Genuinely elegant and demonstrates strong technical range.
  - DuckDB-Wasm binary + worker adds real weight (several MB) to first load, but pays off if the parquet files are the full 5-day dataset and you want ad hoc filtering without a preprocessing step. Column pruning + predicate pushdown + HTTP range reads mean it doesn't have to load a whole large file.
  - `parquet-wasm` (Rust/WASM, pairs with Apache Arrow JS) is fastest/most memory-efficient for larger files; `hyparquet` is lighter-weight/simpler if you just need to read modest files without a full Arrow pipeline.
  - Risk for a 5-day project: debugging WASM loading, worker setup, CORS on file fetches, and byte-level column quirks all in-browser is slower to iterate on than doing it in a Python REPL first.
- **Server/build-time preprocessing (recommended)**: use polars or DuckDB (both trivially read parquet, and DuckDB can directly query it with SQL) in a one-off Python script to explore, clean, decode any packed fields, compute per-match/per-day aggregates, and emit small JSON/newline-JSON/Arrow-IPC files partitioned by map+date+match. This is where you actually spend your "attention to detail" points (bot detection, timestamp handling, byte decoding) in an environment where you can print/inspect intermediate values easily.
- **Middle ground**: do initial exploration/decoding in Python, but also expose the *raw* per-match parquet (or a converted Arrow IPC file) statically, and use Arrow JS (not full DuckDB-wasm) client-side just to read it into typed arrays for deck.gl - lighter than full DuckDB-wasm, still avoids a JSON-with-strings size penalty for numeric columns.

**Synthesized recommendation**: preprocess with polars/DuckDB in Python (fast iteration, easy debugging), output compact per-map/per-day/per-match JSON (or Arrow IPC if you want smaller/faster-parsing numeric payloads), serve as static files, render with Leaflet+CRS.Simple or deck.gl in a small React/Next.js (or plain JS) app, deploy static to Vercel/Netlify. Keep DuckDB-wasm/full client-side parquet as an optional "if time remains" enhancement, not the base plan.

---

## 2. The Coordinate-Mapping Problem

This is explicitly called out as the tricky part, and it's exactly the "attention to detail" the evaluators are watching for. It also has a genuinely well-trodden solution pattern from the game-modding/telemetry-viz community.

### How the community solves it (PUBG / Rust / Apex / Fortnite precedent)
- **PUBG telemetry visualizers** (e.g. `rico0821/pubg_map`, the `pubgmap.io` telemetry explorer) convert `LogPlayerPosition`-style world X/Y (in centimeters in PUBG's case) into image pixel coordinates by dividing by a per-map "world size" constant, then scaling to the minimap image's pixel dimensions. The core insight: **each map has a known world-space bounding box** (often square, e.g. 0–816000 world units), and the transform is just linear rescaling into `[0, image_width] x [0, image_height]`.
- **Rust (uMod community)**: world coordinates are centered at the map's origin (0,0 at map center, not top-left), so the conversion is `imageX = (worldX + mapSize/2) / mapSize * imageWidth`, and critically Rust's Z axis (or Y, depending on convention) needs sign-flipping because the in-game world often has Y/Z increasing "north" while image coordinates increase downward.
- **Common gotcha across all of these**: game engines are frequently **Y-up or Z-up** (Unreal/Unity world space) while image/canvas coordinate systems are **Y-down from top-left**. If you don't flip one axis, your trajectories render correctly left-right but mirrored top-bottom (a very recognizable bug - a great thing to explicitly call out as an assumption/tradeoff in ARCHITECTURE.md even if you get it right, to show you understood the risk).
- **Fortnite/Apex community map tools**: similar approach - extract or empirically determine the map's world bounds (either from game files/wikis or by finding two or more known landmark coordinates), then fit a linear (affine) transform.

### What real games/tools actually do (concrete repos + formulas)
- **PUBG** - confirmed exact approach: telemetry `Location` values are in **centimeters**, and for most maps (Erangel, Miramar, Taego, Vikendi, Deston) the world X/Y range is **0 to ~800,000** (map-specific - Sanhok/Karakin are smaller). The community's entire conversion is one line: `pixelX = (worldX / mapSize) * imageWidth`, `pixelY = (worldY / mapSize) * imageHeight` - no rotation, no rescale asymmetry, because PUBG's minimap images are drawn as a perfect square crop of the world. Reference implementations:
  - [pubg/api-assets](https://github.com/pubg/api-assets) - Official map images + per-map metadata (this is the pattern to look for in your own README: a stated world size per map)
  - [rico0821/pubg_map](https://github.com/rico0821/pubg_map) - Python script doing exactly this linear scaling to plot kills/positions/circle/flight-path on the map image; good to skim for the actual arithmetic
  - [adzpm/pubg-map](https://github.com/adzpm/pubg-map) - Leaflet + Vue interactive map with deep-zoom tile pyramids, shows how to wire the same math into `L.CRS.Simple`
  - [PUBG-heatmap-frontend](https://github.com/mediusoft/PUBG-heatmap-frontend) / [PUBG-heatmap-backend](https://github.com/mediusoft/PUBG-heatmap-backend) - React canvas 2D match replay + heatmap, closest existing analog to this assignment's exact feature set (replay scrubber + heatmap over a minimap)
  - [pubgmap.io telemetry explorer](https://pubgmap.io/telemetry) - live example of a hosted telemetry-to-map tool for UX reference
- **Rust (Facepunch, via uMod/community tools)**: world origin is at the **map center**, not top-left, so the formula gains an offset: `imageX = (worldX + mapSize/2) / mapSize * imageWidth`. Same family of bug as PUBG's but a good reminder that "assume top-left origin" is not universal - always check empirically (see validation step below).
- **GTA V (modding/roleplay-server community, e.g. FiveM/RAGE:MP)**: the open-world map is not a clean square, so tools don't use a single global scale - they use **point-based calibration**: collect several (in-game coord, map-pixel coord) pairs and fit a linear regression / affine transform rather than trusting one documented bounding box. This is the right template when a README doesn't hand you exact bounds.
  - [WhatAboutGaming/gta-coords](https://github.com/WhatAboutGaming/gta-coords) and [Flamm64/GTA-V-World-Map](https://github.com/Flamm64/GTA-V-World-Map) - both are essentially "click a point on the map image, note the in-game coordinate" calibration tools; the pattern (build a small point-picker, then solve for the transform) is directly reusable for your minimaps if the README's stated bounds don't line up cleanly with the image.
  - [RiceaRaul/gta-v-map-leaflet](https://github.com/RiceaRaul/gta-v-map-leaflet) - another Leaflet-based implementation for a non-square, non-trivial world map.
- **Takeaway for LILA BLACK**: an extraction shooter's minimap is almost certainly a clean top-down square/rectangular crop like PUBG's (not GTA's messy open world), so start by assuming the simple linear formula and only fall back to point-based affine/homography calibration if the README's stated bounds don't visually line up when you do the Day-1 scatter-plot validation.

### Techniques, from simplest to most general
1. **2-point linear scale + offset (most likely sufficient here)**: if the map has no rotation and uniform world-to-pixel scale in X and Y (very common for a square battle-royale map), you only need: one known world coordinate + its known pixel location, plus either the map's world-space size (often documented, e.g. in the README you'll get) or a second reference point. Formula:
   - `pixelX = (worldX - worldMinX) / (worldMaxX - worldMinX) * imageWidth`
   - `pixelY = (worldY - worldMinY) / (worldMaxY - worldMinY) * imageHeight` - **and flip if the game's Y grows "up"/"north" while the image's Y grows downward**: use `imageHeight - computedY` in that case.
   - Determine `worldMin/Max` either from the README's stated coordinate system/world size, or empirically by taking the min/max of all observed X/Y per map (a good sanity check regardless).
2. **4-point (or more) affine/least-squares fit**: needed if there's any non-uniform scale, rotation, or the map image doesn't perfectly correspond to the raw world bounds (e.g. minimap has padding/border, or world space is rectangular but the image is square with letterboxing). Pick ≥3 reference points where you know both world coords and pixel coords (can eyeball known named POIs against the minimap image if the README doesn't give exact bounds), and solve a linear system (`numpy.linalg.lstsq`) for the 6 affine parameters `[a b c; d e f]`. This is the same math as `L.Transformation(a, b, c, d)` in Leaflet or a homography in OpenCV, just without needing perspective (a homography/4-point projective transform is overkill unless the minimap image itself is rotated/skewed relative to world axes, which is uncommon for a top-down game minimap).
3. **Validation step (do this regardless of method)**: after transforming, plot a scatter of ALL player positions for a map over the minimap image - if the coordinate system is right, the point cloud should trace the map's playable area (roads, coastlines, structures) almost exactly. This single visual check is the fastest way to catch an axis flip, a wrong scale, or a swapped X/Y - and is worth explicitly doing/screenshotting early (Day 1) before building anything else on top.

### Libraries that make this easy
- **Leaflet + `L.CRS.Simple`**: purpose-built for exactly this (non-geographic image maps - originally popular for game/dungeon maps, floor plans, star maps). You set `bounds = [[0,0],[imageHeight, imageWidth]]` (note Leaflet uses `[y, x]`/`[lat, lng]`-style ordering) and use `L.imageOverlay(url, bounds)`. If your world coordinates don't already match pixel coordinates 1:1, define a custom `L.Transformation(a, b, c, d)` (computes `a*x+b, c*y+d`) or just do the linear rescale yourself before feeding coordinates to Leaflet, then treat the map as a pure pixel grid. Leaflet's own official example (crs-simple) is the standard reference implementation for this pattern.
- **deck.gl / OrthographicView**: deck.gl supports a non-geospatial `OrthographicView`/`COORDINATE_SYSTEM.CARTESIAN` mode where you supply your own pixel-space coordinates directly (no lat/lng needed at all) - arguably even more direct than Leaflet's CRS.Simple since there's no lat/lng abstraction to work around. Do the world→pixel affine transform in your preprocessing step, then feed straight pixel coordinates into ScatterplotLayer/PathLayer/HeatmapLayer with a plain `<img>`/background layer or `BitmapLayer` for the minimap image underneath.
- **Manual canvas transform**: if using PixiJS/Konva/raw Canvas2D, you can equivalently just precompute pixel coordinates in preprocessing (recommended) or apply a `ctx.setTransform(a,b,c,d,e,f)` matching the same affine parameters, then draw in "world units" directly.

### Open-source tooling to *solve* the transform (if simple linear scaling isn't enough)
If the map turns out not to be a clean square (padding/border on the minimap image, non-uniform X/Y scale, or slight rotation), don't hand-tune constants - solve for them with a few reference points using standard open-source math libraries instead of a bespoke GTA-style point-picker UI:
- **`numpy.linalg.lstsq`** - fit the 6-parameter affine (`[a b c; d e f]`, i.e. scale+rotation+shear+translate, no perspective) from ≥3 known `(worldX, worldY) → (pixelX, pixelY)` pairs. This is the right tool 95% of the time for a top-down game minimap - it's exactly the same math Leaflet's `L.Transformation` and deck.gl's coordinate system use internally.
- **`cv2.getAffineTransform`** (OpenCV, `pip install opencv-python-headless`) - same affine fit but takes exactly 3 point pairs and returns the matrix directly; convenient if you don't want to hand-roll the least-squares call.
- **`cv2.getPerspectiveTransform` / `cv2.findHomography`** - only reach for these if the minimap image itself is skewed/rotated relative to the world axes (a true 4-point projective transform). Unlikely for a battle-royale-style top-down map, but `findHomography(..., cv2.RANSAC)` is the robust choice if you have >4 noisy reference points and want outlier rejection.
- **How to get reference points without a README-stated bounding box**: use in-data landmarks you can cross-check visually - e.g. the shrinking "storm"/safety-zone circle is usually logged as a world-space center + radius at each phase, and the circle's final position is visually obvious on the minimap; matching 2-3 storm-circle centers (world coords) against where those circles visibly sit on the minimap image gives you clean, unambiguous calibration points without eyeballing terrain features.

### Concrete step-by-step method (recommended for this project)
1. Extract `player_data.zip`; read the README for stated coordinate system / world bounds / map sizes per map.
2. Load one match's position data; compute min/max X and Y per map.
3. Compare observed min/max against README's stated world size (if given) - decide if origin is top-left, center, or bottom-left of world space.
4. Pick the linear-rescale formula (§ above), including a Y-flip flag per map if needed.
5. **Do the preprocessing (steps 1-4) once, in Python**, emitting already-pixel-space coordinates into your output JSON/Arrow files - so the frontend never has to know about world units at all, only pixel-space, which massively simplifies the renderer and avoids re-deriving the transform in two languages.
6. Validate visually by overlaying all points for a map on its minimap image before writing any playback/filtering code.
7. Note the exact formula + any assumptions in `ARCHITECTURE.md` (this is explicitly requested and is a big attention-to-detail signal).

---

## 3. Visualization Libraries for Trajectories, Markers, Heatmaps

| Library | Rendering | Trajectories | Event markers | Heatmap | Playback/animation | Perf @ 1000s-10000s pts | Notes |
|---|---|---|---|---|---|---|---|
| **Leaflet + Leaflet.heat + CRS.Simple** | SVG/Canvas | Polylines (`L.polyline`), easy | `L.circleMarker`/custom icons | `Leaflet.heat` plugin (canvas-based) | Manual: redraw/update polyline + markers on a timer/slider | Good to ~10-50k points with canvas renderer; can lag with huge marker counts in SVG mode (use `preferCanvas: true`) | Most mature, huge community precedent for exactly this game-map use case; lowest risk |
| **deck.gl** | WebGL | `PathLayer`, `TripsLayer` (built for animated playback, has `currentTime` "playhead" prop natively) | `ScatterplotLayer`/`IconLayer` | `HeatmapLayer` (GPU aggregated) | **TripsLayer is purpose-built for this** - update `currentTime` per frame, trail fades automatically | Excellent - smooth to ~1M points, only degrades at 10M+ | Best animation/playback ergonomics of any option here; steeper learning curve, but directly matches "timeline scrubber" requirement |
| **Kepler.gl** | WebGL (built on deck.gl) | Yes (trip layer support) | Yes | Yes (built-in) | Yes, has a time-range/animation UI out of the box | Same as deck.gl underneath | Turnkey UI is geospatial-first and **requires a Mapbox/base-map service** for its normal flow - awkward to force into "custom static image as basemap," and pulls in a lot you'd have to fight to hide; not recommended unless you specifically want to save UI-building time and can tolerate the geospatial framing |
| **PixiJS / Konva.js** | WebGL(Pixi)/Canvas(Konva) | Manual line drawing | Manual sprites | Would need a custom/third-party heatmap pass | Fully manual, full control | Very good (Pixi is a general WebGL 2D engine) | Most control, most work - good if you want a truly custom look, but reinvents what Leaflet/deck.gl give free |
| **D3.js** | SVG/Canvas | Manual, very flexible for custom easing/annotations | Manual | Manual (e.g. d3-contour or hexbin) | Manual, D3 transitions can drive it | Fine to a few thousand SVG nodes, use canvas for more | Best if you want bespoke chart-like polish (e.g. combined timeline chart below the map); more code to write than Leaflet/deck.gl for the map itself |
| **Plotly (Python, for Streamlit/Dash)** | WebGL/SVG hybrid | `go.Scattergl` lines | `go.Scattergl` markers with symbol/color | `go.Densitymapbox` needs real geo, so instead use 2D histogram/`go.Histogram2dContour` over pixel coords, or overlay `go.Image` (minimap) + `go.Scatter` (points) - this Image+Scatter combo is the clean non-geospatial trick | `Plotly.animate`/frames API supports slider-driven animation but re-renders full frames - can feel less smooth than WebGL-native options | Reasonable to low thousands of points per frame in a Python app | Only path if committing to Streamlit/Dash; the `go.Image` + `go.Scatter` overlay pattern (image as background trace, points in pixel coordinate space) is the practical equivalent of CRS.Simple for Plotly |
| **heatmap.js** | Canvas | n/a | n/a | Yes, standalone, framework-agnostic | n/a | Good, lightweight, single purpose | Simple option if only the heatmap layer is needed on top of a hand-rolled point/path renderer - lower lift than Leaflet.heat for a non-Leaflet stack |

**Synthesis**: For the SPA route (Option A), **Leaflet is the lowest-risk, best-precedented choice specifically because of `CRS.Simple`** (near copy-paste from official examples for the base map + overlay). **deck.gl is the higher-ceiling choice** if comfortable with it - `TripsLayer.currentTime` maps almost 1:1 onto the "timeline scrubber" requirement and its `HeatmapLayer`/`ScatterplotLayer` are GPU-accelerated and effortless at this data scale. A hybrid is also viable: Leaflet for the base map + custom canvas overlay pane for playback, if deck.gl feels like too much new API surface under time pressure.

---

## 4. Timeline / Replay / Playback UI Patterns

Precedent from real game replay/analytics tools:
- **CS2/CS:GO demo UI** (`Shift+F2` panel): scrubber timeline, play/pause, round-jump buttons, speed control (0.25x–8x), separate camera modes. The scrubber is the single most important control - it should support click-to-seek, not just play/pause.
- **Valorant's native replay system**: scrubbable timeline with small icons directly on the timeline marking kills/deaths/ability usage at their timestamp - i.e., **event markers rendered ON the scrubber track itself**, not just on the map. This is a strong, easy-to-copy pattern for LILA's requirement to show kills/deaths/loot/storm-deaths as markers: put a mini marker row under the scrubber in addition to on-map icons, so a level designer can see event density over time at a glance and jump straight to a spike.
- **Third-party tools (e.g. Valorant analyzers like valab)**: filter-by-agent/phase + heatmaps segmented by round phase, and "play back like a replay" - i.e., filters and playback are not mutually exclusive; filtering narrows the dataset feeding the same scrubber/map, which is exactly the UX model to replicate for map/date/match filters here.

**Recommended interaction model**:
- State: a single `currentTimestamp` (or normalized `t` in [0,1] per match) drives (a) which player positions are shown (interpolated or snapped to nearest known sample), (b) which event markers are "active/visible so far" vs. future, (c) play/pause/speed multiplier.
- Scrubber: an `<input type="range">` or custom D3/canvas track bound to `currentTimestamp`; overlay small ticks/dots for event timestamps (kills/deaths/storm-deaths) so the designer can jump to hot moments - this single UI element does a lot of the "feels professional" work with modest effort.
- Playback loop: `requestAnimationFrame` (frontend) advancing `currentTimestamp` by `deltaTime * speedMultiplier`, re-rendering only the layers that depend on time (positions/markers), not re-fetching data.
- For deck.gl specifically, this maps directly onto `TripsLayer`'s `currentTime` prop - feed it the same clock.
- Keep trajectories drawn as a persistent faint full-match line (so the designer always sees the whole path/context) with a brighter "so-far" or "trailing window" segment highlighting current position - mirrors CS2's trail rendering and reads as more polished than a bare dot with no context.

---

## 5. Hosting/Deployment Options

| Host | Best for | Free-tier constraints relevant here | Notes |
|---|---|---|---|
| **Vercel** | Next.js/React static+API | Static assets served via CDN with no special size gate; serverless **function** payload capped ~4.5MB req/resp, function bundle ≤250MB unzipped | If you avoid routing bulk data through a function (serve JSON as static public files instead), size limits are largely a non-issue |
| **Netlify** | Static SPA, also Functions | Similar static-hosting story; "Large Media" (Git-LFS-backed) exists for big binary assets but adds setup complexity - usually unnecessary if your preprocessed JSON/Arrow files stay in the tens-of-MB range per map/day | Good alternative to Vercel, roughly equivalent for this project's needs |
| **Railway / Render / Fly.io** | Real backend + DB/long-running server (Option C's full-stack variant, or serving DuckDB server-side) | Free tiers exist but are limited (sleep on idle, limited hours/compute) - fine for a take-home demo, mention limitation in README | Needed only if you choose the "backend queries parquet live" architecture (1c) |
| **Streamlit Community Cloud** | Streamlit apps specifically | Hard caps observed: ~200MB upload limit, ~1GB memory per app - must keep working dataset well under that (aggregate/downsample before loading into the app, use `@st.cache_data`/`@st.cache_resource`) | Free, zero-config for Python apps, but resource ceiling is real; a 5-day, multi-map, multi-day dataset likely needs pre-aggregation regardless of host, this just makes it non-negotiable |
| **GitHub Pages** | Fully static, no backend at all | No function support at all - must be 100% static (fits well with the "preprocess to JSON, pure frontend" plan) | Viable if you want a totally free, dead-simple deploy target with zero backend; slightly less "impressive" than Vercel for a portfolio piece but functionally fine |

**Practical sizing implication**: whatever stack, plan to keep the *served* dataset (after your own preprocessing/aggregation, not the raw parquet) in the tens-of-MB range per view, split by map/date/match so a level designer's browser only loads what's currently selected rather than all 5 days at once. This single decision (chunk by filter dimensions) is what keeps every hosting option on the table.

---

## 6. Data Handling Nuances

*(General technique guidance - schema is unknown until `player_data.zip` is extracted; verify against the actual README.)*

### Bot detection
No universal telemetry standard, but common real-world patterns worth checking for, in rough order of likelihood:
1. **An explicit boolean/flag column** (`is_bot`, `isNpc`, `player_type`) - check first, cheapest if present.
2. **ID-range or ID-prefix convention**: many game backends allocate bot/AI accounts from a reserved ID block or with a naming prefix (community reports around PUBG-style games mention bot handles following a generated-name pattern, e.g. two fragments joined by an underscore, versus human-chosen usernames) - inspect the distribution of player ID/name formats for a suspiciously uniform synthetic pattern.
3. **Behavioral heuristics** (used in academic bot-detection literature when no flag exists): bots tend to show unnaturally straight/looping movement paths, near-constant inter-action timing, lack of the erratic pauses/direction changes typical of human input, and often don't participate in some human-only behaviors (e.g., looting hesitation, contesting kills). For a 10-15 hour project, only reach for this if there is truly no explicit field/pattern - it's a rabbit hole; a simple, clearly-stated heuristic (e.g., "IDs matching pattern X are classified as bots, verified by checking their movement is unusually uniform") is enough to demonstrate the analytical instinct without over-engineering.
4. Whatever method is used, **document the exact rule in ARCHITECTURE.md's assumptions section** - this is explicitly one of the evaluation's "attention to detail" callouts, so an honest, explicit, checked assumption beats a silent guess.

### Timestamp handling
- Check whether timestamps are epoch integers (seconds vs. milliseconds vs. microseconds - a common silent bug is off-by-1000x), ISO8601 strings, or relative-to-match-start floats/durations.
- Confirm timezone assumptions (likely UTC for server-generated telemetry) before doing any date-based filtering (the assignment explicitly wants filter-by-date).
- If matches span midnight boundaries, decide whether "date" filtering uses match-start date or wall-clock per-event date, and note the choice.
- Use pandas/polars datetime dtypes (not raw ints/strings) as early as possible in preprocessing so sorting-by-time and computing playback deltas is correct and fast.

### "Byte encoding" nuances (likely packed/binary-encoded columns)
- Parquet supports several column encodings transparently handled by the reader (RLE/bit-packing for booleans and low-cardinality ints, dictionary encoding, delta encoding for sorted/monotonic integer or timestamp columns) - pyarrow/polars/pandas decode these automatically; this is *not* usually something you need to hand-decode.
- What likely *does* need manual decoding, if present: an application-level packed field - e.g. a single integer/binary column that packs multiple sub-values (bit-flags for event subtypes, or a coordinate pair packed into one 64-bit value for storage efficiency). Signs to look for: a column with an unexpectedly narrow/wide integer type relative to its apparent semantic range, or a `binary`/`bytes` dtype column that isn't clearly a string.
- General decode approach once suspected: read the README's schema notes first (this is very likely spelled out there); otherwise inspect raw values (`df['col'].unique()[:20]`, check min/max, check bit length needed) and reverse-engineer via bit-shifting/masking (`value & 0xFF`, `value >> 8`, etc.) - validate against a known-good reference row (e.g., a kill event where you independently know the two involved player IDs) before trusting the decode across the dataset.
- Prefer **polars** or **DuckDB SQL** over raw pandas for this exploration - both read parquet natively and fast, polars in particular has ergonomic bitwise ops (`.bitwise_and`, shifts) if packed integer decoding is needed, and DuckDB lets you prototype decode logic in SQL (`x & 255`, `x >> 8`) very quickly in a notebook.

---

## 7. Recommended End-to-End Stack Options

| | **Option A: Next.js + Leaflet/deck.gl + preprocessed static JSON, on Vercel** | **Option B: Python (polars/DuckDB) preprocessing → static JSON + vanilla JS/Leaflet frontend, on Netlify** | **Option C: Streamlit + `st.pydeck_chart`/Plotly + DuckDB, on Streamlit Community Cloud** |
|---|---|---|---|
| Setup speed | Medium (scaffold Next.js, wire Leaflet/deck.gl) | Fast (no framework scaffolding, just HTML/JS + a Python script) | Fastest to first pixel |
| Coordinate mapping | Easy (`CRS.Simple` or deck.gl `OrthographicView`, well precedented) | Same, easy | Workable via `go.Image` + `go.Scatter` overlay, less precedented, more fiddly |
| Playback/scrubber polish | High ceiling (deck.gl `TripsLayer.currentTime`, `requestAnimationFrame`) | High ceiling if hand-rolled with canvas + rAF; more manual wiring than A | Lower ceiling - full-script rerun per slider move risks jank; `st.pydeck_chart` mitigates this somewhat |
| Heatmaps | `HeatmapLayer` (deck.gl, GPU) or `Leaflet.heat` | Same options available | Native support if using `st.pydeck_chart`'s `HeatmapLayer`; clunkier via pure Plotly |
| Filtering UX | Full custom control (React state/dropdowns) | Full custom control (vanilla JS/DOM) | Easy widgets (`st.selectbox` etc.) but each triggers a script rerun |
| Data pipeline risk | Preprocessing is separate Python step either way - low risk | Same - low risk | Same underlying preprocessing need, but easy to accidentally do it live in-app and hit the ~1GB memory ceiling |
| Hosting simplicity | Very easy (static + CDN) | Very easy (static + CDN) | Very easy, but resource-capped (200MB/~1GB RAM) |
| Best fit if... | Comfortable with React/JS, want the most "wow" for evaluators, want highest ceiling on playback smoothness | Prefer minimal framework overhead, most comfortable in plain JS + Python, want fastest path to something solid | Strongest Python skills, weaker JS/React skills, or time is very tight and a "good enough" polished demo beats a more ambitious build |
| Overall risk for 10-15h/5-day | Low-medium (learning curve if new to deck.gl, but well documented) | **Lowest** - least new tooling, most control, most precedent | Medium - real risk of hitting UX/perf ceilings on the two hardest requirements (smooth playback + heatmaps) late in the timeline |

**Recommendation stands as Option B for someone comfortable with both Python and vanilla JS** (best risk/reward - full control without a framework learning curve), **or Option A if strong in React and wanting the more impressive, "obviously deck.gl" technical showcase.** Reserve Option C for a Python-only comfort zone or as a fallback if Day 3 checkpoint shows time pressure.

---

## 8. Suggested Build Plan (10-15 hours / 5 days)

**Day 1 (~2.5-3h) - Data exploration & coordinate calibration**
- Unzip `player_data.zip`, read the README thoroughly (schema, coordinate system, any bot/byte-encoding notes).
- Load one match's parquet in polars/DuckDB; inspect columns, dtypes, ranges, nulls.
- Identify position columns, event-type columns, player-ID/bot signal, timestamp format.
- Do the coordinate transform derivation (§2) for one map; validate visually (scatterplot over minimap image) - **do not proceed until this looks right**, it's the highest-risk item.
- Decide bot-detection rule; document reasoning.

**Day 2 (~3h) - Preprocessing pipeline & core data model**
- Write the Python preprocessing script: parse all matches → decode any packed/byte fields → apply coordinate transform → classify bot/human → normalize timestamps → emit per-map/per-date/per-match JSON (or Arrow) chunks, sized for browser loading.
- Spot-check output against raw data for at least one full match.
- Stand up minimal frontend scaffold (Next.js or plain HTML/JS) that loads one chunk and renders the minimap image at correct pixel dimensions.

**Day 3 (~3h) - Core rendering: journeys + event markers**
- Render player trajectories as paths over the minimap (Leaflet polylines or deck.gl PathLayer), colored/styled distinctly for bots vs. humans.
- Add event markers (kills/deaths/loot/storm-deaths) as distinct icons/colors at their mapped pixel positions.
- Wire up map/date/match filtering (dropdowns) re-loading/re-filtering the appropriate data chunk.

**Day 4 (~3h) - Timeline playback + heatmaps**
- Build the scrubber (range input or custom track) bound to a `currentTimestamp`/`t` state, with play/pause/speed controls, driving which positions/markers are visible (rAF loop).
- Add event-density ticks on the scrubber track itself (kills/deaths markers on the timeline, not just the map).
- Add heatmap layer(s) for kill zones / death zones / traffic density (toggle between them), using deck.gl `HeatmapLayer` or `Leaflet.heat`.

**Day 5 (~2.5-3h) - Polish, deployment, docs**
- UI polish pass: legend, loading states, empty states, responsive basics, sensible default filters on load.
- Deploy to Vercel/Netlify; verify the live URL works end-to-end from a fresh browser/incognito session (catches missed static-asset paths, CORS, etc.).
- Write `README.md` (stack, setup, env vars - likely none needed for a static approach), `ARCHITECTURE.md` (one page: tech choices + why, data flow diagram in words, coordinate-mapping formula used, explicit assumptions, tradeoffs table), and `INSIGHTS.md` (3 concrete, level-designer-useful findings - e.g., a chokepoint with disproportionate deaths, a loot area that's underused relative to its risk, a storm-shrink phase where players get caught disproportionately often - derived from the actual data, not hypothetical).

Buffer: if any day overruns, the first things to cut are the "if time remains" enhancements (in-browser DuckDB-wasm, extra heatmap modes, animation easing polish) - never cut the coordinate-mapping validation step or the deployment/docs pass, since both are explicitly graded.

---

## Key Resources Referenced

- [Leaflet: Non-geographical maps (CRS.Simple official example)](https://leafletjs.com/examples/crs-simple/crs-simple.html) - canonical reference implementation for image-overlay game/dungeon maps.
- [Leaflet Custom coordinate systems example](https://barionleg.github.io/Leaflet/examples/custom-crs/custom-crs.html) - for when scale/offset isn't 1:1.
- [uMod Rust forum: converting world coords to map image coords](https://umod.org/community/rust/38306-converting-world-coordinates-to-map-image-coordinates) - concrete community precedent for the exact affine-rescale problem in a battle-royale-style game.
- [rico0821/pubg_map (GitHub)](https://github.com/rico0821/pubg_map) - PUBG telemetry → map visualization, same problem shape as this assignment (positions, kills, loot, zone events over a minimap).
- [mediusoft/PUBG-heatmap-frontend (GitHub)](https://github.com/mediusoft/PUBG-heatmap-frontend) - 2D replay + heatmap on canvas with React, close analog to the requested deliverable.
- [deck.gl TripsLayer docs](https://deck.gl/docs/api-reference/geo-layers/trips-layer) - `currentTime` playhead prop, directly maps to the scrubber requirement.
- [deck.gl HeatmapLayer docs](https://deck.gl/docs/api-reference/aggregation-layers/heatmap-layer) and [ScatterplotLayer docs](https://deck.gl/docs/api-reference/layers/scatterplot-layer) - GPU-aggregated heatmaps and point rendering, perf notes.
- [deck.gl Performance Optimization guide](https://deck.gl/docs/developer-guide/performance) - scaling characteristics (smooth to ~1M points).
- [DuckDB-Wasm announcement (duckdb.org)](https://duckdb.org/2021/10/29/duckdb-wasm) and [MotherDuck: DuckDB Wasm in the browser](https://motherduck.com/blog/duckdb-wasm-in-browser/) - in-browser SQL over parquet, HTTP range-read behavior, size tradeoffs.
- [Sparkgeo: A DuckDB-Wasm Web Mapping Experiment with Parquet](https://sparkgeo.com/blog/a-duckdb-wasm-web-mapping-experiment-with-parquet/) - practical mapping-specific example of the in-browser-parquet pattern.
- [hyparquet (GitHub)](https://github.com/hyparam/hyparquet) and [parquet-wasm (GitHub)](https://github.com/kylebarron/parquet-wasm) - lightweight vs. Arrow-backed in-browser parquet parsing, with an explicit tradeoff writeup in parquet-wasm's README.
- [Vercel Functions Limits](https://vercel.com/docs/functions/limitations) and [Vercel Limits](https://vercel.com/docs/limits) - 4.5MB function payload cap, 250MB function bundle cap (static assets unaffected).
- [Netlify Large Media requirements/limitations](https://docs.netlify.com/build/git-workflows/large-media/requirements-and-limitations/) - for oversized binary assets, likely unnecessary if data is pre-aggregated.
- [Streamlit Community Cloud resource-limits discussions](https://discuss.streamlit.io/t/how-to-tell-resource-limits-vs-other-errors/35964) - ~200MB upload / ~1GB memory ceilings.
- [Kepler.gl GitHub](https://github.com/keplergl/kepler.gl) and [custom map styles doc](https://github.com/keplergl/kepler.gl/blob/master/docs/api-reference/advanced-usages/custom-map-styles.md) - turnkey but Mapbox-service-coupled, awkward fit for a non-geographic custom minimap.
- Valorant/CS2 replay system coverage (e.g. [dotesports: How to use the VALORANT Replay system](https://dotesports.com/valorant/news/how-to-use-valorant-replay-system)) - scrubber + on-timeline event-icon UX pattern worth copying.
- [Game Bot Detection via Avatar Trajectory Analysis (Sinica)](https://homepage.iis.sinica.edu.tw/~swc/pub/bot_detection_trajectory.html) and [arXiv: A Behavior Analysis-Based Game Bot Detection Approach](https://arxiv.org/pdf/1509.02458) - academic grounding for behavior-based bot heuristics if no explicit flag/ID pattern exists in the data.
- [Apache Parquet encodings spec](https://parquet.apache.org/docs/file-format/data-pages/encodings/) - background on RLE/bit-packing/delta encodings handled transparently by readers, useful for distinguishing "parquet's own encoding" from "an application-level packed field" when the assignment mentions byte-encoding nuances.
