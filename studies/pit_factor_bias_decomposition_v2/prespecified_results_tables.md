# Pre Specified Stage 2 Results Tables

## Status and use

This supplement fixes the post-results reporting layout before the 2010-2022 historical analysis. No Stage-2 outcome has been computed or inserted. Every empirical field is marked **Not yet estimated**, and every claim remains ineligible until the complete data, rights, custody, registration, authorization, endpoint, identity, isolation, and cell-completeness gates pass.

The verified result receipt, not manual selection, must populate the final tables. Rows may not be removed, reordered to emphasize performance, or replaced with a better-looking factor or statistic. If a registered cell or estimand is non-estimable, its row remains and reports the registered failure status.

## Primary result

| Record type | Position | Estimand ID | Definition | Directional prediction | Mean difference | HAC SE | t statistic | Two-sided p | 95 percent CI | Paired months | Comparator mean IC | Publication mean IC | Claim status |
|---|---:|---|---|---|---|---|---|---|---|---|---|---|---|
| PRIMARY | 1 | `P1_roe_publication_signed_decrement` | Mean monthly ROE IC difference `I0000_pit_publication - A1_pit_report_end` | Mean less than zero; two-sided zero-mean test | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not yet estimated | Not yet estimated | Ineligible before authorized execution |

The terms *attenuation* or *timing inflation* are permitted only when the report-period comparator mean IC is positive and the signed difference is negative. Otherwise the result is a recorded-publication displacement.

## Secondary inferential family

All 28 rows below enter one Benjamini-Hochberg family at false-discovery rate 0.10. A non-estimable member remains in the family denominator and is a non-rejection.

| Record type | Family position | Estimand ID | Factor | Definition | Mean difference | HAC SE | t statistic | Two-sided p | BH adjusted p | Paired months | Claim status |
|---|---:|---|---|---|---|---|---|---|---|---|---|
| SECONDARY | 1 | `S_composite_publication_signed_decrement` | Composite | `I0000_pit_publication - A1_pit_report_end` composite IC | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 2 | `S_membership_roe_ic` | ROE | `A1_pit_report_end - A0_final_report_end` IC | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 3 | `S_full_implementation_roe_ic` | ROE | `I1111_full_implementation - I0000_pit_publication` IC | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 4 | `S_membership_momentum_60d_ic` | Momentum 60d | `A1_pit_report_end - A0_final_report_end` IC | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 5 | `S_full_implementation_momentum_60d_ic` | Momentum 60d | `I1111_full_implementation - I0000_pit_publication` IC | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 6 | `S_membership_low_vol_20d_ic` | Low volatility 20d | `A1_pit_report_end - A0_final_report_end` IC | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 7 | `S_full_implementation_low_vol_20d_ic` | Low volatility 20d | `I1111_full_implementation - I0000_pit_publication` IC | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 8 | `S_membership_composite_ic` | Composite | `A1_pit_report_end - A0_final_report_end` IC | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 9 | `S_full_implementation_composite_ic` | Composite | `I1111_full_implementation - I0000_pit_publication` IC | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 10 | `S_roe_timing_report_support_restriction` | ROE | report support restriction | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 11 | `S_roe_timing_common_support_record_replacement` | ROE | common support record replacement | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 12 | `S_roe_timing_publication_support_extension` | ROE | publication support extension | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 13 | `S_shapley_roe_exclude_st_ic` | ROE | Exact monthly Shapley contribution of `exclude_st` to IC | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 14 | `S_shapley_roe_exclude_suspended_ic` | ROE | Exact monthly Shapley contribution of `exclude_suspended` to IC | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 15 | `S_shapley_roe_minimum_amount_20d_ic` | ROE | Exact monthly Shapley contribution of `minimum_amount_20d` to IC | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 16 | `S_shapley_roe_one_session_lag_ic` | ROE | Exact monthly Shapley contribution of `one_session_lag` to IC | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 17 | `S_shapley_momentum_60d_exclude_st_ic` | Momentum 60d | Exact monthly Shapley contribution of `exclude_st` to IC | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 18 | `S_shapley_momentum_60d_exclude_suspended_ic` | Momentum 60d | Exact monthly Shapley contribution of `exclude_suspended` to IC | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 19 | `S_shapley_momentum_60d_minimum_amount_20d_ic` | Momentum 60d | Exact monthly Shapley contribution of `minimum_amount_20d` to IC | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 20 | `S_shapley_momentum_60d_one_session_lag_ic` | Momentum 60d | Exact monthly Shapley contribution of `one_session_lag` to IC | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 21 | `S_shapley_low_vol_20d_exclude_st_ic` | Low volatility 20d | Exact monthly Shapley contribution of `exclude_st` to IC | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 22 | `S_shapley_low_vol_20d_exclude_suspended_ic` | Low volatility 20d | Exact monthly Shapley contribution of `exclude_suspended` to IC | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 23 | `S_shapley_low_vol_20d_minimum_amount_20d_ic` | Low volatility 20d | Exact monthly Shapley contribution of `minimum_amount_20d` to IC | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 24 | `S_shapley_low_vol_20d_one_session_lag_ic` | Low volatility 20d | Exact monthly Shapley contribution of `one_session_lag` to IC | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 25 | `S_shapley_composite_exclude_st_ic` | Composite | Exact monthly Shapley contribution of `exclude_st` to IC | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 26 | `S_shapley_composite_exclude_suspended_ic` | Composite | Exact monthly Shapley contribution of `exclude_suspended` to IC | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 27 | `S_shapley_composite_minimum_amount_20d_ic` | Composite | Exact monthly Shapley contribution of `minimum_amount_20d` to IC | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |
| SECONDARY | 28 | `S_shapley_composite_one_session_lag_ic` | Composite | Exact monthly Shapley contribution of `one_session_lag` to IC | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Ineligible before authorized execution |

