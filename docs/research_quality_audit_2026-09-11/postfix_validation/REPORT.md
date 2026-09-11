# Research Quality Audit — 2026-09-11

> 只读审计；未调用 Simulation POST、Alpha submission、color/write API，也未写入 `.wqb_state/`。机器标记的 relevance/false-positive 仅是人工复核入口，不是 production truth。

## 1. 数据来源与样本

- catalog: `F:\codex\wqb_alpha_factory\.wqb_state\platform_field_catalog_20260910`；fetched_at: `2026-09-10T18:13:08.254966+00:00`；status: `COMPLETE_WITH_SUPPLEMENTS`
- supplemental catalogs: **1**（仅用于主快照缺失 dataset，逐字段保留 provenance）
- fields available: **2407**；真实 stratified sample: **100**
- datasets: `analyst4, fundamental6, news18, option8, option9, pv1, pv13`；historical proposals: **100**

### Sample strata

| dataset | type | coverage | description | alphaCount | count |
|---|---|---|---|---|---:|
| analyst4 | MATRIX | high | rich | high | 1 |
| analyst4 | MATRIX | high | rich | low | 2 |
| analyst4 | MATRIX | high | rich | mid | 2 |
| analyst4 | MATRIX | high | weak | high | 2 |
| analyst4 | MATRIX | high | weak | low | 2 |
| analyst4 | MATRIX | high | weak | mid | 2 |
| analyst4 | MATRIX | low | rich | high | 1 |
| analyst4 | MATRIX | low | rich | mid | 1 |
| analyst4 | MATRIX | low | weak | high | 1 |
| analyst4 | MATRIX | low | weak | low | 1 |
| analyst4 | MATRIX | low | weak | mid | 1 |
| analyst4 | MATRIX | mid | rich | low | 1 |
| analyst4 | MATRIX | mid | rich | mid | 1 |
| analyst4 | MATRIX | mid | weak | high | 1 |
| analyst4 | MATRIX | mid | weak | low | 1 |
| analyst4 | MATRIX | mid | weak | mid | 1 |
| analyst4 | VECTOR | high | weak | high | 1 |
| analyst4 | VECTOR | high | weak | low | 1 |
| analyst4 | VECTOR | high | weak | mid | 1 |
| analyst4 | VECTOR | low | weak | high | 1 |
| analyst4 | VECTOR | low | weak | low | 1 |
| analyst4 | VECTOR | low | weak | mid | 1 |
| analyst4 | VECTOR | mid | weak | high | 1 |
| analyst4 | VECTOR | mid | weak | low | 1 |
| analyst4 | VECTOR | mid | weak | mid | 1 |
| fundamental6 | MATRIX | mid | rich | mid | 1 |
| fundamental6 | MATRIX | mid | weak | high | 5 |
| fundamental6 | MATRIX | mid | weak | low | 5 |
| fundamental6 | MATRIX | mid | weak | mid | 5 |
| fundamental6 | VECTOR | mid | weak | high | 5 |
| fundamental6 | VECTOR | mid | weak | low | 5 |
| fundamental6 | VECTOR | mid | weak | mid | 4 |
| news18 | MATRIX | high | weak | mid | 1 |
| news18 | MATRIX | mid | weak | high | 1 |
| news18 | MATRIX | mid | weak | mid | 1 |
| news18 | VECTOR | high | rich | high | 1 |
| news18 | VECTOR | high | rich | low | 1 |
| news18 | VECTOR | high | rich | mid | 1 |
| news18 | VECTOR | high | weak | high | 1 |
| news18 | VECTOR | high | weak | low | 1 |
| option8 | MATRIX | high | rich | high | 4 |
| option8 | MATRIX | high | weak | high | 4 |
| option9 | MATRIX | high | rich | high | 4 |
| option9 | MATRIX | high | rich | mid | 4 |
| pv1 | MATRIX | high | rich | high | 1 |
| pv1 | MATRIX | high | weak | high | 7 |
| pv13 | MATRIX | high | weak | high | 2 |
| pv13 | MATRIX | low | weak | mid | 2 |
| pv13 | MATRIX | mid | weak | high | 2 |
| pv13 | MATRIX | mid | weak | mid | 2 |

## 2. Discovery top-N（人工复核入口）

### audit_analyst_revision

Hypothesis: Which analyst estimate revisions and expectation changes carry information?

Focus terms: `analyst, revision, estimate, expectation, change`

| display rank | score rank | gap | field | dataset | score | focus overlap |
|---:|---:|---:|---|---|---:|---|
| 1 | 1 | 0 | `anl4_fs_detail_estimate_basic_af_v4_nd_previosestimate` | analyst4 | 13.764455845832018 | analyst, estimate, revision |
| 2 | 2 | 0 | `anl4_fs_detail_lt_v4_nd_estimate` | analyst4 | 10.80585620875659 | analyst, estimate |
| 3 | 3 | 0 | `anl4_fs_detail_lt_v4_nd_previosestimate` | analyst4 | 10.779024053077194 | estimate, revision |
| 4 | 4 | 0 | `anl4_fs_detail_estimate_basic_qf_v4_nd_previosestimate` | analyst4 | 10.757455845832018 | estimate, revision |
| 5 | 5 | 0 | `anl4_fs_detail_estimate_basic_af_v4_nd_estimate` | analyst4 | 10.731309335021201 | analyst, estimate |
| 6 | 6 | 0 | `anl4_fs_detail_estimates_basic_af_v4_nd_sales_high` | analyst4 | 10.719494267038474 | analyst, estimate |
| 7 | 7 | 0 | `anl4_fs_detail_estimates_basic_af_v4_nd_sales_low` | analyst4 | 10.719494267038474 | analyst, estimate |
| 8 | 8 | 0 | `anl4_fs_basic_splt_v4_nd_sales_previosestimate` | analyst4 | 10.691541490700594 | estimate, revision |
| 9 | 9 | 0 | `anl4_fs_detail_estimates_basic_af_v4_nd_sales_median` | analyst4 | 10.66151241751318 | analyst, estimate |
| 10 | 10 | 0 | `anl4_fs_basic_splt_v4_nd_sales_estimate` | analyst4 | 10.650678665594377 | analyst, estimate |

### audit_option_skew

Hypothesis: Which option implied volatility skew fields describe relative risk pricing?

Focus terms: `option, implied, volatility, skew, relative`

