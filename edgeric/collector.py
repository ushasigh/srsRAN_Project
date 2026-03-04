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
from collections import defaultdict

# Import generated protobuf
import metrics_pb2

# Rolling BLER tracker per UE
class BlerTracker:
    """Track cumulative HARQ counts for rolling BLER calculation"""
    def __init__(self):
        # {rnti: {'dl_ack': count, 'dl_nack': count, 'ul_ok': count, 'ul_fail': count}}
        self.counts = defaultdict(lambda: {'dl_ack': 0, 'dl_nack': 0, 'ul_ok': 0, 'ul_fail': 0})
    
    def update(self, rnti, dl_ack, dl_nack, ul_ok, ul_fail):
        """Add new TTI counts to cumulative totals"""
        self.counts[rnti]['dl_ack'] += dl_ack
        self.counts[rnti]['dl_nack'] += dl_nack
        self.counts[rnti]['ul_ok'] += ul_ok
        self.counts[rnti]['ul_fail'] += ul_fail
    
    def get_bler(self, rnti):
        """Get rolling DL and UL BLER percentages"""
        c = self.counts[rnti]
        dl_total = c['dl_ack'] + c['dl_nack']
        ul_total = c['ul_ok'] + c['ul_fail']
        dl_bler = (c['dl_nack'] / dl_total * 100) if dl_total > 0 else 0
        ul_bler = (c['ul_fail'] / ul_total * 100) if ul_total > 0 else 0
        return dl_bler, ul_bler, dl_total, ul_total
    
    def get_counts(self, rnti):
        """Get cumulative counts"""
        return self.counts[rnti]

# Global BLER tracker
bler_tracker = BlerTracker()

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
        
        # HARQ - Update rolling BLER tracker and display
        bler_tracker.update(ue.rnti, mac.dl_harq_ack, mac.dl_harq_nack, mac.ul_crc_ok, mac.ul_crc_fail)
        dl_bler, ul_bler, dl_total, ul_total = bler_tracker.get_bler(ue.rnti)
        harq_color = C.GREEN if dl_bler < 10 and ul_bler < 10 else C.RED
        # Show this TTI's counts and rolling BLER
        print(f"{C.CYAN}║{C.RESET}   {C.DIM}HARQ TTI:{C.RESET}  DL +{mac.dl_harq_ack}/+{mac.dl_harq_nack}  UL +{mac.ul_crc_ok}/+{mac.ul_crc_fail}")
        print(f"{C.CYAN}║{C.RESET}   {C.DIM}BLER:{C.RESET}      DL {harq_color}{dl_bler:5.2f}%{C.RESET} ({dl_total} total)  UL {harq_color}{ul_bler:5.2f}%{C.RESET} ({ul_total} total)")
        
        if quiet:
            print(f"{C.CYAN}╚{'═'*60}{C.RESET}")
            continue
        
        # ───────────────────────────────────────────────────────────────
        # Collect DRB data
        # ───────────────────────────────────────────────────────────────
        drb_lcids = set()
        rlc_by_lcid = {}
        pdcp_by_lcid = {}
        
        for rlc in ue.rlc_drb:
            if rlc.lcid >= 4:  # Only DRBs
                drb_lcids.add(rlc.lcid)
                rlc_by_lcid[rlc.lcid] = rlc
        for pdcp in ue.pdcp_drb:
            drb_lcids.add(pdcp.lcid)
            pdcp_by_lcid[pdcp.lcid] = pdcp
        
        # ───────────────────────────────────────────────────────────────
        # UL (Uplink) Section - All DRBs
        # ───────────────────────────────────────────────────────────────
        if drb_lcids:
            print(f"{C.CYAN}║{C.RESET}")
            print(f"{C.CYAN}║{C.RESET} {C.BOLD}{C.YELLOW}▲ UL (Uplink){C.RESET}")
            
            for lcid in sorted(drb_lcids):
                drb_id = lcid - 3
                rlc = rlc_by_lcid.get(lcid)
                pdcp = pdcp_by_lcid.get(lcid)
                
                print(f"{C.CYAN}║{C.RESET}   {C.BOLD}DRB {drb_id} (LCID {lcid}){C.RESET}")
                if rlc:
                    print(f"{C.CYAN}║{C.RESET}     {C.MAGENTA}RLC:{C.RESET}  buf={fmt_bytes(rlc.ul_buffer):>8s}  RX {rlc.rx_sdus:6d} SDU / {fmt_bytes(rlc.rx_sdu_bytes):>8s}  lat={fmt_latency_us(rlc.rx_sdu_latency_us):>8s}  lost={rlc.rx_lost_pdus}")
                if pdcp:
                    print(f"{C.CYAN}║{C.RESET}     {C.BLUE}PDCP:{C.RESET} RX {pdcp.rx_pdus:6d} PDU / {fmt_bytes(pdcp.rx_pdu_bytes):>8s}  lat={fmt_latency_ns(pdcp.rx_sdu_latency_ns):>8s}  drop={pdcp.rx_dropped_pdus}")
            
            # GTP UL
            gtp = ue.gtp
            if gtp.ul_pkts > 0:
                print(f"{C.CYAN}║{C.RESET}   {C.DIM}GTP-U:{C.RESET} {gtp.ul_pkts:8d} pkts / {fmt_bytes(gtp.ul_bytes):>10s}")
        
        # ───────────────────────────────────────────────────────────────
        # DL (Downlink) Section - All DRBs
        # ───────────────────────────────────────────────────────────────
        if drb_lcids:
            print(f"{C.CYAN}║{C.RESET}")
            print(f"{C.CYAN}║{C.RESET} {C.BOLD}{C.GREEN}▼ DL (Downlink){C.RESET}")
            
            for lcid in sorted(drb_lcids):
                drb_id = lcid - 3
                rlc = rlc_by_lcid.get(lcid)
                pdcp = pdcp_by_lcid.get(lcid)
                
                print(f"{C.CYAN}║{C.RESET}   {C.BOLD}DRB {drb_id} (LCID {lcid}){C.RESET}")
                if rlc:
                    print(f"{C.CYAN}║{C.RESET}     {C.MAGENTA}RLC:{C.RESET}  buf={fmt_bytes(rlc.dl_buffer):>8s}  TX {rlc.tx_sdus:6d} SDU / {fmt_bytes(rlc.tx_sdu_bytes):>8s}  lat={fmt_latency_us(rlc.tx_sdu_latency_us):>8s}  retx={rlc.tx_retx_pdus}")
                if pdcp:
                    print(f"{C.CYAN}║{C.RESET}     {C.BLUE}PDCP:{C.RESET} TX {pdcp.tx_pdus:6d} PDU / {fmt_bytes(pdcp.tx_pdu_bytes):>8s}  lat={fmt_latency_ns(pdcp.tx_pdu_latency_ns):>8s}  drop={pdcp.tx_dropped_sdus}  discard={pdcp.tx_discard_timeouts}")
            
            # GTP DL
            gtp = ue.gtp
            if gtp.dl_pkts > 0:
                print(f"{C.CYAN}║{C.RESET}   {C.DIM}GTP-U:{C.RESET} {gtp.dl_pkts:8d} pkts / {fmt_bytes(gtp.dl_bytes):>10s}")
        
        print(f"{C.CYAN}╚{'═'*60}{C.RESET}")

