#include "edgeric.h"
#include <set>
#include <algorithm>
#include <chrono>

//==============================================================================
// Static Member Definitions
//==============================================================================

// TTI counter
uint32_t edgeric::tti_cnt = 0;

// Control indices
uint32_t edgeric::er_ran_index_weights = 0;
uint32_t edgeric::er_ran_index_mcs = 0;
uint32_t edgeric::er_ran_index_qos = 0;

// Logging flag
bool edgeric::enable_logging = false;
bool edgeric::initialized = false;

// Control maps
std::map<uint16_t, float> edgeric::weights_recved = {};
std::map<uint16_t, uint8_t> edgeric::mcs_recved = {};
std::map<ue_drb_key, dynamic_qos_params> edgeric::qos_overrides = {};

// MAC metrics
std::map<uint16_t, mac_ue_metrics> edgeric::mac_ue = {};
std::map<ue_drb_key, mac_drb_metrics> edgeric::mac_drb = {};

// RLC metrics
std::map<ue_drb_key, rlc_drb_metrics> edgeric::rlc_drb = {};
std::mutex edgeric::rlc_mutex;

// PDCP metrics
std::map<edgeric::cu_up_drb_key, pdcp_drb_metrics> edgeric::pdcp_drb = {};
std::mutex edgeric::pdcp_mutex;

// GTP metrics
std::map<uint32_t, gtp_ue_metrics> edgeric::gtp_ue = {};
std::mutex edgeric::gtp_mutex;

// UE ID correlation maps
std::map<uint32_t, uint16_t> edgeric::ue_index_to_rnti = {};
std::map<uint32_t, uint16_t> edgeric::e1ap_id_to_rnti = {};
std::map<uint32_t, uint32_t> edgeric::cu_up_ue_to_e1ap_id = {};
std::map<uint32_t, uint16_t> edgeric::du_ue_to_rnti = {};
std::mutex edgeric::du_ue_mutex;

//==============================================================================
// ZMQ Sockets (file-scope)
//==============================================================================

static zmq::context_t context(1);
static zmq::socket_t publisher(context, ZMQ_PUB);
static zmq::socket_t subscriber_weights(context, ZMQ_SUB);
static zmq::socket_t subscriber_mcs(context, ZMQ_SUB);
static zmq::socket_t subscriber_qos(context, ZMQ_SUB);

//==============================================================================
// Initialization
//==============================================================================

