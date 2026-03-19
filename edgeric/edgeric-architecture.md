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
| **MAC** | `set_mac_ue()`, `set_dl_tbs()`, `inc_dl_harq_ack()` | RNTI | CQI, SNR, buffer sizes, TBS, MCS, PRBs, HARQ stats, goodput |
| **MAC Delays** | `report_mac_delays()` | RNTI | CE/CRC/HARQ/SR delays (from scheduler metrics, per-report-period) |
| **RLC** | `report_rlc_metrics()` | du_ue_index → RNTI | TX/RX SDUs, PDUs, latency, retransmissions (per LCID) |
| **PDCP** | `report_pdcp_metrics()` | cu_up_ue_index → RNTI | TX/RX PDUs, SDUs, dropped packets, latency (per DRB) |
| **GTP** | `report_gtp_dl/ul_pkt()` | cu_up_ue_index | DL/UL packet counts and bytes (N3 interface) |

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

### UE Lifecycle Management

When a UE disconnects (RRC release), `unregister_ue_by_rnti(rnti)` is called to clean up all metrics:
- MAC UE metrics (`mac_ue`)
- MAC DRB metrics (`mac_drb`)
- RLC DRB metrics (`rlc_drb`)
- PDCP DRB metrics (`pdcp_drb`)
- GTP metrics (`gtp_ue`)
- QoS overrides (`qos_overrides`)
- All ID correlation maps

This ensures only active UEs have their metrics streamed. When a UE reconnects (e.g., RRC re-establishment), it gets a new RNTI and starts with fresh metrics.

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
    // Channel quality (updated per-TTI)
    uint32_t cqi;              // Wideband CQI (0-15)
    float snr;                 // PUSCH SNR in dB
    
    // Buffer status (updated per-TTI)
    uint32_t dl_buffer;        // Total DL pending bytes
    uint32_t ul_buffer;        // Total UL pending bytes (aggregate from BSR)
    
    // Scheduling metrics (reset per-TTI)
    uint32_t dl_tbs;           // DL Transport Block Size scheduled this TTI
    uint32_t ul_tbs;           // UL Transport Block Size scheduled this TTI
    uint32_t dl_mcs;           // DL MCS index this TTI
    uint32_t ul_mcs;           // UL MCS index this TTI
    uint32_t dl_prbs;          // DL PRBs allocated this TTI
    uint32_t ul_prbs;          // UL PRBs allocated this TTI
    
    // Goodput metrics (reset per-TTI) - bytes from successful transmissions
    uint32_t dl_acked_bytes;   // DL bytes confirmed via HARQ ACK (goodput)
    uint32_t ul_ok_bytes;      // UL bytes successfully decoded via CRC OK (goodput)
    
    // HARQ feedback (reset per-TTI)
    uint32_t dl_harq_ack;      // DL HARQ ACKs received this TTI
    uint32_t dl_harq_nack;     // DL HARQ NACKs received this TTI
    uint32_t ul_crc_ok;        // UL CRC passes this TTI
    uint32_t ul_crc_fail;      // UL CRC failures this TTI
    
    // MAC layer delays in ms (updated per-report-period, NOT reset per-TTI)
    float avg_ce_delay_ms;          // Avg CE (Control Element) processing delay
    float avg_crc_delay_ms;         // Avg CRC indication processing delay
    float avg_pucch_harq_delay_ms;  // Avg PUCCH HARQ feedback delay
    float avg_pusch_harq_delay_ms;  // Avg PUSCH HARQ feedback delay
    float avg_sr_to_pusch_delay_ms; // Avg Scheduling Request to PUSCH grant delay
    float avg_sum_mac_delay_ms;     // Sum of all MAC delays above
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

### RLC DRB Metrics (accumulated, per-LCID)
```cpp
struct rlc_drb_metrics {
    // Buffer status
    uint32_t dl_buffer;        // DL pending bytes (RLC TX buffer for this LCID)
    uint32_t ul_buffer;        // (Not used - UL buffer is per-LCG at MAC level)
    
    // TX (DL) metrics - from PDCP towards MAC
    uint64_t tx_sdus;          // SDUs received from PDCP
    uint64_t tx_sdu_bytes;     // SDU bytes received from PDCP
    uint64_t tx_pdus;          // PDUs sent to MAC
    uint64_t tx_pdu_bytes;     // PDU bytes sent to MAC
    uint64_t tx_dropped_sdus;  // SDUs dropped (discard timer, buffer full)
    uint64_t tx_retx_pdus;     // Retransmitted PDUs (RLC AM mode)
    uint32_t tx_sdu_latency_us;// Avg SDU latency: PDCP→MAC (queue delay)
    
    // RX (UL) metrics - from MAC towards PDCP
    uint64_t rx_sdus;          // SDUs delivered to PDCP
    uint64_t rx_sdu_bytes;     // SDU bytes delivered to PDCP
    uint64_t rx_pdus;          // PDUs received from MAC
    uint64_t rx_pdu_bytes;     // PDU bytes received from MAC
    uint64_t rx_lost_pdus;     // Lost PDUs (detected gaps in SN)
    uint32_t rx_sdu_latency_us;// Avg SDU reassembly latency
};
```

