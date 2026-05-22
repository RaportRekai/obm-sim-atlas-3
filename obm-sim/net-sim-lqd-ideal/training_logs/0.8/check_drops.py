#!/usr/bin/env python3
import re
from pathlib import Path

def parse_header(header_line: str):
    """
    Supports headers separated by whitespace and/or commas.
    Returns list of column names.
    """
    cols = re.split(r"[,\s]+", header_line.strip())
    cols = [c for c in cols if c]  # drop empties
    return cols

def iter_rows(file_path: Path, expected_cols: int):
    """
    Yields row token lists. Splits on commas or any whitespace.
    Skips blank lines.
    """
    with file_path.open("r", encoding="utf-8", errors="replace") as f:
        # skip header
        _ = f.readline()
        for line in f:
            line = line.strip()
            if not line:
                continue
            toks = re.split(r"[,\s]+", line)
            toks = [t for t in toks if t]

            # If a line is malformed, skip it (or you can raise)
            if expected_cols and len(toks) != expected_cols:
                # Allow trailing/leading formatting issues by padding/truncating
                if len(toks) < expected_cols:
                    toks = toks + [""] * (expected_cols - len(toks))
                else:
                    toks = toks[:expected_cols]
            yield toks

def file_has_drops(file_path: Path):
    """
    Returns (has_drop: bool, drop_count: int, total_rows: int).
    Expects a 'drop' column (case-insensitive).
    """
    with file_path.open("r", encoding="utf-8", errors="replace") as f:
        header = f.readline()
        if not header:
            return (False, 0, 0)

    cols = parse_header(header)
    if not cols:
        return (False, 0, 0)

    # Find 'drop' column index
    drop_idx = None
    for i, c in enumerate(cols):
        if c.strip().lower() == "drop":
            drop_idx = i
            break
    if drop_idx is None:
        # No drop column; treat as not applicable
        return (False, 0, 0)

    drop_count = 0
    total_rows = 0

    for toks in iter_rows(file_path, expected_cols=len(cols)):
        total_rows += 1
        val = toks[drop_idx].strip()

        # Accept "1", "1.0", etc.
        try:
            if int(float(val)) == 1:
                drop_count += 1
        except Exception:
            # If drop field is non-numeric/missing, ignore
            pass

    return (drop_count > 0, drop_count, total_rows)

def main():
    script_dir = Path(__file__).resolve().parent
    csv_files = sorted(script_dir.glob("*.csv"))

    if not csv_files:
        print(f"No .csv files found in: {script_dir}")
        return

    files_with_drops = []
    print(f"Scanning {len(csv_files)} CSV file(s) in: {script_dir}\n")

    for fp in csv_files:
        has_drop, drop_count, total_rows = file_has_drops(fp)
        if has_drop:
            files_with_drops.append((fp.name, drop_count, total_rows))

    if not files_with_drops:
        print("No files contain drop == 1.")
        return

    print("Files with drop == 1 (at least once):")
    for name, dcnt, rows in files_with_drops:
        print(f"  - {name}: {dcnt} dropped row(s) out of {rows} row(s)")

if __name__ == "__main__":
    main()