void edgeric::init() {
    if (initialized) return;
    
    // Publisher for metrics (conflate mode - only keep latest)
    publisher.set(zmq::sockopt::sndhwm, 1);    // Minimal queue
    publisher.set(zmq::sockopt::conflate, 1);  // Only keep latest message
    publisher.bind("ipc:///tmp/metrics_data");
    
    // Subscriber for weights
    subscriber_weights.connect("ipc:///tmp/control_weights");
    subscriber_weights.set(zmq::sockopt::subscribe, "");
    subscriber_weights.set(zmq::sockopt::conflate, 1);

    // Subscriber for MCS
    subscriber_mcs.connect("ipc:///tmp/control_mcs");
    subscriber_mcs.set(zmq::sockopt::subscribe, "");
    subscriber_mcs.set(zmq::sockopt::conflate, 1);

    // Subscriber for QoS
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

//==============================================================================
// MAC Metrics (scheduler thread - no locking)
//==============================================================================

void edgeric::set_mac_ue(uint16_t rnti, uint32_t cqi, float snr,
                         uint32_t dl_buffer, uint32_t ul_buffer,
                         uint32_t dl_tbs, uint32_t ul_tbs) {
    auto& m = mac_ue[rnti];
    m.cqi = cqi;
    m.snr = snr;
    m.dl_buffer = dl_buffer;
    m.ul_buffer = ul_buffer;
    m.dl_tbs = dl_tbs;
    m.ul_tbs = ul_tbs;
}

void edgeric::set_mac_drb(uint16_t rnti, uint8_t lcid,
                          uint32_t dl_buffer, uint32_t ul_buffer,
                          uint32_t dl_bytes, uint32_t ul_bytes) {
    auto& m = mac_drb[{rnti, lcid}];
    m.dl_buffer = dl_buffer;
    m.ul_buffer = ul_buffer;
    m.dl_bytes = dl_bytes;
    m.ul_bytes = ul_bytes;
}

void edgeric::add_mac_drb_dl_bytes(uint16_t rnti, uint8_t lcid, uint32_t bytes) {
    mac_drb[{rnti, lcid}].dl_bytes += bytes;
}

void edgeric::add_mac_drb_ul_bytes(uint16_t rnti, uint8_t lcid, uint32_t bytes) {
    mac_drb[{rnti, lcid}].ul_bytes += bytes;
}

void edgeric::set_tx_bytes(uint16_t rnti, float tbs) {
    mac_ue[rnti].dl_tbs += static_cast<uint32_t>(tbs);
}

void edgeric::set_rx_bytes(uint16_t rnti, float tbs) {
    mac_ue[rnti].ul_tbs += static_cast<uint32_t>(tbs);
}

void edgeric::set_dl_tbs(uint16_t rnti, uint32_t tbs) {
    mac_ue[rnti].dl_tbs += tbs;  // ACCUMULATE instead of overwrite!
}

void edgeric::set_ul_tbs(uint16_t rnti, uint32_t tbs) {
    mac_ue[rnti].ul_tbs += tbs;  // Accumulate
}

void edgeric::set_dl_mcs(uint16_t rnti, uint32_t mcs) {
    // Use max - multiple allocations may use different MCS
    if (mcs > mac_ue[rnti].dl_mcs) mac_ue[rnti].dl_mcs = mcs;
}

void edgeric::set_ul_mcs(uint16_t rnti, uint32_t mcs) {
    if (mcs > mac_ue[rnti].ul_mcs) mac_ue[rnti].ul_mcs = mcs;
}

void edgeric::set_dl_prbs(uint16_t rnti, uint32_t prbs) {
    mac_ue[rnti].dl_prbs += prbs;  // Accumulate
}

void edgeric::set_ul_prbs(uint16_t rnti, uint32_t prbs) {
    mac_ue[rnti].ul_prbs += prbs;  // Accumulate
}

//==============================================================================
// RLC Metrics (RLC thread - needs locking)
//==============================================================================

void edgeric::report_rlc_metrics(uint32_t du_ue_index, uint8_t lcid,
                                 const rlc_drb_metrics& metrics) {
    std::lock_guard<std::mutex> lock(rlc_mutex);
    
    // Look up RNTI from DU UE index
    auto it = du_ue_to_rnti.find(du_ue_index);
    if (it == du_ue_to_rnti.end()) return;
    
    uint16_t rnti = it->second;
    rlc_drb[{rnti, lcid}] = metrics;
}

void edgeric::register_du_ue(uint32_t du_ue_index, uint16_t rnti) {
    std::lock_guard<std::mutex> lock(du_ue_mutex);
    du_ue_to_rnti[du_ue_index] = rnti;
}

//==============================================================================
// PDCP Metrics (CU-UP thread - needs locking)
//==============================================================================

void edgeric::report_pdcp_metrics(uint32_t cu_up_ue_index, uint8_t drb_id,
                                  const pdcp_drb_metrics& metrics) {
    std::lock_guard<std::mutex> lock(pdcp_mutex);
    pdcp_drb[{cu_up_ue_index, drb_id}] = metrics;
}

//==============================================================================
// GTP Metrics (CU-UP thread - needs locking)
//==============================================================================

void edgeric::report_gtp_dl_pkt(uint32_t cu_up_ue_index, uint32_t pdu_len) {
    std::lock_guard<std::mutex> lock(gtp_mutex);
    auto& m = gtp_ue[cu_up_ue_index];
    m.dl_pkts++;
    m.dl_bytes += pdu_len;
}

void edgeric::report_gtp_ul_pkt(uint32_t cu_up_ue_index, uint32_t pdu_len) {
    std::lock_guard<std::mutex> lock(gtp_mutex);
    auto& m = gtp_ue[cu_up_ue_index];
    m.ul_pkts++;
    m.ul_bytes += pdu_len;
}

//==============================================================================
// UE ID Correlation
//==============================================================================

void edgeric::register_ue(uint32_t ue_index, uint16_t rnti) {
    ue_index_to_rnti[ue_index] = rnti;
}

void edgeric::unregister_ue(uint32_t ue_index) {
    ue_index_to_rnti.erase(ue_index);
}

uint16_t edgeric::get_rnti_from_ue_index(uint32_t ue_index) {
    auto it = ue_index_to_rnti.find(ue_index);
    return (it != ue_index_to_rnti.end()) ? it->second : 0;
}

void edgeric::register_e1ap_rnti(uint32_t e1ap_id, uint16_t rnti) {
    e1ap_id_to_rnti[e1ap_id] = rnti;
}

void edgeric::register_cu_up_ue_e1ap(uint32_t cu_up_ue_index, uint32_t e1ap_id) {
    cu_up_ue_to_e1ap_id[cu_up_ue_index] = e1ap_id;
}

uint16_t edgeric::get_rnti_from_cu_up_ue_index(uint32_t cu_up_ue_index) {
    // Try E1AP correlation first
    auto it1 = cu_up_ue_to_e1ap_id.find(cu_up_ue_index);
    if (it1 != cu_up_ue_to_e1ap_id.end()) {
        auto it2 = e1ap_id_to_rnti.find(it1->second);
        if (it2 != e1ap_id_to_rnti.end()) {
            return it2->second;
        }
    }
    
    // Fallback 1: Try ue_index_to_rnti (CU-CP)
    if (!ue_index_to_rnti.empty()) {
        std::vector<std::pair<uint32_t, uint16_t>> sorted_ues(
            ue_index_to_rnti.begin(), ue_index_to_rnti.end());
        std::sort(sorted_ues.begin(), sorted_ues.end());
        
        if (cu_up_ue_index < sorted_ues.size()) {
            return sorted_ues[cu_up_ue_index].second;
        }
    }
    
    // Fallback 2: Try mac_ue (scheduler - indexed by RNTI directly)
    if (!mac_ue.empty()) {
        std::vector<uint16_t> sorted_rntis;
        for (const auto& [rnti, _] : mac_ue) {
            sorted_rntis.push_back(rnti);
        }
        std::sort(sorted_rntis.begin(), sorted_rntis.end());
        
        if (cu_up_ue_index < sorted_rntis.size()) {
            return sorted_rntis[cu_up_ue_index];
        }
    }
    
    return 0;
}

//==============================================================================
// Per-TTI Metrics Export (main function)
//==============================================================================

void edgeric::send_tti_metrics() {
    ensure_initialized();
    
    // Build TtiMetrics protobuf message
    TtiMetrics tti_msg;
    tti_msg.set_tti_index(getTtiIndex());
    
    // Timestamp in microseconds
    auto now = std::chrono::system_clock::now();
    auto us = std::chrono::duration_cast<std::chrono::microseconds>(
        now.time_since_epoch()).count();
    tti_msg.set_timestamp_us(static_cast<uint64_t>(us));
    
    // Collect unique RNTIs from MAC metrics
    std::set<uint16_t> active_rntis;
    for (const auto& [rnti, _] : mac_ue) {
        active_rntis.insert(rnti);
    }
    
    // Build per-UE metrics
    for (uint16_t rnti : active_rntis) {
        UeMetrics* ue_msg = tti_msg.add_ues();
        ue_msg->set_rnti(rnti);
        
        // MAC aggregate metrics
        auto mac_it = mac_ue.find(rnti);
        if (mac_it != mac_ue.end()) {
            MacUeMetrics* mac_msg = ue_msg->mutable_mac();
            mac_msg->set_cqi(mac_it->second.cqi);
            mac_msg->set_snr(mac_it->second.snr);
            mac_msg->set_dl_buffer(mac_it->second.dl_buffer);
            mac_msg->set_ul_buffer(mac_it->second.ul_buffer);
            mac_msg->set_dl_tbs(mac_it->second.dl_tbs);
            mac_msg->set_ul_tbs(mac_it->second.ul_tbs);
            mac_msg->set_dl_mcs(mac_it->second.dl_mcs);
            mac_msg->set_ul_mcs(mac_it->second.ul_mcs);
            mac_msg->set_dl_prbs(mac_it->second.dl_prbs);
            mac_msg->set_ul_prbs(mac_it->second.ul_prbs);
            mac_msg->set_dl_harq_ack(mac_it->second.dl_harq_ack);
            mac_msg->set_dl_harq_nack(mac_it->second.dl_harq_nack);
            mac_msg->set_ul_crc_ok(mac_it->second.ul_crc_ok);
            mac_msg->set_ul_crc_fail(mac_it->second.ul_crc_fail);
        }
        
        // MAC per-DRB metrics
        for (const auto& [key, drb] : mac_drb) {
            if (key.first != rnti) continue;
            
            MacDrbMetrics* drb_msg = ue_msg->add_mac_drb();
            drb_msg->set_lcid(key.second);
            drb_msg->set_dl_buffer(drb.dl_buffer);
            drb_msg->set_ul_buffer(drb.ul_buffer);
            drb_msg->set_dl_bytes(drb.dl_bytes);
            drb_msg->set_ul_bytes(drb.ul_bytes);
        }
        
        // RLC per-DRB metrics (with lock)
        {
            std::lock_guard<std::mutex> lock(rlc_mutex);
            for (const auto& [key, rlc] : rlc_drb) {
                if (key.first != rnti) continue;
                
                RlcDrbMetrics* rlc_msg = ue_msg->add_rlc_drb();
                rlc_msg->set_lcid(key.second);
                // Buffer status
                rlc_msg->set_dl_buffer(rlc.dl_buffer);
                rlc_msg->set_ul_buffer(rlc.ul_buffer);
                // TX (DL) metrics
                rlc_msg->set_tx_sdus(rlc.tx_sdus);
                rlc_msg->set_tx_sdu_bytes(rlc.tx_sdu_bytes);
                rlc_msg->set_tx_pdus(rlc.tx_pdus);
                rlc_msg->set_tx_pdu_bytes(rlc.tx_pdu_bytes);
                rlc_msg->set_tx_dropped_sdus(rlc.tx_dropped_sdus);
                rlc_msg->set_tx_retx_pdus(rlc.tx_retx_pdus);
                rlc_msg->set_tx_sdu_latency_us(rlc.tx_sdu_latency_us);
                // RX (UL) metrics
                rlc_msg->set_rx_sdus(rlc.rx_sdus);
                rlc_msg->set_rx_sdu_bytes(rlc.rx_sdu_bytes);
                rlc_msg->set_rx_pdus(rlc.rx_pdus);
                rlc_msg->set_rx_pdu_bytes(rlc.rx_pdu_bytes);
                rlc_msg->set_rx_lost_pdus(rlc.rx_lost_pdus);
                rlc_msg->set_rx_sdu_latency_us(rlc.rx_sdu_latency_us);
            }
        }
        
        // PDCP per-DRB metrics (with lock, need to correlate CU-UP UE index)
        {
            std::lock_guard<std::mutex> lock(pdcp_mutex);
            for (const auto& [key, pdcp] : pdcp_drb) {
                uint16_t pdcp_rnti = get_rnti_from_cu_up_ue_index(key.first);
                if (pdcp_rnti != rnti) continue;
                
                PdcpDrbMetrics* pdcp_msg = ue_msg->add_pdcp_drb();
                pdcp_msg->set_drb_id(key.second);
                pdcp_msg->set_lcid(key.second + 3);  // LCID = DRB_ID + 3
                // TX (DL) metrics
                pdcp_msg->set_tx_pdus(pdcp.tx_pdus);
                pdcp_msg->set_tx_pdu_bytes(pdcp.tx_pdu_bytes);
                pdcp_msg->set_tx_sdus(pdcp.tx_sdus);
                pdcp_msg->set_tx_dropped_sdus(pdcp.tx_dropped_sdus);
                pdcp_msg->set_tx_discard_timeouts(pdcp.tx_discard_timeouts);
                pdcp_msg->set_tx_pdu_latency_ns(pdcp.tx_pdu_latency_ns);
                // RX (UL) metrics
                pdcp_msg->set_rx_pdus(pdcp.rx_pdus);
                pdcp_msg->set_rx_pdu_bytes(pdcp.rx_pdu_bytes);
                pdcp_msg->set_rx_delivered_sdus(pdcp.rx_delivered_sdus);
                pdcp_msg->set_rx_dropped_pdus(pdcp.rx_dropped_pdus);
                pdcp_msg->set_rx_sdu_latency_ns(pdcp.rx_sdu_latency_ns);
            }
        }
        
        // GTP metrics per UE (with lock)
        {
            std::lock_guard<std::mutex> lock(gtp_mutex);
            for (const auto& [cu_up_idx, gtp] : gtp_ue) {
                uint16_t gtp_rnti = get_rnti_from_cu_up_ue_index(cu_up_idx);
                if (gtp_rnti != rnti) continue;
                
                GtpMetrics* gtp_msg = ue_msg->mutable_gtp();
                gtp_msg->set_dl_pkts(gtp.dl_pkts);
                gtp_msg->set_dl_bytes(gtp.dl_bytes);
                gtp_msg->set_ul_pkts(gtp.ul_pkts);
                gtp_msg->set_ul_bytes(gtp.ul_bytes);
                break;  // One GTP entry per UE
            }
        }
    }
    
    // Serialize and send via ZMQ
    std::string serialized;
    tti_msg.SerializeToString(&serialized);
    
    zmq::message_t msg(serialized.data(), serialized.size());
    publisher.send(msg, zmq::send_flags::dontwait);
    
    // Reset per-TTI MAC counters (HARQ, scheduling info)
    for (auto& [rnti, m] : mac_ue) {
        m.dl_harq_ack = 0;
        m.dl_harq_nack = 0;
        m.ul_crc_ok = 0;
        m.ul_crc_fail = 0;
        m.dl_tbs = 0;
        m.ul_tbs = 0;
        m.dl_mcs = 0;
        m.ul_mcs = 0;
        m.dl_prbs = 0;
        m.ul_prbs = 0;
    }
    for (auto& [key, m] : mac_drb) {
        m.dl_bytes = 0;
        m.ul_bytes = 0;
    }
}

//==============================================================================
// Legacy API: send_to_er (calls new send_tti_metrics)
//==============================================================================

void edgeric::send_to_er() {
    send_tti_metrics();
}

//==============================================================================
// Legacy API: printmyvariables
//==============================================================================

void edgeric::printmyvariables() {
    if (!enable_logging) return;
    
    std::ofstream logfile("log.txt", std::ios_base::app);
    if (!logfile.is_open()) return;
    
    logfile << "\n========== TTI " << getTtiIndex() << " (raw=" << tti_cnt << ") ==========\n";
    
    // Print per-UE metrics
    for (const auto& [rnti, m] : mac_ue) {
        logfile << "UE RNTI=" << rnti 
                << " CQI=" << m.cqi << " SNR=" << m.snr
                << " DL_BUF=" << m.dl_buffer << " UL_BUF=" << m.ul_buffer
                << " DL_TBS=" << m.dl_tbs << " UL_TBS=" << m.ul_tbs
                << " DL_ACK=" << m.dl_harq_ack << " DL_NACK=" << m.dl_harq_nack
                << " UL_OK=" << m.ul_crc_ok << " UL_FAIL=" << m.ul_crc_fail
                << "\n";
        
        // MAC DRBs (LCID >= 4 are DRBs; 0-3 are SRBs)
        for (const auto& [key, drb] : mac_drb) {
            if (key.first != rnti) continue;
            if (key.second < 4) continue;  // Skip SRBs
            logfile << "  MAC DRB LCID=" << (int)key.second
                    << " dl_buf=" << drb.dl_buffer << " ul_buf=" << drb.ul_buffer
                    << " dl_bytes=" << drb.dl_bytes << " ul_bytes=" << drb.ul_bytes
                    << "\n";
        }
        
        // RLC DRBs
        {
            std::lock_guard<std::mutex> lock(rlc_mutex);
            for (const auto& [key, rlc] : rlc_drb) {
                if (key.first != rnti) continue;
                logfile << "  RLC DRB LCID=" << (int)key.second
                        << " tx_sdus=" << rlc.tx_sdus << " tx_bytes=" << rlc.tx_sdu_bytes
                        << " tx_lat=" << rlc.tx_sdu_latency_us << "us"
                        << " rx_sdus=" << rlc.rx_sdus << " rx_bytes=" << rlc.rx_sdu_bytes
                        << "\n";
            }
        }
        
        // PDCP DRBs (correlate via CU-UP index)
        {
            std::lock_guard<std::mutex> lock(pdcp_mutex);
            for (const auto& [key, pdcp] : pdcp_drb) {
                uint16_t pdcp_rnti = get_rnti_from_cu_up_ue_index(key.first);
                if (pdcp_rnti != rnti) continue;
                logfile << "  PDCP DRB=" << (int)key.second << " (LCID=" << (int)(key.second + 3) << ")"
                        << " tx_pdus=" << pdcp.tx_pdus << " tx_bytes=" << pdcp.tx_pdu_bytes
                        << " tx_drop=" << pdcp.tx_dropped_sdus << " tx_discard=" << pdcp.tx_discard_timeouts
                        << " tx_lat=" << (pdcp.tx_pdu_latency_ns / 1000) << "us"
                        << " rx_pdus=" << pdcp.rx_pdus << " rx_bytes=" << pdcp.rx_pdu_bytes
                        << " rx_drop=" << pdcp.rx_dropped_pdus
                        << " rx_lat=" << (pdcp.rx_sdu_latency_ns / 1000) << "us"
                        << "\n";
            }
        }
        
        // GTP
        {
            std::lock_guard<std::mutex> lock(gtp_mutex);
            for (const auto& [cu_up_idx, gtp] : gtp_ue) {
                uint16_t gtp_rnti = get_rnti_from_cu_up_ue_index(cu_up_idx);
                if (gtp_rnti != rnti) continue;
                logfile << "  GTP dl_pkts=" << gtp.dl_pkts << " dl_bytes=" << gtp.dl_bytes
                        << " ul_pkts=" << gtp.ul_pkts << " ul_bytes=" << gtp.ul_bytes
                        << "\n";
            }
        }
    }
    
    logfile.close();
}

//==============================================================================
// Control Reception
//==============================================================================

void edgeric::get_weights_from_er() {
    ensure_initialized();
    
    zmq::message_t recv_message;
    zmq::recv_result_t size = subscriber_weights.recv(recv_message, zmq::recv_flags::dontwait);

    if (size) {
        SchedulingWeights weights_msg;
        if (weights_msg.ParseFromArray(recv_message.data(), recv_message.size())) {
            er_ran_index_weights = weights_msg.ran_index();
            weights_recved.clear();
            // Weights are indexed by order, map to active RNTIs
            int idx = 0;
            for (const auto& [rnti, _] : mac_ue) {
                if (idx < weights_msg.weights_size()) {
                    weights_recved[rnti] = weights_msg.weights(idx);
                    idx++;
                }
            }
        }
    }
}

void edgeric::get_mcs_from_er() {
    ensure_initialized();
    
    zmq::message_t recv_message;
    zmq::recv_result_t size = subscriber_mcs.recv(recv_message, zmq::recv_flags::dontwait);

    if (size) {
        mcs_control mcs_msg;
        if (mcs_msg.ParseFromArray(recv_message.data(), recv_message.size())) {
            er_ran_index_mcs = mcs_msg.ran_index();
            mcs_recved.clear();
            // MCS values are indexed by order, map to active RNTIs
            // MCS value of 255 means "no override" (use link adaptation)
            int idx = 0;
            for (const auto& [rnti, _] : mac_ue) {
                if (idx < mcs_msg.mcs_size()) {
                    uint8_t mcs_val = static_cast<uint8_t>(mcs_msg.mcs(idx));
                    if (mcs_val < 255) {  // Only override if MCS < 255
                        mcs_recved[rnti] = mcs_val;
                    }
                    idx++;
                }
            }
        }
    }
}

void edgeric::get_qos_from_er() {
    ensure_initialized();
    
    zmq::message_t recv_message;
    zmq::recv_result_t size = subscriber_qos.recv(recv_message, zmq::recv_flags::dontwait);
    
    if (size) {
        QosControl qos_msg;
        if (qos_msg.ParseFromArray(recv_message.data(), recv_message.size())) {
            er_ran_index_qos = qos_msg.ran_index();
            
            std::cerr << "[EdgeRIC] QoS Control Received: ran_index=" << er_ran_index_qos
                      << ", TTI=" << tti_cnt << ", num_drbs=" << qos_msg.drb_qos_size() << std::endl;
            
            for (int i = 0; i < qos_msg.drb_qos_size(); ++i) {
                const DrbQosParams& drb = qos_msg.drb_qos(i);
                uint16_t rnti = static_cast<uint16_t>(drb.rnti());
                uint8_t lcid = static_cast<uint8_t>(drb.lcid());
                ue_drb_key key = {rnti, lcid};
                
                std::cerr << "[EdgeRIC]   RNTI=" << rnti << " LCID=" << (int)lcid;
                if (drb.has_qos_priority()) std::cerr << " qos_prio=" << drb.qos_priority();
                if (drb.has_arp_priority()) std::cerr << " arp_prio=" << drb.arp_priority();
                if (drb.has_pdb_ms()) std::cerr << " pdb=" << drb.pdb_ms();
                if (drb.has_gbr_dl()) std::cerr << " gbr_dl=" << drb.gbr_dl();
                if (drb.has_gbr_ul()) std::cerr << " gbr_ul=" << drb.gbr_ul();
                if (drb.clear_override()) std::cerr << " CLEAR";
                std::cerr << std::endl;
                
                if (drb.clear_override()) {
                    qos_overrides.erase(key);
        } else {
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
                        if (drb.has_gbr_dl()) params.gbr_dl = drb.gbr_dl();
                        if (drb.has_gbr_ul()) params.gbr_ul = drb.gbr_ul();
                        params.override_gbr = true;
                    }
                }
            }
        }
    }
}

