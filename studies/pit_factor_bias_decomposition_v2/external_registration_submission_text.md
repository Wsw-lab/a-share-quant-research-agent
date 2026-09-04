# External Registration Submission Text

## Use condition

This provider-neutral text is ready for an external registration form only after the fixed coverage and rights review passes, the prior-exposure attestation is signed, the plan core is frozen, and the exact `stage2_design_manifest_v1` bytes exist. It does not represent a completed registration. The submitter must attach the exact manifest bytes or enter their exact SHA-256 digest without rewriting the manifest after submission.

## Registration title

Accounting Information Timing and the A Share ROE Signal

## Study description

This registration fixes a historical confirmation of how accounting-information timing and implementation conventions affect measured A-share factor evidence. The study asks how much of the monthly cross-sectional relation between return on equity and subsequent 20-official-session valuation returns remains when an accounting record becomes eligible only on a signal session strictly after its recorded publication date rather than at fiscal report-period end.

The study covers ordinary Shanghai and Shenzhen A-shares. The fixed rebalance interval is January 2010 through December 2022, with signal warm-up from January 2009 and required quote endpoints through January 2023. The historical listing universe, official common SSE and SZSE calendar, recorded report publication dates, contemporaneous ST and suspension states, turnover amount, and exact provider-recorded close observations are bound before execution. A single-version accounting export can identify a recorded-publication-date specification effect only. The study does not claim to reconstruct historical numerical vintages, revisions, first-release values, or the complete information set available to investors.

An already observed 2025-2026 pilot motivated the directional prediction. The pilot was not externally preregistered and is disclosed as prior evidence rather than independent confirmation. No pilot estimate enters the historical Stage-2 estimands.

The sole primary estimand is the mean paired monthly change in ROE Spearman rank information coefficient between the historical-universe recorded-publication specification and the historical-universe report-period specification. The pilot-informed directional prediction is negative; inference reports a two-sided test of a zero mean and a two-sided 95 percent confidence interval using Newey-West HAC with lag three.

The design fixes 28 secondary inferential estimands and applies Benjamini-Hochberg adjustment at false-discovery rate 0.10. Three of those estimands form an ordered common-support identity that separates report-side support restriction, record replacement among common securities, and publication-side support extension. Four A-share implementation components are crossed in a complete factorial: ST exclusion, suspension exclusion, a 20-session CNY 5 million amount floor, and a one-official-session return lag. Two report-end comparators plus the 16 implementation variants yield 18 variants and 72 factor-variant reporting cells across ROE, 60-session momentum, 20-session low volatility, and a fixed-weight composite. Every cell is reported; the 72 cell outputs are descriptive completeness outputs rather than 72 discovery tests. Momentum and low volatility serve as deterministic timing-isolation checks.

Coverage and semantics are reviewed without computing or exposing factor values, ranks, forward-return summaries, information coefficients, portfolio outcomes, test statistics, or variant comparisons. After this registration is independently verified, a separate human execution authorization must bind the registered manifest, registration receipt, plan-core hash, code commit, four raw-input hashes, coverage report, review attestation, prior-exposure evidence, data-rights evidence, and authorized release scope. Historical outcome execution remains prohibited until that authorization is complete and consumed by the registered runner.

The research code, schemas, deterministic fixtures, statistical analysis plan, fixed estimand inventory, and permitted aggregate outputs are intended for public review. Licensed rows, private contracts, local paths, credentials, signatures, restricted evidence, and the per-security endpoint ledger are not public. Public source identity, exact field mapping, official-calendar dates, file hashes, aggregate results, and controlled reviewer access are released only where the written rights packet expressly permits them.

If an exact required endpoint is absent, a required cell is non-estimable and the study receives `INSUFFICIENT_EVIDENCE`; the code may not chase a later quote, use a reopening quote, carry forward an unattested last price, assign a default recovery, shorten the sample, or select a better-performing variant. Negative, null, positive, mixed, sign-reversing, and infeasible outcomes remain reportable under the frozen design.

## Registration contents

The submitted record must contain or identify:

1. the exact `stage2_design_manifest_v1` file or its exact SHA-256 digest;
2. the study title and study ID `a-share-factor-timing-bias-decomposition-v2`;
3. the fixed scope of 18 variants, 72 factor-variant cells, one primary estimand, 28 secondary estimands, and two deterministic isolation checks;
4. the observed-pilot disclosure and single-version claim boundary;
5. the external provider's timezone-aware registration timestamp and immutable identifier; and
6. the access state selected for peer review, together with a provider-controlled record or view-only route that an independent verifier can inspect.

Do not upload licensed market rows, contracts, contact details, account information, credentials, private review evidence, or an authorization that has not yet been signed.

## Keywords

A-shares; return on equity; accounting-data availability; publication timing; backtest specification; pre-registration; specification effects

## Registration statement

The submitted manifest fixes the study design before the registered historical outcome analysis. The 2025-2026 pilot and all known prior specification exposure are disclosed. The 2010-2022 Stage-2 analysis has not been executed, and its release remains subject to separate data-custody authorization after independent verification of this external record.
