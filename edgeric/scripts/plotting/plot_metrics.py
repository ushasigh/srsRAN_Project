#!/usr/bin/env python3
"""
Plot EdgeRIC metrics from JSON file
Creates RLC, PDCP, and MAC plots with all UEs

Usage:
    python3 plot_metrics.py <metrics.json> [--output PREFIX]
    
    Arguments:
        metrics.json    Path to JSONL metrics file
        --output, -o    Output file prefix (default: metrics_plot)
    
    Examples:
        sudo python3 plot_metrics.py telemetry-runs/03-04-2026-run6/metrics.json
        python3 plot_metrics.py metrics.json
        python3 plot_metrics.py metrics.json --output my_plots
        python3 plot_metrics.py /path/to/metrics.json -o results
"""

import json
import sys
import numpy as np
import matplotlib.pyplot as plt
from collections import defaultdict
from datetime import datetime

def parse_jsonl(filepath):
    """Parse JSONL file (one JSON object per line)"""
    metrics = []
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                metrics.append(obj)
            except json.JSONDecodeError as e:
                print(f"Warning: Failed to parse line: {e}", file=sys.stderr)
                continue
    return metrics

def extract_data(metrics):
    """Extract time series data for all UEs"""
    ue_data = defaultdict(lambda: {
        'tti': [],
        'timestamp': [],
        'rlc_dl': {
            'sdu_latency_us': [],
            'pdus': [],
            'pdu_bytes': [],
            'sdus': [],
            'sdu_bytes': [],
        },
        'pdcp_dl': {
            'latency_ns': [],
            'pdus': [],
            'pdu_bytes': [],
        },
        'mac': {
            'cqi': [],
            'dl_mcs': [],
            'dl_buffer': [],
            'dl_tbs': [],
        }
    })
    
    for record in metrics:
        tti = record.get('tti_index', 0)
        timestamp_us = record.get('timestamp_us', 0)
        timestamp_s = timestamp_us / 1e6
        
        for ue in record.get('ues', []):
            rnti = ue.get('rnti', 0)
            
            # MAC data
            mac = ue.get('mac', {})
            mac_dl = mac.get('dl', {})
            ue_data[rnti]['tti'].append(tti)
            ue_data[rnti]['timestamp'].append(timestamp_s)
            ue_data[rnti]['mac']['cqi'].append(mac.get('cqi', 0))
            ue_data[rnti]['mac']['dl_mcs'].append(mac_dl.get('mcs', 0))
            ue_data[rnti]['mac']['dl_buffer'].append(mac_dl.get('buffer', 0))
            ue_data[rnti]['mac']['dl_tbs'].append(mac_dl.get('tbs', 0))
            
            # RLC DL data (from first DRB, typically DRB 1)
            rlc_dl_data = None
            for drb in ue.get('drbs', []):
                rlc = drb.get('rlc', {})
                if rlc and 'dl' in rlc:
                    rlc_dl_data = rlc['dl']
                    break
            
            if rlc_dl_data:
                ue_data[rnti]['rlc_dl']['sdu_latency_us'].append(rlc_dl_data.get('sdu_latency_us', 0))
                ue_data[rnti]['rlc_dl']['pdus'].append(rlc_dl_data.get('pdus', 0))
                ue_data[rnti]['rlc_dl']['pdu_bytes'].append(rlc_dl_data.get('pdu_bytes', 0))
                ue_data[rnti]['rlc_dl']['sdus'].append(rlc_dl_data.get('sdus', 0))
                ue_data[rnti]['rlc_dl']['sdu_bytes'].append(rlc_dl_data.get('sdu_bytes', 0))
            else:
                # No RLC data for this TTI
                ue_data[rnti]['rlc_dl']['sdu_latency_us'].append(0)
                ue_data[rnti]['rlc_dl']['pdus'].append(0)
                ue_data[rnti]['rlc_dl']['pdu_bytes'].append(0)
                ue_data[rnti]['rlc_dl']['sdus'].append(0)
                ue_data[rnti]['rlc_dl']['sdu_bytes'].append(0)
            
            # PDCP DL data (from first DRB)
            pdcp_dl_data = None
            for drb in ue.get('drbs', []):
                pdcp = drb.get('pdcp', {})
                if pdcp and 'dl' in pdcp:
                    pdcp_dl_data = pdcp['dl']
                    break
            
            if pdcp_dl_data:
                ue_data[rnti]['pdcp_dl']['latency_ns'].append(pdcp_dl_data.get('latency_ns', 0))
                ue_data[rnti]['pdcp_dl']['pdus'].append(pdcp_dl_data.get('pdus', 0))
                ue_data[rnti]['pdcp_dl']['pdu_bytes'].append(pdcp_dl_data.get('pdu_bytes', 0))
            else:
                ue_data[rnti]['pdcp_dl']['latency_ns'].append(0)
                ue_data[rnti]['pdcp_dl']['pdus'].append(0)
                ue_data[rnti]['pdcp_dl']['pdu_bytes'].append(0)
    
    return ue_data

