#ifndef EDGERIC_H
#define EDGERIC_H

#include <fstream>
#include <iostream>
#include <map>
#include <tuple>
#include <zmq.hpp>
#include <optional>
#include <cstdint>

// #include "metrics.pb.h"
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
};

#endif // EDGERIC_H



