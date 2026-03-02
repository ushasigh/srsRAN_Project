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

// Protobuf messages
#include "control_mcs.pb.h"
#include "control_weights.pb.h"
#include "control_qos.pb.h"
#include "metrics.pb.h"

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

/// Key for per-UE per-DRB QoS overrides: (RNTI, LCID)
using ue_drb_key = std::pair<uint16_t, uint8_t>;



class edgeric {
private:
    static std::map<uint16_t, float> weights_recved;
    static std::map<uint16_t, uint8_t> mcs_recved;
    static std::map<ue_drb_key, dynamic_qos_params> qos_overrides;  // Dynamic QoS overrides per UE per DRB

    static std::map<uint16_t, float> ue_cqis;
    static std::map<uint16_t, float> ue_snrs;
    static std::map<uint16_t, float> rx_bytes;
    static std::map<uint16_t, float> tx_bytes;
    static std::map<uint16_t, uint32_t> ue_ul_buffers;
    static std::map<uint16_t, uint32_t> ue_dl_buffers;
    static std::map<uint16_t, float> dl_tbs_ues;
    // HARQ ACK/NACK counters per TTI
    static std::map<uint16_t, uint32_t> dl_ok_cnt;
    static std::map<uint16_t, uint32_t> dl_nok_cnt;
    static std::map<uint16_t, uint32_t> ul_ok_cnt;
    static std::map<uint16_t, uint32_t> ul_nok_cnt;
    
    // Per-DRB metrics: key = (RNTI, LCID)
    static std::map<ue_drb_key, uint32_t> drb_dl_buffers;  // DL buffer per DRB
    static std::map<ue_drb_key, uint32_t> drb_ul_buffers;  // UL buffer per DRB (per LCG mapped to LCID)
    static std::map<ue_drb_key, float> drb_tx_bytes;       // DL bytes scheduled per DRB
    static std::map<ue_drb_key, float> drb_rx_bytes;       // UL bytes received per DRB
    
    // UE Index to RNTI mapping (for CU-UP to DU correlation)
    static std::map<uint32_t, uint16_t> ue_index_to_rnti;  // CU-CP ue_index -> RNTI
    
    // E1AP-based CU-UP to RNTI correlation
    static std::map<uint32_t, uint16_t> e1ap_id_to_rnti;  // gnb_cu_cp_ue_e1ap_id -> RNTI
    static std::map<uint32_t, uint32_t> cu_up_ue_to_e1ap_id;  // cu_up_ue_index -> gnb_cu_cp_ue_e1ap_id
    
    // PDCP metrics per UE per DRB: key = (CU-UP ue_index, DRB_ID)
    using cu_up_drb_key = std::pair<uint32_t, uint8_t>;  // (ue_index, drb_id)
    struct pdcp_drb_metrics {
        uint32_t tx_pdus = 0;
        uint32_t tx_pdu_bytes = 0;
        uint32_t tx_dropped_sdus = 0;
        uint32_t rx_pdus = 0;
        uint32_t rx_pdu_bytes = 0;
        uint32_t rx_dropped_pdus = 0;
        uint32_t rx_delivered_sdus = 0;
    };
    static std::map<cu_up_drb_key, pdcp_drb_metrics> pdcp_metrics;  // key = (ue_index, DRB_ID)
    
    // GTP-U metrics per UE (N3 interface to/from UPF)
    struct gtp_ue_metrics {
        uint32_t dl_pkts = 0;    // DL GTP-U packets received from core
        uint32_t dl_bytes = 0;   // DL GTP-U bytes received from core
        uint32_t ul_pkts = 0;    // UL GTP-U packets sent to core
        uint32_t ul_bytes = 0;   // UL GTP-U bytes sent to core
    };
    static std::map<uint32_t, gtp_ue_metrics> gtp_metrics;  // key = ue_index

    static uint32_t er_ran_index_weights;
    static uint32_t er_ran_index_mcs;
    static uint32_t er_ran_index_qos;
    static bool initialized;