def calculate_running_average(data, window=500):
    """Calculate running average with specified window size"""
    if len(data) == 0:
        return []
    
    result = []
    for i in range(len(data)):
        start_idx = max(0, i - window + 1)
        window_data = data[start_idx:i+1]
        if len(window_data) > 0:
            result.append(np.mean(window_data))
        else:
            result.append(0)
    return result

def calculate_dl_rate_mbps(tbs_list):
    """Calculate DL rate in Mbps from TBS (bytes per TTI)
    1 TTI = 1ms, so bytes/TTI * 8 * 1000 = bps
    """
    return [tbs * 8 * 1000 / 1e6 for tbs in tbs_list]  # Convert to Mbps

def plot_rlc_dl(ue_data, output_file=None):
    """Plot RLC DL metrics: queuing latency, PDU, SDU"""
    fig, axes = plt.subplots(3, 1, figsize=(14, 10))
    fig.suptitle('RLC DL Metrics (All UEs)', fontsize=14, fontweight='bold')
    
    colors = plt.cm.tab10.colors
    
    for idx, (rnti, data) in enumerate(sorted(ue_data.items())):
        if len(data['timestamp']) == 0:
            continue
        
        color = colors[idx % len(colors)]
        label = f'UE RNTI {rnti}'
        timestamps = np.array(data['timestamp'])
        
        # Subplot 1: Queuing Latency (SDU latency)
        latency_ms = np.array(data['rlc_dl']['sdu_latency_us']) / 1000.0
        axes[0].plot(timestamps, latency_ms, color=color, label=label, linewidth=1.5, alpha=0.8)
        
        # Subplot 2: PDU (count and bytes)
        pdu_count = np.array(data['rlc_dl']['pdus'])
        pdu_bytes_mb = np.array(data['rlc_dl']['pdu_bytes']) / (1024 * 1024)
        axes[1].plot(timestamps, pdu_count, color=color, label=f'{label} (count)', linewidth=1.5, alpha=0.8, linestyle='-')
        axes[1].plot(timestamps, pdu_bytes_mb, color=color, label=f'{label} (MB)', linewidth=1.5, alpha=0.6, linestyle='--')
        
        # Subplot 3: SDU (count and bytes)
        sdu_count = np.array(data['rlc_dl']['sdus'])
        sdu_bytes_mb = np.array(data['rlc_dl']['sdu_bytes']) / (1024 * 1024)
        axes[2].plot(timestamps, sdu_count, color=color, label=f'{label} (count)', linewidth=1.5, alpha=0.8, linestyle='-')
        axes[2].plot(timestamps, sdu_bytes_mb, color=color, label=f'{label} (MB)', linewidth=1.5, alpha=0.6, linestyle='--')
    
    # Configure subplot 1: Queuing Latency
    axes[0].set_ylabel('Queuing Latency (ms)', fontsize=11)
    axes[0].set_title('RLC DL SDU Queuing Latency', fontsize=12)
    axes[0].legend(loc='best', fontsize=8, ncol=2)
    axes[0].grid(True, alpha=0.3)
    axes[0].set_xlabel('Time (seconds)', fontsize=10)
    
    # Configure subplot 2: PDU
    axes[1].set_ylabel('PDU Count / Bytes (MB)', fontsize=11)
    axes[1].set_title('RLC DL PDU (Count and Bytes)', fontsize=12)
    axes[1].legend(loc='best', fontsize=8, ncol=2)
    axes[1].grid(True, alpha=0.3)
    axes[1].set_xlabel('Time (seconds)', fontsize=10)
    
    # Configure subplot 3: SDU
    axes[2].set_ylabel('SDU Count / Bytes (MB)', fontsize=11)
    axes[2].set_title('RLC DL SDU (Count and Bytes)', fontsize=12)
    axes[2].legend(loc='best', fontsize=8, ncol=2)
    axes[2].grid(True, alpha=0.3)
    axes[2].set_xlabel('Time (seconds)', fontsize=10)
    
    plt.tight_layout()
    
    if output_file:
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"Saved: {output_file}")
    else:
        plt.show()

