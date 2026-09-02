# Prior exposure log

**Study:** `a-share-factor-timing-bias-decomposition-v2`<br>
**Draft local date:** 1 September 2026; no final timezone-aware cutoff has been attested<br>
**Purpose:** Separate disclosed pilot knowledge from future registered evidence.

## People and tools exposed to pilot outcomes

- The repository owner and research team have access to the public pilot receipt and working paper.
- Codex was used to inspect the repository, audit the empirical design, modify code and tests, and draft the pilot paper and Stage-2 protocol.
- Any future submission must include an AI-assistance disclosure and confirm human review and responsibility.

## Data already accessed

- Daily quotes: 3 January 2023 through 24 July 2026.
- Stock master: current export containing historical list and delist dates.
- Fundamental factors: report periods from 2020Q1 through 2026Q2 and publication dates from 8 April 2020 through 24 July 2026.
- The data are licensed for local research and are not redistributed by the repository.

The current files contain no complete revision or vintage history. An `open` column exists, but the current declaration does not establish an unadjusted executable-price convention.

## Outcomes already observed

The team has observed all 16 cells in `evidence/pit_factor_replication_v1/receipt.json` and the corresponding 15-page working paper. In particular:

- ROE mean rank IC falls from 0.0461 under PIT membership/report-period timing to 0.0105 under publication-date timing.
- Composite mean rank IC falls from 0.0332 to 0.0038 across the same transition.
- Both means are negative under the pilot's bundled implementation variant.
- Momentum and low-volatility IC signs disagree with their top-quintile-minus-universe spread signs.

These values may motivate hypotheses but may not be counted as prospective confirmation.

## Specifications already explored or present in the repository

- Four pilot factors: ROE, 60-session momentum, 20-session low volatility, and a fixed 50/30/20 composite.
- Four cumulative pilot variants: naive, PIT universe, PIT publication, and bundled audited lag.
- Numerous non-confirmatory strategy templates and variants elsewhere in the repository.
- Existing synthetic execution experiments, walk-forward utilities, cost and audit modules.
- The ordered three-part ROE common-support decomposition, strict exact-endpoint rule, aggregate publication-exposure diagnostics, and endpoint-ledger integrity contract were added during a post-pilot design audit before any 2010-2022 Stage-2 factor or return outcome was released or inspected. Their origin must be disclosed as audit-driven rather than theory-only.

No later paper may imply that Stage-2 factors were selected without exposure to these alternatives.

The companion `prior_specification_inventory.json` records repository presence separately from known outcome exposure. Where run history cannot be established from durable evidence, the inventory says `unknown`; existence in source code is never treated as proof that a result was or was not viewed.

## Stage-2 isolation rule

The intended primary registered historical panel is fixed at January 2010 through December 2022, with a 2009 warm-up. Outcome rows may be held by an independent data custodian for hashing and outcome-blind coverage review, but they must not be released to the analysis team until the plan core is frozen, `design_manifest_v1` is externally timestamped, `registration_receipt_v1` is verified, and `execution_authorization` is signed. Before authorization, analysts may inspect schemas, rights, aggregate coverage, synthetic fixtures, and the disclosed pilot, but not Stage-2 factor outcomes.

An owner attestation that no 2010-2022 factor IC or return outcome has previously been inspected is still required before this boundary can be locked. If that attestation cannot be made, the study stops and a different protocol must be designed without consulting candidate-sample outcomes.

The January 2025-June 2026 pilot evaluation will be reported as a separate precondition sample; its source quote file begins in 2023. If either interval is also displayed within a long historical chart, the chart and tables must mark it as previously observed and primary inference must remain separately identifiable.

## Required event fields and chronology

Every exposure event added to the final log must contain a unique event identifier, timezone-aware `observed_at`, person or system identity, role, artifact path or external locator, artifact SHA-256 where bytes exist, exposure class, outcomes or metadata seen, affected sample dates, and consequence for the confirmatory boundary. `unknown` is required when durable evidence cannot establish exposure or non-exposure; blank fields and inferred execution histories are prohibited.

The final timestamps must satisfy:

`repository snapshot inspected_at <= inventory_cutoff_at <= inventory.generated_at <= prior_exposure_attestation.attested_at <= plan_core.design_frozen_at <= registration_receipt.registered_at <= registration_receipt.verified_at <= execution_authorization.authorized_at < first Stage-2 outcome access`.

All timestamps must be finite ISO-8601 values with explicit UTC offsets. The current date-only draft does not satisfy this gate and cannot enter the design manifest as a final attestation.

## Amendment rule

New exposure is appended with the required fields and its consequences for the confirmatory boundary. Existing finalized events are never deleted or rewritten after the inventory cutoff. A pre-authorization discovery requires a new inventory version, entries hash, prior-exposure attestation, plan-core hash, and design manifest; a discovery after registration invalidates the existing execution authorization and requires a recorded protocol disposition before any outcome access.
