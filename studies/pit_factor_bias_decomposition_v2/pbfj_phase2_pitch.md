# PBFJ Phase-2 research pitch

## Working title

**Report Dates, Publication Dates, and the A-Share ROE Signal: A Pre-Specified Historical Confirmation**

## Basic research question

In a single-version provider snapshot, how much of the measured A-share ROE-return relation remains after the accounting signal is withheld until the first common official signal session strictly after its recorded report publication date?

## Key papers

Liu, Stambaugh, and Yuan (2019) establish market-specific construction and actual report-release dates in China. Gharghori and Nguyen (2026) provide the direct PBFJ benchmark: a pre-registered China factor-model comparison. Faff (2023, 2026) provides the responsible-science and hybrid pathway. Hou, Xue, and Zhang (2020) and Novy-Marx and Velikov (2016) motivate the replication and implementation boundaries.

## Motivation and puzzle

Asset-pricing results are sensitive to what a historical investor could know and trade. Public quantitative projects often combine final survivors, fiscal-period-end accounting values, contemporaneous returns, and selective reporting. Studying these choices separately obscures which specification change drives a result.

A disclosed pilot using 2023-2026 Shanghai and Shenzhen A-share data provides an empirical precondition. Across 18 evaluation cross-sections from January 2025 through June 2026, replacing report-period availability with publication-date availability reduces mean ROE rank IC from 0.0461 to 0.0105 and fixed-composite IC from 0.0332 to 0.0038. The pilot is too short and has already been observed, so it cannot answer the general question. It remains a separate precondition sample and will not enter the Stage-2 primary estimate.

## Core idea

The study separates two information-set transitions from four implementation components. First, it compares a fixed 31 January 2023 terminal-survivor set (`delistDate` null or strictly after that required outcome cutoff, conditional on listing by each historical signal session) with historical list/delist membership while holding report-period timing fixed. The cutoff does not move with data acquisition. Second, it changes only accounting availability from report-period end to publication date. Third, from the PIT-publication baseline, it runs the complete 2^4 factorial of ST exclusion, suspension exclusion, a 20-session CNY 5 million amount floor, and a one-session implementation lag. Provider-stable identifiers and a documented code-change map must link quotes, master, and fundamentals under one frozen contract; no revision-vintage claim follows.

The total ROE timing contrast is also decomposed by a three-part ordered identity that remains valid when report-side and publication-side signal supports are non-nested. It separates report-side support restriction, record replacement within their intersection, and publication-side support extension. These are arithmetic specification components rather than causal mechanisms, and their monthly sum must equal the total ROE contrast within absolute tolerance `1e-12`.

Within the four-component implementation block, the full factorial prevents the order in which those controls are added from determining their attribution. Exact Shapley values allocate that block's full implementation effect across the four components while distributing their interactions. The two information-set transitions remain explicitly ordered comparisons and are not described as order-invariant. Every factor-variant cell is reported; there is no best-model selection.

## Data

The Stage-2 target is a January 2010-December 2022 SH/SZ A-share outcome panel, including delisted securities, for which no factor return, IC, ranking, or variant outcome may be computed, released, or human-inspected before a signed exposure attestation, external registration, and custodian release authorization. It ends before the observed January 2025-June 2026 pilot evaluation. No reviewed delivery currently passes the complete historical, semantic, and rights gates, and no historical factor-return panel has been assembled. Automated pre-lock validators may parse numeric bytes only to verify schema, finiteness, dates, identifiers, exact endpoint presence, and permitted aggregate coverage; they may not calculate or reveal a research outcome. The IC core requires documented provider close-observation and adjustment semantics, `close_observation_type`, amount, ST and suspension state, list/delist dates, publication-dated ROE, and lawful research, aggregate-reporting, hash-publication, and controlled-review rights. A non-suspended observation must be `traded_close`; a suspended observation must be a `suspension_valuation` recorded or published by the supplier for that exact official session, never a researcher-generated carry-forward. Unadjusted open, point-in-time capitalization, price-limit, and other execution fields belong to the planned portfolio extension.

