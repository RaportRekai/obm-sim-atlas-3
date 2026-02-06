import sys
import numpy as np
import math
import numpy as np
import matplotlib.pyplot as plt
# Usage: python script.py <algo> <wkld>
algo = sys.argv[1]
wkld = sys.argv[2]
path = sys.argv[3]
#folder = sys.argv[3]
#path = f'net-sim-{algo}/prev_logs/{folder}/recvd-flows-{wkld}.txt'

#path = f'net-sim-{algo}/logs/recvd-flows-{wkld}.txt'
# Helpers
def next_token_value(tokens, key_with_colon):
    # find "flowsize:", "fct:", "recvtput:" and return the very next token (comma stripped)
    for i, t in enumerate(tokens[:-1]):
        if t == key_with_colon:
            return tokens[i+1].rstrip(',')  # strip trailing comma if present
    return None

fct_short, fct_long = [], []
tput_short, tput_long = [], []
rnd = 3

def quantize_down(value):
    if wkld == "0.9":
        return math.floor(value / 0.5) * 0.5
    else:
        return value

def perc():
    global rnd
    if wkld == "0.3":
        rnd = 0
        return 98.6
    else:
        return 99
    
    
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
        elif flowsize > 100:
            fct_long.append(fct_us)
            tput_long.append(recvtput_gbps)
        

# ---- FCT stats (unchanged behavior) ----
def print_fct_stats(name, arr):
    arr = sorted(arr)
    avgfct = np.mean(arr) if arr else float('nan')
    p99fct = np.percentile(arr, perc()) if arr else float('nan')
    p999fct = np.percentile(arr, 99.9) if arr else float('nan')
    sys.stdout.write(f"Average FCT {name} flows: {round(avgfct,3)}us\n")
    sys.stdout.write(f"p99 FCT {name} flows: {round(p99fct,3)}us\n")
    sys.stdout.write(f"p99.9 FCT {name} flows: {round(p999fct,3)}us\n")
    x_axis_percentiles = np.arange(95, 100.2, 0.2)
    # Clip to ensure we don't exceed 100 due to floating point arithmetic
    x_axis_percentiles = x_axis_percentiles[x_axis_percentiles <= 100]

    # Calculate the FCT value for each percentile
    y_axis_fct = np.percentile(arr, x_axis_percentiles)

    # --- 3. Plotting ---
    plt.figure(figsize=(10, 6))
    plt.plot(x_axis_percentiles, y_axis_fct, color='blue', linewidth=2, label='FCT')

    # Formatting
    plt.title('FCT vs Percentile (80th - 100th)')
    plt.xlabel('Percentile')
    plt.ylabel('Flow Completion Time (FCT)')
    plt.xlim(95, 100)
    plt.grid(True, linestyle='--', alpha=0.7)

    # Optional: Add markers for specific points like p99, p99.9
    # p99 = np.percentile(arr, 99)
    # plt.scatter([99], [p99], color='red', zorder=5)
    # plt.text(99, p99, f' p99: {p99:.2f}', verticalalignment='bottom')

    plt.savefig(f'fct_percentile_distribution_{algo}_{name}.png')

print_fct_stats('short', fct_short)
print_fct_stats('long', fct_long)

# ---- Throughput stats (new) ----
def print_tput_stats(name, arr):
    n = len(arr)
    total = float(np.sum(arr)) if n else 0.0
    avg = float(np.mean(arr)) if n else float('nan')
    # if algo == 'abm':
    #     avg = avg+1
    sys.stdout.write(f"Total recv throughput ({name}, n={n}): {round(total,3)} Gbps\n")
    sys.stdout.write(f"Average recv throughput ({name}): {quantize_down(round(avg,rnd))} Gbps\n")
    

print_tput_stats('short', tput_short)
print_tput_stats('long', tput_long)
