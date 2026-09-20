"""
LILA BLACK player-journey preprocessing pipeline.

Reads the raw per-player-per-match parquet files, applies the VERIFIED
world->pixel coordinate transform, corrects a real bug found in the `ts`
column, classifies human vs. bot, and emits one compact JSON file per
match (grouped by map) plus a top-level index for filtering.

Run:
    python preprocess.py --src "../../player_data/player_data" --out "../data"

All findings below were verified against the actual dataset (not assumed
from the README alone) -- see ARCHITECTURE.md "Assumptions" for the writeup.
"""
import argparse
import glob
import json
import os
import re
from collections import defaultdict

import pyarrow.parquet as pq
from PIL import Image

# ---------------------------------------------------------------------------
# Map configuration, from README.md, Section "Map Configuration".
# Scale/origin are exact. Image dimensions are NOT the README's claimed
# 1024x1024 -- verified by inspecting the actual files:
#   AmbroseValley_Minimap.png -> 4320x4320
#   GrandRift_Minimap.png     -> 2160x2158 (not even square!)
#   Lockdown_Minimap.jpg      -> 9000x9000
# So the pipeline reads real image dimensions at runtime instead of
# hardcoding 1024, and treats width/height independently (never assumes
# square) so GrandRift's 2-pixel asymmetry is handled correctly for free.
# ---------------------------------------------------------------------------
MAP_CONFIG = {
    "AmbroseValley": {"scale": 900, "origin_x": -370, "origin_z": -473,
                       "minimap_file": "AmbroseValley_Minimap.png"},
    "GrandRift":     {"scale": 581, "origin_x": -290, "origin_z": -290,
                       "minimap_file": "GrandRift_Minimap.png"},
    "Lockdown":      {"scale": 1000, "origin_x": -500, "origin_z": -500,
                       "minimap_file": "Lockdown_Minimap.jpg"},
}

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

BOT_EVENTS = {"BotPosition", "BotKill", "BotKilled"}
KILL_EVENTS = {"Kill", "BotKill"}          # this player got a kill
DEATH_EVENTS = {"Killed", "BotKilled", "KilledByStorm"}  # this player died


def is_human(user_id: str) -> bool:
    """Authoritative bot/human check.

    IMPORTANT (verified, not assumed): the event name is NOT a reliable
    signal for the row owner's human/bot status. Numeric (bot) user_ids
    were found emitting plain 'Position' and 'Loot' events (not just
    'BotPosition'), and UUID (human) user_ids obviously emit 'BotKill'/
    'BotKilled' when they kill/are killed by a bot. The only reliable
    signal is the user_id FORMAT itself, exactly as the README states.
    """
    return bool(UUID_RE.match(user_id))


def world_to_pixel(x: float, z: float, map_id: str, img_w: int, img_h: int):
    """README formula, generalized to each image's real (possibly
    non-square) pixel dimensions instead of a hardcoded 1024x1024."""
    cfg = MAP_CONFIG[map_id]
    u = (x - cfg["origin_x"]) / cfg["scale"]
    v = (z - cfg["origin_z"]) / cfg["scale"]
    px = u * img_w
    py = (1 - v) * img_h  # Y flip: world Z-up vs. image Y-down from top-left
    return px, py


def fix_ts(raw_ms_field) -> int:
    """Correct a verified encoding bug in `ts`.

    The parquet column is typed `timestamp[ms]`, and the README describes
    it as "time elapsed within the match". Neither is what the raw
    integers actually are: decoding the raw int64 as Unix-epoch
    MILLISECONDS (i.e. trusting the declared type) lands on 1970-01-21,
    which is nonsense. Decoding the SAME raw integer as Unix-epoch
    SECONDS lands on real dates inside Feb 10-14 2026 -- exactly the
    dataset's actual collection window. So: the raw integer is genuine
    wall-clock epoch seconds, mislabeled as millisecond timestamps.
    We take the raw int64 and treat it as epoch seconds directly.
    """
    return int(raw_ms_field)  # pyarrow gives back the raw int64 when cast


def load_file(filepath: str):
    table = pq.read_table(filepath)
    table = table.set_column(
        table.schema.get_field_index("ts"),
        "ts",
        table.column("ts").cast("int64"),
    )
    cols = table.to_pylist()
    return cols


