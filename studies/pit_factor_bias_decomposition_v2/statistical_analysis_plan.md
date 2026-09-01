# How Much Do Information Timing and Implementation Choices Shift A-Share Factor Evidence?

## A Pre-Specified Bias Decomposition

**Protocol status:** Draft for data-feasibility review; not locked and not yet externally registered<br>
**Intended route:** Pacific-Basin Finance Journal hybrid pre-registration pathway<br>
**Authors and affiliations:** To be confirmed before external submission<br>
**Protocol date:** 1 September 2026

## 1. Registration status and non-negotiable boundary

This document is a Stage-2 statistical analysis plan, not a claim of completed preregistration. The research team has already observed the results of the repository's 2025-2026 pilot study. Those results are disclosed in the canonical `pit-factor-replication-v1` receipt and cannot be relabeled as prospective evidence. They serve only as an empirical precondition motivating a larger and cleaner study.

The intended publication route follows the Pacific-Basin Finance Journal's responsible-science initiative. Faff (2023) describes a four-phase pre-registration pathway that evaluates the importance of the question and strength of the method before results are known. Faff (2026) subsequently describes a hybrid pathway for studies that require a transparently verified empirical precondition before downstream hypotheses can be fixed. The present pilot is proposed as that disclosed precondition. No Stage-2 outcome analysis may begin until the plan passes its coverage gates, is frozen to a Git commit, raw-file identities, and an official-calendar identity, receives an external timestamp or journal instruction consistent with the chosen pathway, and a separate execution authorization verifies the full chronology and permits release of the blind sample.

## 2. Research question and contribution

The study asks:

> How much do final-survivor sampling, report-period rather than publication-date availability, tradability screens, liquidity requirements, and a one-session implementation lag shift measured A-share factor evidence?

The scientific contribution is a quantitative decomposition of research-design bias, not a search for a new profitable anomaly. The study uses familiar signals so that differences across variants can be attributed to the historical information set and implementation clock rather than to a novel model. The contribution has three layers:

1. **Information-set bias.** Measure the paired effect of historical listing membership and accounting publication timing on the same monthly cross-sections.
2. **Implementation decomposition.** Replace the pilot's bundled stress variant with the complete factorial of four implementation controls, permitting exact Shapley attribution while preserving interactions in the allocation. Formal interaction tests are a planned, unimplemented module and are excluded from the current IC core.
3. **Research governance.** Bind the data declaration, plan, code, registered IC lattice, implemented core outputs, and claim gates in a canonical receipt. A structured deviation-log and receipt-reporting module is planned but unimplemented, so the current receipt cannot claim to contain deviations.

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
- momentum and low-volatility publication-timing differences as deterministic isolation checks, not inferential hypotheses;
- eligible-universe loss, percentage-attenuation output, and signal-missingness diagnostics only after their dedicated reporting code is implemented, tested, and separately frozen.

Secondary estimates are diagnostic and will be labeled as such even when their statistics appear stronger than the primary results.

The current executable runner is deliberately limited to the IC core. Dedicated signal-missingness tables, machine-readable exclusion reason codes, eligible-universe-loss and percentage-attenuation outputs, raw-ratio regressions, robustness analyses, pre-specified two-way interactions, stationary bootstrap intervals, next-open portfolios, transaction costs, turnover, and nonfills are planned modules. They are excluded from the current executable evidence and enter no registered claim until their code, tests, data gates, complete numerical settings, and multiplicity treatment are finished and externally frozen before Stage-2 outcome access.

## 5. Data-feasibility gates

Only outcome-blind metadata and field coverage may be examined before registration. The coverage report must not contain factor returns or portfolio outcomes.

The plan may advance from `draft_data_feasibility_pending` to `locked` only when all of the following outcome-blind, pre-lock feasibility conditions hold:

1. The fixed January 2010 through December 2022 interval supplies all 156 intended rebalances, with quote warm-up from January 2009 and forward outcomes through January 2023.
2. The quote audit shows at least 15 official sessions and 1,000 quoted symbols in all 156 target months.
3. At least 95% of otherwise usable fundamental records contain a valid publication date.
4. Historical list and delist dates are present, and the master contains delisted securities.
5. Adjusted close return semantics and corporate-action handling are documented and hash-bound. Unadjusted open and nonfill semantics are required only if the planned portfolio module is later implemented and frozen; the IC core makes no execution-price claim.
6. Daily amount, ST status, and suspension status are available under documented units and timing semantics.
7. Data rights permit the intended local analysis, the public release of aggregate results, field definitions, and file hashes, and publication of the exact official-calendar session dates embedded in the receipt.
8. The analysis code passes its complete offline test suite and the plan enumerates every result cell.
9. The owner signs a prior-exposure attestation that no 2010-2022 Stage-2 factor outcomes have been inspected; repository specifications are separately inventoried whether or not their execution history is known.
10. An official common SSE/SZSE session calendar includes every common session from January 2009 through the end of January 2023, passes its schema and semantic checks, and is bound by path, byte size, row count, date range, source provenance, and SHA-256 hash before the plan core is frozen.

