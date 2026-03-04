#ifndef EDGERIC_H
#define EDGERIC_H

#include <fstream>
#include <iostream>
#include <map>
#include <tuple>
#include <vector>
#include <zmq.hpp>
#include <optional>
#include <cstdint>
#include <chrono>
#include <mutex>

// Protobuf messages
#include "control_mcs.pb.h"
#include "control_weights.pb.h"
#include "control_qos.pb.h"
#include "metrics.pb.h"

/// TTI rollover constant
constexpr uint32_t TTI_ROLLOVER = 10000;

/// Key for per-UE per-DRB metrics: (RNTI, LCID)
using ue_drb_key = std::pair<uint16_t, uint8_t>;

/// Dynamic QoS parameters that EdgeRIC can override per-UE per-DRB
struct dynamic_qos_params {
    uint8_t  qos_priority;     // QoS Priority Level (1-127, lower = higher priority)
    uint8_t  arp_priority;     // ARP Priority Level (1-15, lower = higher priority)
    uint32_t pdb_ms;           // Packet Delay Budget in milliseconds
    uint64_t gbr_dl;           // Guaranteed Bit Rate DL (bps)
    uint64_t gbr_ul;           // Guaranteed Bit Rate UL (bps)
    
    // Flags to indicate which fields are overridden
    bool override_qos_priority = false;
    bool override_arp_priority = false;
    bool override_pdb = false;
    bool override_gbr = false;
};

//==============================================================================
// Per-TTI Metrics Data Structures (optimized for minimal locking)
//==============================================================================

/// MAC-level per-DRB metrics (updated per-TTI in scheduler)
struct mac_drb_metrics {
    uint32_t dl_buffer = 0;    // DL pending bytes
    uint32_t ul_buffer = 0;    // UL pending bytes
    uint32_t dl_bytes = 0;     // DL bytes scheduled this TTI
    uint32_t ul_bytes = 0;     // UL bytes received this TTI
};

/// MAC-level per-UE aggregate metrics (updated per-TTI)
struct mac_ue_metrics {
    uint32_t cqi = 0;
    float snr = 0.0f;
    uint32_t dl_buffer = 0;    // Total DL buffer
    uint32_t ul_buffer = 0;    // Total UL buffer
    uint32_t dl_tbs = 0;       // DL TBS this TTI
    uint32_t ul_tbs = 0;       // UL TBS this TTI
    uint32_t dl_mcs = 0;       // DL MCS this TTI
    uint32_t ul_mcs = 0;       // UL MCS this TTI
    uint32_t dl_prbs = 0;      // DL PRBs scheduled this TTI
    uint32_t ul_prbs = 0;      // UL PRBs scheduled this TTI
    uint32_t dl_harq_ack = 0;  // DL HARQ ACKs this TTI
    uint32_t dl_harq_nack = 0; // DL HARQ NACKs this TTI
    uint32_t ul_crc_ok = 0;    // UL CRC OK this TTI
    uint32_t ul_crc_fail = 0;  // UL CRC fail this TTI
};

/// RLC-level per-DRB metrics (accumulated, snapshot at TTI boundary)
struct rlc_drb_metrics {
    // Buffer status (from scheduler)
    uint32_t dl_buffer = 0;        // DL pending bytes (RLC TX buffer) - per LCID
    uint32_t ul_buffer = 0;        // UL pending bytes (from BSR) - note: actually per LCG
    // TX (DL)
    uint64_t tx_sdus = 0;
    uint64_t tx_sdu_bytes = 0;
    uint64_t tx_pdus = 0;
    uint64_t tx_pdu_bytes = 0;
    uint64_t tx_dropped_sdus = 0;
    uint64_t tx_retx_pdus = 0;
    uint32_t tx_sdu_latency_us = 0;
    // RX (UL)
    uint64_t rx_sdus = 0;
    uint64_t rx_sdu_bytes = 0;
    uint64_t rx_pdus = 0;
    uint64_t rx_pdu_bytes = 0;
    uint64_t rx_lost_pdus = 0;
    uint32_t rx_sdu_latency_us = 0;
};

