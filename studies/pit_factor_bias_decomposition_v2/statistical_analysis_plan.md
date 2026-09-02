# Report Dates, Publication Dates, and the A-Share ROE Signal

## A Pre-Specified Historical Confirmation

**Protocol status:** Draft for data-feasibility review; not locked and not yet externally registered<br>
**Intended route:** Pacific-Basin Finance Journal hybrid pre-registration pathway<br>
**Authors and affiliations:** To be confirmed before external submission<br>
**Protocol date:** 1 September 2026

## 1. Registration status and non-negotiable boundary

This document is a Stage-2 statistical analysis plan, not a claim of completed preregistration. The research team has already observed the results of the repository's 2025-2026 pilot study. Those results are disclosed in the canonical `pit-factor-replication-v1` receipt and cannot be relabeled as prospective evidence. They serve only as an empirical precondition motivating a larger and cleaner study.

The intended publication route follows the Pacific-Basin Finance Journal's responsible-science initiative. Faff (2023) describes a four-phase pre-registration pathway that evaluates the importance of the question and strength of the method before results are known. Faff (2026) subsequently describes a hybrid pathway for studies that require a transparently verified empirical precondition before downstream hypotheses can be fixed. The present pilot is proposed as that disclosed precondition. No Stage-2 outcome analysis may begin until the plan passes its coverage gates, is frozen to a Git commit, raw-file identities, and an official-calendar identity, receives an external timestamp or journal instruction consistent with the chosen pathway, and a separate execution authorization verifies the full chronology and permits release of the blind sample.

## 2. Research question and contribution

The study asks:

> In a single-version provider snapshot, how much of the measured A-share ROE–return relation remains when the accounting signal is withheld until the first common official signal session strictly after its recorded publication date?

The scientific contribution is a paired measurement of the recorded-publication-date specification effect for A-share ROE, not a search for a new profitable anomaly. Historical membership and the implementation lattice are supporting design features used to establish whether that central estimate depends on sample support or trading-state conventions. The contribution has four layers:

1. **Accounting-clock effect.** Measure the paired ROE IC change when the same historical listing universe moves from report-period eligibility to recorded-publication-date eligibility.
2. **Support and record-replacement decomposition.** Split the total ROE timing contrast by an ordered three-part identity that remains exact for non-nested report-side and publication-side signal supports.
3. **Implementation decomposition.** Replace the pilot's bundled stress variant with the complete factorial of four implementation controls, permitting exact Shapley attribution while preserving interactions in the allocation. Formal interaction tests are a planned, unimplemented module and are excluded from the current IC core.
4. **Research-governance safeguard.** Bind the data declaration, plan, code, proposed-for-registration IC lattice, implemented core outputs, endpoint-reason ledger, and claim gates in a canonical receipt. This supports the economic claim but is not presented as a separate financial contribution. A structured deviation-log module remains planned and unimplemented.

The paper will not claim that any factor is new. Gharghori and Nguyen (2026) already provide the direct pre-registered China factor-model benchmark, and Liu, Stambaugh, and Yuan (2019) already use actual release dates in careful China factor construction. The proposed contribution is a specification-effect design intended for prospective registration, with exact attribution within a complete implementation block. It will not select the best factor or implementation variant, and it will not treat statistical significance as sufficient evidence of an investable strategy.

## 3. Disclosed pilot evidence

The pilot uses a licensed local export covering 3 January 2023 through 24 July 2026 and evaluates a repository-locked test window of 18 monthly cross-sections from January 2025 through June 2026. It reports all 16 combinations of four factors and four cumulative variants. Publication-date alignment produces a negative signed shift in the pilot ROE and composite rank information coefficients; the bundled implementation variant makes both means negative. Momentum and low-volatility ICs disagree in sign with their top-quintile-minus-universe contrasts.

These observations motivate the Stage-2 questions but do not count toward a prospective confirmation. The pilot data, definitions, and result matrix will be included in the eventual manuscript's precondition section and kept separate from the primary Stage-2 estimates.

## 4. Hypotheses and estimands

### 4.1 Sole primary hypothesis

**H1: ROE publication-timing mean contrast.** Within the historical listing universe, the pilot-informed directional prediction is that moving ROE eligibility from fiscal report-period end to the recorded report publication date produces a negative mean monthly change in the cross-sectional association between ROE rank and subsequent return.

The primary estimand is the time-series mean of the paired monthly difference:

`IC(ROE, PIT universe, publication date) - IC(ROE, PIT universe, report-period end)`.