Column names do not satisfy gates 5-7. An authorized reviewer must complete a hash-bound attestation that separately verifies adjusted-return and amount semantics, non-degenerate tradability fields, rights to publish aggregate outputs, and rights to embed the exact official-calendar session dates in a receipt. Without that attestation, the coverage tool reports `BLOCKED` even when every required column is present.

A distinct post-authorization evidence-eligibility stop is evaluated only after the registered runner executes: every one of the 156 months must contain all 72 registered cells, and every cell must contain at least 1,000 finite signal-outcome pairs. This is not a pre-lock coverage test and does not authorize the analysis team to inspect Stage-2 outcomes before registration. Failure produces `INSUFFICIENT_EVIDENCE`; it cannot be repaired by shortening the interval, dropping a cell, or changing the threshold.

If a gate fails, the study stops and reports the failed condition. The team will not replace 2010-2022 with a later feasible interval, shorten the sample, lower the publication-date threshold, remove an inconvenient board, or relax the minimum universe after viewing factor outcomes. A materially different feasible design must become a separately timestamped protocol and may not inherit the primary status of this design.

## 6. Population and sample construction

The target population is ordinary China A-shares listed on the Shanghai or Shenzhen exchanges. B-shares, funds, bonds, preferred shares, and non-equity instruments are excluded using the historically valid security type. A security enters the point-in-time universe on or after its listing date and exits after its delisting date. A final-survivor variant is retained only as a deliberately biased comparator.

The intended previously uninspected primary historical interval is 1 January 2010 through 31 December 2022, subject to the prior-exposure attestation and fixed coverage gates. It ends before the observed 2023-2026 pilot. The first eligible common SSE/SZSE session of each month in the hash-bound official calendar is the rebalance date. Rolling signals may use observations from the fixed warm-up beginning 1 January 2009, but no pre-2010 observation contributes an outcome. The forward horizon is 20 official exchange sessions.

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

Publication-date alignment is not equivalent to vintage reconstruction. The current runner has no validated revision-vintage adapter, so revision-history claims are unconditionally prohibited. Historical as-of timestamps, revision identifiers, and value-at-vintage records would all be necessary for a future adapter but are not sufficient by themselves to open the current claim gate. Later vendor corrections cannot be presented as information available to historical investors.

The IC clock is diagnostic, not a simulated execution claim. The no-lag outcome is adjusted close at session `t+20` divided by adjusted close at signal session `t`, minus one. The lag outcome is adjusted close at `t+21` divided by adjusted close at `t+1`, minus one. These endpoints are defined on the common official exchange-session calendar; a missing symbol row makes the outcome missing and never silently advances the endpoint to that symbol's next observed row. The exact calendar bytes, schema version, source provenance, timezone, date range, and SHA-256 hash are design inputs and must be bound by the frozen plan core and design manifest.

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

All 16 combinations are registered. With four factors, the primary variant matrix contains 72 factor-variant cells: eight cells for A0 and A1 plus 64 cells in the 2^4 implementation factorial. The study reports every cell and never promotes the maximum result.

## 10. Exact implementation decomposition

Let `v(S)` be a registered statistic under implementation-component subset `S`, using the PIT-publication information set. For component `i`, the exact Shapley contribution is:

`phi_i = sum over S not containing i of [|S|! (K-|S|-1)! / K!] × [v(S union {i}) - v(S)]`,

where `K = 4`. Once an authorized Stage-2 execution occurs, all 16 subsets will be evaluated directly, so no model-based interpolation is permitted. The four contributions must sum to `v(all) - v(empty)` up to numerical rounding. In the current runner the decomposition is computed for monthly IC only. Exact Shapley attribution is order-invariant within this four-component implementation block; the ordered A0-to-A1-to-I0000 information-set chain is not claimed to be order-invariant.

Two-way factorial interactions are a planned module. If implemented before outcome access, they will use difference-in-differences contrasts averaged across the remaining components and will enter a separately enumerated family. They are not currently executable evidence. Higher-order interactions remain absorbed by the Shapley allocation and will not be searched for and selectively highlighted.

## 11. Planned portfolio construction and execution

