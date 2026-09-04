# Stage-2 journal study

This directory holds the outcome-blind draft protocol for the proposed paper:

> **Report Dates, Publication Dates, and the A-Share ROE Signal: A Pre-Specified Historical Confirmation**

The existing `pit-factor-replication-v1` receipt is disclosed pilot evidence. It must not be relabeled as a prospective confirmation. Its provider-derived source label, hashes, sizes, aggregate counts, and results are legacy-public facts whose publication and controlled-review basis has not been re-attested by the new Stage-2 rights packet; continued hosting or remediation requires separate licensor or authorized institutional-administrator review. The Stage-2 plan remains `draft_data_feasibility_pending` until the private authoritative coverage audit passes, data rights and the official calendar are documented, the plan core and code are frozen in a design manifest, the manifest receives an external timestamp or journal registration, that receipt is verified, and execution is separately authorized.

The execution surface is intentionally asymmetric. The legacy `run` command
accepts only `synthetic_fixture`; it can verify old v1 receipts but cannot
create a new real-market receipt. Only the immutable repository pilot whose
complete receipt bytes match the fixed historical SHA-256 allowlist can retain
the v1 real-market label in public status; another structurally valid v1
envelope contributes only `INSUFFICIENT_EVIDENCE`, even if its self-asserted
integrity field was recomputed. New real-market outcomes have exactly one
supported entry point: the `run-stage2` orchestrator after it validates the
complete registration and rights chain and atomically consumes the one-use
authorization. The lower-level cell executor is a private deterministic test
helper and is not an alternative execution route.

The public Stage-2 result receipt contains the fixed four-role projection from
the private data declaration. For each role, the private rights packet repeats
the exact source name and complete canonical-to-provider field map and binds
that projection by canonical SHA-256. The declaration must match those four
authorized projections byte-for-byte after canonical JSON serialization;
generic statements such as `approved` cannot stand in for a field map.
Consequently,
`source_identity_publication_permitted` and
`field_mapping_citation_permitted` must both be `true` for every required
dataset; either denial blocks Stage 2 under this design.

## Why the design is different

- The intended 2010-2022 rebalance panel precedes the observed 2025-2026 pilot evaluation, but its final 20-session horizon extends into January 2023 and overlaps the pilot file's raw market-date boundary; that exposure boundary is disclosed and requires a signed prior-exposure attestation before release.
- The prior bundled M3 is replaced by the complete 2^4 factorial of ST exclusion, suspension exclusion, a 20-session amount floor, and a one-session lag.
- Exact Shapley values allocate the full IC implementation effect while preserving interactions; order-invariance is claimed only within that four-component block.
- One primary outcome is fixed in advance: the mean publication-timing IC contrast for ROE, with a pilot-informed negative directional prediction and a two-sided test of a zero mean. The composite is secondary; momentum and low volatility are deterministic timing-isolation checks.
- The total ROE timing contrast is additionally split by an ordered three-part identity that permits non-nested supports: report-side support restriction, within-common-support record replacement, and publication-side support extension. The three components are non-directional secondary estimands, must add back to the primary monthly contrast within `1e-12`, and are not causal, revision, or vintage effects.
- Confirmatory inference contains exactly 29 estimands: one primary and a fixed 28-member Benjamini-Hochberg secondary family. The two timing-isolation checks and common-support efficiency identity are deterministic and separate. All 72 cell means, t-statistics, and top-minus-universe spreads are disclosed but descriptive only; they cannot support cell-specific discovery claims.
- The current IC core includes aggregate signal-missingness/common-support counts, no-return publication-exposure diagnostics, and a per-security endpoint-resolution ledger whose hash and aggregate reason counts are bound in the result receipt. Outcome availability never silently shrinks the signal-eligible denominator. Every quote row must identify either a `traded_close` for a non-suspended security or a supplier-recorded/published same-session `suspension_valuation` for a suspended security; research code never forward-fills one. These provider-close returns and rank ICs are valuation diagnostics, not executable trade returns. Unresolved endpoints make the cell non-estimable and the study `INSUFFICIENT_EVIDENCE`; next quotes, reopening prices, researcher-created last prices, and default recoveries are forbidden, while the delisting-terminal-wealth adapter remains unimplemented.
- A0 is a fixed terminal-survivor comparator, not an extraction-current list. At each historical signal session it requires listing by that session and retains a security only when `delistDate` is null or strictly after 2023-01-31, the fixed required quote/outcome cutoff. Quotes, stock master, and fundamentals must share the reviewed identifier token `provider_stable_exchange_qualified_security_identifier_with_reviewed_code_change_mapping_v1`; the provider definition and every historical code-change/reassignment mapping are separately hash-bound without creating a vintage claim.
- Descriptive tail groups use average percentile ranks, bottom `<= 0.2`, and top `> 0.8`. Equal signal values stay together, so tie-spanning groups may differ from 20%; 1,000 distinct values yield 200 observations in each tail.
- Full per-security non-endpoint exclusion attribution, percentage attenuation, raw-ratio regressions, robustness analyses, structured deviation logging, portfolios, costs, nonfills, turnover, bootstrap intervals, interaction tests, and announcement-event/return-timing studies remain planned or excluded rather than claimed.
- With a single-version fundamental export, the strongest authorized accounting statement is a **recorded-publication-date specification effect**. The protocol does not identify the value investors observed at first release and prohibits revision, vintage-value, and announcement-reaction claims.