def plot_pdcp_dl(ue_data, output_file=None):
    """Plot PDCP DL metrics: latency and PDU"""
    fig, axes = plt.subplots(2, 1, figsize=(14, 8))
    fig.suptitle('PDCP DL Metrics (All UEs)', fontsize=14, fontweight='bold')
    
    colors = plt.cm.tab10.colors
    
    for idx, (rnti, data) in enumerate(sorted(ue_data.items())):
        if len(data['timestamp']) == 0:
            continue
        
        color = colors[idx % len(colors)]
        label = f'UE RNTI {rnti}'
        timestamps = np.array(data['timestamp'])
        
        # Subplot 1: Latency
        latency_ms = np.array(data['pdcp_dl']['latency_ns']) / 1e6
        axes[0].plot(timestamps, latency_ms, color=color, label=label, linewidth=1.5, alpha=0.8)
        
        # Subplot 2: PDU (count and bytes)
        pdu_count = np.array(data['pdcp_dl']['pdus'])
        pdu_bytes_mb = np.array(data['pdcp_dl']['pdu_bytes']) / (1024 * 1024)
        axes[1].plot(timestamps, pdu_count, color=color, label=f'{label} (count)', linewidth=1.5, alpha=0.8, linestyle='-')
        axes[1].plot(timestamps, pdu_bytes_mb, color=color, label=f'{label} (MB)', linewidth=1.5, alpha=0.6, linestyle='--')
    
    # Configure subplot 1: Latency
    axes[0].set_ylabel('PDU Latency (ms)', fontsize=11)
    axes[0].set_title('PDCP DL PDU Latency', fontsize=12)
    axes[0].legend(loc='best', fontsize=8, ncol=2)
    axes[0].grid(True, alpha=0.3)
    axes[0].set_xlabel('Time (seconds)', fontsize=10)
    
    # Configure subplot 2: PDU
    axes[1].set_ylabel('PDU Count / Bytes (MB)', fontsize=11)
    axes[1].set_title('PDCP DL PDU (Count and Bytes)', fontsize=12)
    axes[1].legend(loc='best', fontsize=8, ncol=2)
    axes[1].grid(True, alpha=0.3)
    axes[1].set_xlabel('Time (seconds)', fontsize=10)
    
    plt.tight_layout()
    
    if output_file:
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"Saved: {output_file}")
    else:
        plt.show()

