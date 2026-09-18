"""
pipeline.py — A small, reproducible, offline stand-in for the actual
Google Earth Engine pipeline (BSS2026 script). Real Sentinel-1/2 data
requires GEE auth and cannot run in this sandbox; this module reproduces
the *same statistical structure* (Pearson correlation, delta_corr, a 3x3
Moran's-I-style convolution, the weighted risk_index, the tau threshold)
over a small synthetic raster with a fixed seed, so the provenance layer
can be demonstrated end-to-end and the numbers are exactly reproducible
for the paper's evaluation section.

Default parameters intentionally match the GEE script:
    ALPHA = 0.5, BETA = 0.3, LAMBDA = 0.2, TAU = 0.4
"""

from __future__ import annotations
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from merkle import sha256_hex

GRID_SIZE = 24          # stand-in for AOI pixel grid (real run: scale=100m over 10km buffer)
TIME_STEPS_PER_PERIOD = 6  # simulated cloud-free S2/S1 joined observations per summer window

DEFAULT_PARAMS = {"alpha": 0.5, "beta": 0.3, "lambda": 0.2, "tau": 0.4, "scale_val": 100}

MOORE_KERNEL = np.array([[1, 1, 1],
                          [1, 0, 1],
                          [1, 1, 1]], dtype=float)


