#!/usr/bin/env python3
"""
EdgeRIC MCS Controller - Dynamic MCS Control via ZMQ

This script allows you to dynamically set the MCS (Modulation and Coding Scheme)
for specific UEs. The gNB will use the overridden MCS instead of link adaptation.

NOTE: The MCS control protocol maps MCS values by UE order (sorted by RNTI).
This controller subscribes to metrics to learn active UEs and their order.

Usage:
    python3 mcs_controller.py --interactive
    python3 mcs_controller.py --rnti 17921 --mcs 20
"""

import zmq
import time
import sys
import argparse
import threading
from collections import OrderedDict

# Add parent directory to path for protobuf imports
sys.path.insert(0, '..')

# Import generated protobufs
import control_mcs_pb2
import metrics_pb2


class McsController:
    """MCS Controller that tracks active UEs and sends MCS overrides."""
    
    def __init__(self, 
                 mcs_ipc="ipc:///tmp/control_mcs",
                 metrics_ipc="ipc:///tmp/metrics_data"):
        """Initialize MCS controller with ZMQ sockets."""
        self.context = zmq.Context()
        
        # Publisher for MCS control
        self.mcs_socket = self.context.socket(zmq.PUB)
        self.mcs_socket.bind(mcs_ipc)
        
        # Subscriber for metrics (to learn active UEs)
        self.metrics_socket = self.context.socket(zmq.SUB)
        self.metrics_socket.setsockopt(zmq.CONFLATE, 1)
        self.metrics_socket.setsockopt_string(zmq.SUBSCRIBE, "")
        self.metrics_socket.connect(metrics_ipc)
        
        self.ran_index = 0
        
        # Track active UEs: {rnti: last_seen_tti}
        self.active_ues = OrderedDict()
        
        # MCS overrides per RNTI: {rnti: mcs_value}
        self.mcs_overrides = {}
        
        # Background thread for metrics
        self._running = True
        self._metrics_thread = threading.Thread(target=self._metrics_listener, daemon=True)
        self._metrics_thread.start()
        
        # Give time for connection to establish
        time.sleep(0.5)
        print(f"MCS Controller bound to {mcs_ipc}")
        print(f"Listening for metrics on {metrics_ipc}")
    
    def _metrics_listener(self):
        """Background thread to listen for metrics and track active UEs."""
        while self._running:
            try:
                data = self.metrics_socket.recv(flags=zmq.NOBLOCK)
                tti_msg = metrics_pb2.TtiMetrics()
                tti_msg.ParseFromString(data)
                
                # Update active UEs (sorted by RNTI)
                for ue in tti_msg.ues:
                    self.active_ues[ue.rnti] = tti_msg.tti_index
                
                # Keep sorted by RNTI (this is how gNB orders them)
                self.active_ues = OrderedDict(sorted(self.active_ues.items()))
                
            except zmq.Again:
                pass  # No message available
            except Exception as e:
                print(f"Metrics listener error: {e}")
            
            time.sleep(0.001)  # 1ms poll interval
    
    def get_active_ues(self):
        """Get list of active UEs (sorted by RNTI)."""
        return list(self.active_ues.keys())
    
    def set_mcs(self, rnti: int, mcs: int):
        """
        Set MCS override for a specific UE.
        
        Args:
            rnti: UE RNTI
            mcs: MCS index (0-28 for 5G NR)
        """
        if mcs < 0 or mcs > 28:
            print(f"Warning: MCS {mcs} out of range [0-28], clamping")
            mcs = max(0, min(28, mcs))
        
        self.mcs_overrides[rnti] = mcs
        self._send_mcs_update()
        print(f"Set MCS={mcs} for RNTI={rnti}")
    
    def clear_mcs(self, rnti: int):
        """Clear MCS override for a specific UE (revert to link adaptation)."""
        if rnti in self.mcs_overrides:
            del self.mcs_overrides[rnti]
            self._send_mcs_update()
            print(f"Cleared MCS override for RNTI={rnti}")
        else:
            print(f"No override exists for RNTI={rnti}")
    
    def clear_all(self):
        """Clear all MCS overrides."""
        self.mcs_overrides.clear()
        self._send_mcs_update()
        print("Cleared all MCS overrides")
    
    def set_all_ues(self, mcs: int):
        """Set the same MCS for all active UEs."""
        for rnti in self.active_ues.keys():
            self.mcs_overrides[rnti] = mcs
        self._send_mcs_update()
        print(f"Set MCS={mcs} for all {len(self.active_ues)} active UEs")
    
    def _send_mcs_update(self):
        """Send MCS control message with current overrides."""
        msg = control_mcs_pb2.mcs_control()
        msg.ran_index = self.ran_index
        self.ran_index += 1
        
        # Build MCS array in RNTI order (matching gNB's mac_ue iteration)
        # UEs without override get MCS=255 (special value meaning "no override")
        for rnti in sorted(self.active_ues.keys()):
            if rnti in self.mcs_overrides:
                msg.mcs.append(float(self.mcs_overrides[rnti]))
            else:
                msg.mcs.append(255.0)  # No override - use link adaptation
        
        # Serialize and send
        serialized = msg.SerializeToString()
        self.mcs_socket.send(serialized)
    
    def show_status(self):
        """Show current active UEs and MCS overrides."""
        print("\n=== MCS Controller Status ===")
        print(f"Active UEs: {len(self.active_ues)}")
        
        if not self.active_ues:
            print("  (waiting for UEs...)")
        else:
            for rnti in self.active_ues.keys():
                mcs = self.mcs_overrides.get(rnti, None)
                if mcs is not None:
                    print(f"  RNTI {rnti}: MCS={mcs} (override)")
                else:
                    print(f"  RNTI {rnti}: MCS=auto (link adaptation)")
        print()
    
    def close(self):
        """Clean up resources."""
        self._running = False
        self._metrics_thread.join(timeout=1.0)
        self.mcs_socket.close()
        self.metrics_socket.close()
        self.context.term()