## Files

- `plan.draft.json` - machine-readable protocol; deliberately not locked.
- `execution_plan.template.json` - flat runner contract; its plan core is frozen before registration and its non-core envelope is completed only after authorization.
- `data_declaration.template.json` - private exact-schema declaration. A populated copy stays outside Git; only its fixed public projection and exact private-file hash may enter the result receipt.
- `design_manifest.template.json` - non-self-referential manifest binding the frozen plan core, code, calendar, protocol, and gate artifacts.
- `registration_receipt.template.json` - external timestamp record binding the exact design-manifest hash.
- `external_registration_handoff.template.json` and `external_registration_handoff.md` - provider-neutral submission and independent-verification handoff; no external record is created by repository tooling.
- `external_registration_submission_text.md` - paste-ready provider-neutral study description for a future registry record; it remains unusable until the exact frozen manifest exists.
- `registration_and_authorization_runbook.md` - field-by-field chronology for manifest freeze, external submission, independent verification, registration receipt, execution authorization, and the final non-core envelope.
- `execution_authorization.template.json` - final, non-circular authorization binding the manifest, registration receipt, frozen plan, and blind-data release boundary.
- `official_calendar/README.md` and `official_calendar/calendar.schema.json` - required common SSE/SZSE session-calendar input contract; no calendar data are included in the repository.
- `data_requirements.json` - minimum fields, coverage, rights, and vintage boundary.
- `data_review_attestation.template.json` - fail-closed human review of execution semantics, complete non-latest-only historical membership, actual recorded publication-date/ROE mapping, field informativeness, and rights.
- `data_acquisition_plan.md` - source decision matrix, exact Tushare/official-source field mapping, procurement sequence, and external blockers.
- `stage2_data_procurement_request.md` - provider-neutral bilingual capability, quotation, and rights request; it requests no result-bearing sample rows.
- `provider_outreach_dispatch_checklist.md` - first-contact routing, attachment, reply-rejection, private dispatch-record, and post-response intake checklist.
- `provider_information_boundary.md` - three-level disclosure rule: neutral protocols and blank forms are public; targeted outreach and negotiation records stay outside Git; contracts, contacts, accounts, credentials, and licensed data are never public.
- `provider_rights_confirmation_form.md` - provider or licensed-institution yes/no confirmation for aggregate publication, hashes, calendar dates, controlled review, and private-ledger rights.
- `provider_capability_and_field_mapping.template.xlsx` - public blank response workbook. Before filling it, save a renamed `.completed.xlsx` copy outside every Git worktree; never overwrite the tracked template.
- `private_data_handoff_instructions.md` and `private_handoff_manifest.template.json` - encrypted delivery, immutable closed-file-set, hashing, access-separation, and private evidence controls.
- `provider_delivery_acceptance_receipt.template.json` - optional private post-audit custody record binding the immutable delivery-manifest, metadata-audit, review-attestation, and coverage-report hashes; it is not a formal gate or design-manifest input.
- `provider_delivery_acceptance_protocol.md` - optional outcome-blind operational checklist for the actual contracted delivery, explicitly separate from both the formal bound coverage/review gates and the AKShare/QData 24-cell probe.
- `source_capability_matrix.json` - machine-readable, conservative provider capabilities; it is not a licence or evidence of acquisition.
- `data_rights_attestation.template.json` - dataset-level contract, storage, aggregate-reporting, calendar-publication, and private-ledger rights packet.
- `a_share_quant_agent.data_access` - outcome-blind metadata scanner and pure Tushare daily/calendar/actual-disclosure frame adapters; it makes no network calls and never authorizes Stage 2.
- `coverage_execution_and_acceptance_runbook.md` - operator procedure for the existing metadata audit and authoritative fixed-design coverage script, including the exact acceptance matrix and outcome-blind stop rules.
- `prespecified_results_tables.md` - fixed pre-results reporting supplement containing the one primary row, all 28 secondary rows, both deterministic checks, exposure diagnostics, endpoint-completeness fields, and all 72 descriptive factor-variant cells.
- `statistical_analysis_plan.md` - submission-grade research protocol and inference rules.
- `current_bundle_gap_assessment.md` - non-identifying explanation of why locally available sources remain blocked for Stage 2. The earlier real-data coverage report is intentionally absent from the current public tree pending explicit aggregate/hash publication rights.
- `prior_exposure_log.md` - record of outcomes already seen before Stage 2.
- `prior_specification_inventory.json` - machine-readable inventory of repository specifications and known/unknown outcome exposure. The checked-in public file deliberately remains `draft_incomplete_not_manifest_eligible` and is not a gate artifact. Its populated successor must first live with `coverage_probe_spec.v2.json` in a private, unpushed local preregistration commit, with non-null preparer/timestamp fields, a valid entries hash, and `manifest_eligible_outcome_blind`; the external timestamp binds that commit and those exact bytes. Until an authorized decision explicitly publishes that commit, the current public draft must not be described as the finalized inventory.
- `prior_exposure_attestation.template.json` - owner/authorized-role declaration binding the clean 2010-2022 outcome boundary to the protocol and inventory hashes.
- `coverage_probe_spec.v1.json` - immutable historical probe design retained byte-for-byte and superseded prospectively; it must not be edited in place.
- `coverage_probe_spec.v2.json` - current outcome-blind probe design and claim boundary; publishing it does not authorize or imply execution.
- `coverage_probe_timestamp_package.template.json`, `coverage_probe_timestamp_proof.template.json`, and `coverage_probe_rights_review.template.json` - the canonical timestamp package binds the exact spec hash, prior-inventory hash, and containing Agent commit; the proof must timestamp that package. The v3 rights review must approve the exact raw proof-file SHA-256, carry timezone-aware contract effective/expiry evidence, and separately cover every public metadata/identity field. A finite-expiry record must also hash-bind a clause preserving private probe-artifact retention and continued availability of the already-published aggregate receipt/metadata after expiry. A null expiry passes only with affirmative no-expiry confirmation, false post-expiry booleans, and a null survival-evidence hash; draft or contradictory values are rejected.
- `coverage_probe_receipt.v2.json` - required future canonical public receipt for the executed v2 probe; it must embed the bound timestamp package and proof, the exact rights-review SHA-256, observed request route, explicit publication-consent boundary, and every passed gate. It does not yet exist in this repository.
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

