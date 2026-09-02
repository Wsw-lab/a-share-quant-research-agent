# Stage-2 journal study

This directory holds the outcome-blind draft protocol for the proposed paper:

> **Report Dates, Publication Dates, and the A-Share ROE Signal: A Pre-Specified Historical Confirmation**

The existing `pit-factor-replication-v1` receipt is disclosed pilot evidence. It must not be relabeled as a prospective confirmation. The Stage-2 plan remains `draft_data_feasibility_pending` until a privacy-preserving coverage audit passes, data rights and the official calendar are documented, the plan core and code are frozen in a design manifest, the manifest receives an external timestamp or journal registration, that receipt is verified, and execution is separately authorized.

## Why the design is different

- The intended 2010-2022 rebalance panel precedes the observed 2025-2026 pilot evaluation, but its final 20-session horizon extends into January 2023 and overlaps the pilot file's raw market-date boundary; that exposure boundary is disclosed and requires a signed prior-exposure attestation before release.
- The prior bundled M3 is replaced by the complete 2^4 factorial of ST exclusion, suspension exclusion, a 20-session amount floor, and a one-session lag.
- Exact Shapley values allocate the full IC implementation effect while preserving interactions; order-invariance is claimed only within that four-component block.
- One primary outcome is fixed in advance: the mean publication-timing IC contrast for ROE, with a pilot-informed negative directional prediction and a two-sided test of a zero mean. The composite is secondary; momentum and low volatility are deterministic timing-isolation checks.
- The total ROE timing contrast is additionally split by an ordered three-part identity that permits non-nested supports: report-side support restriction, within-common-support record replacement, and publication-side support extension. The three components are non-directional secondary estimands, must add back to the primary monthly contrast within `1e-12`, and are not causal, revision, or vintage effects.
- Confirmatory inference contains exactly 29 estimands: one primary and a fixed 28-member Benjamini-Hochberg secondary family. The two timing-isolation checks and common-support efficiency identity are deterministic and separate. All 72 cell means, t-statistics, and top-minus-universe spreads are disclosed but descriptive only; they cannot support cell-specific discovery claims.
- The current IC core includes aggregate signal-missingness/common-support counts, no-return publication-exposure diagnostics, and a per-security endpoint-resolution ledger whose hash and aggregate reason counts are bound in the result receipt. Outcome availability never silently shrinks the signal-eligible denominator. Only exact adjusted-close quotes on the required official endpoints are currently supported; unresolved endpoints make the cell non-estimable and the study `INSUFFICIENT_EVIDENCE`. Next quotes, last prices, and default recoveries are forbidden, while suspension-valuation and delisting-terminal-wealth adapters remain unimplemented.
- Full per-security non-endpoint exclusion attribution, percentage attenuation, raw-ratio regressions, robustness analyses, structured deviation logging, portfolios, costs, nonfills, turnover, bootstrap intervals, interaction tests, and announcement-event/return-timing studies remain planned or excluded rather than claimed.
- With a single-version fundamental export, the strongest authorized accounting statement is a **recorded-publication-date specification effect**. The protocol does not identify the value investors observed at first release and prohibits revision, vintage-value, and announcement-reaction claims.

## Files

