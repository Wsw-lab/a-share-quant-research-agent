---
title: "Report Dates, Publication Dates, and the A-Share ROE Signal"
subtitle: "A Pre-Specified Historical Confirmation"
document_status: "Anonymous pre-results protocol draft — not registered; confirmatory outcomes not accessed"
date: "1 September 2026"
keywords: "A-shares; return on equity; accounting-data availability; publication timing; backtest specification; pre-registration"
jel: "G12; G14; C12; M41"
---

# Abstract

Backtests of accounting characteristics can assign a financial-statement value to dates before the report was recorded as public. We ask how much this convention contributes to the apparent relation between return on equity (ROE) and subsequent A-share returns. In an already observed 2025–2026 pilot, replacing fiscal-period eligibility with recorded publication-date eligibility reduced mean monthly ROE rank information coefficient from 0.0461 to 0.0105. Because that result preceded the present design, it motivates rather than tests the prediction. We propose a pre-specified historical confirmation over 156 monthly rebalances from 2010 through 2022. The sole primary estimand is the paired monthly change in ROE IC within a historical listing universe. An ordered common-support identity separates report-support restriction, same-security record replacement, and publication-support extension. Outcome-free diagnostics report how often the optimistic clock admits a record too early, how often it selects a different fiscal period, and the calendar-day reporting-delay distribution. Exact endpoint rules make a cell non-estimable rather than silently chasing a later quote, carrying forward a last price, or assigning a default recovery. A complete 16-variant implementation lattice, combined with two report-end comparators, yields 18 variants; four factors therefore produce 72 fully disclosed factor–variant cells. The study has not been executed and remains conditional on data, custody, semantics, rights, external registration, and authorization gates. Single-version accounting data identify only a recorded-publication-date specification effect, not historical revisions or the complete information available to investors, and the design makes no portfolio-performance claim.

**Keywords:** A-shares; return on equity; accounting-data availability; publication timing; backtest specification; pre-registration
**JEL classifications:** G12; G14; C12; M41

> **Manuscript status.** This is an anonymous pre-results protocol draft. The January 2025–June 2026 pilot evaluation has been observed; its complete aggregate results and known limitations are disclosed in Appendix A. The proposed 2010–2022 historical confirmation is blocked for data feasibility, has not been externally registered or authorized, and has not been executed.

# 1. Introduction

An accounting characteristic cannot be used in a historical investment rule merely because the fiscal period to which it refers has ended. The report must first become public under a stated information rule. When a backtest instead makes a later-recorded value available at fiscal period end, it gives the simulated researcher an informational advantage that the declared publication clock does not permit. The resulting return association may describe a database convention rather than evidence available under that convention in real time.

This paper asks a narrow question: **how much of the measured A-share ROE–return relation remains when the backtest waits until the report's recorded publication date?** The question matters in China because reporting schedules, trading suspensions, Special Treatment designations, unusually small listed firms, and historically changing listing populations make imported construction conventions consequential. It also matters beyond China. Public code can reproduce a calculation while leaving unresolved whether the securities, accounting records, and return endpoints in that calculation belonged to the information set claimed by the researcher.

The sole primary hypothesis is fixed near the beginning because it defines the paper. Within the same historical listing universe, the pilot-informed prediction is that moving ROE eligibility from fiscal report-period end to the recorded report publication date produces a negative mean monthly change in the rank association between ROE and the subsequent 20-session return. If `d_t` denotes publication-date ROE IC minus report-period ROE IC in month `t`, then the directional prediction is `E[d_t] < 0`; the reported inferential test remains the two-sided null `H0: E[d_t] = 0`. A positive estimate is therefore visible as a rejection of the predicted direction rather than relabeled after the fact. In this draft, “pre-specified” means declared in the proposed design; it does not mean externally registered.

The prediction is motivated by an observed pilot and is not theory-only. Across 18 monthly cross-sections from January 2025 through June 2026, changing accounting eligibility while holding historical membership fixed reduced mean ROE rank IC from 0.0461 to 0.0105. The fixed composite fell from 0.0332 to 0.0038, while the price-only momentum and low-volatility calculations were unchanged. The pilot had been viewed before this manuscript, was not externally preregistered, and cannot be treated as independent confirmation. Its role is to state the empirical precondition honestly and motivate a historically earlier panel whose outcome-blind status will depend on custody and prior-exposure gates, not on its calendar date.

The design is built to distinguish three reasons the measured relation can change. First, the two information clocks may leave different usable cross-sections. Second, even among the same securities, the publication-date rule can replace the report selected by the report-period rule. Third, implementation conventions can move the measured association after the information clock is corrected. We therefore add an ordered common-support identity to the primary contrast. It exactly separates report-support restriction, common-support record replacement, and publication-support extension. Starting from the recorded-publication baseline, a complete factorial then crosses four A-share implementation components: exclusion of ST securities, exclusion of suspended securities, a 20-session CNY 5 million amount floor, and a one-official-session return lag.

The paper makes three contributions. First, it measures how much the apparent A-share ROE–return association changes when an accounting record becomes eligible at its recorded publication date rather than at fiscal period end. Second, it separates the total timing effect into same-security record replacement and changes in cross-sectional support, so that an information-clock effect is not conflated with securities entering or leaving the calculation. Third, it evaluates the recorded-publication result across the complete factorial of four pre-specified A-share trading-state, liquidity, and return-clock conventions. External pre-registration, exhaustive disclosure, and executable verification are intended to discipline these claims; they are safeguards rather than separate economic contributions.

The claim is deliberately bounded. A recorded publication date in a single-version export does not prove which numerical value investors saw at first release, reconstruct later revisions, or capture every earlier public signal such as a forecast or earnings express release. The study therefore estimates a recorded-publication-date specification effect, not a complete information-arrival mechanism. Rank IC and a top-quintile-minus-universe diagnostic are measurements rather than investable portfolios. The design does not support claims about transaction-cost-adjusted performance, revision history, or generalization beyond the stated panel.

# 2. Why publication timing matters in A-shares

## 2.1 Familiar signals in a market-specific setting

The study deliberately uses familiar characteristics so that the object being measured is the information rule rather than a newly discovered signal. Profitability, momentum, and low-volatility effects have long histories in empirical asset pricing (Jegadeesh and Titman, 1993; Ang et al., 2006; Novy-Marx, 2013). Their presence here does not imply that the repository's short-window definitions reproduce canonical academic portfolios. ROE is a vendor-supplied profitability measure, momentum is a 60-session price change, low volatility is the negative standard deviation of 20 daily adjusted returns, and the composite fixes their cross-sectional rank weights at 0.50, 0.30, and 0.20.

