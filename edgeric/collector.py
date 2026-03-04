#!/usr/bin/env python3
"""
EdgeRIC Metrics Collector Agent

Subscribes to real-time metrics from srsRAN gNB and displays them.
Uses ZMQ conflate mode to always get the latest metrics (no queueing).

Usage:
    python3 collector.py [--json] [--quiet]
"""

import zmq
import argparse
import json
import sys
from datetime import datetime

# Import generated protobuf
import metrics_pb2

# ANSI colors for terminal output
class C:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    # Colors
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    # Background
    BG_BLUE = '\033[44m'

def fmt_bytes(num_bytes):
    """Format bytes to human readable"""
    if num_bytes < 1024:
        return f"{num_bytes}B"
    elif num_bytes < 1024 * 1024:
        return f"{num_bytes/1024:.1f}KB"
    else:
        return f"{num_bytes/(1024*1024):.2f}MB"

def fmt_rate(bytes_per_tti):
    """Format throughput (bytes/TTI to Mbps)"""
    # 1 TTI = 1ms, so bytes/TTI * 8 * 1000 = bps
    bps = bytes_per_tti * 8 * 1000
    if bps < 1e6:
        return f"{bps/1e3:.0f}Kbps"
    else:
        return f"{bps/1e6:.1f}Mbps"

def fmt_latency_ns(ns):
    """Format nanoseconds"""
    if ns == 0:
        return "-"
    elif ns < 1000:
        return f"{ns}ns"
    elif ns < 1000000:
        return f"{ns/1000:.1f}us"
    else:
        return f"{ns/1000000:.2f}ms"

def fmt_latency_us(us):
    """Format microseconds"""
    if us == 0:
        return "-"
    elif us < 1000:
        return f"{us}us"
    else:
        return f"{us/1000:.2f}ms"