The estimand is the time-series mean of the paired monthly difference, with pilot-informed prediction `E[d_t] < 0`. The reported test is the two-sided null `H0: E[d_t] = 0`, accompanied by a two-sided p-value and 95% confidence interval. As a qualitative sign-based description, the paper may use *timing inflation* or *timing attenuation* only when the report-period comparator IC is positive and the signed difference is negative. This wording is not a percentage-attenuation statistic. If that sign condition does not hold, the result is described neutrally as a timing displacement. H1 is the only primary estimand and its definition and direction may not change after outcome analysis begins.

### 4.2 Secondary estimands

Secondary estimands are:

- the analogous publication-timing difference for the fixed 50/30/20 composite, treated as a downstream result because the timing correction changes only its ROE component;
- the paired effect of replacing final survivors with point-in-time listing membership;
- the paired effect of the full implementation bundle relative to the PIT-publication baseline;
- exact Shapley contributions of ST exclusion, suspension exclusion, the liquidity floor, and the one-session lag;
- the three non-directional ROE components of the ordered common-support identity: report-side support restriction, within-common-support record replacement, and publication-side support extension;
- momentum and low-volatility publication-timing differences as deterministic isolation checks, not inferential hypotheses;
- aggregate signal-missingness and common-support counts plus publication-exposure diagnostics that use no forward returns, reported descriptively outside the inferential family.

Secondary estimates are diagnostic and will be labeled as such even when their statistics appear stronger than the primary results.

The current IC-core contract includes aggregate signal-missingness/common-support counts, the three-part ROE identity, no-return publication-exposure diagnostics, and a machine-readable endpoint-reason code for every signal-eligible record. The complete per-security endpoint ledger remains private but is hash-bound in the result receipt, which publishes aggregate reason counts. Full per-security signal-missingness and non-endpoint exclusion attribution, eligible-universe attribution beyond the registered support counts, percentage attenuation, raw-ratio regressions, robustness analyses, pre-specified two-way interactions, stationary bootstrap intervals, next-open portfolios, transaction costs, turnover, nonfills, and announcement-event or return-timing studies remain excluded until their code, tests, data gates, numerical settings, and multiplicity treatment are finished and externally frozen before Stage-2 outcome access.

## 5. Data-feasibility gates

Only outcome-blind metadata and field coverage may be examined before registration. The coverage report must not contain factor returns or portfolio outcomes.

The plan may advance from `draft_data_feasibility_pending` to `locked` only when all of the following outcome-blind, pre-lock feasibility conditions hold:

1. The fixed January 2010 through December 2022 interval supplies all 156 intended rebalances, with quote warm-up from January 2009 and forward outcomes through January 2023.
2. The quote audit shows at least 15 distinct quote dates that belong to the bound official calendar in every target month; repeated security rows cannot inflate the session count. The monthly scoped universe is constructed from strict SH/SZ A-shares satisfying `listDate <= signal date <= delistDate`, with a missing `delistDate` treated as open-ended. Separately, for every one of the 156 first-session rebalances, at least 1,000 such identifiers must jointly have quote rows at every official session from `t-60` through `t` for the implemented momentum history, at every official session from `t-20` through `t` for 20 daily returns, at every session from `t-19` through `t` for the 20-session amount mean, and at `t`, `t+1`, `t+20`, and `t+21` for the two exact outcome clocks. This pre-lock check uses only identifier/date presence: a dense rebalance date, an aggregate monthly symbol count, or file-level minimum and maximum dates cannot establish per-security warm-up and endpoint availability.
3. At least 95% of otherwise usable fundamental records contain a valid publication date.
4. Every scoped SH/SZ A-share has a valid historical list date; every row identified as delisted has a valid delist date on or after its list date; active/delisted status and delist-date presence are consistent; the master contains delisted securities; and a usable fundamental row cannot have `publishDate < reportPeriodEnd`.
5. Adjusted close return semantics and corporate-action handling are documented and hash-bound. Unadjusted open and nonfill semantics are required only if the planned portfolio module is later implemented and frozen; the IC core makes no execution-price claim.
6. Daily amount, ST status, and suspension status are available under documented units and timing semantics.
7. Data rights permit the intended local analysis, the public release of aggregate results, field definitions, and file hashes, and publication of the exact official-calendar session dates embedded in the receipt.
8. The analysis code passes its complete offline test suite and the plan enumerates every result cell.
9. The owner signs a prior-exposure attestation that no 2010-2022 Stage-2 factor outcomes have been inspected; repository specifications are separately inventoried whether or not their execution history is known.
10. An official common SSE/SZSE session calendar includes every common session from January 2009 through the end of January 2023, passes its schema and semantic checks, and is bound by path, byte size, row count, date range, source provenance, and SHA-256 hash before the plan core is frozen.
11. Exact per-symbol endpoint semantics are reviewed. The current IC adapter supports only an adjusted-close quote on the required official session; suspension valuation, last-price carry-forward, and delisting or terminal-wealth adapters are not implemented. Rights permit a private per-security endpoint-reason ledger to be retained and hash-bound and aggregate endpoint reason counts to be published.