| display rank | score rank | gap | field | dataset | score | focus overlap |
|---:|---:|---:|---|---|---:|---|
| 1 | 6 | 5 | `option_breakeven_60` | option9 | 5.378389596854985 | option |
| 2 | 1 | -1 | `implied_volatility_mean_skew_20` | option8 | 14.225674472933632 | implied, option, skew, volatility |
| 3 | 7 | 4 | `option_breakeven_720` | option9 | 5.378389596854985 | option |
| 4 | 2 | -2 | `implied_volatility_mean_skew_10` | option8 | 14.21658738338545 | implied, option, skew, volatility |
| 5 | 8 | 3 | `option_breakeven_150` | option9 | 5.37272006248733 | option |
| 6 | 3 | -3 | `implied_volatility_mean_skew_150` | option8 | 14.203128367988173 | implied, option, skew, volatility |
| 7 | 9 | 2 | `option_breakeven_90` | option9 | 5.361087680441821 | option |
| 8 | 4 | -4 | `implied_volatility_mean_skew_120` | option8 | 14.190123055163355 | implied, option, skew, volatility |
| 9 | 10 | 1 | `option_breakeven_360` | option9 | 5.35172673052959 | option |
| 10 | 5 | -5 | `implied_volatility_mean_skew_60` | option8 | 14.184896212308779 | implied, option, skew, volatility |

### audit_liquidity_deterioration

Hypothesis: Which liquidity and trading activity fields identify deterioration or participation changes?

Focus terms: `liquidity, volume, turnover, activity, deterioration`

| display rank | score rank | gap | field | dataset | score | focus overlap |
|---:|---:|---:|---|---|---:|---|
| 1 | 1 | 0 | `volume` | pv1 | 4.700591327415783 | volume |
| 2 | 2 | 0 | `vwap` | pv1 | 1.8644453754319656 | volume |
| 3 | 3 | 0 | `adv20` | pv1 | 1.8229382707877708 | volume |

### audit_earnings_change

Hypothesis: Which earnings and fundamental fields capture operating expectation change?

Focus terms: `earnings, fundamental, revenue, profit, cash flow, change`

| display rank | score rank | gap | field | dataset | score | focus overlap |
|---:|---:|---:|---|---|---:|---|
| 1 | 6 | 5 | `cashflow_op` | fundamental6 | 8.981283839640962 | cash flow |
| 2 | 1 | -1 | `max_operating_cashflow_guidance_2` | analyst4 | 16.606817436727567 | cash flow |
| 3 | 7 | 4 | `cashflow_invst` | fundamental6 | 8.142604847476516 | cash flow |
| 4 | 2 | -2 | `min_operating_cashflow_guidance` | analyst4 | 16.582561273010437 | cash flow |
| 5 | 8 | 3 | `cashflow_dividends` | fundamental6 | 8.117915296662229 | cash flow |
| 6 | 3 | -3 | `max_operating_cashflow_guidance` | analyst4 | 16.543565180853218 | cash flow |
| 7 | 9 | 2 | `cashflow_fin` | fundamental6 | 8.096878629392126 | cash flow |
| 8 | 4 | -4 | `cash_flow_operations_min_guidance` | analyst4 | 13.621581036608173 | cash flow |
| 9 | 10 | 1 | `cashflow` | fundamental6 | 8.066293887524466 | NONE |
| 10 | 5 | -5 | `min_free_cash_flow_guidance` | analyst4 | 13.621581036608173 | cash flow |

### audit_sentiment_shock

Hypothesis: Which news and sentiment fields capture attention or belief shocks?

Focus terms: `news, sentiment, mention, event, shock`

| display rank | score rank | gap | field | dataset | score | focus overlap |
|---:|---:|---:|---|---|---:|---|
| 1 | 1 | 0 | `event_sentiment_score` | news18 | 10.606817436727567 | event, news, sentiment |
| 2 | 2 | 0 | `mean_event_sentiment_score` | news18 | 9.569593490679583 | event, sentiment |
| 3 | 3 | 0 | `global_event_novelty_score_2` | news18 | 6.690895754664169 | event, news |
| 4 | 4 | 0 | `event_novelty_score_2` | news18 | 6.670416313399567 | event, news |
| 5 | 5 | 0 | `story_event_record_count_fast_d1` | news18 | 6.606817436727567 | event, news |
| 6 | 6 | 0 | `merger_acquisition_sentiment` | news18 | 6.597464830926485 | news, sentiment |
| 7 | 7 | 0 | `equity_sentiment_score` | news18 | 6.59056554377779 | news, sentiment |
| 8 | 8 | 0 | `earnings_evaluation_sentiment` | news18 | 6.587286561495491 | news, sentiment |
| 9 | 9 | 0 | `composite_sentiment_score_2` | news18 | 6.5751504757950645 | news, sentiment |
| 10 | 10 | 0 | `corporate_action_sentiment` | news18 | 6.5751504757950645 | news, sentiment |

## 3. Semantic classification

- admission: `{'ALLOW': 59, 'REVIEW': 32, 'UNKNOWN': 9}`
- concept: `{'analyst_revision': 3, 'earnings': 20, 'analyst': 14, 'analyst_dispersion': 1, 'data_quality': 2, 'fundamental': 19, 'volatility': 9, 'sentiment': 8, 'liquidity': 3, 'market_price': 10, 'option_relative': 2, 'unknown': 9}`
- suspected false positive: **1**；suspected false negative: **0**

### Suspected semantic cases

| flag | field | dataset | concept | admission | description |
|---|---|---|---|---|---|
| suspected_false_positive | `implied_volatility_mean_90` | option8 | volatility | ALLOW | The average of IvCall90 and IvPut90 |

## 4. Template matching

