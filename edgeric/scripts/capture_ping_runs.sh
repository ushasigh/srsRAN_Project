#!/bin/bash
# sudo ./capture_ping_runs.sh ../telemetry-runs/2026-03-18/run1

DURATION=60
PING_TARGET=10.45.0.1
PING_INTERVAL=0.1

if [ -z "$1" ]; then
    echo "Usage: $0 <output_path>"
    echo "Example: $0 ../telemetry-runs/2026-03-18/run1"
    exit 1
fi

OUTPUT_PATH="$1"

mkdir -p "$OUTPUT_PATH"

cat > "$OUTPUT_PATH/experiment_description.txt" << EOF
Experiment: Ping Latency Test with EdgeRIC Metrics Collection
Date: $(date)
Duration: ${DURATION}s

Components:
- Ping: sudo ip netns exec ue1 ping ${PING_TARGET} -i ${PING_INTERVAL}
- Metrics: EdgeRIC collector agent (collector.py)

Output Files:
- ping_run1.txt: Raw ping output from UE1 namespace
- metrics_ping.json: EdgeRIC metrics collected during the ping test

Network Configuration:
- UE1 network namespace pinging core network at ${PING_TARGET}
- Ping interval: ${PING_INTERVAL}s (high frequency for detailed latency measurement)
EOF

echo "Output directory: $OUTPUT_PATH"
echo "Duration: ${DURATION}s"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting EdgeRIC collector..."
sudo "$SCRIPT_DIR/../venv/bin/python" "$SCRIPT_DIR/../collector.py" --json --output "$OUTPUT_PATH/metrics_ping.json" &
COLLECTOR_PID=$!

sleep 1

echo "Starting ping test..."
sudo ip netns exec ue1 ping "$PING_TARGET" -i "$PING_INTERVAL" > "$OUTPUT_PATH/ping_run1.txt" 2>&1 &
PING_PID=$!

echo "Running for $DURATION seconds..."
sleep $DURATION

echo "Stopping ping..."
sudo kill -2 $PING_PID 2>/dev/null

echo "Stopping collector..."
sudo kill -15 $COLLECTOR_PID 2>/dev/null

sleep 2

if ps -p $COLLECTOR_PID > /dev/null 2>&1; then
    echo "Collector still running, force killing..."
    sudo kill -9 $COLLECTOR_PID 2>/dev/null
fi

if ps -p $PING_PID > /dev/null 2>&1; then
    echo "Ping still running, force killing..."
    sudo kill -9 $PING_PID 2>/dev/null
fi

echo ""
echo "Done. Output files saved to: $OUTPUT_PATH"
echo "  - experiment_description.txt"
echo "  - ping_run1.txt"
echo "  - metrics_ping.json"