Column names do not satisfy gates 5-7. An authorized reviewer must complete a hash-bound attestation that separately verifies adjusted-return and amount semantics, non-degenerate tradability fields, rights to publish aggregate outputs, and rights to embed the exact official-calendar session dates in a receipt. Without that attestation, the coverage tool reports `BLOCKED` even when every required column is present.

A distinct post-authorization evidence-eligibility stop is evaluated only after the registered runner executes: every one of the 156 months must contain all 72 registered cells, every cell must contain at least 1,000 finite signal-outcome pairs, and every member of the signal-eligible denominator must have all required endpoints resolved. This is not a pre-lock coverage test and does not authorize the analysis team to inspect Stage-2 outcomes before registration. Any unresolved endpoint makes its cell non-estimable and produces `INSUFFICIENT_EVIDENCE`; failure cannot be repaired by silently dropping a security, shortening the interval, dropping a cell, or changing the threshold. When this global stop fires, every estimand-level claim-eligibility and rejection flag must be false even if an individual contrast retains at least 120 paired months.

If a gate fails, the study stops and reports the failed condition. The team will not replace 2010-2022 with a later feasible interval, shorten the sample, lower the publication-date threshold, remove an inconvenient board, or relax the minimum universe after viewing factor outcomes. A materially different feasible design must become a separately timestamped protocol and may not inherit the primary status of this design.

## 6. Population and sample construction

The target population is ordinary China A-shares listed on the Shanghai or Shenzhen exchanges. B-shares, funds, bonds, preferred shares, and non-equity instruments are excluded using the historically valid security type. A security enters the point-in-time universe on or after its listing date and exits after its delisting date. A final-survivor variant is retained only as a deliberately biased comparator.

The intended previously uninspected primary historical interval is 1 January 2010 through 31 December 2022, subject to the prior-exposure attestation and fixed coverage gates. It ends before the observed January 2025-June 2026 pilot evaluation; the pilot's source quote file begins in 2023. The first eligible common SSE/SZSE session of each month in the hash-bound official calendar is the rebalance date. Rolling signals may use observations from the fixed warm-up beginning 1 January 2009, but no pre-2010 observation contributes an outcome. The forward horizon is 20 official exchange sessions.

At least 12 months collected after the external registration or journal in-principle acceptance will be reported as a separate prospective extension. Its estimates will not be pooled silently with either the 2010-2022 historical panel or the disclosed pilot. If the journal-approved protocol specifies a different prospective duration, that approved duration controls and will be recorded before the new outcomes are observed.

## 7. Signal definitions

The primary signals preserve continuity with the disclosed pilot:

- **ROE:** the provider's `roeDiluted` field, normalized to decimal units and mapped to `roe`; use the latest disclosed cumulative interim or annual observation under the variant's availability rule, without analyst annualization, and reject observations more than 18 months stale.
- **Momentum 60d:** adjusted close at the signal date divided by adjusted close 60 sessions earlier, minus one.
- **Low volatility 20d:** the negative standard deviation of daily adjusted returns over the prior 20 sessions.
- **Composite:** 0.50 times the cross-sectional percentile rank of ROE, plus 0.30 times the momentum percentile rank, plus 0.20 times the low-volatility percentile rank.

The composite weights are fixed and will not be re-estimated. Rank IC calculations do not require winsorization. Raw-ratio regressions are planned but unimplemented and are excluded from the current IC core. If a later module is implemented and frozen before outcome access, its registered design must specify 1st/99th percentile cross-sectional winsorization, a rank-only alternative, regression controls, standard errors, and its multiplicity family.

The provider field dictionary, endpoint mapping, units, and formula for `roeDiluted` must be reviewed and hash-bound before lock. Duplicate symbol-report-period rows fail closed unless a separately validated vintage schema distinguishes versions. Literature-standard 12-to-1 momentum, 60-session low volatility, and reconstructed ROE are planned robustness signals, not current outputs. The entire robustness program is unimplemented and excluded from the IC-core claim set. A later reconstructed-ROE module is permitted only if point-in-time net income and equity components have documented formulas and availability timestamps; vendor-supplied and reconstructed ROE will never be combined without a reconciliation table.

## 8. Availability clock

The report-period comparator treats ROE as available on `reportPeriodEnd`. This is intentionally optimistic and exists to measure the bias induced by that convention.

The publication-date variants require `publishDate < signal date` when only a calendar date is known: a same-day release is never used in that session's close signal. If a verified timestamp and timezone prove release before a preregistered market-decision cutoff, a timestamp rule may replace this date-only convention only if it is frozen before outcomes are computed.

