#!/usr/bin/env python3
"""
EdgeRIC QoS Random Sender - Sends random QoS updates every 200ms

This script sends random QoS parameter updates for RNTI 17922 and 17923, LCID 4.
"""

import zmq
import time
import random
import sys

# Import the generated protobuf
import control_qos_pb2


def main():
    # ZMQ setup
    context = zmq.Context()
    socket = context.socket(zmq.PUB)
    socket.bind("ipc:///tmp/control_qos_actions")
    
    # Give time for connection to establish
    time.sleep(0.5)
    print("QoS Random Sender started - sending updates every 200ms")
    print("Target UEs: RNTI 17922 and 17923, LCID 4")
    print("Press Ctrl+C to stop\n")
    
    ran_index = 0
    
    # Define ranges for random values
    QOS_PRIO_RANGE = (1, 127)      # QoS priority: 1 (highest) to 127 (lowest)
    ARP_PRIO_RANGE = (1, 15)       # ARP priority: 1 (highest) to 15 (lowest)
    PDB_RANGE = (10, 300)          # Packet Delay Budget: 10ms to 300ms
    GBR_DL_RANGE = (1, 50)         # GBR DL: 1 Mbps to 50 Mbps
    GBR_UL_RANGE = (1, 20)         # GBR UL: 1 Mbps to 20 Mbps
    
    try:
        while True:
            # Create QoS control message
            msg = control_qos_pb2.QosControl()
            msg.ran_index = ran_index
            
            # Generate random QoS for RNTI 17922
            drb1 = msg.drb_qos.add()
            drb1.rnti = 17922
            drb1.lcid = 4
            drb1.qos_priority = random.randint(*QOS_PRIO_RANGE)
            drb1.arp_priority = random.randint(*ARP_PRIO_RANGE)
            drb1.pdb_ms = random.randint(*PDB_RANGE)
            drb1.gbr_dl = random.randint(*GBR_DL_RANGE) * 1_000_000  # Convert to bps
            drb1.gbr_ul = random.randint(*GBR_UL_RANGE) * 1_000_000
            
            # Generate random QoS for RNTI 17923
            drb2 = msg.drb_qos.add()
            drb2.rnti = 17923
            drb2.lcid = 4
            drb2.qos_priority = random.randint(*QOS_PRIO_RANGE)
            drb2.arp_priority = random.randint(*ARP_PRIO_RANGE)
            drb2.pdb_ms = random.randint(*PDB_RANGE)
            drb2.gbr_dl = random.randint(*GBR_DL_RANGE) * 1_000_000
            drb2.gbr_ul = random.randint(*GBR_UL_RANGE) * 1_000_000
            
            # Send message
            socket.send(msg.SerializeToString())
            
            # Print what we sent
            print(f"[{ran_index:04d}] Sent QoS updates:")
            print(f"  RNTI=17922 LCID=4: qos_prio={drb1.qos_priority:3d} arp_prio={drb1.arp_priority:2d} "
                  f"pdb={drb1.pdb_ms:3d}ms gbr_dl={drb1.gbr_dl//1_000_000:2d}Mbps gbr_ul={drb1.gbr_ul//1_000_000:2d}Mbps")
            print(f"  RNTI=17923 LCID=4: qos_prio={drb2.qos_priority:3d} arp_prio={drb2.arp_priority:2d} "
                  f"pdb={drb2.pdb_ms:3d}ms gbr_dl={drb2.gbr_dl//1_000_000:2d}Mbps gbr_ul={drb2.gbr_ul//1_000_000:2d}Mbps")
            print()
            
            ran_index += 1
            time.sleep(0.2)  # 200ms
            
    except KeyboardInterrupt:
        print("\nStopping QoS Random Sender...")
    finally:
        socket.close()
        context.term()
        print("Done.")


if __name__ == '__main__':
    main()
