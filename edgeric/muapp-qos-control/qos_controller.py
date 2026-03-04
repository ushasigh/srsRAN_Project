#!/usr/bin/env python3
"""
EdgeRIC QoS Controller - Dynamic QoS Control via ZMQ

This script allows you to dynamically change QoS parameters (priority, ARP, PDB, GBR)
for specific DRBs (Data Radio Bearers) of specific UEs.

Usage:
    python3 qos_controller.py

The script connects to the gNB via IPC socket and sends QoS control messages.
"""

import zmq
import time
import sys
import argparse

# Import the generated protobuf
import control_qos_pb2

class QosController:
    def __init__(self, ipc_path="ipc:///tmp/control_qos_actions"):
        """Initialize the QoS controller with ZMQ publisher."""
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.bind(ipc_path)
        self.ran_index = 0
        
        # Give time for connection to establish
        time.sleep(0.5)
        print(f"QoS Controller bound to {ipc_path}")
    
    def send_qos_update(self, drb_updates: list):
        """
        Send QoS updates for multiple DRBs.
        
        Args:
            drb_updates: List of dicts, each with:
                - rnti: UE identifier (required)
                - lcid: Logical Channel ID (required)
                - qos_priority: QoS Priority Level (1-127, optional)
                - arp_priority: ARP Priority Level (1-15, optional)
                - pdb_ms: Packet Delay Budget in ms (optional)
                - gbr_dl: Guaranteed Bit Rate DL in bps (optional)
                - gbr_ul: Guaranteed Bit Rate UL in bps (optional)
                - clear: Set to True to clear override (optional)
        """
        msg = control_qos_pb2.QosControl()
        msg.ran_index = self.ran_index
        self.ran_index += 1
        
        for update in drb_updates:
            drb = msg.drb_qos.add()
            drb.rnti = update['rnti']
            drb.lcid = update['lcid']
            
            if update.get('clear', False):
                drb.clear_override = True
            else:
                if 'qos_priority' in update:
                    drb.qos_priority = update['qos_priority']
                if 'arp_priority' in update:
                    drb.arp_priority = update['arp_priority']
                if 'pdb_ms' in update:
                    drb.pdb_ms = update['pdb_ms']
                if 'gbr_dl' in update:
                    drb.gbr_dl = update['gbr_dl']
                if 'gbr_ul' in update:
                    drb.gbr_ul = update['gbr_ul']
        
        # Serialize and send
        serialized = msg.SerializeToString()
        self.socket.send(serialized)
        print(f"Sent QoS update (ran_index={msg.ran_index - 1}): {len(drb_updates)} DRB(s)")
    
    def set_priority(self, rnti: int, lcid: int, qos_priority: int, arp_priority: int = None):
        """Set priority for a specific DRB."""
        update = {'rnti': rnti, 'lcid': lcid, 'qos_priority': qos_priority}
        if arp_priority is not None:
            update['arp_priority'] = arp_priority
        self.send_qos_update([update])
    
    def set_pdb(self, rnti: int, lcid: int, pdb_ms: int):
        """Set Packet Delay Budget for a specific DRB."""
        self.send_qos_update([{'rnti': rnti, 'lcid': lcid, 'pdb_ms': pdb_ms}])
    
    def set_gbr(self, rnti: int, lcid: int, gbr_dl: int, gbr_ul: int = None):
        """Set Guaranteed Bit Rate for a specific DRB."""
        update = {'rnti': rnti, 'lcid': lcid, 'gbr_dl': gbr_dl}
        if gbr_ul is not None:
            update['gbr_ul'] = gbr_ul
        self.send_qos_update([update])
    
    def clear_override(self, rnti: int, lcid: int):
        """Clear QoS override for a specific DRB (revert to static config)."""
        self.send_qos_update([{'rnti': rnti, 'lcid': lcid, 'clear': True}])
    
    def close(self):
        """Clean up resources."""
        self.socket.close()
        self.context.term()


