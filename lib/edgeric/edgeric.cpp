#include "edgeric.h"
#include <set>
#include <algorithm>

// Definition of static member variables
uint32_t edgeric::tti_cnt = 0;
uint32_t edgeric::er_ran_index_weights = 0;
uint32_t edgeric::er_ran_index_mcs = 0;

std::map<uint16_t, float> edgeric::ue_cqis = {};
std::map<uint16_t, float> edgeric::ue_snrs = {};
std::map<uint16_t, float> edgeric::rx_bytes = {};
std::map<uint16_t, float> edgeric::tx_bytes = {};
std::map<uint16_t, uint32_t> edgeric::ue_ul_buffers = {};
std::map<uint16_t, uint32_t> edgeric::ue_dl_buffers = {};
std::map<uint16_t, float> edgeric::dl_tbs_ues = {};
// HARQ ACK/NACK counters
std::map<uint16_t, uint32_t> edgeric::dl_ok_cnt = {};
std::map<uint16_t, uint32_t> edgeric::dl_nok_cnt = {};
std::map<uint16_t, uint32_t> edgeric::ul_ok_cnt = {};
std::map<uint16_t, uint32_t> edgeric::ul_nok_cnt = {};

// Per-DRB metrics
std::map<ue_drb_key, uint32_t> edgeric::drb_dl_buffers = {};
std::map<ue_drb_key, uint32_t> edgeric::drb_ul_buffers = {};
std::map<ue_drb_key, float> edgeric::drb_tx_bytes = {};
std::map<ue_drb_key, float> edgeric::drb_rx_bytes = {};

// UE Index to RNTI mapping
std::map<uint32_t, uint16_t> edgeric::ue_index_to_rnti = {};

// E1AP-based CU-UP to RNTI correlation
std::map<uint32_t, uint16_t> edgeric::e1ap_id_to_rnti = {};
std::map<uint32_t, uint32_t> edgeric::cu_up_ue_to_e1ap_id = {};

// PDCP metrics per UE per DRB (keyed by CU-UP ue_index, not RNTI)
std::map<edgeric::cu_up_drb_key, edgeric::pdcp_drb_metrics> edgeric::pdcp_metrics = {};

// GTP-U metrics per UE (N3 interface)
std::map<uint32_t, edgeric::gtp_ue_metrics> edgeric::gtp_metrics = {};

// std::map<uint16_t, float> edgeric::weights_recved = {};
std::map<uint16_t, float> edgeric::weights_recved = {};
//     {17921, 0.55f},  // Example: RNTI 1001 with a weight of 0.75
//     {17922, 0.45f}   // Example: RNTI 1002 with a weight of 0.85
// };

// std::map<uint16_t, uint8_t> edgeric::mcs_recved = {};
std::map<uint16_t, uint8_t> edgeric::mcs_recved = {};
//     {17921, 12},  // Example: RNTI 1001 with an MCS value of 12
//     {17922, 15}   // Example: RNTI 1002 with an MCS value of 18
// };

// Dynamic QoS overrides per UE per DRB (key = {rnti, lcid})
std::map<ue_drb_key, dynamic_qos_params> edgeric::qos_overrides = {};
uint32_t edgeric::er_ran_index_qos = 0;

bool edgeric::enable_logging = true; // Initialize logging flag to false
bool edgeric::initialized = false;

zmq::context_t context;
zmq::socket_t publisher(context, ZMQ_PUB);
zmq::socket_t subscriber_weights(context, ZMQ_SUB);
zmq::socket_t subscriber_mcs(context, ZMQ_SUB);
zmq::socket_t subscriber_qos(context, ZMQ_SUB);

void edgeric::init() {
    publisher.bind("ipc:///tmp/metrics");
    //publisher.bind("tcp://172.10.10.1:5050");

    subscriber_weights.connect("ipc:///tmp/control_weights_actions");
    //subscriber_weights.connect("tcp://172.10.10.2:5051");
    subscriber_weights.set(zmq::sockopt::subscribe, "");
    subscriber_weights.set(zmq::sockopt::conflate, 1);

    subscriber_mcs.connect("ipc:///tmp/control_mcs_actions");
    //subscriber_mcs.connect("tcp://172.10.10.2:5050");
    subscriber_mcs.set(zmq::sockopt::subscribe, "");
    subscriber_mcs.set(zmq::sockopt::conflate, 1);

    // QoS control subscriber
    subscriber_qos.connect("ipc:///tmp/control_qos_actions");
    subscriber_qos.set(zmq::sockopt::subscribe, "");
    subscriber_qos.set(zmq::sockopt::conflate, 1);

    initialized = true;
}

void edgeric::ensure_initialized() {
    if (!initialized) {
        init();
    }
}