//==============================================================================
// Control Getters
//==============================================================================

std::optional<float> edgeric::get_weights(uint16_t rnti) {
    auto it = weights_recved.find(rnti);
    return (it != weights_recved.end()) ? std::optional<float>(it->second) : std::nullopt;
}

std::optional<uint8_t> edgeric::get_mcs(uint16_t rnti) {
    auto it = mcs_recved.find(rnti);
    return (it != mcs_recved.end()) ? std::optional<uint8_t>(it->second) : std::nullopt;
}

//==============================================================================
// QoS Override API
//==============================================================================

void edgeric::set_dynamic_qos(uint16_t rnti, uint8_t lcid, const dynamic_qos_params& params) {
    qos_overrides[{rnti, lcid}] = params;
}

void edgeric::clear_dynamic_qos(uint16_t rnti, uint8_t lcid) {
    qos_overrides.erase({rnti, lcid});
}

void edgeric::clear_all_dynamic_qos(uint16_t rnti) {
    for (auto it = qos_overrides.begin(); it != qos_overrides.end(); ) {
        if (it->first.first == rnti) {
            it = qos_overrides.erase(it);
        } else {
            ++it;
        }
    }
}

std::optional<dynamic_qos_params> edgeric::get_dynamic_qos(uint16_t rnti, uint8_t lcid) {
    auto it = qos_overrides.find({rnti, lcid});
    return (it != qos_overrides.end()) ? std::optional<dynamic_qos_params>(it->second) : std::nullopt;
}