China-specific evidence shows why apparently routine construction choices cannot be treated as neutral. Liu, Stambaugh, and Yuan (2019) build factors around institutional features of the Chinese market, including the behavior of very small firms, short listing histories, and sparse trading, and they align annual accounting inputs to public announcement dates. Li et al. (2024) replicate 469 A-share anomaly variables using announcement dates or pre-set lags for accounting availability and show that breakpoint, weighting, and small-stock conventions materially affect replication. Publication-date alignment is therefore not novel by itself. Gharghori and Nguyen (2025, 2026) also demonstrate that a China factor comparison can be pre-specified and reported through distinct pre-results and post-results studies. The incremental object here is the paired size of the recorded-publication effect and its separation from sample support and implementation choices.

Historical membership is a separate concern. Conditioning a study on terminal survivors can change performance inferences (Brown et al., 1992), while omitted delisting returns can distort measured returns (Shumway, 1997). The sign of the membership effect in an A-share cross-section is not mechanically negative; it depends on the firms that disappear and the relation among their characteristics and returns. Historical membership is consequently measured as a secondary specification effect, not given a directional hypothesis.

## 2.2 The recorded-publication channel

Fiscal period end describes the economic period to which a report relates. It is not the date on which the associated database record becomes eligible under a publication rule. Suppose the report-period clock selects a recent high-ROE record for a monthly signal, although that record's stored publication date is on or after the signal date. A publication-date clock must instead select an older eligible record or exclude the security if no qualifying record remains. The ranking, the usable sample, or both can change.

The primary contrast measures the combined consequence of those changes. Its expected negative sign reflects the observed pilot: the optimistic clock produced the larger ROE IC. That prediction does not imply that every premature record is favorable or that publication itself causes a return. A zero interval would fail to establish a nonzero mean displacement; a positive effect would reject the predicted direction. The common-support identity in Section 5 asks whether any total effect operates through record replacement among the same securities or through a changed usable cross-section.

Three outcome-free exposure diagnostics make the clock discrepancy observable without creating additional hypothesis tests. For every rebalance, the study reports the **premature share**: the fraction of report-period-eligible ROE observations whose selected record has `publishDate >= signal date`. It reports the **selected-report-changed share** among common-signal-support securities: the fraction for which the two clocks select different report-period identities. It also reports the count, mean, median, interquartile range, and maximum of the calendar days from each report-side selected record's fiscal period end to its recorded publication date. These are descriptive measures of treatment intensity, use no forward return, and do not enter the Benjamini–Hochberg family.

The design does not add an announcement-event study. A single-version export cannot show the ROE value visible at first release, and a date-only field does not resolve publication time relative to the market close. Earlier forecasts, preliminary results, or other disclosures may also convey profitability information before the stored report date. Pre-announcement, announcement-window, and post-announcement returns would therefore be easy to overinterpret as investor response. Such an analysis requires separately validated first-release values and announcement-time semantics and would need a new, externally frozen estimand family.

## 2.3 Implementation and specification search

ST designations, suspensions, low turnover amount, and contemporaneous signal-to-return clocks can determine whether a measured association survives a more realistic decision set. Implementation costs likewise reshape anomaly economics (Novy-Marx and Velikov, 2016). The present study stops short of a costed portfolio. It asks whether four explicit controls change monthly cross-sectional IC after the accounting clock has been corrected.

The complete factorial is used because a cumulative ablation makes attribution depend on the order in which components are added. Exact monthly Shapley values distribute the difference between the empty and full implementation specifications across the four components and their interactions without choosing a preferred entry order. This allocation is conditional on the recorded-publication baseline and is not a causal decomposition.

Specification search is not cured by a conventional t-statistic or by publishing code after the choices are made (Lo and MacKinlay, 1990; White, 2000; Harvey, Liu, and Zhu, 2016). Standardized replication can sharply reduce apparent anomaly evidence (Hou, Xue, and Zhang, 2020). The design therefore fixes one primary, a complete secondary family, two deterministic isolation checks, and every descriptive factor–variant cell before historical outcomes are released. This discipline does not erase the observed pilot or other earlier repository experimentation; it bounds what the proposed confirmation may claim.

# 3. Disclosed pilot evidence

## 3.1 Evidence role and sample

The observed pilot uses a local research export described as licensed in the legacy repository record. The file is not redistributed. The already-public legacy receipt reports its file interval, row and symbol metadata, labels 2023–2024 as a training interval, and evaluates 18 first-session monthly cross-sections from January 2025 through June 2026 with a 20-session forward horizon. Four factors and four cumulative variants yield 16 factor–variant cells. Appendix A reports all 16; no favorable cell is selected as the pilot conclusion. These provider-derived hashes, metadata, and aggregates are reproduced only as facts already exposed by that legacy receipt; the new Stage-2 rights packet has not established their publication or controlled-review basis. Continued hosting or remediation requires a separate licensor or authorized institutional-administrator review.

The pilot's plan was locked on 31 August 2026, after both the evaluation interval and the market-file endpoint, and no external timestamp preceded outcome access. It is therefore an observed empirical precondition rather than prospectively confirmatory evidence. Its performance, generalization, and trading-decision flags are false.

## 3.2 The timing transition

**Table 1. Pilot information-clock transition**

| Factor | Historical-universe report-end IC | Recorded-publication IC | Difference | Role |
|---|---:|---:|---:|---|
| ROE | 0.0461 | 0.0105 | -0.0356 | Pilot-informed primary direction |
| Momentum 60d | -0.0495 | -0.0495 | 0.0000 | Price-only isolation |
| Low volatility 20d | 0.0550 | 0.0550 | 0.0000 | Price-only isolation |
| Composite | 0.0332 | 0.0038 | -0.0294 | ROE-dependent secondary |

*Notes.* Each value averages 18 monthly cross-sections. “Difference” is recorded-publication IC minus historical-universe report-end IC. These observed statistics were not externally preregistered and receive no new hypothesis test in this paper. The complete pilot matrix, including Newey–West statistics, top-minus-universe diagnostics, and mean cross-sectional counts, appears in Appendix A.

The ROE shift is 77.2% of its positive report-end comparator, and the composite shift is 88.5% of its positive comparator, expressed only as descriptive ratios. Momentum and low-volatility ICs are identical across the timing transition because neither signal uses publication-dated accounting data. Under the pilot's bundled implementation variant, ROE and composite means become negative, but no component-specific interpretation is possible from a cumulative transition.

The complete matrix also shows why the best-looking output is not an adequate conclusion. Momentum has negative mean rank IC but positive top-quintile-minus-universe spread in every pilot variant; low volatility shows the opposite sign combination. A full-rank association and an extreme-bin contrast weight the cross-section differently. Both remain descriptive outputs, and the factor label cannot be changed according to which statistic is more favorable.

## 3.3 Separation from the historical confirmation

