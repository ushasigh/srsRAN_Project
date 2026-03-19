#!/bin/bash
#
# Capture WebRTC QoE metrics between two UEs via Jitsi Meet
# Both UEs join the same room, creating a peer-to-peer WebRTC connection
#
# Usage:
#   sudo ./capture_webrtc_2ue.sh <output_path> [--duration <seconds>]
#
# Example:
#   sudo ./capture_webrtc_2ue.sh ../telemetry-runs/2026-03-18/webrtc_2ue_run1 --duration 60

DURATION=60
UE1_NAMESPACE=ue1
UE2_NAMESPACE=ue2
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
    echo "Usage: $0 <output_path> [--room <room_name>] [--duration <seconds>]"
    echo "Example: $0 ../telemetry-runs/2026-03-18/webrtc_2ue_run1 --duration 60"
    exit 1
fi

mkdir -p "$OUTPUT_PATH"

# Generate room name if not provided
if [ -z "$ROOM_NAME" ]; then
    ROOM_NAME="edgeric-2ue-$(date +%s)"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cat > "$OUTPUT_PATH/experiment_description.txt" << EOF
Experiment: WebRTC QoE Test - Two UEs via Jitsi Meet
Date: $(date)
Duration: ${DURATION}s

Components:
- Jitsi Server: ${JITSI_SERVER}
- Room: ${ROOM_NAME}
- UE1 Namespace: ${UE1_NAMESPACE}
- UE2 Namespace: ${UE2_NAMESPACE}
- Metrics: EdgeRIC collector agent (collector.py)
- QoE Capture: Selenium-based WebRTC metrics capture on both UEs

Output Files:
- webrtc_qoe_ue1.json: WebRTC QoE metrics from UE1
- webrtc_qoe_ue2.json: WebRTC QoE metrics from UE2
- metrics_webrtc.json: EdgeRIC RAN metrics
- experiment_description.txt: This file

Captured Metrics:
- WebRTC Layer: RTT, jitter, packet loss, audio/video bitrate, frame rate
- RAN Layer: MAC, RLC, PDCP, GTP metrics for both UEs
EOF

echo "============================================"
echo "WebRTC 2-UE Test"
echo "============================================"
echo "Output directory: $OUTPUT_PATH"
echo "Duration: ${DURATION}s"
echo "Room: $ROOM_NAME"
echo "Server: $JITSI_SERVER"
echo "UE1: $UE1_NAMESPACE"
echo "UE2: $UE2_NAMESPACE"
echo "============================================"
echo ""

# Setup both namespaces
echo "Setting up network namespaces..."

# UE1 setup
echo "  Configuring $UE1_NAMESPACE..."
sudo ip netns exec "$UE1_NAMESPACE" ip link set lo up 2>/dev/null || true
sudo ip netns exec "$UE1_NAMESPACE" ip route add default via 10.45.0.1 2>/dev/null || true
sudo mkdir -p /etc/netns/"$UE1_NAMESPACE"
echo "nameserver 8.8.8.8" | sudo tee /etc/netns/"$UE1_NAMESPACE"/resolv.conf > /dev/null

# UE2 setup
echo "  Configuring $UE2_NAMESPACE..."
sudo ip netns exec "$UE2_NAMESPACE" ip link set lo up 2>/dev/null || true
sudo ip netns exec "$UE2_NAMESPACE" ip route add default via 10.45.0.1 2>/dev/null || true
sudo mkdir -p /etc/netns/"$UE2_NAMESPACE"
echo "nameserver 8.8.8.8" | sudo tee /etc/netns/"$UE2_NAMESPACE"/resolv.conf > /dev/null

echo "  Done."
echo ""

# Start EdgeRIC collector
echo "Starting EdgeRIC collector..."
sudo "$SCRIPT_DIR/../venv/bin/python" "$SCRIPT_DIR/../collector.py" --json --output "$OUTPUT_PATH/metrics_webrtc.json" &
COLLECTOR_PID=$!
sleep 2

# Start UE1 WebRTC capture
echo "Starting WebRTC capture on $UE1_NAMESPACE..."
sudo ip netns exec "$UE1_NAMESPACE" "$SCRIPT_DIR/../venv/bin/python" "$SCRIPT_DIR/capture_webrtc_qoe.py" \
    --room "$ROOM_NAME" \
    --server "$JITSI_SERVER" \
    --duration "$DURATION" \
    --interval "$INTERVAL_MS" \
    --output "$OUTPUT_PATH/webrtc_qoe_ue1.json" &
UE1_PID=$!

# Wait a bit for UE1 to join the room first
sleep 5

# Start UE2 WebRTC capture
echo "Starting WebRTC capture on $UE2_NAMESPACE..."
sudo ip netns exec "$UE2_NAMESPACE" "$SCRIPT_DIR/../venv/bin/python" "$SCRIPT_DIR/capture_webrtc_qoe.py" \
    --room "$ROOM_NAME" \
    --server "$JITSI_SERVER" \
    --duration "$DURATION" \
    --interval "$INTERVAL_MS" \
    --output "$OUTPUT_PATH/webrtc_qoe_ue2.json" &
UE2_PID=$!

echo ""
echo "Both UEs are joining room: https://${JITSI_SERVER}/${ROOM_NAME}"
echo "Running for $DURATION seconds..."
echo ""

# Wait for both to finish
wait $UE1_PID 2>/dev/null
echo "UE1 capture completed."

wait $UE2_PID 2>/dev/null
echo "UE2 capture completed."

# Stop collector
echo "Stopping collector..."
sudo kill -15 $COLLECTOR_PID 2>/dev/null
sleep 2

if ps -p $COLLECTOR_PID > /dev/null 2>&1; then
    sudo kill -9 $COLLECTOR_PID 2>/dev/null
fi

echo ""
echo "============================================"
echo "Done. Output files saved to: $OUTPUT_PATH"
echo "============================================"
echo "  - experiment_description.txt"
echo "  - webrtc_qoe_ue1.json"
echo "  - webrtc_qoe_ue2.json"
echo "  - metrics_webrtc.json"
echo ""
echo "To plot results:"
echo "  python3 plotting/plot_dl_metrics.py $OUTPUT_PATH/metrics_webrtc.json --output webrtc"
echo "  python3 plotting/plot_webrtc_qoe.py $OUTPUT_PATH/webrtc_qoe_ue1.json --output webrtc_ue1"
echo "  python3 plotting/plot_webrtc_qoe.py $OUTPUT_PATH/webrtc_qoe_ue2.json --output webrtc_ue2"