/// PDCP-level per-DRB metrics (from CU-UP, accumulated)
struct pdcp_drb_metrics {
    // TX (DL)
    uint64_t tx_pdus = 0;
    uint64_t tx_pdu_bytes = 0;
    uint64_t tx_sdus = 0;
    uint64_t tx_dropped_sdus = 0;
    uint32_t tx_discard_timeouts = 0;     // Discard timer expirations
    uint32_t tx_pdu_latency_ns = 0;       // Avg PDU latency: SDU in → PDU out
    // RX (UL)
    uint64_t rx_pdus = 0;
    uint64_t rx_pdu_bytes = 0;
    uint64_t rx_delivered_sdus = 0;
    uint64_t rx_dropped_pdus = 0;
    uint32_t rx_sdu_latency_ns = 0;       // Avg SDU latency: PDU in → SDU out
};

/// GTP-U per-UE metrics (from CU-UP, accumulated)
struct gtp_ue_metrics {
    uint64_t dl_pkts = 0;
    uint64_t dl_bytes = 0;
    uint64_t ul_pkts = 0;
    uint64_t ul_bytes = 0;
};

//==============================================================================
// EdgeRIC Class
//==============================================================================

class edgeric {
private:
    // Control: weights, MCS, QoS overrides
    static std::map<uint16_t, float> weights_recved;
    static std::map<uint16_t, uint8_t> mcs_recved;
    static std::map<ue_drb_key, dynamic_qos_params> qos_overrides;

    //==========================================================================
    // Per-TTI Metrics Storage
    //==========================================================================
    
    // MAC metrics (per-UE aggregate)
    static std::map<uint16_t, mac_ue_metrics> mac_ue;
    
    // MAC metrics (per-DRB)
    static std::map<ue_drb_key, mac_drb_metrics> mac_drb;
    
    // RLC metrics (per-DRB) - updated from RLC layer
    static std::map<ue_drb_key, rlc_drb_metrics> rlc_drb;
    static std::mutex rlc_mutex;  // Protects rlc_drb (cross-thread access)
    
    // PDCP metrics (per-DRB) - keyed by (cu_up_ue_index, drb_id)
    using cu_up_drb_key = std::pair<uint32_t, uint8_t>;
    static std::map<cu_up_drb_key, pdcp_drb_metrics> pdcp_drb;
    static std::mutex pdcp_mutex;  // Protects pdcp_drb
    
    // GTP metrics (per-UE) - keyed by cu_up_ue_index
    static std::map<uint32_t, gtp_ue_metrics> gtp_ue;
    static std::mutex gtp_mutex;  // Protects gtp_ue
    
    //==========================================================================
    // UE ID Correlation Maps
    //==========================================================================
    
    // CU-CP ue_index -> RNTI (set when UE is created)
    static std::map<uint32_t, uint16_t> ue_index_to_rnti;
    
    // E1AP-based correlation
    static std::map<uint32_t, uint16_t> e1ap_id_to_rnti;      // e1ap_id -> RNTI
    static std::map<uint32_t, uint32_t> cu_up_ue_to_e1ap_id;  // cu_up_ue_index -> e1ap_id
    
    // DU UE index -> RNTI (for RLC layer)
    static std::map<uint32_t, uint16_t> du_ue_to_rnti;
    static std::mutex du_ue_mutex;  // Protects du_ue_to_rnti
    
    //==========================================================================
    // Internal State
    //==========================================================================
    
    static uint32_t er_ran_index_weights;
    static uint32_t er_ran_index_mcs;
    static uint32_t er_ran_index_qos;
    static bool initialized;
    
    static void ensure_initialized();

public:
    static bool enable_logging;
    static uint32_t tti_cnt;
    
    //==========================================================================
    // TTI Management
    //==========================================================================
    
    /// Set the TTI counter (called from scheduler every slot)
    static void setTTI(uint32_t tti_count) { tti_cnt = tti_count; }
    
    /// Get TTI index with rollover at TTI_ROLLOVER (10000)
    static uint32_t getTtiIndex() { return tti_cnt % TTI_ROLLOVER; }
    
    //==========================================================================
    // MAC Metrics (called from scheduler, same thread - no locking needed)
    //==========================================================================
    
    /// Set per-UE aggregate MAC metrics
    static void set_mac_ue(uint16_t rnti, uint32_t cqi, float snr,
                           uint32_t dl_buffer, uint32_t ul_buffer,
                           uint32_t dl_tbs, uint32_t ul_tbs);
    
    /// Increment HARQ ACK/NACK counters
    static void inc_dl_harq_ack(uint16_t rnti) { mac_ue[rnti].dl_harq_ack++; }
    static void inc_dl_harq_nack(uint16_t rnti) { mac_ue[rnti].dl_harq_nack++; }
    static void inc_ul_crc_ok(uint16_t rnti) { mac_ue[rnti].ul_crc_ok++; }
    static void inc_ul_crc_fail(uint16_t rnti) { mac_ue[rnti].ul_crc_fail++; }
    
