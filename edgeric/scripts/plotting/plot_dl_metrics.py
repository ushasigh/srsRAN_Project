#!/usr/bin/env python3
# python3 plotting/plot_mac_delays.py ../telemetry-runs/2026-03-18/run1/metrics_ping.json --output ping_metrics
"""
Plot EdgeRIC DL metrics from JSON file
Creates MAC DL, RLC DL, PDCP DL, and GTP DL plots

Usage:
    python3 plot_dl_metrics.py <metrics.json> [--output PREFIX]
    
Output plots:
    - {prefix}_mac_dl.png   : MAC DL (CQI, MCS, buffer, rate, HARQ OK/NOK)
    - {prefix}_rlc_dl.png   : RLC DL (latency, PDU, SDU)
    - {prefix}_pdcp_dl.png  : PDCP DL (latency, PDU)
    - {prefix}_gtp_dl.png   : GTP DL (packet count, bytes)
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


def extract_dl_data(metrics):
    """Extract DL time series data for all UEs"""
    ue_data = defaultdict(lambda: {
        'tti': [],
        'timestamp': [],
        'mac_dl': {
            'cqi': [],
            'mcs': [],
            'buffer': [],
            'tbs': [],
            'harq_ack': [],
            'harq_nack': [],
        },
        'rlc_dl': {
            'sdu_latency_us': [],
            'pdus': [],
            'pdu_bytes': [],
            'sdus': [],
            'sdu_bytes': [],
            'dropped_sdus': [],
            'retx_pdus': [],
        },
        'pdcp_dl': {
            'latency_ns': [],
            'pdus': [],
            'pdu_bytes': [],
            'dropped_sdus': [],
            'discard_timeouts': [],
        },
        'gtp_dl': {
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
            
            # MAC DL data
            mac = ue.get('mac', {})
            mac_dl = mac.get('dl', {})
            ue_data[rnti]['mac_dl']['cqi'].append(mac.get('cqi', 0))
            ue_data[rnti]['mac_dl']['mcs'].append(mac_dl.get('mcs', 0))
            ue_data[rnti]['mac_dl']['buffer'].append(mac_dl.get('buffer', 0))
            ue_data[rnti]['mac_dl']['tbs'].append(mac_dl.get('tbs', 0))
            ue_data[rnti]['mac_dl']['harq_ack'].append(mac_dl.get('harq_ack_tti', 0))
            ue_data[rnti]['mac_dl']['harq_nack'].append(mac_dl.get('harq_nack_tti', 0))
            
            # RLC DL data (from first DRB)
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
                ue_data[rnti]['rlc_dl']['dropped_sdus'].append(rlc_dl_data.get('dropped_sdus', 0))
                ue_data[rnti]['rlc_dl']['retx_pdus'].append(rlc_dl_data.get('retx_pdus', 0))
            else:
                ue_data[rnti]['rlc_dl']['sdu_latency_us'].append(0)
                ue_data[rnti]['rlc_dl']['pdus'].append(0)
                ue_data[rnti]['rlc_dl']['pdu_bytes'].append(0)
                ue_data[rnti]['rlc_dl']['sdus'].append(0)
                ue_data[rnti]['rlc_dl']['sdu_bytes'].append(0)
                ue_data[rnti]['rlc_dl']['dropped_sdus'].append(0)
                ue_data[rnti]['rlc_dl']['retx_pdus'].append(0)
            
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
                ue_data[rnti]['pdcp_dl']['dropped_sdus'].append(pdcp_dl_data.get('dropped_sdus', 0))
                ue_data[rnti]['pdcp_dl']['discard_timeouts'].append(pdcp_dl_data.get('discard_timeouts', 0))
            else:
                ue_data[rnti]['pdcp_dl']['latency_ns'].append(0)
                ue_data[rnti]['pdcp_dl']['pdus'].append(0)
                ue_data[rnti]['pdcp_dl']['pdu_bytes'].append(0)
                ue_data[rnti]['pdcp_dl']['dropped_sdus'].append(0)
                ue_data[rnti]['pdcp_dl']['discard_timeouts'].append(0)
            
            # GTP DL data
            gtp = ue.get('gtp', {})
            gtp_dl = gtp.get('dl', {})
            ue_data[rnti]['gtp_dl']['pkts'].append(gtp_dl.get('pkts', 0))
            ue_data[rnti]['gtp_dl']['bytes'].append(gtp_dl.get('bytes', 0))
    
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


def calculate_dl_rate_mbps(tbs_list):
    """Calculate DL rate in Mbps from TBS (bytes per TTI)"""
    return [tbs * 8 * 1000 / 1e6 for tbs in tbs_list]


def plot_mac_dl(ue_data, output_file=None):
    """Plot MAC DL metrics: CQI, MCS, Buffer, Rate, HARQ ACK, HARQ NACK"""
    fig, axes = plt.subplots(3, 2, figsize=(16, 12))
    fig.suptitle('MAC DL Metrics (All UEs)', fontsize=14, fontweight='bold')
    
    colors = plt.cm.tab10.colors
    
    for idx, (rnti, data) in enumerate(sorted(ue_data.items())):
        if len(data['timestamp']) == 0:
            continue
        
        color = colors[idx % len(colors)]
        label = f'UE RNTI {rnti}'
        timestamps = np.array(data['timestamp'])
        
        # CQI
        cqi = np.array(data['mac_dl']['cqi'])
        axes[0, 0].plot(timestamps, cqi, color=color, label=label, linewidth=1.0, alpha=0.8)
        
        # MCS
        mcs = np.array(data['mac_dl']['mcs'])
        axes[0, 1].plot(timestamps, mcs, color=color, label=label, linewidth=1.0, alpha=0.8)
        
        # Buffer
        buffer_mb = np.array(data['mac_dl']['buffer']) / (1024 * 1024)
        axes[1, 0].plot(timestamps, buffer_mb, color=color, label=label, linewidth=1.0, alpha=0.8)
        
        # Rate (500-sample running average)
        tbs = np.array(data['mac_dl']['tbs'])
        rate_mbps = calculate_dl_rate_mbps(tbs)
        rate_avg = calculate_running_average(rate_mbps, window=500)
        axes[1, 1].plot(timestamps, rate_avg, color=color, label=label, linewidth=1.0, alpha=0.8)
        
        # HARQ ACK (100ms aggregation)
        harq_ack = np.array(data['mac_dl']['harq_ack'])
        harq_ack_agg = calculate_running_sum(harq_ack, window=100)
        axes[2, 0].plot(timestamps, harq_ack_agg, color=color, label=label, linewidth=1.0, alpha=0.8)
        
        # HARQ NACK (100ms aggregation)
        harq_nack = np.array(data['mac_dl']['harq_nack'])
        harq_nack_agg = calculate_running_sum(harq_nack, window=100)
        axes[2, 1].plot(timestamps, harq_nack_agg, color=color, label=label, linewidth=1.0, alpha=0.8)
    
    # Configure axes
    axes[0, 0].set_ylabel('CQI', fontsize=11)
    axes[0, 0].set_title('Channel Quality Indicator (CQI)', fontsize=12)
    axes[0, 0].legend(loc='best', fontsize=8, ncol=2)
    axes[0, 0].grid(True, alpha=0.3)
    axes[0, 0].set_ylim(0, 16)
    
    axes[0, 1].set_ylabel('MCS', fontsize=11)
    axes[0, 1].set_title('Downlink MCS', fontsize=12)
    axes[0, 1].legend(loc='best', fontsize=8, ncol=2)
    axes[0, 1].grid(True, alpha=0.3)
    axes[0, 1].set_ylim(0, 29)
    
    axes[1, 0].set_ylabel('Buffer (MB)', fontsize=11)
    axes[1, 0].set_title('Downlink Buffer Size', fontsize=12)
    axes[1, 0].legend(loc='best', fontsize=8, ncol=2)
    axes[1, 0].grid(True, alpha=0.3)
    
    axes[1, 1].set_ylabel('Rate (Mbps)', fontsize=11)
    axes[1, 1].set_title('Downlink Rate (500-sample Avg)', fontsize=12)
    axes[1, 1].legend(loc='best', fontsize=8, ncol=2)
    axes[1, 1].grid(True, alpha=0.3)
    
    axes[2, 0].set_ylabel('Count (per 100ms)', fontsize=11)
    axes[2, 0].set_title('DL HARQ ACK (OK) - 100ms Agg', fontsize=12)
    axes[2, 0].legend(loc='best', fontsize=8, ncol=2)
    axes[2, 0].grid(True, alpha=0.3)
    axes[2, 0].set_xlabel('Time (seconds)', fontsize=10)
    
    axes[2, 1].set_ylabel('Count (per 100ms)', fontsize=11)
    axes[2, 1].set_title('DL HARQ NACK (NOK) - 100ms Agg', fontsize=12)
    axes[2, 1].legend(loc='best', fontsize=8, ncol=2)
    axes[2, 1].grid(True, alpha=0.3)
    axes[2, 1].set_xlabel('Time (seconds)', fontsize=10)
    
    plt.tight_layout()
    
    if output_file:
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"Saved: {output_file}")
    else:
        plt.show()


def plot_rlc_dl(ue_data, output_file=None):
    """Plot RLC DL metrics: queuing latency, PDU, SDU, drops/retx"""
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.suptitle('RLC DL Metrics (All UEs)', fontsize=14, fontweight='bold')
    
    colors = plt.cm.tab10.colors
    
    for idx, (rnti, data) in enumerate(sorted(ue_data.items())):
        if len(data['timestamp']) == 0:
            continue
        
        color = colors[idx % len(colors)]
        label = f'UE RNTI {rnti}'
        timestamps = np.array(data['timestamp'])
        
        # Queuing Latency
        latency_ms = np.array(data['rlc_dl']['sdu_latency_us']) / 1000.0
        axes[0, 0].plot(timestamps, latency_ms, color=color, label=label, linewidth=1.0, alpha=0.8)
        
        # PDU count
        pdu_count = np.array(data['rlc_dl']['pdus'])
        axes[0, 1].plot(timestamps, pdu_count, color=color, label=label, linewidth=1.0, alpha=0.8)
        
        # Dropped SDUs
        dropped_sdus = np.array(data['rlc_dl']['dropped_sdus'])
        axes[1, 0].plot(timestamps, dropped_sdus, color=color, label=label, linewidth=1.0, alpha=0.8)
        
        # Retx PDUs
        retx_pdus = np.array(data['rlc_dl']['retx_pdus'])
        axes[1, 1].plot(timestamps, retx_pdus, color=color, label=label, linewidth=1.0, alpha=0.8)
    
    axes[0, 0].set_ylabel('Queuing Latency (ms)', fontsize=11)
    axes[0, 0].set_title('RLC DL SDU Queuing Latency', fontsize=12)
    axes[0, 0].legend(loc='best', fontsize=8, ncol=2)
    axes[0, 0].grid(True, alpha=0.3)
    
    axes[0, 1].set_ylabel('PDU Count', fontsize=11)
    axes[0, 1].set_title('RLC DL PDU Count', fontsize=12)
    axes[0, 1].legend(loc='best', fontsize=8, ncol=2)
    axes[0, 1].grid(True, alpha=0.3)
    
    axes[1, 0].set_ylabel('Dropped SDUs', fontsize=11)
    axes[1, 0].set_title('RLC DL Dropped SDUs', fontsize=12)
    axes[1, 0].legend(loc='best', fontsize=8, ncol=2)
    axes[1, 0].grid(True, alpha=0.3)
    axes[1, 0].set_xlabel('Time (seconds)', fontsize=10)
    
    axes[1, 1].set_ylabel('Retx PDUs', fontsize=11)
    axes[1, 1].set_title('RLC DL Retransmitted PDUs', fontsize=12)
    axes[1, 1].legend(loc='best', fontsize=8, ncol=2)
    axes[1, 1].grid(True, alpha=0.3)
    axes[1, 1].set_xlabel('Time (seconds)', fontsize=10)
    
    plt.tight_layout()
    
    if output_file:
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"Saved: {output_file}")
    else:
        plt.show()


def plot_pdcp_dl(ue_data, output_file=None):
    """Plot PDCP DL metrics: latency, PDU, drops"""
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.suptitle('PDCP DL Metrics (All UEs)', fontsize=14, fontweight='bold')
    
    colors = plt.cm.tab10.colors
    
    for idx, (rnti, data) in enumerate(sorted(ue_data.items())):
        if len(data['timestamp']) == 0:
            continue
        
        color = colors[idx % len(colors)]
        label = f'UE RNTI {rnti}'
        timestamps = np.array(data['timestamp'])
        
        # Latency
        latency_ms = np.array(data['pdcp_dl']['latency_ns']) / 1e6
        axes[0, 0].plot(timestamps, latency_ms, color=color, label=label, linewidth=1.0, alpha=0.8)
        
        # PDU count
        pdu_count = np.array(data['pdcp_dl']['pdus'])
        axes[0, 1].plot(timestamps, pdu_count, color=color, label=label, linewidth=1.0, alpha=0.8)
        
        # Dropped SDUs
        dropped_sdus = np.array(data['pdcp_dl']['dropped_sdus'])
        axes[1, 0].plot(timestamps, dropped_sdus, color=color, label=label, linewidth=1.0, alpha=0.8)
        
        # Discard Timeouts
        discard_timeouts = np.array(data['pdcp_dl']['discard_timeouts'])
        axes[1, 1].plot(timestamps, discard_timeouts, color=color, label=label, linewidth=1.0, alpha=0.8)
    
    axes[0, 0].set_ylabel('PDU Latency (ms)', fontsize=11)
    axes[0, 0].set_title('PDCP DL PDU Latency', fontsize=12)
    axes[0, 0].legend(loc='best', fontsize=8, ncol=2)
    axes[0, 0].grid(True, alpha=0.3)
    
    axes[0, 1].set_ylabel('PDU Count', fontsize=11)
    axes[0, 1].set_title('PDCP DL PDU Count', fontsize=12)
    axes[0, 1].legend(loc='best', fontsize=8, ncol=2)
    axes[0, 1].grid(True, alpha=0.3)
    
    axes[1, 0].set_ylabel('Dropped SDUs', fontsize=11)
    axes[1, 0].set_title('PDCP DL Dropped SDUs', fontsize=12)
    axes[1, 0].legend(loc='best', fontsize=8, ncol=2)
    axes[1, 0].grid(True, alpha=0.3)
    axes[1, 0].set_xlabel('Time (seconds)', fontsize=10)
    
    axes[1, 1].set_ylabel('Discard Timeouts', fontsize=11)
    axes[1, 1].set_title('PDCP DL Discard Timeouts', fontsize=12)
    axes[1, 1].legend(loc='best', fontsize=8, ncol=2)
    axes[1, 1].grid(True, alpha=0.3)
    axes[1, 1].set_xlabel('Time (seconds)', fontsize=10)
    
    plt.tight_layout()
    
    if output_file:
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"Saved: {output_file}")
    else:
        plt.show()


def plot_gtp_dl(ue_data, output_file=None):
    """Plot GTP DL metrics: packet count and bytes"""
    fig, axes = plt.subplots(2, 1, figsize=(14, 8))
    fig.suptitle('GTP DL Metrics (All UEs)', fontsize=14, fontweight='bold')
    
    colors = plt.cm.tab10.colors
    
    for idx, (rnti, data) in enumerate(sorted(ue_data.items())):
        if len(data['timestamp']) == 0:
            continue
        
        color = colors[idx % len(colors)]
        label = f'UE RNTI {rnti}'
        timestamps = np.array(data['timestamp'])
        
        # Packet count
        pkts = np.array(data['gtp_dl']['pkts'])
        axes[0].plot(timestamps, pkts, color=color, label=label, linewidth=1.5, alpha=0.8)
        
        # Bytes
        gtp_bytes_kb = np.array(data['gtp_dl']['bytes']) / 1024.0
        axes[1].plot(timestamps, gtp_bytes_kb, color=color, label=label, linewidth=1.5, alpha=0.8)
    
    axes[0].set_ylabel('Packet Count', fontsize=11)
    axes[0].set_title('GTP DL Packet Count (Cumulative)', fontsize=12)
    axes[0].legend(loc='best', fontsize=8, ncol=2)
    axes[0].grid(True, alpha=0.3)
    axes[0].set_xlabel('Time (seconds)', fontsize=10)
    
    axes[1].set_ylabel('Bytes (KB)', fontsize=11)
    axes[1].set_title('GTP DL Bytes (Cumulative)', fontsize=12)
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
        description='Plot EdgeRIC DL metrics from JSON file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 plot_dl_metrics.py metrics.json
  python3 plot_dl_metrics.py metrics.json --output my_plots
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
    
    ue_data = extract_dl_data(metrics)
    print(f"Found {len(ue_data)} UEs")
    
    for rnti, data in sorted(ue_data.items()):
        print(f"  UE RNTI {rnti}: {len(data['timestamp'])} samples")
    
    input_dir = os.path.dirname(os.path.abspath(args.file)) or os.getcwd()
    prefix = args.output
    
    print(f"\nGenerating DL plots...")
    
    mac_file = os.path.join(input_dir, f'{prefix}_mac_dl.png')
    rlc_file = os.path.join(input_dir, f'{prefix}_rlc_dl.png')
    pdcp_file = os.path.join(input_dir, f'{prefix}_pdcp_dl.png')
    gtp_file = os.path.join(input_dir, f'{prefix}_gtp_dl.png')
    
    plot_mac_dl(ue_data, output_file=mac_file)
    plot_rlc_dl(ue_data, output_file=rlc_file)
    plot_pdcp_dl(ue_data, output_file=pdcp_file)
    plot_gtp_dl(ue_data, output_file=gtp_file)
    
    print("\nDL plots generated successfully!")


if __name__ == '__main__':
    main()
