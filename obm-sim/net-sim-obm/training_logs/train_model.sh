parent=/home/dan/LQD/obm-sim/obm-sim/net-sim-obm/training_logs
#directory_list=(0.2 0.4 0.62 0.8)
rm -rf $parent/*.joblib
directory_list=(0.3 0.6 0.9)
maxDepth=4
regex_agg='_a[^_]*\.csv$'
regex_tor='_t[^_]*\.csv$'
python3 merge_logs.py "$parent" "$regex_tor" "$parent/merged_tor.csv" "${directory_list[@]}"
python3 merge_logs.py "$parent" "$regex_agg" "$parent/merged_agg.csv" "${directory_list[@]}"
python3 train_model.py 4 "$parent/merged_tor.csv" 32
python3 train_model.py 4 "$parent/merged_agg.csv" 9
