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

#include "scheduler_time_pf.h"
#include "../slicing/slice_ue_repository.h"
#include "../ue_context/ue_cell.h"
#include <cmath>
#include <fstream>

// EdgeRIC integration
#include "../../edgeric/edgeric.h"

using namespace srsran;

// Global TTI counter for EdgeRIC
static uint32_t tti_cnt = 0;

scheduler_time_pf::scheduler_time_pf(const scheduler_ue_expert_config& expert_cfg_) :
  fairness_coeff(std::get<time_pf_scheduler_config>(expert_cfg_.policy_cfg).pf_sched_fairness_coeff)
{
}

void scheduler_time_pf::add_ue(du_ue_index_t ue_index)
{
  if (not ue_history_db.contains(ue_index)) {
    ue_history_db.emplace(ue_index, ue_index, exp_avg_alpha, fairness_coeff);
  }
}

void scheduler_time_pf::rem_ue(du_ue_index_t ue_index)
{
  ue_history_db.erase(ue_index);
}

void scheduler_time_pf::compute_ue_dl_priorities(slot_point               pdcch_slot,
                                                  slot_point               pdsch_slot,
                                                  span<ue_newtx_candidate> ue_candidates)
{
  // Increment TTI counter
  tti_cnt++;

  // Number of slots elapsed since last scheduling.
  unsigned nof_slots_elapsed = 1;
  if (last_pdsch_slot.valid()) {
    nof_slots_elapsed = pdsch_slot - last_pdsch_slot;
  }
  last_pdsch_slot = pdsch_slot;

  for (ue_newtx_candidate& candidate : ue_candidates) {
    // EdgeRIC: Extract and send UE metrics
    if (candidate.ue_cc != nullptr) {
      const ue_cell& ue_cc = *candidate.ue_cc;
      
      // Get CQI and SNR from channel state
      float effective_cqi = ue_cc.link_adaptation_controller().get_effective_cqi();
      float effective_snr = ue_cc.channel_state_manager().get_pusch_snr();
      
      // Get buffer status
      uint32_t dl_newtx_bytes = candidate.ue->pending_dl_newtx_bytes();
      uint32_t ul_newtx_bytes = candidate.ue->pending_ul_newtx_bytes();
      
      // Send to EdgeRIC
      edgeric::set_cqi(static_cast<unsigned int>(ue_cc.rnti()), effective_cqi);
      edgeric::set_snr(static_cast<unsigned int>(ue_cc.rnti()), effective_snr);
      edgeric::set_dl_buffer(static_cast<unsigned int>(ue_cc.rnti()), dl_newtx_bytes);
      edgeric::set_ul_buffer(static_cast<unsigned int>(ue_cc.rnti()), ul_newtx_bytes);
    }

    if (not ue_history_db.contains(candidate.ue->ue_index())) {
      // UE not yet added, assign a default high priority.
      candidate.priority = max_sched_priority;
      continue;
    }

    ue_ctxt& ctxt = ue_history_db[candidate.ue->ue_index()];
    
    // Update avg rate for slots with no allocation.
    ctxt.update_dl_avg_rate_no_alloc(nof_slots_elapsed);

    // Compute PF priority: pending_bytes / avg_rate^fairness_coeff
    double avg_rate = ctxt.dl_avg_rate();
    if (avg_rate < 1.0) {
      avg_rate = 1.0; // Avoid division by zero or very small values.
    }
    
    double pf_metric = static_cast<double>(candidate.pending_bytes) / std::pow(avg_rate, fairness_coeff);
    candidate.priority = pf_metric;
    ctxt.dl_prio = pf_metric;
  }

  // EdgeRIC: Log scheduling info from PF scheduler
  std::ofstream logfile("pf-scheduler-log.txt", std::ios_base::app);
  if (logfile.is_open()) {
    logfile << "PF_SCHED TTI: " << tti_cnt 
            << ", EdgeRIC TTI: " << edgeric::tti_cnt 
            << ", Candidates: " << ue_candidates.size() << std::endl;
    logfile.close();
  }
}