void edgeric::set_qos_priority(uint16_t rnti, uint8_t lcid, uint8_t priority) {
    auto& p = qos_overrides[{rnti, lcid}];
    p.qos_priority = priority;
    p.override_qos_priority = true;
}

void edgeric::set_arp_priority(uint16_t rnti, uint8_t lcid, uint8_t arp) {
    auto& p = qos_overrides[{rnti, lcid}];
    p.arp_priority = arp;
    p.override_arp_priority = true;
}

void edgeric::set_pdb(uint16_t rnti, uint8_t lcid, uint32_t pdb_ms) {
    auto& p = qos_overrides[{rnti, lcid}];
    p.pdb_ms = pdb_ms;
    p.override_pdb = true;
}

void edgeric::set_gbr(uint16_t rnti, uint8_t lcid, uint64_t gbr_dl, uint64_t gbr_ul) {
    auto& p = qos_overrides[{rnti, lcid}];
    p.gbr_dl = gbr_dl;
    p.gbr_ul = gbr_ul;
    p.override_gbr = true;
}

std::optional<uint8_t> edgeric::get_qos_priority(uint16_t rnti, uint8_t lcid) {
    auto it = qos_overrides.find({rnti, lcid});
    if (it != qos_overrides.end() && it->second.override_qos_priority) {
        return it->second.qos_priority;
    }
    return std::nullopt;
}

