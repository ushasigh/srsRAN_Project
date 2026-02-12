# EdgeRIC Dynamic QoS Control

This module enables dynamic QoS (Quality of Service) parameter control for the srsRAN gNB scheduler via ZMQ and Protobuf.

## Overview

EdgeRIC can dynamically override QoS parameters (priority, ARP, PDB, GBR) for specific UE DRBs (Data Radio Bearers) without modifying the static QoS configuration. These overrides affect the QoS scheduler's prioritization decisions.

## Prerequisites

```bash
# Install Python dependencies
sudo apt-get install -y python3-protobuf python3-zmq
# OR
pip3 install protobuf pyzmq --break-system-packages
```

## Files

| File | Description |
|------|-------------|
| `control_qos.proto` | Protobuf message definition for QoS control |
| `control_qos_pb2.py` | Generated Python protobuf module |
| `qos_controller.py` | Interactive QoS controller |
| `qos_random_sender.py` | Automatic random QoS sender (for testing) |

## Usage

### 1. Start the gNB with QoS Scheduler

Make sure your `zmq-mode.yml` has:
```yaml
cell_cfg:
  scheduler:
    policy:
      qos_sched:
```

Then run:
```bash
cd /home/wcsng-23/gitrepos/ushasi-hpe
sudo ./run_gnb_multi_ue.sh
```

### 2. Run the QoS Controller

#### Interactive Mode
```bash
cd /home/wcsng-23/gitrepos/ushasi-hpe/srsRAN_Project/lib/protobufs
python3 qos_controller.py -i
```

**Commands:**
```
priority <rnti> <lcid> <qos_prio> [arp_prio]  - Set priority
pdb <rnti> <lcid> <pdb_ms>                    - Set Packet Delay Budget
gbr <rnti> <lcid> <gbr_dl_mbps> [gbr_ul_mbps] - Set GBR (in Mbps)
clear <rnti> <lcid>                           - Clear override
example                                        - Send example updates
quit                                           - Exit
```

**Examples:**
```
qos> priority 17922 4 1 1
qos> pdb 17922 4 50
qos> gbr 17922 4 20 5
qos> clear 17922 4
```

#### Command-Line Mode
```bash
# Set QoS priority
python3 qos_controller.py --rnti 17922 --lcid 4 --qos-priority 1 --arp-priority 1

# Set PDB
python3 qos_controller.py --rnti 17922 --lcid 4 --pdb-ms 50

# Set GBR
python3 qos_controller.py --rnti 17922 --lcid 4 --gbr-dl-mbps 20 --gbr-ul-mbps 5

# Clear override
python3 qos_controller.py --rnti 17922 --lcid 4 --clear
```

### 3. Random QoS Sender (Testing)

Sends random QoS updates every 200ms for RNTI 17922 and 17923:

```bash
cd /home/wcsng-23/gitrepos/ushasi-hpe/srsRAN_Project/lib/protobufs
python3 qos_random_sender.py
```

## Log Files

The gNB writes logs to the build directory:

```bash
# EdgeRIC QoS reception log (what was received from Python)
tail -f /home/wcsng-23/gitrepos/ushasi-hpe/srsRAN_Project/build/apps/gnb/edgeric_qos_log.txt

# Scheduler QoS usage log (what values are being used per DRB)
tail -f /home/wcsng-23/gitrepos/ushasi-hpe/srsRAN_Project/build/apps/gnb/edgeric_qos_sched_log.txt
```

## QoS Parameters

| Parameter | Range | Description |
|-----------|-------|-------------|
| `qos_priority` | 1-127 | QoS Priority Level (1 = highest) |
| `arp_priority` | 1-15 | ARP Priority Level (1 = highest) |
| `pdb_ms` | 10-300+ | Packet Delay Budget in milliseconds |
| `gbr_dl` | bps | Guaranteed Bit Rate Downlink |
| `gbr_ul` | bps | Guaranteed Bit Rate Uplink |

## Architecture

```
┌─────────────────────┐      ZMQ (IPC)       ┌─────────────────────┐
│   Python Script     │ ─────────────────────▶│   srsRAN gNB        │
│  (qos_controller)   │  control_qos.proto   │   (edgeric.cpp)     │
└─────────────────────┘                       └──────────┬──────────┘
                                                         │
                                                         ▼
                                              ┌─────────────────────┐
                                              │  QoS Scheduler      │
                                              │ (scheduler_time_qos)│
                                              └─────────────────────┘
```

## Recompiling Protobuf

If you modify `control_qos.proto`:

```bash
cd /home/wcsng-23/gitrepos/ushasi-hpe/srsRAN_Project/lib/protobufs
protoc --cpp_out=../edgeric --python_out=. control_qos.proto
```

Then rebuild the gNB:
```bash
cd /home/wcsng-23/gitrepos/ushasi-hpe
./make-ran.sh
```
