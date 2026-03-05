# EdgeRIC Python Agent

Python-side collector and controller for EdgeRIC real-time telemetry.

## Setup

```bash
cd srsRAN_Project/edgeric
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Collector Agent

Subscribes to real-time metrics from the gNB:

```bash
# Pretty-printed output (default)
python3 collector.py

# JSON output (one line per TTI)
python3 collector.py --json

# JSON to file
python3 collector.py --json --output metrics.json

# Quiet mode (MAC-level only, no per-DRB details)
python3 collector.py --quiet
```

### Output Example

```
 TTI 04999 │ 17:43:48.859 │ 2 UE(s) 

╔══ UE RNTI 17921 (0x4601) ══════════════════════════════════════════
║ ▸ MAC Layer
║   Channel:  CQI=15  SNR=  1.2dB
║   Buffers:  DL= 156.2KB  UL=      0B
║   DL Sched: TBS= 3329  MCS=28  PRBs= 40  Rate=26.6Mbps
║   UL Sched: TBS=  241  MCS= 1  PRBs= 47  Rate=1.9Mbps
║   HARQ TTI:  DL +1/+0  UL +1/+0
║   BLER:      DL  0.52% (1924 total)  UL  0.00% (487 total)
║
║ ▲ UL (Uplink)
║   DRB 1 (LCID 4)
║     RLC:  buf=      0B  RX   1080 SDU / 58.10KB  lat=    -     lost=0
║     PDCP: RX   1075 PDU / 57.80KB  lat=  1.10ms  drop=0
║   GTP-U:    11213 pkts /   573.4KB
║
║ ▼ DL (Downlink)
║   DRB 1 (LCID 4)
║     RLC:  buf= 156.2KB  TX   2896 SDU /  3.87MB  lat= 43.24ms  retx=0
║     PDCP: TX   2883 PDU /  3.85MB  lat=  71.0us  drop=0  discard=0
║   GTP-U:    30336 pkts /    40.47MB
╚════════════════════════════════════════════════════════════
```

## Metrics Reference

### MAC Layer Metrics (per TTI)

| Metric | Unit | Description |
|--------|------|-------------|
| `cqi` | Index (0-15) | Wideband Channel Quality Indicator |
| `snr` | dB | PUSCH Signal-to-Noise Ratio |
| `dl_buffer` | Bytes | Total DL pending bytes in RLC buffer |
| `ul_buffer` | Bytes | Total UL pending bytes (from BSR) |
| `dl_tbs` | Bytes | DL Transport Block Size this TTI |
| `ul_tbs` | Bytes | UL Transport Block Size this TTI |
| `dl_mcs` | Index (0-28) | DL Modulation and Coding Scheme |
| `ul_mcs` | Index (0-28) | UL Modulation and Coding Scheme |
| `dl_prbs` | Count | DL Physical Resource Blocks allocated |
| `ul_prbs` | Count | UL Physical Resource Blocks allocated |
| `dl_harq_ack` | Count | DL HARQ ACKs received this TTI |
| `dl_harq_nack` | Count | DL HARQ NACKs received this TTI |
| `ul_crc_ok` | Count | UL CRC passes this TTI |
| `ul_crc_fail` | Count | UL CRC failures this TTI |

### Rate Calculation

Instantaneous rate is derived from TBS:
```
Rate (bps) = TBS (bytes) × 8 × 1000
```
Since 1 TTI = 1ms, TBS in bytes/TTI converts directly to rate.

### RLC Metrics (per DRB, accumulated)

| Metric | Unit | Description |
|--------|------|-------------|
| `dl_buffer` | Bytes | DL pending bytes in RLC TX buffer |
| `ul_buffer` | Bytes | UL pending bytes (from BSR, per LCG) |
| `tx_sdus` | Count | SDUs received from PDCP (DL) |
| `tx_sdu_bytes` | Bytes | SDU bytes received from PDCP |
| `tx_sdu_latency_us` | Microseconds | Avg SDU latency (PDCP→MAC queue delay) |
| `rx_sdus` | Count | SDUs delivered to PDCP (UL) |
| `rx_sdu_bytes` | Bytes | SDU bytes delivered to PDCP |
| `rx_lost_pdus` | Count | Lost PDUs (detected gaps) |

### PDCP Metrics (per DRB, accumulated)

| Metric | Unit | Description |
|--------|------|-------------|
| `tx_pdus` | Count | PDCP PDUs transmitted (DL) |
| `tx_pdu_bytes` | Bytes | TX PDU bytes |
| `tx_dropped_sdus` | Count | SDUs dropped (discard timer, etc) |
| `tx_discard_timeouts` | Count | Discard timer expirations |
| `tx_pdu_latency_ns` | Nanoseconds | Avg latency: SDU in → PDU out |
| `rx_pdus` | Count | PDCP PDUs received (UL) |
| `rx_pdu_bytes` | Bytes | RX PDU bytes |
| `rx_dropped_pdus` | Count | PDUs dropped (integrity fail, etc) |
| `rx_sdu_latency_ns` | Nanoseconds | Avg latency: PDU in → SDU out |

### GTP-U Metrics (per UE, accumulated)

| Metric | Unit | Description |
|--------|------|-------------|
| `dl_pkts` | Count | DL GTP-U packets from core (N3) |
| `dl_bytes` | Bytes | DL GTP-U bytes from core |
| `ul_pkts` | Count | UL GTP-U packets to core |
| `ul_bytes` | Bytes | UL GTP-U bytes to core |

## ZMQ Addresses

| Channel | Direction | Address |
|---------|-----------|---------|
| Metrics | gNB → Agent | `ipc:///tmp/metrics_data` |
| QoS Control | Agent → gNB | `ipc:///tmp/control_qos_actions` |
| Weight Control | Agent → gNB | `ipc:///tmp/control_weights` |
| MCS Control | Agent → gNB | `ipc:///tmp/control_mcs` |

## Conflate Mode

Both the gNB publisher and Python subscriber use ZMQ conflate mode:
- Only the latest message is kept in the queue
- Prevents backpressure/queue buildup if subscriber is slow
- Guarantees real-time view (may skip TTIs if subscriber can't keep up)

## Protobuf Schema

See `metrics_pb2.py` (generated from `lib/protobufs/metrics.proto`)

```
TtiMetrics
├── tti_index (uint32, rolls over at 10000)
├── timestamp_us (uint64, Unix time in microseconds)
└── ues[] (repeated UeMetrics)
    ├── rnti (uint32, C-RNTI)
    ├── mac (MacUeMetrics)
    │   ├── cqi, snr
    │   ├── dl_buffer, ul_buffer
    │   ├── dl_tbs, ul_tbs
    │   ├── dl_mcs, ul_mcs
    │   ├── dl_prbs, ul_prbs
    │   └── dl_harq_ack, dl_harq_nack, ul_crc_ok, ul_crc_fail
    ├── mac_drb[] (MacDrbMetrics per LCID)
    ├── rlc_drb[] (RlcDrbMetrics per LCID)
    ├── pdcp_drb[] (PdcpDrbMetrics per DRB)
    └── gtp (GtpMetrics)
```

## Notes

- **Per-TTI vs Accumulated**: MAC scheduling metrics (TBS, MCS, PRBs, HARQ) are per-TTI and reset after each report. RLC, PDCP, and GTP metrics are accumulated totals.
- **LCID Mapping**: DRBs use LCID = DRB_ID + 3 (e.g., DRB 1 → LCID 4)
- **Zero Values**: TBS=0 means the UE was not scheduled that TTI (normal behavior)
