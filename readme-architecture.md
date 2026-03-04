# EdgeRIC Architecture

## Overview

EdgeRIC is a real-time telemetry and control system for srsRAN gNB that collects metrics from multiple protocol layers and enables external control via ZeroMQ.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              srsRAN gNB Process                                     │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐          │
│  │   GTP-U      │   │    PDCP      │   │     RLC      │   │     MAC      │          │
│  │  (CU-UP)     │   │   (CU-UP)    │   │    (DU)      │   │    (DU)      │          │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘   └──────┬───────┘          │
│         │                  │                  │                  │                  │
│         │ report_gtp_*     │ report_pdcp_*    │ report_rlc_*     │ set_mac_*        │
│         │ (ue_index)       │ (ue_index)       │ (du_ue_index)    │ (RNTI)           │
│         │                  │                  │                  │                  │
│         ▼                  ▼                  ▼                  ▼                  │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │                           edgeric (Static Class)                             │   │
│  ├──────────────────────────────────────────────────────────────────────────────┤   │
│  │                                                                              │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐     │   │
│  │  │                    ID Correlation Maps                               │     │   │
│  │  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │     │   │
│  │  │  │ du_ue_to_rnti   │  │ e1ap_to_rnti    │  │ cu_up_ue_to_e1ap    │  │     │   │
│  │  │  │ du_ue_index→RNTI│  │ e1ap_id→RNTI    │  │ cu_up_idx→e1ap_id   │  │     │   │
│  │  │  └─────────────────┘  └─────────────────┘  └─────────────────────┘  │     │   │
│  │  └─────────────────────────────────────────────────────────────────────┘     │   │
│  │                                                                              │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐     │   │
│  │  │                    Per-TTI Metrics Storage                          │     │   │
│  │  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │     │   │
│  │  │  │ mac_ue       │  │ mac_drb      │  │ rlc_drb      │  │ pdcp_drb │ │     │   │
│  │  │  │ map<RNTI,..> │  │ map<key,..>  │  │ map<key,..>  │  │ map<..>  │ │     │   │
│  │  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────┘ │     │   │
│  │  │  ┌──────────────┐                                                   │     │   │
│  │  │  │ gtp_ue       │   Protected by std::mutex for thread safety       │     │   │
│  │  │  │ map<ue_idx,> │                                                   │     │   │
│  │  │  └──────────────┘                                                   │     │   │
│  │  └─────────────────────────────────────────────────────────────────────┘     │   │
│  │                                                                              │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐     │   │
│  │  │                    Control Reception                                │     │   │
│  │  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │     │   │
│  │  │  │ mcs_recved      │  │ weights_recved  │  │ qos_overrides       │  │     │   │
│  │  │  │ map<RNTI,MCS>   │  │ map<RNTI,float> │  │ map<key,QoS>        │  │     │   │
│  │  │  └─────────────────┘  └─────────────────┘  └─────────────────────┘  │     │   │
│  │  └─────────────────────────────────────────────────────────────────────┘     │   │
│  │                                                                              │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
│                                        │                                            │
│                     ┌──────────────────┼──────────────────┐                         │
│                     │                  │                  │                         │
│                     ▼                  ▼                  ▼                         │
│            get_mcs_from_er()   get_weights_from_er()   get_qos_from_er()           │
│                                        │                                            │
│                                        │ send_tti_metrics() @ every TTI             │
│                                        ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │                         Protobuf Serialization                               │   │
│  │                                                                              │   │
│  │   TtiMetrics {                                                               │   │
│  │     tti_index: uint32 (rolls over @ 10000)                                   │   │
│  │     timestamp_us: uint64 (Unix time in microseconds)                         │   │
│  │     ues: [                                                                   │   │
│  │       UeMetrics {                                                            │   │
│  │         rnti, mac (MacUeMetrics), mac_drb[], rlc_drb[], pdcp_drb[], gtp      │   │
│  │       }, ...                                                                 │   │
│  │     ]                                                                        │   │
│  │   }                                                                          │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
│                                        │                                            │
└────────────────────────────────────────┼────────────────────────────────────────────┘
                                         │
          ┌──────────────────────────────┴──────────────────────────────┐
          │                                                             │
          ▼                                                             ▼
┌─────────────────────────┐                              ┌─────────────────────────┐
│   ZMQ PUB Socket        │                              │   ZMQ SUB Sockets       │
│ ipc:///tmp/metrics_data │                              │ (Control Channels)      │
│                         │                              │                         │
│  Publishes TtiMetrics   │                              │ • control_mcs           │
│  every TTI (1ms)        │                              │ • control_weights       │
│  (Conflate mode)        │                              │ • control_qos_actions   │
└───────────┬─────────────┘                              └───────────┬─────────────┘
            │                                                        │
            ▼                                                        ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│                           EdgeRIC Python Agents (edgeric/)                        │