    static void ensure_initialized();
    

public:
    static bool enable_logging;
    static uint32_t tti_cnt;
    static void setTTI(uint32_t tti_count) {tti_cnt = tti_count;}
    static void printmyvariables();
    static void init();
    //Setters
    static void set_cqi(uint16_t rnti, float cqi) {ue_cqis[rnti] = cqi;}
    static void set_snr(uint16_t rnti, float snr) {ue_snrs[rnti] = snr;}
    static void set_ul_buffer(uint16_t rnti, uint32_t ul_buffer) {ue_ul_buffers[rnti] = ul_buffer;}
    static void set_dl_buffer(uint16_t rnti, uint32_t dl_buffer) {ue_dl_buffers[rnti] = dl_buffer;}
    static void set_tx_bytes(uint16_t rnti, float tbs) {tx_bytes[rnti] += tbs;} // ue_dl_buffers[rnti] -= tbs; }
    static void set_rx_bytes(uint16_t rnti, float tbs) {rx_bytes[rnti] += tbs;} // ue_ul_buffers[rnti] -= tbs;}
    static void set_dl_tbs(uint16_t rnti, float tbs) {dl_tbs_ues[rnti] = tbs;}
    // HARQ ACK/NACK setters - called from scheduler feedback handlers
    static void inc_dl_ok(uint16_t rnti) {dl_ok_cnt[rnti]++;}
    static void inc_dl_nok(uint16_t rnti) {dl_nok_cnt[rnti]++;}
    static void inc_ul_ok(uint16_t rnti) {ul_ok_cnt[rnti]++;}
    static void inc_ul_nok(uint16_t rnti) {ul_nok_cnt[rnti]++;}
    
    // Per-DRB setters - called for per-bearer telemetry
    static void set_drb_dl_buffer(uint16_t rnti, uint8_t lcid, uint32_t dl_buffer) {
        drb_dl_buffers[{rnti, lcid}] = dl_buffer;
    }
    static void set_drb_ul_buffer(uint16_t rnti, uint8_t lcid, uint32_t ul_buffer) {
        drb_ul_buffers[{rnti, lcid}] = ul_buffer;
    }
    static void add_drb_tx_bytes(uint16_t rnti, uint8_t lcid, float bytes) {
        drb_tx_bytes[{rnti, lcid}] += bytes;
    }
    static void add_drb_rx_bytes(uint16_t rnti, uint8_t lcid, float bytes) {
        drb_rx_bytes[{rnti, lcid}] += bytes;
    }
    // Get all DRBs for a given RNTI (returns list of LCIDs with data)
    static std::vector<uint8_t> get_drb_lcids(uint16_t rnti);
    
    //////////////////////////////////// UE Index to RNTI Mapping (CU-CP populates this)
    /// Register UE index to RNTI mapping - called from CU-CP when UE is created
    static void register_ue(uint32_t ue_index, uint16_t rnti);
    /// Unregister UE - called when UE is removed
    static void unregister_ue(uint32_t ue_index);
    /// Get RNTI from UE index (returns 0 if not found)
    static uint16_t get_rnti_from_ue_index(uint32_t ue_index);
    /// Get UE index from RNTI (returns UINT32_MAX if not found)
    static uint32_t get_ue_index_from_rnti(uint16_t rnti);
    
    //////////////////////////////////// E1AP-based CU-UP to RNTI Correlation
    /// Register E1AP ID to RNTI mapping - called from CU-CP when bearer context is set up
    /// @param gnb_cu_cp_ue_e1ap_id The E1AP UE ID assigned by CU-CP
    /// @param rnti The RNTI of the UE
    static void register_e1ap_rnti(uint32_t gnb_cu_cp_ue_e1ap_id, uint16_t rnti);
    
    /// Register CU-UP UE index to E1AP ID mapping - called from CU-UP E1AP when bearer context is set up
    /// @param cu_up_ue_index The CU-UP internal UE index
    /// @param gnb_cu_cp_ue_e1ap_id The E1AP UE ID from CU-CP (received in bearer context setup request)
    static void register_cu_up_ue_e1ap(uint32_t cu_up_ue_index, uint32_t gnb_cu_cp_ue_e1ap_id);
    
    /// Get RNTI from CU-UP UE index using E1AP correlation (returns 0 if not found)
    static uint16_t get_rnti_from_cu_up_ue_index(uint32_t cu_up_ue_index);
    
    //////////////////////////////////// PDCP Metrics (from CU-UP)
    /// Report PDCP metrics for a UE/DRB - called from PDCP metrics aggregator
    /// @param ue_index CU-UP UE index
    /// @param drb_id DRB ID (1-32)
    /// @param tx TX (DL) metrics
    /// @param rx RX (UL) metrics
    static void report_pdcp_metrics(uint32_t ue_index, uint8_t drb_id,
                                    uint32_t tx_pdus, uint32_t tx_pdu_bytes, uint32_t tx_dropped_sdus,
                                    uint32_t rx_pdus, uint32_t rx_pdu_bytes, uint32_t rx_dropped_pdus,
                                    uint32_t rx_delivered_sdus);
    /// Get all DRB IDs with PDCP metrics for a given RNTI (deprecated - use get_pdcp_drb_ids_by_ue_index)
    static std::vector<uint8_t> get_pdcp_drb_ids(uint16_t rnti);
    /// Get all DRB IDs with PDCP metrics for a given CU-UP UE index
    static std::vector<uint8_t> get_pdcp_drb_ids_by_ue_index(uint32_t ue_index);
    