The confirmatory design is continuous with the pilot's question but is not an exact replay. The pilot permits a record on its publication day, whereas the proposed date-only rule requires `publishDate < signal date`. The pilot derives rebalances from observed quote dates; the confirmation requires a bound common SSE/SZSE official calendar. The pilot reads a normalized ROE field without an 18-month staleness rule; the confirmation requires the provider's raw `roeDiluted` definition, decimal normalization, and a fixed staleness limit. Its bundled implementation label is not evidence that suspension semantics were independently attested.

These are restrictions on a separate historical design, not retroactive repairs to pilot results. The 2010–2022 panel is historically earlier but may be described as outcome-blind only if the custody and final prior-exposure gates pass. The pilot supplies prior evidence and design input; none of its factor–variant or rebalance estimates enters the historical primary or secondary estimates. A genuinely prospective extension of at least 12 months would begin only after external registration or journal in-principle acceptance and would be reported separately.

[[FIGURE:ACCOUNTING_TIMELINE]]

*Figure 1. Accounting-record availability under the two clocks.* The report-period rule can select a record between fiscal period end and its recorded publication date. The conservative date-only rule first permits that record on an official session strictly after the stored publication date. The figure describes database eligibility, not the complete information set of investors or the numerical vintage visible at first release.

# 4. Data, outcomes, and feasibility

## 4.1 Population, periods, and required inputs

The target population is ordinary A-shares listed on the Shanghai or Shenzhen exchanges. B-shares, funds, bonds, preferred shares, non-equity instruments, and Beijing Stock Exchange securities are outside the boundary. Historical point-in-time eligibility begins on or after a security's listing date and ends after its delisting date. The deliberately optimistic A0 comparator is fixed at the required quote/outcome cutoff, 31 January 2023: at each historical signal session, the security must already be listed and its `delistDate` must be null or strictly after that fixed cutoff. Extraction-current status and acquisition date do not redefine terminal survival. Active and delisted status/date combinations must be internally consistent.

Quotes, stock master, and fundamentals must share the human-reviewed identifier contract `provider_stable_exchange_qualified_security_identifier_with_reviewed_code_change_mapping_v1`. The canonical `NNNNNN.SH`/`NNNNNN.SZ` syntax is necessary but does not establish stable identity. A provider identifier definition and a documented mapping for every historical code change or reassignment are separately hash-bound before the input files; this is an identity-linkage requirement, not a vintage-data claim. Duplicate date–symbol quote keys and duplicate effective security-master records fail closed.

The historical rebalance interval is fixed at 1 January 2010 through 31 December 2022. Rolling signals may use a warm-up beginning 1 January 2009, but no warm-up observation contributes to an outcome. The rebalance date is the first common official SSE/SZSE session of each month, producing 156 target months. The final December 2022 horizon extends 20 official sessions into January 2023. That endpoint overlaps raw dates in the later pilot market file but is not a pilot factor-cell or rebalance estimate.

Four bound inputs are required: a daily quote panel, a historically effective security master, publication-dated fundamentals, and a common official exchange calendar. Every quote row must retain finite positive `close_raw` and `adjustment_factor`, use exact `price_adjustment_method=close_equals_close_raw_times_adjustment_factor` and `price_adjustment_convention=provider_cumulative_backward_adjusted_hfq_no_rebasing`, and mechanically satisfy `close=close_raw×adjustment_factor` within fixed `1e-12` relative and absolute tolerances. The cumulative factor is used as delivered without rebasing; per-symbol positive constant rescaling leaves return ratios unchanged, and cross-sectional price levels are not estimands. A human review separately binds evidence hashes for the provider raw-close/valuation definition, adjustment-factor convention, and normalization or adapter record. Every quote row must also carry `close_observation_type`: exactly `traded_close` when `is_suspended=false` and exactly `suspension_valuation` when `is_suspended=true`. Provider evidence must establish that a suspension valuation was recorded or published for that exact official session; the research code may not manufacture one by forward-filling a last price. The panel must also document turnover-amount units and contemporaneous ST and suspension status. The master must include delisted securities and historically valid list, delist, status, and security-type fields; board metadata is strongly preferred but is not a current executable gate. Fundamentals must preserve the provider's raw `roeDiluted` definition, units, report-period end, and recorded publication date. The calendar must document source, timezone, exact common sessions, schema version, and file hash.

ROE is the latest eligible cumulative interim or annual `roeDiluted` observation, normalized to decimal units without analyst annualization and rejected when more than 18 months stale. Duplicate security–report-period rows fail closed unless a separately validated vintage schema identifies their versions. With a date-only field, a record becomes eligible only when `publishDate < signal date`; same-day use is prohibited. This rule identifies when a single-version record is admitted under the declared clock. It does not identify the value visible at first release or reconstruct corrections.

## 4.2 Signals and exact outcomes

The four fixed signals are ROE; provider close-observation momentum over 60 official sessions; the negative standard deviation of daily valuation returns over 20 official sessions; and a complete-case composite equal to 0.50 times the ROE percentile rank, plus 0.30 times momentum rank, plus 0.20 times low-volatility rank. The weights are not re-estimated. Missing signals are not imputed. Industry neutralization, size residualization, alternative lookbacks, reconstructed ROE, and raw-ratio regressions are outside the claim set.

The no-lag outcome is the provider close observation at official session `t+20` divided by that at signal session `t`, minus one. The lagged outcome is the provider close observation at `t+21` divided by that at `t+1`, minus one. Each cross-section candidate belongs to the lifecycle-eligible strict A-share master and has an exact signal-session close observation. Before design freeze, every member of `active master ∩ signal-session quote identifiers` must have exact rows at `t`, `t+1`, `t+20`, and `t+21`, so the exact-endpoint count equals the candidate count in every month; the separate minimum of 1,000 complete quote contracts remains. Both traded closes and supplier-recorded suspension valuations must occur among the signal-session candidates. The code may not chase a security's next observed quote, use a reopening quote, forward-fill its last price, substitute a default return or recovery, or silently omit the security. A missing forward exit, lagged entry, or lagged exit receives one of three mutually exclusive reason codes and makes that factor–variant–month cell non-estimable. A non-finite close observation or valuation return is an input-integrity failure, not a fourth endpoint reason.

This exact-only rule applies equally to securities that delist, change identifiers, or have an unexplained quote gap within the horizon. A suspended session is resolved only by an attested supplier-recorded or published same-session valuation; that valuation is not an executable fill. An independently documented terminal return can qualify only if the bound quote product represents it as the exact required endpoint under the declared total-return semantics; an analyst-created delisting payoff does not. Because the design requires every one of the 72 factor–variant cells in every one of the 156 months, any unresolved endpoint that makes a required cell non-estimable leads to the global status `INSUFFICIENT_EVIDENCE`. A count threshold cannot rescue a cell after an otherwise eligible security has been silently lost.