| field | concept | top template | family | score | admission |
|---|---|---|---|---:|---|
| `anl4_epsa_flag` | analyst_revision | `delayed_confirmation` | delayed_confirmation | 100 | ALLOW |
| `anl4_fs_guidances_advanced_af_nd_epsa_minguidance` | earnings | `distribution_regime` | distribution_regime | 66 | ALLOW |
| `eps_adjusted_min_guidance_qtr` | earnings | `distribution_regime` | distribution_regime | 66 | ALLOW |
| `anl4_af_eps_value` | earnings | `distribution_regime` | distribution_regime | 66 | ALLOW |
| `ebit_median` | earnings | `distribution_regime` | distribution_regime | 46 | ALLOW |
| `min_adjusted_funds_from_operations_guidance` | analyst | `robust_cross_section` | robust_cross_section | 22 | REVIEW |
| `est_epsa` | earnings | `distribution_regime` | distribution_regime | 66 | ALLOW |
| `anl4_fs_detail_estimates_advanced_af_nd_rd_exp_number` | analyst | `distribution_regime` | distribution_regime | 36 | REVIEW |
| `anl4_fcfps_number` | earnings | `distribution_regime` | distribution_regime | 46 | ALLOW |
| `anl4_fs_detail_estimate_1qf_v4_nd_totgw_mean` | analyst | `distribution_regime` | distribution_regime | 32 | REVIEW |
| `anl4_qf_az_hgih_spfc` | earnings | `distribution_regime` | distribution_regime | 66 | ALLOW |
| `anl4_fs_detail_estimates_advanced_af_nd_sga_number` | analyst | `distribution_regime` | distribution_regime | 36 | REVIEW |
| `anl4_fs_detail_estimates_advanced_af_nd_epsr_std` | analyst_dispersion | `distribution_regime` | distribution_regime | 72 | ALLOW |
| `anl4_fcfps_flag` | analyst_revision | `delayed_confirmation` | delayed_confirmation | 100 | ALLOW |
| `anl4_fs_detail_estimates_advanced_af_nd_capex_mean` | analyst | `distribution_regime` | distribution_regime | 56 | REVIEW |
| `cash_flow_from_operations` | earnings | `distribution_regime` | distribution_regime | 46 | ALLOW |
| `anl4_dez1qfv4_est` | analyst | `vector_change_signal` | vector_change | -15 | REVIEW |
| `anl4_fs_detail_estimate_basic_af_v4_nd_currency` | analyst | `vector_change_signal` | vector_change | -15 | REVIEW |
| `estimate_value_currency_code` | analyst | `vector_change_signal` | vector_change | -15 | REVIEW |
| `anl4_basicqfv4_maxguidance` | analyst | `vector_change_signal` | vector_change | -15 | REVIEW |
| `anl4_fs_basic_splt_v4_nd_div_previosestimate` | analyst_revision | `vector_change_signal` | vector_change | 0 | REVIEW |
| `anl4_fs_guidance_basic_qf_v4_nd_estimate` | analyst | `vector_change_signal` | vector_change | -15 | REVIEW |
| `anl4_basicconqfv110_pu` | analyst | `vector_change_signal` | vector_change | -15 | REVIEW |
| `anl4_fsactualqfv4_actual` | data_quality | `vector_change_signal` | vector_change | 0 | REVIEW |
| `anl4_basicdetailqfv110_prevval` | data_quality | `vector_change_signal` | vector_change | 0 | REVIEW |
| `anl4_fs_guidances_advanced_qf_nd_totgw_maxguidance` | analyst | `distribution_regime` | distribution_regime | 32 | REVIEW |
| `max_ebitda_guidance` | earnings | `distribution_regime` | distribution_regime | 66 | ALLOW |
| `anl4_afv4_eps_low` | earnings | `distribution_regime` | distribution_regime | 66 | ALLOW |
| `anl4_fs_guidances_advanced_qf_nd_ffoa_minguidance` | analyst | `robust_cross_section` | robust_cross_section | 22 | REVIEW |
| `max_total_goodwill_guidance` | analyst | `distribution_regime` | distribution_regime | 32 | REVIEW |
| `fnd6_rank` | fundamental | `distribution_regime` | distribution_regime | 56 | REVIEW |
| `cashflow_op` | earnings | `distribution_regime` | distribution_regime | 46 | ALLOW |
| `fnd6_newq_xoptepsqp` | earnings | `distribution_regime` | distribution_regime | 66 | ALLOW |
| `fnd6_newqv1300_aol2q` | fundamental | `distribution_regime` | distribution_regime | 66 | ALLOW |
| `fnd6_newqeventv110_tstkq` | fundamental | `vector_change_signal` | vector_change | -15 | REVIEW |
| `fnd6_divd` | fundamental | `vector_change_signal` | vector_change | -15 | REVIEW |
| `fnd6_newqeventv110_ivstq` | fundamental | `vector_change_signal` | vector_change | -15 | REVIEW |
| `fnd6_optex` | fundamental | `distribution_regime` | distribution_regime | 56 | REVIEW |
| `fnd6_pncdq` | earnings | `distribution_regime` | distribution_regime | 66 | ALLOW |
| `fnd6_prclq` | fundamental | `distribution_regime` | distribution_regime | 56 | REVIEW |
| `fnd6_eventv110_dteepsq` | earnings | `vector_change_signal` | vector_change | 0 | REVIEW |
| `fnd6_iints` | fundamental | `vector_change_signal` | vector_change | -15 | REVIEW |
| `fnd6_newqeventv110_setpq` | fundamental | `vector_change_signal` | vector_change | -15 | REVIEW |
| `fnd6_fic` | fundamental | `distribution_regime` | distribution_regime | 36 | REVIEW |
| `fnd6_newqv1300_spceq` | earnings | `distribution_regime` | distribution_regime | 66 | ALLOW |
| `fnd6_txds` | fundamental | `distribution_regime` | distribution_regime | 56 | REVIEW |
| `fnd6_sics` | fundamental | `vector_change_signal` | vector_change | -15 | REVIEW |
| `fnd6_eventv110_gdwliepsq` | earnings | `vector_change_signal` | vector_change | 0 | REVIEW |
| `fnd6_newqeventv110_icaptq` | fundamental | `vector_change_signal` | vector_change | -15 | REVIEW |
| `fnd6_newqv1300_xsgaq` | fundamental | `distribution_regime` | distribution_regime | 56 | REVIEW |
| `fnd6_newqv1300_prcepsq` | earnings | `distribution_regime` | distribution_regime | 66 | ALLOW |
| `fnd6_reajo` | earnings | `distribution_regime` | distribution_regime | 66 | ALLOW |
| `fnd6_newqeventv110_diladq` | fundamental | `vector_change_signal` | vector_change | -15 | REVIEW |
| `fnd6_newqeventv110_prcd12` | earnings | `vector_change_signal` | vector_change | 0 | REVIEW |
| `fnd6_newqeventv110_lseq` | fundamental | `vector_change_signal` | vector_change | 0 | REVIEW |
| `fnd6_aox` | fundamental | `distribution_regime` | distribution_regime | 66 | ALLOW |
| `fnd6_newq_xoptdqp` | earnings | `distribution_regime` | distribution_regime | 66 | ALLOW |
| `fnd6_txtubxintbs` | fundamental | `distribution_regime` | distribution_regime | 56 | REVIEW |
| `fnd6_eventv110_optvolq` | volatility | `vector_change_signal` | vector_change | 0 | REVIEW |
| `fnd6_newqeventv110_lol2q` | fundamental | `vector_change_signal` | vector_change | 0 | REVIEW |
| `mean_earnings_evaluation_sentiment` | sentiment | `event_triggered_signal` | event_trigger | 65 | ALLOW |
| `rp_nip_inverstor` | sentiment | `event_triggered_signal` | event_trigger | 65 | ALLOW |
| `rp_nip_credit` | sentiment | `event_triggered_signal` | event_trigger | 65 | ALLOW |
| `nws18_nip` | sentiment | `vector_change_signal` | vector_change | 0 | REVIEW |
| `global_event_novelty_score_2` | sentiment | `vector_change_signal` | vector_change | 0 | REVIEW |
| `nws18_relevance` | sentiment | `vector_change_signal` | vector_change | -15 | REVIEW |
| `nws18_event_relevance` | sentiment | `vector_change_signal` | vector_change | -15 | REVIEW |
| `nws18_bee_fast_d1` | sentiment | `vector_change_signal` | vector_change | -15 | REVIEW |
| `implied_volatility_call_150` | volatility | `downside_volatility` | downside_risk | 77 | ALLOW |
| `implied_volatility_mean_90` | volatility | `downside_volatility` | downside_risk | 77 | ALLOW |
| `implied_volatility_mean_skew_150` | volatility | `downside_volatility` | downside_risk | 77 | ALLOW |
| `parkinson_volatility_150` | volatility | `downside_volatility` | downside_risk | 77 | ALLOW |
| `implied_volatility_put_60` | volatility | `downside_volatility` | downside_risk | 77 | ALLOW |
| `historical_volatility_90` | volatility | `downside_volatility` | downside_risk | 77 | ALLOW |
| `implied_volatility_call_10` | volatility | `downside_volatility` | downside_risk | 77 | ALLOW |
| `historical_volatility_60` | volatility | `downside_volatility` | downside_risk | 77 | ALLOW |
| `pcr_oi_180` | liquidity | `robust_cross_section` | robust_cross_section | 32 | ALLOW |
| `call_breakeven_60` | liquidity | `distribution_regime` | distribution_regime | 42 | ALLOW |
| `call_breakeven_180` | market_price | `distribution_regime` | distribution_regime | 42 | ALLOW |
| `forward_price_360` | option_relative | `distribution_regime` | distribution_regime | 42 | ALLOW |
| `pcr_oi_120` | option_relative | `robust_cross_section` | robust_cross_section | 32 | ALLOW |
| `option_breakeven_180` | market_price | `distribution_regime` | distribution_regime | 42 | ALLOW |
| `pcr_oi_30` | liquidity | `robust_cross_section` | robust_cross_section | 32 | ALLOW |
| `option_breakeven_20` | market_price | `robust_cross_section` | robust_cross_section | 32 | ALLOW |
| `adjfactor` | market_price | `robust_cross_section` | robust_cross_section | 32 | ALLOW |
| `adv20` | unknown | `robust_cross_section` | robust_cross_section | 22 | REVIEW |
| `vwap` | market_price | `robust_cross_section` | robust_cross_section | 32 | ALLOW |
| `low` | market_price | `distribution_regime` | distribution_regime | 42 | ALLOW |
| `open` | market_price | `distribution_regime` | distribution_regime | 42 | ALLOW |
| `returns` | market_price | `accumulated_change` | accumulated_change | 48 | ALLOW |
| `close` | market_price | `distribution_regime` | distribution_regime | 42 | ALLOW |
| `sharesout` | unknown | `distribution_regime` | distribution_regime | 32 | REVIEW |
| `pv13_com_page_rank` | unknown | `distribution_regime` | distribution_regime | 32 | REVIEW |
| `pv13_revere_term` | unknown | `distribution_regime` | distribution_regime | 32 | REVIEW |
| `pv13_revere_index_cap` | unknown | `distribution_regime` | distribution_regime | 32 | REVIEW |
| `pv13_revere_level` | unknown | `distribution_regime` | distribution_regime | 32 | REVIEW |
| `rel_num_all` | unknown | `robust_cross_section` | robust_cross_section | 22 | REVIEW |
| `single_sector_pureplay_company_count` | unknown | `robust_cross_section` | robust_cross_section | 22 | REVIEW |
| `rel_ret_part` | market_price | `accumulated_change` | accumulated_change | 48 | ALLOW |
| `pv13_revere_parent` | unknown | `distribution_regime` | distribution_regime | 32 | REVIEW |