def plot_mac(ue_data, output_file=None):
    """Plot MAC metrics: CQI, DL MCS, DL buffer, DL running average rate"""
    fig, axes = plt.subplots(4, 1, figsize=(14, 12))
    fig.suptitle('MAC DL Metrics (All UEs)', fontsize=14, fontweight='bold')
    
    colors = plt.cm.tab10.colors
    
    for idx, (rnti, data) in enumerate(sorted(ue_data.items())):
        if len(data['timestamp']) == 0:
            continue
        
        color = colors[idx % len(colors)]
        label = f'UE RNTI {rnti}'
        timestamps = np.array(data['timestamp'])
        
        # Subplot 1: CQI
        cqi = np.array(data['mac']['cqi'])
        axes[0].plot(timestamps, cqi, color=color, label=label, linewidth=1.5, alpha=0.8)
        
        # Subplot 2: DL MCS
        dl_mcs = np.array(data['mac']['dl_mcs'])
        axes[1].plot(timestamps, dl_mcs, color=color, label=label, linewidth=1.5, alpha=0.8)
        
        # Subplot 3: DL Buffer
        dl_buffer_mb = np.array(data['mac']['dl_buffer']) / (1024 * 1024)
        axes[2].plot(timestamps, dl_buffer_mb, color=color, label=label, linewidth=1.5, alpha=0.8)
        
        # Subplot 4: DL Running Average Rate (500 sample window)
        dl_tbs = np.array(data['mac']['dl_tbs'])
        dl_rate_mbps = calculate_dl_rate_mbps(dl_tbs)
        dl_rate_avg = calculate_running_average(dl_rate_mbps, window=500)
        axes[3].plot(timestamps, dl_rate_avg, color=color, label=label, linewidth=1.5, alpha=0.8)
    
    # Configure subplot 1: CQI
    axes[0].set_ylabel('CQI', fontsize=11)
    axes[0].set_title('Channel Quality Indicator (CQI)', fontsize=12)
    axes[0].legend(loc='best', fontsize=8, ncol=2)
    axes[0].grid(True, alpha=0.3)
    axes[0].set_ylim(0, 16)
    
    # Configure subplot 2: DL MCS
    axes[1].set_ylabel('DL MCS', fontsize=11)
    axes[1].set_title('Downlink Modulation and Coding Scheme', fontsize=12)
    axes[1].legend(loc='best', fontsize=8, ncol=2)
    axes[1].grid(True, alpha=0.3)
    axes[1].set_ylim(0, 29)
    
    # Configure subplot 3: DL Buffer
    axes[2].set_ylabel('DL Buffer (MB)', fontsize=11)
    axes[2].set_title('Downlink Buffer Size', fontsize=12)
    axes[2].legend(loc='best', fontsize=8, ncol=2)
    axes[2].grid(True, alpha=0.3)
    
    # Configure subplot 4: DL Running Average Rate
    axes[3].set_ylabel('DL Rate (Mbps)', fontsize=11)
    axes[3].set_title('Downlink Rate (500-sample Running Average)', fontsize=12)
    axes[3].legend(loc='best', fontsize=8, ncol=2)
    axes[3].grid(True, alpha=0.3)
    axes[3].set_xlabel('Time (seconds)', fontsize=10)
    
    plt.tight_layout()
    
    if output_file:
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"Saved: {output_file}")
    else:
        plt.show()

def main():
    import argparse
    import os
    
    parser = argparse.ArgumentParser(
        description='Plot EdgeRIC metrics from JSON file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 plot_metrics.py metrics.json
  python3 plot_metrics.py metrics.json --output my_plots
  python3 plot_metrics.py /path/to/metrics.json --output results
        """
    )
    parser.add_argument('file', type=str, help='Path to JSON metrics file (JSONL format)')
    parser.add_argument('--output', '-o', type=str, default='metrics_plot',
                       help='Output file prefix (default: metrics_plot)')
    
    args = parser.parse_args()
    
    json_file = args.file
    output_prefix = args.output
    
    # Check if file exists
    if not os.path.exists(json_file):
        print(f"Error: File not found: {json_file}", file=sys.stderr)
        sys.exit(1)
    
    if not os.path.isfile(json_file):
        print(f"Error: Not a file: {json_file}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Reading metrics from: {json_file}")
    try:
        metrics = parse_jsonl(json_file)
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        sys.exit(1)
    
    if len(metrics) == 0:
        print("Error: No metrics found in file!", file=sys.stderr)
        sys.exit(1)
    
    print(f"Parsed {len(metrics)} metric records")
    
    ue_data = extract_data(metrics)
    print(f"Found {len(ue_data)} UEs")
    
    for rnti, data in sorted(ue_data.items()):
        print(f"  UE RNTI {rnti}: {len(data['timestamp'])} samples")
    
    if not ue_data:
        print("No UE data found!")
        sys.exit(1)
    
    # Determine output directory (same as input file directory)
    input_dir = os.path.dirname(os.path.abspath(json_file))
    if not input_dir:
        input_dir = os.getcwd()
    
    # Generate plots
    print(f"\nGenerating plots with prefix: {output_prefix}...")
    print(f"Output directory: {input_dir}")
    
    rlc_file = os.path.join(input_dir, f'{output_prefix}_rlc_dl.png')
    pdcp_file = os.path.join(input_dir, f'{output_prefix}_pdcp_dl.png')
    mac_file = os.path.join(input_dir, f'{output_prefix}_mac.png')
    
    plot_rlc_dl(ue_data, output_file=rlc_file)
    plot_pdcp_dl(ue_data, output_file=pdcp_file)
    plot_mac(ue_data, output_file=mac_file)
    
    print("\nAll plots generated successfully!")
    print(f"  - {rlc_file}")
    print(f"  - {pdcp_file}")
    print(f"  - {mac_file}")

if __name__ == '__main__':
    main()