- `plan.draft.json` - machine-readable protocol; deliberately not locked.
- `execution_plan.template.json` - flat runner contract; its plan core is frozen before registration and its non-core envelope is completed only after authorization.
- `design_manifest.template.json` - non-self-referential manifest binding the frozen plan core, code, calendar, protocol, and gate artifacts.
- `registration_receipt.template.json` - external timestamp record binding the exact design-manifest hash.
- `external_registration_handoff.template.json` and `external_registration_handoff.md` - provider-neutral submission and independent-verification handoff; no external record is created by repository tooling.
- `execution_authorization.template.json` - final, non-circular authorization binding the manifest, registration receipt, frozen plan, and blind-data release boundary.
- `official_calendar/README.md` and `official_calendar/calendar.schema.json` - required common SSE/SZSE session-calendar input contract; no calendar data are included in the repository.
- `data_requirements.json` - minimum fields, coverage, rights, and vintage boundary.
- `data_review_attestation.template.json` - fail-closed human review of execution semantics, field informativeness, and rights.
- `data_acquisition_plan.md` - source decision matrix, exact Tushare/official-source field mapping, procurement sequence, and external blockers.
- `source_capability_matrix.json` - machine-readable, conservative provider capabilities; it is not a licence or evidence of acquisition.
- `data_rights_attestation.template.json` - dataset-level contract, storage, aggregate-reporting, calendar-publication, and private-ledger rights packet.
- `a_share_quant_agent.data_access` - outcome-blind metadata scanner and pure Tushare daily/calendar/actual-disclosure frame adapters; it makes no network calls and never authorizes Stage 2.
- `statistical_analysis_plan.md` - submission-grade research protocol and inference rules.
- `current_bundle_coverage.json` - retained pre-calendar three-file diagnostic; not valid under the current four-input execution gate.
- `current_bundle_gap_assessment.md` - interpretation of why that bundle is blocked for Stage 2.
- `prior_exposure_log.md` - record of outcomes already seen before Stage 2.
- `prior_specification_inventory.json` - machine-readable inventory of repository specifications and known/unknown outcome exposure.
- `prior_exposure_attestation.template.json` - owner/authorized-role declaration binding the clean 2010-2022 outcome boundary to the protocol and inventory hashes.
- `coverage_probe_spec.v1.json` - immutable historical probe design retained byte-for-byte and superseded prospectively; it must not be edited in place.
- `coverage_probe_spec.v2.json` - current outcome-blind probe design and claim boundary; publishing it does not authorize or imply execution.
- `coverage_probe_timestamp_proof.template.json` and `coverage_probe_rights_review.template.json` - explicit human evidence templates; null/draft values are deliberately rejected.
- `coverage_probe_receipt.v2.json` - required future canonical public receipt for the executed v2 probe; it must bind the exact spec hash and pre-execution external timestamp proof and report every fixed gate as passed. It does not yet exist in this repository.
- `a_share_quant_agent.coverage_probe` - fail-closed preflight, exact 24-cell provider probe, and public/private receipt verifier. It never reads factors or returns.
- `pbfj_phase1_eoi_draft.md` and `pbfj_phase2_pitch.md` - journal-pathway drafts; neither has been sent.
- `author_identity_package.private.template.json` - private completion checklist for names, affiliations, ORCID, correspondence, CRediT roles, funding, and conflicts; do not commit a populated copy without every author's approval.

Run the coverage audit before changing the plan status:

```bash
PYTHONPATH=src python3 -m a_share_quant_agent.study_v2_coverage \
  --quotes /authorized/path/daily_quotes.csv \
  --stock-master /authorized/path/stock_master.csv \
  --fundamentals /authorized/path/fundamentals.csv \
  --official-calendar /authorized/path/official_calendar.csv \
  --minimum-history-years 13 \
  --minimum-publish-date-rate 0.95 \
  --minimum-monthly-observations 156 \
  --minimum-symbols-per-month 1000 \
  --minimum-sessions-per-month 15 \
  --output /private/output/study_v2_coverage.json
```

The current bundle has zero quoted months inside the fixed 2010-2022 target, fails the 13-year/156-month design gate, and has no completed review attestation, so it is `BLOCKED_FOR_STAGE2`. Column presence alone never passes the execution, tradability, or rights gates. Because the verifiable receipt embeds the exact official-calendar session dates, the rights review must explicitly permit publication of those dates; this does not authorize publication of licensed quote or fundamental rows. After an authorized reviewer completes the attestation, pass it with `--review-attestation /private/path/review.json`; the public repository receives only its hash and non-identifying status, never the local path or licensed market rows.

Before that four-input audit, the metadata-only intake can be run without
factor or return inspection:

```bash
PYTHONPATH=src python3 -m a_share_quant_agent.data_access \
  --quotes /authorized/path/daily_quotes.csv \
  --stock-master /authorized/path/stock_master.csv \
  --fundamentals /authorized/path/fundamentals.csv \
  --official-calendar /authorized/path/official_calendar.csv \
  --rights-attestation /private/path/data_rights_attestation.json \
  --output /private/output/stage2_data_access_audit.json
```

This command records only file hashes, dimensions, date ranges, duplicate-key
counts, required-field non-null rates, and ST/suspension distinct values.  A
`pass_metadata_only` result is still not execution authorization; a human must
complete the review, external registration, and authorization chain.

The bounded coverage probe has its own three-command lifecycle. First obtain a
provider-controlled timestamp for the exact committed v2 specification and a
verified rights review (the two templates above are intentionally incomplete),
then run a no-network preflight:

```bash
PYTHONPATH=src python3 -m a_share_quant_agent.coverage_probe preflight \
  --spec studies/pit_factor_bias_decomposition_v2/coverage_probe_spec.v2.json \
  --prior-inventory studies/pit_factor_bias_decomposition_v2/prior_specification_inventory.json \
  --timestamp-proof /private/probe/timestamp-proof.json \
  --rights-review /private/probe/rights-review.json \
  --qdata-checkout /authorized/qdata-free-source-quant-research-db \
  --output-dir /private/probe/run-YYYYMMDD \
  --agent-commit <40-hex-commit> \
  --report /private/probe/preflight.json
```