For continuity with the pilot, each estimable cell also reports the equal-weight top signal quintile valuation return minus the equal-weight universe mean. The frozen grouping rule uses average percentile ranks, defines the bottom quintile as `rank <= 0.2`, and defines the top quintile as `rank > 0.8`. Equal signal values receive one average rank and remain together; group sizes may therefore differ from 20% when a tie spans a boundary, while 1,000 distinct values produce exactly 200 securities in each tail. The diagnostic is neither self-financing nor cost adjusted and cannot support an implementability claim. Every return and IC in this core is a valuation diagnostic, not an executable trade return. Candidate, signal-missing, signal-eligible, exact-resolved, and unresolved counts are reported for every monthly cell. The runner constructs one endpoint-resolution record per signal-eligible key and binds its hash and aggregate reason counts in the public receipt. Public-only verification checks the receipt's structure and integrity but cannot inspect the withheld ledger. In a controlled audit, an authorized verifier supplied with the private ledger additionally checks its hash, canonical order, uniqueness, aggregate counts, and per-cell cardinality against the published denominators; without licensed raw inputs it still cannot independently authenticate the underlying security identities.

## 4.3 Outcome-blind feasibility gates

Feasibility has three distinct gates. First, the externally timestamped bounded source probe requests only 12 fixed securities on two fixed dates and can establish only source-retrieval feasibility; its passing receipt is hash-bound into the later design. Second, a full outcome-blind coverage and rights review may inspect dates, identifiers, fields, semantics, rights, and aggregate counts—but not factor ICs, portfolio returns, candidate rankings, or historical outcome summaries—to establish the 2009 warm-up, all 156 target months, January 2023 quote coverage, valid and status-consistent historical list/delist records, publication-date coverage, non-degenerate trading-status fields, official calendar, field semantics, lawful aggregate disclosure, reviewer access, and custody. Every quote row must pass the exact `close_observation_type`/suspension mapping, both observation types must occur among signal-session candidates, and human evidence must establish supplier-recorded same-session valuation provenance. For each target rebalance, every active-master signal-session candidate must have all `t/t+1/t+20/t+21` endpoints, and at least 1,000 identifiers must additionally satisfy the full joint history-and-endpoint contract across `t-60..t`, `t-20..t`, `t-19..t`, and the four endpoints. File endpoints, aggregate monthly counts, and a dense rebalance date do not establish those conditions. Third, only after registration and execution authorization does the runner form factor-variant signal-eligible denominators and enforce exact endpoint resolution and the private reason ledger. The pre-lock presence gate does not replace that final cell-level condition, and a bounded two-date probe cannot establish either one.

A legacy feasibility audit inspected schemas and aggregate coverage in locally retained material. It did not establish that any delivery passes the fixed Stage-2 interval, field, semantic, endpoint, or rights gates, and it did not assemble or view a complete 2010–2022 factor-return or IC series. Calendar labels do not establish blindness: final eligibility remains conditional on the signed exposure inventory, independent custody, external timestamp, and authorized release.

> **Current feasibility status: BLOCKED_FOR_STAGE2.** No reviewed delivery has passed the complete 2009 warm-up, 2010–2022 analysis, January 2023 endpoint, lifecycle, all-candidate exact-endpoint, official-calendar, raw-`roeDiluted`, recorded-publication-date, close-observation mapping, supplier-recorded suspension-valuation, signal-session non-degeneracy, publication-rights, and controlled-review gates. The final exposure attestation and external registration chain are also incomplete. The historical outcome analysis remains unrun.

# 5. Empirical design and estimands

## 5.1 Primary recorded-publication contrast

Let `IC_f,v,t` be the cross-sectional Spearman rank correlation between factor `f` under variant `v` and its pre-specified exact 20-session return in month `t`. The information-set chain begins with three variants that have no implementation component:

1. `A0_final_report_end`: fixed 31 January 2023 terminal-survivor universe (`delistDate` null or strictly after the cutoff, with listing required by the historical signal session); ROE available at report-period end;
2. `A1_pit_report_end`: historical listing universe; ROE available at report-period end; and
3. `I0000_pit_publication`: historical listing universe; ROE available strictly after the recorded publication date.

The sole primary monthly contrast is

`d_t = IC_ROE,I0000,t − IC_ROE,A1,t`,

and the primary estimand is its time-series mean over the fixed panel. The directional prediction is negative; the reported test is the two-sided null of a zero mean with a two-sided confidence interval. “Timing inflation” or “attenuation” may be used only when the report-period comparator IC is positive and the signed difference is negative. Otherwise the neutral term is “recorded-publication displacement.”

The paired difference `A1 − A0` separately measures the historical-membership specification effect within available fields. The information-set transitions are intentionally ordered. The study does not claim that reversing them would produce the same attribution.

## 5.2 Ordered common-support identity

For the ROE primary in month `t`, let `U_R,t` be the securities with a finite report-period ROE signal and exact outcome under `A1`, let `U_P,t` be the corresponding set under `I0000`, and let `C_t = U_R,t ∩ U_P,t`. Define `IC_t(s,U)` as the ROE rank IC computed from signal vector `s` and the same exact outcome over security set `U`. Let `s_R` and `s_P` denote the report-period and recorded-publication signal vectors.

The total primary monthly contrast obeys the exact ordered identity

`IC_t(s_P,U_P) − IC_t(s_R,U_R)`

`= [IC_t(s_R,C) − IC_t(s_R,U_R)]`

`+ [IC_t(s_P,C) − IC_t(s_R,C)]`

`+ [IC_t(s_P,U_P) − IC_t(s_P,C)].`

The first term is **report-support restriction**: it holds the report-period signal fixed and restricts its calculation to common support. The second is **common-support record replacement**: it holds securities and outcomes fixed while changing the report selected under the two clocks. The third is **publication-support extension**: it moves from common support to the full recorded-publication support while holding the publication-date signal fixed. “Extension” names the final step in the chosen path; `U_R,t` and `U_P,t` need not be nested, and the term may have either sign.

The identity is algebraically exhaustive for the chosen path but is not unique, causal, or order invariant. All three monthly components are pre-specified secondary estimands and enter the Benjamini–Hochberg family. They are estimable only when the full and common-support ICs are finite and all required endpoints are exact. Their monthly sum must reproduce `d_t` to numerical tolerance; failure is an implementation error, not an economic result. Alongside them, the outcome-free exposure diagnostics in Section 2.2 report why the two supports or selected records differ.

## 5.3 Implementation lattice