## 5. Multi-field relationships

- pair candidates audited: **30**
- triple candidates audited: **10**
- pair selection is deliberately balanced across available admissions (ALLOW/REVIEW/REJECT) and relationship/dataset groups; it is not a prevalence estimate.

### Pair summary

| admission | relationship_type | count |
|---|---|---:|
| REJECT | comparable_scale | 11 |
| REJECT | numerator_denominator | 3 |
| REJECT | revision_dispersion | 1 |
| REVIEW | numerator_denominator | 1 |
| REVIEW | revision_dispersion | 1 |
| REVIEW | same_economic_concept | 3 |
| REVIEW | unknown | 10 |

| template | left | right | admission | relation | reasons |
|---|---|---|---|---|---|
| `generic_pair_ratio_extreme` | `ebit_median` | `fnd6_newqv1300_aol2q` | REVIEW | numerator_denominator | frequency compatibility is REVIEW; auto Factory cannot use it; frequency evidence is incomplete; relationship needs review |
| `generic_pair_spread_change` | `ebit_median` | `anl4_fs_detail_estimates_advanced_af_nd_epsr_std` | REVIEW | revision_dispersion | frequency compatibility is REVIEW; auto Factory cannot use it; frequency evidence is incomplete; relationship needs review |
| `relative_correlation_regime` | `ebit_median` | `anl4_fs_guidances_advanced_af_nd_epsa_minguidance` | REVIEW | same_economic_concept | frequency compatibility is REVIEW; auto Factory cannot use it; frequency evidence is incomplete; relationship needs review |
| `relative_spread_change` | `ebit_median` | `cashflow_op` | REVIEW | same_economic_concept | frequency compatibility is REVIEW; auto Factory cannot use it; frequency evidence is incomplete; relationship needs review |
| `relative_covariance` | `cashflow_op` | `fnd6_eventv110_gdwliepsq` | REVIEW | same_economic_concept | frequency compatibility is REVIEW; auto Factory cannot use it; frequency evidence is incomplete; relationship needs review |
| `relative_spread_change` | `ebit_median` | `anl4_basicconqfv110_pu` | REVIEW | unknown | 至少一个字段语义 UNKNOWN/REVIEW，不能宣称经济关系; frequency evidence is incomplete; relationship needs review |
| `relative_spread_change` | `ebit_median` | `fnd6_newqeventv110_tstkq` | REVIEW | unknown | 至少一个字段语义 UNKNOWN/REVIEW，不能宣称经济关系; frequency evidence is incomplete; relationship needs review |
| `relative_covariance` | `ebit_median` | `nws18_event_relevance` | REVIEW | unknown | 至少一个字段语义 UNKNOWN/REVIEW，不能宣称经济关系; frequency evidence is incomplete; relationship needs review |
| `relative_covariance` | `ebit_median` | `adv20` | REVIEW | unknown | 至少一个字段语义 UNKNOWN/REVIEW，不能宣称经济关系; frequency evidence is incomplete; relationship needs review |
| `relative_spread_change` | `ebit_median` | `pv13_com_page_rank` | REVIEW | unknown | 至少一个字段语义 UNKNOWN/REVIEW，不能宣称经济关系; frequency evidence is incomplete; relationship needs review |
| `relative_correlation_regime` | `fnd6_newqv1300_aol2q` | `fnd6_txds` | REVIEW | unknown | 至少一个字段语义 UNKNOWN/REVIEW，不能宣称经济关系; frequency evidence is incomplete; relationship needs review |
| `generic_pair_spread_change` | `fnd6_newqeventv110_tstkq` | `rp_nip_inverstor` | REVIEW | unknown | 至少一个字段语义 UNKNOWN/REVIEW，不能宣称经济关系; frequency evidence is incomplete; relationship needs review |
| `relative_correlation_regime` | `fnd6_newqeventv110_tstkq` | `implied_volatility_mean_90` | REVIEW | unknown | 至少一个字段语义 UNKNOWN/REVIEW，不能宣称经济关系; frequency evidence is incomplete; relationship needs review |
| `relative_ratio_extreme` | `fnd6_newqeventv110_tstkq` | `pcr_oi_30` | REVIEW | unknown | 至少一个字段语义 UNKNOWN/REVIEW，不能宣称经济关系; frequency evidence is incomplete; relationship needs review |
| `generic_pair_ratio_extreme` | `fnd6_newqeventv110_tstkq` | `sharesout` | REVIEW | unknown | 至少一个字段语义 UNKNOWN/REVIEW，不能宣称经济关系; frequency evidence is incomplete; relationship needs review |
| `generic_pair_ratio_extreme` | `ebit_median` | `anl4_fcfps_flag` | REJECT | comparable_scale | ratio requires a directional numerator/denominator or put/call pair; frequency evidence is incomplete; relationship needs review |
| `generic_pair_ratio_extreme` | `cashflow_op` | `anl4_fcfps_flag` | REJECT | comparable_scale | ratio requires a directional numerator/denominator or put/call pair; frequency evidence is incomplete; relationship needs review |
| `relative_spread_change` | `ebit_median` | `historical_volatility_90` | REJECT | comparable_scale | spread requires comparable quantities or an explicit differential; frequency evidence is incomplete; relationship needs review |
| `relative_ratio_extreme` | `ebit_median` | `option_breakeven_20` | REJECT | comparable_scale | ratio requires a directional numerator/denominator or put/call pair; frequency evidence is incomplete; relationship needs review |
| `relative_spread_change` | `ebit_median` | `vwap` | REJECT | comparable_scale | spread requires comparable quantities or an explicit differential; frequency evidence is incomplete; relationship needs review |
| `relative_spread_change` | `ebit_median` | `rel_ret_part` | REJECT | comparable_scale | spread requires comparable quantities or an explicit differential; frequency evidence is incomplete; relationship needs review |
| `generic_pair_spread_change` | `cashflow_op` | `rp_nip_inverstor` | REJECT | comparable_scale | spread requires comparable quantities or an explicit differential; frequency evidence is incomplete; relationship needs review |
| `relative_covariance` | `cashflow_op` | `parkinson_volatility_150` | REJECT | comparable_scale | co-movement requires a shared or explicitly complementary mechanism; frequency evidence is incomplete; relationship needs review |
| `relative_ratio_extreme` | `fnd6_newqv1300_aol2q` | `option_breakeven_20` | REJECT | comparable_scale | ratio requires a directional numerator/denominator or put/call pair; frequency evidence is incomplete; relationship needs review |
| `relative_correlation_regime` | `fnd6_newqv1300_aol2q` | `vwap` | REJECT | comparable_scale | co-movement requires a shared or explicitly complementary mechanism; frequency evidence is incomplete; relationship needs review |
| `generic_pair_ratio_extreme` | `fnd6_newqv1300_aol2q` | `rel_ret_part` | REJECT | comparable_scale | ratio requires a directional numerator/denominator or put/call pair; frequency evidence is incomplete; relationship needs review |
| `relative_ratio_extreme` | `fnd6_newqv1300_aol2q` | `anl4_epsa_flag` | REJECT | numerator_denominator | ratio direction is only proven for earnings over assets; frequency evidence is incomplete; relationship needs review |
| `relative_spread_change` | `cashflow_op` | `fnd6_eventv110_dteepsq` | REJECT | numerator_denominator | spread requires comparable quantities or an explicit differential; frequency evidence is incomplete; relationship needs review |
| `relative_spread_change` | `fnd6_newqv1300_aol2q` | `mean_earnings_evaluation_sentiment` | REJECT | numerator_denominator | spread requires comparable quantities or an explicit differential; frequency evidence is incomplete; relationship needs review |
| `generic_pair_ratio_extreme` | `ebit_median` | `anl4_fs_detail_estimates_advanced_af_nd_epsr_std` | REJECT | revision_dispersion | ratio requires a directional numerator/denominator or put/call pair; frequency evidence is incomplete; relationship needs review |

