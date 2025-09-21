#!/usr/bin/env python3
"""
plot_reordering_summary.py  (styled to match plot_fct_bars.py)

Generates two grouped bar charts across algorithms and experiments (loads):
1) Max consecutive packet reorders (per experiment)          → y-label: "Max consecutive packet reorders"
2) Total packets reordered, scaled to thousands (per experiment)
   → y-label: "Packets Reordered (in Thousands)"

Inputs (per algorithm subfolder):
- Raw TXT file containing multiple experiments separated by lines of only '@'
- CSVs produced by reorder_burst_multi_store_min.py:
    exp_001_flow_max.csv
    exp_002_flow_max.csv
    exp_003_flow_max.csv
  (the script searches recursively for these)

Outputs (in --out-dir, default: plots_reordering):
- max_reordering_per_experiment.png
- total_reorders_per_experiment.png
- summary.csv (rows: load, algorithm, overall_max_per_flow, total_reorders)

Usage examples:
  python3 plot_reordering_summary.py
  python3 plot_reordering_summary.py --algos DT ABM OBM LQD --loads 0.3 0.6 0.9
  python3 plot_reordering_summary.py --input-file flows_with_experiments.txt
"""

import argparse
import csv
import os
import re
from pathlib import Path
from typing import Dict, List
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

# ---------- Style (mirrors plot_fct_bars.py) ----------
ALGO_COLORS = {
    "DT":  "#00FFFF",
    "ABM": "#FFD700",
    "OBM": "#FF0000",
    "LQD": "#32CD32",
}

# Bigger fonts, thick ticks, dotted grids
YLABEL_FONTSIZE = 44
XLABEL_FONTSIZE = 42
YTICK_FONTSIZE  = 40
XTICK_FONTSIZE  = 38
LEGEND_FONTSIZE = 40
TICK_LENGTH     = 12
TICK_WIDTH      = 2.4
MAX_YTICKS      = 9

def square_legend(ax, labels, fontsize=None):
    fs = fontsize or LEGEND_FONTSIZE
    n = len(labels)
    ncol = int(np.ceil(np.sqrt(max(1, n))))
    lgd = ax.legend(loc="upper left", frameon=True, fontsize=fs,
                    ncol=ncol, columnspacing=1.2, handlelength=1.8,
                    borderpad=0.7, labelspacing=0.7)
    lgd.get_frame().set_edgecolor("black")
    lgd.get_frame().set_linewidth(1.4)

def compact_even_ticks(ax, max_ticks: int, bottom: float = 0.0):
    ax.set_ylim(bottom=bottom)
    locator = MaxNLocator(nbins=max_ticks, steps=[1, 2, 2.5, 5, 10])
    ax.yaxis.set_major_locator(locator)
    ticks = [t for t in ax.get_yticks() if t >= bottom]
    if len(ticks) >= 2:
        delta = ticks[1] - ticks[0]
        ax.set_ylim(top=ticks[-1] + delta, bottom=bottom)
        ax.yaxis.set_major_locator(locator)
        ticks2 = [t for t in ax.get_yticks() if t >= bottom]
        if len(ticks2) >= 2:
            ax.set_yticks(ticks2[:-1])
    ax.tick_params(axis="y", labelsize=YTICK_FONTSIZE, length=TICK_LENGTH, width=TICK_WIDTH)

def grouped_bars(ax, x_ticks, data_matrix, legend_labels, color_for_label, xlabel, ylabel):
    """
    Bars *touch* inside each group (shrunk block), solid edges, dotted y-grid.
    data_matrix: shape (G groups, B bars)
    legend_labels: list of length B, displayed in that order
    """
    data_matrix = np.asarray(data_matrix, dtype=float)
    if data_matrix.ndim == 1:
        data_matrix = data_matrix[:, None]
    G, B = data_matrix.shape

    group_gap   = 0.10
    group_width = 1.0 - group_gap
    shrink      = 0.90
    bar_w       = (group_width / max(B, 1)) * shrink
    block_w     = B * bar_w

    x_centers  = np.arange(G, dtype=float)
    group_left = x_centers - group_width / 2.0
    block_left = group_left + (group_width - block_w) / 2.0

    for j, lbl in enumerate(legend_labels):
        y = data_matrix[:, j]
        lefts = block_left + j * bar_w
        ax.bar(lefts, y, align="edge", width=bar_w, label=lbl,
               color=color_for_label(lbl), edgecolor="black", linewidth=1.8)

    ax.set_ylabel(ylabel, fontsize=YLABEL_FONTSIZE, labelpad=16)
    ax.set_xlabel("Load", fontsize=XLABEL_FONTSIZE, labelpad=10)
    ax.set_xticks(x_centers)
    ax.set_xticklabels([str(t) for t in x_ticks], fontsize=XTICK_FONTSIZE)
    ax.tick_params(axis="x", labelsize=XTICK_FONTSIZE, length=TICK_LENGTH, width=TICK_WIDTH)
    ax.yaxis.grid(True, linestyle=":", color="#999999", linewidth=1.2)
    ax.set_axisbelow(True)

