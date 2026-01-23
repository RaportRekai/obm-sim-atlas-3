#!/usr/bin/env python3
"""
reorder_burst_multi_store_min.py — Multiple experiments, two CSVs per experiment.

Input rows (CSV-like):
col1,col2,col3,col4,col5,col6,col7,...
- Flow ID = (col1, col2, col4, col5)
- next_expected = col6 (int)
- seq_received  = col7 (int)

Reordering event:
- seq_received > next_expected

Per experiment (separated by lines made only of '@'):
  A) exp_XXX_flow_max.csv
     Columns: flow_id_col1,flow_id_col2,flow_id_col4,flow_id_col5,per_flow_max
     (per_flow_max = max count of reorders sharing the same next_expected within that flow; 0 if none)

  B) exp_XXX_hist_desc.csv
     Columns: reorder_peak,flow_count
     (descending k from M..0, where M = max(per_flow_max) in the experiment)

Usage:
  python3 reorder_burst_multi_store_min.py data.txt
  python3 reorder_burst_multi_store_min.py data.txt --out-dir results
"""

import argparse
import os
import re
import csv
from collections import defaultdict, Counter

SEP_RE = re.compile(r"^@+$")  # line of only '@'s (any count)

def is_separator(line: str) -> bool:
    return SEP_RE.match(line.strip()) is not None

def parse_line(line, lineno, strict=False):
    """Return (flow_id, next_expected, seq_received), 'SEP' for separator, or None to skip."""
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    if is_separator(s):
        return "SEP"
    parts = [p.strip() for p in s.split(",")]
    if len(parts) < 7:
        if strict:
            raise ValueError(f"Line {lineno}: expected ≥7 fields, got {len(parts)}: {s}")
        return None
    try:
        flow_id = (parts[0], parts[1], parts[3], parts[4])  # (col1,col2,col4,col5)
        next_expected = int(parts[5])                       # col6
        seq_received  = int(parts[6])                       # col7
    except Exception as e:
        if strict:
            raise ValueError(f"Line {lineno}: parse error for col6/col7: {e}\n{s}")
        return None
    return flow_id, next_expected, seq_received

def analyze_experiment(lines_iterable, start_lineno=1, strict=False):
    """
    Consume lines for one experiment until a separator or EOF.
    Returns:
      consumed: number of lines consumed (incl. separator if present)
      result: {
        'per_flow_max': {flow_id: int},  # includes zeros
        'overall_max': int,              # max(per_flow_max.values())
        'total_flows': int
      }
    """
    counts = defaultdict(lambda: defaultdict(int))  # counts[flow][next_expected] = reorder hits
    seen_flows = set()
    consumed = 0

    for raw_line in lines_iterable:
        consumed += 1
        parsed = parse_line(raw_line, start_lineno + consumed - 1, strict=strict)
        if parsed == "SEP":
            break
        if parsed is None:
            continue
        fid, nxt, got = parsed
        seen_flows.add(fid)
        if got > nxt:
            counts[fid][nxt] += 1

    # Build per-flow max (include zeros for flows with no reorders)
    per_flow_max = {fid: 0 for fid in seen_flows}
    for fid, per_expected in counts.items():
        if per_expected:
            per_flow_max[fid] = max(per_expected.values())

    overall_max = max(per_flow_max.values()) if per_flow_max else 0

    return consumed, {
        "per_flow_max": per_flow_max,
        "overall_max": overall_max,
        "total_flows": len(seen_flows),
    }

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if header:
            w.writerow(header)
        w.writerows(rows)

def main():
    ap = argparse.ArgumentParser(description="Two-CSV per experiment reordering analysis.")
    ap.add_argument("file", help="Path to the input txt/CSV file")
    ap.add_argument("--out-dir", help="Output directory (default: <input>_analysis)")
    ap.add_argument("--strict", action="store_true", help="Fail on malformed lines instead of skipping")
    args = ap.parse_args()

    in_path = args.file
    base = os.path.splitext(os.path.basename(in_path))[0]
    out_dir = args.out_dir or f"{base}_analysis"
    ensure_dir(out_dir)

    with open(in_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    pos = 0
    exp_idx = 0

    while pos < len(lines):
        consumed, res = analyze_experiment(lines[pos:], start_lineno=pos + 1, strict=args.strict)
        pos += consumed if consumed > 0 else len(lines)

        if res["total_flows"] == 0:
            # skip empty chunks (e.g., consecutive separators)
            continue

        exp_idx += 1
        per_flow_max = res["per_flow_max"]
        overall_max = res["overall_max"]

        # ---- CSV 1: per-flow max ----
        flow_rows = []
        # Sort by descending per_flow_max, then by flow_id tuple for stable order
        for fid, m in sorted(per_flow_max.items(), key=lambda x: (-x[1], x[0])):
            c1, c2, c4, c5 = fid
            flow_rows.append([c1, c2, c4, c5, m])

        write_csv(
            os.path.join(out_dir, f"exp_{exp_idx:03d}_flow_max.csv"),
            ["flow_id_col1","flow_id_col2","flow_id_col4","flow_id_col5","per_flow_max"],
            flow_rows
        )

        # ---- CSV 2: histogram descending from M..0 ----
        hist_counts = Counter(per_flow_max.values())
        hist_rows = []
        for k in range(overall_max, -1, -1):
            hist_rows.append([k, hist_counts.get(k, 0)])

        write_csv(
            os.path.join(out_dir, f"exp_{exp_idx:03d}_hist_desc.csv"),
            ["reorder_peak","flow_count"],
            hist_rows
        )

    print(f"Saved analysis to: {out_dir}")

if __name__ == "__main__":
    main()