std::optional<uint8_t> edgeric::get_arp_priority(uint16_t rnti, uint8_t lcid) {
    auto it = qos_overrides.find({rnti, lcid});
    if (it != qos_overrides.end() && it->second.override_arp_priority) {
        return it->second.arp_priority;
    }
    return std::nullopt;
}

std::optional<uint32_t> edgeric::get_pdb(uint16_t rnti, uint8_t lcid) {
    auto it = qos_overrides.find({rnti, lcid});
    if (it != qos_overrides.end() && it->second.override_pdb) {
        return it->second.pdb_ms;
    }
    return std::nullopt;
}

std::optional<uint64_t> edgeric::get_gbr_dl(uint16_t rnti, uint8_t lcid) {
    auto it = qos_overrides.find({rnti, lcid});
    if (it != qos_overrides.end() && it->second.override_gbr) {
        return it->second.gbr_dl;
    }
    return std::nullopt;
}

std::optional<uint64_t> edgeric::get_gbr_ul(uint16_t rnti, uint8_t lcid) {
    auto it = qos_overrides.find({rnti, lcid});
    if (it != qos_overrides.end() && it->second.override_gbr) {
        return it->second.gbr_ul;
    }
    return std::nullopt;
}

//==============================================================================
// Legacy Helper Functions
//==============================================================================