def interactive_mode(controller):
    """Interactive mode for testing QoS control."""
    print("\n=== EdgeRIC QoS Controller - Interactive Mode ===")
    print("Commands:")
    print("  priority <rnti> <lcid> <qos_prio> [arp_prio]  - Set priority")
    print("  pdb <rnti> <lcid> <pdb_ms>                    - Set Packet Delay Budget")
    print("  gbr <rnti> <lcid> <gbr_dl_mbps> [gbr_ul_mbps] - Set GBR (in Mbps)")
    print("  clear <rnti> <lcid>                          - Clear override")
    print("  example                                       - Send example updates")
    print("  quit                                          - Exit")
    print()
    
    while True:
        try:
            cmd = input("qos> ").strip().split()
            if not cmd:
                continue
            
            if cmd[0] == 'quit' or cmd[0] == 'exit':
                break
            
            elif cmd[0] == 'priority':
                if len(cmd) < 4:
                    print("Usage: priority <rnti> <lcid> <qos_prio> [arp_prio]")
                    continue
                rnti, lcid, qos_prio = int(cmd[1]), int(cmd[2]), int(cmd[3])
                arp_prio = int(cmd[4]) if len(cmd) > 4 else None
                controller.set_priority(rnti, lcid, qos_prio, arp_prio)
                print(f"  -> Set priority for RNTI={rnti}, LCID={lcid}: qos={qos_prio}, arp={arp_prio}")
            
            elif cmd[0] == 'pdb':
                if len(cmd) < 4:
                    print("Usage: pdb <rnti> <lcid> <pdb_ms>")
                    continue
                rnti, lcid, pdb_ms = int(cmd[1]), int(cmd[2]), int(cmd[3])
                controller.set_pdb(rnti, lcid, pdb_ms)
                print(f"  -> Set PDB for RNTI={rnti}, LCID={lcid}: {pdb_ms}ms")
            
            elif cmd[0] == 'gbr':
                if len(cmd) < 4:
                    print("Usage: gbr <rnti> <lcid> <gbr_dl_mbps> [gbr_ul_mbps]")
                    continue
                rnti, lcid = int(cmd[1]), int(cmd[2])
                gbr_dl = int(float(cmd[3]) * 1_000_000)  # Convert Mbps to bps
                gbr_ul = int(float(cmd[4]) * 1_000_000) if len(cmd) > 4 else None
                controller.set_gbr(rnti, lcid, gbr_dl, gbr_ul)
                print(f"  -> Set GBR for RNTI={rnti}, LCID={lcid}: DL={gbr_dl/1e6}Mbps, UL={gbr_ul/1e6 if gbr_ul else 'N/A'}Mbps")
            
            elif cmd[0] == 'clear':
                if len(cmd) < 3:
                    print("Usage: clear <rnti> <lcid>")
                    continue
                rnti, lcid = int(cmd[1]), int(cmd[2])
                controller.clear_override(rnti, lcid)
                print(f"  -> Cleared override for RNTI={rnti}, LCID={lcid}")
            
            elif cmd[0] == 'example':
                # Example: Set QoS for two DRBs of UE with RNTI 17921
                print("Sending example QoS updates...")
                controller.send_qos_update([
                    {
                        'rnti': 17921,
                        'lcid': 4,  # DRB1 (e.g., Voice)
                        'qos_priority': 1,
                        'arp_priority': 1,
                        'pdb_ms': 20,
                    },
                    {
                        'rnti': 17921,
                        'lcid': 5,  # DRB2 (e.g., Video)
                        'qos_priority': 20,
                        'gbr_dl': 10_000_000,  # 10 Mbps
                        'gbr_ul': 2_000_000,   # 2 Mbps
                    },
                    {
                        'rnti': 17921,
                        'lcid': 6,  # DRB3 (e.g., Data)
                        'qos_priority': 80,
                    },
                ])
                print("  -> Sent example updates for RNTI=17921, LCIDs 4, 5, 6")
            
            else:
                print(f"Unknown command: {cmd[0]}")
        
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")


def main():
    parser = argparse.ArgumentParser(description='EdgeRIC QoS Controller')
    parser.add_argument('--ipc', default='ipc:///tmp/control_qos_actions',
                        help='IPC path for ZMQ socket')
    parser.add_argument('--rnti', type=int, help='UE RNTI')
    parser.add_argument('--lcid', type=int, help='Logical Channel ID')
    parser.add_argument('--qos-priority', type=int, help='QoS Priority (1-127)')
    parser.add_argument('--arp-priority', type=int, help='ARP Priority (1-15)')
    parser.add_argument('--pdb-ms', type=int, help='Packet Delay Budget in ms')
    parser.add_argument('--gbr-dl-mbps', type=float, help='GBR DL in Mbps')
    parser.add_argument('--gbr-ul-mbps', type=float, help='GBR UL in Mbps')
    parser.add_argument('--clear', action='store_true', help='Clear override')
    parser.add_argument('--interactive', '-i', action='store_true',
                        help='Interactive mode')
    
    args = parser.parse_args()
    
    controller = QosController(args.ipc)
    
    try:
        if args.interactive:
            interactive_mode(controller)
        elif args.rnti is not None and args.lcid is not None:
            # Command-line mode
            update = {'rnti': args.rnti, 'lcid': args.lcid}
            
            if args.clear:
                update['clear'] = True
            else:
                if args.qos_priority is not None:
                    update['qos_priority'] = args.qos_priority
                if args.arp_priority is not None:
                    update['arp_priority'] = args.arp_priority
                if args.pdb_ms is not None:
                    update['pdb_ms'] = args.pdb_ms
                if args.gbr_dl_mbps is not None:
                    update['gbr_dl'] = int(args.gbr_dl_mbps * 1_000_000)
                if args.gbr_ul_mbps is not None:
                    update['gbr_ul'] = int(args.gbr_ul_mbps * 1_000_000)
            
            controller.send_qos_update([update])
            print("QoS update sent!")
        else:
            # Default to interactive mode if no arguments
            interactive_mode(controller)
    finally:
        controller.close()


if __name__ == '__main__':
    main()