void edgeric::send_to_er() {
    ensure_initialized();  // Ensure that the ZMQ sockets are initialized

    // Create a Metrics protobuf message
    Metrics metrics_msg;
    metrics_msg.set_tti_cnt(tti_cnt);

    // Populate the Metrics message with UeMetrics for each UE
    for (const auto& ue_cqi_pair : ue_cqis) {
        uint16_t rnti = ue_cqi_pair.first;

        UeMetrics* ue_metrics = metrics_msg.add_ue_metrics();
        ue_metrics->set_rnti(rnti);

        // Set CQI (from ue_cqis)
        ue_metrics->set_cqi(static_cast<uint32_t>(ue_cqi_pair.second));

        // Set SNR, default to 0 if not available
        auto snr_it = ue_snrs.find(rnti);
        ue_metrics->set_snr((snr_it != ue_snrs.end()) ? snr_it->second : 0.0f);

        // Set Tx Bytes, default to 0 if not available
        auto tx_bytes_it = tx_bytes.find(rnti);
        ue_metrics->set_tx_bytes((tx_bytes_it != tx_bytes.end()) ? tx_bytes_it->second : 0.0f);

        // Set Rx Bytes, default to 0 if not available
        auto rx_bytes_it = rx_bytes.find(rnti);
        ue_metrics->set_rx_bytes((rx_bytes_it != rx_bytes.end()) ? rx_bytes_it->second : 0.0f);

        // Set DL Buffer, default to 0 if not available
        auto dl_buffer_it = ue_dl_buffers.find(rnti);
        ue_metrics->set_dl_buffer((dl_buffer_it != ue_dl_buffers.end()) ? dl_buffer_it->second : 0);

        // Set UL Buffer, default to 0 if not available
        auto ul_buffer_it = ue_ul_buffers.find(rnti);
        ue_metrics->set_ul_buffer((ul_buffer_it != ue_ul_buffers.end()) ? ul_buffer_it->second : 0);

        // Set DL TBS, default to 0 if not available
        auto dl_tbs_it = dl_tbs_ues.find(rnti);
        ue_metrics->set_dl_tbs((dl_tbs_it != dl_tbs_ues.end()) ? dl_tbs_it->second : 0);

        // Set HARQ ACK/NACK counters
        auto dl_ok_it = dl_ok_cnt.find(rnti);
        ue_metrics->set_dl_ok((dl_ok_it != dl_ok_cnt.end()) ? dl_ok_it->second : 0);

        auto dl_nok_it = dl_nok_cnt.find(rnti);
        ue_metrics->set_dl_nok((dl_nok_it != dl_nok_cnt.end()) ? dl_nok_it->second : 0);

        auto ul_ok_it = ul_ok_cnt.find(rnti);
        ue_metrics->set_ul_ok((ul_ok_it != ul_ok_cnt.end()) ? ul_ok_it->second : 0);

        auto ul_nok_it = ul_nok_cnt.find(rnti);
        ue_metrics->set_ul_nok((ul_nok_it != ul_nok_cnt.end()) ? ul_nok_it->second : 0);
        
        // Add per-DRB metrics for this UE
        std::vector<uint8_t> lcids = get_drb_lcids(rnti);
        for (uint8_t lcid : lcids) {
            ue_drb_key key = {rnti, lcid};
            DrbMetrics* drb = ue_metrics->add_drb_metrics();
            drb->set_lcid(lcid);
            
            auto dl_buf_it = drb_dl_buffers.find(key);
            drb->set_dl_buffer((dl_buf_it != drb_dl_buffers.end()) ? dl_buf_it->second : 0);
            
            auto ul_buf_it = drb_ul_buffers.find(key);
            drb->set_ul_buffer((ul_buf_it != drb_ul_buffers.end()) ? ul_buf_it->second : 0);
            
            auto tx_it = drb_tx_bytes.find(key);
            drb->set_tx_bytes((tx_it != drb_tx_bytes.end()) ? tx_it->second : 0.0f);
            
            auto rx_it = drb_rx_bytes.find(key);
            drb->set_rx_bytes((rx_it != drb_rx_bytes.end()) ? rx_it->second : 0.0f);
        }
        
        // Note: PDCP and GTP metrics are keyed by CU-UP ue_index, not RNTI
        // They are logged separately in printmyvariables() but not added to protobuf
        // as we cannot correlate CU-UP ue_index with DU RNTI in split architecture
    }

    // Serialize the Metrics message to a string
    std::string serialized_msg;
    if (!metrics_msg.SerializeToString(&serialized_msg)) {
        std::cerr << "Failed to serialize Metrics message." << std::endl;
        return;
    }

    // Send the serialized message via ZMQ
    zmq::message_t zmq_msg(serialized_msg.size());
    memcpy(zmq_msg.data(), serialized_msg.data(), serialized_msg.size());

    publisher.send(zmq_msg, zmq::send_flags::dontwait);

    // Clear the maps after sending
    ue_cqis.clear();
    ue_snrs.clear();
    tx_bytes.clear();
    rx_bytes.clear();
    dl_tbs_ues.clear();
    // Clear HARQ counters each TTI
    dl_ok_cnt.clear();
    dl_nok_cnt.clear();
    ul_ok_cnt.clear();
    ul_nok_cnt.clear();
    // Clear per-DRB MAC/RLC metrics each TTI (from DU scheduler)
    drb_dl_buffers.clear();
    drb_ul_buffers.clear();
    drb_tx_bytes.clear();
    drb_rx_bytes.clear();
    // NOTE: Do NOT clear pdcp_metrics and gtp_metrics here!
    // They are reported asynchronously from CU-UP and not synced with scheduler TTI.
    // They will accumulate and be displayed each TTI until overwritten by next report.
    // ue_dl_buffers.clear();
    // ue_ul_buffers.clear();
}