This section is a design requirement for a future portfolio module, not a description of code that currently exists. No portfolio, cost, turnover, or nonfill claim may be made from the IC-core runner. If completed and externally frozen before outcome access, each month eligible securities will be sorted into deciles using cross-sectional ranks. The headline portfolio contrast will be top decile minus bottom decile. Equal-weight results will be primary for comparability; lagged float-market-cap weights will be secondary.

Signals are formed after close `t`. Baseline entry is the unadjusted open at `t+1` and exit is the unadjusted open at `t+21`; the lag component shifts those endpoints to `t+2` and `t+22`. A price-limit lock, suspension, or missing-open entry is not chased and its intended weight remains cash until the next rebalance. An exit nonfill is attempted at the first executable unadjusted open for up to 20 subsequent official sessions. If neither a trade nor an independently verified cash settlement occurs, the conservative terminal recovery is zero, with a last-observed-price sensitivity reported. Delistings use verified exchange or depository cash settlement when available and otherwise follow the same terminal rule.

The planned cost model uses a date-indexed schedule for statutory taxes and documented baseline commission and slippage assumptions. In addition, every portfolio would be stressed at 10, 25, and 50 basis points of round-trip non-tax cost. One-way turnover, round-trip turnover, gross return, each cost component, net return, and nonfill rate would all be reported. The study does not label a factor implementable merely because its gross IC is positive.

## 12. Outcomes

For every month, variant, and factor, the current IC core records:

- Spearman-equivalent rank IC;
- equal-weight top-quintile minus universe mean return for continuity with the pilot;
- the eligible cross-sectional count attached to that cell.

The corresponding 72-cell aggregate means, Newey-West t-statistics, and top-quintile-minus-universe spreads are reported in full as descriptive completeness outputs. No cell-specific hypothesis is registered, and no unadjusted cell t-statistic or spread may support a discovery claim. Confirmatory inference is restricted to the sole primary and the fixed 25-member secondary family described below.

The current runner does not produce a dedicated signal-missingness table, per-security exclusion reason codes, an eligible-universe-loss decomposition, or percentage-attenuation output. Those reports are planned, unimplemented, and excluded from current evidentiary claims. A later implementation must be tested and frozen before Stage-2 outcome access; it may not be reconstructed selectively after results are seen.

The pilot's top-quintile-minus-universe statistic is not self-financing and is not treated as a portfolio return. Decile long-short returns, costs, turnover, and nonfills are unavailable until the planned module is implemented, tested, and separately locked; any later long-short outcome must retain explicit financing and short-leg caveats, including the practical limits on shorting A-shares.

## 13. Statistical inference and multiplicity

The unit of time-series inference is the monthly observation. The registered inferential set contains exactly 26 estimands: one primary plus 25 secondary family members. Two deterministic timing-isolation checks are reported separately and are not inferential hypotheses. Primary tests use the paired monthly difference between variants rather than comparing two independently estimated t-statistics. The mean paired difference receives a Newey-West HAC standard error with lag three and a two-sided 95% confidence interval. Directional expectations organize interpretation but do not convert the reported test to a one-sided p-value.

Because H1 is the sole primary estimand, it receives no multiplicity adjustment. The fixed secondary IC family contains exactly 25 members: one downstream composite publication-timing contrast, eight paired contrasts (membership and full-implementation effects for each of four factors), and sixteen component-factor Shapley estimates. Its p-values use the Benjamini-Hochberg procedure at false-discovery rate 0.10. A missing or non-estimable registered member remains in the family denominator and is a non-rejection. The momentum and low-volatility publication-timing contrasts are deterministic isolation checks outside the inferential family; either must be zero to absolute tolerance `1e-12` or the run fails closed. Portfolio, interaction, and stationary-bootstrap families do not yet exist and require a separate locked plan. Unadjusted and adjusted values are both reported.

If fewer than 120 paired monthly observations remain for an estimand, the paper reports the estimate and interval but makes no statistical-significance or generalization claim for that estimand. The evidentiary gate remains all 156 registered rebalances with complete factor-variant cells; falling below it cannot be repaired by selecting a shorter interval.

The 156-month design has a precision rationale. Under a normal-approximation 80% power sensitivity, a monthly paired-difference standard deviation of 0.08-0.12 and HAC variance inflation of 1.0-1.5 imply an absolute IC minimum detectable effect of approximately 0.018-0.033. These conservative scenarios may be supplemented by simulations based only on the already disclosed pilot before registration; no Stage-2 outcome may revise the threshold. The current IC core reports signed and absolute IC change. Eligible-universe-loss and percentage-attenuation outputs are planned but unimplemented and excluded from current claims. A percentage attenuation statistic may be reported only if that module is later implemented and frozen and only when the comparator IC is positive, its absolute value is at least 0.005, and the signed difference is negative. This restriction does not alter Section 4's narrower qualitative sign-based wording rule; otherwise the paper uses the neutral term timing displacement.

