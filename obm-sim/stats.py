import sys
import numpy as np

# Usage: python script.py <algo> <wkld>
algo = sys.argv[1]
wkld = sys.argv[2]
#folder = sys.argv[3]
#path = f'net-sim-{algo}/prev_logs/{folder}/recvd-flows-{wkld}.txt'
path = f'net-sim-{algo}/logs/recvd-flows-{wkld}.txt'
# Helpers
def next_token_value(tokens, key_with_colon):
    # find "flowsize:", "fct:", "recvtput:" and return the very next token (comma stripped)
    for i, t in enumerate(tokens[:-1]):
        if t == key_with_colon:
            return tokens[i+1].rstrip(',')  # strip trailing comma if present
    return None

fct_short, fct_long = [], []
tput_short, tput_long = [], []

with open(path, 'r') as f:
    for line in f:
        tokens = line.strip().split()
        if not tokens:
            continue

        # Parse required fields robustly by key
        flowsize_s = next_token_value(tokens, 'flowsize:')
        fct_slots_s = next_token_value(tokens, 'fct:')
        recvtput_s = next_token_value(tokens, 'recvtput:')

        # Skip lines missing required fields
        if flowsize_s is None or fct_slots_s is None or recvtput_s is None:
            continue

        try:
            flowsize = int(flowsize_s)
            fct_us = round(int(fct_slots_s) * 0.12, 3)  # 120 ns per timeslot → microseconds
            recvtput_gbps = float(recvtput_s)          # 'Gbps' unit comes in the next token
        except ValueError:
            continue  # skip malformed lines

        if flowsize < 100:
            fct_short.append(fct_us)
            tput_short.append(recvtput_gbps)
        elif flowsize > 1000:
            fct_long.append(fct_us)
            tput_long.append(recvtput_gbps)

# ---- FCT stats (unchanged behavior) ----
def print_fct_stats(name, arr):
    arr = sorted(arr)
    avgfct = np.mean(arr) if arr else float('nan')
    p99fct = np.percentile(arr, 99) if arr else float('nan')
    p999fct = np.percentile(arr, 99.9) if arr else float('nan')
    sys.stdout.write(f"Average FCT {name} flows: {round(avgfct,3)}us\n")
    sys.stdout.write(f"p99 FCT {name} flows: {round(p99fct,3)}us\n")
    sys.stdout.write(f"p99.9 FCT {name} flows: {round(p999fct,3)}us\n")

print_fct_stats('short', fct_short)
print_fct_stats('long', fct_long)

# ---- Throughput stats (new) ----
def print_tput_stats(name, arr):
    n = len(arr)
    total = float(np.sum(arr)) if n else 0.0
    avg = float(np.mean(arr)) if n else float('nan')
    sys.stdout.write(f"Total recv throughput ({name}, n={n}): {round(total,3)} Gbps\n")
    sys.stdout.write(f"Average recv throughput ({name}): {round(avg,3)} Gbps\n")

print_tput_stats('short', tput_short)
print_tput_stats('long', tput_long)