Starting at `I0000`, the study crosses four binary components: ST exclusion on the signal session, suspension exclusion on the signal session, a 20-session mean turnover-amount floor of CNY 5 million, and a one-official-session outcome lag. Every subset is pre-specified. The 16 implementation variants share historical listing membership and the recorded-publication accounting rule. Together with `A0` and `A1`, the design has 18 variants. Four factors therefore produce 72 factor–variant reporting cells; the implementation lattice itself contains 16 variants and 64 factor–variant cells.

The 18-variant, 72-cell design remains the target. If a supplier cannot prove that suspended-session values were recorded or published for the exact official session, the study remains blocked; a carried-forward research price may not be relabeled. The only possible fallback is prospective and outcome blind: before external registration, remove every suspension-component factorial variant, leaving 10 variants and 40 factor–variant cells, then re-enumerate the estimands and multiplicity family and re-freeze and externally timestamp every design artifact. No 40-cell switch is permitted after registration or outcome access.

[[FIGURE:DESIGN_MAP]]

*Figure 2. Pre-specified information and implementation design.* The information-set chain is ordered. The implementation lattice evaluates all 16 subsets, so its Shapley allocation does not depend on a preferred sequence of component entry. `I0000` is the empty implementation variant and appears once among the 18 total variants; 18 variants multiplied by four factors produce 72 reporting cells.

## 5.4 Exact monthly Shapley allocation

Following Shapley (1953), let `v_t(S)` be the monthly IC for a fixed factor under implementation subset `S`, with `K = 4` components. For component `i`, the monthly allocation is

`phi_i,t = sum_{S not containing i} [ |S|! (K−|S|−1)! / K! ] [ v_t(S union {i}) − v_t(S) ].`

All 16 subset values must be finite in a month before that month enters a component summary. Shapley values are computed within each complete month, their sum must equal `v_t(all) − v_t(empty)` up to numerical tolerance, and Newey–West inference is then applied to each component's monthly series. No interpolation replaces a missing subset. The allocation distributes interactions among components but is not a formal interaction test.

## 5.5 Estimand and reporting ledger

**Table 2. Pre-specified estimand and reporting ledger**

| Group | Count | Definition | Inference | Authorized role |
|---|---:|---|---|---|
| Primary P1 | 1 | ROE `I0000 − A1` monthly IC | NW HAC lag 3; two-sided 95% CI and p-value | Sole primary conclusion |
| Common-support identity | 3 | Report-support restriction; record replacement; publication-support extension | NW inference; included in BH family | Secondary channel accounting |
| Composite timing | 1 | Composite `I0000 − A1` monthly IC | Included in BH family | ROE-dependent secondary |
| Membership effects | 4 | `A1 − A0` IC, one per factor | Included in BH family | Secondary specification effect |
| Full-implementation effects | 4 | `I1111 − I0000` IC, one per factor | Included in BH family | Secondary bundled effect |
| Component Shapley effects | 16 | Four components multiplied by four factors | Monthly Shapley and NW inference; included in BH family | Conditional secondary attribution |
| Timing-isolation checks | 2 | Momentum and low-volatility `I0000 − A1` | Exact tolerance `1e−12`; no hypothesis test | Nonzero value invalidates the run |
| Exposure diagnostics | 3 sets | Premature share; selected report changed; reporting-delay distribution | Descriptive only | Documents timing treatment intensity without returns |
| Cell completeness outputs | 72 | Four factors multiplied by 18 variants | Mean IC, NW t, top-minus-universe, mean N, endpoint counts | Descriptive only; no cell discovery |

The inferential set contains 29 estimands: one primary and a fixed 28-member secondary family. All 28 secondary p-values receive Benjamini–Hochberg adjustment at nominal false-discovery rate 0.10 (Benjamini and Hochberg, 1995). The two deterministic isolation checks and outcome-free exposure diagnostics are outside that count. A non-estimable secondary remains in the family denominator and is a non-rejection; if endpoint failure makes a required reporting cell non-estimable, the stronger global insufficient-evidence rule controls.

Momentum and low volatility do not depend on accounting publication dates. Their `I0000 − A1` IC contrasts must equal zero to absolute tolerance `1e−12`. A nonzero contrast indicates that the implementation failed to isolate the changed information field and causes the run to fail closed.

# 6. Estimation, inference, and complete reporting

The unit of time-series inference is the monthly cross-section. Paired contrasts use only months for which both required ICs are finite, subject to the stronger rule that every required factor–variant–month cell must be estimable. Comparing two separately estimated t-statistics is prohibited. For the primary and every inferential secondary, the study reports the mean monthly estimate, Newey–West HAC standard error with lag three, two-sided t-statistic, two-sided p-value, and 95% confidence interval (Newey and West, 1987).

The primary receives no multiplicity adjustment because it is the sole primary estimand. The fixed 28-member secondary family uses Benjamini–Hochberg adjusted p-values at nominal FDR 0.10. Its estimands are correlated by construction, so adjusted thresholds do not replace effect sizes, intervals, or the stated design logic. Secondary estimates remain secondary even if they appear stronger than the primary. The three common-support components enter the same family and are not promoted according to which path term looks most favorable.

If fewer than 120 paired months remain for an otherwise estimable contrast, the estimate and interval are shown but no statistical-significance or generalization claim is authorized. This rule does not override the exact endpoint and 72-cell completeness requirements. If any global evidence-eligibility gate fails, every estimand-level `claim_eligible` and rejection flag is forced to false even when an individual contrast has at least 120 paired months. Under a normal-approximation planning sensitivity with 156 months, monthly paired-difference standard deviation of 0.08–0.12, and HAC variance inflation of 1.0–1.5, an absolute IC effect of roughly 0.018–0.033 is expected to be detectable with 80% power. No historical outcome may be used to revise that planning range.

All 72 cell-level mean ICs, Newey–West t-statistics, top-minus-universe diagnostics, mean cross-sectional counts, and endpoint-reason counts will be displayed. They are descriptive completeness outputs, not 72 discovery tests. The paper will not headline the maximum, select the better of IC and quintile spread, or conceal a null or sign-reversing cell. Dedicated outcome-free exposure diagnostics and the exact common-support accounting are mandatory outputs. Formal interactions, alternative factors, next-open portfolios, costs, turnover, capacity, and announcement-event studies are excluded unless completed, tested, and externally frozen before confirmatory outcome access under a new or amended protocol accepted by the registration authority.

# 7. Registration and reproducibility status

Before any historical outcome is released, the data and rights gates, official calendar, prior-specification inventory, owner exposure attestation, flat plan core, code revision, and complete estimand ledger must be frozen and bound to an externally timestamped registration artifact. Independent verification must precede a separate execution authorization. The authorized run must reproduce the bound plan and disclose every execution or deviation. This sequence is intended to support the pre-results and hybrid pathways described by Faff (2023, 2026), subject to editor acceptance. Appendix C records the artifact sequence, trust boundary, reproducibility package, and stopping rules in full.

