"""
gee_extract.py — Python (earthengine-api) translation of the original
BSS2026 GEE JavaScript pipeline. Computes the exact same stages
(maskS2clouds -> getData -> corr1/corr2 -> deltaCorr -> r_t -> moran ->
risk_index -> change_mask) and, instead of Map.addLayer, writes out a
JSON file whose structure matches pipeline.StageRecord's fields
(input_ref, params, output) -- ready to be hashed and anchored by the
provenance layer via load_real_episode.py.

WHY THIS RUNS ON YOUR MACHINE, NOT IN THE SANDBOX:
Earth Engine calls go to earthengine.googleapis.com, which this
sandbox's network allow-list does not include. Run this script wherever
you already run GEE Python code (local machine, Colab, etc.).

SETUP (one-time):
    pip install earthengine-api
    earthengine authenticate
        (requires a Google Cloud project with the Earth Engine API
        enabled and registered for EE access -- same requirement as
        the JS Code Editor, just via CLI/browser OAuth once)

RUN:
    python3 gee_extract.py --project YOUR_GCP_PROJECT_ID
        [--episode-id almaty-2023_2024-episode-001]
        [--out real_episode_data.json]

If this fails (auth/quota/project-registration issues), fall back to
the JS Code Editor + CSV export path -- ask for that loader instead.
"""

from __future__ import annotations
import argparse
import hashlib
import json
import time

import ee

# ---- same constants as the original JS script -----------------------
DEFAULT_PARAMS = {"alpha": 0.5, "beta": 0.3, "lambda": 0.2, "tau": 0.4, "scale_val": 100}

AOI_LON, AOI_LAT, AOI_BUFFER_M = 76.9455, 43.1575, 10000

P1_START, P1_END = "2023-06-01", "2023-08-31"
P2_START, P2_END = "2024-06-01", "2024-08-31"
FULL_START, FULL_END = "2023-01-01", "2024-12-31"

N_SAMPLES = 200      # points sampled per raster stage for the array_hash commitment
SAMPLE_SEED = 42     # fixed seed -> deterministic sampling -> reproducible hashes


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


# ---- direct translation of the JS pipeline ----------------------------

def mask_s2_clouds(image: ee.Image) -> ee.Image:
    qa = image.select("QA60")
    mask = qa.bitwiseAnd(1 << 10).eq(0).And(qa.bitwiseAnd(1 << 11).eq(0))
    return image.updateMask(mask).divide(10000).copyProperties(image, ["system:time_start"])


def get_s2_ndvi(aoi: ee.Geometry, start: str, end: str) -> ee.ImageCollection:
    return (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
        .map(mask_s2_clouds)
        .map(lambda img: img.normalizedDifference(["B8", "B4"]).rename("NDVI")
             .copyProperties(img, ["system:time_start", "system:index"]))
    )


def get_s1_sar(aoi: ee.Geometry, start: str, end: str) -> ee.ImageCollection:
    def add_ratio(img):
        ratio = img.select("VV").divide(img.select("VH")).rename("VVVH")
        return img.addBands(ratio).select("VVVH").copyProperties(
            img, ["system:time_start", "system:index"])

    return (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(aoi)
        .filterDate(start, end)
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .map(add_ratio)
    )


def get_data(aoi: ee.Geometry, start: str, end: str) -> ee.ImageCollection:
    ndvi = get_s2_ndvi(aoi, start, end)
    sar = get_s1_sar(aoi, start, end)
    joined = ee.Join.inner().apply(
        ndvi, sar,
        ee.Filter.maxDifference(
            difference=15 * 24 * 60 * 60 * 1000,
            leftField="system:time_start",
            rightField="system:time_start",
        ),
    )

    def combine(f):
        return ee.Image(f.get("primary")).addBands(ee.Image(f.get("secondary")))

    return ee.ImageCollection(joined.map(combine))


def collection_id_hash(collection: ee.ImageCollection) -> dict:
    """Data-acquisition leaf: commits to the exact set of scene IDs used,
    so re-using/replaying an old scene (Attack Type 1) changes this hash."""
    ids = collection.aggregate_array("system:index").getInfo()
    ids_sorted = sorted(ids)
    return {"scene_ids_hash": sha256_hex(canonical(ids_sorted)), "n_scenes": len(ids_sorted)}


def raster_stage_output(image: ee.Image, band: str, aoi: ee.Geometry, scale: int) -> dict:
    """Statistical-computation leaf output: mean over AOI (matches the
    original script's reduceRegion sensitivity-analysis pattern) PLUS a
    deterministic sample-based hash committing to actual pixel values,
    not just their mean (so an attacker can't preserve the mean while
    changing the underlying distribution)."""
    mean_val = image.reduceRegion(
        reducer=ee.Reducer.mean(), geometry=aoi, scale=scale, maxPixels=1e9, bestEffort=True
    ).get(band).getInfo()

    samples = image.sample(
        region=aoi, scale=scale, numPixels=N_SAMPLES, seed=SAMPLE_SEED, geometries=True
    ).getInfo()

    rows = []
    for feat in samples.get("features", []):
        coords = feat.get("geometry", {}).get("coordinates", [None, None])
        val = feat.get("properties", {}).get(band)
        rows.append({"lon": round(coords[0], 6) if coords[0] is not None else None,
                      "lat": round(coords[1], 6) if coords[1] is not None else None,
                      "val": round(val, 6) if val is not None else None})
    rows.sort(key=lambda r: (r["lon"] or 0, r["lat"] or 0))

    return {
        "mean": None if mean_val is None else round(float(mean_val), 6),
        "n_samples": len(rows),
        "array_hash": sha256_hex(canonical(rows)),
    }