std::vector<uint8_t> edgeric::get_drb_lcids(uint16_t rnti) {
    std::set<uint8_t> lcids;
    for (const auto& [key, _] : mac_drb) {
        if (key.first == rnti) lcids.insert(key.second);
    }
    return std::vector<uint8_t>(lcids.begin(), lcids.end());
}

std::vector<uint8_t> edgeric::get_pdcp_drb_ids(uint16_t rnti) {
    // Deprecated - use get_pdcp_drb_ids_by_ue_index
    return {};
}

std::vector<uint8_t> edgeric::get_pdcp_drb_ids_by_ue_index(uint32_t ue_index) {
    std::lock_guard<std::mutex> lock(pdcp_mutex);
    std::set<uint8_t> drb_ids;
    for (const auto& [key, _] : pdcp_drb) {
        if (key.first == ue_index) drb_ids.insert(key.second);
    }
    return std::vector<uint8_t>(drb_ids.begin(), drb_ids.end());
}

std::optional<gtp_ue_metrics> edgeric::get_gtp_metrics(uint16_t rnti) {
    std::lock_guard<std::mutex> lock(gtp_mutex);
    for (const auto& [cu_up_idx, gtp] : gtp_ue) {
        if (get_rnti_from_cu_up_ue_index(cu_up_idx) == rnti) {
            return gtp;
        }
    }
    return std::nullopt;
}

void edgeric::collect_ue_telemetry(uint16_t rnti, float cqi, float snr,
                                   uint32_t dl_buffer_bytes, uint32_t ul_buffer_bytes) {
    // Only update CQI, SNR, and buffer values - DO NOT overwrite TBS/PRBs/MCS
    // which are set earlier during the scheduling phase
    auto& m = mac_ue[rnti];
    m.cqi = static_cast<uint32_t>(cqi);
    m.snr = snr;
    m.dl_buffer = dl_buffer_bytes;
    m.ul_buffer = ul_buffer_bytes;
}
