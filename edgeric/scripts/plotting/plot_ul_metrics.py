#!/usr/bin/env python3
"""
Plot EdgeRIC UL metrics from JSON file
Creates MAC UL, RLC UL, PDCP UL, and GTP UL plots

Usage:
    python3 plot_ul_metrics.py <metrics.json> [--output PREFIX]
    
Output plots:
    - {prefix}_mac_ul.png   : MAC UL (MCS, buffer, rate, CRC OK/FAIL)
    - {prefix}_rlc_ul.png   : RLC UL (latency, PDU, SDU)
    - {prefix}_pdcp_ul.png  : PDCP UL (latency, PDU)
    - {prefix}_gtp_ul.png   : GTP UL (packet count, bytes)
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


def extract_ul_data(metrics):
    """Extract UL time series data for all UEs"""
    ue_data = defaultdict(lambda: {
        'tti': [],
        'timestamp': [],
        'mac_ul': {
            'mcs': [],
            'buffer': [],
            'tbs': [],
            'crc_ok': [],
            'crc_fail': [],
        },
        'rlc_ul': {
            'sdu_latency_us': [],
            'pdus': [],
            'pdu_bytes': [],
            'sdus': [],
            'sdu_bytes': [],
        },
        'pdcp_ul': {
            'latency_ns': [],
            'pdus': [],
            'pdu_bytes': [],
        },
        'gtp_ul': {
            'pkts': [],
            'bytes': [],
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
            
            # MAC UL data
            mac = ue.get('mac', {})
            mac_ul = mac.get('ul', {})
            ue_data[rnti]['mac_ul']['mcs'].append(mac_ul.get('mcs', 0))
            ue_data[rnti]['mac_ul']['buffer'].append(mac_ul.get('buffer', 0))
            ue_data[rnti]['mac_ul']['tbs'].append(mac_ul.get('tbs', 0))
            ue_data[rnti]['mac_ul']['crc_ok'].append(mac_ul.get('crc_ok_tti', 0))
            ue_data[rnti]['mac_ul']['crc_fail'].append(mac_ul.get('crc_fail_tti', 0))
            
            # RLC UL data (from first DRB)
            rlc_ul_data = None
            for drb in ue.get('drbs', []):
                rlc = drb.get('rlc', {})
                if rlc and 'ul' in rlc:
                    rlc_ul_data = rlc['ul']
                    break
            
            if rlc_ul_data:
                ue_data[rnti]['rlc_ul']['sdu_latency_us'].append(rlc_ul_data.get('sdu_latency_us', 0))
                ue_data[rnti]['rlc_ul']['pdus'].append(rlc_ul_data.get('pdus', 0))
                ue_data[rnti]['rlc_ul']['pdu_bytes'].append(rlc_ul_data.get('pdu_bytes', 0))
                ue_data[rnti]['rlc_ul']['sdus'].append(rlc_ul_data.get('sdus', 0))
                ue_data[rnti]['rlc_ul']['sdu_bytes'].append(rlc_ul_data.get('sdu_bytes', 0))
            else:
                ue_data[rnti]['rlc_ul']['sdu_latency_us'].append(0)
                ue_data[rnti]['rlc_ul']['pdus'].append(0)
                ue_data[rnti]['rlc_ul']['pdu_bytes'].append(0)
                ue_data[rnti]['rlc_ul']['sdus'].append(0)
                ue_data[rnti]['rlc_ul']['sdu_bytes'].append(0)
            
            # PDCP UL data (from first DRB)
            pdcp_ul_data = None
            for drb in ue.get('drbs', []):
                pdcp = drb.get('pdcp', {})
                if pdcp and 'ul' in pdcp:
                    pdcp_ul_data = pdcp['ul']
                    break
            
            if pdcp_ul_data:
                ue_data[rnti]['pdcp_ul']['latency_ns'].append(pdcp_ul_data.get('latency_ns', 0))
                ue_data[rnti]['pdcp_ul']['pdus'].append(pdcp_ul_data.get('pdus', 0))
                ue_data[rnti]['pdcp_ul']['pdu_bytes'].append(pdcp_ul_data.get('pdu_bytes', 0))
            else:
                ue_data[rnti]['pdcp_ul']['latency_ns'].append(0)
                ue_data[rnti]['pdcp_ul']['pdus'].append(0)
                ue_data[rnti]['pdcp_ul']['pdu_bytes'].append(0)
            
            # GTP UL data
            gtp = ue.get('gtp', {})
            gtp_ul = gtp.get('ul', {})
            ue_data[rnti]['gtp_ul']['pkts'].append(gtp_ul.get('pkts', 0))
            ue_data[rnti]['gtp_ul']['bytes'].append(gtp_ul.get('bytes', 0))
    
    return ue_data


def calculate_running_average(data, window=500):
    """Calculate running average with specified window size"""
    if len(data) == 0:
        return []
    result = []
    for i in range(len(data)):
        start_idx = max(0, i - window + 1)
        window_data = data[start_idx:i+1]
        result.append(np.mean(window_data) if len(window_data) > 0 else 0)
    return result


def calculate_running_sum(data, window=100):
    """Calculate running sum with specified window size (e.g., 100ms aggregation)"""
    if len(data) == 0:
        return []
    result = []
    for i in range(len(data)):
        start_idx = max(0, i - window + 1)
        window_data = data[start_idx:i+1]
        result.append(np.sum(window_data))
    return result


def calculate_ul_rate_mbps(tbs_list):
    """Calculate UL rate in Mbps from TBS (bytes per TTI)"""
    return [tbs * 8 * 1000 / 1e6 for tbs in tbs_list]


def plot_mac_ul(ue_data, output_file=None):
    """Plot MAC UL metrics: MCS, Buffer, Rate, CRC OK, CRC FAIL"""
    fig, axes = plt.subplots(3, 2, figsize=(16, 12))
    fig.suptitle('MAC UL Metrics (All UEs)', fontsize=14, fontweight='bold')
    
    colors = plt.cm.tab10.colors
    
    for idx, (rnti, data) in enumerate(sorted(ue_data.items())):
        if len(data['timestamp']) == 0:
            continue
        
        color = colors[idx % len(colors)]
        label = f'UE RNTI {rnti}'
        timestamps = np.array(data['timestamp'])
        
        # MCS
        mcs = np.array(data['mac_ul']['mcs'])
        axes[0, 0].plot(timestamps, mcs, color=color, label=label, linewidth=1.0, alpha=0.8)
        
        # Buffer
        buffer_mb = np.array(data['mac_ul']['buffer']) / (1024 * 1024)
        axes[0, 1].plot(timestamps, buffer_mb, color=color, label=label, linewidth=1.0, alpha=0.8)
        
        # Rate (500-sample running average)
        tbs = np.array(data['mac_ul']['tbs'])
        rate_mbps = calculate_ul_rate_mbps(tbs)
        rate_avg = calculate_running_average(rate_mbps, window=500)
        axes[1, 0].plot(timestamps, rate_avg, color=color, label=label, linewidth=1.0, alpha=0.8)
        
        # CRC OK (100ms aggregation)
        crc_ok = np.array(data['mac_ul']['crc_ok'])
        crc_ok_agg = calculate_running_sum(crc_ok, window=100)
        axes[1, 1].plot(timestamps, crc_ok_agg, color=color, label=label, linewidth=1.0, alpha=0.8)
        
        # CRC FAIL (100ms aggregation)
        crc_fail = np.array(data['mac_ul']['crc_fail'])
        crc_fail_agg = calculate_running_sum(crc_fail, window=100)
        axes[2, 0].plot(timestamps, crc_fail_agg, color=color, label=label, linewidth=1.0, alpha=0.8)
    
    # Hide unused subplot
    axes[2, 1].axis('off')
    
    # Configure axes
    axes[0, 0].set_ylabel('MCS', fontsize=11)
    axes[0, 0].set_title('Uplink MCS', fontsize=12)
    axes[0, 0].legend(loc='best', fontsize=8, ncol=2)
    axes[0, 0].grid(True, alpha=0.3)
    axes[0, 0].set_ylim(0, 29)
    
    axes[0, 1].set_ylabel('Buffer (MB)', fontsize=11)
    axes[0, 1].set_title('Uplink Buffer Size', fontsize=12)
    axes[0, 1].legend(loc='best', fontsize=8, ncol=2)
    axes[0, 1].grid(True, alpha=0.3)
    
    axes[1, 0].set_ylabel('Rate (Mbps)', fontsize=11)
    axes[1, 0].set_title('Uplink Rate (500-sample Avg)', fontsize=12)
    axes[1, 0].legend(loc='best', fontsize=8, ncol=2)
    axes[1, 0].grid(True, alpha=0.3)
    
    axes[1, 1].set_ylabel('Count (per 100ms)', fontsize=11)
    axes[1, 1].set_title('UL CRC OK - 100ms Agg', fontsize=12)
    axes[1, 1].legend(loc='best', fontsize=8, ncol=2)
    axes[1, 1].grid(True, alpha=0.3)
    
    axes[2, 0].set_ylabel('Count (per 100ms)', fontsize=11)
    axes[2, 0].set_title('UL CRC FAIL - 100ms Agg', fontsize=12)
    axes[2, 0].legend(loc='best', fontsize=8, ncol=2)
    axes[2, 0].grid(True, alpha=0.3)
    axes[2, 0].set_xlabel('Time (seconds)', fontsize=10)
    
    plt.tight_layout()
    
    if output_file:
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"Saved: {output_file}")
    else:
        plt.show()


def plot_rlc_ul(ue_data, output_file=None):
    """Plot RLC UL metrics: latency, PDU, SDU"""
    fig, axes = plt.subplots(3, 1, figsize=(14, 10))
    fig.suptitle('RLC UL Metrics (All UEs)', fontsize=14, fontweight='bold')
    
    colors = plt.cm.tab10.colors
    
    for idx, (rnti, data) in enumerate(sorted(ue_data.items())):
        if len(data['timestamp']) == 0:
            continue
        
        color = colors[idx % len(colors)]
        label = f'UE RNTI {rnti}'
        timestamps = np.array(data['timestamp'])
        
        # Latency
        latency_ms = np.array(data['rlc_ul']['sdu_latency_us']) / 1000.0
        axes[0].plot(timestamps, latency_ms, color=color, label=label, linewidth=1.5, alpha=0.8)
        
        # PDU
        pdu_count = np.array(data['rlc_ul']['pdus'])
        pdu_bytes_mb = np.array(data['rlc_ul']['pdu_bytes']) / (1024 * 1024)
        axes[1].plot(timestamps, pdu_count, color=color, label=f'{label} (count)', linewidth=1.5, alpha=0.8, linestyle='-')
        axes[1].plot(timestamps, pdu_bytes_mb, color=color, label=f'{label} (MB)', linewidth=1.5, alpha=0.6, linestyle='--')
        
        # SDU
        sdu_count = np.array(data['rlc_ul']['sdus'])
        sdu_bytes_mb = np.array(data['rlc_ul']['sdu_bytes']) / (1024 * 1024)
        axes[2].plot(timestamps, sdu_count, color=color, label=f'{label} (count)', linewidth=1.5, alpha=0.8, linestyle='-')
        axes[2].plot(timestamps, sdu_bytes_mb, color=color, label=f'{label} (MB)', linewidth=1.5, alpha=0.6, linestyle='--')
    
    axes[0].set_ylabel('SDU Latency (ms)', fontsize=11)
    axes[0].set_title('RLC UL SDU Latency', fontsize=12)
    axes[0].legend(loc='best', fontsize=8, ncol=2)
    axes[0].grid(True, alpha=0.3)
    axes[0].set_xlabel('Time (seconds)', fontsize=10)
    
    axes[1].set_ylabel('PDU Count / Bytes (MB)', fontsize=11)
    axes[1].set_title('RLC UL PDU (Count and Bytes)', fontsize=12)
    axes[1].legend(loc='best', fontsize=8, ncol=2)
    axes[1].grid(True, alpha=0.3)
    axes[1].set_xlabel('Time (seconds)', fontsize=10)
    
    axes[2].set_ylabel('SDU Count / Bytes (MB)', fontsize=11)
    axes[2].set_title('RLC UL SDU (Count and Bytes)', fontsize=12)
    axes[2].legend(loc='best', fontsize=8, ncol=2)
    axes[2].grid(True, alpha=0.3)
    axes[2].set_xlabel('Time (seconds)', fontsize=10)
    
    plt.tight_layout()
    
    if output_file:
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"Saved: {output_file}")
    else:
        plt.show()


def plot_pdcp_ul(ue_data, output_file=None):
    """Plot PDCP UL metrics: latency and PDU"""
    fig, axes = plt.subplots(2, 1, figsize=(14, 8))
    fig.suptitle('PDCP UL Metrics (All UEs)', fontsize=14, fontweight='bold')
    
    colors = plt.cm.tab10.colors
    
    for idx, (rnti, data) in enumerate(sorted(ue_data.items())):
        if len(data['timestamp']) == 0:
            continue
        
        color = colors[idx % len(colors)]
        label = f'UE RNTI {rnti}'
        timestamps = np.array(data['timestamp'])
        
        # Latency
        latency_ms = np.array(data['pdcp_ul']['latency_ns']) / 1e6
        axes[0].plot(timestamps, latency_ms, color=color, label=label, linewidth=1.5, alpha=0.8)
        
        # PDU
        pdu_count = np.array(data['pdcp_ul']['pdus'])
        pdu_bytes_mb = np.array(data['pdcp_ul']['pdu_bytes']) / (1024 * 1024)
        axes[1].plot(timestamps, pdu_count, color=color, label=f'{label} (count)', linewidth=1.5, alpha=0.8, linestyle='-')
        axes[1].plot(timestamps, pdu_bytes_mb, color=color, label=f'{label} (MB)', linewidth=1.5, alpha=0.6, linestyle='--')
    
    axes[0].set_ylabel('PDU Latency (ms)', fontsize=11)
    axes[0].set_title('PDCP UL PDU Latency', fontsize=12)
    axes[0].legend(loc='best', fontsize=8, ncol=2)
    axes[0].grid(True, alpha=0.3)
    axes[0].set_xlabel('Time (seconds)', fontsize=10)
    
    axes[1].set_ylabel('PDU Count / Bytes (MB)', fontsize=11)
    axes[1].set_title('PDCP UL PDU (Count and Bytes)', fontsize=12)
    axes[1].legend(loc='best', fontsize=8, ncol=2)
    axes[1].grid(True, alpha=0.3)
    axes[1].set_xlabel('Time (seconds)', fontsize=10)
    
    plt.tight_layout()
    
    if output_file:
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"Saved: {output_file}")
    else:
        plt.show()


def plot_gtp_ul(ue_data, output_file=None):
    """Plot GTP UL metrics: packet count and bytes"""
    fig, axes = plt.subplots(2, 1, figsize=(14, 8))
    fig.suptitle('GTP UL Metrics (All UEs)', fontsize=14, fontweight='bold')
    
    colors = plt.cm.tab10.colors
    
    for idx, (rnti, data) in enumerate(sorted(ue_data.items())):
        if len(data['timestamp']) == 0:
            continue
        
        color = colors[idx % len(colors)]
        label = f'UE RNTI {rnti}'
        timestamps = np.array(data['timestamp'])
        
        # Packet count
        pkts = np.array(data['gtp_ul']['pkts'])
        axes[0].plot(timestamps, pkts, color=color, label=label, linewidth=1.5, alpha=0.8)
        
        # Bytes
        gtp_bytes_kb = np.array(data['gtp_ul']['bytes']) / 1024.0
        axes[1].plot(timestamps, gtp_bytes_kb, color=color, label=label, linewidth=1.5, alpha=0.8)
    
    axes[0].set_ylabel('Packet Count', fontsize=11)
    axes[0].set_title('GTP UL Packet Count (Cumulative)', fontsize=12)
    axes[0].legend(loc='best', fontsize=8, ncol=2)
    axes[0].grid(True, alpha=0.3)
    axes[0].set_xlabel('Time (seconds)', fontsize=10)
    
    axes[1].set_ylabel('Bytes (KB)', fontsize=11)
    axes[1].set_title('GTP UL Bytes (Cumulative)', fontsize=12)
    axes[1].legend(loc='best', fontsize=8, ncol=2)
    axes[1].grid(True, alpha=0.3)
    axes[1].set_xlabel('Time (seconds)', fontsize=10)
    
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
        description='Plot EdgeRIC UL metrics from JSON file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 plot_ul_metrics.py metrics.json
  python3 plot_ul_metrics.py metrics.json --output my_plots
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
    
    ue_data = extract_ul_data(metrics)
    print(f"Found {len(ue_data)} UEs")
    
    for rnti, data in sorted(ue_data.items()):
        print(f"  UE RNTI {rnti}: {len(data['timestamp'])} samples")
    
    input_dir = os.path.dirname(os.path.abspath(args.file)) or os.getcwd()
    prefix = args.output
    
    print(f"\nGenerating UL plots...")
    
    mac_file = os.path.join(input_dir, f'{prefix}_mac_ul.png')
    rlc_file = os.path.join(input_dir, f'{prefix}_rlc_ul.png')
    pdcp_file = os.path.join(input_dir, f'{prefix}_pdcp_ul.png')
    gtp_file = os.path.join(input_dir, f'{prefix}_gtp_ul.png')
    
    plot_mac_ul(ue_data, output_file=mac_file)
    plot_rlc_ul(ue_data, output_file=rlc_file)
    plot_pdcp_ul(ue_data, output_file=pdcp_file)
    plot_gtp_ul(ue_data, output_file=gtp_file)
    
    print("\nUL plots generated successfully!")


if __name__ == '__main__':
    main()
