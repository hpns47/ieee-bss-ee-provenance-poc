"""
make_figures.py — Renders Figures A-E specified in BSS2026_Improvement_Brief.md
Section 2, from attack_sweep_results.json (attack_sweep.py) and
benchmark_results.json (benchmark.py). Both inputs must exist already.

All figures: 300 DPI, serif font (Times New Roman if available, else DejaVu
Serif), English labels, no em/en-dashes, sized for IEEE single-column
(~3.4in) except Fig. B which is sized a bit taller for 9 row labels.

Run: python3 attack_sweep.py && python3 benchmark.py && python3 make_figures.py
Output: fig_A_detection_vs_magnitude.png ... fig_E_storage_growth.png
"""
from __future__ import annotations
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.family"] = "serif"
plt.rcParams["font.serif"] = ["Times New Roman", "DejaVu Serif"]
plt.rcParams["font.size"] = 8
plt.rcParams["axes.titlesize"] = 9
plt.rcParams["axes.labelsize"] = 8.5
plt.rcParams["legend.fontsize"] = 7.5

SINGLE_COL = (3.4, 2.5)
TAU_BASE = 0.4


def load(path):
    with open(path) as f:
        return json.load(f)


def fig_a(sweep, out="fig_A_detection_vs_magnitude.png"):
    rows = [r for r in sweep if r["attack_type"] == "type2_parameter" and r["target_stage"] == "change_mask"]
    by_mag = {}
    for r in rows:
        pct = round(abs(r["magnitude"]) / TAU_BASE * 100, 4)
        by_mag.setdefault(pct, []).append(r)
    xs = sorted(by_mag)
    proposed = [np.mean([r["proposed_detection_rate"] for r in by_mag[x]]) * 100 for x in xs]
    naive = [np.mean([r["naive_detection_rate"] for r in by_mag[x]]) * 100 for x in xs]

    fig, ax = plt.subplots(figsize=SINGLE_COL)
    ax.plot(xs, proposed, marker="o", label="Proposed (Merkle)", color="#1a4d7a", linewidth=1.6)
    ax.plot(xs, naive, marker="s", label="Naive baseline", color="#b23a3a", linewidth=1.6, linestyle="--")
    ax.set_xlabel(r"Attack magnitude on $\tau$ (% of baseline value)")
    ax.set_ylabel("Detection rate (%)")
    ax.set_title("Fig. A: Tamper-injection coverage vs. injected\nmagnitude (Type-2, change_mask tau)")
    ax.set_ylim(-5, 105)
    ax.legend(loc="center right")
    ax.grid(alpha=0.3, linewidth=0.5)
    fig.tight_layout()
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")


def fig_b(sweep, out="fig_B_localization_heatmap.png"):
    stages = [
        "data_acquisition_s2", "data_acquisition_s1",
        "pearson_corr_period1", "pearson_corr_period2",
        "delta_corr", "r_t", "moran_index", "risk_index", "change_mask",
    ]
    cols = ["type2_parameter", "type3_output"]
    grid = np.full((len(stages), len(cols)), np.nan)
    for r in sweep:
        if r["attack_type"] not in cols:
            continue
        i = stages.index(r["target_stage"])
        j = cols.index(r["attack_type"])
        prev = grid[i, j]
        val = r["proposed_localization_accuracy"] * 100
        grid[i, j] = val if np.isnan(prev) else (prev + val) / 2

    fig, ax = plt.subplots(figsize=(3.4, 4.2))
    masked = np.ma.masked_invalid(grid)
    cmap = plt.get_cmap("Greens").copy()
    cmap.set_bad(color="#eeeeee")
    im = ax.imshow(masked, cmap=cmap, vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels(["Type-2\n(parameter)", "Type-3\n(output)"])
    ax.set_yticks(range(len(stages)))
    ax.set_yticklabels(stages, fontsize=7)
    for i in range(len(stages)):
        for j in range(len(cols)):
            v = grid[i, j]
            txt = "N/A" if np.isnan(v) else f"{v:.0f}%"
            ax.text(j, i, txt, ha="center", va="center", fontsize=6.5,
                     color="black" if (np.isnan(v) or v < 60) else "white")
    ax.set_title("Fig. B: Localization accuracy by stage\nand attack type")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="Localization accuracy (%)")
    fig.tight_layout()
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")


def fig_c(sweep, out="fig_C_type1_detection.png"):
    rows = {r["target_stage"]: r for r in sweep if r["attack_type"] == "type1_data"}
    labels = ["data_acquisition_s2\n(Sentinel-2)", "data_acquisition_s1\n(Sentinel-1)"]
    keys = ["data_acquisition_s2", "data_acquisition_s1"]
    proposed = [rows[k]["proposed_detection_rate"] * 100 for k in keys]
    naive = [rows[k]["naive_detection_rate"] * 100 for k in keys]

    x = np.arange(len(labels))
    width = 0.32
    fig, ax = plt.subplots(figsize=SINGLE_COL)
    ax.bar(x - width / 2, proposed, width, label="Proposed (Merkle)", color="#1a4d7a")
    ax.bar(x + width / 2, naive, width, label="Naive baseline", color="#b23a3a")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylabel("Detection rate (%)")
    ax.set_ylim(0, 110)
    ax.set_title("Fig. C: Type-1 (data-level) scene\nreplay detection")
    ax.legend(loc="upper center")
    ax.grid(alpha=0.3, axis="y", linewidth=0.5)
    fig.tight_layout()
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")