This authoritative report is private rights-controlled evidence: it contains
exact input hashes, byte sizes, and detailed aggregate coverage. Its `--output`
must be a new file outside **every** Git worktree, including an unrelated or
linked checkout and the QData checkout. The CLI publishes complete canonical
bytes atomically with mode `0600` and never overwrites an existing entry. A
separate rights-reviewed public-export command is not implemented; do not copy
this report into Git merely because it contains no raw rows.

No reviewed delivery currently passes the fixed 13-year/156-month gate together
with the required field, provenance, and rights checks, so the study remains
`BLOCKED_FOR_STAGE2`. Column presence alone never passes the execution,
supplier-recorded suspension-valuation, tradability, or rights gates. Because the verifiable receipt embeds the exact
official-calendar session dates, the rights review must explicitly permit
publication of those dates; this does not authorize publication of licensed
quote or fundamental rows. After an authorized reviewer completes the
attestation, pass it with `--review-attestation /private/path/review.json`; the
public repository receives only its hash and non-identifying status, never the
local path or licensed market rows.

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

`--output` is mandatory because this diagnostic includes exact hashes, byte
sizes, counts, and date extrema. It uses the same new-file, outside-every-Git-
worktree, atomic mode-`0600`, no-overwrite contract as the authoritative
coverage report and never prints the payload to stdout. A redacted public
export is not implemented.