**Note**: RLC metrics are reported per actual DRB (LCID). Only LCIDs with active RLC entities appear.

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

### GTP UE Metrics (accumulated, per-UE)
```cpp
struct gtp_ue_metrics {
    uint64_t dl_pkts;      // DL GTP-U packets received from UPF (N3 interface)
    uint64_t dl_bytes;     // DL GTP-U bytes received from UPF
    uint64_t ul_pkts;      // UL GTP-U packets sent to UPF (N3 interface)
    uint64_t ul_bytes;     // UL GTP-U bytes sent to UPF
};
```

**Note**: GTP metrics represent IP-level traffic on the N3 interface (between gNB CU-UP and 5G Core UPF). These are cumulative counters since UE connection, tracking actual user data volume before/after all radio processing.

## Metrics Timing and Periodicity

### Reset Behavior

| Category | Metrics | Reset After Each TTI | Update Frequency |
|----------|---------|---------------------|------------------|
| **Scheduling** | `dl_tbs`, `ul_tbs`, `dl_mcs`, `ul_mcs`, `dl_prbs`, `ul_prbs` | Yes | Per-TTI (1ms) |
| **HARQ Feedback** | `dl_harq_ack`, `dl_harq_nack`, `ul_crc_ok`, `ul_crc_fail` | Yes | Per-TTI |
| **Goodput** | `dl_acked_bytes`, `ul_ok_bytes` | Yes | Per-TTI |
| **MAC Delays** | `avg_ce_delay_ms`, `avg_crc_delay_ms`, etc. | No | Per-report-period (default 1000ms) |
| **RLC Counts** | SDU/PDU counts, bytes, retransmissions | No | Accumulated |
| **PDCP Counts** | PDU counts, bytes, drops | No | Accumulated |
| **GTP Counts** | Packet/byte counts | No | Accumulated |
| **Channel Quality** | `cqi`, `snr` | No | Updated when reported |
| **Buffers** | `dl_buffer`, `ul_buffer` | No | Updated per-TTI |

### MAC Layer Delays Explained

The MAC delay metrics are **averaged over the srsRAN scheduler report period** (configurable via `du_report_period`, default 1000ms):

| Delay Metric | What It Measures |
|--------------|------------------|
| `avg_ce_delay_ms` | Time from UL Control Element reception to scheduler processing |
| `avg_crc_delay_ms` | Time from PUSCH transmission to CRC indication result |
| `avg_pucch_harq_delay_ms` | Time from PDSCH transmission to PUCCH HARQ-ACK/NACK feedback |
| `avg_pusch_harq_delay_ms` | Time from PUSCH grant to CRC result processing |
| `avg_sr_to_pusch_delay_ms` | Time from Scheduling Request detection to PUSCH grant |
| `avg_sum_mac_delay_ms` | Simple sum of all five delays above |

These delays are reported in **milliseconds** and represent processing/feedback latencies in the MAC layer.

### Goodput vs Scheduled Bytes

| Metric | Description | Timing |
|--------|-------------|--------|
| `dl_tbs` | Bytes scheduled for DL transmission (PDSCH) | Recorded at scheduling time |
| `dl_acked_bytes` | Bytes confirmed delivered (HARQ ACK received) | Recorded when ACK arrives (~4-8 slots later) |
| `ul_tbs` | Bytes expected from UL (PUSCH grant) | Recorded at scheduling time |
| `ul_ok_bytes` | Bytes successfully decoded (CRC OK) | Recorded when CRC result available (~1-2 slots later) |

**Important**: In any given TTI, `tbs` and `acked_bytes` do NOT correspond to the same transmission due to HARQ round-trip delay. For aggregate throughput, average over time.

## LCID Mapping (5G NR)

| LCID | Bearer Type | Purpose |
|------|-------------|---------|
| 0 | CCCH | Common Control Channel (RRC before security) |
| 1 | SRB1 | Signaling Radio Bearer 1 (RRC after security) |
| 2 | SRB2 | Signaling Radio Bearer 2 (NAS messages) |
| 3 | SRB3 | Signaling Radio Bearer 3 (if configured) |
| **4+** | **DRBs** | Data Radio Bearers (LCID = DRB_ID + 3) |

Example: DRB1 = LCID 4, DRB2 = LCID 5, DRB3 = LCID 6

