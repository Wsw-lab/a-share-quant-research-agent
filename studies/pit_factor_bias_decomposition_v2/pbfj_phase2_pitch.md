# PBFJ Phase-2 research pitch

## Working title

**How Much Do Information Timing and Implementation Choices Shift A-Share Factor Evidence? A Pre-Specified Bias Decomposition**

## Basic research question

How much do survivorship, accounting first-availability, tradability, liquidity, and execution-timing conventions change measured A-share factor evidence?

## Key papers

Liu, Stambaugh, and Yuan (2019) establish market-specific construction and actual report-release dates in China. Gharghori and Nguyen (2026) provide the direct PBFJ benchmark: a pre-registered China factor-model comparison. Faff (2023, 2026) provides the responsible-science and hybrid pathway. Hou, Xue, and Zhang (2020) and Novy-Marx and Velikov (2016) motivate the replication and implementation boundaries.

## Motivation and puzzle

Asset-pricing results are sensitive to what a historical investor could know and trade. Public quantitative projects often combine final survivors, fiscal-period-end accounting values, contemporaneous returns, and selective reporting. Studying these choices separately obscures which specification change drives a result.

A disclosed pilot using 2023-2026 Shanghai and Shenzhen A-share data provides an empirical precondition. Across 18 evaluation cross-sections from January 2025 through June 2026, replacing report-period availability with publication-date availability reduces mean ROE rank IC from 0.0461 to 0.0105 and fixed-composite IC from 0.0332 to 0.0038. The pilot is too short and has already been observed, so it cannot answer the general question. It remains a separate precondition sample and will not enter the Stage-2 primary estimate.

## Core idea

The study separates two information-set transitions from four implementation components. First, it compares final survivors with historical list/delist membership while holding report-period timing fixed. Second, it changes only accounting availability from report-period end to publication date. Third, from the PIT-publication baseline, it runs the complete 2^4 factorial of ST exclusion, suspension exclusion, a 20-session CNY 5 million amount floor, and a one-session implementation lag.

Within the four-component implementation block, the full factorial prevents the order in which those controls are added from determining their attribution. Exact Shapley values allocate that block's full implementation effect across the four components while distributing their interactions. The two information-set transitions remain explicitly ordered comparisons and are not described as order-invariant. Every factor-variant cell is reported; there is no best-model selection.

## Data

The Stage-2 target is a January 2010-December 2022 SH/SZ A-share outcome panel, including delisted securities, for which no factor outcomes may be inspected before a signed exposure attestation and journal-authorized release. It ends before the observed 2023-2026 pilot. Some 2020-2022 fundamental rows have already been available for outcome-blind feasibility review, but the current quote bundle starts in 2023 and no historical factor-return panel has been assembled. The IC core requires documented adjusted-return semantics, amount, ST and suspension state, list/delist dates, publication-dated ROE, and lawful research and aggregate-reporting rights. Unadjusted open, point-in-time capitalization, price-limit, and other execution fields belong to the planned portfolio extension.

The current licensed bundle covers 2023-2026 for the full market and is frozen as observed pilot evidence. It cannot be used to satisfy the blind Stage-2 historical requirement. If the full 2010-2022 panel fails any outcome-blind coverage, publication-date, membership, rights, or code gate, the study stops rather than selecting a shorter feasible interval after outcomes are seen. Publication dates support first-availability analysis; revision-history claims remain prohibited without explicit historical vintages.

## Tools and method

The sole primary estimand is the paired monthly signed ROE rank-IC decrement when accounting availability moves from report-period end to publication date within the point-in-time universe: `IC(publication date) - IC(report-period end)`. The directional expectation is non-positive, while inference reports a two-sided Newey-West HAC interval and p-value. Because there is one primary test, no primary Holm adjustment is used.

The fixed-weight composite timing difference is secondary. Momentum and low-volatility timing differences are registered deterministic isolation checks because their signals do not use accounting publication dates; nonzero differences indicate an implementation-isolation failure rather than new factor evidence. The registered inferential set contains exactly 26 estimands: the sole primary plus a secondary family of exactly 25 p-values—one composite timing contrast, eight paired IC contrasts covering membership and the full implementation effect for four factors, and sixteen component-by-factor IC Shapley estimates. Benjamini-Hochberg controls that family at FDR 0.10. The two isolation checks sit outside that inferential count.

The current executable runner is IC-core-only: it produces the complete cell matrix, paired IC estimands, HAC inference, and exact IC Shapley values for the four-component implementation block. The 72 cell means, t-statistics, and top-minus-universe spreads are reported as descriptive completeness outputs only and cannot support cell-specific discovery claims. Dedicated signal-missingness tables, exclusion reason codes, eligible-universe-loss and percentage-attenuation outputs, raw-ratio regressions, robustness analyses, next-open portfolios, costs, nonfills, stationary bootstrap intervals, and factorial interaction tests are planned but unimplemented modules. They will enter no registered claim unless their code, tests, data gates, numerical settings, and multiplicity treatment are completed and frozen before outcome access. Shapley values preserve interactions in the allocation but are not formal interaction tests.