This command emits an aggregate-only diagnostic of exact file hashes, CSV
structure, malformed or duplicate keys, required-field completeness, date
ranges and ordering, numeric typing, ST/suspension typing and informativeness,
exact close-observation-type mapping,
listing/delisting lifecycle coherence, exchange scope, and the supplied rights
attestation. It necessarily parses raw numeric fields for those fixed
integrity tests, but it does not compute, retain, release, or human-display
factor returns, signal rankings, ICs, portfolios, test statistics, or variant
orderings. A
`pass_metadata_only` result is diagnostic only: it is not a formal readiness
gate or execution authorization, and a human must still complete the
authoritative coverage review, external registration, and authorization chain.

The bounded coverage probe has its own three-command lifecycle. First audit a
pre-inventory Git base snapshot, complete every inventory identity and
timezone-aware chronology field, verify its canonical entries hash, and set its
status to `manifest_eligible_outcome_blind`. The inventory's
`repository_snapshot.head_commit` names that already-existing audited base; it
must be an ancestor of the later commit containing the finalized inventory and
v2 spec. It cannot equal a self-embedded future commit id. Commit the exact
final inventory and v2 spec in a descendant commit, then populate the canonical
timestamp package with their exact hashes and that containing Agent commit.
Obtain a provider-controlled timestamp only after inventory generation, have it
independently verified, and complete a verified v3 rights review that names the
exact raw timestamp-proof SHA-256 and contract term. For finite terms it must
also bind the post-expiry retention/publication-survival clause; for an
affirmatively non-expiring term the post-expiry fields remain false/null (the
templates are intentionally incomplete). Then run a no-network preflight:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m a_share_quant_agent.coverage_probe preflight \
  --spec studies/pit_factor_bias_decomposition_v2/coverage_probe_spec.v2.json \
  --prior-inventory studies/pit_factor_bias_decomposition_v2/prior_specification_inventory.json \
  --timestamp-package /private/probe/timestamp-package.json \
  --timestamp-proof /private/probe/timestamp-proof.json \
  --rights-review /private/probe/rights-review.json \
  --qdata-checkout /authorized/qdata-free-source-quant-research-db \
  --output-dir /private/probe/run-YYYYMMDD \
  --agent-commit <40-hex-commit> \
  --report /private/probe/preflight.json