    /// Set per-DRB MAC metrics
    static void set_mac_drb(uint16_t rnti, uint8_t lcid,
                            uint32_t dl_buffer, uint32_t ul_buffer,
                            uint32_t dl_bytes, uint32_t ul_bytes);
    
    /// Add bytes to DRB (accumulated during TTI)
    static void add_mac_drb_dl_bytes(uint16_t rnti, uint8_t lcid, uint32_t bytes);
    static void add_mac_drb_ul_bytes(uint16_t rnti, uint8_t lcid, uint32_t bytes);
    
    //==========================================================================
    // RLC Metrics (called from RLC layer, different thread - needs locking)
    //==========================================================================
    
    /// Report RLC metrics for a DRB (called from RLC metrics collector)
    static void report_rlc_metrics(uint32_t du_ue_index, uint8_t lcid,
                                   const rlc_drb_metrics& metrics);
    
    /// Register DU UE index to RNTI mapping
    static void register_du_ue(uint32_t du_ue_index, uint16_t rnti);
    
    //==========================================================================
    // PDCP Metrics (called from CU-UP, different thread - needs locking)
    //==========================================================================
    
    /// Report PDCP metrics for a DRB
    static void report_pdcp_metrics(uint32_t cu_up_ue_index, uint8_t drb_id,
                                    const pdcp_drb_metrics& metrics);
    
    //==========================================================================
    // GTP Metrics (called from CU-UP, different thread - needs locking)
    //==========================================================================
    
    /// Report GTP DL packet (from UPF)
    static void report_gtp_dl_pkt(uint32_t cu_up_ue_index, uint32_t pdu_len);
    
    /// Report GTP UL packet (to UPF)
    static void report_gtp_ul_pkt(uint32_t cu_up_ue_index, uint32_t pdu_len);
    
    //==========================================================================
    // UE ID Correlation
    //==========================================================================
    
    /// Register UE (CU-CP ue_index -> RNTI)
    static void register_ue(uint32_t ue_index, uint16_t rnti);
    static void unregister_ue(uint32_t ue_index);
    static uint16_t get_rnti_from_ue_index(uint32_t ue_index);
    
    /// E1AP-based correlation (CU-UP ue_index -> RNTI)
    static void register_e1ap_rnti(uint32_t e1ap_id, uint16_t rnti);
    static void register_cu_up_ue_e1ap(uint32_t cu_up_ue_index, uint32_t e1ap_id);
    static uint16_t get_rnti_from_cu_up_ue_index(uint32_t cu_up_ue_index);
    
    //==========================================================================
    // ZMQ Telemetry - Per-TTI Export
    //==========================================================================
    
    /// Send per-TTI metrics over ZMQ (called every TTI from scheduler)
    static void send_tti_metrics();
    
    /// Legacy: print to log file
    static void printmyvariables();
    
    /// Legacy: send_to_er (for backwards compatibility)
    static void send_to_er();
    
    /// Initialize ZMQ sockets
    static void init();
    
    //==========================================================================
    // ZMQ Control Reception
    //==========================================================================
    
    static void get_weights_from_er();
    static void get_mcs_from_er();
    static void get_qos_from_er();
    
    //==========================================================================
    // Control Getters (called from scheduler)
    //==========================================================================
    
    static std::optional<float> get_weights(uint16_t rnti);
    static std::optional<uint8_t> get_mcs(uint16_t rnti);
    
    //==========================================================================
    // QoS Override API
    //==========================================================================
    
    static void set_dynamic_qos(uint16_t rnti, uint8_t lcid, const dynamic_qos_params& params);
    static void clear_dynamic_qos(uint16_t rnti, uint8_t lcid);
    static void clear_all_dynamic_qos(uint16_t rnti);
    static std::optional<dynamic_qos_params> get_dynamic_qos(uint16_t rnti, uint8_t lcid);
    
    static void set_qos_priority(uint16_t rnti, uint8_t lcid, uint8_t priority);
    static void set_arp_priority(uint16_t rnti, uint8_t lcid, uint8_t arp);
    static void set_pdb(uint16_t rnti, uint8_t lcid, uint32_t pdb_ms);
    static void set_gbr(uint16_t rnti, uint8_t lcid, uint64_t gbr_dl, uint64_t gbr_ul);
    