// Get all DRB LCIDs for a given RNTI
std::vector<uint8_t> edgeric::get_drb_lcids(uint16_t rnti) {
    std::vector<uint8_t> lcids;
    std::set<uint8_t> lcid_set;  // Use set to avoid duplicates
    
    // Collect LCIDs from all per-DRB maps
    for (const auto& pair : drb_dl_buffers) {
        if (pair.first.first == rnti) {
            lcid_set.insert(pair.first.second);
        }
    }
    for (const auto& pair : drb_ul_buffers) {
        if (pair.first.first == rnti) {
            lcid_set.insert(pair.first.second);
        }
    }
    for (const auto& pair : drb_tx_bytes) {
        if (pair.first.first == rnti) {
            lcid_set.insert(pair.first.second);
        }
    }
    for (const auto& pair : drb_rx_bytes) {
        if (pair.first.first == rnti) {
            lcid_set.insert(pair.first.second);
        }
    }
    
    lcids.assign(lcid_set.begin(), lcid_set.end());
    return lcids;
}

// UE Index to RNTI mapping functions
void edgeric::register_ue(uint32_t ue_index, uint16_t rnti) {
    ue_index_to_rnti[ue_index] = rnti;
    std::ofstream logfile("log.txt", std::ios_base::app);
    if (logfile.is_open()) {
        logfile << "EdgeRIC: Registered UE index " << ue_index << " -> RNTI " << rnti << std::endl;
        logfile.close();
    }
}

void edgeric::unregister_ue(uint32_t ue_index) {
    ue_index_to_rnti.erase(ue_index);
}

uint16_t edgeric::get_rnti_from_ue_index(uint32_t ue_index) {
    auto it = ue_index_to_rnti.find(ue_index);
    return (it != ue_index_to_rnti.end()) ? it->second : 0;
}

uint32_t edgeric::get_ue_index_from_rnti(uint16_t rnti) {
    for (const auto& pair : ue_index_to_rnti) {
        if (pair.second == rnti) {
            return pair.first;
        }
    }
    return UINT32_MAX;
}

// E1AP-based CU-UP to RNTI correlation
void edgeric::register_e1ap_rnti(uint32_t gnb_cu_cp_ue_e1ap_id, uint16_t rnti) {
    e1ap_id_to_rnti[gnb_cu_cp_ue_e1ap_id] = rnti;
}

void edgeric::register_cu_up_ue_e1ap(uint32_t cu_up_ue_index, uint32_t gnb_cu_cp_ue_e1ap_id) {
    cu_up_ue_to_e1ap_id[cu_up_ue_index] = gnb_cu_cp_ue_e1ap_id;
}

uint16_t edgeric::get_rnti_from_cu_up_ue_index(uint32_t cu_up_ue_index) {
    // Step 1: Get the E1AP ID from CU-UP UE index
    auto e1ap_it = cu_up_ue_to_e1ap_id.find(cu_up_ue_index);
    if (e1ap_it == cu_up_ue_to_e1ap_id.end()) {
        return 0;  // CU-UP UE not registered
    }
    
    uint32_t e1ap_id = e1ap_it->second;
    
    // Step 2: Get the RNTI from E1AP ID
    auto rnti_it = e1ap_id_to_rnti.find(e1ap_id);
    if (rnti_it == e1ap_id_to_rnti.end()) {
        return 0;  // E1AP ID not mapped to RNTI yet
    }
    
    return rnti_it->second;
}

// PDCP metrics reporting
void edgeric::report_pdcp_metrics(uint32_t ue_index, uint8_t drb_id,
                                   uint32_t tx_pdus, uint32_t tx_pdu_bytes, uint32_t tx_dropped_sdus,
                                   uint32_t rx_pdus, uint32_t rx_pdu_bytes, uint32_t rx_dropped_pdus,
                                   uint32_t rx_delivered_sdus) {
    // Store by CU-UP ue_index directly (not RNTI, as CU-UP has different indices)
    cu_up_drb_key key = {ue_index, drb_id};
    pdcp_drb_metrics& m = pdcp_metrics[key];
    m.tx_pdus = tx_pdus;
    m.tx_pdu_bytes = tx_pdu_bytes;
    m.tx_dropped_sdus = tx_dropped_sdus;
    m.rx_pdus = rx_pdus;
    m.rx_pdu_bytes = rx_pdu_bytes;
    m.rx_dropped_pdus = rx_dropped_pdus;
    m.rx_delivered_sdus = rx_delivered_sdus;
}

std::vector<uint8_t> edgeric::get_pdcp_drb_ids(uint16_t rnti) {
    // This function is deprecated - PDCP metrics are now keyed by ue_index
    // Return empty for now
    return {};
}