├───────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  ┌─────────────────────────┐  ┌─────────────────────────┐  ┌───────────────────┐  │
│  │    collector.py         │  │    muapp-mcs/           │  │ muapp-qos-control │  │
│  │    (Metrics Display)    │  │    mcs_controller.py    │  │ qos_controller.py │  │
│  │                         │  │                         │  │                   │  │
│  │  • Subscribes to        │  │  • Set MCS per UE       │  │ • Set QoS params  │  │
│  │    metrics_data         │  │  • Values 0-28          │  │ • Priority, PDB   │  │
│  │  • Pretty print / JSON  │  │  • 255 = auto (LA)      │  │ • GBR, ARP        │  │
│  │  • Rolling BLER calc    │  │                         │  │                   │  │
│  └─────────────────────────┘  └─────────────────────────┘  └───────────────────┘  │
│                                                                                   │
└───────────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Metrics Collection (Per Layer)

| Layer | Reporter Function | Key Type | Metrics |
|-------|------------------|----------|---------|
| **MAC** | `set_mac_ue()`, `set_dl_tbs()`, `set_dl_prbs()` | RNTI | CQI, SNR, buffer sizes, TBS, MCS, PRBs, HARQ stats |
| **RLC** | `report_rlc_metrics()` | du_ue_index → RNTI | TX/RX SDUs, PDUs, latency, retransmissions |
| **PDCP** | `report_pdcp_metrics()` | ue_index → RNTI | TX/RX PDUs, SDUs, dropped packets, latency |
| **GTP** | `report_gtp_dl/ul_pkt()` | ue_index | DL/UL packet counts and bytes |

### 2. ID Correlation Chain

```
CU-UP ue_index → E1AP ID → RNTI
                    ↑
        du_ue_index → RNTI (direct)
```

The correlation is established via:
- `register_du_ue(du_ue_index, rnti)` - Called when UE joins scheduler
- `register_cu_up_ue_e1ap(ue_index, e1ap_id)` - Called in CU-UP E1AP handler
- `register_e1ap_rnti(e1ap_id, rnti)` - Called in CU-CP E1AP handler

### 3. TTI-Synchronized Output

Every TTI (1ms), `send_tti_metrics()` is called from the scheduler:
1. Collects all metrics from static maps
2. Correlates CU-UP indices to RNTIs
3. Serializes to `TtiMetrics` protobuf message
4. Publishes via ZMQ to `ipc:///tmp/metrics_data`
5. Clears per-TTI counters (TBS, MCS, PRBs, HARQ counts)

## Thread Safety

Multiple threads access EdgeRIC concurrently:
- **Scheduler thread**: MAC metrics, `send_tti_metrics()`
- **RLC executor threads**: RLC metrics per bearer
- **CU-UP threads**: PDCP and GTP metrics

Protection via `std::mutex`:
- `rlc_mutex` - RLC metrics map
- `pdcp_mutex` - PDCP metrics map  
- `gtp_mutex` - GTP metrics map
- `du_ue_mutex` - ID mapping

## Control Interface

External controllers can send commands via ZMQ PUB sockets:

| Channel | Protobuf Message | Effect |
|---------|-----------------|--------|
| `ipc:///tmp/control_mcs` | `mcs_control` | Override MCS selection (255 = no override) |
| `ipc:///tmp/control_weights` | `SchedulingWeights` | Override PF scheduler weights |
| `ipc:///tmp/control_qos_actions` | `QosControl` | Override priority, PDB, GBR per DRB |

### MCS Control

MCS values are sent as an ordered array matching the gNB's UE order (sorted by RNTI):
- Values 0-28: Override MCS to specified value
- Value 255: No override (use link adaptation)

## File Structure

```
srsRAN_Project/
├── lib/
│   ├── edgeric/
│   │   ├── edgeric.h              # Class declaration, data structures
│   │   ├── edgeric.cpp            # Implementation
│   │   └── CMakeLists.txt         # Build configuration
│   └── protobufs/
│       ├── metrics.proto          # TtiMetrics, UeMetrics definitions
│       ├── control_qos.proto      # QoS control messages
│       ├── control_weights.proto  # Scheduler weight control
│       └── control_mcs.proto      # MCS control
│
├── edgeric/                       # Python agents
│   ├── collector.py               # Metrics collector/display
│   ├── metrics_pb2.py             # Generated protobuf
│   ├── control_mcs_pb2.py         # Generated protobuf
│   ├── control_qos_pb2.py         # Generated protobuf
│   ├── requirements.txt           # Python dependencies
│   ├── README.md                  # Agent documentation
│   ├── muapp-mcs/                 # MCS control muApp
│   │   ├── mcs_controller.py
│   │   └── README.md
│   └── muapp-qos-control/         # QoS control muApp
│       ├── qos_controller.py
│       └── README_QOS_CONTROL.md
│
└── readme-architecture.md         # This file
```

## Python Agent Usage

### Collector (Metrics Display)

```bash
cd edgeric
source venv/bin/activate

# Pretty-printed output
python3 collector.py

# JSON output (for ML/analytics)
python3 collector.py --json

# Quiet mode (MAC-level only)
python3 collector.py --quiet
```

