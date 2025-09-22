!/bin/bash

# cd net-sim-dt/
# echo python3 network.py 144-host-2-tier-fattree.json workloads/incast-trace-100G-degree-0.2.csv.processed 1000000
# python3 network.py 144-host-2-tier-fattree.json workloads/incast-trace-100G-degree-0.2.csv.processed 0.2 1000000
# cd ..
# echo workloads/incast-trace-100G-degree-0.2.csv.processed 0.2 > stats_dt.txt
# python3 stats.py dt 0.2
# python3 stats.py dt 0.2 >> stats_dt.txt

# # cd net-sim-dt/
# # echo python3 network.py 144-host-2-tier-fattree.json workloads/incast-trace-100G-degree-0.4.csv.processed 1000000
# # python3 network.py 144-host-2-tier-fattree.json workloads/incast-trace-100G-degree-0.4.csv.processed 0.4 1000000
# # cd ..
# echo workloads/incast-trace-100G-degree-0.4.csv.processed 0.4 >> stats_dt.txt
# python3 stats.py dt 0.4
# python3 stats.py dt 0.4 >> stats_dt.txt

# # cd net-sim-dt/
# # echo python3 network.py 144-host-2-tier-fattree.json workloads/incast-trace-100G-degree-0.6.csv.processed 1000000
# # python3 network.py 144-host-2-tier-fattree.json workloads/incast-trace-100G-degree-0.6.csv.processed 0.62 1000000
# # cd ..
# echo workloads/incast-trace-100G-degree-0.6.csv.processed 0.62 >> stats_dt.txt
# python3 stats.py dt 0.62
# python3 stats.py dt 0.62 >> stats_dt.txt

# # cd net-sim-dt/
# # echo python3 network.py 144-host-2-tier-fattree.json workloads/incast-trace-100G-degree-0.8.csv.processed 1000000
# # python3 network.py 144-host-2-tier-fattree.json workloads/incast-trace-100G-degree-0.8.csv.processed 0.8 1000000
# # cd ..
# echo workloads/incast-trace-100G-degree-0.8.csv.processed 0.8 >> stats_dt.txt
# python3 stats.py dt 0.8
# python3 stats.py dt 0.8 >> stats_dt.txt

cd net-sim-dt/
echo python3 network.py 144-host-2-tier-fattree.json workloads/websearch-trace-100G-load-0.3.csv.processed 1000000
python3 network.py 144-host-2-tier-fattree.json workloads/websearch-trace-100G-load-0.3.csv.processed 0.3 1000000
cd ..
echo workloads/websearch-trace-100G-load-0.3.csv.processed 0.3 >> stats_dt.txt
python3 stats.py dt 0.3
python3 stats.py dt 0.3 >> stats_dt.txt

cd net-sim-dt/
echo python3 network.py 144-host-2-tier-fattree.json workloads/websearch-trace-100G-load-0.6.csv.processed 1000000
python3 network.py 144-host-2-tier-fattree.json workloads/websearch-trace-100G-load-0.6.csv.processed 0.6 1000000
cd ..
echo workloads/websearch-trace-100G-load-0.6.csv.processed 0.6 >> stats_dt.txt
python3 stats.py dt 0.6
python3 stats.py dt 0.6 >> stats_dt.txt

cd net-sim-dt/
echo python3 network.py 144-host-2-tier-fattree.json workloads/websearch-trace-100G-load-0.9.csv.processed 1000000
python3 network.py 144-host-2-tier-fattree.json workloads/websearch-trace-100G-load-0.9.csv.processed 0.9 1000000
cd ..
echo workloads/websearch-trace-100G-load-0.9.csv.processed 0.9 >> stats_dt.txt
python3 stats.py dt 0.9
python3 stats.py dt 0.9 >> stats_dt.txt