std::vector<uint8_t> edgeric::get_pdcp_drb_ids_by_ue_index(uint32_t ue_index) {
    std::vector<uint8_t> drb_ids;
    std::set<uint8_t> drb_id_set;
    
    for (const auto& pair : pdcp_metrics) {
        if (pair.first.first == ue_index) {
            drb_id_set.insert(pair.first.second);
        }
    }
    
    drb_ids.assign(drb_id_set.begin(), drb_id_set.end());
    return drb_ids;
}

// GTP-U metrics reporting
void edgeric::report_gtp_dl_pkt(uint32_t ue_index, uint32_t pdu_len) {
    gtp_ue_metrics& m = gtp_metrics[ue_index];
    m.dl_pkts++;
    m.dl_bytes += pdu_len;
}

void edgeric::report_gtp_ul_pkt(uint32_t ue_index, uint32_t pdu_len) {
    gtp_ue_metrics& m = gtp_metrics[ue_index];
    m.ul_pkts++;
    m.ul_bytes += pdu_len;
}

std::optional<edgeric::gtp_ue_metrics> edgeric::get_gtp_metrics(uint16_t rnti) {
    // Need to find ue_index from rnti
    uint32_t ue_index = get_ue_index_from_rnti(rnti);
    if (ue_index == UINT32_MAX) {
        return std::nullopt;
    }
    auto it = gtp_metrics.find(ue_index);
    if (it != gtp_metrics.end()) {
        return it->second;
    }
    return std::nullopt;
}

// Get weights function
std::optional<float> edgeric::get_weights(uint16_t rnti) {
    if (weights_recved.empty()) {
        return std::nullopt;  // Return no value if the map is empty
    }

    auto it = weights_recved.find(rnti);
    if (it != weights_recved.end()) {
        return it->second;  // Return the weight if the RNTI is found
    } else {
        return std::nullopt;  // Return no value if the RNTI is not found
    }
}

std::optional<uint8_t> edgeric::get_mcs(uint16_t rnti) {
    if (mcs_recved.empty()) {
        return std::nullopt;  // Return no value if the map is empty
    }

    auto it = mcs_recved.find(rnti);
    if (it != mcs_recved.end()) {
        return it->second;  // Return the weight if the RNTI is found
    } else {
        return std::nullopt;  // Return no value if the RNTI is not found
    }
}