These controls establish scope, chronology, and artifact identity; they do not prove that a data vendor is correct or that software can execute only once. Licensed rows are not redistributed. Because the registered public receipt discloses the reviewed source identity and exact field-mapping projection, every required dataset must separately grant source-identity publication and field-mapping citation, as well as lawful aggregate disclosure, hash publication, and an authorized independent rerun or controlled reviewer access. The private rights packet records, for each of the four dataset roles, the exact source name and complete canonical-to-provider field map that may be cited, together with a canonical projection hash; the public declaration must reproduce those four authorized projections exactly. A generic compliance statement, omitted or additional field, swapped role, hash mismatch, denial, or unresolved conditional permission is a hard stop. Private contract text, source references, signatures, and verification records are not included in the public projection. Hashes identify retained bytes rather than the complete information available to investors.

# 8. Outcome-contingent interpretation

**Table 3. Pre-specified outcome and stopping interpretation**

| Observed condition | Authorized interpretation | Prohibited interpretation |
|---|---|---|
| Primary mean is negative and CI excludes zero | Recorded-publication alignment reduces ROE IC in the historical panel; “attenuation” only if comparator IC is positive | Proof of revision bias, investor response, or investable alpha |
| Primary CI includes zero | A nonzero mean displacement is not established; precision is assessed from interval width | Proof of no effect, equivalence, or pilot generalization |
| Primary mean is positive and CI excludes zero | Directional expectation is rejected; recorded-publication alignment increases measured ROE IC | Relabeling the sign, changing H1, or suppressing the result |
| Common-support terms differ | The ordered identity locates the total change among support and record-replacement terms | Unique, causal, or order-invariant attribution |
| Other secondary estimates differ | Pre-specified descriptive or adjusted differences are reported | Selecting a new primary or claiming unregistered heterogeneity |
| An isolation, endpoint, data, rights, registration, or completeness gate fails | No primary conclusion; failure status and reason are reported | Chasing prices, dropping cells, shortening the interval, or relaxing thresholds |

Pilot, historical confirmation, prospective extension, and any exploratory appendix remain separate. Exact effects, intervals, adjusted and unadjusted p-values, exposure diagnostics, endpoint counts, and every pre-specified cell remain reportable under negative, null, positive, mixed, or sign-reversing outcomes.

# 9. Limitations

First, the historical panel is not forward in calendar time and is not entitled to an unconditional outcome-blind label. Some 2020–2022 fundamental rows have been inspected for schema and aggregate coverage. Although no complete historical quote outcome panel or historical factor-return or IC series has been assembled or viewed, evidentiary status still depends on a complete exposure inventory, signed attestation, credible custody, external timestamp, and authorized release. Only a post-registration extension is genuinely prospective.

Second, the required historical data and publication rights are not secured. The exact-only endpoint rule and supplier-recorded suspension-valuation evidence are intentionally demanding and may make the proposed design infeasible, particularly around delistings, suspensions, and identifier changes. That outcome is scientifically preferable to silently selecting securities with convenient horizon prices. Before registration only, the explicitly disclosed 40-cell suspension-off redesign may be prospectively frozen; after registration or outcome access, no such relaxation is permitted.

Third, recorded publication timing is not historical vintage reconstruction. A single-version export can prevent its retained value from entering before the stored date, but it cannot establish the exact value visible then, distinguish later corrections, or capture all earlier public signals about profitability. The study therefore cannot identify revision bias, announcement surprise, information leakage, or post-announcement drift.

Fourth, the executable outcome is IC based. It does not model a self-financing long–short portfolio, executable entry prices, price-limit locks, borrow constraints, turnover, commissions, stamp duty, slippage, capacity, or nonfills. A positive IC or quintile diagnostic is not evidence that a strategy can be traded.

Fifth, the four signals are simple and partly vendor defined. The short momentum and volatility windows may not match canonical factors, and the composite weights are heuristic. This is acceptable for measuring how a fixed signal set responds to specification choices, but it limits structural asset-pricing interpretation.

Finally, the secondary family contains correlated contrasts and Shapley allocations. Benjamini–Hochberg adjustment is a fixed reporting discipline, not a substitute for effect sizes or a guarantee under every dependence structure. Public code and fixtures also do not provide fully independent empirical reproduction when licensed rows cannot be redistributed. These statistical and access limits remain visible regardless of the result.

# 10. Conclusion

The paper asks how much of the measured A-share ROE–return relation remains when a backtest waits for the report's recorded publication date. Its answer will come from one paired primary contrast, not from selecting the strongest variant. An ordered common-support identity will show whether any total displacement reflects the usable cross-section or replacement of the accounting record among the same securities. The complete implementation lattice then asks whether the recorded-publication result survives A-share trading-state, liquidity, and return-clock conventions.

Negative, null, positive, mixed, and infeasible outcomes are all informative under the frozen design. A negative primary would quantify recorded-publication attenuation when the comparator is positive. An interval containing zero would fail to establish a nonzero mean effect, with precision determined by its width. A positive estimate would reject the predicted direction. An unresolved exact endpoint or failed data gate would show that the proposed question cannot be answered with the bound inputs. None of these outcomes establishes revision history, investor reaction, or an investable portfolio.

At the date of this manuscript, the historical confirmation remains blocked for data feasibility and has not been externally registered, authorized, or executed. A finished-looking document does not change that evidentiary boundary.

# Appendix A. Complete observed pilot matrix

The pilot evaluates four factors across four cumulative variants and reports all 16 factor–variant cells. The matrix is reproduced without re-estimation or selection.

| Variant | Factor | Mean IC | NW t | Top minus universe | Mean N |
|---|---|---:|---:|---:|---:|
| M0 naive | ROE | 0.0435 | 2.45 | 0.562% | 4,533 |
| M0 naive | Momentum 60d | -0.0514 | -1.68 | 0.765% | 4,516 |
| M0 naive | Low volatility 20d | 0.0529 | 1.86 | -1.038% | 4,527 |
| M0 naive | Composite | 0.0302 | 1.38 | 0.502% | 4,516 |
| M1 historical universe | ROE | 0.0461 | 2.63 | 0.593% | 4,554 |
| M1 historical universe | Momentum 60d | -0.0495 | -1.62 | 0.784% | 4,538 |
| M1 historical universe | Low volatility 20d | 0.0550 | 1.94 | -0.993% | 4,549 |
| M1 historical universe | Composite | 0.0332 | 1.53 | 0.539% | 4,538 |
| M2 recorded publication | ROE | 0.0105 | 0.61 | -0.111% | 4,554 |
| M2 recorded publication | Momentum 60d | -0.0495 | -1.62 | 0.784% | 4,538 |
| M2 recorded publication | Low volatility 20d | 0.0550 | 1.94 | -0.993% | 4,549 |
| M2 recorded publication | Composite | 0.0038 | 0.18 | -0.007% | 4,538 |
| M3 bundled implementation | ROE | -0.0108 | -0.47 | -0.393% | 4,339 |
| M3 bundled implementation | Momentum 60d | -0.0446 | -1.86 | 0.864% | 4,328 |
| M3 bundled implementation | Low volatility 20d | 0.0291 | 0.91 | -1.417% | 4,339 |
| M3 bundled implementation | Composite | -0.0194 | -0.76 | -0.340% | 4,328 |

