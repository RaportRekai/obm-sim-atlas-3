#!/bin/bash

# 1. defined as proper Bash arrays
algo_run_no=(1 2 2 1 4 1)
algo=("credence" "dt" "abm" "obm" "occamy" "lqd")
# algo_run_no=(2 2)
# algo=("dt" "abm")
# NOTE: $wkld is used below but not defined. 
# Ensure you define it before running, e.g., wkld="tcp"
# wkld="tcp" 

for i in {0..5}
do
    # 2. Use double quotes for variable expansion
    # Access array elements using ${array[i]}
    
    # Websearch Workloads


    # wkld="0.3"
    # path="net-sim-${algo[$i]}/prev_logs/all_logs/run_${algo_run_no[$i]}/recvd-flows-${wkld}.txt"
    # echo "workloads/websearch-trace-100G-load-0.3.csv.processed" >> stats_${algo[$i]}.txt
    # python3 stats.py ${algo[$i]} 0.3 "$path"
    # # Added "$path" here, otherwise the script hangs waiting for input or fails
    # python3 stats.py ${algo[$i]} 0.3 "$path" >> stats_${algo[$i]}.txt

    # # Block 2: Load 0.6 (Note: you used 0.62 in the python arg, kept as is)
    # wkld="0.6"
    # path="net-sim-${algo[$i]}/prev_logs/all_logs/run_${algo_run_no[$i]}/recvd-flows-${wkld}.txt"
    # echo "workloads/websearch-trace-100G-load-0.6.csv.processed" >> stats_${algo[$i]}.txt
    # python3 stats.py ${algo[$i]} 0.6 "$path"
    # python3 stats.py ${algo[$i]} 0.6 "$path" >> stats_${algo[$i]}.txt

    # Block 3: Load 0.9
    wkld="0.9"
    path="net-sim-${algo[$i]}/prev_logs/all_logs/run_${algo_run_no[$i]}/recvd-flows-${wkld}.txt"
    echo "workloads/websearch-trace-100G-load-0.9.csv.processed" >> stats_${algo[$i]}.txt
    python3 stats.py ${algo[$i]} 0.9 "$path"
    python3 stats.py ${algo[$i]} 0.9 "$path" >> stats_${algo[$i]}.txt





    # Incast Workloads


    # Block 1: Load 0.2
    # wkld="0.2"
    # path="net-sim-${algo[$i]}/prev_logs/all_logs/run_${algo_run_no[$i]}/recvd-flows-${wkld}.txt"
    # echo "workloads/incast-trace-100G-load-0.2.csv.processed" >> stats_${algo[$i]}.txt
    # python3 stats.py ${algo[$i]} 0.2 "$path"
    # # Added "$path" here, otherwise the script hangs waiting for input or fails
    # python3 stats.py ${algo[$i]} 0.2 "$path" >> stats_${algo[$i]}.txt

    # # Block 2: Load 0.6 (Note: you used 0.62 in the python arg, kept as is)
    # wkld="0.62"
    # path="net-sim-${algo[$i]}/prev_logs/all_logs/run_${algo_run_no[$i]}/recvd-flows-${wkld}.txt"
    # echo "workloads/incast-trace-100G-load-0.6.csv.processed" >> stats_${algo[$i]}.txt
    # python3 stats.py ${algo[$i]} 0.62 "$path"
    # python3 stats.py ${algo[$i]} 0.62 "$path" >> stats_${algo[$i]}.txt

    # # Block 3: Load 0.4
    # wkld="0.4"
    # path="net-sim-${algo[$i]}/prev_logs/all_logs/run_${algo_run_no[$i]}/recvd-flows-${wkld}.txt"
    # echo "workloads/incast-trace-100G-load-0.4.csv.processed" >> stats_${algo[$i]}.txt
    # python3 stats.py ${algo[$i]} 0.4 "$path"
    # python3 stats.py ${algo[$i]} 0.4 "$path" >> stats_${algo[$i]}.txt

    # # Block 4: Load 0.8
    # wkld="0.8"
    # path="net-sim-${algo[$i]}/prev_logs/all_logs/run_${algo_run_no[$i]}/recvd-flows-${wkld}.txt"
    # echo "workloads/incast-trace-100G-load-0.8.csv.processed" >> stats_${algo[$i]}.txt
    # python3 stats.py ${algo[$i]} 0.8 "$path"
    # python3 stats.py ${algo[$i]} 0.8 "$path" >> stats_${algo[$i]}.txt

done