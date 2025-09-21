#!/usr/bin/env python3
"""
plot_fct_abs_abm_lqd.py
───────────────────────
Parse stats files and draw grouped-bar charts of **absolute** FCTs
(µs) for **only** ABM and LQD (no normalization).

Charts produced (per dataset: incast/websearch, per flow: short/medium/long):
  • 99-percentile FCT (µs)
  • 99.9-percentile FCT (µs)

Input lines expected in each stats_*.txt (examples):
  - "workloads/websearch-trace-100G-load-0.6.csv.processed"
  - "p99 FCT short flows: 134.05us"
  - "p99.9 FCT long flows: 20101.903us"

Usage:
  python plot_fct_abs_abm_lqd.py --files stats_abm.txt stats_lqd.txt --outdir graphs_abs
"""

import os
import re
import argparse
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from collections import defaultdict

# ── Display mapping (only ABM & LQD) ────────────────────────────
ALGO_META = {
    "abm": ("ABM", "#FFD700"),
    "lqd": ("LQD", "#32CD32"),
}
ORDERED_LABELS = ["ABM", "LQD"]

DATASET_XLABEL = {"incast": "Incast Degree", "websearch": "Load"}

# ——— Bigger fonts for ~0.49× two-column LaTeX width ———
YLABEL_FONTSIZE = 44
XLABEL_FONTSIZE = 42
YTICK_FONTSIZE  = 40
XTICK_FONTSIZE  = 38
LEGEND_FONTSIZE = 40
TICK_LENGTH     = 12
TICK_WIDTH      = 2.4

# Target number of visible y-ticks (after hiding the very top one)
MAX_YTICKS = 9

WORKLOAD_RE = re.compile(
    r"workloads/(?P<kind>incast|websearch)-trace-100G-(?P<axis>degree|load)-(?P<val>[0-9.]+)\.csv\.processed",
    re.I
)

def parse_file(path, algo_key, agg):
    """
    Fill agg[dataset][x][algo]['short'/'medium'/'long'][metric] = value.
    FCT metrics parsed: 'p99', 'p999' (µs). (Averages are ignored for this script.)
    """
    algo_label, _ = ALGO_META[algo_key]
    dataset = None; xval = None
    with open(path, "r", errors="ignore") as fh:
        for ln in fh:
            m = WORKLOAD_RE.search(ln)
            if m:
                dataset = m.group("kind").lower()
                xval = float(m.group("val"))
                continue
            if not dataset:
                continue
            # Short flows
            sm = re.search(r"p99 FCT short flows:\s*([\d.]+)\s*us", ln, re.I)
            if sm: agg[dataset][xval][algo_label]["short"]["p99"]  = float(sm.group(1));  continue
            sm = re.search(r"p99\.9 FCT short flows:\s*([\d.]+)\s*us", ln, re.I)
            if sm: agg[dataset][xval][algo_label]["short"]["p999"] = float(sm.group(1));  continue
            # Medium flows (present in websearch only)
            sm = re.search(r"p99 FCT medium flows:\s*([\d.]+)\s*us", ln, re.I)
            if sm: agg[dataset][xval][algo_label]["medium"]["p99"]  = float(sm.group(1)); continue
            sm = re.search(r"p99\.9 FCT medium flows:\s*([\d.]+)\s*us", ln, re.I)
            if sm: agg[dataset][xval][algo_label]["medium"]["p999"] = float(sm.group(1)); continue
            # Long flows
            sm = re.search(r"p99 FCT long flows:\s*([\d.]+)\s*us", ln, re.I)
            if sm: agg[dataset][xval][algo_label]["long"]["p99"]  = float(sm.group(1));  continue
            sm = re.search(r"p99\.9 FCT long flows:\s*([\d.]+)\s*us", ln, re.I)
            if sm: agg[dataset][xval][algo_label]["long"]["p999"] = float(sm.group(1));  continue

def compact_even_ticks(ax, max_ticks: int, bottom: float = 0.0):
    """Equally spaced ticks with a capped count and a little headroom."""
    ax.set_ylim(bottom=bottom)
    locator = MaxNLocator(nbins=max_ticks, steps=[1, 2, 2.5, 5, 10])
    ax.yaxis.set_major_locator(locator)
    ticks = [t for t in ax.get_yticks() if t >= bottom]
    if len(ticks) < 2:
        ax.tick_params(axis="y", labelsize=YTICK_FONTSIZE, length=TICK_LENGTH, width=TICK_WIDTH)
        return
    delta = ticks[1] - ticks[0]
    ax.set_ylim(top=ticks[-1] + delta, bottom=bottom)
    ax.yaxis.set_major_locator(locator)
    ticks2 = [t for t in ax.get_yticks() if t >= bottom]
    if len(ticks2) >= 2:
        ax.set_yticks(ticks2[:-1])
    ax.tick_params(axis="y", labelsize=YTICK_FONTSIZE, length=TICK_LENGTH, width=TICK_WIDTH)