def run_episode(project: str, episode_id: str, params: dict = None) -> list:
    ee.Initialize(project=project)
    params = dict(DEFAULT_PARAMS if params is None else params)
    scale = params["scale_val"]
    aoi = ee.Geometry.Point([AOI_LON, AOI_LAT]).buffer(AOI_BUFFER_M).bounds()

    records = []
    now = time.time()

    def add(label, input_ref, stage_params, output):
        records.append({
            "label": label, "input_ref": input_ref, "params": stage_params,
            "output": output, "timestamp": now,
        })

    print(f"[{episode_id}] pulling S2/S1 metadata for data-acquisition leaves...")
    s2_p1p2 = get_s2_ndvi(aoi, P1_START, P2_END)  # covers both windows for a combined scene-id commitment
    s1_p1p2 = get_s1_sar(aoi, P1_START, P2_END)
    add("data_acquisition_s2",
        {"collection": "COPERNICUS/S2_SR_HARMONIZED", "periods": [f"{P1_START}/{P1_END}", f"{P2_START}/{P2_END}"]},
        {"cloud_pct_lt": 30, "cloud_mask": "QA60_bits_10_11"},
        collection_id_hash(s2_p1p2))
    add("data_acquisition_s1",
        {"collection": "COPERNICUS/S1_GRD", "periods": [f"{P1_START}/{P1_END}", f"{P2_START}/{P2_END}"]},
        {"instrument_mode": "IW", "join_max_diff_days": 15},
        collection_id_hash(s1_p1p2))

    print(f"[{episode_id}] computing period-1 / period-2 correlation...")
    series1 = get_data(aoi, P1_START, P1_END)
    series2 = get_data(aoi, P2_START, P2_END)
    corr1 = series1.reduce(ee.Reducer.pearsonsCorrelation()).select("correlation")
    corr2 = series2.reduce(ee.Reducer.pearsonsCorrelation()).select("correlation")

    add("pearson_corr_period1", {"period": f"{P1_START}/{P1_END}"}, {"reducer": "pearsonsCorrelation"},
        raster_stage_output(corr1, "correlation", aoi, scale))
    add("pearson_corr_period2", {"period": f"{P2_START}/{P2_END}"}, {"reducer": "pearsonsCorrelation"},
        raster_stage_output(corr2, "correlation", aoi, scale))

    delta_corr = corr2.subtract(corr1).rename("delta_corr")
    add("delta_corr", {"depends_on": ["pearson_corr_period1", "pearson_corr_period2"]}, {},
        raster_stage_output(delta_corr, "delta_corr", aoi, scale))

    print(f"[{episode_id}] computing full-period r_t (this covers 2 years of data, may be slow)...")
    r_t = get_data(aoi, FULL_START, FULL_END).reduce(ee.Reducer.pearsonsCorrelation()) \
        .select("correlation").rename("r_t")
    add("r_t", {"period": f"{FULL_START}/{FULL_END}"}, {"reducer": "pearsonsCorrelation"},
        raster_stage_output(r_t, "r_t", aoi, scale))

    print(f"[{episode_id}] computing Moran's I and risk index...")
    weights = [[1, 1, 1], [1, 0, 1], [1, 1, 1]]
    mean_delta = delta_corr.reduceRegion(ee.Reducer.mean(), aoi, scale).get("delta_corr")
    moran = delta_corr.subtract(ee.Number(mean_delta)) \
        .convolve(ee.Kernel.fixed(3, 3, weights)).rename("moran_index")
    add("moran_index", {"depends_on": ["delta_corr"]}, {"kernel": weights},
        raster_stage_output(moran, "moran_index", aoi, scale))

    risk_index = (delta_corr.abs().multiply(params["alpha"])
                  .add(moran.abs().multiply(params["beta"]))
                  .add(r_t.abs().multiply(params["lambda"])))
    risk_index = risk_index.rename("risk_index")
    add("risk_index", {"depends_on": ["delta_corr", "moran_index", "r_t"]},
        {"alpha": params["alpha"], "beta": params["beta"], "lambda": params["lambda"]},
        raster_stage_output(risk_index, "risk_index", aoi, scale))

    change_mask = risk_index.gt(params["tau"]).rename("change_mask")
    changed_count = change_mask.reduceRegion(
        reducer=ee.Reducer.sum(), geometry=aoi, scale=scale, maxPixels=1e9, bestEffort=True
    ).get("change_mask").getInfo()
    cm_output = raster_stage_output(change_mask, "change_mask", aoi, scale)
    cm_output["changed_pixels_est"] = None if changed_count is None else round(float(changed_count))
    add("change_mask", {"depends_on": ["risk_index"]}, {"tau": params["tau"]}, cm_output)

    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, help="Your Google Cloud project ID registered for Earth Engine")
    ap.add_argument("--episode-id", default="almaty-2023_2024-episode-001")
    ap.add_argument("--out", default="real_episode_data.json")
    args = ap.parse_args()

    records = run_episode(args.project, args.episode_id)
    with open(args.out, "w") as f:
        json.dump({"episode_id": args.episode_id, "params": DEFAULT_PARAMS, "records": records}, f, indent=2)
    print(f"\nWrote {len(records)} stage records to {args.out}")
    print("Next: python3 load_real_episode.py --in", args.out)


if __name__ == "__main__":
    main()