## Deterministic timing isolation checks

| Check ID | Factor | Definition | Absolute tolerance | Maximum absolute difference | Passed | Consequence |
|---|---|---|---:|---|---|---|
| `C_publication_isolation_momentum_60d` | Momentum 60d | `I0000_pit_publication - A1_pit_report_end` IC | `1e-12` | Not yet estimated | Not yet estimated | Any nonzero failure invalidates the run |
| `C_publication_isolation_low_vol_20d` | Low volatility 20d | `I0000_pit_publication - A1_pit_report_end` IC | `1e-12` | Not yet estimated | Not yet estimated | Any nonzero failure invalidates the run |

## Publication exposure and support diagnostics

These fields use no forward return and remain outside the inferential family.

| Diagnostic | Definition | Full-sample result | Monthly detail | Inference |
|---|---|---|---|---|
| Premature report-record share | Report-period-selected records with `publishDate >= signal date` divided by report signal count | Not yet estimated | Not yet estimated | Descriptive only |
| Changed report-period share | Common-signal-support securities selecting a different report-period identity under the two clocks | Not yet estimated | Not yet estimated | Descriptive only |
| Reporting-delay calendar days | Count, mean, median, p25, p75, and maximum from report-period end to recorded publication date | Not yet estimated | Not yet estimated | Descriptive only |
| Report signal support | Report signal, report-only, and missing-publication-date counts | Not yet estimated | Not yet estimated | Descriptive only |
| Publication signal support | Publication signal, publication-only, and common-signal counts | Not yet estimated | Not yet estimated | Descriptive only |
| Common-support identity | Three monthly components, total timing difference, and efficiency residual | Not yet estimated | Not yet estimated | Identity tolerance `1e-12` |

## Complete factor variant cell table

All 72 factor-variant rows are descriptive completeness outputs. The mean IC, Newey-West t statistic, top-minus-universe diagnostic, mean N, complete-month count, and status must be reported for every row. This table does not create 72 hypothesis tests.

