# EdgeRIC MCS Control muApp

This microApp allows dynamic MCS (Modulation and Coding Scheme) control for individual UEs. When an MCS override is set, the gNB scheduler will use the specified MCS instead of link adaptation.

## Setup

```bash
cd srsRAN_Project/edgeric
source venv/bin/activate

# Generate protobuf (if not already done)
protoc --python_out=. --proto_path=../lib/protobufs ../lib/protobufs/control_mcs.proto
```

## Usage

### Interactive Mode (recommended)

```bash
cd muapp-mcs
python3 mcs_controller.py --interactive
```

Commands:
```
mcs> status                # Show active UEs and current overrides
mcs> set 17921 20          # Set MCS=20 for RNTI 17921
mcs> set 17922 28          # Set MCS=28 for RNTI 17922
mcs> setall 15             # Set MCS=15 for all active UEs
mcs> clear 17921           # Clear override (revert to link adaptation)
mcs> clearall              # Clear all overrides
mcs> quit
```

### Command-Line Mode

```bash
# Set MCS for a specific UE
python3 mcs_controller.py --rnti 17921 --mcs 20

# Clear MCS override
python3 mcs_controller.py --rnti 17921 --clear
```

## MCS Index Reference

| MCS Index | Modulation | Approx. Code Rate | Use Case |
|-----------|------------|-------------------|----------|
| 0-9       | QPSK       | Low               | Poor channel, cell edge |
| 10-16     | 16QAM      | Medium            | Average channel |
| 17-28     | 64QAM      | High              | Good channel, high throughput |

**Note:** MCS 27-28 typically require very good channel conditions (CQI 14-15).

## How It Works

1. **Metrics Subscription**: The controller subscribes to `ipc:///tmp/metrics_data` to learn active UEs and their RNTIs.

2. **MCS Control**: When you set an MCS override, it publishes to `ipc:///tmp/control_mcs` with an ordered array of MCS values matching the gNB's UE ordering.

3. **gNB Processing**: The gNB receives the control message in `get_mcs_from_er()` and applies the MCS during scheduling (see `set_pdsch_params()` in `ue_cell_grid_allocator.cpp`).

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      MCS Controller                          │
│                                                              │
│  ┌─────────────────┐          ┌─────────────────────────┐   │
│  │ Metrics         │◄─────────│ ipc:///tmp/metrics_data │   │
│  │ Subscriber      │  (SUB)   │ (from gNB)              │   │
│  └─────────────────┘          └─────────────────────────┘   │
│          │                                                   │
│          ▼                                                   │
│  ┌─────────────────┐                                        │
│  │ Active UE       │  Tracks RNTIs in sorted order          │
│  │ Tracker         │                                        │
│  └─────────────────┘                                        │
│          │                                                   │
│          ▼                                                   │
│  ┌─────────────────┐          ┌─────────────────────────┐   │
│  │ MCS Control     │─────────►│ ipc:///tmp/control_mcs  │   │
│  │ Publisher       │  (PUB)   │ (to gNB)                │   │
│  └─────────────────┘          └─────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

## Example: Comparing MCS Impact

```bash
# Terminal 1: Run collector to see metrics
python3 ../collector.py --quiet

# Terminal 2: Set low MCS (see throughput drop)
python3 mcs_controller.py --rnti 17921 --mcs 5

# Terminal 2: Set high MCS (see throughput increase)
python3 mcs_controller.py --rnti 17921 --mcs 28

# Terminal 2: Revert to link adaptation
python3 mcs_controller.py --rnti 17921 --clear
```

## Limitations

- MCS override is for **DL only** (affects PDSCH scheduling)
- UL MCS is determined by gNB link adaptation based on PUSCH CRC/SNR
- Setting MCS too high for channel conditions will cause HARQ failures
- The MCS value of 255 is used internally to mean "no override"

## Protobuf Schema

```protobuf
message mcs_control {
    uint32 ran_index = 1;       // Incrementing control index
    repeated float mcs = 2;     // MCS values per UE (ordered by RNTI)
}
```