```

Only a `READY` report permits `coverage_probe run`; it requests exactly the
12 registered symbols on the two registered dates (24 cells), in raw mode,
through the dedicated `ExactDateAkShareProbeAdapter`. That adapter does not
import or call QData: it verifies the pinned AkShare module bytes, allows only
one `stock_zh_a_hist` HTTPS request per cell with `start_date=end_date`, disables
redirects, and fails closed on any fallback, lookback, other endpoint, or
unobserved final host. The actual response host determines the recorded
upstream identity. The QData checkout remains a clean, hash-bound historical
provenance input only. Provider failures produce a
redacted `BLOCKED` receipt; the private `--output-dir` must be new and outside
every Git worktree before the first provider request, and no output directory
is reused. Verify a receipt
with `coverage_probe verify --receipt ... --artifact-root ... --spec ...` before
using it in the design manifest. A malformed or missing timestamp/rights file
causes the CLI to write an auditable `BLOCKED` preflight report and exit
nonzero; it can never be interpreted as authorization. This probe establishes
neither historical fundamentals nor any factor, return, IC, portfolio,
revision, or vintage result. The public receipt exposes artifact hashes,
filenames, sizes, row counts, symbol/date-range summaries, route metadata, and
timestamp verifier/URI only when the rights review separately approves each
category; approval of generic “aggregate publication” alone cannot pass.
The runner checks that the contract was effective by the review and remains
active at preflight, immediately before the first provider request, and again
immediately before receipt publication. A finite expiry before any checkpoint,
missing hash-evidenced post-expiry private-retention or continued-publication
rights, an unconfirmed or contradictory null expiry, a substituted proof file,
or a substituted rights review stops fail closed without a receipt. The public
receipt and private manifest both bind the same exact rights-review SHA-256.
The completed staging directory is published only through the operating
system's atomic exclusive no-replace rename. A racing file, symlink, or empty
directory at the destination is preserved and the probe fails closed.
Missing coverage is public only as a total count and failures only as category
counts. Exact failed symbol-date identities remain in the hash-bound private
request log; `coverage_probe verify --artifact-root ...` reconciles that log
against the public aggregates without publishing it. Before any request and
again before receipt publication, a recursive public-surface lint rejects
credential-like keys or URL queries, URL user information, unsafe local URLs,
file URIs, and absolute local paths without echoing the rejected value.

Pre-lock feasibility uses only outcome-blind aggregate coverage and review evidence. The monthly candidate set is the intersection of lifecycle-eligible A-share master identifiers and identifiers carrying a provider close observation on the exact signal session. Every such candidate—not merely 1,000 of them—must have exact `t`, `t+1`, `t+20`, and `t+21` rows, so the exact-endpoint count equals the candidate count in every target month. Both close-observation types must occur among those fixed signal-session candidates, and a human attestation must bind evidence that suspension valuations were supplier-recorded or published for the exact session. The registered coverage gate separately requires at least 1,000 identifiers per month to satisfy the complete exact-session quote-history contract. The requirement that all 72 registered cells contain at least 1,000 finite signal-outcome pairs in each of 156 months is a separate post-authorization evidence-status stop; so is the requirement that every signal-eligible record have all required exact official-session endpoints resolved. Neither is evaluated as a factor outcome by the coverage audit, and neither can be used to inspect outcomes before registration.

Conditional rights are machine-bound one-to-one, not accepted as free text.
Each restriction has a unique `restriction_id`, its exact dataset permission
field, and a description; exactly one satisfied review must repeat that ID and
permission and bind a review timestamp and evidence hash. Missing, duplicate,
unknown, permission-mismatched, or false-permission mappings fail closed. The
tracked attestation remains an unfilled template and supplies no rights by
itself.

The 18-variant, 72-cell design remains the target. If the supplier cannot prove same-session suspension-valuation provenance, the status stays `BLOCKED_FOR_STAGE2`. Only before external registration and before any Stage-2 outcome access may a newly timestamped amendment remove all suspension-component factorial variants, leaving 10 variants and 40 cells and requiring a complete re-freeze of the SAP, plan, manifest, estimand/multiplicity inventory, and authorization. That fallback is unavailable after registration or outcome access.

`plan.draft.json` is a protocol source, not a runner input. It must not be made executable by changing only its `status`. The registration contract is deliberately non-circular:

1. Complete the outcome-blind prior-specification inventory against an audited pre-inventory base commit; set it to `manifest_eligible_outcome_blind`; commit those exact bytes and `coverage_probe_spec.v2.json` in a descendant commit; create and externally timestamp the canonical package manifest binding both hashes and that containing Agent commit; independently verify it before execution; execute only the bounded outcome-blind scope; then complete the coverage and review gates, freeze the official calendar, and sign the prior-exposure attestation. The same inventory bytes remain immutable downstream: the plan and design manifest bind their exact hash, while the audited base commit must be an ancestor of both the probe commit and the later plan code commit.
2. Complete the private exact-schema data declaration and every fixed-public-projection consent field. Its `dataset_source_mappings` object must contain exactly the four required roles and exactly every canonical field for each role. Complete the v2 private rights packet with the identical per-role projections and their canonical SHA-256 hashes; validation rejects a swapped role, omitted or extra field, generic compliance word, hash mismatch, or any difference between rights and declaration. Then hash both the exact private declaration bytes and the canonical allowlisted projection. Keep both populated private artifacts outside Git. These identities must exist before any plan-core field that refers to them is materialized.
3. Materialize every plan-core field from `execution_plan.template.json`, including the already-computed declaration hash and all preceding gate-artifact identities; set `design_frozen_at`; and compute `registered_content_sha256` over canonical plan content after excluding only `external_registration` and `locked_at`. No manifest, receipt, or authorization exists at this point.
4. Create `design_manifest_v1`, which binds that exact plan-core hash plus the code, calendar, protocol, SAP, inventory, actual prior-exposure log, attestation, coverage, rights-review hashes, the already-computed data-declaration public-projection hash, and the official-calendar session-list projection hash. It contains neither its own hash nor any later receipt.
5. Submit the exact design-manifest bytes or their SHA-256 digest to the external registration provider, then record the provider response in `registration_receipt_v1`.
6. Only after independently verifying that receipt may an authorized person create `execution_authorization`, which binds the manifest, receipt, plan core, calendar, and gate artifacts and permits release of the blind 2010-2022 outcome data. The completed manifest, registration receipt, and authorization must each independently approve their exact public-receipt embedding scope and all fixed privacy assertions.
7. Finally populate the non-core `external_registration` envelope with the three backward-pointing hashes and set `locked_at = execution_authorization.authorized_at`. Because the plan-core digest excludes only that later envelope and `locked_at`, this final packaging does not alter the registered design.

The `run-stage2` command therefore requires the actual prior-exposure log as `--prior-exposure-log`, in addition to its signed attestation, the externally timestamped v2 probe specification as `--coverage-probe-spec`, and its canonical passed public receipt as `--coverage-probe-receipt`. The supported command prefix is exactly `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m a_share_quant_agent.confirmatory_study run-stage2`; bytecode suppression must be active when Python starts, and the CLI rejects a real Stage-2 invocation without it. This prevents module import from creating an ignored `__pycache__` entry before the whole-repository clean check. Before authorization consumption, the runner recomputes only control-artifact hashes, validates the fixed probe scope and timestamp chronology, and cross-checks that the raw-input hashes declared by the locked plan, coverage report, review, manifest, and authorization chain agree; it does not open or hash the four raw inputs at that stage. Operators must pass both a fresh `--output-dir /private/results/run-id` and an explicit `--authorization-consumption-dir /private/custodian-controlled/store`. Before any authorization claim, the runner starts from each target's nearest existing parent and uses Git's worktree/common-directory identity to reject either path if it resolves inside any Git worktree, including an unrelated repository, linked checkout, QData checkout, or ignored in-repository directory. After every outcome-blind gate passes and before either quote or fundamental outcomes are loaded, the runner atomically creates `<authorization-sha256>.consumed.json` in the protected consumption directory. An existing marker fails closed, and a failed or interrupted claim remains consumed and requires a newly signed authorization. After consumption, each raw input is captured exactly once and its digest is checked against the registered declarations; coverage recomputation, panel loaders, and receipt input evidence reuse those bytes rather than reopening mutable paths. A mismatch leaves the authorization consumed and publishes no result. A finite rights expiry is checked at consumption, before outcome preparation, at every monthly execution boundary, and before receipt publication; expiry stops without a receipt. The complete result is staged beside the target and published with the operating system's exclusive atomic rename; if any file, symlink, or empty directory wins the destination race after the initial check, publication fails without replacing it.

Public verification is deliberately self-contained: `verify-stage2 --receipt receipt.json` checks the published receipt, its embedded hash-bound authorization-consumption record, aggregate endpoint metadata, and every public structural and statistical invariant without requiring either private sidecar. A custodian or reviewer with authorized private access can additionally pass `--authorization-consumption /private/store/<authorization-sha256>.consumed.json` and `--endpoint-ledger endpoint_reason_ledger.private.json`. The former checks the actual canonical marker, filename, hash, authorization, plan, scope, code, and chronology bindings; the latter checks ledger hash, canonical ordering, uniqueness, cardinality, and reason counts. The `status` command uses public verification only and therefore cannot prove that a private marker has not later been deleted.

The public receipt has a fail-closed privacy boundary. It embeds only the reviewed `dataset_source_mappings` projection because every required dataset must explicitly grant source-identity publication and field-mapping citation; it never embeds source references, contract scope or text, rights-review text, signatures, verification URIs, or local paths. Each published per-role projection is the exact object authorized and hash-bound inside the private v2 rights packet, while the exact private declaration and rights packet are represented only by their hashes; the externally registered manifest binds the declaration projection hash. Every entry in the public Stage-2 `data.files` map—raw data, private attestations and reports, registration records, and public-source control artifacts alike—has the uniform exact shape `{ "sha256": ... }`. Byte sizes, basenames, and paths remain private unless a later rights packet explicitly permits them under a newly registered schema; using the same digest-only shape for public-source controls prevents accidental schema widening by file class. Permitted aggregate sample and coverage diagnostics remain separate allowlisted fields. The nested bounded-probe receipt retains only the metadata categories independently approved by its own probe rights review. The official-calendar session list is handled by its own consented projection, so its public list remains verifiable without copying the raw CSV serialization. Before authorization consumption, and again during receipt verification, recursive linting rejects credential-like keys, POSIX, Windows, home-relative, and file-URI absolute paths, URL user information or credential query keys, non-HTTPS URLs, localhost/internal hostnames, and non-public IP addresses. Errors identify only the structural field path and never echo the rejected value.

This is an exact-schema migration: the rights packet is `stage2_data_rights_attestation_v2`, its public per-role mapping container is `stage2_public_dataset_source_mappings_v1`, and the resulting declaration projection is `stage2_public_data_declaration_projection_v3`. A v1 rights packet, a single unbound source name, an arbitrary compliance string, or an older consent field list is intentionally rejected. Older draft declarations and registration artifacts without `public_receipt_embedding`, declarations with any extra top-level field, and manifests without both `public_receipt_projection_sha256` entries are also rejected. Start from the maintained templates, keep completed private declarations and rights packets outside Git, set every consent/privacy assertion to `true` only after review, recompute every downstream hash, and obtain a new external registration receipt and execution authorization. Do not retrofit or rehash an already registered artifact in place.

The current runner accepts only the explicit human-verification evidence types in the maintained templates; it does not validate cryptographic signatures or registry inclusion proofs, and a cryptographic label alone cannot pass. Hashes establish artifact identity and integrity, but the authenticity of the provider timestamp rests on the retained provider record and a named human verifier. The enforced chronology is `timestamped <= verified <= probe execution start/first request`. That human verification is an explicit trust boundary, not a cryptographic claim. A future cryptographic path requires a separately implemented and tested protocol. No external registration, execution authorization, or Stage-2 outcome run has been performed by these templates.

Real-data Stage-2 execution is additionally bound to Python 3.12.12, NumPy 2.0.2, and pandas 2.3.3 and requires a clean checked-out registered commit across the whole repository, including untracked files. The Python 3.10/3.11 fixture runs are portability checks only; they do not authorize a different registered runtime.

`execution_authorization` records the permitted study scope and verifies the registration chronology. The local runner now enforces one claim per authorization hash in one protected sidecar directory by exclusive file creation before outcome load; it does not provide a global nonce, external revocation service, cryptographic signature, or protection against a privileged custodian deleting/replacing that directory. The custodian must retain the private sidecar durably and reviewers should compare it with the receipt. External registration, independent provider-record review, human authorization, and lawful data access remain separate mandatory trust boundaries.
