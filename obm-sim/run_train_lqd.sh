BASE_DIR="net-sim-lqd"

cd "$BASE_DIR"
rm -rf logs/*

mkdir -p '../net-sim-obm/training_logs/0.3'
rm -rf "../net-sim-obm/training_logs/0.3/*"
python3 network.py 144-host-2-tier-fattree.json "workloads/websearch-trace-100G-load-0.3.csv.processed" 0.3 100000
cd ..
echo workloads/websearch-trace-100G-load-0.3.csv.processed >> stats_obm.txt
python3 stats.py lqd 0.3
python3 stats.py lqd 0.3 >> stats_obm.txt

cd "$BASE_DIR"
mkdir -p '../net-sim-obm/training_logs/0.6'
rm -rf "../net-sim-obm/training_logs/0.6/*"
python3 network.py 144-host-2-tier-fattree.json "workloads/websearch-trace-100G-load-0.6.csv.processed" 0.6 100000
cd ..
echo workloads/websearch-trace-100G-load-0.6.csv.processed >> stats_obm.txt
python3 stats.py lqd 0.6
python3 stats.py lqd 0.6 >> stats_obm.txt

cd "$BASE_DIR"
mkdir -p '../net-sim-obm/training_logs/0.9'
rm -rf "../net-sim-obm/training_logs/0.9/*"
python3 network.py 144-host-2-tier-fattree.json "workloads/websearch-trace-100G-load-0.9.csv.processed" 0.9 100000
cd ..
echo workloads/websearch-trace-100G-load-0.9.csv.processed >> stats_obm.txt
python3 stats.py lqd 0.9
python3 stats.py lqd 0.9 >> stats_obm.txt
mv "$LOG_DIR/recvd-flows-0.9.txt" "$NEW_FOLDER/"
cp "$SWITCH_FILE" "$NEW_FOLDER/"