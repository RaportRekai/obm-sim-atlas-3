# usage python merge_logs.py . _a merged_agg.csv 0.9
# usage python merge_logs.py . _t merged_agg.csv 0.9
#!/usr/bin/env python3
import os
import re
import sys
import pandas as pd

def main():

    parent = sys.argv[1]
    regex = sys.argv[2]
    output_csv = sys.argv[3]
    dir_list = sys.argv[4:]

    pattern = re.compile(regex)
    os.remove(output_csv)
    #breakpoint()
    print("removed csv files")
    selected_files = []
    for d in dir_list:
        subdir = os.path.join(parent, d)

        for name in os.listdir(subdir):
            if not name.endswith(".csv"):
                continue
            if pattern.search(name):  # use search so pattern like "_t..." matches anywhere in filename
                selected_files.append(os.path.join(subdir, name))
    dfs = []
    #os.remove(output_csv)
    for path in selected_files:
        dfs.append(pd.read_csv(path, delim_whitespace=True))

    merged = pd.concat(dfs, ignore_index=True)

    # write in the same whitespace-separated format as your switch logs
    merged.to_csv(output_csv, sep=" ", index=False)

    print(f"Merged {len(selected_files)} files into {output_csv}")
    # print(f"Rows: {len(merged)}")

if __name__ == "__main__":
    main()