For the implemented IC core, the canonical receipt binds the plan-core hash, code revision, declared raw-file hashes, sample coverage, the registered variant/factor lattice, implemented result cells and estimands, and explicit claim gates. Its verifier checks those structures, hashes, identities, and counts; it does not detect arbitrary per-security silent drops. A structured deviation log and receipt-reporting module is planned but unimplemented, so the current receipt does not claim to contain deviations. Proprietary rows are not redistributed; reviewers receive a lawful authorized-rerun or controlled-access path, public schemas and fixtures, and aggregate integrity evidence.

## What is new?

The project is not another China factor horse race. Gharghori and Nguyen (2026) already provide a pre-registered comparison of prominent factor models in China, while Liu, Stambaugh, and Yuan (2019) already use actual public-release dates in careful China factor construction. The proposed contribution is instead a specification-effect design intended for prospective registration: a paired estimate of the signed ROE timing decrement, transparent survivorship and timing transitions, and an order-invariant Shapley decomposition confined to a complete four-component implementation block.

The design joins information timing, survivorship, implementation constraints, all-cell reporting, and governance. It claims neither new factors nor implementability from the IC core.

The distinction between publication timing and data vintages is also substantive. Many studies use conservative lags but do not quantify the bias created by replacing actual publication dates with fiscal period ends. The proposed paired design measures that bias directly while refusing to infer a revision effect from a single-version export.

## So what?

If publication and implementation controls remove most familiar factor evidence, practitioner backtests that omit those controls may overstate measured cross-sectional predictability. If the evidence survives, the result identifies which registered specification changes matter least within the study's boundary and supplies a stronger measurement benchmark. Either outcome is informative because publication does not depend on a positive or statistically significant result.

The practical output is a reusable bias taxonomy and an executable IC audit protocol for A-share research. Portfolio implementation is a separately gated extension. The scientific output is a specification-effect decomposition that can later be compared across factors, periods, and markets under new registered protocols.

## Primary contribution

The paper contributes to empirical asset pricing by measuring the distance between naive and historically available factor evidence, rather than adding another factor to the anomaly zoo. It contributes to responsible finance research by making prior exposure, data feasibility, multiplicity, implementation, and negative outcomes part of the registered design.

## Other considerations

The principal risks are restricted-data review, incomplete 2010-2022 publication history, uninformative suspension fields, an unverified official SSE/SZSE session calendar, and release of the blind sample before journal authorization. These risks are explicit hard gates. The study will stop rather than shorten the target interval or weaken a threshold after outcomes are seen. The frozen plan core will be bound first by `design_manifest_v1`; the external registration receipt will bind that manifest hash; and only a later `execution_authorization` may permit blind-data release. The final plan envelope records those backward-pointing hashes without changing the registered core. A provider record without a verifiable digital signature requires named human verification and remains an explicit trust boundary. Planned reporting, portfolio, robustness, bootstrap, and interaction modules remain outside the current executable evidence until separately completed and frozen. The current repository has no software license, so the empirical submission does not describe the code as open source; licensing and any separate software-paper route require an owner decision.

## References

Faff, R. W. (2023). PBFJ Editorial: Engaging with responsible science - "Open for business" - launching the PBFJ pre-registration publication initiative. *Pacific-Basin Finance Journal, 79*, 101837. https://doi.org/10.1016/j.pacfin.2022.101837

Faff, R. W. (2026). PBFJ Editorial: Responsible and open science in action - an update on the PBFJ experiment and beyond. *Pacific-Basin Finance Journal, 96*, 103045. https://doi.org/10.1016/j.pacfin.2025.103045

Gharghori, P., & Nguyen, A. (2026). Which factors in China? A pre-registered study. *Pacific-Basin Finance Journal, 96*, 103012. https://doi.org/10.1016/j.pacfin.2025.103012

Hou, K., Xue, C., & Zhang, L. (2020). Replicating anomalies. *Review of Financial Studies, 33*(5), 2019-2133. https://doi.org/10.1093/rfs/hhy131

Liu, J., Stambaugh, R. F., & Yuan, Y. (2019). Size and value in China. *Journal of Financial Economics, 134*(1), 48-69. https://doi.org/10.1016/j.jfineco.2019.03.008

Novy-Marx, R., & Velikov, M. (2016). A taxonomy of anomalies and their trading costs. *Review of Financial Studies, 29*(1), 104-147. https://doi.org/10.1093/rfs/hhv063