*Notes.* Each row averages 18 monthly cross-sections. “NW t” is a Newey–West statistic produced by the pilot implementation with lag three; the pilot plan did not separately preregister that lag, and no multiplicity adjustment was applied. “Top minus universe” is the equal-weight return of the top signal quintile minus the equal-weight universe mean over the 20-session window. It is not self-financing or cost adjusted. The M3 machine identifier used the word “audited,” but independent suspension and execution semantics were not attested; the neutral label “bundled implementation” is therefore used here.

# Appendix B. Pre-specified variant inventory

The 18 variants below are fixed. `I0000` is both the final information-set state and the empty implementation variant, so it is counted once.

| ID | Historical universe | Accounting availability | Enabled implementation components |
|---|---|---|---|
| A0_final_report_end | Fixed 2023-01-31 terminal survivors | Report-period end | None |
| A1_pit_report_end | Point in time | Report-period end | None |
| I0000_pit_publication | Point in time | Recorded publication date | None |
| I1000_st | Point in time | Recorded publication date | ST exclusion |
| I0100_suspension | Point in time | Recorded publication date | Suspension exclusion |
| I0010_liquidity | Point in time | Recorded publication date | CNY 5m amount floor |
| I0001_lag | Point in time | Recorded publication date | One-session lag |
| I1100_st_suspension | Point in time | Recorded publication date | ST; suspension |
| I1010_st_liquidity | Point in time | Recorded publication date | ST; liquidity |
| I1001_st_lag | Point in time | Recorded publication date | ST; lag |
| I0110_suspension_liquidity | Point in time | Recorded publication date | Suspension; liquidity |
| I0101_suspension_lag | Point in time | Recorded publication date | Suspension; lag |
| I0011_liquidity_lag | Point in time | Recorded publication date | Liquidity; lag |
| I1110_st_suspension_liquidity | Point in time | Recorded publication date | ST; suspension; liquidity |
| I1101_st_suspension_lag | Point in time | Recorded publication date | ST; suspension; lag |
| I1011_st_liquidity_lag | Point in time | Recorded publication date | ST; liquidity; lag |
| I0111_suspension_liquidity_lag | Point in time | Recorded publication date | Suspension; liquidity; lag |
| I1111_full_implementation | Point in time | Recorded publication date | ST; suspension; liquidity; lag |

# Appendix C. Registration, verification, and stopping rules

## C.1 Pre-lock gates

The bounded source-probe specification must receive an external timestamp before it is run, and the later plan must bind a passing canonical probe receipt. That probe checks only its fixed two-date, 12-security retrieval scope. A separate full outcome-blind coverage and semantics review—without factor values, forward-return summaries, rankings, or ICs—must establish the 2009 warm-up, 156 target rebalances, and January 2023 quote coverage; at least 15 distinct quoted dates that belong to the official calendar in each target month; the fixed 31 January 2023 terminal-survivor comparator; provider-stable identifier semantics shared by quotes, master, and fundamentals; a documented code-change/reassignment map; exact `close_observation_type`/suspension mapping; both observation types among signal-session candidates; and supplier-recorded same-session suspension-valuation provenance. In every month, every active-master signal-session candidate must have `t/t+1/t+20/t+21` rows, so its exact-endpoint and candidate counts are equal. At least 1,000 strict SH/SZ A-share identifiers per rebalance must additionally satisfy the full joint contract across every session from `t-60` through `t`, every session from `t-20` through `t`, every session from `t-19` through `t`, and all four endpoints. These are per-symbol identifier/date-presence contracts: aggregate monthly symbol counts, a dense first session, and file-level minimum or maximum dates are insufficient. The review must also establish at least 95% valid recorded publication dates among otherwise usable fundamental records; historical listing and delisting coverage; corporate-action, amount, ST, suspension, and decision-cutoff semantics; a bound official common-session calendar; lawful research, aggregate-disclosure, calendar-publication, endpoint-ledger-retention, and reviewer-access rights; a passing offline test suite; and a signed prior-exposure attestation with a contemporaneous inventory of earlier specifications and known outcome access.

Failure at either pre-lock layer stops the proposed design. The sample may not be shortened, shifted, or made less demanding after outcomes are viewed. A materially different feasible study requires a new timestamped protocol and cannot inherit the primary status of this one. After authorization, the runner fixes each signal-eligible denominator before outcome lookup and produces the private endpoint ledger. All 72 factor–variant cells must then be estimable in all 156 months, with at least 1,000 finite exact signal–outcome pairs per cell. An unresolved exact endpoint makes the affected cell non-estimable; any missing required cell yields `INSUFFICIENT_EVIDENCE`.

## C.2 Artifact sequence and trust boundary

The evidence sequence is: outcome-blind coverage and rights review; frozen flat plan core; design manifest binding the plan, code revision, data declarations, four raw-input identities, and gate evidence; external timestamp of the manifest bytes or SHA-256 digest; registration receipt; independent verification; separate execution authorization; and a final execution envelope that points backward to the frozen artifacts without altering the registered plan core. Only then may the custodian release the historical outcome panel.

The current runner accepts only an explicit human-verified registry record; it does not implement cryptographic signature or registry-inclusion-proof validation, so a cryptographic label alone cannot pass. A named authorized human must retain, verify, and hash the provider page, email, or journal record. Hashes establish identity and integrity of retained bytes but do not authenticate an unsigned provider timestamp by themselves. A future cryptographic path requires a separately implemented, tested, and frozen protocol. The chain records scope and chronology; it cannot prove that software executes only once. Every authorized rerun or deviation must therefore be disclosed. An outcome-aware deviation cannot replace the primary analysis and may appear only in a labeled exploratory appendix.

After exclusive authorization consumption, the runner captures each of the four raw inputs exactly once. Coverage recomputation, panel loading, and input evidence use those same captured bytes, so a later path replacement cannot substitute a different panel. A mismatch consumes the authorization and produces no result receipt. For a finite contract, expiry is rechecked at consumption, before outcome preparation, at every monthly execution boundary, and before receipt publication; an expired right also stops without a receipt.

## C.3 Reproducibility package and stopping conditions

