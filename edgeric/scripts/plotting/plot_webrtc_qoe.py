#!/usr/bin/env python3
"""
Plot WebRTC QoE metrics from capture file

Usage:
    python3 plot_webrtc_qoe.py <webrtc_qoe.json> [--output PREFIX]
"""

import json
import sys
import os
import numpy as np
import matplotlib.pyplot as plt


def load_qoe_data(filepath):
    """Load QoE JSON file"""
    with open(filepath, 'r') as f:
        return json.load(f)


def plot_webrtc_qoe(data, output_file=None):
    """Plot WebRTC QoE metrics - RTT, jitter, packet loss"""
    metrics = data.get('metrics', [])
    qoe_summary = data.get('qoe_summary', {})
    
    if not metrics:
        print("No metrics data found!")
        return
    
    # Extract time series
    times = [m.get('elapsed_s', 0) for m in metrics]
    
    # RTT (ms)
    rtts = []
    for m in metrics:
        rtt = m.get('summary', {}).get('rtt_ms')
        rtts.append(rtt if rtt is not None else np.nan)
    
    # Jitter (ms)
    jitters = []
    for m in metrics:
        jitter = m.get('summary', {}).get('jitter_ms')
        jitters.append(jitter if jitter is not None else np.nan)
    
    # Packet loss (%)
    packet_loss = []
    for m in metrics:
        loss = m.get('summary', {}).get('packet_loss_percent')
        packet_loss.append(loss if loss is not None else np.nan)
    
    # Connection state
    states = []
    state_map = {'new': 0, 'connecting': 1, 'connected': 2, 'disconnected': 3, 'failed': 4, 'closed': 5}
    for m in metrics:
        state = m.get('summary', {}).get('connection_state', 'unknown')
        states.append(state_map.get(state, -1))
    
    # Video framerate
    framerates = []
    for m in metrics:
        fps = m.get('summary', {}).get('video_framerate')
        framerates.append(fps if fps is not None else np.nan)
    
    # Create figure
    fig, axes = plt.subplots(5, 1, figsize=(14, 14))
    fig.suptitle('WebRTC QoE Metrics (Jitsi Meet)', fontsize=14, fontweight='bold')
    
    # Plot 1: RTT
    valid_rtts = [r for r in rtts if not np.isnan(r)]
    if valid_rtts:
        axes[0].plot(times, rtts, linewidth=1.2, color='#2E86AB', label='RTT')
        axes[0].fill_between(times, rtts, alpha=0.2, color='#2E86AB')
        axes[0].axhline(y=np.nanmean(rtts), color='orange', linestyle='--', alpha=0.7, 
                       label=f'Mean: {np.nanmean(rtts):.1f}ms')
        # Add p95 line
        p95 = np.nanpercentile(rtts, 95)
        axes[0].axhline(y=p95, color='red', linestyle=':', alpha=0.7,
                       label=f'P95: {p95:.1f}ms')
    axes[0].set_ylabel('RTT (ms)', fontsize=11)
    axes[0].set_title('Round-Trip Time', fontsize=12)
    axes[0].grid(True, alpha=0.3)
    axes[0].legend(loc='best', fontsize=8)
    
    # Plot 2: Jitter
    valid_jitters = [j for j in jitters if not np.isnan(j)]
    if valid_jitters:
        axes[1].plot(times, jitters, linewidth=1.2, color='#28A745', label='Jitter')
        axes[1].fill_between(times, jitters, alpha=0.2, color='#28A745')
        axes[1].axhline(y=np.nanmean(jitters), color='orange', linestyle='--', alpha=0.7,
                       label=f'Mean: {np.nanmean(jitters):.1f}ms')
    axes[1].set_ylabel('Jitter (ms)', fontsize=11)
    axes[1].set_title('Jitter', fontsize=12)
    axes[1].grid(True, alpha=0.3)
    axes[1].legend(loc='best', fontsize=8)
    
    # Plot 3: Packet Loss
    valid_loss = [p for p in packet_loss if not np.isnan(p)]
    if valid_loss:
        axes[2].plot(times, packet_loss, linewidth=1.2, color='#DC3545', label='Packet Loss')
        axes[2].fill_between(times, packet_loss, alpha=0.2, color='#DC3545')
        if max(valid_loss) > 0:
            axes[2].axhline(y=np.nanmean(packet_loss), color='orange', linestyle='--', alpha=0.7,
                           label=f'Mean: {np.nanmean(packet_loss):.2f}%')
    axes[2].set_ylabel('Packet Loss (%)', fontsize=11)
    axes[2].set_title('Packet Loss', fontsize=12)
    axes[2].grid(True, alpha=0.3)
    axes[2].legend(loc='best', fontsize=8)
    axes[2].set_ylim(bottom=0)
    
    # Plot 4: Video Framerate
    valid_fps = [f for f in framerates if not np.isnan(f)]
    if valid_fps:
        axes[3].plot(times, framerates, linewidth=1.2, color='#6C757D', label='Framerate')
        axes[3].fill_between(times, framerates, alpha=0.2, color='#6C757D')
        axes[3].axhline(y=np.nanmean(framerates), color='orange', linestyle='--', alpha=0.7,
                       label=f'Mean: {np.nanmean(framerates):.1f} fps')
    axes[3].set_ylabel('FPS', fontsize=11)
    axes[3].set_title('Video Framerate', fontsize=12)
    axes[3].grid(True, alpha=0.3)
    axes[3].legend(loc='best', fontsize=8)
    axes[3].set_ylim(bottom=0)
    
    # Plot 5: Connection State
    state_colors = {0: 'gray', 1: 'yellow', 2: 'green', 3: 'orange', 4: 'red', 5: 'black'}
    state_names = {0: 'new', 1: 'connecting', 2: 'connected', 3: 'disconnected', 4: 'failed', 5: 'closed'}
    
    for i in range(len(times) - 1):
        if states[i] >= 0:
            axes[4].axvspan(times[i], times[i+1], alpha=0.6, 
                          color=state_colors.get(states[i], 'gray'))
    
    axes[4].set_ylabel('Connection State', fontsize=11)
    axes[4].set_title('WebRTC Connection State', fontsize=12)
    axes[4].set_xlabel('Elapsed Time (seconds)', fontsize=11)
    axes[4].set_yticks(list(state_names.keys()))
    axes[4].set_yticklabels(list(state_names.values()))
    axes[4].set_ylim(-0.5, 5.5)
    axes[4].grid(True, alpha=0.3, axis='x')
    
    # Add QoE summary box
    rtt_stats = qoe_summary.get('rtt_stats_ms', {})
    jitter_stats = qoe_summary.get('jitter_stats_ms', {})
    loss_stats = qoe_summary.get('packet_loss_stats_percent', {})
    
    summary_lines = [
        "QoE Summary",
        "─" * 24,
        f"Samples: {len(metrics)}",
        f"Connection: {qoe_summary.get('connection_established_s', 'N/A'):.2f}s" if qoe_summary.get('connection_established_s') else "Connection: N/A",
        "",
        "RTT (ms):",
        f"  Mean: {rtt_stats.get('mean', 0):.1f}" if rtt_stats else "  N/A",
        f"  P95:  {rtt_stats.get('p95', 0):.1f}" if rtt_stats else "",
        f"  Max:  {rtt_stats.get('max', 0):.1f}" if rtt_stats else "",
        "",
        "Jitter (ms):",
        f"  Mean: {jitter_stats.get('mean', 0):.1f}" if jitter_stats else "  N/A",
        f"  P95:  {jitter_stats.get('p95', 0):.1f}" if jitter_stats else "",
        "",
        "Packet Loss (%):",
        f"  Mean: {loss_stats.get('mean', 0):.2f}" if loss_stats else "  N/A",
        f"  Max:  {loss_stats.get('max', 0):.2f}" if loss_stats else "",
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


def plot_webrtc_distribution(data, output_file=None):
    """Plot distribution/histogram of WebRTC metrics"""
    metrics = data.get('metrics', [])
    
    if not metrics:
        return
    
    # Extract values
    rtts = [m.get('summary', {}).get('rtt_ms') for m in metrics]
    rtts = [r for r in rtts if r is not None]
    
    jitters = [m.get('summary', {}).get('jitter_ms') for m in metrics]
    jitters = [j for j in jitters if j is not None]
    
    losses = [m.get('summary', {}).get('packet_loss_percent') for m in metrics]
    losses = [l for l in losses if l is not None]
    
    # Create figure
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    fig.suptitle('WebRTC Metrics Distribution', fontsize=14, fontweight='bold')
    
    # RTT histogram
    if rtts:
        axes[0].hist(rtts, bins=30, color='#2E86AB', alpha=0.7, edgecolor='black')
        axes[0].axvline(np.mean(rtts), color='red', linestyle='--', label=f'Mean: {np.mean(rtts):.1f}ms')
        axes[0].axvline(np.percentile(rtts, 95), color='orange', linestyle=':', label=f'P95: {np.percentile(rtts, 95):.1f}ms')
        axes[0].set_xlabel('RTT (ms)')
        axes[0].set_ylabel('Count')
        axes[0].set_title('RTT Distribution')
        axes[0].legend(fontsize=8)
    
    # Jitter histogram
    if jitters:
        axes[1].hist(jitters, bins=30, color='#28A745', alpha=0.7, edgecolor='black')
        axes[1].axvline(np.mean(jitters), color='red', linestyle='--', label=f'Mean: {np.mean(jitters):.1f}ms')
        axes[1].axvline(np.percentile(jitters, 95), color='orange', linestyle=':', label=f'P95: {np.percentile(jitters, 95):.1f}ms')
        axes[1].set_xlabel('Jitter (ms)')
        axes[1].set_ylabel('Count')
        axes[1].set_title('Jitter Distribution')
        axes[1].legend(fontsize=8)
    
    # Packet loss histogram
    if losses:
        axes[2].hist(losses, bins=30, color='#DC3545', alpha=0.7, edgecolor='black')
        axes[2].axvline(np.mean(losses), color='red', linestyle='--', label=f'Mean: {np.mean(losses):.2f}%')
        axes[2].set_xlabel('Packet Loss (%)')
        axes[2].set_ylabel('Count')
        axes[2].set_title('Packet Loss Distribution')
        axes[2].legend(fontsize=8)
    
    plt.tight_layout()
    
    if output_file:
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"Saved: {output_file}")
    else:
        plt.show()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Plot WebRTC QoE metrics',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('file', type=str, help='Path to webrtc_qoe.json file')
    parser.add_argument('--output', '-o', type=str, default='webrtc',
                       help='Output file prefix (default: webrtc)')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.file):
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Loading QoE data from: {args.file}")
    data = load_qoe_data(args.file)
    
    print(f"Found {len(data.get('metrics', []))} samples")
    
    input_dir = os.path.dirname(os.path.abspath(args.file)) or os.getcwd()
    
    # Generate main QoE plot
    output_file = os.path.join(input_dir, f'{args.output}_qoe.png')
    print(f"Generating QoE time series plot...")
    plot_webrtc_qoe(data, output_file)
    
    # Generate distribution plot
    dist_file = os.path.join(input_dir, f'{args.output}_distribution.png')
    print(f"Generating distribution plot...")
    plot_webrtc_distribution(data, dist_file)
    
    # Print summary
    qoe_summary = data.get('qoe_summary', {})
    rtt_stats = qoe_summary.get('rtt_stats_ms', {})
    jitter_stats = qoe_summary.get('jitter_stats_ms', {})
    loss_stats = qoe_summary.get('packet_loss_stats_percent', {})
    
    print(f"\nQoE Summary:")
    print(f"  Room: {data.get('room_name', 'N/A')}")
    print(f"  Server: {data.get('jitsi_server', 'N/A')}")
    print(f"  Duration: {data.get('duration_s', 0)}s")
    print(f"  Samples: {data.get('total_samples', 0)}")
    print(f"  Connection Time: {qoe_summary.get('connection_established_s', 'N/A')}")
    
    if rtt_stats:
        print(f"\n  RTT (ms):")
        print(f"    Mean: {rtt_stats.get('mean', 0):.1f}")
        print(f"    P95:  {rtt_stats.get('p95', 0):.1f}")
        print(f"    Max:  {rtt_stats.get('max', 0):.1f}")
    
    if jitter_stats:
        print(f"\n  Jitter (ms):")
        print(f"    Mean: {jitter_stats.get('mean', 0):.1f}")
        print(f"    P95:  {jitter_stats.get('p95', 0):.1f}")
        print(f"    Max:  {jitter_stats.get('max', 0):.1f}")
    
    if loss_stats:
        print(f"\n  Packet Loss (%):")
        print(f"    Mean: {loss_stats.get('mean', 0):.2f}")
        print(f"    Max:  {loss_stats.get('max', 0):.2f}")


if __name__ == '__main__':
    main()