Publication-date alignment in a single-version provider export is not equivalent to vintage reconstruction. It withholds the stored snapshot record until its recorded `publishDate` and therefore identifies only a recorded-publication-date specification effect. The current runner has no validated revision-vintage adapter and cannot establish the numerical value investors observed at first release. Revision, restatement, vintage-value, historical-investor-information, announcement-reaction, and return-timing claims are unconditionally prohibited. Historical as-of timestamps, revision identifiers, first-release values, and value-at-vintage records would be necessary for a future adapter but would still require a separately frozen design. Later vendor corrections cannot be presented as information available to historical investors.

The IC clock is diagnostic, not a simulated execution claim. The no-lag outcome is adjusted close at session `t+20` divided by adjusted close at signal session `t`, minus one. The lag outcome is adjusted close at `t+21` divided by adjusted close at `t+1`, minus one. The signal-eligible denominator is fixed before outcome lookup. Under the current adapter, each required start and end must have an exact adjusted-close quote on the corresponding common official session. A missing required symbol endpoint makes the entire factor-variant-month cell non-estimable and the study `INSUFFICIENT_EVIDENCE`; the security may not be dropped, advanced to its next observed quote or reopening date, valued using an unattested last price, or assigned zero or any other default recovery. Calendarized suspension valuation and verified delisting or terminal-wealth adapters are not implemented and cannot be improvised after outcome access. The exact calendar bytes, schema version, source provenance, timezone, date range, and SHA-256 hash are design inputs and must be bound by the frozen plan core and design manifest, but calendar position alone does not prove that a per-security endpoint price exists.

The registered no-return publication-exposure diagnostics report, by month, report-side, publication-side, common, report-only, and publication-only signal-support counts; the share of report-side selected records whose recorded `publishDate` is on or after the signal date; the share of common-support securities whose selected report period changes under publication eligibility; and the calendar-day distribution from report-period end to recorded publication date. They use no forward return, receive no p-value, sit outside the BH family, and cannot support an announcement mechanism or event-study interpretation.

## 9. Variant architecture

The information-set chain contains three variants with no implementation component:

- **A0:** final-survivor universe and report-period availability;
- **A1:** point-in-time universe and report-period availability;
- **I0000:** point-in-time universe and publication-date availability.

The difference A1 minus A0 isolates historical membership within the available fields. The difference I0000 minus A1 isolates publication timing for accounting-dependent signals.

Implementation analysis starts from I0000 and crosses four binary components:

1. exclude ST securities on the signal session;
2. exclude suspended securities on the signal session;
3. require 20-session mean amount of at least CNY 5 million;
4. shift the IC return clock by one official exchange session.

All 16 combinations are pre-specified for proposed external registration. With four factors, the primary variant matrix contains 72 factor-variant cells: eight cells for A0 and A1 plus 64 cells in the 2^4 implementation factorial. The study reports every cell and never promotes the maximum result.

### 9.1 Ordered ROE common-support decomposition

The 18 variants and 72 factor-variant cells remain unchanged. The following bridge statistics are derived only for the ROE `I0000 − A1` contrast and are not additional variants.

For month `t`, let `R_t` be the finite report-period ROE signal support under A1 and `P_t` the finite recorded-publication-date ROE signal support under I0000, after all non-outcome eligibility rules. Required endpoints must be resolved for every member before either set is used. Let `C_t = R_t ∩ P_t`; neither support is assumed to contain the other. Let `IC_R(S)` and `IC_P(S)` denote rank ICs after both the relevant ROE signal and the common outcome are re-ranked inside set `S`.

The primary monthly contrast has the exact ordered decomposition:

`IC_P(P_t) - IC_R(R_t)`

`= [IC_R(C_t) - IC_R(R_t)]`

`+ [IC_P(C_t) - IC_R(C_t)]`

`+ [IC_P(P_t) - IC_P(C_t)]`.

The three terms are named, in order, the **report-side support-restriction component**, **within-common-support record-replacement component**, and **publication-side support-extension component**. Each is a non-directional, two-sided secondary estimand with Newey-West lag-three inference and membership in the fixed BH family. The identity must hold separately in every estimable month to absolute tolerance `1e-12`; a non-finite bridge IC or larger residual invalidates the run. No support nesting, bridge imputation, or outcome-conditioned deletion may be imposed to make the identity hold. The decomposition is arithmetic and path ordered. It is not causal, and record replacement is not a revision or vintage effect.

## 10. Exact implementation decomposition

Let `v(S)` be a pre-specified statistic under implementation-component subset `S`, using the PIT-publication information set. For component `i`, the exact Shapley contribution is:

`phi_i = sum over S not containing i of [|S|! (K-|S|-1)! / K!] × [v(S union {i}) - v(S)]`,