A locally retained pilot export is described as licensed in the legacy repository record and remains the already-observed pilot evidence; it cannot satisfy the blind Stage-2 historical requirement. The publication basis for legacy provider-derived hashes and aggregates, and any controlled-review permission, must be reviewed separately with the licensor or authorized institutional administrator rather than inferred from the new Stage-2 form. If the full 2010-2022 panel fails any outcome-blind coverage, publication-date, membership, endpoint, rights, or code gate, the study stops rather than selecting a shorter feasible interval after outcomes are seen. In a single-version export, the recorded publication date supports only a recorded-publication-date specification effect. It does not identify the value investors observed at first release, and revision, vintage-value, restatement, announcement-reaction, and return-timing claims remain prohibited.

## Tools and method

The sole primary estimand is the mean paired monthly ROE rank-IC contrast when accounting eligibility moves from report-period end to the recorded report publication date within the historical listing universe: `IC(publication date) - IC(report-period end)`. The pilot-informed directional prediction is `E[d_t] < 0`, while inference tests the two-sided null `H0: E[d_t] = 0` and reports a Newey-West HAC interval and p-value. Because there is one primary estimand, no primary multiplicity adjustment is used.

The fixed-weight composite timing difference is secondary. Momentum and low-volatility timing differences are pre-specified deterministic isolation checks proposed for registration because their signals do not use accounting publication dates; nonzero differences indicate an implementation-isolation failure rather than new factor evidence. The proposed inferential set contains exactly 29 estimands: the sole primary plus a secondary family of exactly 28 p-values—one composite timing contrast, eight paired IC contrasts covering membership and the full implementation effect for four factors, sixteen component-by-factor IC Shapley estimates, and the three non-directional ROE common-support components. Benjamini-Hochberg controls that family at FDR 0.10. The two isolation checks and the common-support efficiency identity sit outside that inferential count.

The current IC-core contract produces the complete cell matrix, paired IC estimands, HAC inference, exact IC Shapley values, the ordered ROE common-support decomposition, aggregate signal-missingness/support counts, and publication-exposure diagnostics that use no forward returns. The 72 cell means, t-statistics, and top-minus-universe spreads are reported as descriptive completeness outputs only and cannot support cell-specific discovery claims. Exact provider-recorded traded closes and attested supplier-recorded/published same-session suspension valuations resolve required official-session endpoints; the research code never forward-fills a valuation. The resulting returns and rank ICs are valuation diagnostics, not executable trade-return evidence. The signal-eligible denominator is fixed before outcome lookup; any unresolved endpoint makes its cell non-estimable and the study `INSUFFICIENT_EVIDENCE`. The code may not move to a later quote, use an unattested last price, or assign a default recovery. The result receipt binds the private per-security endpoint-reason ledger by hash and publishes aggregate counts. The delisting-terminal-wealth adapter, suspension execution/fill assumptions, full non-endpoint exclusion attribution, percentage attenuation, raw-ratio regressions, robustness analyses, next-open portfolios, costs, nonfills, stationary bootstrap intervals, factorial interactions, and announcement-event/return-timing studies remain excluded. The 18-variant, 72-cell design remains blocked if the supplier cannot prove same-session suspension-valuation provenance; only before external registration and any Stage-2 outcome access may a prospective re-frozen suspension-off amendment use 10 variants and 40 cells. Shapley values preserve interactions in the allocation but are not formal interaction tests.

For the implemented IC core, the canonical receipt binds the plan-core hash, code revision, declared raw-file hashes, sample coverage, the registered variant/factor lattice, implemented result cells and estimands, common-support efficiency, aggregate missingness/support diagnostics, aggregate endpoint reason counts, the complete private endpoint-ledger hash, and explicit claim gates. Public verification checks the receipt's structure, hashes, aggregate accounting, and claim gates without requiring proprietary rows. In an explicit controlled-audit mode, an authorized verifier supplied with the private ledger additionally checks complete per-record ledger coverage and its binding hash; a structured deviation log remains planned and unimplemented. Proprietary rows are not redistributed; reviewers receive a lawful authorized-rerun or controlled-access path, public schemas and fixtures, and aggregate integrity evidence.

## What is new?

