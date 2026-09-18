"""
load_real_episode_from_csv.py — builds real_episode_data.json from the 3
CSV exports produced by gee_extract.js (the Code Editor fallback path),
in the exact same StageRecord shape gee_extract.py's run_episode() would
have written directly via earthengine-api.

Use this path only if gee_extract.py itself can't run (auth/project
registration was a blocker for this account -- see gee_extract.js header).

SETUP: run gee_extract.js in https://code.earthengine.google.com/, run the
3 export tasks in the Tasks tab, download ee_samples.csv,
ee_stage_scalars.csv, ee_scene_ids.csv from Google Drive into this folder.

RUN:
    python3 load_real_episode_from_csv.py
    python3 load_real_episode.py --in real_episode_data.json
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import time
from collections import defaultdict

DEFAULT_PARAMS = {"alpha": 0.5, "beta": 0.3, "lambda": 0.2, "tau": 0.4, "scale_val": 100}
P1_START, P1_END = "2023-06-01", "2023-08-31"
P2_START, P2_END = "2024-06-01", "2024-08-31"
FULL_START, FULL_END = "2023-01-01", "2024-12-31"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _num_or_none(v):
    return None if v in ("", None) else round(float(v), 6)


def load_samples(path):
    by_stage = defaultdict(list)
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            by_stage[row["stage"]].append({
                "lon": _num_or_none(row["lon"]),
                "lat": _num_or_none(row["lat"]),
                "val": _num_or_none(row["val"]),
            })
    return by_stage


def load_scalars(path):
    out = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            cpe = row.get("changed_pixels_est", "")
            out[row["stage"]] = {
                "mean": _num_or_none(row["mean"]),
                "changed_pixels_est": None if cpe in ("", None) else round(float(cpe)),
            }
    return out


def load_scene_ids(path):
    by_coll = defaultdict(list)
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            by_coll[row["collection"]].append(row["scene_index"])
    return by_coll


def stage_output(samples_by_stage, scalars_by_stage, label):
    rows = sorted(samples_by_stage[label], key=lambda r: (r["lon"] or 0, r["lat"] or 0))
    scal = scalars_by_stage[label]
    out = {
        "mean": scal["mean"],
        "n_samples": len(rows),
        "array_hash": sha256_hex(canonical(rows)),
    }
    if scal["changed_pixels_est"] is not None:
        out["changed_pixels_est"] = int(scal["changed_pixels_est"])
    return out


def collection_output(scene_ids_by_coll, label):
    ids_sorted = sorted(scene_ids_by_coll[label])
    return {"scene_ids_hash": sha256_hex(canonical(ids_sorted)), "n_scenes": len(ids_sorted)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", default="ee_samples.csv")
    ap.add_argument("--scalars", default="ee_stage_scalars.csv")
    ap.add_argument("--scene-ids", default="ee_scene_ids.csv")
    ap.add_argument("--episode-id", default="almaty-2023_2024-episode-001")
    ap.add_argument("--out", default="real_episode_data.json")
    args = ap.parse_args()

    samples = load_samples(args.samples)
    scalars = load_scalars(args.scalars)
    scene_ids = load_scene_ids(args.scene_ids)
    now = time.time()

    records = []

    def add(label, input_ref, params, output):
        records.append({"label": label, "input_ref": input_ref, "params": params, "output": output, "timestamp": now})

    add("data_acquisition_s2",
        {"collection": "COPERNICUS/S2_SR_HARMONIZED", "periods": [f"{P1_START}/{P1_END}", f"{P2_START}/{P2_END}"]},
        {"cloud_pct_lt": 30, "cloud_mask": "QA60_bits_10_11"},
        collection_output(scene_ids, "data_acquisition_s2"))
    add("data_acquisition_s1",
        {"collection": "COPERNICUS/S1_GRD", "periods": [f"{P1_START}/{P1_END}", f"{P2_START}/{P2_END}"]},
        {"instrument_mode": "IW", "join_max_diff_days": 15},
        collection_output(scene_ids, "data_acquisition_s1"))

    add("pearson_corr_period1", {"period": f"{P1_START}/{P1_END}"}, {"reducer": "pearsonsCorrelation"},
        stage_output(samples, scalars, "pearson_corr_period1"))
    add("pearson_corr_period2", {"period": f"{P2_START}/{P2_END}"}, {"reducer": "pearsonsCorrelation"},
        stage_output(samples, scalars, "pearson_corr_period2"))
    add("delta_corr", {"depends_on": ["pearson_corr_period1", "pearson_corr_period2"]}, {},
        stage_output(samples, scalars, "delta_corr"))
    add("r_t", {"period": f"{FULL_START}/{FULL_END}"}, {"reducer": "pearsonsCorrelation"},
        stage_output(samples, scalars, "r_t"))
    add("moran_index", {"depends_on": ["delta_corr"]}, {"kernel": [[1, 1, 1], [1, 0, 1], [1, 1, 1]]},
        stage_output(samples, scalars, "moran_index"))
    add("risk_index", {"depends_on": ["delta_corr", "moran_index", "r_t"]},
        {"alpha": DEFAULT_PARAMS["alpha"], "beta": DEFAULT_PARAMS["beta"], "lambda": DEFAULT_PARAMS["lambda"]},
        stage_output(samples, scalars, "risk_index"))
    add("change_mask", {"depends_on": ["risk_index"]}, {"tau": DEFAULT_PARAMS["tau"]},
        stage_output(samples, scalars, "change_mask"))

    with open(args.out, "w") as f:
        json.dump({"episode_id": args.episode_id, "params": DEFAULT_PARAMS, "records": records}, f, indent=2)
    print(f"Wrote {len(records)} stage records to {args.out}")
    print("Next: python3 load_real_episode.py --in", args.out)


if __name__ == "__main__":
    main()