## Collector Features

The Python collector (`collector.py`) provides:

1. **Real-time display**: Pretty-printed metrics per UE with color coding
2. **DL/UL separation**: Separate sections for uplink and downlink traffic
3. **Rolling BLER**: Cumulative Block Error Rate calculation (since collector start)
4. **Goodput display**: Shows successfully transmitted bytes (not just scheduled)
5. **MAC delay display**: Shows scheduler processing delays in milliseconds
6. **JSON output**: Machine-readable JSONL format for ML/analytics
7. **Per-DRB breakdown**: RLC and PDCP metrics per Data Radio Bearer

### BLER Calculation

BLER is calculated cumulatively in the collector (not by gNB):
```
DL BLER = cumulative_harq_nack / (cumulative_harq_ack + cumulative_harq_nack) × 100%
UL BLER = cumulative_crc_fail / (cumulative_crc_ok + cumulative_crc_fail) × 100%
```

Resets when: collector restarts, or UE reconnects with new RNTI.

### Sample Output

```
╔══ UE RNTI 17921 (0x4601) ══════════════════════════════════════════
║ ▸ MAC Layer
║   Channel:  CQI=15  SNR= 25.3dB
║   Buffers:  DL=  303.5KB  UL=      0B
║   DL Sched: TBS= 3649  MCS=26  PRBs= 48  Goodput=29.2Mbps
║   UL Sched: TBS=    0  MCS= 0  PRBs=  0  Goodput=0Kbps
║   HARQ TTI:  DL +1/+0  UL +0/+0
║   BLER:      DL  0.00% (138 total)  UL  2.50% (80 total)
║   MAC Delays: CE=0.00ms  CRC=3.00ms  PUCCH=3.00ms  PUSCH=3.00ms  SR→PUSCH=6.00ms
║   Sum MAC:    15.00ms
║
║ ▲ UL (Uplink)
║   DRB 1 (LCID 4)
║     RLC:  buf=      0B
║           SDU: RX     49 /    2.6KB  lat=112.80ms
║           PDU: RX     75 /    2.9KB  lost=0
║     PDCP: RX     51 PDU /    2.7KB  lat= 136.7us  drop=0
║   GTP-U:    59666 pkts /     3.00MB
║
║ ▼ DL (Downlink)
║   DRB 1 (LCID 4)
║     RLC:  buf= 303.5KB
║           SDU: TX    136 /  186.3KB  lat=188.46ms  drop=0
║           PDU: TX    176 /  172.8KB  retx=0
║     PDCP: TX    136 PDU /  186.3KB  lat=  36.2us  drop=0  discard=0
║   GTP-U:   147341 pkts /   196.51MB
╚════════════════════════════════════════════════════════════════════
```

## Configuration

### MAC Delay Report Period

The MAC layer delays are averaged over the srsRAN scheduler metrics report period. Configure in gNB YAML:

```yaml
metrics:
  periodicity:
    du_report_period: 1000  # in milliseconds (default: 1000ms = 1 second)
```

Shorter periods = more frequent updates but higher CPU overhead.

### JSON Output Format

When running `collector.py --json`, each line is a JSON object:

```json
{
  "tti_index": 1234,
  "timestamp_us": 1710000000000000,
  "ues": [{
    "rnti": 17921,
    "mac": {
      "cqi": 15,
      "snr": 25.3,
      "dl": {
        "buffer": 310784,
        "tbs": 3649,
        "acked_bytes": 3649,
        "mcs": 26,
        "prbs": 48,
        "harq_ack_tti": 1,
        "harq_nack_tti": 0,
        "bler_pct": 0.0,
        "harq_total": 138
      },
      "ul": {
        "buffer": 0,
        "tbs": 0,
        "ok_bytes": 0,
        "mcs": 0,
        "prbs": 0,
        "crc_ok_tti": 0,
        "crc_fail_tti": 0,
        "bler_pct": 2.5,
        "crc_total": 80
      },
      "avg_ce_delay_ms": 0.0,
      "avg_crc_delay_ms": 3.0,
      "avg_pucch_harq_delay_ms": 3.0,
      "avg_pusch_harq_delay_ms": 3.0,
      "avg_sr_to_pusch_delay_ms": 6.0,
      "avg_sum_mac_delay_ms": 15.0
    },
    "drbs": [...],
    "gtp": {"dl": {...}, "ul": {...}}
  }]
}
```

## Building

```bash
cd srsRAN_Project/build
ninja

# Generate Python protobufs (if .proto files changed)
cd ../lib/protobufs
protoc --cpp_out=../edgeric --python_out=../../edgeric metrics.proto
protoc --cpp_out=../edgeric --python_out=../../edgeric control_*.proto
```