## 14. Missing data and exclusions

Missing signals are not filled with cross-sectional means. A security with a missing required field is excluded from that factor's monthly cross-section. The composite requires all three primary component ranks. The current runner records the resulting cell-level cross-sectional count but does not yet create a dedicated missingness table.

Machine-readable per-security reason codes for every exclusion category are planned but unimplemented and excluded from the current IC core. Until that module is implemented, tested, and frozen, the study may not claim a reason-code audit or publish selectively reconstructed exclusion counts. The current verifier checks the registered variant/factor lattice, required cell identities and counts, and exposed cross-sectional sizes; it cannot detect every arbitrary per-security omission or explain why a security is absent. A discovered exclusion outside the registered rules invalidates the affected result, but absence of such a finding is not proof that no silent drop occurred. Security identifiers must be stable across symbol changes or linked through a documented permanent identifier. Duplicate date-symbol quote keys and duplicate effective security-master records fail closed.

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
- a canonical receipt binding the plan core, code revision, declared input-file hashes, registered IC lattice, implemented core output tables, and claim gates.

The current receipt exposes structural and integrity evidence only for the implemented IC core. It does not contain a machine-readable deviation log, prove that every per-security exclusion was justified, or detect arbitrary silent row drops. Deviation logging and receipt reporting remain planned, unimplemented modules.

The nested draft protocol is not accepted directly by the runner. The evidence chain is non-circular and must occur in this order:

1. Freeze the outcome-blind coverage report, rights/semantics review, official calendar, prior-specification inventory, and prior-exposure attestation.
2. Materialize every core field in the flat execution-plan template. Merely changing the draft's `status` is prohibited. Set `design_frozen_at` and compute the canonical plan-core digest after excluding only the not-yet-populated `external_registration` envelope and `locked_at`. The frozen core binds the analysis dates, warm-up interval, protocol/SAP/inventory/attestation/calendar hashes, code commit, all 18 variants, all four factors, IC clocks, current missingness rules, and every implemented inference setting.
3. Create `design_manifest_v1` to bind that exact plan-core digest, code, protocol, SAP, coverage and review artifacts, inventory, the actual prior-exposure log and its attestation, data declaration, raw-input identities, and official calendar. The manifest contains neither its own digest nor any later receipt or authorization.
4. Submit the exact manifest bytes or their SHA-256 digest to the external provider and record the response as `registration_receipt_v1`, which points backward to the manifest digest.
5. Independently verify the receipt and create `execution_authorization`, which points backward to the manifest, receipt, frozen plan core, calendar, and gate artifacts and authorizes blind-data release. No Stage-2 outcome file may be released or inspected before that authorization.
6. Complete the final execution-plan envelope by recording the plan-core digest, manifest hash, receipt hash, authorization hash, provider record, and `locked_at = authorized_at`. The envelope and `locked_at` are excluded from the previously registered plan-core digest, so this packaging is non-circular and cannot change the frozen design.

The current runner accepts only `runner_scope = ic_core_only`. If the registration provider supplies a verifiable digital signature, its algorithm, key identifier, signed payload, and signature are retained. If it does not, hashes establish the identity and integrity of local artifacts but do not authenticate the provider's timestamp by themselves; a named authorized human must verify the retained provider page, email, or journal record and hash that evidence. This is the explicit human trust boundary.

Licensed raw rows will not be published without explicit permission. Hashes establish file identity, not vendor correctness. An independent authorized rerun is strongly preferred and will be recorded separately from the authors' execution.

The repository currently has no software license. No document may call it open source, and no JOSS submission may be attempted, until the owner makes an explicit license decision and the selected license is added. That legal choice is outside the statistical protocol.

## 17. Deviations and stopping rules

The protocol requires every deviation to receive a timestamp, rationale, affected estimand, and classification as administrative, data-driven but outcome-blind, or outcome-aware. The structured deviation-log and receipt-reporting module is planned but unimplemented; the current runner and verifier do not create or validate such a log. Until that module is implemented and frozen, deviations require explicit manual disclosure and no receipt may claim to bind them. Outcome-aware deviations cannot replace the primary analysis; they appear only as exploratory sensitivity checks.

The study stops without primary conclusions if:

- a minimum coverage or rights gate fails;
- prior exposure to the intended 2010-2022 outcomes cannot be ruled out and documented before data release;
- the frozen plan, `design_manifest_v1`, `registration_receipt_v1`, and `execution_authorization` hashes or required timestamps are missing, inconsistent, circular, or out of order;
- a required variant or factor cell is missing;
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
- `revision_history_claim = false`.

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