void edgeric::printmyvariables() {
    if (enable_logging) { // Check if logging is enabled
        std::ofstream logfile("log.txt", std::ios_base::app); // Open log file in append mode
        if (logfile.is_open()) {
            logfile << "========== TTI: " << tti_cnt << " ==========" << std::endl;

            for (const auto& cqi_pair : ue_cqis) {
                auto rnti = cqi_pair.first;

                // Fetch UE-level metrics
                float weight = (weights_recved.count(rnti) > 0) ? weights_recved.at(rnti) : 0;
                int mcs = (mcs_recved.count(rnti) > 0) ? static_cast<int>(mcs_recved.at(rnti)) : 0;
                int cqi = static_cast<int>(cqi_pair.second);
                int snr = (ue_snrs.count(rnti) > 0) ? static_cast<int>(ue_snrs.at(rnti)) : 0;
                int rx_byte = (rx_bytes.count(rnti) > 0) ? static_cast<int>(rx_bytes.at(rnti)) : 0;
                int tx_byte = (tx_bytes.count(rnti) > 0) ? static_cast<int>(tx_bytes.at(rnti)) : 0;
                int ul_buffer = (ue_ul_buffers.count(rnti) > 0) ? static_cast<int>(ue_ul_buffers.at(rnti)) : 0;
                int dl_buffer = (ue_dl_buffers.count(rnti) > 0) ? static_cast<int>(ue_dl_buffers.at(rnti)) : 0;
                float dl_tbs = (dl_tbs_ues.count(rnti) > 0) ? static_cast<int>(dl_tbs_ues.at(rnti)) : 0;
                // HARQ counters
                uint32_t dl_ok = (dl_ok_cnt.count(rnti) > 0) ? dl_ok_cnt.at(rnti) : 0;
                uint32_t dl_nok = (dl_nok_cnt.count(rnti) > 0) ? dl_nok_cnt.at(rnti) : 0;
                uint32_t ul_ok = (ul_ok_cnt.count(rnti) > 0) ? ul_ok_cnt.at(rnti) : 0;
                uint32_t ul_nok = (ul_nok_cnt.count(rnti) > 0) ? ul_nok_cnt.at(rnti) : 0;

                // Print UE header with PHY/aggregate metrics
                logfile << "  RNTI: " << rnti << std::endl;
                logfile << "    PHY: CQI=" << cqi << " SNR=" << snr 
                        << " MCS=" << mcs << " Weights=" << weight << std::endl;
                logfile << "    HARQ: DL_OK=" << dl_ok << " DL_NOK=" << dl_nok 
                        << " UL_OK=" << ul_ok << " UL_NOK=" << ul_nok << std::endl;
                logfile << "    Aggregate: TX=" << tx_byte << " RX=" << rx_byte 
                        << " DL_BUF=" << dl_buffer << " UL_BUF=" << ul_buffer 
                        << " TBS=" << static_cast<int>(dl_tbs) << std::endl;
                
                // Collect all DRBs for this UE from MAC/RLC layer
                std::set<uint8_t> all_drbs;
                std::vector<uint8_t> lcids = get_drb_lcids(rnti);
                
                // MAC uses LCID (4+ for DRBs), convert to DRB ID
                // LCID = DRB_ID + 3 typically (LCID 4 = DRB 1, LCID 5 = DRB 2, etc.)
                for (uint8_t lcid : lcids) {
                    if (lcid >= 4) {  // Skip SRBs (LCID 0-3)
                        all_drbs.insert(lcid - 3);  // Convert LCID to DRB ID
                    } else {
                        all_drbs.insert(lcid);  // For LCG-based UL (0-7), keep as-is
                    }
                }
                
                // Log per-DRB MAC/RLC metrics (PDCP/GTP logged separately below by CU-UP UE index)
                for (uint8_t drb_id : all_drbs) {
                    logfile << "    DRB " << static_cast<int>(drb_id) << ":" << std::endl;
                    
                    // MAC/RLC metrics (using LCID = DRB_ID + 3 for DRBs, or direct for LCG)
                    uint8_t lcid = (drb_id >= 1 && drb_id <= 29) ? (drb_id + 3) : drb_id;
                    ue_drb_key mac_key = {rnti, lcid};
                    uint32_t drb_dl_buf = (drb_dl_buffers.count(mac_key) > 0) ? drb_dl_buffers.at(mac_key) : 0;
                    uint32_t drb_ul_buf = (drb_ul_buffers.count({rnti, drb_id}) > 0) ? drb_ul_buffers.at({rnti, drb_id}) : 0;
                    float drb_tx = (drb_tx_bytes.count(mac_key) > 0) ? drb_tx_bytes.at(mac_key) : 0.0f;
                    float drb_rx = (drb_rx_bytes.count(mac_key) > 0) ? drb_rx_bytes.at(mac_key) : 0.0f;
                    
                    logfile << "      MAC/RLC: TX=" << static_cast<int>(drb_tx) 
                            << " RX=" << static_cast<int>(drb_rx)
                            << " DL_BUF=" << drb_dl_buf 
                            << " UL_BUF=" << drb_ul_buf << std::endl;
                }
                
            }
            
            // Output CU-UP metrics separately (PDCP/GTP keyed by CU-UP UE index)
            // These use different UE indices than DU/scheduler, so output separately
            // Debug: always show section header with counts
            logfile << "  --- CU-UP Metrics (PDCP=" << pdcp_metrics.size() 
                    << " GTP=" << gtp_metrics.size() << ") ---" << std::endl;
            
            // Collect all CU-UP UE indices with metrics
            std::set<uint32_t> cu_up_ue_indices;
            for (const auto& p : pdcp_metrics) {
                cu_up_ue_indices.insert(p.first.first);  // key = (ue_index, drb_id)
            }
            for (const auto& g : gtp_metrics) {
                cu_up_ue_indices.insert(g.first);  // key is ue_index
            }
            
            for (uint32_t ue_idx : cu_up_ue_indices) {
                uint16_t rnti = get_rnti_from_cu_up_ue_index(ue_idx);
                logfile << "  CU-UP UE_IDX=" << ue_idx;
                if (rnti != 0) {
                    logfile << " (RNTI=" << rnti << ")";
                }
                logfile << std::endl;
                
                // PDCP metrics for this UE (iterate over all DRBs)
                std::vector<uint8_t> drb_ids = get_pdcp_drb_ids_by_ue_index(ue_idx);
                for (uint8_t drb_id : drb_ids) {
                    cu_up_drb_key key = {ue_idx, drb_id};
                    auto pm_it = pdcp_metrics.find(key);
                    if (pm_it != pdcp_metrics.end()) {
                        const pdcp_drb_metrics& m = pm_it->second;
                        logfile << "    PDCP DRB" << static_cast<int>(drb_id)
                                << ": TX_PDUs=" << m.tx_pdus
                                << " TX_Bytes=" << m.tx_pdu_bytes
                                << " TX_Drop=" << m.tx_dropped_sdus
                                << " RX_PDUs=" << m.rx_pdus
                                << " RX_Bytes=" << m.rx_pdu_bytes
                                << " RX_Drop=" << m.rx_dropped_pdus
                                << " RX_SDUs=" << m.rx_delivered_sdus << std::endl;
                    }
                }
                
                // GTP metrics for this UE
                auto gtp_it = gtp_metrics.find(ue_idx);
                if (gtp_it != gtp_metrics.end()) {
                    const gtp_ue_metrics& gm = gtp_it->second;
                    logfile << "    GTP-U: DL_Pkts=" << gm.dl_pkts
                            << " DL_Bytes=" << gm.dl_bytes
                            << " UL_Pkts=" << gm.ul_pkts
                            << " UL_Bytes=" << gm.ul_bytes << std::endl;
                }
            }

            logfile.close();
        } else {
            std::cerr << "Unable to open log file" << std::endl;
        }
    }
}