### Triple summary

| fields | admission | relation | reasons |
|---|---|---|---|
| `anl4_fcfps_flag`, `anl4_fs_detail_estimate_1qf_v4_nd_netprofita_std`, `rp_nip_inverstor` | REVIEW | unknown_confirmation | pair edges do not prove one shared confirmation mechanism; frequency evidence is incomplete; relationship needs review |
| `anl4_fcfps_flag`, `anl4_fs_detail_estimate_1qf_v4_nd_netprofita_std`, `rp_nip_ratings` | REVIEW | unknown_confirmation | pair edges do not prove one shared confirmation mechanism; frequency evidence is incomplete; relationship needs review |
| `anl4_fcfps_flag`, `anl4_fs_detail_estimate_1qf_v4_nd_netprofita_std`, `event_start_date_utc` | REVIEW | unknown | 至少一个字段语义 UNKNOWN/REVIEW，不能宣称经济关系; frequency evidence is incomplete; relationship needs review |
| `anl4_fcfps_flag`, `anl4_fs_detail_estimate_1qf_v4_nd_netprofita_std`, `anl4_under` | REVIEW | unknown_confirmation | pair edges do not prove one shared confirmation mechanism; frequency evidence is incomplete; relationship needs review |
| `anl4_fcfps_flag`, `anl4_fs_detail_estimate_1qf_v4_nd_netprofita_std`, `anl4_total_rec` | REVIEW | unknown_confirmation | pair edges do not prove one shared confirmation mechanism; frequency evidence is incomplete; relationship needs review |
| `anl4_fcfps_flag`, `anl4_fs_detail_estimate_1qf_v4_nd_netprofita_std`, `mean_earnings_evaluation_sentiment` | REVIEW | unknown_confirmation | pair edges do not prove one shared confirmation mechanism; frequency evidence is incomplete; relationship needs review |
| `anl4_fcfps_flag`, `anl4_fs_detail_estimate_1qf_v4_nd_netprofita_std`, `rp_nip_earnings` | REVIEW | unknown_confirmation | pair edges do not prove one shared confirmation mechanism; frequency evidence is incomplete; relationship needs review |
| `anl4_fcfps_flag`, `anl4_fs_detail_estimate_1qf_v4_nd_netprofita_std`, `editorial_commentary_sentiment_2` | REVIEW | unknown_confirmation | pair edges do not prove one shared confirmation mechanism; frequency evidence is incomplete; relationship needs review |
| `anl4_fcfps_flag`, `anl4_fs_detail_estimate_1qf_v4_nd_netprofita_std`, `rp_nip_credit` | REVIEW | unknown_confirmation | pair edges do not prove one shared confirmation mechanism; frequency evidence is incomplete; relationship needs review |
| `anl4_fcfps_flag`, `anl4_fs_detail_estimate_1qf_v4_nd_netprofita_std`, `global_event_novelty_score_2` | REVIEW | unknown_confirmation | pair edges do not prove one shared confirmation mechanism; frequency evidence is incomplete; relationship needs review |