where `K = 4`. Once an authorized Stage-2 execution occurs, all 16 subsets will be evaluated directly, so no model-based interpolation is permitted. The four contributions must sum to `v(all) - v(empty)` up to numerical rounding. In the current runner the decomposition is computed for monthly IC only. Exact Shapley attribution is order-invariant within this four-component implementation block; the ordered A0-to-A1-to-I0000 information-set chain is not claimed to be order-invariant.

Two-way factorial interactions are a planned module. If implemented before outcome access, they will use difference-in-differences contrasts averaged across the remaining components and will enter a separately enumerated family. They are not currently executable evidence. Higher-order interactions remain absorbed by the Shapley allocation and will not be searched for and selectively highlighted.

## 11. Planned portfolio construction and execution

This section is a design requirement for a future portfolio module, not a description of code that currently exists. No portfolio, cost, turnover, or nonfill claim may be made from the IC-core runner. If completed and externally frozen before outcome access, each month eligible securities will be sorted into deciles using cross-sectional ranks. The headline portfolio contrast will be top decile minus bottom decile. Equal-weight results will be primary for comparability; lagged float-market-cap weights will be secondary.

Signals would be formed after close `t`. Baseline entry would use the unadjusted open at `t+1` and exit the unadjusted open at `t+21`; a lag component would shift those endpoints to `t+2` and `t+22`. No nonfill, suspension-valuation, delisting, terminal-wealth, last-price, or default-recovery rule is authorized by the present IC protocol. Any future portfolio module must acquire the required execution and terminal-event data, implement and test a complete fail-closed rule, and freeze it under a separate registration before viewing its outcomes.

The planned cost model uses a date-indexed schedule for statutory taxes and documented baseline commission and slippage assumptions. In addition, every portfolio would be stressed at 10, 25, and 50 basis points of round-trip non-tax cost. One-way turnover, round-trip turnover, gross return, each cost component, net return, and nonfill rate would all be reported. The study does not label a factor implementable merely because its gross IC is positive.

## 12. Outcomes

For every month, variant, and factor, the current IC core records:

- Spearman-equivalent rank IC;
- equal-weight top-quintile minus universe mean return for continuity with the pilot;
- the eligible cross-sectional count attached to that cell.

The corresponding 72-cell aggregate means, Newey-West t-statistics, and top-quintile-minus-universe spreads are reported in full as descriptive completeness outputs. No cell-specific hypothesis is registered, and no unadjusted cell t-statistic or spread may support a discovery claim. Confirmatory inference is restricted to the sole primary and the fixed 28-member secondary family described below.

The current IC-core output includes aggregate signal-missingness counts, the five report/publication/common-support counts, the no-return publication-exposure diagnostics, and a machine-readable endpoint-resolution code for every signal-eligible record. The result receipt reports aggregate endpoint-code counts, binds the complete private per-security ledger by SHA-256, and verifies that the ledger covers the signal-eligible denominator exactly. A full per-security signal-missingness and non-endpoint exclusion audit, eligible-universe attribution beyond the registered support counts, and percentage attenuation remain unimplemented and excluded; they may not be reconstructed selectively after results are seen.

The pilot's top-quintile-minus-universe statistic is not self-financing and is not treated as a portfolio return. Decile long-short returns, costs, turnover, and nonfills are unavailable until the planned module is implemented, tested, and separately locked; any later long-short outcome must retain explicit financing and short-leg caveats, including the practical limits on shorting A-shares.

## 13. Statistical inference and multiplicity

The unit of time-series inference is the monthly observation. The pre-specified inferential set proposed for external registration contains exactly 29 estimands: one primary plus 28 secondary family members. Two deterministic timing-isolation checks and the common-support efficiency identity are reported separately and are not inferential hypotheses. Primary tests use the paired monthly difference between variants rather than comparing two independently estimated t-statistics. The mean paired difference receives a Newey-West HAC standard error with lag three and a two-sided 95% confidence interval. Directional expectations organize interpretation but do not convert the reported test to a one-sided p-value.

Because H1 is the sole primary estimand, it receives no multiplicity adjustment. The fixed secondary IC family contains exactly 28 members: one downstream composite publication-timing contrast, eight paired contrasts (membership and full-implementation effects for each of four factors), sixteen component-factor Shapley estimates, and the three non-directional ROE common-support components. Its p-values use the Benjamini-Hochberg procedure at false-discovery rate 0.10. A missing or non-estimable registered member remains in the family denominator and is a non-rejection. The momentum and low-volatility publication-timing contrasts are deterministic isolation checks outside the inferential family; either must be zero to absolute tolerance `1e-12` or the run fails closed. The three common-support components must add to the primary monthly contrast to absolute tolerance `1e-12`; a larger residual also fails closed. Portfolio, event-study, interaction, and stationary-bootstrap families do not exist and require a separate locked plan. Unadjusted and adjusted values are both reported.