| Record type | Position | Variant | Factor | Universe | Accounting clock | Implementation components | Mean IC | NW t | Top minus universe | Mean N | Complete months | Status |
|---|---:|---|---|---|---|---|---|---|---|---|---|---|
| CELL | 1 | `A0_final_report_end` | `roe` | Fixed 2023-01-31 terminal survivors | Report-period end | None | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 2 | `A0_final_report_end` | `momentum_60d` | Fixed 2023-01-31 terminal survivors | Report-period end | None | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 3 | `A0_final_report_end` | `low_vol_20d` | Fixed 2023-01-31 terminal survivors | Report-period end | None | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 4 | `A0_final_report_end` | `composite` | Fixed 2023-01-31 terminal survivors | Report-period end | None | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 5 | `A1_pit_report_end` | `roe` | Point in time | Report-period end | None | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 6 | `A1_pit_report_end` | `momentum_60d` | Point in time | Report-period end | None | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 7 | `A1_pit_report_end` | `low_vol_20d` | Point in time | Report-period end | None | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 8 | `A1_pit_report_end` | `composite` | Point in time | Report-period end | None | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 9 | `I0000_pit_publication` | `roe` | Point in time | Recorded publication date | None | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 10 | `I0000_pit_publication` | `momentum_60d` | Point in time | Recorded publication date | None | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 11 | `I0000_pit_publication` | `low_vol_20d` | Point in time | Recorded publication date | None | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 12 | `I0000_pit_publication` | `composite` | Point in time | Recorded publication date | None | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 13 | `I1000_st` | `roe` | Point in time | Recorded publication date | ST exclusion | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 14 | `I1000_st` | `momentum_60d` | Point in time | Recorded publication date | ST exclusion | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 15 | `I1000_st` | `low_vol_20d` | Point in time | Recorded publication date | ST exclusion | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 16 | `I1000_st` | `composite` | Point in time | Recorded publication date | ST exclusion | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 17 | `I0100_suspension` | `roe` | Point in time | Recorded publication date | Suspension exclusion | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 18 | `I0100_suspension` | `momentum_60d` | Point in time | Recorded publication date | Suspension exclusion | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 19 | `I0100_suspension` | `low_vol_20d` | Point in time | Recorded publication date | Suspension exclusion | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 20 | `I0100_suspension` | `composite` | Point in time | Recorded publication date | Suspension exclusion | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 21 | `I0010_liquidity` | `roe` | Point in time | Recorded publication date | CNY 5m amount floor | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 22 | `I0010_liquidity` | `momentum_60d` | Point in time | Recorded publication date | CNY 5m amount floor | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 23 | `I0010_liquidity` | `low_vol_20d` | Point in time | Recorded publication date | CNY 5m amount floor | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 24 | `I0010_liquidity` | `composite` | Point in time | Recorded publication date | CNY 5m amount floor | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 25 | `I0001_lag` | `roe` | Point in time | Recorded publication date | One-session lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 26 | `I0001_lag` | `momentum_60d` | Point in time | Recorded publication date | One-session lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 27 | `I0001_lag` | `low_vol_20d` | Point in time | Recorded publication date | One-session lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 28 | `I0001_lag` | `composite` | Point in time | Recorded publication date | One-session lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 29 | `I1100_st_suspension` | `roe` | Point in time | Recorded publication date | ST; suspension | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 30 | `I1100_st_suspension` | `momentum_60d` | Point in time | Recorded publication date | ST; suspension | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 31 | `I1100_st_suspension` | `low_vol_20d` | Point in time | Recorded publication date | ST; suspension | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 32 | `I1100_st_suspension` | `composite` | Point in time | Recorded publication date | ST; suspension | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 33 | `I1010_st_liquidity` | `roe` | Point in time | Recorded publication date | ST; liquidity | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 34 | `I1010_st_liquidity` | `momentum_60d` | Point in time | Recorded publication date | ST; liquidity | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 35 | `I1010_st_liquidity` | `low_vol_20d` | Point in time | Recorded publication date | ST; liquidity | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 36 | `I1010_st_liquidity` | `composite` | Point in time | Recorded publication date | ST; liquidity | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 37 | `I1001_st_lag` | `roe` | Point in time | Recorded publication date | ST; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 38 | `I1001_st_lag` | `momentum_60d` | Point in time | Recorded publication date | ST; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 39 | `I1001_st_lag` | `low_vol_20d` | Point in time | Recorded publication date | ST; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 40 | `I1001_st_lag` | `composite` | Point in time | Recorded publication date | ST; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 41 | `I0110_suspension_liquidity` | `roe` | Point in time | Recorded publication date | Suspension; liquidity | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 42 | `I0110_suspension_liquidity` | `momentum_60d` | Point in time | Recorded publication date | Suspension; liquidity | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 43 | `I0110_suspension_liquidity` | `low_vol_20d` | Point in time | Recorded publication date | Suspension; liquidity | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 44 | `I0110_suspension_liquidity` | `composite` | Point in time | Recorded publication date | Suspension; liquidity | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 45 | `I0101_suspension_lag` | `roe` | Point in time | Recorded publication date | Suspension; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 46 | `I0101_suspension_lag` | `momentum_60d` | Point in time | Recorded publication date | Suspension; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 47 | `I0101_suspension_lag` | `low_vol_20d` | Point in time | Recorded publication date | Suspension; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 48 | `I0101_suspension_lag` | `composite` | Point in time | Recorded publication date | Suspension; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 49 | `I0011_liquidity_lag` | `roe` | Point in time | Recorded publication date | Liquidity; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 50 | `I0011_liquidity_lag` | `momentum_60d` | Point in time | Recorded publication date | Liquidity; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 51 | `I0011_liquidity_lag` | `low_vol_20d` | Point in time | Recorded publication date | Liquidity; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 52 | `I0011_liquidity_lag` | `composite` | Point in time | Recorded publication date | Liquidity; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 53 | `I1110_st_suspension_liquidity` | `roe` | Point in time | Recorded publication date | ST; suspension; liquidity | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 54 | `I1110_st_suspension_liquidity` | `momentum_60d` | Point in time | Recorded publication date | ST; suspension; liquidity | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 55 | `I1110_st_suspension_liquidity` | `low_vol_20d` | Point in time | Recorded publication date | ST; suspension; liquidity | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 56 | `I1110_st_suspension_liquidity` | `composite` | Point in time | Recorded publication date | ST; suspension; liquidity | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 57 | `I1101_st_suspension_lag` | `roe` | Point in time | Recorded publication date | ST; suspension; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 58 | `I1101_st_suspension_lag` | `momentum_60d` | Point in time | Recorded publication date | ST; suspension; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 59 | `I1101_st_suspension_lag` | `low_vol_20d` | Point in time | Recorded publication date | ST; suspension; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 60 | `I1101_st_suspension_lag` | `composite` | Point in time | Recorded publication date | ST; suspension; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 61 | `I1011_st_liquidity_lag` | `roe` | Point in time | Recorded publication date | ST; liquidity; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 62 | `I1011_st_liquidity_lag` | `momentum_60d` | Point in time | Recorded publication date | ST; liquidity; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 63 | `I1011_st_liquidity_lag` | `low_vol_20d` | Point in time | Recorded publication date | ST; liquidity; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 64 | `I1011_st_liquidity_lag` | `composite` | Point in time | Recorded publication date | ST; liquidity; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 65 | `I0111_suspension_liquidity_lag` | `roe` | Point in time | Recorded publication date | Suspension; liquidity; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 66 | `I0111_suspension_liquidity_lag` | `momentum_60d` | Point in time | Recorded publication date | Suspension; liquidity; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 67 | `I0111_suspension_liquidity_lag` | `low_vol_20d` | Point in time | Recorded publication date | Suspension; liquidity; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 68 | `I0111_suspension_liquidity_lag` | `composite` | Point in time | Recorded publication date | Suspension; liquidity; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 69 | `I1111_full_implementation` | `roe` | Point in time | Recorded publication date | ST; suspension; liquidity; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 70 | `I1111_full_implementation` | `momentum_60d` | Point in time | Recorded publication date | ST; suspension; liquidity; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 71 | `I1111_full_implementation` | `low_vol_20d` | Point in time | Recorded publication date | ST; suspension; liquidity; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |
| CELL | 72 | `I1111_full_implementation` | `composite` | Point in time | Recorded publication date | ST; suspension; liquidity; lag | Not yet estimated | Not yet estimated | Not yet estimated | Not yet estimated | 0 of 156 | Not run |