The intended package includes the timestamped plan and manifest, tagged code, public schemas and deterministic fixtures, tests, fixed logical file labels and permitted hashes, only the aggregate row/date counts exposed in explicit authorized receipt fields, the authorized source identity and field-mapping projection, calendar identity, the prior-specification inventory, exposure attestation, complete aggregate results, exposure and endpoint diagnostics, and a canonical receipt. Raw/control byte sizes, private operator basenames, local paths, and proprietary rows are not public artifacts. An independent authorized rerun or controlled reviewer access is required. Verification checks artifact hashes, factor–variant–month identities, result counts, estimand identities, exact-support counts, and common-support identities; it does not prove vendor correctness. Real-data execution is bound to Python 3.12.12, NumPy 2.0.2, and pandas 2.3.3 and requires the entire repository, including untracked files, to be clean at the checked-out registered commit.

The study stops without a primary conclusion if a data, rights, custody, registration, authorization, all-candidate exact-endpoint, cell-completeness, publication-field, provider-close-observation, supplier suspension-valuation, official-calendar, isolation, common-support-identity, or reproduction gate fails. Negative, null, positive, mixed, and sign-reversing economic outcomes are not stop conditions.

# Declarations

## Pre-registration status

This manuscript has not been externally registered and has not received journal in-principle acceptance. The externally timestamped bounded source probe has not been run; the final manifest, receipt, and authorization have not been issued; and the historical analysis has not been executed. The observed pilot is disclosed in Section 3 and Appendix A.

## Data and code availability

The legacy repository record describes the pilot's local export as licensed, and its raw rows are not redistributed. The new Stage-2 rights packet has not re-attested the publication or controlled-review basis for the already-public pilot hashes and aggregates; continued hosting or remediation therefore requires separate licensor or authorized institutional-administrator review. The proposed historical panel is not available under a completed rights and semantics attestation. Original public schemas, deterministic fixtures, plan templates, and aggregate evidence are shared under the MIT License only where repository ownership and separate data rights permit; proprietary data and third-party materials remain subject to their agreements. An author-anonymized verification package must be used for blinded editorial review; the required source-identity disclosure remains intact.

## Authorship, funding, and competing interests

This is an anonymous drafting version. Author names, affiliations, ORCID identifiers, CRediT contributions, funding declarations, and competing-interest statements are deferred to the private author identity package and must be completed before submission.

## Declaration of generative AI and AI-assisted technologies in manuscript preparation

**Draft declaration — human confirmation required before submission.** OpenAI Codex supported literature organization, consistency checks, code and evidence inspection, drafting, document generation, and editing. It did not generate or infer historical confirmatory outcomes. Before submission, the named authors must verify every source, number, method, interpretation, and disclosure; record any tool and version required by the journal; and accept full responsibility.

# References

Ang, A., Hodrick, R. J., Xing, Y., & Zhang, X. (2006). The cross-section of volatility and expected returns. *Journal of Finance, 61*(1), 259–299. https://doi.org/10.1111/j.1540-6261.2006.00836.x

Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate: A practical and powerful approach to multiple testing. *Journal of the Royal Statistical Society: Series B (Methodological), 57*(1), 289–300. https://doi.org/10.1111/j.2517-6161.1995.tb02031.x

Brown, S. J., Goetzmann, W., Ibbotson, R. G., & Ross, S. A. (1992). Survivorship bias in performance studies. *Review of Financial Studies, 5*(4), 553–580. https://doi.org/10.1093/rfs/5.4.553

Faff, R. W. (2023). PBFJ editorial: Engaging with responsible science—“Open for business”—launching the PBFJ pre-registration publication initiative. *Pacific-Basin Finance Journal, 79*, 101837. https://doi.org/10.1016/j.pacfin.2022.101837

Faff, R. W. (2026). PBFJ editorial: Responsible and open science in action—an update on the PBFJ experiment and beyond. *Pacific-Basin Finance Journal, 96*, 103045. https://doi.org/10.1016/j.pacfin.2025.103045

Gharghori, P., & Nguyen, A. (2025). Which factors in China? A pre-registered report. *Pacific-Basin Finance Journal, 91*, 102562. https://doi.org/10.1016/j.pacfin.2024.102562

Gharghori, P., & Nguyen, A. (2026). Which factors in China? A pre-registered study. *Pacific-Basin Finance Journal, 96*, 103012. https://doi.org/10.1016/j.pacfin.2025.103012

Harvey, C. R., Liu, Y., & Zhu, H. (2016). … and the cross-section of expected returns. *Review of Financial Studies, 29*(1), 5–68. https://doi.org/10.1093/rfs/hhv059

Hou, K., Xue, C., & Zhang, L. (2020). Replicating anomalies. *Review of Financial Studies, 33*(5), 2019–2133. https://doi.org/10.1093/rfs/hhy131

Jegadeesh, N., & Titman, S. (1993). Returns to buying winners and selling losers: Implications for stock market efficiency. *Journal of Finance, 48*(1), 65–91. https://doi.org/10.1111/j.1540-6261.1993.tb04702.x

Li, Z., Liu, L. X., Liu, X., & Wei, K. C. J. (2024). Replicating and digesting anomalies in the Chinese A-share market. *Management Science, 70*(8), 5066–5090. https://doi.org/10.1287/mnsc.2023.4904

Liu, J., Stambaugh, R. F., & Yuan, Y. (2019). Size and value in China. *Journal of Financial Economics, 134*(1), 48–69. https://doi.org/10.1016/j.jfineco.2019.03.008

Lo, A. W., & MacKinlay, A. C. (1990). Data-snooping biases in tests of financial asset pricing models. *Review of Financial Studies, 3*(3), 431–467. https://doi.org/10.1093/rfs/3.3.431

Newey, W. K., & West, K. D. (1987). A simple, positive semi-definite, heteroskedasticity and autocorrelation consistent covariance matrix. *Econometrica, 55*(3), 703–708. https://doi.org/10.2307/1913610

Novy-Marx, R. (2013). The other side of value: The gross profitability premium. *Journal of Financial Economics, 108*(1), 1–28. https://doi.org/10.1016/j.jfineco.2013.01.003

Novy-Marx, R., & Velikov, M. (2016). A taxonomy of anomalies and their trading costs. *Review of Financial Studies, 29*(1), 104–147. https://doi.org/10.1093/rfs/hhv063

Shapley, L. S. (1953). A value for n-person games. In H. W. Kuhn & A. W. Tucker (Eds.), *Contributions to the Theory of Games II* (pp. 307–317). Princeton University Press.

Shumway, T. (1997). The delisting bias in CRSP data. *Journal of Finance, 52*(1), 327–340. https://doi.org/10.1111/j.1540-6261.1997.tb03818.x

White, H. (2000). A reality check for data snooping. *Econometrica, 68*(5), 1097–1126. https://doi.org/10.1111/1468-0262.00152