## 6. Mechanism identity and proposals

- current proposal diversity: `{"proposal_count": 100, "expression": {"unique_count": 100, "diversity_ratio": 1.0}, "structure": {"unique_family_count": 17, "dominant_family": "robust_cross_section", "dominant_share": 0.13}, "semantic": {"known_mechanism_count": 9, "unknown_mechanism_count": 11, "dominant_mechanism": "liquidity:ratio:signed", "dominant_share": 0.1348314606741573}, "field_concepts": {"unique_known_count": 5, "unknown_count": 11}, "datasets": {"unique_count": 6}, "lineages": {"unique_independent_count": 17, "unknown_count": 0, "dominant_lineage_share": 0.1}, "warnings": [], "dominant_mechanism": "liquidity:ratio:signed", "dominant_mechanism_share": 0.1348314606741573, "dominant_structure": "robust_cross_section", "dominant_structure_share": 0.13, "layers": {"optimization": {"count": 0, "mechanism_count": 0, "lineage_count": 0, "field_concept_count": 0}, "exploration": {"count": 100, "mechanism_count": 9, "lineage_count": 17, "field_concept_count": 5}}}`
- current mechanism keys: **10**；UNKNOWN: **11**
- dry-run batch count: **100**
- dry-run priority distribution: `{'NORMAL': 92, 'LOW': 8}`

### Mechanism review candidates

- `earnings:level:slow_moving`：同一 key 下出现多个 template/relationship，需人工判断 false merge；families=['accumulated_change', 'adaptive_scale_change', 'compounding_pressure', 'delayed_confirmation', 'distribution_regime', 'distributional_change', 'extreme_location', 'group_centered_level', 'persistent_level', 'robust_cross_section']；relationships=['None']
- `earnings:probability:slow_moving`：同一 key 下出现多个 template/relationship，需人工判断 false merge；families=['accumulated_change', 'adaptive_scale_change', 'compounding_pressure', 'delayed_confirmation', 'distribution_regime', 'distributional_change', 'extreme_location', 'group_centered_level', 'persistent_level', 'robust_cross_section']；relationships=['None']
- `liquidity:ratio:signed`：同一 key 下出现多个 template/relationship，需人工判断 false merge；families=['adaptive_scale_change', 'compounding_pressure', 'delayed_confirmation', 'distribution_regime', 'risk_adjusted_reversal', 'robust_cross_section']；relationships=['None']
- `market_price:change:signed`：同一 key 下出现多个 template/relationship，需人工判断 false merge；families=['distributional_change', 'group_centered_level', 'group_relative_change', 'group_relative_extreme', 'robust_cross_section', 'turnover_control']；relationships=['None']
- `market_price:level:signed`：同一 key 下出现多个 template/relationship，需人工判断 false merge；families=['adaptive_scale_change', 'delayed_confirmation', 'distribution_regime', 'group_centered_level', 'risk_adjusted_reversal', 'robust_cross_section']；relationships=['None']
- `sentiment:level:event_driven`：同一 key 下出现多个 template/relationship，需人工判断 false merge；families=['adaptive_scale_change', 'distribution_regime', 'group_centered_level', 'persistent_level', 'robust_cross_section', 'vector_change', 'vector_persistence']；relationships=['None']
- `sentiment:ratio:event_driven`：同一 key 下出现多个 template/relationship，需人工判断 false merge；families=['adaptive_scale_change', 'vector_change', 'vector_persistence']；relationships=['None']
- `volatility:level:signed`：同一 key 下出现多个 template/relationship，需人工判断 false merge；families=['accumulated_change', 'adaptive_scale_change', 'compounding_pressure', 'distribution_regime', 'downside_risk', 'group_centered_level', 'persistent_level', 'risk_adjusted_reversal', 'robust_cross_section']；relationships=['None']
- `volatility:ratio:signed`：同一 key 下出现多个 template/relationship，需人工判断 false merge；families=['accumulated_change', 'adaptive_scale_change', 'compounding_pressure', 'delayed_confirmation', 'distribution_regime', 'distributional_change', 'downside_risk', 'risk_adjusted_reversal', 'robust_cross_section']；relationships=['None']

### Budget priority controlled probe

- baseline on the real dry-run batch: `{'NORMAL': 92, 'LOW': 8}`
- self-question unresolved-context probe: `{'HIGH': 19, 'LOW': 1}` for **20** candidates; this is a rule-sensitivity probe, not evidence that the questions are resolved.

## 7. HIGH/NORMAL/LOW 候选人工抽查