Only a `READY` report permits `coverage_probe run`; it requests exactly the
12 registered symbols on the two registered dates (24 cells), in raw mode,
and publishes only aggregate counts and hashes. Provider failures produce a
redacted `BLOCKED` receipt; no output directory is reused. Verify a receipt
with `coverage_probe verify --receipt ... --artifact-root ... --spec ...` before
using it in the design manifest. A malformed or missing timestamp/rights file
causes the CLI to write an auditable `BLOCKED` preflight report and exit
nonzero; it can never be interpreted as authorization. This probe establishes
neither historical fundamentals nor any factor, return, IC, portfolio,
revision, or vintage result.

Pre-lock feasibility uses only outcome-blind aggregate coverage and review evidence. The requirement that all 72 registered cells contain at least 1,000 finite signal-outcome pairs in each of 156 months is a separate post-authorization evidence-status stop; so is the stricter requirement that every signal-eligible record have all required exact official-session endpoints resolved. Neither is evaluated as a factor outcome by the coverage audit, and neither can be used to inspect outcomes before registration.

`plan.draft.json` is a protocol source, not a runner input. It must not be made executable by changing only its `status`. The registration contract is deliberately non-circular:

1. Commit and externally timestamp `coverage_probe_spec.v2.json`, execute only its bounded outcome-blind scope, then complete the coverage and review gates, freeze the official calendar, complete the prior-specification inventory, and sign the prior-exposure attestation.
2. Materialize every plan-core field from `execution_plan.template.json`, set `design_frozen_at`, and compute `registered_content_sha256` over canonical plan content after excluding only `external_registration` and `locked_at`. No receipt or authorization exists at this point.
3. Create `design_manifest_v1`, which binds that exact plan-core hash plus the code, calendar, protocol, SAP, inventory, actual prior-exposure log, attestation, coverage, and rights-review hashes. It contains neither its own hash nor any later receipt.
4. Submit the exact design-manifest bytes or their SHA-256 digest to the external registration provider, then record the provider response in `registration_receipt_v1`.
5. Only after independently verifying that receipt may an authorized person create `execution_authorization`, which binds the manifest, receipt, plan core, calendar, and gate artifacts and permits release of the blind 2010-2022 outcome data.
6. Finally populate the non-core `external_registration` envelope with the three backward-pointing hashes and set `locked_at = execution_authorization.authorized_at`. Because the plan-core digest excludes only that later envelope and `locked_at`, this final packaging does not alter the registered design.

The `run-stage2` command therefore requires the actual prior-exposure log as `--prior-exposure-log`, in addition to its signed attestation, the externally timestamped v2 probe specification as `--coverage-probe-spec`, and its canonical passed public receipt as `--coverage-probe-receipt`. The runner recomputes all file hashes, validates the fixed probe scope and timestamp chronology, and requires the design manifest, registration receipt, execution authorization, and final result receipt to bind the same digests. Operators should also pass `--authorization-consumption-dir /private/custodian-controlled/store`; after every outcome-blind gate passes and before either quote or fundamental outcomes are loaded, the runner atomically creates `<authorization-sha256>.consumed.json` there. An existing marker fails closed, and a failed or interrupted claim remains consumed and requires a newly signed authorization.

Public verification is deliberately self-contained: `verify-stage2 --receipt receipt.json` checks the published receipt, its embedded hash-bound authorization-consumption record, aggregate endpoint metadata, and every public structural and statistical invariant without requiring either private sidecar. A custodian or reviewer with authorized private access can additionally pass `--authorization-consumption /private/store/<authorization-sha256>.consumed.json` and `--endpoint-ledger endpoint_reason_ledger.private.json`. The former checks the actual canonical marker, filename, hash, authorization, plan, scope, code, and chronology bindings; the latter checks ledger hash, canonical ordering, uniqueness, cardinality, and reason counts. The `status` command uses public verification only and therefore cannot prove that a private marker has not later been deleted.

The current runner accepts only the explicit human-verification evidence types in the maintained templates; it does not validate cryptographic signatures or registry inclusion proofs, and a cryptographic label alone cannot pass. Hashes establish artifact identity and integrity, but the authenticity of the provider timestamp rests on the retained provider record and a named human verifier. That human verification is an explicit trust boundary, not a cryptographic claim. A future cryptographic path requires a separately implemented and tested protocol. No external registration, execution authorization, or Stage-2 outcome run has been performed by these templates.

Real-data Stage-2 execution is additionally bound to Python 3.12.12, NumPy 2.0.2, and pandas 2.3.3 and requires a clean checked-out registered commit across the whole repository, including untracked files. The Python 3.10/3.11 fixture runs are portability checks only; they do not authorize a different registered runtime.

`execution_authorization` records the permitted study scope and verifies the registration chronology. The local runner now enforces one claim per authorization hash in one protected sidecar directory by exclusive file creation before outcome load; it does not provide a global nonce, external revocation service, cryptographic signature, or protection against a privileged custodian deleting/replacing that directory. The custodian must retain the private sidecar durably and reviewers should compare it with the receipt. External registration, independent provider-record review, human authorization, and lawful data access remain separate mandatory trust boundaries.