## Endpoint and cell completeness

| Measure | Registered requirement | Result | Status consequence |
|---|---|---|---|
| Target monthly rebalances | Exactly 156 | Not yet estimated | Fewer months block the primary claim |
| Registered factor-variant-month cells | Exactly 11,232 | Not yet estimated | Any missing required cell produces `INSUFFICIENT_EVIDENCE` |
| Minimum finite exact pairs per cell-month | At least 1,000 | Not yet estimated | A deficient cell-month produces `INSUFFICIENT_EVIDENCE` |
| Signal-eligible endpoint ledger coverage | One unique ledger row per signal-eligible key | Not yet estimated | Missing, duplicate, or extra rows invalidate controlled verification |
| Missing exact forward exit | Zero | Not yet estimated | The affected cell is non-estimable |
| Missing exact lag entry | Zero | Not yet estimated | The affected cell is non-estimable |
| Missing exact lag exit | Zero | Not yet estimated | The affected cell is non-estimable |
| Unresolved endpoint fallback | None permitted | Not yet estimated | Chasing, reopening, carrying forward, or default recovery invalidates the run |
| Global evidence gate | Every registered data and control gate passes | Not yet estimated | Every claim flag remains false when the gate fails |

## Reporting completion rule

The post-results manuscript must reproduce the primary row, every secondary row, both isolation checks, every exposure diagnostic, all 72 cell rows, and the endpoint-completeness table. Negative, null, positive, mixed, sign-reversing, and infeasible outcomes remain visible. Exploratory analyses, if later authorized, appear in a separately labeled appendix and cannot replace a registered row.
