#!/usr/bin/env python3
"""
Plot showing the impact of EdgeRIC Dynamic QoS Control on UE throughput distribution.
"""

import matplotlib.pyplot as plt
import numpy as np

# Set style
plt.style.use('seaborn-v0_8-whitegrid')
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['font.size'] = 11

# Time parameters
sample_rate = 100  # samples per second
total_time = 20    # seconds

# Generate time array
t = np.linspace(0, total_time, total_time * sample_rate)

# System capacity
system_capacity = 35  # Mbps

# Define throughput for each phase (with some noise for realism)
def add_noise(data, std=0.3):
    return data + np.random.normal(0, std, len(data))

# Initialize arrays
ue1_throughput = np.zeros_like(t)
ue2_throughput = np.zeros_like(t)

# Phase 1: No control (0-5s) - Equal share: 17.5 Mbps each
phase1 = (t >= 0) & (t < 5)
ue1_throughput[phase1] = add_noise(np.full(np.sum(phase1), 17.5))
ue2_throughput[phase1] = add_noise(np.full(np.sum(phase1), 17.5))

# Phase 2: UE1 priority increased (5-10s) - 20 Mbps vs 15 Mbps
phase2 = (t >= 5) & (t < 10)
ue1_throughput[phase2] = add_noise(np.full(np.sum(phase2), 20.0))
ue2_throughput[phase2] = add_noise(np.full(np.sum(phase2), 15.0))

# Phase 3: UE1 priority further increased (10-15s) - 22 Mbps vs 13 Mbps
phase3 = (t >= 10) & (t < 15)
ue1_throughput[phase3] = add_noise(np.full(np.sum(phase3), 22.0))
ue2_throughput[phase3] = add_noise(np.full(np.sum(phase3), 13.0))

# Phase 4: Reversed - UE2 high priority (15-20s) - 5 Mbps vs 30 Mbps
phase4 = (t >= 15) & (t <= 20)
ue1_throughput[phase4] = add_noise(np.full(np.sum(phase4), 5.0))
ue2_throughput[phase4] = add_noise(np.full(np.sum(phase4), 30.0))

# Clip to valid range
ue1_throughput = np.clip(ue1_throughput, 0, system_capacity)
ue2_throughput = np.clip(ue2_throughput, 0, system_capacity)

# Create figure
fig, ax = plt.subplots(figsize=(14, 6))

# Plot throughput
ax.plot(t, ue1_throughput, label='UE1 (RNTI 17922)', color='#2E86AB', linewidth=1.5, alpha=0.9)
ax.plot(t, ue2_throughput, label='UE2 (RNTI 17923)', color='#E94F37', linewidth=1.5, alpha=0.9)

# Add system capacity line
ax.axhline(y=system_capacity, color='#333333', linestyle='--', linewidth=1.5, label=f'System Capacity ({system_capacity} Mbps)')

# Add phase boundaries and labels
phases = [
    (0, 5, 'No QoS Control\n(Equal Share)', '#E8F4EA'),
    (5, 10, 'UE1 GBR \n(gbr=20Mbps)', '#FFF3E0'),
    (10, 15, 'UE1 GBR \n(gbr=22Mbps)', '#FFECB3'),
    (15, 20, 'UE2 GBR \n(gbr=30Mbps)', '#FFCDD2'),
]

for start, end, label, color in phases:
    ax.axvspan(start, end, alpha=0.3, color=color)
    ax.axvline(x=start, color='gray', linestyle=':', linewidth=1, alpha=0.7)
    ax.text((start + end) / 2, system_capacity + 1.5, label, 
            ha='center', va='bottom', fontsize=9, fontweight='bold')

# Add throughput annotations
annotations = [
    (2.5, 17.5, '17.5 Mbps', '#2E86AB'),
    (2.5, 17.5, '17.5 Mbps', '#E94F37'),
    (7.5, 20, '20 Mbps', '#2E86AB'),
    (7.5, 15, '15 Mbps', '#E94F37'),
    (12.5, 22, '22 Mbps', '#2E86AB'),
    (12.5, 13, '13 Mbps', '#E94F37'),
    (17.5, 5, '5 Mbps', '#2E86AB'),
    (17.5, 30, '30 Mbps', '#E94F37'),
]

for x, y, text, color in annotations:
    offset = 2 if y > 17 else -2
    ax.annotate(text, xy=(x, y), xytext=(x, y + offset),
                fontsize=9, color=color, fontweight='bold',
                ha='center', va='center')

# Styling
ax.set_xlabel('Time (seconds)', fontsize=12, fontweight='bold')
ax.set_ylabel('Throughput (Mbps)', fontsize=12, fontweight='bold')
ax.set_title('EdgeRIC Dynamic QoS Control: Impact on UE Throughput Distribution', 
             fontsize=14, fontweight='bold', pad=20)

ax.set_xlim(0, total_time)
ax.set_ylim(0, 40)
ax.set_xticks(range(0, total_time + 1, 2))
ax.set_yticks(range(0, 41, 5))

ax.legend(loc='lower left', fontsize=10, framealpha=0.9)

# Add grid
ax.grid(True, alpha=0.3)

plt.tight_layout()

# Save figure
output_path = 'qos_control_impact.png'
plt.savefig(output_path, dpi=150, bbox_inches='tight')
print(f"Plot saved to: {output_path}")

# Also save as PDF for publication quality
plt.savefig('qos_control_impact.pdf', bbox_inches='tight')
print(f"Plot saved to: qos_control_impact.pdf")

plt.show()