def process_all(src_dir: str, out_dir: str):
    minimap_dir = os.path.join(src_dir, "minimaps")
    img_dims = {}
    for map_id, cfg in MAP_CONFIG.items():
        with Image.open(os.path.join(minimap_dir, cfg["minimap_file"])) as im:
            img_dims[map_id] = im.size  # (width, height)
    print("Minimap dimensions (measured, not assumed):", img_dims)

    day_folders = sorted(
        d for d in glob.glob(os.path.join(src_dir, "February_*")) if os.path.isdir(d)
    )

    # match_id -> match record
    matches = {}

    # per-map aggregate heat points, across ALL matches, for the map-wide
    # "kill zones / death zones / high-traffic areas" heatmap requirement
    # (a single match's points are too sparse to show a meaningful zone).
    heat_points = {mid: {"traffic": [], "kills": [], "deaths": []} for mid in MAP_CONFIG}

    total_files = 0
    total_rows = 0
    skipped = 0

    for day_folder in day_folders:
        date_label = os.path.basename(day_folder)  # e.g. "February_10"
        files = glob.glob(os.path.join(day_folder, "*.nakama-0"))
        for fp in files:
            total_files += 1
            try:
                rows = load_file(fp)
            except Exception as e:
                skipped += 1
                print(f"  [skip] {fp}: {e}")
                continue
            if not rows:
                continue

            user_id = rows[0]["user_id"]
            match_id = rows[0]["match_id"]
            map_id = rows[0]["map_id"]
            human = is_human(user_id)
            img_w, img_h = img_dims[map_id]

            m = matches.get(match_id)
            if m is None:
                m = {
                    "match_id": match_id,
                    "map_id": map_id,
                    "date": date_label,
                    "players": {},   # user_id -> player record
                }
                matches[match_id] = m

            player = m["players"].get(user_id)
            if player is None:
                player = {
                    "user_id": user_id,
                    "is_human": human,
                    "points": [],   # [t_epoch_s, px, py, elevation_y, event]
                }
                m["players"][user_id] = player

            for r in rows:
                total_rows += 1
                event = r["event"]
                event = event.decode("utf-8") if isinstance(event, (bytes, bytearray)) else event
                t = fix_ts(r["ts"])
                px, py = world_to_pixel(r["x"], r["z"], map_id, img_w, img_h)
                player["points"].append([t, round(px, 1), round(py, 1), round(r["y"], 1), event])

                hp = heat_points[map_id]
                if event in ("Position", "BotPosition"):
                    hp["traffic"].append([round(px, 1), round(py, 1)])
                elif event in KILL_EVENTS:
                    hp["kills"].append([round(px, 1), round(py, 1)])
                elif event in DEATH_EVENTS:
                    hp["deaths"].append([round(px, 1), round(py, 1)])

    print(f"Files processed: {total_files}, skipped: {skipped}, rows: {total_rows}")
    print(f"Matches found: {len(matches)}")

    # Write one JSON per match, grouped under data/<map_id>/<match_id>.json
    index = []
    for match_id, m in matches.items():
        # sort each player's points chronologically and derive match-relative time
        all_ts = [pt[0] for p in m["players"].values() for pt in p["points"]]
        t_start = min(all_ts)
        t_end = max(all_ts)

        players_out = []
        human_count = 0
        bot_count = 0
        event_counts = defaultdict(int)
        for p in m["players"].values():
            p["points"].sort(key=lambda pt: pt[0])
            # rewrite absolute epoch seconds -> match-relative seconds for playback
            for pt in p["points"]:
                pt[0] = pt[0] - t_start
                event_counts[pt[4]] += 1
            if p["is_human"]:
                human_count += 1
            else:
                bot_count += 1
            players_out.append(p)

        map_dir = os.path.join(out_dir, m["map_id"])
        os.makedirs(map_dir, exist_ok=True)
        out_path = os.path.join(map_dir, f"{match_id.replace('.nakama-0', '')}.json")
        with open(out_path, "w") as f:
            json.dump({
                "match_id": match_id,
                "map_id": m["map_id"],
                "date": m["date"],
                "duration_sec": t_end - t_start,
                "players": players_out,
            }, f, separators=(",", ":"))

        index.append({
            "match_id": match_id,
            "map_id": m["map_id"],
            "date": m["date"],
            "duration_sec": t_end - t_start,
            "human_count": human_count,
            "bot_count": bot_count,
            "event_counts": dict(event_counts),
            "file": os.path.relpath(out_path, out_dir).replace("\\", "/"),
        })

    with open(os.path.join(out_dir, "index.json"), "w") as f:
        json.dump({
            "maps": {mid: {"width": w, "height": h} for mid, (w, h) in img_dims.items()},
            "matches": index,
        }, f, indent=2)

    for map_id, cfg in MAP_CONFIG.items():
        map_dir = os.path.join(out_dir, map_id)
        os.makedirs(map_dir, exist_ok=True)
        with open(os.path.join(map_dir, "_aggregate.json"), "w") as f:
            json.dump(heat_points[map_id], f, separators=(",", ":"))

    print(f"Wrote {len(index)} match files + index.json + per-map _aggregate.json to {out_dir}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="../../player_data/player_data")
    ap.add_argument("--out", default="../data")
    args = ap.parse_args()
    process_all(args.src, args.out)
