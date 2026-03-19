#!/usr/bin/env python3
"""
Plot YouTube QoE metrics from capture file

Usage:
    python3 plot_youtube_qoe.py <youtube_qoe.json> [--output PREFIX]
"""

import json
import sys
import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


# Quality to approximate bitrate mapping (Mbps)
QUALITY_BITRATE = {
    'tiny': 0.1,
    'small': 0.3,
    'medium': 0.7,
    'large': 1.5,
    'hd720': 2.5,
    'hd1080': 5.0,
    'hd1440': 9.0,
    'hd2160': 20.0,
    'highres': 25.0,
}


def load_qoe_data(filepath):
    """Load QoE JSON file"""
    with open(filepath, 'r') as f:
        return json.load(f)


def plot_youtube_qoe(data, output_file=None):
    """Plot YouTube QoE metrics"""
    metrics = data.get('metrics', [])
    qoe_summary = data.get('qoe_summary', {})
    
    if not metrics:
        print("No metrics data found!")
        return
    
    # Extract time series
    times = [m.get('elapsed_s', 0) for m in metrics]
    
    # Buffer level (seconds)
    buffer_seconds = [m.get('buffered_seconds', 0) for m in metrics]
    
    # Playback quality (convert to numeric)
    qualities = [m.get('playback_quality', 'unknown') for m in metrics]
    quality_numeric = [QUALITY_BITRATE.get(q, 0) for q in qualities]
    
    # Player state (1=playing, 3=buffering)
    states = [m.get('player_state_code', -1) for m in metrics]
    is_buffering = [1 if s == 3 else 0 for s in states]
    
    # Current playback position
    playback_pos = [m.get('current_time_s', 0) for m in metrics]
    
    # Extract bandwidth from video_stats (lbw field) - in bits/s, convert to Mbps
    bandwidth_mbps = []
    header_delay_ms = []
    for m in metrics:
        vs = m.get('video_stats', {})
        lbw = vs.get('lbw')
        lhd = vs.get('lhd')
        if lbw:
            try:
                bandwidth_mbps.append(float(lbw) / 1_000_000)
            except:
                bandwidth_mbps.append(None)
        else:
            bandwidth_mbps.append(None)
        if lhd:
            try:
                header_delay_ms.append(float(lhd) * 1000)  # Convert to ms
            except:
                header_delay_ms.append(None)
        else:
            header_delay_ms.append(None)
    
    # Create figure - 5 subplots now
    fig, axes = plt.subplots(5, 1, figsize=(14, 14))
    fig.suptitle('YouTube QoE Metrics', fontsize=14, fontweight='bold')
    
    # Plot 1: Buffer Level
    axes[0].plot(times, buffer_seconds, linewidth=1, color='#2E86AB')
    axes[0].fill_between(times, buffer_seconds, alpha=0.3, color='#2E86AB')
    axes[0].set_ylabel('Buffer (seconds)', fontsize=11)
    axes[0].set_title('Buffer Level', fontsize=12)
    axes[0].grid(True, alpha=0.3)
    axes[0].axhline(y=5, color='orange', linestyle='--', alpha=0.7, label='5s threshold')
    axes[0].legend(loc='best', fontsize=8)
    
    # Plot 2: Quality/Bitrate
    axes[1].plot(times, quality_numeric, linewidth=1, color='#28A745', drawstyle='steps-post')
    axes[1].fill_between(times, quality_numeric, alpha=0.3, color='#28A745', step='post')
    axes[1].set_ylabel('Est. Bitrate (Mbps)', fontsize=11)
    axes[1].set_title('Video Quality / Estimated Bitrate', fontsize=12)
    axes[1].grid(True, alpha=0.3)
    
    # Add quality labels on right y-axis
    ax1_twin = axes[1].twinx()
    ax1_twin.set_ylim(axes[1].get_ylim())
    quality_ticks = [(v, k) for k, v in QUALITY_BITRATE.items() if v <= max(quality_numeric) * 1.2]
    if quality_ticks:
        ax1_twin.set_yticks([v for v, k in quality_ticks])
        ax1_twin.set_yticklabels([k for v, k in quality_ticks], fontsize=8)
    
    # Plot 3: Buffering Events
    axes[2].fill_between(times, is_buffering, alpha=0.7, color='#DC3545', step='post')
    axes[2].set_ylabel('Buffering', fontsize=11)
    axes[2].set_title('Buffering/Stall Events', fontsize=12)
    axes[2].set_ylim(-0.1, 1.1)
    axes[2].set_yticks([0, 1])
    axes[2].set_yticklabels(['Playing', 'Buffering'])
    axes[2].grid(True, alpha=0.3)
    
    # Add stall event annotations
    stall_events = qoe_summary.get('stall_events', [])
    for i, stall in enumerate(stall_events[:10]):  # Show first 10
        duration_ms = stall.get('duration_ms', 0)
        axes[2].annotate(f'{duration_ms}ms', 
                        xy=(times[min(i*10, len(times)-1)], 0.5),
                        fontsize=8, color='red')
    
    # Plot 4: Measured Bandwidth (from YouTube's ABR algorithm)
    valid_bw = [(t, b) for t, b in zip(times, bandwidth_mbps) if b is not None]
    if valid_bw:
        bw_times, bw_values = zip(*valid_bw)
        axes[3].plot(bw_times, bw_values, linewidth=1.2, color='#9B59B6', label='Measured BW')
        axes[3].fill_between(bw_times, bw_values, alpha=0.2, color='#9B59B6')
        
        # Add reference lines for quality thresholds
        axes[3].axhline(y=2.5, color='green', linestyle='--', alpha=0.5, label='720p (~2.5 Mbps)')
        axes[3].axhline(y=5.0, color='blue', linestyle='--', alpha=0.5, label='1080p (~5 Mbps)')
        axes[3].axhline(y=15.0, color='red', linestyle='--', alpha=0.5, label='4K (~15 Mbps)')
        
        avg_bw = sum(bw_values) / len(bw_values)
        axes[3].axhline(y=avg_bw, color='orange', linestyle='-', alpha=0.7, 
                       label=f'Avg: {avg_bw:.1f} Mbps')
    axes[3].set_ylabel('Bandwidth (Mbps)', fontsize=11)
    axes[3].set_title('YouTube Measured Throughput (ABR Bandwidth Estimate)', fontsize=12)
    axes[3].grid(True, alpha=0.3)
    axes[3].legend(loc='best', fontsize=7)
    axes[3].set_ylim(bottom=0)
    
    # Plot 5: Playback Position (to detect stalls)
    axes[4].plot(times, playback_pos, linewidth=1, color='#6C757D')
    axes[4].set_ylabel('Playback Position (s)', fontsize=11)
    axes[4].set_title('Video Playback Position', fontsize=12)
    axes[4].set_xlabel('Elapsed Time (seconds)', fontsize=11)
    axes[4].grid(True, alpha=0.3)
    
    # Calculate bandwidth stats
    valid_bw_values = [b for b in bandwidth_mbps if b is not None]
    avg_bw_str = f"{sum(valid_bw_values)/len(valid_bw_values):.2f}" if valid_bw_values else "N/A"
    
    # Get optimal format from first metric
    optimal_fmt = metrics[0].get('video_stats', {}).get('optimal_format', 'N/A') if metrics else 'N/A'
    
    # Add QoE summary box
    summary_lines = [
        "QoE Summary",
        "─" * 22,
        f"Samples: {len(metrics)}",
        f"Startup: {qoe_summary.get('startup_time_s', 0):.2f}s" if qoe_summary.get('startup_time_s') else "Startup: N/A",
        f"Stalls: {qoe_summary.get('total_stalls', 0)}",
        f"Stall Time: {qoe_summary.get('total_stall_duration_ms', 0)}ms",
        f"Quality Switches: {qoe_summary.get('quality_switches', 0)}",
        "",
        "Network Stats",
        "─" * 22,
        f"Avg Bandwidth: {avg_bw_str} Mbps",
        f"Optimal Quality: {optimal_fmt}",
        f"Playing at: {qualities[-1] if qualities else 'N/A'}",
    ]
    summary_text = "\n".join(summary_lines)
    
    props = dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.9, edgecolor='gray')
    fig.text(0.98, 0.98, summary_text, transform=fig.transFigure, fontsize=9,
             verticalalignment='top', horizontalalignment='right',
             bbox=props, fontfamily='monospace')
    
    plt.tight_layout()
    plt.subplots_adjust(top=0.94, right=0.85)
    
    if output_file:
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"Saved: {output_file}")
    else:
        plt.show()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Plot YouTube QoE metrics',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('file', type=str, help='Path to youtube_qoe.json file')
    parser.add_argument('--output', '-o', type=str, default='youtube',
                       help='Output file prefix (default: youtube)')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.file):
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Loading QoE data from: {args.file}")
    data = load_qoe_data(args.file)
    
    print(f"Found {len(data.get('metrics', []))} samples")
    
    input_dir = os.path.dirname(os.path.abspath(args.file)) or os.getcwd()
    output_file = os.path.join(input_dir, f'{args.output}_qoe.png')
    
    print(f"Generating QoE plot...")
    plot_youtube_qoe(data, output_file)
    
    # Print summary
    qoe_summary = data.get('qoe_summary', {})
    print(f"\nQoE Summary:")
    print(f"  Video: {data.get('video_url', 'N/A')}")
    print(f"  Duration: {data.get('duration_s', 0)}s")
    print(f"  Samples: {data.get('total_samples', 0)}")
    print(f"  Startup Time: {qoe_summary.get('startup_time_s', 'N/A')}")
    print(f"  Total Stalls: {qoe_summary.get('total_stalls', 0)}")
    print(f"  Total Stall Duration: {qoe_summary.get('total_stall_duration_ms', 0)}ms")
    print(f"  Quality Switches: {qoe_summary.get('quality_switches', 0)}")


if __name__ == '__main__':
    main()