| priority | field(s) | template | mechanism | question |
|---|---|---|---|---|
| NORMAL | anl4_fs_detail_estimates_advanced_af_nd_epsr_std | `group_centered_level` | 字段 anl4_fs_detail_estimates_advanced_af_nd_epsr_std 被识别为 analyst_dispersion，测量为 dispersion，频率为 annual，符号语义为 nonnegative_dispersion | 字段 anl4_fs_detail_estimates_advanced_af_nd_epsr_std 的 group_centered_level 结构是否提供可复现的增量信号？ |
| NORMAL | anl4_afv4_eps_low, anl4_fs_detail_estimates_advanced_af_nd_epsr_std | `relative_spread_change` | 字段 anl4_afv4_eps_low 被识别为 earnings，测量为 level，频率为 annual，符号语义为 nonnegative_level，行为为 slow_moving；盈利相关字段承载经营预期，适合变化与信息扩散检验。该机制仍需用独立样 | 字段 anl4_afv4_eps_low 的 relative_spread_change 结构是否提供可复现的增量信号？ |
| NORMAL | cash_flow_from_operations, anl4_fs_detail_estimates_advanced_af_nd_epsr_std | `generic_pair_spread_change` | 字段 cash_flow_from_operations 被识别为 earnings，测量为 ratio，频率为 annual，符号语义为 nonnegative_level，行为为 slow_moving；盈利相关字段承载经营预期，适合变化与信息扩散检验。该 | 字段 cash_flow_from_operations 的 generic_pair_spread_change 结构是否提供可复现的增量信号？ |
| NORMAL | anl4_basicdetailqfv110_prevval | `vector_change_signal` | 字段 anl4_basicdetailqfv110_prevval 被识别为 data_quality，测量为 level，频率为 unknown，符号语义为 nonnegative_level，行为为 unknown；数据质量字段描述可用性风险，只进入缺失或 | 字段 anl4_basicdetailqfv110_prevval 的 vector_change_signal 结构是否提供可复现的增量信号？ |
| NORMAL | fnd6_newqv1300_spceq | `group_centered_level` | 字段 fnd6_newqv1300_spceq 被识别为 earnings，测量为 level，频率为 unknown，符号语义为 nonnegative_level，行为为 slow_moving；盈利相关字段承载经营预期，适合变化与信息扩散检验。该机制仍需 | 字段 fnd6_newqv1300_spceq 的 group_centered_level 结构是否提供可复现的增量信号？ |
| NORMAL | cash_flow_from_operations, anl4_afv4_eps_low | `relative_correlation_regime` | 字段 cash_flow_from_operations 被识别为 earnings，测量为 ratio，频率为 annual，符号语义为 nonnegative_level，行为为 slow_moving；盈利相关字段承载经营预期，适合变化与信息扩散检验。该 | 字段 cash_flow_from_operations 的 relative_correlation_regime 结构是否提供可复现的增量信号？ |
| NORMAL | max_ebitda_guidance, anl4_afv4_eps_low | `generic_pair_spread_change` | 字段 max_ebitda_guidance 被识别为 earnings，测量为 level，频率为 annual，符号语义为 nonnegative_level，行为为 slow_moving；盈利相关字段承载经营预期，适合变化与信息扩散检验。该机制仍需用独 | 字段 max_ebitda_guidance 的 generic_pair_spread_change 结构是否提供可复现的增量信号？ |
| NORMAL | fnd6_newqv1300_aol2q | `group_centered_level` | 字段 fnd6_newqv1300_aol2q 被识别为 fundamental，测量为 level，频率为 unknown，符号语义为 nonnegative_level，行为为 slow_moving；低频基本面水平代表经济规模，适合持久性和相对状态检验。 | 字段 fnd6_newqv1300_aol2q 的 group_centered_level 结构是否提供可复现的增量信号？ |
| NORMAL | call_breakeven_60 | `group_centered_level` | 字段 call_breakeven_60 被识别为 liquidity，测量为 level，频率为 unknown，符号语义为 nonnegative_level，行为为 signed；交易活跃度或未平仓量描述参与程度，适合流动性与活动强度检验。该机制仍需用独 | 字段 call_breakeven_60 的 group_centered_level 结构是否提供可复现的增量信号？ |
| NORMAL | vwap, rel_ret_part | `relative_correlation_regime` | 字段 vwap 被识别为 market_price，测量为 count，频率为 daily，符号语义为 signed_level，行为为 signed；该字段的 count 测量与 relative_correlation 的有限结构相容。该机制仍需用独立样本 | 字段 vwap 的 relative_correlation_regime 结构是否提供可复现的增量信号？ |
| NORMAL | low, rel_ret_part | `relative_correlation_regime` | 字段 low 被识别为 market_price，测量为 level，频率为 daily，符号语义为 signed_level，行为为 signed；该字段的 level 测量与 relative_correlation 的有限结构相容。该机制仍需用独立样本和 | 字段 low 的 relative_correlation_regime 结构是否提供可复现的增量信号？ |
| NORMAL | rel_ret_part, returns | `generic_pair_spread_change` | 字段 rel_ret_part 被识别为 market_price，测量为 change，频率为 daily，符号语义为 signed_change，行为为 signed；该字段的 change 测量与 generic_multi_field_spread 的 | 字段 rel_ret_part 的 generic_pair_spread_change 结构是否提供可复现的增量信号？ |
| NORMAL | close, low | `relative_spread_change` | 字段 close 被识别为 market_price，测量为 level，频率为 daily，符号语义为 signed_level，行为为 signed；该字段的 level 测量与 relative_spread_change 的有限结构相容。该机制仍需用独 | 字段 close 的 relative_spread_change 结构是否提供可复现的增量信号？ |
| NORMAL | pcr_oi_120 | `distribution_regime` | 字段 pcr_oi_120 被识别为 option_relative，测量为 ratio，频率为 unknown，符号语义为 bounded，行为为 bounded；put-call/skew 字段表达期权分布的相对位置，适合离散或相对关系检验。该机制仍需用独 | 字段 pcr_oi_120 的 distribution_regime 结构是否提供可复现的增量信号？ |
| NORMAL | nws18_nip | `vector_change_signal` | 字段 nws18_nip 被识别为 sentiment，测量为 level，频率为 unknown，符号语义为 signed_level，行为为 event_driven；该字段的 level 测量与 vector_change 的有限结构相容。该机制仍需用独 | 字段 nws18_nip 的 vector_change_signal 结构是否提供可复现的增量信号？ |
| NORMAL | implied_volatility_mean_90 | `reversal_vol_adjusted` | 字段 implied_volatility_mean_90 被识别为 volatility，测量为 level，频率为 unknown，符号语义为 nonnegative_level，行为为 signed；波动率是风险暴露或状态变量，适合风险调整、regime | 字段 implied_volatility_mean_90 的 reversal_vol_adjusted 结构是否提供可复现的增量信号？ |
| NORMAL | implied_volatility_call_10 | `reversal_vol_adjusted` | 字段 implied_volatility_call_10 被识别为 volatility，测量为 ratio，频率为 unknown，符号语义为 nonnegative_level，行为为 signed；波动率是风险暴露或状态变量，适合风险调整、regime | 字段 implied_volatility_call_10 的 reversal_vol_adjusted 结构是否提供可复现的增量信号？ |
| NORMAL | anl4_fs_detail_estimates_advanced_af_nd_epsr_std | `extreme_low_continuation` | 字段 anl4_fs_detail_estimates_advanced_af_nd_epsr_std 被识别为 analyst_dispersion，测量为 dispersion，频率为 annual，符号语义为 nonnegative_dispersion | 字段 anl4_fs_detail_estimates_advanced_af_nd_epsr_std 的 extreme_low_continuation 结构是否提供可复现的增量信号？ |
| NORMAL | anl4_fs_detail_estimates_advanced_af_nd_epsr_std, anl4_afv4_eps_low | `generic_pair_spread_change` | 字段 anl4_fs_detail_estimates_advanced_af_nd_epsr_std 被识别为 analyst_dispersion，测量为 dispersion，频率为 annual，符号语义为 nonnegative_dispersion | 字段 anl4_fs_detail_estimates_advanced_af_nd_epsr_std 的 generic_pair_spread_change 结构是否提供可复现的增量信号？ |
| NORMAL | anl4_fsactualqfv4_actual | `vector_change_signal` | 字段 anl4_fsactualqfv4_actual 被识别为 data_quality，测量为 level，频率为 unknown，符号语义为 nonnegative_level，行为为 unknown；数据质量字段描述可用性风险，只进入缺失或陈旧信息机制 | 字段 anl4_fsactualqfv4_actual 的 vector_change_signal 结构是否提供可复现的增量信号？ |
| LOW | anl4_basicconqfv110_pu | `vector_change_signal` | 字段 anl4_basicconqfv110_pu 的语义准入为 REVIEW；当前 profile 只能支持 vector_change 的语法审阅，不能证明该字段具备该经济机制。 | 字段 anl4_basicconqfv110_pu 的 vector_change_signal 结构是否提供可复现的增量信号？ |
| LOW | anl4_dez1qfv4_est | `vector_change_signal` | 字段 anl4_dez1qfv4_est 的语义准入为 REVIEW；当前 profile 只能支持 vector_change 的语法审阅，不能证明该字段具备该经济机制。 | 字段 anl4_dez1qfv4_est 的 vector_change_signal 结构是否提供可复现的增量信号？ |
| LOW | estimate_value_currency_code | `vector_change_signal` | 字段 estimate_value_currency_code 的语义准入为 REVIEW；当前 profile 只能支持 vector_change 的语法审阅，不能证明该字段具备该经济机制。 | 字段 estimate_value_currency_code 的 vector_change_signal 结构是否提供可复现的增量信号？ |
| LOW | fnd6_newqeventv110_ivstq | `vector_change_signal` | 字段 fnd6_newqeventv110_ivstq 的语义准入为 REVIEW；当前 profile 只能支持 vector_change 的语法审阅，不能证明该字段具备该经济机制。 | 字段 fnd6_newqeventv110_ivstq 的 vector_change_signal 结构是否提供可复现的增量信号？ |
| LOW | fnd6_newqeventv110_setpq | `vector_change_signal` | 字段 fnd6_newqeventv110_setpq 的语义准入为 REVIEW；当前 profile 只能支持 vector_change 的语法审阅，不能证明该字段具备该经济机制。 | 字段 fnd6_newqeventv110_setpq 的 vector_change_signal 结构是否提供可复现的增量信号？ |
| LOW | fnd6_newqeventv110_tstkq | `vector_change_signal` | 字段 fnd6_newqeventv110_tstkq 的语义准入为 REVIEW；当前 profile 只能支持 vector_change 的语法审阅，不能证明该字段具备该经济机制。 | 字段 fnd6_newqeventv110_tstkq 的 vector_change_signal 结构是否提供可复现的增量信号？ |
| LOW | nws18_bee_fast_d1 | `vector_change_signal` | 字段 nws18_bee_fast_d1 的语义准入为 REVIEW；当前 profile 只能支持 vector_change 的语法审阅，不能证明该字段具备该经济机制。 | 字段 nws18_bee_fast_d1 的 vector_change_signal 结构是否提供可复现的增量信号？ |
| LOW | anl4_basicconqfv110_pu | `vector_persistent_signal` | 字段 anl4_basicconqfv110_pu 的语义准入为 REVIEW；当前 profile 只能支持 vector_persistence 的语法审阅，不能证明该字段具备该经济机制。 | 字段 anl4_basicconqfv110_pu 的 vector_persistent_signal 结构是否提供可复现的增量信号？ |