// void edgeric::get_weights_from_er()
// {
//     ensure_initialized();  // Ensure that the ZMQ sockets are initialized

//     // Check for message on the weights subscriber
//     zmq::message_t recv_message_er;
//     zmq::recv_result_t size = subscriber_weights.recv(recv_message_er, zmq::recv_flags::dontwait);

//     if (size) {
//         SchedulingWeights weights_msg;
//         if (weights_msg.ParseFromArray(recv_message_er.data(), recv_message_er.size())) {
//             er_ran_index_weights = weights_msg.ran_index();
//             for (int i = 0; i < weights_msg.weights_size(); i += 2) {
//                 uint16_t rnti = static_cast<uint16_t>(weights_msg.weights(i));
//                 float weight = weights_msg.weights(i + 1);
//                 weights_recved[rnti] = weight;
//             }
//         } else {
//             std::cerr << "Failed to parse SchedulingWeights message." << std::endl;
//         }
//     } else {
//         weights_recved.clear();  // Clear weights as no valid data was received
//         // weights_recved = {
//         //         {17921, 0.5f},  // Example: RNTI 1001 with a weight of 0.75
//         //         {17922, 0.5f}   // Example: RNTI 1002 with a weight of 0.85
//         //     };
        
//     }

//     // // Immediately check for message on the MCS subscriber
//     // zmq::message_t recv_message_er2;
//     // zmq::recv_result_t size2 = subscriber_mcs.recv(recv_message_er2, zmq::recv_flags::dontwait);

//     // if (size2) {
//     //     mcs_control mcs_msg;
//     //     if (mcs_msg.ParseFromArray(recv_message_er2.data(), recv_message_er2.size())) {
//     //         er_ran_index_mcs = mcs_msg.ran_index();
//     //         for (int i = 0; i < mcs_msg.mcs_size(); i += 2) {
//     //             uint16_t rnti = static_cast<uint16_t>(mcs_msg.mcs(i));
//     //             uint8_t mcs = mcs_msg.mcs(i + 1);
//     //             mcs_recved[rnti] = mcs;
//     //         }
//     //     } else {
//     //         std::cerr << "Failed to parse mcs_control message." << std::endl;
//     //     }
//     // } else {
//     //     // mcs_recved.clear();  // Clear weights as no valid data was received
//     //     mcs_recved = {
//     //             {17921, 18},  // Example: RNTI 1001 with a weight of 0.75
//     //             {17922, 10}   // Example: RNTI 1002 with a weight of 0.85
//     //         };
        
//     // }
// }
void edgeric::get_weights_from_er()
{
    ensure_initialized();  // Ensure that the ZMQ sockets are initialized

    // Check for message on the weights subscriber
    zmq::message_t recv_message_er;
    zmq::recv_result_t size = subscriber_weights.recv(recv_message_er, zmq::recv_flags::dontwait);

    if (size) {
        SchedulingWeights weights_msg;
        if (weights_msg.ParseFromArray(recv_message_er.data(), recv_message_er.size())) {
            er_ran_index_weights = weights_msg.ran_index();
            
            float total_weight = 0.0f;

            // First, store the weights and calculate the total weight
            for (int i = 0; i < weights_msg.weights_size(); i += 2) {
                uint16_t rnti = static_cast<uint16_t>(weights_msg.weights(i));
                float weight = weights_msg.weights(i + 1);
                weights_recved[rnti] = weight;
                total_weight += weight;
            }

            // Normalize the weights so that the sum is 1
            if (total_weight > 0.0f) {
                for (auto& pair : weights_recved) {
                    pair.second /= total_weight;
                }
            } else {
                std::cerr << "Total weight is zero, cannot normalize." << std::endl;
            }

        } else {
            std::cerr << "Failed to parse SchedulingWeights message." << std::endl;
        }
    } else {
        weights_recved.clear();  // Clear weights as no valid data was received
        // weights_recved = {
        //         {17921, 0.5f},  // Example: RNTI 1001 with a weight of 0.75
        //         {17922, 0.5f}   // Example: RNTI 1002 with a weight of 0.85
        //     };
    }
}

// void edgeric::get_weights_from_er()
// {
//     ensure_initialized();  // Ensure that the ZMQ sockets are initialized
//     zmq::message_t recv_message_er;
//     zmq::recv_result_t size = subscriber_weights.recv(recv_message_er, zmq::recv_flags::dontwait);

//     if (size) {
//         // Deserialize the received message into a SchedulingWeights protobuf object
//         SchedulingWeights weights_msg;
//         if (weights_msg.ParseFromArray(recv_message_er.data(), recv_message_er.size())) {

//             // Successfully parsed the protobuf message
//             er_ran_index_weights = weights_msg.ran_index();

//             // Update the weights_recved map with the received values
//                 for (int i = 0; i < weights_msg.weights_size(); i += 2) {
//                     uint16_t rnti = static_cast<uint16_t>(weights_msg.weights(i));
//                     float weight = weights_msg.weights(i + 1);
//                     weights_recved[rnti] = weight;
//                 }

