#!/usr/bin/env python3
"""
plot_fct_bars.py
────────────────
Parse stats files (DT/ABM/OBM/LQD) and draw grouped-bar charts.

All graphs are **normalized to OBM**:
  • Normalized 99-percentile FCT (short / medium / long)
  • Normalized 99.9-percentile FCT (short / medium / long)
  • Normalized Average Throughput (long flows only)

Input lines expected in each stats_*.txt (examples):
  - "Average FCT short flows: 9.769us"
  - "p99 FCT short flows: 134.05us"
  - "p99.9 FCT short flows: 269.4us"
  - "Average FCT long flows: 8252.744us"
  - "p99 FCT long flows: 19790.137us"
  - "p99.9 FCT long flows: 20101.903us"
  - "Average recv throughput (long): 5.246 Gbps"

Usage:
  python plot_fct_bars.py --files stats_dt.txt stats_abm.txt stats_obm.txt stats_lqd.txt --outdir graphs --dpi 180
"""

import os
import re
import argparse
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from collections import defaultdict

# ── Display mapping ──────────────────────────────────────────────
ALGO_META = {
    "dt":  ("DT",  "#00FFFF"),
    "abm": ("ABM", "#FFD700"),
    "obm": ("OBM", "#FF0000"),
    "lqd": ("LQD", "#32CD32"),
}
ORDERED_LABELS = ["DT", "ABM", "OBM", "LQD"]
BASELINE_LABEL = "OBM"  # normalization reference (must match an ORDERED_LABELS item)

DATASET_XLABEL = {"incast": "Incast Degree", "websearch": "Network Load"}

# ——— Bigger fonts for ~0.49× two-column LaTeX width ———
YLABEL_FONTSIZE = 53
XLABEL_FONTSIZE = 53
YTICK_FONTSIZE  = 53
XTICK_FONTSIZE  = 53
LEGEND_FONTSIZE = 39
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
    FCT metrics: 'avg', 'p99', 'p999' (all in µs). Throughput: 'tput_avg_gbps' (long only).
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
            sm = re.search(r"Average FCT short flows:\s*([\d.]+)\s*us", ln, re.I)
            if sm: agg[dataset][xval][algo_label]["short"]["avg"] = float(sm.group(1));  continue
            sm = re.search(r"p99 FCT short flows:\s*([\d.]+)\s*us", ln, re.I)
            if sm: agg[dataset][xval][algo_label]["short"]["p99"]  = float(sm.group(1));  continue
            sm = re.search(r"p99\.9 FCT short flows:\s*([\d.]+)\s*us", ln, re.I)
            if sm: agg[dataset][xval][algo_label]["short"]["p999"] = float(sm.group(1));  continue
            # Medium flows (present in websearch only)
            sm = re.search(r"Average FCT medium flows:\s*([\d.]+)\s*us", ln, re.I)
            if sm: agg[dataset][xval][algo_label]["medium"]["avg"] = float(sm.group(1)); continue
            sm = re.search(r"p99 FCT medium flows:\s*([\d.]+)\s*us", ln, re.I)
            if sm: agg[dataset][xval][algo_label]["medium"]["p99"]  = float(sm.group(1)); continue
            sm = re.search(r"p99\.9 FCT medium flows:\s*([\d.]+)\s*us", ln, re.I)
            if sm: agg[dataset][xval][algo_label]["medium"]["p999"] = float(sm.group(1)); continue
            # Long flows
            sm = re.search(r"Average FCT long flows:\s*([\d.]+)\s*us", ln, re.I)
            if sm: agg[dataset][xval][algo_label]["long"]["avg"] = float(sm.group(1));   continue
            sm = re.search(r"p99 FCT long flows:\s*([\d.]+)\s*us", ln, re.I)
            if sm: agg[dataset][xval][algo_label]["long"]["p99"]  = float(sm.group(1));  continue
            sm = re.search(r"p99\.9 FCT long flows:\s*([\d.]+)\s*us", ln, re.I)
            if sm: agg[dataset][xval][algo_label]["long"]["p999"] = float(sm.group(1));  continue
            # Average receive throughput (long) in Gbps
            sm = re.search(r"Average\s+recv\s+throughput\s*\(long\):\s*([\d.]+)\s*Gbps", ln, re.I)
            if sm:
                agg[dataset][xval][algo_label]["long"]["tput_avg_gbps"] = float(sm.group(1))
                continue

def compact_even_ticks(ax, max_ticks: int, bottom: float = 0.0):
    """
    Equally spaced ticks with a capped count.
    Add one extra tick of headroom; hide the top tick so space remains.
    """
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
    """
    Bars *touch* inside each group (slightly shrunk as a block for aesthetics).
    """
    n = len(ORDERED_LABELS)
    group_gap   = 0.10
    group_width = 1.0 - group_gap

    shrink = 0.90                      # shrink block 10% but bars still touch
    bar_w  = (group_width / n) * shrink
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

