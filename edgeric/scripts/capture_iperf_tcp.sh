#!/bin/bash
# sudo ./capture_iperf_udp.sh ../telemetry-runs/2026-03-18/run7 --dump

DURATION=60
IPERF_SERVER=10.45.0.1
IPERF_PORT=5202
IPERF_INTERVAL=0.1
UE_NAMESPACE=ue2

# Remote tcpdump settings
REMOTE_HOST="wcsng5g@137.110.111.11"
REMOTE_SSH_PORT=22
REMOTE_IFACE="ogstun"
TCPDUMP_HOST="10.45.0.8"
LOCAL_IP="137.110.198.151"
NC_PORT=5050

# Parse arguments
ENABLE_DUMP=false
OUTPUT_PATH=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --dump|-d)
            ENABLE_DUMP=true
            shift
            ;;
        *)
            OUTPUT_PATH="$1"
            shift
            ;;
    esac
done

if [ -z "$OUTPUT_PATH" ]; then
    echo "Usage: $0 <output_path> [--dump|-d]"
    echo "Example: $0 ../telemetry-runs/2026-03-18/run6"
    echo "         $0 ../telemetry-runs/2026-03-18/run6 --dump"
    echo ""
    echo "Options:"
    echo "  --dump, -d    Enable remote tcpdump capture"
    exit 1
fi

mkdir -p "$OUTPUT_PATH"

if [ "$ENABLE_DUMP" = true ]; then
    DUMP_STATUS="Enabled"
    DUMP_FILES="- capture.pcap: tcpdump capture from remote host (${TCPDUMP_HOST})"
    DUMP_CONFIG="- Remote tcpdump host: ${REMOTE_HOST}"
else
    DUMP_STATUS="Disabled"
    DUMP_FILES=""
    DUMP_CONFIG=""
fi

cat > "$OUTPUT_PATH/experiment_description.txt" << EOF
Experiment: TCP iPerf Test with EdgeRIC Metrics Collection
Date: $(date)
Duration: ${DURATION}s
tcpdump: ${DUMP_STATUS}

Components:
- iPerf3 TCP: sudo ip netns exec ${UE_NAMESPACE} iperf3 -c ${IPERF_SERVER} -p ${IPERF_PORT} -i ${IPERF_INTERVAL} -t ${DURATION} -R
- Metrics: EdgeRIC collector agent (collector.py)
${ENABLE_DUMP:+- tcpdump: Remote capture from ${REMOTE_HOST} on ${REMOTE_IFACE} interface}

Output Files:
- iperf_tcp.txt: iPerf3 TCP output from ${UE_NAMESPACE} namespace
- metrics_tcp.json: EdgeRIC metrics collected during the TCP test
${DUMP_FILES}

Test Configuration:
- UE namespace: ${UE_NAMESPACE}
- iPerf server: ${IPERF_SERVER}:${IPERF_PORT}
- Direction: Reverse (-R, server to client = downlink)
- Report interval: ${IPERF_INTERVAL}s
- Protocol: TCP
${DUMP_CONFIG}
EOF

echo "Output directory: $OUTPUT_PATH"
echo "Duration: ${DURATION}s"
echo "tcpdump: $DUMP_STATUS"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ORIGINAL_USER="${SUDO_USER:-$USER}"

if [ "$ENABLE_DUMP" = true ]; then
    echo "Starting local netcat listener for tcpdump..."
    nc -l -p $NC_PORT > "$OUTPUT_PATH/capture.pcap" &
    NC_PID=$!
    sleep 1

    echo "Starting remote tcpdump via SSH (as $ORIGINAL_USER)..."
    sudo -u "$ORIGINAL_USER" ssh -p $REMOTE_SSH_PORT $REMOTE_HOST "sudo tcpdump -i $REMOTE_IFACE host $TCPDUMP_HOST -B 65536 -w - -U | nc $LOCAL_IP $NC_PORT" &
    SSH_PID=$!
    sleep 2
fi

echo "Starting EdgeRIC collector..."
sudo "$SCRIPT_DIR/../venv/bin/python" "$SCRIPT_DIR/../collector.py" --json --output "$OUTPUT_PATH/metrics_tcp.json" &
COLLECTOR_PID=$!

sleep 2

echo "Starting iPerf3 TCP test..."
sudo ip netns exec "$UE_NAMESPACE" iperf3 -c "$IPERF_SERVER" -p "$IPERF_PORT" -i "$IPERF_INTERVAL" -t "$DURATION" -R > "$OUTPUT_PATH/iperf_tcp.txt" 2>&1 &
IPERF_PID=$!

echo "Running for $DURATION seconds..."
sleep $DURATION

echo "Stopping iPerf..."
sudo kill -2 $IPERF_PID 2>/dev/null

sleep 2

echo "Stopping collector..."
sudo kill -15 $COLLECTOR_PID 2>/dev/null

if [ "$ENABLE_DUMP" = true ]; then
    echo "Stopping remote tcpdump..."
    sudo -u "$ORIGINAL_USER" ssh -p $REMOTE_SSH_PORT $REMOTE_HOST "sudo pkill -2 tcpdump" 2>/dev/null
    kill $SSH_PID 2>/dev/null
    kill $NC_PID 2>/dev/null
fi

sleep 2

if ps -p $COLLECTOR_PID > /dev/null 2>&1; then
    echo "Collector still running, force killing..."
    sudo kill -9 $COLLECTOR_PID 2>/dev/null
fi

if ps -p $IPERF_PID > /dev/null 2>&1; then
    echo "iPerf still running, force killing..."
    sudo kill -9 $IPERF_PID 2>/dev/null
fi

echo ""
echo "Done. Output files saved to: $OUTPUT_PATH"
echo "  - experiment_description.txt"
echo "  - iperf_tcp.txt"
echo "  - metrics_tcp.json"
if [ "$ENABLE_DUMP" = true ]; then
    echo "  - capture.pcap"
fi