//         } else {
//             std::cerr << "Failed to parse SchedulingWeights message." << std::endl;
//         }
//     } else {
//         // weights_recved.clear();  // Clear weights as no valid data was received
//         weights_recved = {
//                 {17921, 0.75f},  // Example: RNTI 1001 with a weight of 0.75
//                 {17922, 0.25f}   // Example: RNTI 1002 with a weight of 0.85
//             };
        
//     }



//     zmq::message_t recv_message_er2;
//     zmq::recv_result_t size2 = subscriber_mcs.recv(recv_message_er2, zmq::recv_flags::dontwait);

//     if (size2) {
//         // Deserialize the received message into a SchedulingWeights protobuf object
//         mcs_control mcs_msg;
//         if (mcs_msg.ParseFromArray(recv_message_er2.data(), recv_message_er2.size())) {

//             // Successfully parsed the protobuf message
//             er_ran_index_mcs = mcs_msg.ran_index();

//             // Update the weights_recved map with the received values
//                 for (int i = 0; i < mcs_msg.mcs_size(); i += 2) {
//                     uint16_t rnti = static_cast<uint16_t>(mcs_msg.mcs(i));
//                     uint8_t mcs = mcs_msg.mcs(i + 1);
//                     mcs_recved[rnti] = mcs;
//                 }

//         } else {
//             std::cerr << "Failed to parse SchedulingWeights message." << std::endl;
//         }
//     } else {
//         // mcs_recved.clear();  // Clear weights as no valid data was received
//         mcs_recved = {
//                 {17921, 18},  // Example: RNTI 1001 with a weight of 0.75
//                 {17922, 10}   // Example: RNTI 1002 with a weight of 0.85
//             };
        
//     }
// }

void edgeric::get_mcs_from_er()
{
    ensure_initialized();  // Ensure that the ZMQ sockets are initialized
    zmq::message_t recv_message_er;
    zmq::recv_result_t size = subscriber_mcs.recv(recv_message_er, zmq::recv_flags::dontwait);

    if (size) {
        // Deserialize the received message into a SchedulingWeights protobuf object
        mcs_control mcs_msg;
        if (mcs_msg.ParseFromArray(recv_message_er.data(), recv_message_er.size())) {

            // Successfully parsed the protobuf message
            er_ran_index_mcs = mcs_msg.ran_index();

            // Update the weights_recved map with the received values
                for (int i = 0; i < mcs_msg.mcs_size(); i += 2) {
                    uint16_t rnti = static_cast<uint16_t>(mcs_msg.mcs(i));
                    uint8_t mcs = mcs_msg.mcs(i + 1);
                    mcs_recved[rnti] = mcs;
                }

        } else {
            std::cerr << "Failed to parse SchedulingWeights message." << std::endl;
        }
    } else {
        mcs_recved.clear();  // Clear weights as no valid data was received
        // mcs_recved = {
        //         {17921, 18},  // Example: RNTI 1001 with a weight of 0.75
        //         {17922, 10}   // Example: RNTI 1002 with a weight of 0.85
        //     };
        
    }
}

//////////////////////////////////////////////////////////////////////////////
// Dynamic QoS Control Implementation (Per-UE, Per-DRB)
//////////////////////////////////////////////////////////////////////////////

void edgeric::set_dynamic_qos(uint16_t rnti, uint8_t lcid, const dynamic_qos_params& params) {
    ue_drb_key key = {rnti, lcid};
    qos_overrides[key] = params;
}

void edgeric::clear_dynamic_qos(uint16_t rnti, uint8_t lcid) {
    ue_drb_key key = {rnti, lcid};
    qos_overrides.erase(key);
}

void edgeric::clear_all_dynamic_qos(uint16_t rnti) {
    // Remove all DRBs for this UE
    for (auto it = qos_overrides.begin(); it != qos_overrides.end(); ) {
        if (it->first.first == rnti) {
            it = qos_overrides.erase(it);
        } else {
            ++it;
        }
    }
}

std::optional<dynamic_qos_params> edgeric::get_dynamic_qos(uint16_t rnti, uint8_t lcid) {
    ue_drb_key key = {rnti, lcid};
    auto it = qos_overrides.find(key);
    if (it != qos_overrides.end()) {
        return it->second;
    }
    return std::nullopt;
}

void edgeric::set_qos_priority(uint16_t rnti, uint8_t lcid, uint8_t priority) {
    ue_drb_key key = {rnti, lcid};
    auto& params = qos_overrides[key];
    params.qos_priority = priority;
    params.override_qos_priority = true;
}

void edgeric::set_arp_priority(uint16_t rnti, uint8_t lcid, uint8_t arp) {
    ue_drb_key key = {rnti, lcid};
    auto& params = qos_overrides[key];
    params.arp_priority = arp;
    params.override_arp_priority = true;
}

void edgeric::set_pdb(uint16_t rnti, uint8_t lcid, uint32_t pdb_ms) {
    ue_drb_key key = {rnti, lcid};
    auto& params = qos_overrides[key];
    params.pdb_ms = pdb_ms;
    params.override_pdb = true;
}

