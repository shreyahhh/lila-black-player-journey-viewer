# Project Documentation

This is the extended reference doc - covering the assignment's required points plus the broader product/technical context a PM or engineer would want before building on top of this. For the required one-pagers, see [README.md](README.md) (setup), [ARCHITECTURE.md](ARCHITECTURE.md) (system design), and [INSIGHTS.md](INSIGHTS.md) (data findings). This doc is the "everything else."

---

## 1. What this is, in product terms

**Problem:** LILA Games' Level Design team has raw player telemetry from LILA BLACK but no visual way to answer basic design questions - where players fight, where they die to the storm, which parts of a map never get visited.

**User:** a Level Designer. Not a data scientist - they shouldn't need to write a query or open a notebook. They think in terms of "this building," "that choke point," not `x=1099.5, z=2963.8`.

**Core job-to-be-done:** open a match, watch it play out on the actual map art, and spot patterns - either in one match ("why did everyone die here?") or across hundreds of matches ("which parts of this map are dead space?").

**Non-goals (explicitly out of scope for this pass):**
- Real-time/live telemetry (this is a historical-data explorer, not a live dashboard)
- Cross-map or cross-day comparison views (e.g. "AmbroseValley vs. Lockdown side by side")
- Authentication/access control (the assignment's data has no PII concerns - `user_id` is an opaque UUID/bot-id with no names, so an open link is acceptable for this exercise; see §6 for what changes in production)
- Editing/annotating the data from the tool (read-only viewer)

---

## 2. Tech stack, and specifically why

| Layer | Choice | Why this, not the alternative |
|---|---|---|
| Data parsing | Python + [`pyarrow`](https://arrow.apache.org/docs/python/) | Native Parquet reader, no pandas overhead needed since we only do one pass per file |
| Image metadata | [`Pillow`](https://pillow.readthedocs.io/) | Only used to read real minimap pixel dimensions - turned out to matter (see ARCHITECTURE.md, the README's stated 1024×1024 was wrong) |
| Map rendering | [Leaflet](https://leafletjs.com/) with [`L.CRS.Simple`](https://leafletjs.com/examples/crs-simple/crs-simple.html) | The standard tool for "plot points on a static image, not a real map" - used across the PUBG/Rust/GTA map-tooling community for exactly this problem. Alternative considered: [deck.gl](https://deck.gl/) (more GPU headroom, steeper learning curve) - not needed at this data scale (≤ a few thousand points/match) |
| Density overlays | [Leaflet.heat](https://github.com/Leaflet/Leaflet.heat) | Small, does one thing, integrates directly with CRS.Simple coordinates |
| Hosting | GitHub Pages | Zero-cost, zero-config for a static site with no backend; the whole app is `index.html` + `data/*.json` + `minimaps/*` |
| Everything else | Plain JS, no framework, no build step | At this scope (one page, no routing, no component reuse pressure) React/Vue would add a build pipeline for no real benefit - see tradeoffs table in ARCHITECTURE.md |

**Full research trail:** the broader survey of alternatives considered before landing here (Streamlit/Dash, deck.gl vs. Leaflet vs. Kepler.gl, in-browser DuckDB-Wasm parsing vs. offline preprocessing, hosting options and their free-tier limits) is in [`RESEARCH.md`](RESEARCH.md) - kept separate since it's exploratory notes, not a decision record.

---

## 3. Data pipeline at a glance

```
1,243 Parquet files (89,104 rows, 796 matches, 3 maps, 5 days)
        │  pipeline/preprocess.py
        ▼
796 match JSON files + index.json + 3 per-map _aggregate.json  (~6.6MB total)
        │  index.html (fetch)
        ▼
Rendered in-browser: paths, event markers, heatmaps, playback
```

Full walkthrough - including the coordinate transform derivation and the two real data bugs found (mislabeled minimap dimensions, mislabeled `ts` units) - is in [ARCHITECTURE.md](ARCHITECTURE.md). The short version: everything risky (Parquet parsing, unit conversions, human/bot classification) happens once, offline, in Python, so the browser only ever deals with plain pixel coordinates and JSON.

---

## 4. Product decisions and their rationale

- **Match dropdown sorted by player count, descending.** A Level Designer exploring cold has no way to know which of 566 AmbroseValley matches is "interesting" - surfacing the busiest matches first (more players → more likely to have combat/events worth looking at) removes a blind pick.
- **Heatmap defaults to "off," not "traffic."** A heatmap on top of a path-covered map is visually noisy; showing it only on request keeps the default view legible.
- **Map-wide heatmap modes are separate from the per-match one**, and precomputed at build time rather than fetched live. A single match has too few kill/death events to show a real pattern - the question "where do people die on this map" only makes sense aggregated across hundreds of matches, and fetching hundreds of match files client-side just to answer it would be slow and wasteful.
- **Playback speed defaults to 2x**, not 1x. Matches run up to ~15 minutes; watching one in real time is tedious for a first look, and a Level Designer can always slow down once they've found something interesting.
- **No login, no per-user state.** Nothing in the requirements calls for it, and adding it would be unjustified complexity for a read-only exploration tool over already-anonymized data.

---

## 5. What a PM would probably ask next

- **"Can we track this over time?"** Not yet - this reads a fixed snapshot (`player_data.zip`, Feb 10–14 2026). Turning it into an ongoing tool means a real ingestion pipeline (see §6) instead of a one-off preprocessing script.
- **"Can Level Designers leave notes on a spot?"** Not currently - this is a read-only viewer. The natural next feature would be lightweight annotations (pin a comment to a map location), which would need actual persistent storage (see §6), not just static JSON.
- **"How do we know if this is actually useful?"** No usage tracking exists (nor should it, for an internal tool built as a take-home). In a real rollout, the metric that matters is something like *"number of distinct Level Designers opening the tool per week"* and *"time from a reported balance issue to a Level Designer finding supporting evidence in the tool"* - a proxy for whether it's actually replacing ad-hoc data requests to engineering.
- **"What did you learn from the data itself?"** See [INSIGHTS.md](INSIGHTS.md) - map rotation is heavily skewed toward AmbroseValley, human-vs-human combat is nearly nonexistent (bots dominate encounters), and storm deaths are rare across all three maps.

---

## 6. What changes if this became a real production tool

This was built as a static, read-only tool over a fixed data snapshot, which is the right scope for the assignment but not how a permanent internal tool would be built. If LILA Games wanted to keep this running against live data:

| Concern | Current approach (fine for this exercise) | What it'd need in production |
|---|---|---|
| Data freshness | One-time `player_data.zip` → static JSON | A scheduled ingestion job (e.g. nightly) pulling new match data from wherever the game server (Nakama, per the filename convention) lands it, re-running the same coordinate/ts/bot-detection pipeline |
| Data volume | 6.6MB total, fits in a git repo and loads instantly | At real production scale (thousands of matches/day, indefinitely) static JSON-per-match stops scaling - would need a real datastore (e.g. Postgres/DuckDB file + a thin API) and pagination/lazy loading instead of one `index.json` listing every match ever |
| Hosting | GitHub Pages (free, zero-config, but rebuilds require a new commit) | Any standard static host behind the company's auth (Vercel/Netlify/internal), likely behind SSO if it should only be visible to LILA staff |
| Access control | None - the data has no PII (opaque UUIDs, no player names/emails) | If tied to real accounts in the future, would need SSO-gated access even though the current dataset itself isn't sensitive |
| Coordinate/schema drift | Hardcoded `MAP_CONFIG` (scale/origin per map), validated once against this snapshot | A new map or a schema change to the telemetry format would silently break rendering unless the pipeline validates its own assumptions on every run (see §7) |
| Observability | None (offline script, run manually) | Ingestion pipeline failures (a bad match file, a new event type, a map added without minimap config) should alert someone rather than fail silently |

None of this is a criticism of the current build - it's scoped correctly for a 5-day take-home over a fixed dataset. It's here so the tradeoff is explicit rather than assumed.

---

## 7. Suggested next engineering steps (beyond assignment scope)

1. **A validation script for the pipeline itself.** Right now correctness was verified manually (see ARCHITECTURE.md's verification section) - worth turning into an automated check that runs on every `preprocess.py` execution: assert 100% of transformed points land in `[0, width] x [0, height]`, assert every `match_id` maps to exactly one `map_id`, assert `human_count + bot_count == total distinct user_ids for that match`, fail loudly if any of these regress on a future data drop.
2. **Point the existing INSIGHTS.md findings at exact map locations.** The three insights are backed by real aggregate stats; now that the heatmap is live, a quick pass naming the actual building/POI where kills cluster (visible in the "kill zones" heatmap) would make them concretely actionable rather than just statistical.
3. **A `_aggregate.json` per (map, date)`, not just per map**, if "has this map's traffic pattern changed over the 5 days" ever becomes a real question - trivial to add since the pipeline already iterates day-by-day.
4. **Minimap image compression.** Lockdown's source JPG and AmbroseValley's PNG are both several MB at full resolution (4320×4320 / 9000×9000) - fine for a 5-day exercise, but would benefit from a build-time downscale/compression pass if load time on a slow connection ever becomes a concern.