    //////////////////////////////////// GTP-U Metrics (from CU-UP, N3 interface)
    /// Report GTP-U DL packet received (from UPF to gNB)
    /// @param ue_index CU-UP UE index
    /// @param pdu_len Length of the GTP-U payload (SDU)
    static void report_gtp_dl_pkt(uint32_t ue_index, uint32_t pdu_len);
    
    /// Report GTP-U UL packet sent (from gNB to UPF)
    /// @param ue_index CU-UP UE index
    /// @param pdu_len Length of the GTP-U payload (SDU)
    static void report_gtp_ul_pkt(uint32_t ue_index, uint32_t pdu_len);
    
    /// Get GTP metrics for a UE by RNTI (returns nullopt if not found)
    static std::optional<gtp_ue_metrics> get_gtp_metrics(uint16_t rnti);
    
    //////////////////////////////////// ZMQ function to send RT-E2 Report 
    static void send_to_er();
    
    //////////////////////////////////// ZMQ function to receive RT-E2 Policy - called at end of slot
    static void get_weights_from_er();
    static void get_mcs_from_er();

    //////////////////////////////////// Static getters - sets the control actions - called at slot beginning
    
    static std::optional<float> get_weights(uint16_t);
    static std::optional<uint8_t> get_mcs(uint16_t);
    
    //////////////////////////////////// Dynamic QoS control - can be called from EdgeRIC agent
    //////////////////////////////////// All functions take (rnti, lcid) to identify a specific DRB
    
    /// Set dynamic QoS parameters for a specific DRB of a UE
    static void set_dynamic_qos(uint16_t rnti, uint8_t lcid, const dynamic_qos_params& params);
    
    /// Clear dynamic QoS override for a specific DRB (reverts to static config)
    static void clear_dynamic_qos(uint16_t rnti, uint8_t lcid);
    
    /// Clear all dynamic QoS overrides for a UE (all DRBs)
    static void clear_all_dynamic_qos(uint16_t rnti);
    
    /// Get dynamic QoS parameters for a specific DRB (returns nullopt if no override)
    static std::optional<dynamic_qos_params> get_dynamic_qos(uint16_t rnti, uint8_t lcid);
    
    /// Convenience setters for individual QoS parameters (per DRB)
    static void set_qos_priority(uint16_t rnti, uint8_t lcid, uint8_t priority);
    static void set_arp_priority(uint16_t rnti, uint8_t lcid, uint8_t arp);
    static void set_pdb(uint16_t rnti, uint8_t lcid, uint32_t pdb_ms);
    static void set_gbr(uint16_t rnti, uint8_t lcid, uint64_t gbr_dl, uint64_t gbr_ul);
    
    /// Convenience getters for individual QoS parameters (per DRB, returns nullopt if not overridden)
    static std::optional<uint8_t> get_qos_priority(uint16_t rnti, uint8_t lcid);
    static std::optional<uint8_t> get_arp_priority(uint16_t rnti, uint8_t lcid);
    static std::optional<uint32_t> get_pdb(uint16_t rnti, uint8_t lcid);
    static std::optional<uint64_t> get_gbr_dl(uint16_t rnti, uint8_t lcid);
    static std::optional<uint64_t> get_gbr_ul(uint16_t rnti, uint8_t lcid);
    
    /// ZMQ function to receive QoS control from EdgeRIC agent
    static void get_qos_from_er();
    
    //////////////////////////////////// Centralized Telemetry Collection
    /// Collect telemetry for a single UE - called from scheduler every TTI
    /// @param rnti UE RNTI
    /// @param cqi Wideband CQI value
    /// @param snr PUSCH SNR in dB
    /// @param dl_buffer_bytes Pending DL buffer bytes
    /// @param ul_buffer_bytes Pending UL buffer bytes
    static void collect_ue_telemetry(uint16_t rnti, float cqi, float snr, 
                                      uint32_t dl_buffer_bytes, uint32_t ul_buffer_bytes);
};

#endif // EDGERIC_H