# ---------- Helpers to find/parse files ----------
FLOW_MAX_PATTERN = re.compile(r"exp_(\d+)_flow_max\.csv$", re.I)
SEP_RE = re.compile(r"^@+$")  # separator line

def discover_algo_dirs(root: Path, explicit: List[str] = None) -> List[Path]:
    if explicit:
        dirs = [root / a for a in explicit]  # keep user order
    else:
        dirs = sorted([p for p in root.iterdir() if p.is_dir()], key=lambda x: x.name.lower())
    good = []
    for d in dirs:
        if any(d.rglob("*.txt")) or any(d.rglob("exp_*_flow_max.csv")):
            good.append(d)
    return good

def find_txt_file(algo_dir: Path, preferred: str = None) -> Path:
    if preferred:
        p = algo_dir / preferred
        if p.exists():
            return p
    txts = sorted(algo_dir.rglob("*.txt"))
    if not txts:
        raise FileNotFoundError(f"No TXT file found under {algo_dir}")
    return txts[0]

def collect_flow_max_csvs(algo_dir: Path) -> Dict[int, Path]:
    mapping = {}
    for p in algo_dir.rglob("exp_*_flow_max.csv"):
        m = FLOW_MAX_PATTERN.search(p.name)
        if m:
            idx = int(m.group(1))
            mapping[idx] = p
    if not mapping:
        raise FileNotFoundError(f"No exp_*_flow_max.csv found under {algo_dir}")
    return mapping

def read_overall_max_from_flow_max_csv(csv_path: Path) -> int:
    maxv = 0
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        if rdr.fieldnames and "per_flow_max" in rdr.fieldnames:
            for row in rdr:
                try:
                    v = int(float(row["per_flow_max"]))
                    if v > maxv: maxv = v
                except Exception:
                    continue
        else:
            f.seek(0)
            r = csv.reader(f)
            for row in r:
                if not row: continue
                try:
                    v = int(float(row[-1]))
                    if v > maxv: maxv = v
                except Exception:
                    continue
    return maxv

def split_experiments(lines: List[str]) -> List[List[str]]:
    chunks, cur = [], []
    for ln in lines:
        if SEP_RE.match(ln.strip()):
            if cur:
                chunks.append(cur)
                cur = []
        else:
            cur.append(ln)
    if cur: chunks.append(cur)
    return chunks

def count_total_reorders_in_chunk(chunk_lines: List[str]) -> int:
    total = 0
    for line in chunk_lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = [p.strip() for p in s.split(",")]
        if len(parts) < 7:
            continue
        try:
            nxt = int(parts[5])  # col6
            got = int(parts[6])  # col7
        except Exception:
            continue
        if got > nxt:
            total += 1
    return total

# ---------- Label/color utilities ----------
def display_label_for_folder(name: str) -> str:
    n = name.strip().lower()
    if n == "dt": return "DT"
    if n == "abm": return "ABM"
    if n == "obm": return "OBM"
    if n == "lqd": return "LQD"
    return name  # fallback: show as-is

def make_color_picker(legend_labels: List[str]):
    cycle = plt.rcParams['axes.prop_cycle'].by_key().get('color', [])
    def pick(lbl: str) -> str:
        if lbl in ALGO_COLORS:
            return ALGO_COLORS[lbl]
        if cycle:
            return cycle[hash(lbl) % len(cycle)]
        return "#888888"
    return pick

