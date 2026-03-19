#!/usr/bin/env python3
"""
Extract and plot TCP metrics from pcap file using tshark
Plots: RTT, Throughput, Retransmissions

Usage:
    python3 plot_tcp_pcap.py <capture.pcap> [--output PREFIX]

Requirements:
    - tshark (Wireshark CLI) installed
    - numpy, matplotlib
"""

import subprocess
import sys
import os
import numpy as np
import matplotlib.pyplot as plt
from collections import defaultdict


def run_tshark(pcap_file, fields, display_filter=None):
    """Run tshark and return output lines"""
    cmd = ['tshark', '-r', pcap_file, '-T', 'fields']
    
    for field in fields:
        cmd.extend(['-e', field])
    
    if display_filter:
        cmd.extend(['-Y', display_filter])
    
    cmd.append('-E')
    cmd.append('separator=,')
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"tshark error: {result.stderr}", file=sys.stderr)
        return []
    
    return [line for line in result.stdout.strip().split('\n') if line]


def extract_tcp_rtt(pcap_file):
    """Extract TCP RTT measurements"""
    fields = ['frame.time_relative', 'tcp.analysis.ack_rtt']
    lines = run_tshark(pcap_file, fields, 'tcp.analysis.ack_rtt')
    
    times = []
    rtts = []
    
    for line in lines:
        parts = line.split(',')
        if len(parts) >= 2 and parts[0] and parts[1]:
            try:
                time = float(parts[0])
                rtt = float(parts[1]) * 1000  # Convert to ms
                times.append(time)
                rtts.append(rtt)
            except ValueError:
                continue
    
    return np.array(times), np.array(rtts)


def extract_throughput(pcap_file, interval=0.5):
    """Extract throughput over time intervals"""
    fields = ['frame.time_relative', 'tcp.len']
    lines = run_tshark(pcap_file, fields, 'tcp.len > 0')
    
    if not lines:
        return np.array([]), np.array([])
    
    # Collect bytes per time
    data = []
    for line in lines:
        parts = line.split(',')
        if len(parts) >= 2 and parts[0] and parts[1]:
            try:
                time = float(parts[0])
                tcp_len = int(parts[1])
                data.append((time, tcp_len))
            except ValueError:
                continue
    
    if not data:
        return np.array([]), np.array([])
    
    # Bin into intervals
    max_time = max(t for t, _ in data)
    bins = int(max_time / interval) + 1
    
    bytes_per_bin = defaultdict(int)
    for time, tcp_len in data:
        bin_idx = int(time / interval)
        bytes_per_bin[bin_idx] += tcp_len
    
    times = []
    throughputs = []
    
    for i in range(bins):
        times.append(i * interval)
        bytes_in_interval = bytes_per_bin.get(i, 0)
        throughput_mbps = (bytes_in_interval * 8) / (interval * 1e6)
        throughputs.append(throughput_mbps)
    
    return np.array(times), np.array(throughputs)


def extract_retransmissions(pcap_file, interval=0.5):
    """Extract TCP retransmissions over time"""
    fields = ['frame.time_relative']
    lines = run_tshark(pcap_file, fields, 'tcp.analysis.retransmission')
    
    if not lines:
        # Try alternative filter
        lines = run_tshark(pcap_file, fields, 'tcp.analysis.fast_retransmission or tcp.analysis.retransmission')
    
    retrans_times = []
    for line in lines:
        if line:
            try:
                retrans_times.append(float(line))
            except ValueError:
                continue
    
    if not retrans_times:
        return np.array([]), np.array([])
    
    # Bin into intervals
    max_time = max(retrans_times)
    bins = int(max_time / interval) + 1
    
    counts_per_bin = defaultdict(int)
    for t in retrans_times:
        bin_idx = int(t / interval)
        counts_per_bin[bin_idx] += 1
    
    times = []
    counts = []
    
    for i in range(bins):
        times.append(i * interval)
        counts.append(counts_per_bin.get(i, 0))
    
    return np.array(times), np.array(counts)