## 8. 结论记录（人工）

### Discovery

- `audit_analyst_revision`：returned=10，focus-hit=10/10，score/display inversion=0。
- `audit_option_skew`：returned=10，focus-hit=10/10，score/display inversion=10。
- `audit_liquidity_deterioration`：returned=3，focus-hit=3/3，score/display inversion=0。
- `audit_earnings_change`：returned=10，focus-hit=9/10，score/display inversion=10。
- `audit_sentiment_shock`：returned=10，focus-hit=10/10，score/display inversion=0。
- `audit_liquidity_deterioration` 在显式 semantic 模式下只返回 3 个 pv1 字段，pv13 没有直接命中 focus 词；这是安全的候选不足，不应凭空把 pv13 的分类/竞争者字段当成流动性字段。
- 本轮已确认并修复的生产问题是英语功能词进入关键词（真实 `pv13` 字段曾因 `or` 被选中）；修复后该假设不再返回这些 coverage-only 字段。
- option/earnings 的 score/display inversion 来自既有 stratified round-robin contract；本轮未把它误报为 ranking bug。option 候选中 breakeven 是期权相关但不是 skew-specific，需由 Agent 在假设层继续筛选。

### Semantic and template

- semantic admission: `{'ALLOW': 59, 'REVIEW': 32, 'UNKNOWN': 9}`；唯一机器 false-positive review candidate 是 `implied_volatility_mean_90`，其描述明确是 IvCall/IvPut 平均值，人工判断为 volatility 的合理 ALLOW，不构成修复依据；未发现机器 false-negative。
- top template admissions: `{'ALLOW': 48, 'REVIEW': 52}`；真实 sample 中 `distribution_regime` 与 `vector_change_signal` 占多数，需结合字段描述和研究问题解释，不能仅按 template 名称计为机制新颖性。

### Relationships, mechanism identity, budget

- pair summary: `{'REVIEW': 15, 'REJECT': 15}`；triple summary: `{'REVIEW': 10}`。本轮没有因频率缺失而宣称 ALLOW：显式关系在 frequency UNKNOWN 时保持 REVIEW，非 comparable pairs 保持 REJECT。
- mechanism identity: 100 historical proposals、10 个已见机制 key、11 个 UNKNOWN；100/100 expression unique、19 个 structure families、15 个 lineages。6 个 cluster 是 false-merge review candidates，当前没有独立证据确认 false split/merge。
- budget: real dry-run batch 100 个，priority `{'NORMAL': 92, 'LOW': 8}`；其中 UNKNOWN mechanism key 的 8 个候选被降为 LOW，未被伪装成 HIGH，但当前 target=100 时仍会作为低优先级候补，属于下一步 policy review 风险。

### Production decision

- production change: 仅补齐 Discovery 英语功能词停用词，并为该行为增加两个红绿回归测试；未新增 workflow/state/scheduler，也未改变 relationship、mechanism 或 budget contract。
- no-change areas: semantic classifier、template registry、relationship gate、mechanism key 和 budget selection 未因单个 review candidate 改动。
- Simulation recommendation: 暂不进入真实 Simulation；先由 Agent 复核 3 个跨假设质量问题（option skew specificity、earnings change specificity、LOW UNKNOWN candidate policy），随后才考虑小规模、明确假设的验证。
