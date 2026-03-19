ssh wcsng5g@137.110.111.11 -p 22
sudo tcpdump -i ogstun host 10.45.0.8 -w - -U | nc 137.110.198.151 5000

#!/bin/bash

DURATION=20
SERVER=10.45.0.2
PORT=5201

echo "Starting collector..."
sudo ./venv/bin/python collector.py --json --output metrics.json &
COLLECTOR_PID=$!

echo "Starting tcpdump..."
sudo tcpdump -i any -w iperf_tcp.pcap tcp and host $SERVER and port $PORT &
TCPDUMP_PID=$!

echo "Running for $DURATION seconds..."
sleep $DURATION

echo "Stopping tcpdump..."
sudo kill -2 $TCPDUMP_PID

echo "Stopping collector..."
sudo kill -15 $COLLECTOR_PID

sleep 2

# force kill if still alive
if ps -p $COLLECTOR_PID > /dev/null; then
    echo "Collector still running, force killing..."
    sudo kill -9 $COLLECTOR_PID
fi

echo "Done."