def square_legend(ax, loc="upper left"):
    """Legend in a square-ish grid (4 items → 2×2)."""
    import math
    ncol = int(math.ceil(math.sqrt(len(ORDERED_LABELS))))
    lgd = ax.legend(loc=loc, frameon=True, fontsize=LEGEND_FONTSIZE,
                    ncol=ncol, columnspacing=1.2, handlelength=1.8,
                    borderpad=0.5, labelspacing=0.5)
    lgd.get_frame().set_edgecolor("black")
    lgd.get_frame().set_linewidth(1.4)

def _any_finite(series):
    """True if any algo has any finite value."""
    for lbl in ORDERED_LABELS:
        arr = np.asarray(series.get(lbl, []), dtype=float)
        if np.isfinite(arr).any():
            return True
    return False

def _normalize_series(series, ref_vals):
    """Divide each algorithm series by the reference values per x."""
    out = {}
    ref = np.asarray(ref_vals, dtype=float)
    for lbl, ys in series.items():
        arr = np.asarray(ys, dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            out_arr = np.where(np.isfinite(ref) & (ref != 0), arr / ref, np.nan)
        out[lbl] = out_arr.tolist()
    return out

def _legend_loc_for(dataset: str, flow: str, metric: str) -> str:
    """
    Put legend in upper-right ONLY for:
      - p99 (99p) + short + websearch
      - p99 (99p) + short + incast
    Everything else stays upper-left (default).
    """
    if metric == "p99" and flow == "short" and dataset in ("websearch", "incast"):
        return "upper right"
    return "upper left"

def plot_all(agg, outdir, dpi: int):
    colors = {ALGO_META[k][0]: ALGO_META[k][1] for k in ALGO_META}
    for dataset in ("incast", "websearch"):
        if dataset not in agg:
            continue
        xvals = sorted(agg[dataset].keys())

        # ── Normalized 99p and 99.9p FCT (per flow) ───────────────
        for metric, ylabel in (("p99", "Normalized 99-perc. FCT"),
                               ("p999", "Normalized 99.9-percentile FCT")):
            for flow in ("short", "medium", "long"):
                series = {lbl: [] for lbl in ORDERED_LABELS}
                for lbl in ORDERED_LABELS:
                    for xv in xvals:
                        v = agg[dataset][xv].get(lbl, {}).get(flow, {}).get(metric, np.nan)
                        series[lbl].append(v)

                if not _any_finite(series):
                    continue

                ref_vals = series.get(BASELINE_LABEL, [])
                series_norm = _normalize_series(series, ref_vals)

                fig, ax = plt.subplots(figsize=(14.5, 12.5))
                grouped_bars(ax, xvals, series_norm, colors, ylabel, dataset)
                square_legend(ax, loc=_legend_loc_for(dataset, flow, metric))
                compact_even_ticks(ax, MAX_YTICKS, bottom=0)
                fig.tight_layout()
                fn = f"fct_{metric}_{flow}_{dataset}_norm_{BASELINE_LABEL}.png"
                fig.savefig(os.path.join(outdir, fn), dpi=dpi, bbox_inches="tight")
                plt.close(fig)

        # ── Normalized Average Throughput (long flows) ────────────
        series_tput = {lbl: [] for lbl in ORDERED_LABELS}
        for lbl in ORDERED_LABELS:
            for xv in xvals:
                v = agg[dataset][xv].get(lbl, {}).get("long", {}).get("tput_avg_gbps", np.nan)
                series_tput[lbl].append(v)

        if _any_finite(series_tput):
            ref_vals = series_tput.get(BASELINE_LABEL, [])
            series_tput_norm = _normalize_series(series_tput, ref_vals)

            fig, ax = plt.subplots(figsize=(14.5, 12.5))
            ylabel = "Normalized Avg. Throughput"
            grouped_bars(ax, xvals, series_tput_norm, colors, ylabel, dataset)
            square_legend(ax)  # default upper-left
            compact_even_ticks(ax, MAX_YTICKS, bottom=0)
            fig.tight_layout()
            fn = f"throughput_avg_long_{dataset}_norm_{BASELINE_LABEL}.png"
            fig.savefig(os.path.join(outdir, fn), dpi=dpi, bbox_inches="tight")
            plt.close(fig)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", nargs="*", default=[
        "stats_dt.txt", "stats_abm.txt", "stats_obm.txt", "stats_lqd.txt",
    ], help="Paths to stats files (any order).")
    ap.add_argument("--outdir", default=".", help="Where to write PNGs.")
    ap.add_argument("--dpi", type=int, default=180,
                    help="PNG resolution (DPI). Lower values → smaller files. Default: 180")
    args = ap.parse_args()

    agg = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {
        "short": {}, "medium": {}, "long": {}
    })))
    for path in args.files:
        base = os.path.basename(path).lower()
        algo_key = None
        if "stats_" in base:
            if   "dt"  in base: algo_key = "dt"
            elif "abm" in base: algo_key = "abm"
            elif "obm" in base: algo_key = "obm"
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
    plot_all(agg, args.outdir, dpi=args.dpi)
    print(f"Done. PNGs written to: {args.outdir} (DPI={args.dpi})")

if __name__ == "__main__":
    main()