void scheduler_time_pf::compute_ue_ul_priorities(slot_point               pdcch_slot,
                                                  slot_point               pusch_slot,
                                                  span<ue_newtx_candidate> ue_candidates)
{
  // Number of slots elapsed since last scheduling.
  unsigned nof_slots_elapsed = 1;
  if (last_pusch_slot.valid()) {
    nof_slots_elapsed = pusch_slot - last_pusch_slot;
  }
  last_pusch_slot = pusch_slot;

  for (ue_newtx_candidate& candidate : ue_candidates) {
    if (not ue_history_db.contains(candidate.ue->ue_index())) {
      // UE not yet added, assign a default high priority.
      candidate.priority = max_sched_priority;
      continue;
    }

    ue_ctxt& ctxt = ue_history_db[candidate.ue->ue_index()];
    
    // Update avg rate for slots with no allocation.
    ctxt.update_ul_avg_rate_no_alloc(nof_slots_elapsed);

    // Compute PF priority: pending_bytes / avg_rate^fairness_coeff
    double avg_rate = ctxt.ul_avg_rate();
    if (avg_rate < 1.0) {
      avg_rate = 1.0; // Avoid division by zero or very small values.
    }
    
    double pf_metric = static_cast<double>(candidate.pending_bytes) / std::pow(avg_rate, fairness_coeff);
    candidate.priority = pf_metric;
    ctxt.ul_prio = pf_metric;
  }
}

void scheduler_time_pf::save_dl_newtx_grants(span<const dl_msg_alloc> dl_grants)
{
  for (const auto& grant : dl_grants) {
    if (ue_history_db.contains(grant.context.ue_index)) {
      unsigned total_bytes = 0;
      for (const auto& cw : grant.pdsch_cfg.codewords) {
        total_bytes += cw.tb_size_bytes;
      }
      ue_history_db[grant.context.ue_index].save_dl_alloc(total_bytes);
    }
  }
}

void scheduler_time_pf::save_ul_newtx_grants(span<const ul_sched_info> ul_grants)
{
  for (const auto& grant : ul_grants) {
    if (ue_history_db.contains(grant.context.ue_index)) {
      ue_history_db[grant.context.ue_index].save_ul_alloc(grant.pusch_cfg.tb_size_bytes);
    }
  }
}

// ue_ctxt implementation

scheduler_time_pf::ue_ctxt::ue_ctxt(du_ue_index_t ue_index_, double alpha, double fairness) :
  ue_index(ue_index_),
  fairness_coeff(fairness),
  dl_avg_rate_(alpha),
  ul_avg_rate_(alpha)
{
}

void scheduler_time_pf::ue_ctxt::save_dl_alloc(unsigned alloc_bytes)
{
  dl_sum_alloc_bytes += alloc_bytes;
  dl_avg_rate_.push(static_cast<double>(dl_sum_alloc_bytes));
  dl_sum_alloc_bytes = 0;
}

void scheduler_time_pf::ue_ctxt::save_ul_alloc(unsigned alloc_bytes)
{
  ul_sum_alloc_bytes += alloc_bytes;
  ul_avg_rate_.push(static_cast<double>(ul_sum_alloc_bytes));
  ul_sum_alloc_bytes = 0;
}

void scheduler_time_pf::ue_ctxt::update_dl_avg_rate_no_alloc(unsigned nof_slots)
{
  // For slots where UE was not allocated, push zero to update the average.
  for (unsigned i = 0; i < nof_slots; ++i) {
    if (dl_sum_alloc_bytes == 0) {
      dl_avg_rate_.push(0.0);
    }
  }
}

void scheduler_time_pf::ue_ctxt::update_ul_avg_rate_no_alloc(unsigned nof_slots)
{
  // For slots where UE was not allocated, push zero to update the average.
  for (unsigned i = 0; i < nof_slots; ++i) {
    if (ul_sum_alloc_bytes == 0) {
      ul_avg_rate_.push(0.0);
    }
  }
}