def print_tti_metrics(tti_msg, quiet=False):
    """Pretty print TTI metrics with categorization"""
    timestamp = datetime.fromtimestamp(tti_msg.timestamp_us / 1e6)
    
    # Header
    print(f"\n{C.BOLD}{C.BG_BLUE}{C.WHITE} TTI {tti_msg.tti_index:05d} │ {timestamp.strftime('%H:%M:%S.%f')[:-3]} │ {len(tti_msg.ues)} UE(s) {C.RESET}")
    
    if len(tti_msg.ues) == 0:
        print(f"{C.DIM}  No active UEs{C.RESET}")
        return
    
    for ue in tti_msg.ues:
        mac = ue.mac
        
        # ═══════════════════════════════════════════════════════════════
        # UE Header
        # ═══════════════════════════════════════════════════════════════
        print(f"\n{C.BOLD}{C.CYAN}╔══ UE RNTI {ue.rnti} (0x{ue.rnti:04X}) ══════════════════════════════════════════{C.RESET}")
        
        # ───────────────────────────────────────────────────────────────
        # MAC Layer (UE Aggregate)
        # ───────────────────────────────────────────────────────────────
        print(f"{C.CYAN}║{C.RESET} {C.BOLD}{C.GREEN}▸ MAC Layer{C.RESET}")
        
        # Channel Quality
        print(f"{C.CYAN}║{C.RESET}   {C.DIM}Channel:{C.RESET}  CQI={C.YELLOW}{mac.cqi:2d}{C.RESET}  SNR={C.YELLOW}{mac.snr:5.1f}dB{C.RESET}")
        
        # Buffers
        print(f"{C.CYAN}║{C.RESET}   {C.DIM}Buffers:{C.RESET}  DL={fmt_bytes(mac.dl_buffer):>8s}  UL={fmt_bytes(mac.ul_buffer):>8s}")
        
        # Scheduling (TBS, MCS, PRBs)
        print(f"{C.CYAN}║{C.RESET}   {C.DIM}DL Sched:{C.RESET} TBS={mac.dl_tbs:5d}  MCS={C.YELLOW}{mac.dl_mcs:2d}{C.RESET}  PRBs={C.YELLOW}{mac.dl_prbs:3d}{C.RESET}  Rate={fmt_rate(mac.dl_tbs)}")
        print(f"{C.CYAN}║{C.RESET}   {C.DIM}UL Sched:{C.RESET} TBS={mac.ul_tbs:5d}  MCS={C.YELLOW}{mac.ul_mcs:2d}{C.RESET}  PRBs={C.YELLOW}{mac.ul_prbs:3d}{C.RESET}  Rate={fmt_rate(mac.ul_tbs)}")
        
        # HARQ
        dl_total = mac.dl_harq_ack + mac.dl_harq_nack
        ul_total = mac.ul_crc_ok + mac.ul_crc_fail
        dl_bler = (mac.dl_harq_nack / dl_total * 100) if dl_total > 0 else 0
        ul_bler = (mac.ul_crc_fail / ul_total * 100) if ul_total > 0 else 0
        harq_color = C.GREEN if dl_bler < 10 and ul_bler < 10 else C.RED
        print(f"{C.CYAN}║{C.RESET}   {C.DIM}HARQ:{C.RESET}     DL ACK/NACK={mac.dl_harq_ack}/{mac.dl_harq_nack} ({harq_color}{dl_bler:.0f}%BLER{C.RESET})  "
              f"UL OK/FAIL={mac.ul_crc_ok}/{mac.ul_crc_fail} ({harq_color}{ul_bler:.0f}%BLER{C.RESET})")
        
        if quiet:
            print(f"{C.CYAN}╚{'═'*60}{C.RESET}")
            continue
        
        # ───────────────────────────────────────────────────────────────
        # Per-DRB Metrics (RLC + PDCP)
        # ───────────────────────────────────────────────────────────────
        # Get all LCIDs from RLC and PDCP
        drb_lcids = set()
        for rlc in ue.rlc_drb:
            if rlc.lcid >= 4:  # Only DRBs
                drb_lcids.add(rlc.lcid)
        for pdcp in ue.pdcp_drb:
            drb_lcids.add(pdcp.lcid)
        
        if drb_lcids:
            print(f"{C.CYAN}║{C.RESET}")
            print(f"{C.CYAN}║{C.RESET} {C.BOLD}{C.BLUE}▸ Per-DRB Metrics{C.RESET}")
            
            for lcid in sorted(drb_lcids):
                drb_id = lcid - 3
                print(f"{C.CYAN}║{C.RESET}   {C.BOLD}DRB {drb_id} (LCID {lcid}){C.RESET}")
                
                # RLC for this LCID
                for rlc in ue.rlc_drb:
                    if rlc.lcid == lcid:
                        print(f"{C.CYAN}║{C.RESET}     {C.MAGENTA}RLC:{C.RESET} Buf DL={fmt_bytes(rlc.dl_buffer):>8s} UL={fmt_bytes(rlc.ul_buffer):>8s}")
                        print(f"{C.CYAN}║{C.RESET}          TX {rlc.tx_sdus}SDU/{fmt_bytes(rlc.tx_sdu_bytes)} lat={fmt_latency_us(rlc.tx_sdu_latency_us)}")
                        print(f"{C.CYAN}║{C.RESET}          RX {rlc.rx_sdus}SDU/{fmt_bytes(rlc.rx_sdu_bytes)} lost={rlc.rx_lost_pdus}")
                        break
                
                # PDCP for this LCID
                for pdcp in ue.pdcp_drb:
                    if pdcp.lcid == lcid:
                        print(f"{C.CYAN}║{C.RESET}     {C.GREEN}PDCP:{C.RESET} TX {pdcp.tx_pdus}PDU/{fmt_bytes(pdcp.tx_pdu_bytes)} drop={pdcp.tx_dropped_sdus} discard={pdcp.tx_discard_timeouts} lat={fmt_latency_ns(pdcp.tx_pdu_latency_ns)}")
                        print(f"{C.CYAN}║{C.RESET}           RX {pdcp.rx_pdus}PDU/{fmt_bytes(pdcp.rx_pdu_bytes)} drop={pdcp.rx_dropped_pdus} lat={fmt_latency_ns(pdcp.rx_sdu_latency_ns)}")
                        break
        
        # ───────────────────────────────────────────────────────────────
        # GTP-U (Per UE)
        # ───────────────────────────────────────────────────────────────
        gtp = ue.gtp
        if gtp.dl_pkts > 0 or gtp.ul_pkts > 0:
            print(f"{C.CYAN}║{C.RESET}")
            print(f"{C.CYAN}║{C.RESET} {C.BOLD}{C.RED}▸ GTP-U (N3 Interface){C.RESET}")
            print(f"{C.CYAN}║{C.RESET}   DL: {gtp.dl_pkts:6d} pkts / {fmt_bytes(gtp.dl_bytes):>10s}")
            print(f"{C.CYAN}║{C.RESET}   UL: {gtp.ul_pkts:6d} pkts / {fmt_bytes(gtp.ul_bytes):>10s}")
        
        print(f"{C.CYAN}╚{'═'*60}{C.RESET}")

