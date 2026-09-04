# Stage 2 Registration and Authorization Runbook

## Purpose and current status

This runbook turns the existing JSON templates into a human-controlled operating sequence. It does not perform an external registration, authenticate a registry, sign an authorization, or release historical outcomes. As of 4 September 2026, the data and review gates have not passed, so `design_manifest.template.json`, `registration_receipt.template.json`, `execution_authorization.template.json`, and `execution_plan.template.json` must retain their draft states and null external fields.

## Route selection

Choose the external route only after the data and rights gates pass and any journal guidance has been recorded.

- An OSF Registration is the default independent route when the journal accepts it. OSF describes registrations as time-stamped, read-only study records. A registration can be public or embargoed; an embargoed record can use an anonymized view-only link for blinded review. Submitted registration contents cannot be edited. Start from a new registration rather than depending on project-based registration because OSF has announced changes to its project workflow. See the [official OSF registration guide](https://help.osf.io/article/330-welcome-to-registrations) and [OSF project transition notice](https://help.osf.io/article/744-osf-projects-api-impact).
- A Zenodo record is an archival alternative only if the editor accepts a published or embargoed deposit as the external registration evidence. A saved draft is not sufficient. Zenodo assigns a DOI when an upload is published and allows a DOI to be reserved before publication. See the [official Zenodo deposit guide](https://help.zenodo.org/docs/deposit/) and [official DOI guidance](https://help.zenodo.org/docs/deposit/describe-records/reserve-doi/).
- A journal or editorial route is acceptable when it preserves the exact manifest bytes or digest, supplies a reviewable timezone-aware record, and fits the journal's pre-registration or hybrid Registered Report procedure.

The code has no preferred provider and does not log in to any registry. The chosen route must permit an independent human to verify the same study identifier, artifact hash, provider identifier, timestamp, and access record.

## Fixed chronology

The only permitted order is:

1. bounded probe specification and prior inventory receive their required external timestamp before the bounded probe runs;
2. the bounded probe receipt passes its fixed scope;
3. the four delivered historical inputs pass metadata, rights, full coverage, and human semantics review;
4. the prior-exposure inventory and attestation are completed and signed;
5. the flat execution-plan core is fully materialized and frozen;
6. `stage2_design_manifest_v1` binds the plan-core hash, clean code commit, raw-input hashes, data declaration, official calendar, coverage report, review attestation, protocol, statistical analysis plan, prior inventory, prior-exposure evidence, and probe receipt;
7. an external provider accepts the exact manifest bytes or their exact SHA-256 digest;
8. an independent human verifies the provider record and retains hash-bound evidence;
9. `stage2_registration_receipt_v1` records the verified external fact;
10. a separate authorized custodian signs `stage2_execution_authorization_v1` after rechecking all hashes, chronology, rights, privacy, and the no-outcome-access assertion;
11. the final execution-plan envelope records the backward-pointing manifest, receipt, and authorization hashes without changing the frozen plan core; and
12. the runner consumes the authorization once in a protected private directory before it reads historical outcome bytes.

Every timestamp must be ISO 8601 with an explicit UTC offset. Equality is allowed only where the template chronology permits it. No later artifact may be inserted into and thereby alter an earlier hashed artifact.

## Design manifest completion

Create a private working copy of `design_manifest.template.json`. Do not edit the tracked template. Populate it only after the coverage and prior-exposure gates pass.

The completed manifest must:

- change `status` to `frozen_outcome_blind`;
- record a timezone-aware `design_frozen_at`;
- bind the canonical plan-core SHA-256 computed after removing only `external_registration` and `locked_at` from the fully materialized plan;
- bind the exact hashes of the bounded probe receipt, data declaration, official calendar, reviewed coverage report, review attestation, protocol source, statistical analysis plan, prior specification inventory, prior-exposure log, and signed prior-exposure attestation;
- bind the four exact raw-input hashes and the clean registered code commit;
- bind the permitted public projections for the data declaration and official-calendar session dates;
- preserve the fixed 18-variant, 72-cell, one-primary, 28-secondary, three-component common-support, exact-endpoint, price-adjustment, terminal-survivor, identifier, quintile, and single-version claim assertions; and
- set public-receipt consent and all privacy assertions to true only after a human confirms that the full manifest is safe to publish.

The manifest intentionally has no self-hash, registration receipt hash, execution authorization hash, or external identifier. Compute its SHA-256 only after the file is closed and do not change a byte after submission.

## External submission

Use `external_registration_submission_text.md` for the registry description. Submit the exact manifest file or its exact digest. If the platform archives a file, download or independently reopen the archived copy and compare its SHA-256. If the platform records only a digest, compare the displayed digest character for character with the local closed-file hash.

Record provider, identifier, provider-controlled URL or authorized view-only URL, registration time, artifact type, artifact SHA-256, and submission notes in a private copy of `external_registration_handoff.template.json`. The submitted record must be immutable or read-only for the registered version. If blinded review is planned, remove identifying material before submission and use the platform's embargo or anonymous view-only mechanism rather than altering the record later.

## Independent verification and registration receipt

The submitter and verifier may be the same human only if the journal and institutional process allow it, but verification must still be a separate recorded action. The verifier opens the provider-controlled record without relying on the submitter's local file, checks the study identity and artifact hash, confirms the timezone-aware timestamp, and retains a permitted export, screenshot, PDF, or provider email as exact evidence bytes.

Create a private working copy of `registration_receipt.template.json`. Populate it only from the verified provider record. The completed receipt must:

- change `status` to the accepted registered state required by the runner;
- record the provider, immutable identifier, `registered_at`, later `recorded_at`, verification URI, registered artifact type, exact manifest SHA-256, and bounded-probe receipt SHA-256;
- preserve the registered scope summary exactly;
- use proof type `human_verified_registry_record`;
- record the retained evidence SHA-256, verifier identity, and timezone-aware `verified_at`;
- satisfy `design_frozen_at <= registered_at <= recorded_at <= verified_at`; and
- approve public embedding only after confirming that local paths, restricted evidence, and unapproved identities or URLs are absent.

The current code validates structure, hashes, chronology, and an explicit human-verification record. It does not validate a cryptographic signature or registry inclusion proof. The receipt must say so.

## Execution authorization

Create a private working copy of `execution_authorization.template.json` only after the registration receipt passes independent verification. The authorizer must have a documented basis to release the licensed historical inputs for the registered analysis.

The completed authorization must:

- change `status` to `authorized` and record `authorized_at`, authorizer, role, and authority basis;
- bind the exact design-manifest, registration-receipt, and plan-core hashes;
- bind every artifact and code commit listed in `bound_artifacts`;
- reproduce the complete chronology and set every chronology assertion to true only after checking evidence;
- confirm that data rights are active at authorization and that any required post-expiry publication and review survival term is separately evidenced;
- confirm that no factor, return, IC, rank, portfolio, or variant outcome was computed, released, or inspected before authorization;
- leave `authorized_runner_scope=ic_core_only`, the 2010-2022 period, fixed price, identity, universe, rank, endpoint, output, and claim boundaries unchanged;
- set `outcome_data_release_permitted_after_authorized_at=true` only after all preceding checks pass;
- retain every planned or excluded module as unauthorized;
- provide a human-verified signature evidence hash and verification URI;
- approve public embedding only after the privacy review passes; and
- preserve the one-use authorization-consumption contract.

The authorization is not a journal acceptance, cryptographic nonce, or permission to alter the registered design. A failed or interrupted authorized run consumes the local authorization claim and requires a newly signed authorization.

## Final execution envelope

After authorization is closed and hashed, populate only the permitted non-core envelope fields in the final private execution plan:

- provider, identifier, registration time, registered content hash, manifest hash, receipt hash, authorization hash, and verification URI under `external_registration`; and
- `locked_at`, equal to `execution_authorization.authorized_at`.

Do not recompute or rewrite the registered plan core. Before launch, the runner must validate all control artifacts, reject any dirty repository or runtime mismatch, atomically consume the authorization in a protected directory outside every Git worktree, capture each raw input once, recompute its registered hash, and reuse those captured bytes for coverage, analysis, and receipt evidence.

## No go records

None of the following can serve as external registration or execution authority:

- a Git commit timestamp or tag without the required provider record;
- a local file creation or modification time;
- a sent email that does not preserve an immutable accepted artifact and reviewable provider timestamp;
- a mutable cloud document or draft registry entry;
- a private record that the independent verifier cannot access through an authorized provider-controlled route;
- a DOI reservation without publication or another accepted immutable record;
- a manifest whose bytes changed after submission;
- a self-authored receipt with no provider evidence;
- a placeholder, null, copied example, or assertion whose external event did not occur;
- an authorization signed before registration verification;
- an authorization signed after contract expiry without a newly valid data right; or
- a completed form that exposes a contract, credential, local path, or unapproved identity in the public receipt.

If any item above occurs, retain the evidence privately, leave the public templates unchanged, record `BLOCKED_FOR_STAGE2`, and do not access outcomes.

## Operator completion record

The registration stage is complete only when the manifest hash can be independently matched to a provider-controlled record and a valid registration receipt. The authorization stage is complete only when a qualified custodian signs after that verification and every authorization assertion is true. Until both conditions hold, the only correct repository status is `BLOCKED_FOR_STAGE2`.