def fig_d(bench, out="fig_D_latency_loglog.png"):
    overhead = bench["overhead_by_scale"]
    order = ["100m", "50m", "30m", "20m", "10m"]
    # n_leaves is constant (9); use pixel-count proxy grid^2 via known SCALE_TO_GRID mapping
    scale_to_grid = {"100m": 24, "50m": 34, "30m": 48, "20m": 63, "10m": 96}
    pixel_proxy = [scale_to_grid[label] ** 2 for label in order]
    pipe_ms = [overhead[label]["pipe_mean"] for label in order]
    anchor_ms = [overhead[label]["anchor_mean"] for label in order]

    fig, ax = plt.subplots(figsize=(3.6, 2.8))
    ax.loglog(pixel_proxy, pipe_ms, marker="o", label="Pipeline compute", color="#1a4d7a")
    ax.loglog(pixel_proxy, anchor_ms, marker="s", label="Hash+Merkle+sign", color="#b23a3a")
    ax.set_xticks(pixel_proxy)
    ax.set_xticklabels([f"{label}\n({px}px)" for label, px in zip(order, pixel_proxy)], fontsize=6)
    ax.set_xlabel("GEE scale (grid cells)")
    ax.set_ylabel("Time (ms)")
    ax.set_title("Fig. D: Latency vs. resolution (log-log)")
    ax.legend(loc="upper left", fontsize=7)
    ax.grid(alpha=0.3, which="both", linewidth=0.4)
    fig.tight_layout()
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")


def fig_e(bench, out="fig_E_storage_growth.png"):
    proj = bench["storage_projection"]
    cadences = ["monthly monitoring", "bi-weekly monitoring", "weekly monitoring"]
    fig, ax = plt.subplots(figsize=SINGLE_COL)
    colors = {"monthly monitoring": "#1a4d7a", "bi-weekly monitoring": "#3a8a5c", "weekly monitoring": "#b23a3a"}
    for cadence in cadences:
        rows = sorted([r for r in proj if r["cadence"] == cadence], key=lambda r: r["years"])
        xs = [r["years"] for r in rows]
        ys = [r["on_chain_bytes"] / 1024 for r in rows]
        ax.plot(xs, ys, marker="o", label=cadence.replace(" monitoring", ""), color=colors[cadence])
    ax.set_xlabel("Monitoring period (years)")
    ax.set_ylabel("Anchored ledger storage (KB)")
    ax.set_title("Fig. E: Anchored ledger storage growth\n(O(episodes) scaling)")
    ax.set_xticks([1, 2, 5])
    ax.legend(loc="upper left")
    ax.grid(alpha=0.3, linewidth=0.5)
    fig.tight_layout()
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")


def fig_f(fp_results, out="fig_F_false_positive_rate.png"):
    labels = {
        "genuine_unmodified": "Genuine\n(unmodified)",
        "legitimate_new_param_recomputed": "New param\n(recomputed)",
        "legitimate_old_episode_naive_check": "Old episode,\nnaive check (bug)",
        "legitimate_old_episode_scoped_check": "Old episode,\nscoped check (fix)",
    }
    order = list(labels)
    rates = [next(r["false_positive_rate"] for r in fp_results if r["scenario"] == k) * 100 for k in order]
    colors = ["#1a4d7a", "#1a4d7a", "#b23a3a", "#3a8a5c"]

    fig, ax = plt.subplots(figsize=(4.2, 2.8))
    x = np.arange(len(order))
    ax.bar(x, rates, color=colors, width=0.6)
    for i, v in enumerate(rates):
        ax.text(i, v + 3, f"{v:.0f}%", ha="center", fontsize=7)
    ax.set_xticks(x)
    ax.set_xticklabels([labels[k] for k in order], fontsize=6.5, rotation=20, ha="right")
    ax.set_ylabel("False positive rate (%)")
    ax.set_ylim(0, 115)
    ax.set_title("Fig. F: False positive rate across\nlegitimate scenarios")
    ax.grid(alpha=0.3, axis="y", linewidth=0.5)
    fig.tight_layout()
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")


def main():
    sweep = load("attack_sweep_results.json")
    bench = load("benchmark_results.json")
    fig_a(sweep)
    fig_b(sweep)
    fig_c(sweep)
    fig_d(bench)
    fig_e(bench)
    try:
        fp_results = load("fp_sweep_results.json")
        fig_f(fp_results)
    except FileNotFoundError:
        print("skipped Fig. F: fp_sweep_results.json not found (run fp_sweep.py first)")


if __name__ == "__main__":
    main()