If fewer than 120 paired monthly observations remain for an estimand, the paper reports the estimate and interval but makes no statistical-significance or generalization claim for that estimand. The evidentiary gate remains all 156 registered rebalances with complete factor-variant cells; falling below it cannot be repaired by selecting a shorter interval.

The 156-month design has a precision rationale. Under a normal-approximation 80% power sensitivity, a monthly paired-difference standard deviation of 0.08-0.12 and HAC variance inflation of 1.0-1.5 imply an absolute IC minimum detectable effect of approximately 0.018-0.033. These conservative scenarios may be supplemented by simulations based only on the already disclosed pilot before registration; no Stage-2 outcome may revise the threshold. The current IC core reports signed and absolute IC change plus the three ordered common-support components. Percentage attenuation remains unimplemented and excluded. It may be reported only if a later module is implemented and frozen and only when the comparator IC is positive, its absolute value is at least 0.005, and the signed difference is negative. This restriction does not alter Section 4's narrower qualitative sign-based wording rule; otherwise the paper uses the neutral term timing displacement.

## 14. Missing data and exclusions

Missing signals are not filled with cross-sectional means. A security with a missing required signal field is excluded from that factor's signal-eligible cross-section, and aggregate factor-specific missing counts are reported. The current runner does not attribute those signal omissions to a more granular reason taxonomy. The composite requires all three primary component ranks. The signal-eligible denominator is finalized before outcome lookup, and outcome availability cannot remove a security from it.

Every signal-eligible record receives a machine-readable endpoint-resolution code. Under the current exact-quote adapter, only `EXACT_OFFICIAL_SESSION_ADJUSTED_CLOSE` is resolved; the fixed unresolved codes are `MISSING_EXACT_FORWARD_EXIT`, `MISSING_EXACT_LAG_ENTRY`, and `MISSING_EXACT_LAG_EXIT`. The current adapter records which required quote is absent but does not infer whether suspension, delisting, or another economic cause produced that absence. Any non-finite return after exact endpoints resolve is a separate cell-integrity failure, not an endpoint reason code. The result receipt exposes aggregate code counts and a SHA-256 for the complete private ledger, and its verifier requires the ledger-key set to equal the signal-eligible key set. This endpoint audit does not claim a full per-security explanation of all signal or universe exclusions. Security identifiers must be stable across symbol changes or linked through a documented permanent identifier. Duplicate date-symbol quote keys and duplicate effective security-master records fail closed.

## 15. Planned robustness analyses (currently excluded)

The current runner does not implement the robustness program. Every item below is planned, secondary, and excluded from the current executable evidence. An item may enter the study only after its code, complete numerical settings, data gates, estimand list, and multiplicity treatment are implemented, tested, and frozen before Stage-2 outcome access:

- calendar subperiods determined without reference to factor returns;
- Main Board, ChiNext, and STAR Market, when their coverage passes the same field gates;
- state-owned versus non-state-owned firms only when an independently sourced, historically effective ownership field is available;
- industry- and size-neutralized ranks;
- 12-to-1 momentum and 60-session low volatility;
- reconstructed versus vendor-supplied ROE;
- equal-weight versus lagged float-market-cap weight;
- baseline versus stressed transaction costs;
- announcement-event or return-timing windows, which additionally require a separately validated first-release/vintage and timestamp contract;
- a pre-specified second-vendor audit sample when data rights permit.

No subgroup created after observing a large or surprising return may enter the confirmatory tables. Such findings may appear only in a labeled exploratory appendix. A structured machine-readable deviation log and its receipt integration are planned but unimplemented; until they exist, any deviation must be disclosed manually and the receipt must not be described as containing it. Listing an item in this planned section does not make it registered or executable.

## 16. Reproducibility and evidence chain

The public reproducibility package will contain:

- the externally timestamped plan and statistical analysis plan;
- a tagged analysis-code release;
- schemas and deterministic synthetic fixtures;
- unit, contract, and end-to-end tests;
- raw-file names, sizes, row counts, date ranges, and SHA-256 hashes without local paths;
- the official common-session calendar's schema, source provenance, byte size, row count, date range, and SHA-256 hash;
- a data-rights statement and vendor field dictionary where redistribution is permitted;
- a machine-readable prior-specification inventory and signed owner exposure attestation;
- the complete registered result matrix;
- monthly aggregate statistics when licensing permits;
- a canonical result receipt binding the plan core, code revision, declared input-file hashes, registered IC lattice, all 29 inferential estimands, common-support efficiency, implemented aggregate missingness/support and exposure diagnostics, aggregate endpoint reason counts, the SHA-256 and key-count integrity of the complete private per-security endpoint-reason ledger, the authorization-consumption record and hash, and claim gates.

