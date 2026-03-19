#!/bin/bash

DURATION=60
UE_NAMESPACE=ue1
VIDEO_URL=""
INTERVAL_MS=100
QUALITY=""

# Parse arguments
OUTPUT_PATH=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --video|-v)
            VIDEO_URL="$2"
            shift 2
            ;;
        --duration|-d)
            DURATION="$2"
            shift 2
            ;;
        --quality|-q)
            QUALITY="$2"
            shift 2
            ;;
        *)
            OUTPUT_PATH="$1"
            shift
            ;;
    esac
done

if [ -z "$OUTPUT_PATH" ] || [ -z "$VIDEO_URL" ]; then
    echo "Usage: $0 <output_path> --video <youtube_url> [--duration <seconds>] [--quality <level>]"
    echo "Example: $0 ../telemetry-runs/2026-03-18/youtube_run1 --video 'https://www.youtube.com/watch?v=VIDEO_ID' --duration 60"
    echo ""
    echo "Quality options: highest, hd2160, hd1440, hd1080, hd720, large, medium, small"
    echo "  Use --quality hd2160 to force 4K and stress-test network throughput"
    exit 1
fi

mkdir -p "$OUTPUT_PATH"

cat > "$OUTPUT_PATH/experiment_description.txt" << EOF
Experiment: YouTube QoE Test with EdgeRIC Metrics Collection
Date: $(date)
Duration: ${DURATION}s

Components:
- YouTube Video: ${VIDEO_URL}
- UE Namespace: ${UE_NAMESPACE}
- Metrics: EdgeRIC collector agent (collector.py)
- QoE Capture: Selenium-based YouTube metrics capture

Output Files:
- youtube_qoe.json: YouTube QoE metrics (100ms granularity)
- metrics_youtube.json: EdgeRIC RAN metrics
- experiment_description.txt: This file

Captured Metrics:
- Application Layer: bitrate, buffer level, quality, stalls, quality switches
- RAN Layer: MAC, RLC, PDCP, GTP metrics
EOF

echo "Output directory: $OUTPUT_PATH"
echo "Duration: ${DURATION}s"
echo "Video: $VIDEO_URL"
if [ -n "$QUALITY" ]; then
    echo "Forced quality: $QUALITY"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting EdgeRIC collector..."
sudo "$SCRIPT_DIR/../venv/bin/python" "$SCRIPT_DIR/../collector.py" --json --output "$OUTPUT_PATH/metrics_youtube.json" &
COLLECTOR_PID=$!

sleep 2

# Setup namespace for Chrome (loopback + DNS + default route)
echo "Setting up $UE_NAMESPACE namespace for Chrome..."
sudo ip netns exec "$UE_NAMESPACE" ip link set lo up 2>/dev/null || true
sudo ip netns exec "$UE_NAMESPACE" ip route add default via 10.45.0.1 2>/dev/null || true
sudo mkdir -p /etc/netns/"$UE_NAMESPACE"
echo "nameserver 8.8.8.8" | sudo tee /etc/netns/"$UE_NAMESPACE"/resolv.conf > /dev/null

echo "Starting YouTube QoE capture in $UE_NAMESPACE namespace..."

# Build quality argument if specified
QUALITY_ARG=""
if [ -n "$QUALITY" ]; then
    QUALITY_ARG="--quality $QUALITY"
    echo "Forcing quality: $QUALITY"
fi

sudo ip netns exec "$UE_NAMESPACE" "$SCRIPT_DIR/../venv/bin/python" "$SCRIPT_DIR/capture_youtube_qoe.py" \
    --video "$VIDEO_URL" \
    --duration "$DURATION" \
    --interval "$INTERVAL_MS" \
    --output "$OUTPUT_PATH/youtube_qoe.json" \
    $QUALITY_ARG &
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
echo "  - youtube_qoe.json"
echo "  - metrics_youtube.json"
echo ""
echo "To plot results:"
echo "  python3 plotting/plot_dl_metrics.py $OUTPUT_PATH/metrics_youtube.json --output youtube"
echo "  python3 plotting/plot_youtube_qoe.py $OUTPUT_PATH/youtube_qoe.json --output youtube"