def print_json(tti_msg):
    """Print metrics as JSON with DL/UL separation"""
    data = {
        "tti_index": tti_msg.tti_index,
        "timestamp_us": tti_msg.timestamp_us,
        "ues": []
    }
    
    for ue in tti_msg.ues:
        # Update rolling BLER tracker
        bler_tracker.update(ue.rnti, ue.mac.dl_harq_ack, ue.mac.dl_harq_nack, 
                           ue.mac.ul_crc_ok, ue.mac.ul_crc_fail)
        dl_bler, ul_bler, dl_total, ul_total = bler_tracker.get_bler(ue.rnti)
        
        ue_data = {
            "rnti": ue.rnti,
            "mac": {
                "cqi": ue.mac.cqi,
                "snr": ue.mac.snr,
                "dl": {
                    "buffer": ue.mac.dl_buffer,
                    "tbs": ue.mac.dl_tbs,
                    "mcs": ue.mac.dl_mcs,
                    "prbs": ue.mac.dl_prbs,
                    "harq_ack_tti": ue.mac.dl_harq_ack,
                    "harq_nack_tti": ue.mac.dl_harq_nack,
                    "bler_pct": round(dl_bler, 2),
                    "harq_total": dl_total,
                },
                "ul": {
                    "buffer": ue.mac.ul_buffer,
                    "tbs": ue.mac.ul_tbs,
                    "mcs": ue.mac.ul_mcs,
                    "prbs": ue.mac.ul_prbs,
                    "crc_ok_tti": ue.mac.ul_crc_ok,
                    "crc_fail_tti": ue.mac.ul_crc_fail,
                    "bler_pct": round(ul_bler, 2),
                    "crc_total": ul_total,
                },
            },
            "drbs": [],
            "gtp": {
                "dl": {"pkts": ue.gtp.dl_pkts, "bytes": ue.gtp.dl_bytes},
                "ul": {"pkts": ue.gtp.ul_pkts, "bytes": ue.gtp.ul_bytes},
            }
        }
        
        # Group RLC and PDCP by LCID with DL/UL separation
        drb_lcids = set()
        rlc_by_lcid = {}
        pdcp_by_lcid = {}
        
        for rlc in ue.rlc_drb:
            if rlc.lcid >= 4:
                drb_lcids.add(rlc.lcid)
                rlc_by_lcid[rlc.lcid] = {
                    "dl": {
                        "buffer": rlc.dl_buffer,
                        "sdus": rlc.tx_sdus,
                        "sdu_bytes": rlc.tx_sdu_bytes,
                        "latency_us": rlc.tx_sdu_latency_us,
                        "retx_pdus": rlc.tx_retx_pdus,
                        "dropped_sdus": rlc.tx_dropped_sdus,
                    },
                    "ul": {
                        "buffer": rlc.ul_buffer,
                        "sdus": rlc.rx_sdus,
                        "sdu_bytes": rlc.rx_sdu_bytes,
                        "latency_us": rlc.rx_sdu_latency_us,
                        "lost_pdus": rlc.rx_lost_pdus,
                    }
                }
        
        for pdcp in ue.pdcp_drb:
            drb_lcids.add(pdcp.lcid)
            pdcp_by_lcid[pdcp.lcid] = {
                "dl": {
                    "pdus": pdcp.tx_pdus,
                    "pdu_bytes": pdcp.tx_pdu_bytes,
                    "dropped_sdus": pdcp.tx_dropped_sdus,
                    "discard_timeouts": pdcp.tx_discard_timeouts,
                    "latency_ns": pdcp.tx_pdu_latency_ns,
                },
                "ul": {
                    "pdus": pdcp.rx_pdus,
                    "pdu_bytes": pdcp.rx_pdu_bytes,
                    "dropped_pdus": pdcp.rx_dropped_pdus,
                    "latency_ns": pdcp.rx_sdu_latency_ns,
                }
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