The result receipt exposes structural and integrity evidence for the IC core and binds the private endpoint ledger by hash. The runner constructs one endpoint-resolution record for every signal-eligible key. Public-only verification checks the canonical receipt, registered identities, aggregate counts, and ledger metadata, but cannot inspect the withheld ledger. An explicit controlled-audit mode, when supplied with the private ledger, additionally checks its hash, canonical ordering, uniqueness, per-cell cardinality, reason counts, and agreement with the published signal-eligible denominators. Without licensed raw inputs, neither mode can independently authenticate the underlying security identities. The receipt does not contain a machine-readable deviation log or provide a complete per-security audit of non-endpoint signal and universe exclusions. Structured deviation logging remains planned and unimplemented.

The nested draft protocol is not accepted directly by the runner. The evidence chain is non-circular and must occur in this order:

1. Retain `coverage_probe_spec.v1.json` byte-for-byte, externally timestamp `coverage_probe_spec.v2.json` before its bounded probe is run, and then freeze the v2 probe receipt, outcome-blind coverage report, rights/semantics review, official calendar, prior-specification inventory, and prior-exposure attestation.
2. Materialize every core field in the flat execution-plan template. Merely changing the draft's `status` is prohibited. Set `design_frozen_at` and compute the canonical plan-core digest after excluding only the not-yet-populated `external_registration` envelope and `locked_at`. The frozen core binds the analysis dates, warm-up interval, protocol/SAP/inventory/attestation/calendar hashes, code commit, all 18 variants, all four factors, IC clocks, current missingness rules, and every implemented inference setting.
3. Create `design_manifest_v1` to bind that exact plan-core digest, code, protocol, SAP, coverage and review artifacts, inventory, the actual prior-exposure log and its attestation, data declaration, raw-input identities, and official calendar. The manifest contains neither its own digest nor any later receipt or authorization.
4. Submit the exact manifest bytes or their SHA-256 digest to the external provider and record the response as `registration_receipt_v1`, which points backward to the manifest digest.
5. Independently verify the receipt and create `execution_authorization`, which points backward to the manifest, receipt, frozen plan core, calendar, and gate artifacts and authorizes blind-data release. No Stage-2 outcome file may be released or inspected before that authorization.
6. Complete the final execution-plan envelope by recording the plan-core digest, manifest hash, receipt hash, authorization hash, provider record, and `locked_at = authorized_at`. The envelope and `locked_at` are excluded from the previously registered plan-core digest, so this packaging is non-circular and cannot change the frozen design.
7. At execution, validate the complete chain and atomically create the private authorization-consumption sidecar, keyed by the authorization-file SHA-256, before loading any quote/fundamental outcome rows or computing any factor/outcome value. Exclusive creation makes a second local claim fail closed; an interrupted or failed claim remains consumed and requires a new authorization. The sidecar is outside the immutable authorization and final plan envelope, so it points backward without creating a hash cycle.

The current runner accepts only `runner_scope = ic_core_only` and only the explicit human-verification evidence types in the maintained templates. It does not implement cryptographic signature or registry-inclusion-proof validation, so a cryptographic label alone cannot pass. Hashes establish the identity and integrity of retained local artifacts but do not authenticate the provider's timestamp by themselves; a named authorized human must verify the retained provider page, email, or journal record and hash that evidence. This is the explicit human trust boundary. A future cryptographic path requires a separately implemented, tested, and frozen protocol.

The registered real-data execution environment is exact rather than ranged: Python 3.12.12, NumPy 2.0.2, and pandas 2.3.3. The runner verifies those three versions and requires the entire repository—not only the package source directory—to be clean at the checked-out registered commit. Any tracked modification or untracked file, including a repository-root Python import hook, blocks execution. Cross-version fixture tests remain compatibility checks and do not change this real-data runtime contract.

Licensed raw rows will not be published without explicit permission. Hashes establish file identity, not vendor correctness. An independent authorized rerun is strongly preferred and will be recorded separately from the authors' execution.

Original repository code and documentation are released under the MIT License. That license does not grant rights to proprietary market data, third-party materials, trademarks, or any licensed rows withheld from the repository; data access and reviewer inspection remain separately governed by the documented rights gate.

## 17. Deviations and stopping rules

The protocol requires every deviation to receive a timestamp, rationale, affected estimand, and classification as administrative, data-driven but outcome-blind, or outcome-aware. The structured deviation-log and receipt-reporting module is planned but unimplemented; the current runner and verifier do not create or validate such a log. Until that module is implemented and frozen, deviations require explicit manual disclosure and no receipt may claim to bind them. Outcome-aware deviations cannot replace the primary analysis; they appear only as exploratory sensitivity checks.

The study stops without primary conclusions if:

