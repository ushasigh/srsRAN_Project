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

#pragma once

#include "scheduler_policy.h"
#include "srsran/adt/slotted_array.h"
#include "srsran/scheduler/config/scheduler_expert_config.h"
#include "srsran/support/math/exponential_averager.h"

namespace srsran {

/// Proportional Fair scheduler policy.
class scheduler_time_pf final : public scheduler_policy
{
public:
  scheduler_time_pf(const scheduler_ue_expert_config& expert_cfg_);

  void add_ue(du_ue_index_t ue_index) override;

  void rem_ue(du_ue_index_t ue_index) override;

  void compute_ue_dl_priorities(slot_point               pdcch_slot,
                                slot_point               pdsch_slot,
                                span<ue_newtx_candidate> ue_candidates) override;

  void compute_ue_ul_priorities(slot_point               pdcch_slot,
                                slot_point               pusch_slot,
                                span<ue_newtx_candidate> ue_candidates) override;

  void save_dl_newtx_grants(span<const dl_msg_alloc> dl_grants) override;

  void save_ul_newtx_grants(span<const ul_sched_info> ul_grants) override;

private:
  // Policy parameters.
  const double fairness_coeff;
  
  /// Coefficient used to compute exponential moving average.
  const double exp_avg_alpha = 0.01;

  /// Holds the information needed to compute priority of a UE.
  struct ue_ctxt {
    ue_ctxt(du_ue_index_t ue_index_, double alpha, double fairness);

    /// Returns average DL rate expressed in bytes per slot of the UE.
    [[nodiscard]] double dl_avg_rate() const { return dl_avg_rate_.get_average_value(); }
    /// Returns average UL rate expressed in bytes per slot of the UE.
    [[nodiscard]] double ul_avg_rate() const { return ul_avg_rate_.get_average_value(); }

    void save_dl_alloc(unsigned alloc_bytes);
    void save_ul_alloc(unsigned alloc_bytes);
    
    /// Update average rates for slots with no allocation.
    void update_dl_avg_rate_no_alloc(unsigned nof_slots);
    void update_ul_avg_rate_no_alloc(unsigned nof_slots);

    const du_ue_index_t ue_index;
    const double        fairness_coeff;

    /// DL priority value of the UE.
    double dl_prio = 0.0;
    /// UL priority value of the UE.
    double ul_prio = 0.0;

  private:
    // Sum of DL bytes allocated for a given slot.
    unsigned dl_sum_alloc_bytes = 0;
    // Sum of UL bytes allocated for a given slot.
    unsigned ul_sum_alloc_bytes = 0;
    // Average DL rate expressed in bytes per slot experienced by UE.
    exp_average_fast_start<double> dl_avg_rate_;
    // Average UL rate expressed in bytes per slot experienced by UE.
    exp_average_fast_start<double> ul_avg_rate_;
  };

  slotted_id_table<du_ue_index_t, ue_ctxt, MAX_NOF_DU_UES> ue_history_db;

  slot_point last_pdsch_slot;
  slot_point last_pusch_slot;
};

} // namespace srsran
