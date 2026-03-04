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
│  │  │  └─────────────────┘  └─────────────────┘  └─────────────────────────┘  │     │   │
│  │  └─────────────────────────────────────────────────────────────────────┘     │   │
│  │                                                                              │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐     │   │
│  │  │                    Per-TTI Metrics Storage                          │     │   │
│  │  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │     │   │
│  │  │  │ mac_ue_met   │  │ mac_drb_met  │  │ rlc_drb_met  │  │ pdcp_met │ │     │   │
│  │  │  │ map<RNTI,..> │  │ map<RNTI,..> │  │ map<RNTI,..> │  │ map<..>  │ │     │   │
│  │  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────┘ │     │   │
│  │  │  ┌──────────────┐                                                   │     │   │
│  │  │  │ gtp_ue_met   │   All protected by std::mutex for thread safety   │     │   │
│  │  │  │ map<ue_idx,> │                                                   │     │   │
│  │  │  └──────────────┘                                                   │     │   │
│  │  └─────────────────────────────────────────────────────────────────────┘     │   │
│  │                                                                              │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐     │   │
│  │  │                    TTI State                                        │     │   │
│  │  │  current_tti (uint32)    TTI_ROLLOVER = 10000                       │     │   │
│  │  └─────────────────────────────────────────────────────────────────────┘     │   │
│  │                                                                              │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
│                                        │                                            │
│                                        │ send_tti_metrics() @ every TTI             │
│                                        ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │                         Protobuf Serialization                               │   │
│  │                                                                              │   │
│  │   TtiMetrics {                                                               │   │
│  │     tti_index: uint32 (rolls over @ 10000)                                   │   │
│  │     ue_metrics: [                                                            │   │
│  │       UeMetrics {                                                            │   │
│  │         rnti, mac_ue_metrics, mac_drb_metrics[],                             │   │
│  │         rlc_drb_metrics[], pdcp_drb_metrics[], gtp_ue_metrics                │   │
│  │       }, ...                                                                 │   │
│  │     ]                                                                        │   │
│  │   }                                                                          │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
│                                        │                                            │
└────────────────────────────────────────┼────────────────────────────────────────────┘
                                         │
                 ┌───────────────────────┴───────────────────────┐
                 │                                               │
                 ▼                                               ▼
    ┌────────────────────────┐                      ┌────────────────────────┐
    │   ZMQ PUB Socket       │                      │   ZMQ SUB Sockets      │
    │ ipc:///tmp/metrics     │                      │ (Control Channels)     │
    │                        │                      │                        │
    │  Publishes TtiMetrics  │                      │ • control_qos_actions  │
    │  every TTI             │                      │ • control_weights      │
    │                        │                      │ • control_mcs          │
    └───────────┬────────────┘                      └───────────┬────────────┘
                │                                               │
                ▼                                               ▼
    ┌────────────────────────┐                      ┌────────────────────────┐
    │   External Agent       │                      │   External Controller  │
    │   (Subscriber)         │                      │   (Publisher)          │
    │                        │                      │                        │
    │  Receives metrics      │                      │  Sends QoS/Weight/MCS  │
    │  for ML/analytics      │                      │  control commands      │
    └────────────────────────┘                      └────────────────────────┘
```

## Data Flow

### 1. Metrics Collection (Per Layer)

| Layer | Reporter Function | Key Type | Metrics |
|-------|------------------|----------|---------|
| **MAC** | `set_mac_ue()`, `set_mac_drb()` | RNTI | CQI, SNR, buffer sizes, HARQ stats, TBS |
| **RLC** | `report_rlc_metrics()` | du_ue_index → RNTI | TX/RX SDUs, PDUs, latency, retransmissions |
| **PDCP** | `report_pdcp_metrics()` | ue_index → RNTI | TX/RX PDUs, SDUs, dropped packets |
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
4. Publishes via ZMQ to `ipc:///tmp/metrics`
5. Clears per-TTI counters (MAC bytes, HARQ counts)

## Thread Safety

Multiple threads access EdgeRIC concurrently:
- **Scheduler thread**: MAC metrics, `send_tti_metrics()`
- **RLC executor threads**: RLC metrics per bearer
- **CU-UP threads**: PDCP and GTP metrics

