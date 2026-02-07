import sys
import os
import numpy as np
import plotly.graph_objects as go

# ==========================================
# CONFIGURATION
# ==========================================
ALGOS = ['credence', 'dt', 'abm', 'obm', 'occamy']
RUN = [1,1,1,7,3]
XLIM_START = 80
XLIM_END = 100
STEP = 0.2
# ==========================================

def next_token_value(tokens, key_with_colon):
    for i, t in enumerate(tokens[:-1]):
        if t == key_with_colon:
            return tokens[i+1].rstrip(',')
    return None

def read_data(wkld):
    """Reads logs for all algos and returns a dictionary of data"""
    data_store = {algo: {'short': [], 'long': []} for algo in ALGOS}
    
    for algo in ALGOS:
        path = f'net-sim-{algo}/prev_logs/all_logs/run_{RUN[ALGOS.index(algo)]}/recvd-flows-{wkld}.txt'
        
        if not os.path.exists(path):
            print(f"Warning: Log file not found for {algo} at {path}")
            continue
            
        print(f"Reading {algo} from {path}...")
        
        try:
            with open(path, 'r') as f:
                for line in f:
                    tokens = line.strip().split()
                    if not tokens: continue

                    flowsize_s = next_token_value(tokens, 'flowsize:')
                    fct_slots_s = next_token_value(tokens, 'fct:')
                    
                    if not flowsize_s or not fct_slots_s: continue

                    try:
                        flowsize = int(flowsize_s)
                        fct_us = round(int(fct_slots_s) * 0.12, 3) 
                        
                        if flowsize < 100:
                            data_store[algo]['short'].append(fct_us)
                        elif flowsize > 1000:
                            data_store[algo]['long'].append(fct_us)
                    except ValueError:
                        continue
        except Exception as e:
            print(f"Error reading {path}: {e}")
            
    return data_store

def plot_interactive(data_store, flow_type, wkld):
    """Generates an interactive HTML plot using Plotly"""
    fig = go.Figure()
    
    # Styles mapped to Plotly colors/dashes
    styles = {
        'credence': {'color': 'blue',   'dash': 'solid'},
        'dt':       {'color': 'red',    'dash': 'dash'},
        'abm':      {'color': 'green',  'dash': 'dashdot'},
        'obm':      {'color': 'orange', 'dash': 'dot'},
        'occamy':   {'color': 'purple', 'dash': 'dash'}
    }

    x_percentiles = np.arange(XLIM_START, XLIM_END + 0.05, STEP)
    x_percentiles = x_percentiles[x_percentiles <= 100]

    has_data = False
    
    for algo in ALGOS:
        fcts = data_store[algo][flow_type]
        if not fcts:
            continue
            
        has_data = True
        fcts.sort()
        y_values = np.percentile(fcts, x_percentiles)
        
        s = styles.get(algo, {'color': 'black', 'dash': 'solid'})
        
        # Add Trace
        fig.add_trace(go.Scatter(
            x=x_percentiles,
            y=y_values,
            mode='lines',
            name=algo.upper(),
            line=dict(color=s['color'], dash=s['dash'], width=2),
            hovertemplate=
            f"<b>{algo.upper()}</b><br>" +
            "Percentile: %{x:.1f}%<br>" +
            "FCT: %{y:.2f} us<extra></extra>"
        ))

    if not has_data:
        print(f"No valid data found for {flow_type} flows.")
        return

    # Layout Updates
    fig.update_layout(
        title=f'FCT Tail Distribution ({flow_type.capitalize()} flows, Load: {wkld})',
        xaxis_title='Percentile',
        yaxis_title='Flow Completion Time (us)',
        xaxis=dict(range=[XLIM_START, 100]),
        template='plotly_white',
        hovermode="x unified" # Shows all lines' values when hovering over one X point
    )

    out_file = f'interactive_fct_{flow_type}_{wkld}.html'
    fig.write_html(out_file)
    print(f"Interactive plot saved to: {out_file}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 plot_interactive.py <wkld_suffix>")
        sys.exit(1)
        
    wkld = sys.argv[1]
    data = read_data(wkld)
    
    plot_interactive(data, 'short', wkld)
    plot_interactive(data, 'long', wkld)

if __name__ == "__main__":
    main()