def grouped_bars(ax, x_ticks, data_by_label, colors, ylabel, dataset):
    """Two bars per group (ABM, LQD), bars touch; groups slightly shrunk."""
    n = len(ORDERED_LABELS)  # = 2
    group_gap   = 0.10
    group_width = 1.0 - group_gap

    shrink  = 0.82   # thinner bars (tune 0.78–0.86 to taste)
    bar_w   = (group_width / n) * shrink
    block_w = n * bar_w

    x_centers  = np.arange(len(x_ticks), dtype=float)
    group_left = x_centers - group_width / 2.0
    block_left = group_left + (group_width - block_w) / 2.0

    for j, lbl in enumerate(ORDERED_LABELS):
        y = np.array(data_by_label.get(lbl, []), dtype=float)
        lefts = block_left + j * bar_w
        ax.bar(lefts, y, align="edge", width=bar_w, label=lbl,
               color=colors[lbl], edgecolor="black", linewidth=1.8)

    ax.set_ylabel(ylabel, fontsize=YLABEL_FONTSIZE, labelpad=16)
    ax.set_xlabel(DATASET_XLABEL[dataset], fontsize=XLABEL_FONTSIZE, labelpad=10)
    ax.set_xticks(x_centers)
    ax.set_xticklabels([str(t) for t in x_ticks], fontsize=XTICK_FONTSIZE)
    ax.tick_params(axis="x", labelsize=XTICK_FONTSIZE, length=TICK_LENGTH, width=TICK_WIDTH)
    ax.yaxis.grid(True, linestyle=":", color="#999999", linewidth=1.2)
    ax.set_axisbelow(True)

def square_legend(ax):
    """Legend in a compact grid (2 items → 2 columns)."""
    lgd = ax.legend(loc="upper left", frameon=True, fontsize=LEGEND_FONTSIZE,
                    ncol=2, columnspacing=1.2, handlelength=1.8,
                    borderpad=0.7, labelspacing=0.7)
    lgd.get_frame().set_edgecolor("black")
    lgd.get_frame().set_linewidth(1.4)

def _any_finite(series):
    """True if any algo has any finite value."""
    for lbl in ORDERED_LABELS:
        arr = np.asarray(series.get(lbl, []), dtype=float)
        if np.isfinite(arr).any():
            return True
    return False

def plot_all(agg, outdir):
    colors = {ALGO_META[k][0]: ALGO_META[k][1] for k in ALGO_META}
    for dataset in ("incast", "websearch"):
        if dataset not in agg:
            continue
        xvals = sorted(agg[dataset].keys())

        # ── Absolute FCT at 99p and 99.9p ─────────────────────────
        for metric, ylabel in (("p99", "99-percentile FCT (µs)"),
                               ("p999", "99.9-percentile FCT (µs)")):
            for flow in ("short", "medium", "long"):
                series = {lbl: [] for lbl in ORDERED_LABELS}
                for lbl in ORDERED_LABELS:
                    for xv in xvals:
                        v = agg[dataset][xv].get(lbl, {}).get(flow, {}).get(metric, np.nan)
                        series[lbl].append(v)

                if not _any_finite(series):
                    continue

                fig, ax = plt.subplots(figsize=(14.5, 12.5))
                grouped_bars(ax, xvals, series, colors, ylabel, dataset)
                square_legend(ax)
                compact_even_ticks(ax, MAX_YTICKS, bottom=0)
                fig.tight_layout()
                fn = f"fct_abs_{metric}_{flow}_{dataset}_ABM_vs_LQD.png"
                fig.savefig(os.path.join(outdir, fn), dpi=400, bbox_inches="tight")
                plt.close(fig)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", nargs="*", default=[
        "stats_abm.txt", "stats_lqd.txt",
    ], help="Paths to stats files (ABM/LQD only; any order).")
    ap.add_argument("--outdir", default="graphs_abs", help="Where to write PNGs.")
    args = ap.parse_args()

    agg = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {
        "short": {}, "medium": {}, "long": {}
    })))
    for path in args.files:
        base = os.path.basename(path).lower()
        algo_key = None
        if "stats_" in base:
            if   "abm" in base: algo_key = "abm"
            elif "lqd" in base: algo_key = "lqd"
        if not algo_key:
            continue
        if not os.path.isfile(path):
            print(f"⚠️  File not found: {path}")
            continue
        parse_file(path, algo_key, agg)

    if not agg:
        print("No data parsed. Check --files paths.")
        return

    os.makedirs(args.outdir, exist_ok=True)
    plot_all(agg, args.outdir)
    print(f"Done. PNGs written to: {args.outdir}")

if __name__ == "__main__":
    main()