    static std::optional<uint8_t> get_qos_priority(uint16_t rnti, uint8_t lcid);
    static std::optional<uint8_t> get_arp_priority(uint16_t rnti, uint8_t lcid);
    static std::optional<uint32_t> get_pdb(uint16_t rnti, uint8_t lcid);
    static std::optional<uint64_t> get_gbr_dl(uint16_t rnti, uint8_t lcid);
    static std::optional<uint64_t> get_gbr_ul(uint16_t rnti, uint8_t lcid);
    
    //==========================================================================
    // Legacy API (for backwards compatibility)
    //==========================================================================
    
    static void set_cqi(uint16_t rnti, float cqi) { mac_ue[rnti].cqi = static_cast<uint32_t>(cqi); }
    static void set_snr(uint16_t rnti, float snr) { mac_ue[rnti].snr = snr; }
    static void set_ul_buffer(uint16_t rnti, uint32_t ul_buffer) { mac_ue[rnti].ul_buffer = ul_buffer; }
    static void set_dl_buffer(uint16_t rnti, uint32_t dl_buffer) { mac_ue[rnti].dl_buffer = dl_buffer; }
    static void set_tx_bytes(uint16_t rnti, float tbs);
    static void set_rx_bytes(uint16_t rnti, float tbs);
    static void set_dl_tbs(uint16_t rnti, uint32_t tbs);
    static void set_ul_tbs(uint16_t rnti, uint32_t tbs);
    static void set_dl_mcs(uint16_t rnti, uint32_t mcs);
    static void set_ul_mcs(uint16_t rnti, uint32_t mcs);
    static void set_dl_prbs(uint16_t rnti, uint32_t prbs);
    static void set_ul_prbs(uint16_t rnti, uint32_t prbs);
    static void inc_dl_ok(uint16_t rnti) { inc_dl_harq_ack(rnti); }
    static void inc_dl_nok(uint16_t rnti) { inc_dl_harq_nack(rnti); }
    static void inc_ul_ok(uint16_t rnti) { inc_ul_crc_ok(rnti); }
    static void inc_ul_nok(uint16_t rnti) { inc_ul_crc_fail(rnti); }
    
    // RLC buffer setters (called from scheduler with LCID granularity)
    static void set_rlc_dl_buffer(uint16_t rnti, uint8_t lcid, uint32_t dl_buffer) {
        std::lock_guard<std::mutex> lock(rlc_mutex);
        rlc_drb[{rnti, lcid}].dl_buffer = dl_buffer;
    }
    static void set_rlc_ul_buffer(uint16_t rnti, uint8_t lcg, uint32_t ul_buffer) {
        // Note: UL buffer is per LCG, we store it mapped to LCID=lcg+4 for simplicity
        std::lock_guard<std::mutex> lock(rlc_mutex);
        rlc_drb[{rnti, static_cast<uint8_t>(lcg + 4)}].ul_buffer = ul_buffer;
    }
    // Legacy aliases
    static void set_drb_dl_buffer(uint16_t rnti, uint8_t lcid, uint32_t dl_buffer) {
        set_rlc_dl_buffer(rnti, lcid, dl_buffer);
    }
    static void set_drb_ul_buffer(uint16_t rnti, uint8_t lcg, uint32_t ul_buffer) {
        set_rlc_ul_buffer(rnti, lcg, ul_buffer);
    }
    static void add_drb_tx_bytes(uint16_t rnti, uint8_t lcid, float bytes) {
        mac_drb[{rnti, lcid}].dl_bytes += static_cast<uint32_t>(bytes);
    }
    static void add_drb_rx_bytes(uint16_t rnti, uint8_t lcid, float bytes) {
        mac_drb[{rnti, lcid}].ul_bytes += static_cast<uint32_t>(bytes);
    }
    
    static std::vector<uint8_t> get_drb_lcids(uint16_t rnti);
    static std::vector<uint8_t> get_pdcp_drb_ids(uint16_t rnti);
    static std::vector<uint8_t> get_pdcp_drb_ids_by_ue_index(uint32_t ue_index);
    static std::optional<gtp_ue_metrics> get_gtp_metrics(uint16_t rnti);
    
    static void collect_ue_telemetry(uint16_t rnti, float cqi, float snr,
                                     uint32_t dl_buffer_bytes, uint32_t ul_buffer_bytes);
};

#endif // EDGERIC_H