Protection via `std::mutex`:
- `rlc_drb_mutex` - RLC metrics map
- `pdcp_drb_mutex` - PDCP metrics map  
- `gtp_ue_mutex` - GTP metrics map
- `du_ue_to_rnti_mutex` - ID mapping

## Control Interface

External controllers can send commands via ZMQ PUB sockets:

| Channel | Protobuf Message | Effect |
|---------|-----------------|--------|
| `ipc:///tmp/control_qos_actions` | `QosControl` | Override priority, PDB, GBR per DRB |
| `ipc:///tmp/control_weights` | `SchedulingWeights` | Override PF scheduler weights |
| `ipc:///tmp/control_mcs` | `mcs_control` | Override MCS selection |

## File Structure

```
lib/edgeric/
├── edgeric.h              # Class declaration, data structures
├── edgeric.cpp            # Implementation
├── CMakeLists.txt         # Build configuration
└── readme-architecture.md # This file

lib/protobufs/
├── metrics.proto          # TtiMetrics, UeMetrics definitions
├── control_qos.proto      # QoS control messages
├── control_weights.proto  # Scheduler weight control
└── control_mcs.proto      # MCS control
```

## Usage Example (Python Subscriber)

```python
import zmq

context = zmq.Context()
socket = context.socket(zmq.SUB)
socket.connect("ipc:///tmp/metrics")
socket.setsockopt_string(zmq.SUBSCRIBE, "")

while True:
    data = socket.recv()
    metrics = TtiMetrics()
    metrics.ParseFromString(data)
    print(f"TTI {metrics.tti_index}: {len(metrics.ue_metrics)} UEs")
```

## Metrics Struct Definitions

### MAC UE Metrics
```cpp
struct mac_ue_metrics {
    uint32_t cqi, snr, dl_buffer, ul_buffer;
    uint32_t dl_tbs, ul_tbs;
    uint32_t dl_harq_ack, dl_harq_nack;
    uint32_t ul_crc_ok, ul_crc_fail;
};
```

### MAC DRB Metrics  
```cpp
struct mac_drb_metrics {
    uint32_t dl_buffer, ul_buffer;
    uint32_t dl_bytes, ul_bytes;  // Per-TTI counters
};
```

### RLC DRB Metrics
```cpp
struct rlc_drb_metrics {
    uint64_t tx_sdus, tx_sdu_bytes, tx_pdus, tx_pdu_bytes;
    uint64_t tx_dropped_sdus, tx_retx_pdus;
    uint32_t tx_sdu_latency_us;
    uint64_t rx_sdus, rx_sdu_bytes, rx_pdus, rx_pdu_bytes;
    uint64_t rx_lost_pdus;
    uint32_t rx_sdu_latency_us;
};
```

### PDCP DRB Metrics
```cpp
struct pdcp_drb_metrics {
    // TX (DL) - from IP to RLC
    uint64_t tx_pdus, tx_pdu_bytes, tx_sdus, tx_dropped_sdus;
    uint32_t tx_discard_timeouts;     // Discard timer expirations (delay budget exceeded)
    uint32_t tx_pdu_latency_ns;       // Avg latency: SDU arrival → PDU to RLC
    
    // RX (UL) - from RLC to IP  
    uint64_t rx_pdus, rx_pdu_bytes, rx_delivered_sdus, rx_dropped_pdus;
    uint32_t rx_sdu_latency_ns;       // Avg latency: PDU arrival → SDU delivery
};
```

### PDCP Latency Explanation

**TX PDU Latency** (`tx_pdu_latency_ns`):
- Measures time from PDCP receiving an SDU from upper layer (IP/SDAP) until transmitting the PDU to RLC
- Includes: ciphering time, integrity protection, PDCP header construction, any internal queueing

**RX SDU Latency** (`rx_sdu_latency_ns`):
- Measures time from PDCP receiving a PDU from RLC until delivering the SDU to upper layer
- Includes: reordering wait time, deciphering, integrity verification

### GTP UE Metrics
```cpp
struct gtp_ue_metrics {
    uint64_t dl_pkts, dl_bytes;
    uint64_t ul_pkts, ul_bytes;
};
```
