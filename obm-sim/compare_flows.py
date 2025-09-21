#!/usr/bin/env python3
import re, sys, csv, math, pathlib
from collections import defaultdict

ABM_DEFAULT = "/home/dan/LQD/obm-sim/obm-sim/short_flow_completion_time_abm.txt"
OBM_DEFAULT = "/home/dan/LQD/obm-sim/obm-sim/short_flow_completion_time_obm.txt"

LINE_RE = re.compile(
    r"flow completion time for\s+(\('h\d+',\s*\d+,\s*\d+\))\s*=\s*([0-9]*\.?[0-9]+)",
    re.IGNORECASE
)

def parse_file(path):
    data = {}
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = LINE_RE.search(line)
            if m:
                key = re.sub(r"\s+", " ", m.group(1))  # normalize spaces in tuple
                val = float(m.group(2))
                data[key] = val  # last occurrence wins if duplicates
    return data

def main(abm_path, obm_path):
    abm = parse_file(abm_path)
    obm = parse_file(obm_path)

    keys = sorted(set(abm) | set(obm))
    better, worse, tie, missing = [], [], [], []

    rows = []
    for k in keys:
        a = abm.get(k)
        o = obm.get(k)
        if a is None or o is None:
            missing.append((k, a, o))
            rows.append([k, a, o, None, None, "missing_in_" + ("ABM" if a is None else "OBM")])
            continue

        delta = a - o                 # +ve => OBM faster
        pct = (delta / a * 100.0) if a != 0 else (math.inf if delta > 0 else -math.inf if delta < 0 else 0.0)
        status = "tie"
        if o < a: 
            status = "OBM better"
            better.append((k, a, o, delta, pct))
        elif o > a:
            status = "OBM worse"
            worse.append((k, a, o, delta, pct))
        else:
            tie.append((k, a, o, delta, pct))
        rows.append([k, a, o, delta, pct, status])

    # Summary
    print(f"Compared {len(keys)} flows.")
    print(f"  OBM better: {len(better)}")
    print(f"  OBM worse : {len(worse)}")
    print(f"  ties      : {len(tie)}")
    if missing:
        print(f"  missing   : {len(missing)} (present in only one file)")

    # Top 10 improvements and regressions by % (absolute)
    better_sorted = sorted(better, key=lambda x: x[4], reverse=True)[:10]
    worse_sorted  = sorted(worse,  key=lambda x: x[4])[:10]

    def show(label, lst):
        print(f"\nTop {label}:")
        if not lst:
            print("  (none)")
            return
        for k,a,o,d,p in lst:
            print(f"  {k}: ABM={a:.3f}, OBM={o:.3f} → Δ={d:.3f} ({p:.2f}% vs ABM)")

    show("10 OBM improvements", better_sorted)
    show("10 OBM regressions", worse_sorted)

    # Write full CSV
    out = pathlib.Path("fct_comparison.csv")
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["flow_id","ABM_FCT","OBM_FCT","Delta_ABM_minus_OBM","Pct_Improvement_vs_ABM","Status"])
        w.writerows(rows)
    print(f"\nWrote full comparison to {out.resolve()}")

if __name__ == "__main__":
    abm_path = sys.argv[1] if len(sys.argv) > 1 else ABM_DEFAULT
    obm_path = sys.argv[2] if len(sys.argv) > 2 else OBM_DEFAULT
    main(abm_path, obm_path)