# ---------- Main plotting logic ----------
def main():
    ap = argparse.ArgumentParser(description="Plot max reordering and total reorderings across algorithms/experiments.")
    ap.add_argument("--algos", nargs="+", help="Algorithm subfolder names (order = bar order). Defaults to all subfolders.")
    ap.add_argument("--loads", nargs="+", default=["0.3","0.6","0.9"], help="Load labels per experiment index order (exp_001, exp_002, ...).")
    ap.add_argument("--input-file", default=None, help="TXT filename inside each algo folder (if omitted, auto-pick first *.txt).")
    ap.add_argument("--out-dir", default="plots_reordering", help="Output folder for images and summary.csv")
    ap.add_argument("--dpi", type=int, default=400, help="DPI for saved PNGs (match FCT plots)")
    args = ap.parse_args()

    root = Path(".").resolve()
    out_dir = root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Discover algorithms (bar order = folder order; pass --algos 'DT ABM OBM LQD' to force)
    algo_dirs = discover_algo_dirs(root, args.algos)
    if not algo_dirs:
        raise SystemExit("No algorithm subfolders found (containing a TXT or exp_*_flow_max.csv).")
    algo_tags   = [d.name for d in algo_dirs]                       # underlying dir names
    legend_lbls = [display_label_for_folder(n) for n in algo_tags]  # shown in legend
    color_for_label = make_color_picker(legend_lbls)

    # Gather data per algorithm
    per_algo_overall_max: Dict[str, Dict[int,int]] = {}
    per_algo_total_reorders: Dict[str, Dict[int,int]] = {}
    all_exp_indices = set()

    for d in algo_dirs:
        algo_key = d.name  # use directory name as key
        # flow-max CSVs
        flow_csvs = collect_flow_max_csvs(d)
        per_algo_overall_max[algo_key] = {}
        for exp_idx, csv_path in flow_csvs.items():
            per_algo_overall_max[algo_key][exp_idx] = read_overall_max_from_flow_max_csv(csv_path)
            all_exp_indices.add(exp_idx)

        # TXT → total reorder counts
        txt_path = find_txt_file(d, preferred=args.input_file)
        with txt_path.open("r", encoding="utf-8") as f:
            chunks = split_experiments(f.readlines())
        totals = {}
        for i, chunk in enumerate(chunks, start=1):
            totals[i] = count_total_reorders_in_chunk(chunk)
            all_exp_indices.add(i)
        per_algo_total_reorders[algo_key] = totals

    exp_indices_sorted = sorted(all_exp_indices)
    load_labels = (args.loads + [""]*len(exp_indices_sorted))[:len(exp_indices_sorted)]

    # Build matrices (groups = experiments ordered; bars = algos in requested order)
    max_matrix: List[List[float]] = []
    tot_matrix: List[List[float]] = []
    for exp_idx in exp_indices_sorted:
        max_row, tot_row = [], []
        for algo_key in algo_tags:
            max_row.append(per_algo_overall_max.get(algo_key, {}).get(exp_idx, 0))
            tot_row.append(per_algo_total_reorders.get(algo_key, {}).get(exp_idx, 0))
        max_matrix.append(max_row)
        tot_matrix.append(tot_row)
    max_matrix = np.array(max_matrix, dtype=float)
    tot_matrix = np.array(tot_matrix, dtype=float)

    # Summary CSV (raw counts; unscaled)
    with (out_dir / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["load","algorithm","overall_max_per_flow","total_reorders"])
        for exp_idx, load in zip(exp_indices_sorted, load_labels):
            for algo_key, lbl in zip(algo_tags, legend_lbls):
                w.writerow([load, lbl,
                            per_algo_overall_max.get(algo_key, {}).get(exp_idx, 0),
                            per_algo_total_reorders.get(algo_key, {}).get(exp_idx, 0)])

    # ---------- Plotting (no titles) ----------
    def render(matrix, ylabel, filename, legend_fs=None):
        fig, ax = plt.subplots(figsize=(14.5, 12.5))
        grouped_bars(ax, load_labels, matrix, legend_lbls, color_for_label,
                     xlabel="Load", ylabel=ylabel)
        square_legend(ax, legend_lbls, fontsize=legend_fs)
        compact_even_ticks(ax, MAX_YTICKS, bottom=0)
        fig.tight_layout()
        fig.savefig(out_dir / filename, dpi=args.dpi, bbox_inches="tight")
        plt.close(fig)

    # Max consecutive packet reorders (smaller legend)
    render(
        max_matrix,
        ylabel="Max Consecutive Packet Reorders",
        filename="max_reordering_per_experiment.png",
        legend_fs=LEGEND_FONTSIZE - 8,
    )

    # Total packets reordered (in thousands)
    tot_matrix_k = tot_matrix / 1000.0
    render(
        tot_matrix_k,
        ylabel="Thousands of Packets Reordered",
        filename="total_reorders_per_experiment.png",
    )

    print(f"Saved plots and summary to: {out_dir}")
    print(f"- {out_dir/'max_reordering_per_experiment.png'}")
    print(f"- {out_dir/'total_reorders_per_experiment.png'}")
    print(f"- {out_dir/'summary.csv'}")

if __name__ == "__main__":
    main()