void edgeric::set_gbr(uint16_t rnti, uint8_t lcid, uint64_t gbr_dl, uint64_t gbr_ul) {
    ue_drb_key key = {rnti, lcid};
    auto& params = qos_overrides[key];
    params.gbr_dl = gbr_dl;
    params.gbr_ul = gbr_ul;
    params.override_gbr = true;
}

std::optional<uint8_t> edgeric::get_qos_priority(uint16_t rnti, uint8_t lcid) {
    ue_drb_key key = {rnti, lcid};
    auto it = qos_overrides.find(key);
    if (it != qos_overrides.end() && it->second.override_qos_priority) {
        return it->second.qos_priority;
    }
    return std::nullopt;
}

std::optional<uint8_t> edgeric::get_arp_priority(uint16_t rnti, uint8_t lcid) {
    ue_drb_key key = {rnti, lcid};
    auto it = qos_overrides.find(key);
    if (it != qos_overrides.end() && it->second.override_arp_priority) {
        return it->second.arp_priority;
    }
    return std::nullopt;
}

std::optional<uint32_t> edgeric::get_pdb(uint16_t rnti, uint8_t lcid) {
    ue_drb_key key = {rnti, lcid};
    auto it = qos_overrides.find(key);
    if (it != qos_overrides.end() && it->second.override_pdb) {
        return it->second.pdb_ms;
    }
    return std::nullopt;
}

std::optional<uint64_t> edgeric::get_gbr_dl(uint16_t rnti, uint8_t lcid) {
    ue_drb_key key = {rnti, lcid};
    auto it = qos_overrides.find(key);
    if (it != qos_overrides.end() && it->second.override_gbr) {
        return it->second.gbr_dl;
    }
    return std::nullopt;
}

std::optional<uint64_t> edgeric::get_gbr_ul(uint16_t rnti, uint8_t lcid) {
    ue_drb_key key = {rnti, lcid};
    auto it = qos_overrides.find(key);
    if (it != qos_overrides.end() && it->second.override_gbr) {
        return it->second.gbr_ul;
    }
    return std::nullopt;
}

void edgeric::get_qos_from_er() {
    ensure_initialized();
    
    zmq::message_t recv_message;
    zmq::recv_result_t size = subscriber_qos.recv(recv_message, zmq::recv_flags::dontwait);
    
    if (size) {
        // Parse the QoS control protobuf message
        QosControl qos_msg;
        if (qos_msg.ParseFromArray(recv_message.data(), recv_message.size())) {
            er_ran_index_qos = qos_msg.ran_index();
            
            // Log received QoS control message
            if (enable_logging) {
                std::ofstream logfile("log.txt", std::ios_base::app);
                if (logfile.is_open()) {
                    logfile << "QoS Control Received (ran_index=" << er_ran_index_qos 
                            << ", TTI=" << tti_cnt << ")" << std::endl;
                    logfile.close();
                }
            }
            
            // Process each DRB QoS override
            for (int i = 0; i < qos_msg.drb_qos_size(); ++i) {
                const DrbQosParams& drb = qos_msg.drb_qos(i);
                uint16_t rnti = static_cast<uint16_t>(drb.rnti());
                uint8_t lcid = static_cast<uint8_t>(drb.lcid());
                ue_drb_key key = {rnti, lcid};
                
                if (drb.clear_override()) {
                    // Clear the override for this DRB
                    qos_overrides.erase(key);
                } else {
                    // Apply the overrides
                    auto& params = qos_overrides[key];
                    
                    if (drb.has_qos_priority()) {
                        params.qos_priority = static_cast<uint8_t>(drb.qos_priority());
                        params.override_qos_priority = true;
                    }
                    if (drb.has_arp_priority()) {
                        params.arp_priority = static_cast<uint8_t>(drb.arp_priority());
                        params.override_arp_priority = true;
                    }
                    if (drb.has_pdb_ms()) {
                        params.pdb_ms = drb.pdb_ms();
                        params.override_pdb = true;
                    }
                    if (drb.has_gbr_dl() || drb.has_gbr_ul()) {
                        if (drb.has_gbr_dl()) {
                            params.gbr_dl = drb.gbr_dl();
                        }
                        if (drb.has_gbr_ul()) {
                            params.gbr_ul = drb.gbr_ul();
                        }
                        params.override_gbr = true;
                    }
                }
            }
        } else {
            std::cerr << "Failed to parse QosControl message." << std::endl;
        }
    }
    // If no message received, keep existing overrides (they persist until cleared)
}

//////////////////////////////////////////////////////////////////////////////
// Centralized Telemetry Collection
//////////////////////////////////////////////////////////////////////////////

void edgeric::collect_ue_telemetry(uint16_t rnti, float cqi, float snr, 
                                    uint32_t dl_buffer_bytes, uint32_t ul_buffer_bytes) {
    // Store metrics in the static maps - these will be logged via printmyvariables()
    // and sent via send_to_er() which are already called in cell_scheduler::run_slot()
    ue_cqis[rnti] = cqi;
    ue_snrs[rnti] = snr;
    ue_dl_buffers[rnti] = dl_buffer_bytes;
    ue_ul_buffers[rnti] = ul_buffer_bytes;
}