# EdgeRIC Python Agent

Python-side collector and controller for EdgeRIC real-time telemetry.

## Setup

```bash
cd srsRAN_Project/edgeric
pip install -r requirements.txt
```

## Collector Agent

Subscribes to real-time metrics from the gNB:

```bash
# Pretty-printed output (default)
python3 collector.py

# JSON output (one line per TTI)
python3 collector.py --json

# Quiet mode (UE-level only, no per-DRB)
python3 collector.py --quiet

# Raw bytes (debugging)
python3 collector.py --raw
```

### Output Example

```
═══════════════════════════════════════════════════════════════
TTI  1234 | 14:32:15.123 | 1 UE(s)
═══════════════════════════════════════════════════════════════

┌─ UE RNTI=17921 (0x4601)
│  MAC: CQI=15 SNR=28.5dB DL_buf=1.2KB UL_buf=0B
│       TBS: DL=1024 UL=256 | HARQ: ACK=1 NACK=0 | CRC: OK=1 FAIL=0
│    MAC-DRB LCID=4: DL_buf=1.2KB UL_buf=0B DL=512B UL=0B
│    RLC LCID=4: TX: 10SDU/5.0KB lat=150us | RX: 5SDU/2.0KB
│    PDCP DRB=1 (LCID=4): TX: 10PDU/5.2KB drop=0 discard=0 lat=50us
│                         RX: 5PDU/2.1KB drop=0 lat=30us
│    GTP: DL: 100pkt/150.0KB | UL: 50pkt/25.0KB
└─────────────────────────────────────────────

```

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
    ├── rnti
    ├── mac (MacUeMetrics)
    ├── mac_drb[] (MacDrbMetrics)
    ├── rlc_drb[] (RlcDrbMetrics)
    ├── pdcp_drb[] (PdcpDrbMetrics)
    └── gtp (GtpMetrics)
```