def _array_hash(arr: np.ndarray) -> str:
    return sha256_hex(np.round(arr, 6).tobytes())


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _convolve_same(arr: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Minimal 'same'-padded 2D convolution (edge-zero-padded), matching
    ee.Image.convolve(ee.Kernel.fixed(3,3,weights)) closely enough for a
    structural PoC."""
    kh, kw = kernel.shape
    ph, pw = kh // 2, kw // 2
    padded = np.pad(arr, ((ph, ph), (pw, pw)), mode="constant")
    out = np.zeros_like(arr)
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            region = padded[i:i + kh, j:j + kw]
            out[i, j] = np.sum(region * kernel)
    return out


def _pearson_stack(ndvi_stack: np.ndarray, sar_stack: np.ndarray) -> np.ndarray:
    """Per-pixel Pearson correlation across the time axis (axis=0),
    mirroring ee.Reducer.pearsonsCorrelation() applied per-pixel over an
    ImageCollection."""
    t = ndvi_stack.shape[0]
    ndvi_mean = ndvi_stack.mean(axis=0)
    sar_mean = sar_stack.mean(axis=0)
    ndvi_dev = ndvi_stack - ndvi_mean
    sar_dev = sar_stack - sar_mean
    cov = (ndvi_dev * sar_dev).sum(axis=0) / t
    ndvi_std = np.sqrt((ndvi_dev ** 2).sum(axis=0) / t)
    sar_std = np.sqrt((sar_dev ** 2).sum(axis=0) / t)
    denom = ndvi_std * sar_std
    denom[denom == 0] = 1e-9
    return cov / denom


@dataclass
class StageRecord:
    label: str
    input_ref: dict
    params: dict
    output: dict          # summary stats + array_hash -- what actually gets hashed as output_i
    operator_did: str
    timestamp: float
    _raw_array: Optional[np.ndarray] = field(default=None, repr=False)  # kept off-chain, for audit recompute only

    def leaf_payload(self) -> dict:
        """Exactly H_i = SHA256(input_ref, params_i, output_i, operator_DID, timestamp) per Section 4.1."""
        return {
            "input_ref": self.input_ref,
            "params": self.params,
            "output": self.output,
            "operator_did": self.operator_did,
            "timestamp": self.timestamp,
        }

    def leaf_hash(self) -> str:
        return sha256_hex(_canonical(self.leaf_payload()))


def _gen_raw_data(seed: int):
    rng = np.random.default_rng(seed)
    shape = (TIME_STEPS_PER_PERIOD, GRID_SIZE, GRID_SIZE)
    # NDVI baseline with mild spatial structure + noise, period 2 has a
    # localized "hidden change" patch injected in the SAR ratio only
    # (the whole point of the optical-radar decoupling method).
    ndvi1 = 0.5 + 0.05 * rng.standard_normal(shape)
    ndvi2 = 0.5 + 0.05 * rng.standard_normal(shape)
    sar1 = 1.2 + 0.1 * rng.standard_normal(shape)
    sar2 = 1.2 + 0.1 * rng.standard_normal(shape)

    # inject a hidden-change patch: SAR shifts but NDVI stays stable (decoupling signal)
    patch = np.s_[:, 8:14, 8:14]
    sar2[patch] += 0.6

    full_ndvi = np.concatenate([ndvi1, ndvi2], axis=0)
    full_sar = np.concatenate([sar1, sar2], axis=0)
    return ndvi1, ndvi2, sar1, sar2, full_ndvi, full_sar


def run_episode(seed: int, operator_did: str, params: Optional[dict] = None,
                 timestamp: Optional[float] = None) -> list:
    """
    Runs the synthetic multi-level pipeline once and returns an ordered
    list of StageRecord, mirroring the GEE script's stage order:

      0. data_acquisition_s2
      1. data_acquisition_s1
      2. pearson_corr_period1   (corr1)
      3. pearson_corr_period2   (corr2)
      4. delta_corr             (deltaCorr)
      5. r_t                    (full-period correlation)
      6. moran_index
      7. risk_index
      8. change_mask
    """
    params = dict(DEFAULT_PARAMS if params is None else params)
    ts = time.time() if timestamp is None else timestamp
    ndvi1, ndvi2, sar1, sar2, full_ndvi, full_sar = _gen_raw_data(seed)

    records = []

    def add(label, input_ref, stage_params, output_dict, raw=None):
        rec = StageRecord(label=label, input_ref=input_ref, params=stage_params,
                           output=output_dict, operator_did=operator_did,
                           timestamp=ts, _raw_array=raw)
        records.append(rec)
        return rec

    add("data_acquisition_s2",
        {"collection": "COPERNICUS/S2_SR_HARMONIZED", "periods": ["2023-06-01/2023-08-31", "2024-06-01/2024-08-31"]},
        {"cloud_pct_lt": 30, "cloud_mask": "QA60_bits_10_11"},
        {"n_images_ref_hash": sha256_hex(f"s2-seed{seed}".encode())})

    add("data_acquisition_s1",
        {"collection": "COPERNICUS/S1_GRD", "periods": ["2023-06-01/2023-08-31", "2024-06-01/2024-08-31"]},
        {"instrument_mode": "IW", "join_max_diff_days": 15},
        {"n_images_ref_hash": sha256_hex(f"s1-seed{seed}".encode())})

    corr1 = _pearson_stack(ndvi1, sar1)
    add("pearson_corr_period1", {"period": "2023-06-01/2023-08-31"}, {"reducer": "pearsonsCorrelation"},
        {"mean": float(corr1.mean()), "array_hash": _array_hash(corr1)}, raw=corr1)

    corr2 = _pearson_stack(ndvi2, sar2)
    add("pearson_corr_period2", {"period": "2024-06-01/2024-08-31"}, {"reducer": "pearsonsCorrelation"},
        {"mean": float(corr2.mean()), "array_hash": _array_hash(corr2)}, raw=corr2)

    delta_corr = corr2 - corr1
    add("delta_corr", {"depends_on": ["pearson_corr_period1", "pearson_corr_period2"]}, {},
        {"mean": float(delta_corr.mean()), "array_hash": _array_hash(delta_corr)}, raw=delta_corr)

    r_t = _pearson_stack(full_ndvi, full_sar)
    add("r_t", {"period": "2023-01-01/2024-12-31"}, {"reducer": "pearsonsCorrelation"},
        {"mean": float(r_t.mean()), "array_hash": _array_hash(r_t)}, raw=r_t)

    mean_delta = delta_corr.mean()
    moran = _convolve_same(delta_corr - mean_delta, MOORE_KERNEL)
    add("moran_index", {"depends_on": ["delta_corr"]}, {"kernel": MOORE_KERNEL.tolist()},
        {"mean": float(moran.mean()), "array_hash": _array_hash(moran)}, raw=moran)

    risk_index = (np.abs(delta_corr) * params["alpha"]
                  + np.abs(moran) * params["beta"]
                  + np.abs(r_t) * params["lambda"])
    add("risk_index", {"depends_on": ["delta_corr", "moran_index", "r_t"]},
        {"alpha": params["alpha"], "beta": params["beta"], "lambda": params["lambda"]},
        {"mean": float(risk_index.mean()), "array_hash": _array_hash(risk_index)}, raw=risk_index)

    change_mask = (risk_index > params["tau"]).astype(float)
    add("change_mask", {"depends_on": ["risk_index"]}, {"tau": params["tau"]},
        {"changed_pixels": int(change_mask.sum()), "array_hash": _array_hash(change_mask)}, raw=change_mask)

    return records