def print_json(tti_msg):
    """Print metrics as JSON"""
    data = {
        "tti_index": tti_msg.tti_index,
        "timestamp_us": tti_msg.timestamp_us,
        "ues": []
    }
    
    for ue in tti_msg.ues:
        ue_data = {
            "rnti": ue.rnti,
            "mac": {
                "cqi": ue.mac.cqi,
                "snr": ue.mac.snr,
                "dl_buffer": ue.mac.dl_buffer,
                "ul_buffer": ue.mac.ul_buffer,
                "dl_tbs": ue.mac.dl_tbs,
                "ul_tbs": ue.mac.ul_tbs,
                "dl_mcs": ue.mac.dl_mcs,
                "ul_mcs": ue.mac.ul_mcs,
                "dl_prbs": ue.mac.dl_prbs,
                "ul_prbs": ue.mac.ul_prbs,
                "dl_harq_ack": ue.mac.dl_harq_ack,
                "dl_harq_nack": ue.mac.dl_harq_nack,
                "ul_crc_ok": ue.mac.ul_crc_ok,
                "ul_crc_fail": ue.mac.ul_crc_fail,
            },
            "drbs": [],
            "gtp": {
                "dl_pkts": ue.gtp.dl_pkts,
                "dl_bytes": ue.gtp.dl_bytes,
                "ul_pkts": ue.gtp.ul_pkts,
                "ul_bytes": ue.gtp.ul_bytes,
            }
        }
        
        # Group RLC and PDCP by LCID
        drb_lcids = set()
        rlc_by_lcid = {}
        pdcp_by_lcid = {}
        
        for rlc in ue.rlc_drb:
            if rlc.lcid >= 4:
                drb_lcids.add(rlc.lcid)
                rlc_by_lcid[rlc.lcid] = {
                    "dl_buffer": rlc.dl_buffer, "ul_buffer": rlc.ul_buffer,
                    "tx_sdus": rlc.tx_sdus, "tx_sdu_bytes": rlc.tx_sdu_bytes,
                    "tx_sdu_latency_us": rlc.tx_sdu_latency_us,
                    "rx_sdus": rlc.rx_sdus, "rx_sdu_bytes": rlc.rx_sdu_bytes,
                    "rx_lost_pdus": rlc.rx_lost_pdus
                }
        
        for pdcp in ue.pdcp_drb:
            drb_lcids.add(pdcp.lcid)
            pdcp_by_lcid[pdcp.lcid] = {
                "tx_pdus": pdcp.tx_pdus, "tx_pdu_bytes": pdcp.tx_pdu_bytes,
                "tx_dropped_sdus": pdcp.tx_dropped_sdus, "tx_discard_timeouts": pdcp.tx_discard_timeouts,
                "tx_pdu_latency_ns": pdcp.tx_pdu_latency_ns,
                "rx_pdus": pdcp.rx_pdus, "rx_pdu_bytes": pdcp.rx_pdu_bytes,
                "rx_dropped_pdus": pdcp.rx_dropped_pdus, "rx_sdu_latency_ns": pdcp.rx_sdu_latency_ns
            }
        
        for lcid in sorted(drb_lcids):
            drb_data = {
                "drb_id": lcid - 3,
                "lcid": lcid,
                "rlc": rlc_by_lcid.get(lcid, {}),
                "pdcp": pdcp_by_lcid.get(lcid, {})
            }
            ue_data["drbs"].append(drb_data)
        
        data["ues"].append(ue_data)
    
    print(json.dumps(data))

def main():
    parser = argparse.ArgumentParser(description='EdgeRIC Metrics Collector')
    parser.add_argument('--json', action='store_true', help='Output as JSON (one line per TTI)')
    parser.add_argument('--quiet', '-q', action='store_true', help='Only show MAC-level metrics, skip per-DRB')
    parser.add_argument('--address', default='ipc:///tmp/metrics_data', help='ZMQ address to connect to')
    args = parser.parse_args()
    
    # Setup ZMQ subscriber with conflate
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.setsockopt(zmq.CONFLATE, 1)  # Only keep latest message
    socket.setsockopt_string(zmq.SUBSCRIBE, "")  # Subscribe to all
    socket.connect(args.address)
    
    print(f"{C.BOLD}EdgeRIC Collector{C.RESET} connected to {C.CYAN}{args.address}{C.RESET}")
    print(f"Waiting for metrics... (Ctrl+C to exit)\n")
    
    msg_count = 0
    try:
        while True:
            # Receive message
            data = socket.recv()
            msg_count += 1
            
            # Parse protobuf
            tti_msg = metrics_pb2.TtiMetrics()
            try:
                tti_msg.ParseFromString(data)
            except Exception as e:
                print(f"[{msg_count}] Failed to parse protobuf: {e}")
                continue
            
            if args.json:
                print_json(tti_msg)
            else:
                print_tti_metrics(tti_msg, quiet=args.quiet)
                
    except KeyboardInterrupt:
        print(f"\n\n{C.BOLD}Received {msg_count} messages.{C.RESET} Exiting...")
    finally:
        socket.close()
        context.term()

if __name__ == "__main__":
    main()