- a minimum coverage or rights gate fails;
- prior exposure to the intended 2010-2022 outcomes cannot be ruled out and documented before data release;
- the frozen plan, `design_manifest_v1`, `registration_receipt_v1`, and `execution_authorization` hashes or required timestamps are missing, inconsistent, circular, or out of order;
- the authorization-consumption sidecar cannot be exclusively and durably created before outcome load, already exists for that authorization hash, or differs from the hash-bound record in the receipt;
- a required variant or factor cell is missing;
- any signal-eligible security lacks an exact required official-session endpoint under the current adapter, or the endpoint-reason ledger is missing, duplicated, unhashed, or does not cover the signal-eligible denominator exactly;
- the three common-support components fail to add to the primary monthly timing contrast within absolute tolerance `1e-12`;
- publication dates cannot be distinguished from report-period dates;
- adjusted-close return semantics or corporate-action handling cannot be documented; a later portfolio claim additionally stops if unadjusted execution prices cannot be distinguished from adjusted research prices;
- the code revision cannot reproduce its receipt on the authorized data.

Negative, null, mixed, and sign-reversing results are all publishable outcomes under the protocol. A result is not a failure because it lacks statistical significance.

## 18. Manuscript and claim policy

The eventual empirical paper will lead with the bias-decomposition question, not the repository. The repository appears as the implementation and evidence infrastructure. The paper will distinguish:

- the disclosed pilot;
- the registered historical panel;
- the prospective post-registration extension;
- any exploratory appendix.

Until all corresponding evidence gates pass, the receipt fields remain:

- `performance_claim = false`;
- `generalization_claim = false`;
- `usable_for_trading_decisions = false`;
- `revision_history_claim = false`;
- `vintage_value_claim = false`;
- `historical_investor_observed_value_claim = false`;
- `announcement_reaction_claim = false`;
- `return_timing_claim = false`;
- `portfolio_or_trading_claim = false`.

Even after a valid IC execution, the single-version accounting claim remains bounded to a recorded-publication-date specification effect. A result may not be described as a reconstructed historical information set, revision effect, restatement effect, or announcement reaction.

The final paper will include an AI-assistance disclosure describing tools used for code scaffolding, document drafting, and editing; human authors must review, validate, and take responsibility for every technical and interpretive decision.

## References

Brown, S. J., Goetzmann, W., Ibbotson, R. G., & Ross, S. A. (1992). Survivorship bias in performance studies. *Review of Financial Studies, 5*(4), 553-580. https://doi.org/10.1093/rfs/5.4.553

Faff, R. W. (2023). PBFJ Editorial: Engaging with responsible science - "Open for business" - launching the PBFJ pre-registration publication initiative. *Pacific-Basin Finance Journal, 79*, 101837. https://doi.org/10.1016/j.pacfin.2022.101837

Faff, R. W. (2026). PBFJ Editorial: Responsible and open science in action - an update on the PBFJ experiment and beyond. *Pacific-Basin Finance Journal, 96*, 103045. https://doi.org/10.1016/j.pacfin.2025.103045

Gharghori, P., & Nguyen, A. (2026). Which factors in China? A pre-registered study. *Pacific-Basin Finance Journal, 96*, 103012. https://doi.org/10.1016/j.pacfin.2025.103012

Harvey, C. R., Liu, Y., & Zhu, H. (2016). ... and the cross-section of expected returns. *Review of Financial Studies, 29*(1), 5-68. https://doi.org/10.1093/rfs/hhv059

Hou, K., Xue, C., & Zhang, L. (2020). Replicating anomalies. *Review of Financial Studies, 33*(5), 2019-2133. https://doi.org/10.1093/rfs/hhy131

Liu, J., Stambaugh, R. F., & Yuan, Y. (2019). Size and value in China. *Journal of Financial Economics, 134*(1), 48-69. https://doi.org/10.1016/j.jfineco.2019.03.008

Newey, W. K., & West, K. D. (1987). A simple, positive semi-definite, heteroskedasticity and autocorrelation consistent covariance matrix. *Econometrica, 55*(3), 703-708. https://doi.org/10.2307/1913610

Novy-Marx, R., & Velikov, M. (2016). A taxonomy of anomalies and their trading costs. *Review of Financial Studies, 29*(1), 104-147. https://doi.org/10.1093/rfs/hhv063

Shapley, L. S. (1953). A value for n-person games. In H. W. Kuhn & A. W. Tucker (Eds.), *Contributions to the Theory of Games II* (pp. 307-317). Princeton University Press.

Stambaugh, R. F., Yu, J., & Yuan, Y. (2017). Mispricing factors. *Review of Financial Studies, 30*(4), 1270-1315. https://doi.org/10.1093/rfs/hhw107

White, H. (2000). A reality check for data snooping. *Econometrica, 68*(5), 1097-1126. https://doi.org/10.1111/1468-0262.00152