The project is not another China factor horse race. Gharghori and Nguyen (2026) already provide a pre-registered comparison of prominent factor models in China, while Liu, Stambaugh, and Yuan (2019) already use actual public-release dates in careful China factor construction. The proposed contribution is instead a specification-effect design intended for prospective registration: a paired estimate of the signed ROE timing decrement, an exact three-part separation of report support, common-support record replacement, and publication support, transparent survivorship and timing transitions, and an order-invariant Shapley decomposition confined to a complete four-component implementation block.

The central contribution is the paired ROE timing effect and its exact separation into support restriction, record replacement, and support extension. Survivorship, implementation constraints, all-cell reporting, and governance make that result interpretable and auditable; they are supporting design features rather than separate claims of financial novelty. The study claims neither new factors nor implementability from the IC core.

The distinction between publication timing and data vintages is also substantive. Many studies use conservative lags but do not quantify the specification change created by replacing recorded publication dates with fiscal period ends. The proposed paired design measures that snapshot-based timing displacement and refuses to relabel it as the investor's historical value, a revision effect, or an announcement reaction.

## So what?

If publication and implementation controls remove most familiar factor evidence, practitioner backtests that omit those controls may overstate measured cross-sectional predictability. If the evidence survives, the result identifies which registered specification changes matter least within the study's boundary and supplies a stronger measurement benchmark. Either outcome is informative because publication does not depend on a positive or statistically significant result.

The practical output is a reusable bias taxonomy and an executable IC audit protocol for A-share research. Portfolio implementation is a separately gated extension. The scientific output is a specification-effect decomposition that can later be compared across factors, periods, and markets under new registered protocols.

## Primary contribution

The paper contributes to empirical asset pricing by measuring how much of the A-share ROE signal depends on admitting an accounting record before its stored publication date, then showing whether the change comes from different security support or a different record for the same security. The factorial implementation audit and registration chain support the credibility of that answer rather than substitute for the economic contribution.

## Other considerations

The principal risks are restricted-data review, incomplete 2010-2022 publication history, uninformative suspension fields, an unverified official SSE/SZSE session calendar, and release of the blind sample before external registration plus custodian release authorization. These risks are explicit hard gates. The study will stop rather than shorten the target interval or weaken a threshold after outcomes are seen. The frozen plan core will be bound first by `design_manifest_v1`; the external registration receipt will bind that manifest hash; and only a later `execution_authorization` issued by an authorized data custodian may permit blind-data release. This local authorization records a post-registration custody decision, not journal or editor acceptance. The final plan envelope records those backward-pointing hashes without changing the registered core. The current runner accepts only a named human verifier and hash-bound provider record as an explicit trust boundary; it does not validate a cryptographic signature or inclusion-proof label. Planned reporting, portfolio, robustness, bootstrap, and interaction modules remain outside the current executable evidence until separately completed and frozen. Original repository code and documentation are released under the MIT License; that license does not grant rights to proprietary market data or third-party materials.

## References

Faff, R. W. (2023). PBFJ Editorial: Engaging with responsible science - "Open for business" - launching the PBFJ pre-registration publication initiative. *Pacific-Basin Finance Journal, 79*, 101837. https://doi.org/10.1016/j.pacfin.2022.101837

Faff, R. W. (2026). PBFJ Editorial: Responsible and open science in action - an update on the PBFJ experiment and beyond. *Pacific-Basin Finance Journal, 96*, 103045. https://doi.org/10.1016/j.pacfin.2025.103045

Gharghori, P., & Nguyen, A. (2026). Which factors in China? A pre-registered study. *Pacific-Basin Finance Journal, 96*, 103012. https://doi.org/10.1016/j.pacfin.2025.103012

Hou, K., Xue, C., & Zhang, L. (2020). Replicating anomalies. *Review of Financial Studies, 33*(5), 2019-2133. https://doi.org/10.1093/rfs/hhy131

Liu, J., Stambaugh, R. F., & Yuan, Y. (2019). Size and value in China. *Journal of Financial Economics, 134*(1), 48-69. https://doi.org/10.1016/j.jfineco.2019.03.008

Novy-Marx, R., & Velikov, M. (2016). A taxonomy of anomalies and their trading costs. *Review of Financial Studies, 29*(1), 104-147. https://doi.org/10.1093/rfs/hhv063