def interactive_mode(controller):
    """Interactive mode for testing MCS control."""
    print("\n=== EdgeRIC MCS Controller - Interactive Mode ===")
    print("Commands:")
    print("  set <rnti> <mcs>     - Set MCS for a UE (0-28)")
    print("  setall <mcs>         - Set MCS for all active UEs")
    print("  clear <rnti>         - Clear MCS override for a UE")
    print("  clearall             - Clear all MCS overrides")
    print("  status / list        - Show active UEs and overrides")
    print("  quit                 - Exit")
    print()
    
    while True:
        try:
            cmd = input("mcs> ").strip().split()
            if not cmd:
                continue
            
            if cmd[0] in ('quit', 'exit', 'q'):
                break
            
            elif cmd[0] == 'set':
                if len(cmd) < 3:
                    print("Usage: set <rnti> <mcs>")
                    continue
                rnti, mcs = int(cmd[1]), int(cmd[2])
                controller.set_mcs(rnti, mcs)
            
            elif cmd[0] == 'setall':
                if len(cmd) < 2:
                    print("Usage: setall <mcs>")
                    continue
                mcs = int(cmd[1])
                controller.set_all_ues(mcs)
            
            elif cmd[0] == 'clear':
                if len(cmd) < 2:
                    print("Usage: clear <rnti>")
                    continue
                rnti = int(cmd[1])
                controller.clear_mcs(rnti)
            
            elif cmd[0] == 'clearall':
                controller.clear_all()
            
            elif cmd[0] in ('status', 'list', 'ls', 's'):
                controller.show_status()
            
            else:
                print(f"Unknown command: {cmd[0]}")
        
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except ValueError as e:
            print(f"Invalid value: {e}")
        except Exception as e:
            print(f"Error: {e}")


def main():
    parser = argparse.ArgumentParser(description='EdgeRIC MCS Controller')
    parser.add_argument('--mcs-ipc', default='ipc:///tmp/control_mcs',
                        help='IPC path for MCS control socket')
    parser.add_argument('--metrics-ipc', default='ipc:///tmp/metrics_data',
                        help='IPC path for metrics subscription')
    parser.add_argument('--rnti', type=int, help='UE RNTI')
    parser.add_argument('--mcs', type=int, help='MCS index (0-28)')
    parser.add_argument('--clear', action='store_true', help='Clear MCS override')
    parser.add_argument('--interactive', '-i', action='store_true',
                        help='Interactive mode')
    
    args = parser.parse_args()
    
    controller = McsController(args.mcs_ipc, args.metrics_ipc)
    
    try:
        if args.interactive:
            interactive_mode(controller)
        elif args.rnti is not None:
            if args.clear:
                controller.clear_mcs(args.rnti)
            elif args.mcs is not None:
                controller.set_mcs(args.rnti, args.mcs)
            else:
                print("Error: --mcs required with --rnti")
        else:
            # Default to interactive mode
            interactive_mode(controller)
    finally:
        controller.close()


if __name__ == '__main__':
    main()