def plot_tcp_metrics(rtt_data, throughput_data, retrans_data, output_file=None):
    """Plot TCP RTT, Throughput, and Retransmissions"""
    fig, axes = plt.subplots(3, 1, figsize=(12, 10))
    
    rtt_times, rtt_values = rtt_data
    tput_times, tput_values = throughput_data
    retrans_times, retrans_counts = retrans_data
    
    # Plot RTT
    if len(rtt_times) > 0:
        axes[0].plot(rtt_times, rtt_values, linewidth=1, color='#1f77b4')
        axes[0].set_ylabel('RTT (ms)', fontsize=11)
        axes[0].set_title('TCP RTT', fontsize=12, fontweight='bold')
        axes[0].grid(True, alpha=0.3)
    else:
        axes[0].text(0.5, 0.5, 'No RTT data', ha='center', va='center', transform=axes[0].transAxes)
        axes[0].set_title('TCP RTT', fontsize=12, fontweight='bold')
    
    # Plot Throughput
    if len(tput_times) > 0:
        axes[1].plot(tput_times, tput_values, linewidth=1, color='#1f77b4')
        axes[1].set_ylabel('Throughput (Mbps)', fontsize=11)
        axes[1].set_title('Throughput', fontsize=12, fontweight='bold')
        axes[1].grid(True, alpha=0.3)
    else:
        axes[1].text(0.5, 0.5, 'No throughput data', ha='center', va='center', transform=axes[1].transAxes)
        axes[1].set_title('Throughput', fontsize=12, fontweight='bold')
    
    # Plot Retransmissions as bar chart
    if len(retrans_times) > 0:
        bar_width = retrans_times[1] - retrans_times[0] if len(retrans_times) > 1 else 0.5
        axes[2].bar(retrans_times, retrans_counts, width=bar_width * 0.8, color='#1f77b4', alpha=0.8)
        axes[2].set_ylabel('Retransmissions', fontsize=11)
        axes[2].set_title('TCP Drops', fontsize=12, fontweight='bold')
        axes[2].grid(True, alpha=0.3, axis='y')
    else:
        axes[2].text(0.5, 0.5, 'No retransmissions', ha='center', va='center', transform=axes[2].transAxes)
        axes[2].set_title('TCP Drops', fontsize=12, fontweight='bold')
    
    axes[2].set_xlabel('Time (s)', fontsize=11)
    
    plt.tight_layout()
    
    if output_file:
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"Saved: {output_file}")
    else:
        plt.show()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Extract and plot TCP metrics from pcap file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 plot_tcp_pcap.py capture.pcap
  python3 plot_tcp_pcap.py capture.pcap --output tcp_analysis
        """
    )
    parser.add_argument('pcap', type=str, help='Path to pcap file')
    parser.add_argument('--output', '-o', type=str, default='tcp',
                       help='Output file prefix (default: tcp)')
    parser.add_argument('--interval', '-i', type=float, default=0.5,
                       help='Time interval for binning in seconds (default: 0.5)')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.pcap):
        print(f"Error: File not found: {args.pcap}", file=sys.stderr)
        sys.exit(1)
    
    # Check tshark is available
    try:
        subprocess.run(['tshark', '--version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: tshark not found. Please install Wireshark/tshark.", file=sys.stderr)
        sys.exit(1)
    
    print(f"Analyzing pcap: {args.pcap}")
    
    print("Extracting TCP RTT...")
    rtt_data = extract_tcp_rtt(args.pcap)
    print(f"  Found {len(rtt_data[0])} RTT samples")
    
    print("Extracting throughput...")
    throughput_data = extract_throughput(args.pcap, args.interval)
    print(f"  Found {len(throughput_data[0])} intervals")
    
    print("Extracting retransmissions...")
    retrans_data = extract_retransmissions(args.pcap, args.interval)
    total_retrans = int(np.sum(retrans_data[1])) if len(retrans_data[1]) > 0 else 0
    print(f"  Found {total_retrans} retransmissions")
    
    input_dir = os.path.dirname(os.path.abspath(args.pcap)) or os.getcwd()
    output_file = os.path.join(input_dir, f'{args.output}_analysis.png')
    
    print(f"\nGenerating plot...")
    plot_tcp_metrics(rtt_data, throughput_data, retrans_data, output_file)
    
    # Print summary
    if len(rtt_data[1]) > 0:
        print(f"\nRTT Summary:")
        print(f"  Min:  {np.min(rtt_data[1]):.2f} ms")
        print(f"  Mean: {np.mean(rtt_data[1]):.2f} ms")
        print(f"  Max:  {np.max(rtt_data[1]):.2f} ms")
    
    if len(throughput_data[1]) > 0:
        print(f"\nThroughput Summary:")
        print(f"  Min:  {np.min(throughput_data[1]):.2f} Mbps")
        print(f"  Mean: {np.mean(throughput_data[1]):.2f} Mbps")
        print(f"  Max:  {np.max(throughput_data[1]):.2f} Mbps")
    
    print(f"\nTotal Retransmissions: {total_retrans}")
    
    print("\nDone!")


if __name__ == '__main__':
    main()
