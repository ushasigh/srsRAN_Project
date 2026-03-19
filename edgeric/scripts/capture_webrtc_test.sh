#!/bin/bash
#
# Capture WebRTC QoE metrics (via Jitsi Meet) alongside EdgeRIC RAN metrics
#
# Usage:
#   sudo ./capture_webrtc_test.sh <output_path> [--room <room_name>] [--duration <seconds>]
#
# Example:
#   sudo ./capture_webrtc_test.sh ../telemetry-runs/2026-03-18/webrtc_run1 --duration 60

DURATION=60
UE_NAMESPACE=ue1
ROOM_NAME=""
INTERVAL_MS=100
JITSI_SERVER="meet.jit.si"

# Parse arguments
OUTPUT_PATH=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --room|-r)
            ROOM_NAME="$2"
            shift 2
            ;;
        --duration|-d)
            DURATION="$2"
            shift 2
            ;;
        --server|-s)
            JITSI_SERVER="$2"
            shift 2
            ;;
        *)
            OUTPUT_PATH="$1"
            shift
            ;;
    esac
done

if [ -z "$OUTPUT_PATH" ]; then
    echo "Usage: $0 <output_path> [--room <room_name>] [--duration <seconds>] [--server <jitsi_server>]"
    echo "Example: $0 ../telemetry-runs/2026-03-18/webrtc_run1 --duration 60"
    echo ""
    echo "Options:"
    echo "  --room, -r      Jitsi room name (default: random generated)"
    echo "  --duration, -d  Test duration in seconds (default: 60)"
    echo "  --server, -s    Jitsi server (default: meet.jit.si)"
    exit 1
fi

mkdir -p "$OUTPUT_PATH"

# Generate room name if not provided
if [ -z "$ROOM_NAME" ]; then
    ROOM_NAME="edgeric-test-$(date +%s)"
fi

cat > "$OUTPUT_PATH/experiment_description.txt" << EOF
Experiment: WebRTC QoE Test with EdgeRIC Metrics Collection
Date: $(date)
Duration: ${DURATION}s

Components:
- Jitsi Server: ${JITSI_SERVER}
- Room: ${ROOM_NAME}
- UE Namespace: ${UE_NAMESPACE}
- Metrics: EdgeRIC collector agent (collector.py)
- QoE Capture: Selenium-based WebRTC metrics capture

Output Files:
- webrtc_qoe.json: WebRTC QoE metrics (RTT, jitter, packet loss, bitrate)
- metrics_webrtc.json: EdgeRIC RAN metrics
- experiment_description.txt: This file

Captured Metrics:
- WebRTC Layer: RTT, jitter, packet loss, audio/video bitrate, frame rate, resolution
- RAN Layer: MAC, RLC, PDCP, GTP metrics
EOF

echo "Output directory: $OUTPUT_PATH"
echo "Duration: ${DURATION}s"
echo "Room: $ROOM_NAME"
echo "Server: $JITSI_SERVER"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting EdgeRIC collector..."
sudo "$SCRIPT_DIR/../venv/bin/python" "$SCRIPT_DIR/../collector.py" --json --output "$OUTPUT_PATH/metrics_webrtc.json" &
COLLECTOR_PID=$!

sleep 2

# Setup namespace for Chrome (loopback + DNS + default route)
echo "Setting up $UE_NAMESPACE namespace for Chrome..."
sudo ip netns exec "$UE_NAMESPACE" ip link set lo up 2>/dev/null || true
sudo ip netns exec "$UE_NAMESPACE" ip route add default via 10.45.0.1 2>/dev/null || true
sudo mkdir -p /etc/netns/"$UE_NAMESPACE"
echo "nameserver 8.8.8.8" | sudo tee /etc/netns/"$UE_NAMESPACE"/resolv.conf > /dev/null

echo "Starting WebRTC QoE capture in $UE_NAMESPACE namespace..."
echo "Join the meeting from another device to test bidirectional communication:"
echo "  https://${JITSI_SERVER}/${ROOM_NAME}"
echo ""

sudo ip netns exec "$UE_NAMESPACE" "$SCRIPT_DIR/../venv/bin/python" "$SCRIPT_DIR/capture_webrtc_qoe.py" \
    --room "$ROOM_NAME" \
    --server "$JITSI_SERVER" \
    --duration "$DURATION" \
    --interval "$INTERVAL_MS" \
    --output "$OUTPUT_PATH/webrtc_qoe.json" &
QOE_PID=$!

echo "Running for $DURATION seconds (plus startup time)..."

# Wait for QoE capture to finish
wait $QOE_PID 2>/dev/null

echo "Stopping collector..."
sudo kill -15 $COLLECTOR_PID 2>/dev/null

sleep 2

if ps -p $COLLECTOR_PID > /dev/null 2>&1; then
    echo "Collector still running, force killing..."
    sudo kill -9 $COLLECTOR_PID 2>/dev/null
fi

echo ""
echo "Done. Output files saved to: $OUTPUT_PATH"
echo "  - experiment_description.txt"
echo "  - webrtc_qoe.json"
echo "  - metrics_webrtc.json"
echo ""
echo "To plot results:"
echo "  python3 plotting/plot_dl_metrics.py $OUTPUT_PATH/metrics_webrtc.json --output webrtc"
echo "  python3 plotting/plot_webrtc_qoe.py $OUTPUT_PATH/webrtc_qoe.json --output webrtc"
