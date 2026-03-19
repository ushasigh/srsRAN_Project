#!/usr/bin/env python3
#python3 plotting/plot_mac_delays.py ../telemetry-runs/2026-03-18/run1/metrics_ping.json --output ping_metrics
"""
Plot EdgeRIC MAC delay metrics from JSON file
Creates MAC delay plots (CE, CRC, HARQ, SR delays)

Usage:
    python3 plot_mac_delays.py <metrics.json> [--output PREFIX]
    
Output plots:
    - {prefix}_mac_delays.png : MAC delays (CE, CRC, PUCCH HARQ, PUSCH HARQ, SR→PUSCH, Total)
"""

import json
import sys
import numpy as np
import matplotlib.pyplot as plt
from collections import defaultdict


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


def extract_delay_data(metrics):
    """Extract MAC delay time series data for all UEs"""
    ue_data = defaultdict(lambda: {
        'tti': [],
        'timestamp': [],
        'mac_delays': {
            'avg_ce_delay_ms': [],
            'avg_crc_delay_ms': [],
            'avg_pucch_harq_delay_ms': [],
            'avg_pusch_harq_delay_ms': [],
            'avg_sr_to_pusch_delay_ms': [],
            'avg_sum_mac_delay_ms': [],
        }
    })
    
    for record in metrics:
        tti = record.get('tti_index', 0)
        timestamp_us = record.get('timestamp_us', 0)
        timestamp_s = timestamp_us / 1e6
        
        for ue in record.get('ues', []):
            rnti = ue.get('rnti', 0)
            ue_data[rnti]['tti'].append(tti)
            ue_data[rnti]['timestamp'].append(timestamp_s)
            
            # MAC delays
            mac = ue.get('mac', {})
            ue_data[rnti]['mac_delays']['avg_ce_delay_ms'].append(mac.get('avg_ce_delay_ms', 0))
            ue_data[rnti]['mac_delays']['avg_crc_delay_ms'].append(mac.get('avg_crc_delay_ms', 0))
            ue_data[rnti]['mac_delays']['avg_pucch_harq_delay_ms'].append(mac.get('avg_pucch_harq_delay_ms', 0))
            ue_data[rnti]['mac_delays']['avg_pusch_harq_delay_ms'].append(mac.get('avg_pusch_harq_delay_ms', 0))
            ue_data[rnti]['mac_delays']['avg_sr_to_pusch_delay_ms'].append(mac.get('avg_sr_to_pusch_delay_ms', 0))
            ue_data[rnti]['mac_delays']['avg_sum_mac_delay_ms'].append(mac.get('avg_sum_mac_delay_ms', 0))
    
    return ue_data


def plot_mac_delays(ue_data, output_file=None):
    """Plot MAC delay metrics: CE, CRC, PUCCH HARQ, PUSCH HARQ, SR-to-PUSCH, Sum"""
    fig, axes = plt.subplots(3, 2, figsize=(16, 12))
    fig.suptitle('MAC Delay Metrics (All UEs)', fontsize=14, fontweight='bold')
    
    colors = plt.cm.tab10.colors
    
    delay_configs = [
        ('avg_ce_delay_ms', 'CE Delay', 'CE Delay (ms)'),
        ('avg_crc_delay_ms', 'CRC Delay', 'CRC Delay (ms)'),
        ('avg_pucch_harq_delay_ms', 'PUCCH HARQ Delay', 'PUCCH HARQ Delay (ms)'),
        ('avg_pusch_harq_delay_ms', 'PUSCH HARQ Delay', 'PUSCH HARQ Delay (ms)'),
        ('avg_sr_to_pusch_delay_ms', 'SR to PUSCH Delay', 'SR→PUSCH Delay (ms)'),
        ('avg_sum_mac_delay_ms', 'Total MAC Delay', 'Total MAC Delay (ms)'),
    ]
    
    for idx, (rnti, data) in enumerate(sorted(ue_data.items())):
        if len(data['timestamp']) == 0:
            continue
        
        color = colors[idx % len(colors)]
        label = f'UE RNTI {rnti}'
        timestamps = np.array(data['timestamp'])
        
        for i, (key, title, ylabel) in enumerate(delay_configs):
            ax = axes[i // 2, i % 2]
            delay_data = np.array(data['mac_delays'][key])
            ax.plot(timestamps, delay_data, color=color, label=label, linewidth=1.0, alpha=0.8)
    
    for i, (key, title, ylabel) in enumerate(delay_configs):
        ax = axes[i // 2, i % 2]
        ax.set_ylabel(ylabel, fontsize=11)
        ax.set_title(title, fontsize=12)
        ax.legend(loc='best', fontsize=8, ncol=2)
        ax.grid(True, alpha=0.3)
        ax.set_xlabel('Time (seconds)', fontsize=10)
    
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
        description='Plot EdgeRIC MAC delay metrics from JSON file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 plot_mac_delays.py metrics.json
  python3 plot_mac_delays.py metrics.json --output my_plots
        """
    )
    parser.add_argument('file', type=str, help='Path to JSON metrics file (JSONL format)')
    parser.add_argument('--output', '-o', type=str, default='metrics',
                       help='Output file prefix (default: metrics)')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.file):
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Reading metrics from: {args.file}")
    metrics = parse_jsonl(args.file)
    
    if len(metrics) == 0:
        print("Error: No metrics found in file!", file=sys.stderr)
        sys.exit(1)
    
    print(f"Parsed {len(metrics)} metric records")
    
    ue_data = extract_delay_data(metrics)
    print(f"Found {len(ue_data)} UEs")
    
    for rnti, data in sorted(ue_data.items()):
        print(f"  UE RNTI {rnti}: {len(data['timestamp'])} samples")
    
    input_dir = os.path.dirname(os.path.abspath(args.file)) or os.getcwd()
    prefix = args.output
    
    print(f"\nGenerating MAC delay plots...")
    
    delays_file = os.path.join(input_dir, f'{prefix}_mac_delays.png')
    plot_mac_delays(ue_data, output_file=delays_file)
    
    print("\nMAC delay plots generated successfully!")


if __name__ == '__main__':
    main()
