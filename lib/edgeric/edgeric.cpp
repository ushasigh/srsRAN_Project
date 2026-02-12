#include "edgeric.h"

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

        // Set UL Buffer, default to 0 if not available
        auto dl_tbs_it = dl_tbs_ues.find(rnti);
        ue_metrics->set_dl_tbs((dl_tbs_it != dl_tbs_ues.end()) ? dl_tbs_it->second : 0);
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
    // ue_dl_buffers.clear();
    // ue_ul_buffers.clear();
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
            logfile << "TTI: " << tti_cnt << ", Weights index: " << er_ran_index_weights << ", MCS index: " << er_ran_index_mcs << std::endl;

            for (const auto& cqi_pair : ue_cqis) {
                auto rnti = cqi_pair.first;

                // Fetch or default metrics for the RNTI
                float weight = (weights_recved.count(rnti) > 0) ? weights_recved.at(rnti) : 0;
                int mcs = (mcs_recved.count(rnti) > 0) ? static_cast<int>(mcs_recved.at(rnti)) : 0;
                int cqi = static_cast<int>(cqi_pair.second);
                int snr = (ue_snrs.count(rnti) > 0) ? static_cast<int>(ue_snrs.at(rnti)) : 0;
                int rx_byte = (rx_bytes.count(rnti) > 0) ? static_cast<int>(rx_bytes.at(rnti)) : 0;
                int tx_byte = (tx_bytes.count(rnti) > 0) ? static_cast<int>(tx_bytes.at(rnti)) : 0;
                int ul_buffer = (ue_ul_buffers.count(rnti) > 0) ? static_cast<int>(ue_ul_buffers.at(rnti)) : 0;
                int dl_buffer = (ue_dl_buffers.count(rnti) > 0) ? static_cast<int>(ue_dl_buffers.at(rnti)) : 0;
                float dl_tbs = (dl_tbs_ues.count(rnti) > 0) ? static_cast<int>(dl_tbs_ues.at(rnti)) : 0;

                // Print all metrics in one line
                logfile << "RNTI: " << rnti 
                        << " Weights: " << weight
                        << " MCS: " << mcs
                        << " CQI: " << cqi
                        << " SNR: " << snr
                        << " Rx Bytes: " << rx_byte
                        << " Tx Bytes: " << tx_byte
                        << " UL Buffer: " << ul_buffer
                        << " DL Buffer: " << dl_buffer
                        << " DL TBS: " << dl_tbs
                        << std::endl;
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
                std::ofstream logfile("edgeric_qos_log.txt", std::ios_base::app);
                if (logfile.is_open()) {
                    logfile << "========== QoS Control Received (ran_index=" << er_ran_index_qos 
                            << ", TTI=" << tti_cnt << ") ==========" << std::endl;
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
                    
                    // Log clear action
                    if (enable_logging) {
                        std::ofstream logfile("edgeric_qos_log.txt", std::ios_base::app);
                        if (logfile.is_open()) {
                            logfile << "  CLEAR: RNTI=" << rnti << ", LCID=" << static_cast<int>(lcid) << std::endl;
                        }
                    }
                } else {
                    // Apply the overrides
                    auto& params = qos_overrides[key];
                    
                    // Log the update
                    if (enable_logging) {
                        std::ofstream logfile("edgeric_qos_log.txt", std::ios_base::app);
                        if (logfile.is_open()) {
                            logfile << "  UPDATE: RNTI=" << rnti << ", LCID=" << static_cast<int>(lcid);
                        }
                    }
                    
                    if (drb.has_qos_priority()) {
                        params.qos_priority = static_cast<uint8_t>(drb.qos_priority());
                        params.override_qos_priority = true;
                        if (enable_logging) {
                            std::ofstream logfile("edgeric_qos_log.txt", std::ios_base::app);
                            if (logfile.is_open()) {
                                logfile << " qos_prio=" << static_cast<int>(params.qos_priority);
                            }
                        }
                    }
                    if (drb.has_arp_priority()) {
                        params.arp_priority = static_cast<uint8_t>(drb.arp_priority());
                        params.override_arp_priority = true;
                        if (enable_logging) {
                            std::ofstream logfile("edgeric_qos_log.txt", std::ios_base::app);
                            if (logfile.is_open()) {
                                logfile << " arp_prio=" << static_cast<int>(params.arp_priority);
                            }
                        }
                    }
                    if (drb.has_pdb_ms()) {
                        params.pdb_ms = drb.pdb_ms();
                        params.override_pdb = true;
                        if (enable_logging) {
                            std::ofstream logfile("edgeric_qos_log.txt", std::ios_base::app);
                            if (logfile.is_open()) {
                                logfile << " pdb_ms=" << params.pdb_ms;
                            }
                        }
                    }
                    if (drb.has_gbr_dl() || drb.has_gbr_ul()) {
                        if (drb.has_gbr_dl()) {
                            params.gbr_dl = drb.gbr_dl();
                        }
                        if (drb.has_gbr_ul()) {
                            params.gbr_ul = drb.gbr_ul();
                        }
                        params.override_gbr = true;
                        if (enable_logging) {
                            std::ofstream logfile("edgeric_qos_log.txt", std::ios_base::app);
                            if (logfile.is_open()) {
                                logfile << " gbr_dl=" << params.gbr_dl << " gbr_ul=" << params.gbr_ul;
                            }
                        }
                    }
                    
                    if (enable_logging) {
                        std::ofstream logfile("edgeric_qos_log.txt", std::ios_base::app);
                        if (logfile.is_open()) {
                            logfile << std::endl;
                        }
                    }
                }
            }
            
            // Log current state of all QoS overrides
            if (enable_logging && !qos_overrides.empty()) {
                std::ofstream logfile("edgeric_qos_log.txt", std::ios_base::app);
                if (logfile.is_open()) {
                    logfile << "  --- Current QoS Override State ---" << std::endl;
                    for (const auto& [key, params] : qos_overrides) {
                        logfile << "    RNTI=" << key.first << " LCID=" << static_cast<int>(key.second) << ":";
                        if (params.override_qos_priority) {
                            logfile << " qos_prio=" << static_cast<int>(params.qos_priority);
                        }
                        if (params.override_arp_priority) {
                            logfile << " arp_prio=" << static_cast<int>(params.arp_priority);
                        }
                        if (params.override_pdb) {
                            logfile << " pdb_ms=" << params.pdb_ms;
                        }
                        if (params.override_gbr) {
                            logfile << " gbr_dl=" << params.gbr_dl << " gbr_ul=" << params.gbr_ul;
                        }
                        logfile << std::endl;
                    }
                }
            }
            
        } else {
            std::cerr << "Failed to parse QosControl message." << std::endl;
        }
    }
    // If no message received, keep existing overrides (they persist until cleared)
}