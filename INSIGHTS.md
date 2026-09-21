# Insights

Draft, computed from the full preprocessed dataset (796 matches, 89,104 events, all 3 maps) via `pipeline/preprocess.py` + `data/index.json`. Numbers are real; the "actionable" framing is a first pass to sharpen once the tool is used interactively (e.g. to see *where* on the map these patterns concentrate).

## 1. AmbroseValley absorbs the large majority of play; GrandRift is barely touched

**What caught my eye:** matches are wildly unevenly distributed across the 3 maps in rotation.

**The numbers:** of 796 total matches - AmbroseValley: 566 (71%), Lockdown: 171 (21%), GrandRift: 59 (7%). This isn't just "AmbroseValley is the primary map" (as the README frames it) - GrandRift is getting an order of magnitude less play than either other map, which is a bigger gap than "secondary map" implies.

**Actionable:** if map rotation is supposed to be roughly even (or intentionally weighted, but not this extreme), check matchmaking/rotation-weight config for GrandRift. Metrics to watch: **matches-per-map-per-day** as a rotation health KPI; **time-to-fill** for GrandRift lobbies specifically (if players are opting out of it, queue times there should be visibly longer).

**Why a level designer should care:** a map that's technically "in rotation" but almost never played gets almost no live playtesting signal - any balance issues on GrandRift are close to invisible in this kind of telemetry simply because sample size is 10x smaller than the other maps.

---

## 2. Human-vs-human combat is almost nonexistent - nearly all kills are against bots

**What caught my eye:** the `Kill`/`Killed` event counts (human killed human) are vanishingly small next to `BotKill`/`BotKilled`.

**The numbers:** across all 796 matches: `Kill`=3, `Killed`=3 (human-on-human, note these should be equal and are - consistent data) vs. `BotKill`=2,415, `BotKilled`=700 (human-vs-bot). Human-on-human combat is **~0.1%** of all recorded combat events. This holds per-map too (AmbroseValley: 2 vs. 1,797+486; GrandRift: 1 vs. 192+46; Lockdown: 0 vs. 426+168).

**Actionable:** if part of the game's appeal is meant to be human PvP tension (typical for an extraction shooter), this data suggests players are almost never encountering each other - likely because bot density dilutes lobbies enough that humans rarely converge, or spawn/zone spacing keeps them apart. Metrics affected: **PvP-engagement-rate per match**, **average distance between human players over time**. Actionable items: consider reducing bot-to-human ratio in matchmaking, or biasing spawn points / storm shrink direction to increase human-human proximity late in a match.

**Why a level designer should care:** loot placement, chokepoints, and sightlines are usually designed assuming players will fight each other there - if that's not happening in practice, those design intentions aren't landing, and it's not visible without telemetry like this.

---

## 3. Storm deaths are rare across all maps - the storm isn't the thing that's killing players

**What caught my eye:** `KilledByStorm` counts are small relative to match count, on every map.

**The numbers:** 39 storm deaths total across 796 matches (≈5% of matches have even one storm death): 17 on AmbroseValley (566 matches), 5 on GrandRift (59 matches), 17 on Lockdown (171 matches) - Lockdown's rate (17/171 ≈ 10%) is roughly double AmbroseValley's (17/566 ≈ 3%) despite Lockdown being the smaller, "close-quarters" map where a shrinking zone should matter more, not just proportionally more but on an absolute per-match basis too.

**Actionable:** either the storm timer/damage is tuned generously enough that most players extract or die to combat first (which may be intentional), or players are consistently out-rotating it. Metrics to track: **storm-death-rate per map**, **average distance-to-safe-zone-edge at time of extraction**. If storm pressure is meant to be a bigger late-match forcing function, this data says it currently isn't one - worth deliberately tightening on Lockdown first, since its higher relative rate suggests the mechanic is already more "felt" there and there's room to lean into it.

**Why a level designer should care:** the storm is a core pacing tool for an extraction shooter - if it's rarely the actual cause of death, the map's "late game" pressure is coming from somewhere else (bots, other players, or just the clock), which changes what should be tuned to create tension.

---

*(Bonus, not one of the required 3): Loot pickups per match are noticeably lower on Lockdown (~12/match) than AmbroseValley (~17.6/match) or GrandRift (~14.9/match) despite similar average match durations (~400-430s across all three) - worth checking loot spawn density on Lockdown specifically once the tool's heatmap is used to see if that's map-wide or concentrated in specific under-looted zones.)*
