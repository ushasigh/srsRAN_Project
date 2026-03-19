#!/usr/bin/env python3
"""
Plot ping latency CDF from ping output file
Shows percentile summary (p50, p90, p95, p99) in a box

Usage:
    python3 plot_ping_latency.py <ping_output.txt> [--output PREFIX]
"""

import re
import sys
import numpy as np
import matplotlib.pyplot as plt


def parse_ping_file(filepath):
    """Parse ping output file and extract latencies in ms"""
    latencies = []
    pattern = re.compile(r'time=([0-9.]+)\s*ms')
    
    with open(filepath, 'r') as f:
        for line in f:
            match = pattern.search(line)
            if match:
                latencies.append(float(match.group(1)))
    
    return np.array(latencies)


def plot_ping_cdf(latencies, output_file=None):
    """Plot CDF of ping latencies with percentile summary box"""
    fig, ax = plt.subplots(figsize=(10, 7))
    
    # Sort latencies for CDF
    sorted_latencies = np.sort(latencies)
    cdf = np.arange(1, len(sorted_latencies) + 1) / len(sorted_latencies)
    
    # Plot CDF
    ax.plot(sorted_latencies, cdf, linewidth=2, color='#2E86AB')
    ax.fill_between(sorted_latencies, cdf, alpha=0.3, color='#2E86AB')
    
    # Calculate percentiles
    p50 = np.percentile(latencies, 50)
    p90 = np.percentile(latencies, 90)
    p95 = np.percentile(latencies, 95)
    p99 = np.percentile(latencies, 99)
    mean_lat = np.mean(latencies)
    min_lat = np.min(latencies)
    max_lat = np.max(latencies)
    
    # Draw percentile lines
    for p, val, color in [(0.50, p50, '#28A745'), (0.90, p90, '#FFC107'), 
                           (0.95, p95, '#FD7E14'), (0.99, p99, '#DC3545')]:
        ax.axhline(y=p, color=color, linestyle='--', alpha=0.7, linewidth=1)
        ax.axvline(x=val, color=color, linestyle='--', alpha=0.7, linewidth=1)
    
    # Create summary text box
    summary_text = (
        f"Ping Latency Summary\n"
        f"{'─' * 22}\n"
        f"Samples:  {len(latencies):,}\n"
        f"Min:      {min_lat:.2f} ms\n"
        f"Mean:     {mean_lat:.2f} ms\n"
        f"p50:      {p50:.2f} ms\n"
        f"p90:      {p90:.2f} ms\n"
        f"p95:      {p95:.2f} ms\n"
        f"p99:      {p99:.2f} ms\n"
        f"Max:      {max_lat:.2f} ms"
    )
    
    # Add text box
    props = dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.9, edgecolor='gray')
    ax.text(0.97, 0.03, summary_text, transform=ax.transAxes, fontsize=10,
            verticalalignment='bottom', horizontalalignment='right',
            bbox=props, fontfamily='monospace')
    
    # Configure axes
    ax.set_xlabel('Latency (ms)', fontsize=12)
    ax.set_ylabel('CDF', fontsize=12)
    ax.set_title('Ping Latency CDF', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, 1.02)
    ax.set_xlim(0, None)
    
    # Add y-axis ticks at percentile levels
    ax.set_yticks([0, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 1.0])
    ax.set_yticklabels(['0%', '25%', '50%', '75%', '90%', '95%', '99%', '100%'])
    
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
        description='Plot ping latency CDF from ping output file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 plot_ping_latency.py ping_run1.txt
  python3 plot_ping_latency.py ping_run1.txt --output ping_metrics
        """
    )
    parser.add_argument('file', type=str, help='Path to ping output file')
    parser.add_argument('--output', '-o', type=str, default='ping',
                       help='Output file prefix (default: ping)')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.file):
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Reading ping output from: {args.file}")
    latencies = parse_ping_file(args.file)
    
    if len(latencies) == 0:
        print("Error: No ping latencies found in file!", file=sys.stderr)
        sys.exit(1)
    
    print(f"Parsed {len(latencies)} ping samples")
    
    # Print summary to console
    print(f"\nLatency Summary:")
    print(f"  Min:  {np.min(latencies):.2f} ms")
    print(f"  Mean: {np.mean(latencies):.2f} ms")
    print(f"  p50:  {np.percentile(latencies, 50):.2f} ms")
    print(f"  p90:  {np.percentile(latencies, 90):.2f} ms")
    print(f"  p95:  {np.percentile(latencies, 95):.2f} ms")
    print(f"  p99:  {np.percentile(latencies, 99):.2f} ms")
    print(f"  Max:  {np.max(latencies):.2f} ms")
    
    input_dir = os.path.dirname(os.path.abspath(args.file)) or os.getcwd()
    prefix = args.output
    
    print(f"\nGenerating CDF plot...")
    
    cdf_file = os.path.join(input_dir, f'{prefix}_latency_cdf.png')
    plot_ping_cdf(latencies, output_file=cdf_file)
    
    print("\nPing latency CDF plot generated successfully!")


if __name__ == '__main__':
    main()
