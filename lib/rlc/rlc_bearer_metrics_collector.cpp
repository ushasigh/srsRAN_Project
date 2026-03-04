/*
 *
 * Copyright 2021-2026 Software Radio Systems Limited
 *
 * This file is part of srsRAN.
 *
 * srsRAN is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as
 * published by the Free Software Foundation, either version 3 of
 * the License, or (at your option) any later version.
 *
 * srsRAN is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.
 *
 * A copy of the GNU Affero General Public License can be found in
 * the LICENSE file in the top-level directory of this distribution
 * and at http://www.gnu.org/licenses/.
 *
 */

#include "rlc_bearer_metrics_collector.h"
#include "../edgeric/edgeric.h"

using namespace srsran;

rlc_bearer_metrics_collector::rlc_bearer_metrics_collector(gnb_du_id_t           du_,
                                                           du_ue_index_t         ue_,
                                                           rb_id_t               rb_,
                                                           timer_duration        metrics_period_,
                                                           rlc_metrics_notifier* rlc_metrics_notif_,
                                                           task_executor&        ue_executor_) :
  du(du_),
  ue(ue_),
  rb(rb_),
  metrics_period(metrics_period_),
  rlc_metrics_notif(rlc_metrics_notif_),
  ue_executor(ue_executor_),
  logger("RLC", {du_, ue_, rb_, "DL/UL"})
{
  m_lower.counter   = UINT32_MAX;
  m_higher.counter  = UINT32_MAX;
  m_rx_high.counter = UINT32_MAX;
}

void rlc_bearer_metrics_collector::push_tx_high_metrics(const rlc_tx_metrics_higher& m_higher_)
{
  if (not ue_executor.execute([this, m_higher_]() { push_tx_high_metrics_impl(m_higher_); })) {
    logger.log_error("Could not push TX high metrics");
  }
}

void rlc_bearer_metrics_collector::push_tx_low_metrics(const rlc_tx_metrics_lower& m_lower_)
{
  // Because of its size, passing this metrics object directly through a capture in a unique_task would involve malloc
  // and free. Therefore we pass the object through a triple buffer instead.
  metrics_lower_triple_buf.write_and_commit(m_lower_);
  if (not ue_executor.execute([this]() { push_tx_low_metrics_impl(metrics_lower_triple_buf.read()); })) {
    logger.log_error("Could not push TX low metrics");
  }
}

void rlc_bearer_metrics_collector::push_rx_high_metrics(const rlc_rx_metrics& m_rx_high_)
{
  if (not ue_executor.execute([this, m_rx_high_]() { push_rx_high_metrics_impl(m_rx_high_); })) {
    logger.log_error("Could not push RX high metrics");
  }
}

void rlc_bearer_metrics_collector::push_tx_high_metrics_impl(const rlc_tx_metrics_higher& m_higher_)
{
  m_higher = m_higher_;
  push_report();
}

void rlc_bearer_metrics_collector::push_tx_low_metrics_impl(const rlc_tx_metrics_lower& m_lower_)
{
  m_lower = m_lower_;
  push_report();
}

void rlc_bearer_metrics_collector::push_rx_high_metrics_impl(const rlc_rx_metrics& m_rx_high_)
{
  m_rx_high = m_rx_high_;
  push_report();
}

void rlc_bearer_metrics_collector::push_report()
{
  if (m_lower.counter != m_higher.counter || m_lower.counter != m_rx_high.counter) {
    return;
  }
  rlc_metrics report = {du, ue, rb, {m_higher, m_lower}, m_rx_high, 0, metrics_period};
  rlc_metrics_notif->report_metrics(report);
  
  // Report to EdgeRIC (only for DRBs, LCID >= 4)
  if (rb.is_drb()) {
    uint8_t lcid = static_cast<uint8_t>(rb.get_drb_id()) + 3;  // DRB ID to LCID conversion
    
    // Build RLC metrics struct for EdgeRIC
    rlc_drb_metrics er_metrics;
    
    // TX (DL) metrics
    er_metrics.tx_sdus = m_higher.num_sdus;
    er_metrics.tx_sdu_bytes = m_higher.num_sdu_bytes;
    er_metrics.tx_dropped_sdus = m_higher.num_dropped_sdus + m_higher.num_discarded_sdus;
    er_metrics.tx_pdus = m_lower.num_pdus_no_segmentation;
    er_metrics.tx_pdu_bytes = m_lower.num_pdu_bytes_no_segmentation;
    
    // Calculate average TX SDU latency
    if (m_lower.num_of_pulled_sdus > 0) {
      er_metrics.tx_sdu_latency_us = m_lower.sum_sdu_latency_us / m_lower.num_of_pulled_sdus;
    }
    
    // AM mode specific: retransmissions
    if (std::holds_alternative<rlc_am_tx_metrics_lower>(m_lower.mode_specific)) {
      const auto& am = std::get<rlc_am_tx_metrics_lower>(m_lower.mode_specific);
      er_metrics.tx_retx_pdus = am.num_retx_pdus;
      // Add segmented PDUs to total
      er_metrics.tx_pdus += am.num_pdus_with_segmentation;
      er_metrics.tx_pdu_bytes += am.num_pdu_bytes_with_segmentation;
    } else if (std::holds_alternative<rlc_um_tx_metrics_lower>(m_lower.mode_specific)) {
      const auto& um = std::get<rlc_um_tx_metrics_lower>(m_lower.mode_specific);
      er_metrics.tx_pdus += um.num_pdus_with_segmentation;
      er_metrics.tx_pdu_bytes += um.num_pdu_bytes_with_segmentation;
    }
    
    // RX (UL) metrics
    er_metrics.rx_sdus = m_rx_high.num_sdus;
    er_metrics.rx_sdu_bytes = m_rx_high.num_sdu_bytes;
    er_metrics.rx_pdus = m_rx_high.num_pdus;
    er_metrics.rx_pdu_bytes = m_rx_high.num_pdu_bytes;
    er_metrics.rx_lost_pdus = m_rx_high.num_lost_pdus;
    
    // RX SDU latency (reassembly time) - already an average in sdu_latency_us
    er_metrics.rx_sdu_latency_us = static_cast<uint32_t>(m_rx_high.sdu_latency_us);
    
    // Report to EdgeRIC
    edgeric::report_rlc_metrics(static_cast<uint32_t>(ue), lcid, er_metrics);
  }
}