### MCS Control muApp

```bash
cd edgeric/muapp-mcs

# Interactive mode
python3 mcs_controller.py -i

# Command-line
python3 mcs_controller.py --rnti 17921 --mcs 20
python3 mcs_controller.py --rnti 17921 --clear
```

### QoS Control muApp

```bash
cd edgeric/muapp-qos-control

# Interactive mode
python3 qos_controller.py -i

# Command-line
python3 qos_controller.py --rnti 17921 --lcid 4 --qos-priority 1 --pdb-ms 20
```

## Metrics Struct Definitions

### MAC UE Metrics (per-TTI)
```cpp
struct mac_ue_metrics {
    uint32_t cqi;              // Wideband CQI (0-15)
    float snr;                 // PUSCH SNR in dB
    uint32_t dl_buffer;        // Total DL pending bytes
    uint32_t ul_buffer;        // Total UL pending bytes (from BSR)
    uint32_t dl_tbs;           // DL Transport Block Size this TTI
    uint32_t ul_tbs;           // UL Transport Block Size this TTI
    uint32_t dl_mcs;           // DL MCS index this TTI
    uint32_t ul_mcs;           // UL MCS index this TTI
    uint32_t dl_prbs;          // DL PRBs allocated this TTI
    uint32_t ul_prbs;          // UL PRBs allocated this TTI
    uint32_t dl_harq_ack;      // DL HARQ ACKs this TTI
    uint32_t dl_harq_nack;     // DL HARQ NACKs this TTI
    uint32_t ul_crc_ok;        // UL CRC passes this TTI
    uint32_t ul_crc_fail;      // UL CRC failures this TTI
};
```

### MAC DRB Metrics  
```cpp
struct mac_drb_metrics {
    uint32_t dl_buffer;        // DL pending bytes
    uint32_t ul_buffer;        // UL pending bytes
    uint32_t dl_bytes;         // DL bytes scheduled this TTI
    uint32_t ul_bytes;         // UL bytes received this TTI
};
```

### RLC DRB Metrics (accumulated)
```cpp
struct rlc_drb_metrics {
    // Buffer status
    uint32_t dl_buffer;        // DL pending bytes (RLC TX buffer)
    uint32_t ul_buffer;        // UL pending bytes (from BSR, per LCG)
    // TX (DL) metrics
    uint64_t tx_sdus, tx_sdu_bytes, tx_pdus, tx_pdu_bytes;
    uint64_t tx_dropped_sdus, tx_retx_pdus;
    uint32_t tx_sdu_latency_us;
    // RX (UL) metrics
    uint64_t rx_sdus, rx_sdu_bytes, rx_pdus, rx_pdu_bytes;
    uint64_t rx_lost_pdus;
    uint32_t rx_sdu_latency_us;
};
```

### PDCP DRB Metrics (accumulated)
```cpp
struct pdcp_drb_metrics {
    // TX (DL) - from SDAP to RLC
    uint64_t tx_pdus, tx_pdu_bytes, tx_sdus, tx_dropped_sdus;
    uint32_t tx_discard_timeouts;     // Discard timer expirations
    uint32_t tx_pdu_latency_ns;       // Avg latency: SDU in → PDU out
    // RX (UL) - from RLC to SDAP  
    uint64_t rx_pdus, rx_pdu_bytes, rx_delivered_sdus, rx_dropped_pdus;
    uint32_t rx_sdu_latency_ns;       // Avg latency: PDU in → SDU out
};
```

### GTP UE Metrics (accumulated)
```cpp
struct gtp_ue_metrics {
    uint64_t dl_pkts, dl_bytes;    // DL from UPF (N3)
    uint64_t ul_pkts, ul_bytes;    // UL to UPF (N3)
};
```

## Per-TTI vs Accumulated Metrics

| Type | Metrics | Reset After Each TTI |
|------|---------|---------------------|
| **Per-TTI** | TBS, MCS, PRBs, HARQ counts | Yes |
| **Accumulated** | RLC SDU/PDU counts, PDCP counts, GTP counts, latencies | No |

## Collector Features

The Python collector (`collector.py`) provides:

1. **Real-time display**: Pretty-printed metrics per UE
2. **DL/UL separation**: Separate sections for uplink and downlink
3. **Rolling BLER**: Cumulative Block Error Rate calculation
4. **JSON output**: Machine-readable format for ML/analytics
5. **Per-DRB breakdown**: RLC and PDCP metrics per Data Radio Bearer

### BLER Calculation

BLER is calculated cumulatively in the collector (not per-TTI):
```
DL BLER = cumulative_harq_nack / (cumulative_harq_ack + cumulative_harq_nack) × 100%
UL BLER = cumulative_crc_fail / (cumulative_crc_ok + cumulative_crc_fail) × 100%
```

## Building

```bash
cd srsRAN_Project/build
ninja

# Generate Python protobufs (if needed)
cd ../edgeric
protoc --python_out=. --proto_path=../lib/protobufs ../lib/protobufs/*.proto
```
