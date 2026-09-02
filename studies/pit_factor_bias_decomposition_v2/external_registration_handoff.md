# External registration handoff

This handoff prepares the Stage-2 design for an external registration step. It
does not register the study, create a timestamp, or authorize data release.
The machine-readable checklist is
`external_registration_handoff.template.json`; it must remain a template until
the exact frozen design manifest exists.

## What is submitted

Submit the exact bytes of `design_manifest_v1` (or its SHA-256 digest) after all
preconditions in the template are satisfied. The manifest binds the frozen
plan core, code commit, probe receipt, historical-data inputs, official
calendar, rights review, prior-exposure inventory, and statistical analysis
plan. Do not submit `plan.draft.json`, a working-tree file, or a regenerated
manifest after submission.

## Provider-neutral route

The owner must choose one provider route and record it before submission:

* OSF Registries: create a registration containing the manifest file or digest,
  then retain the public registration URL and provider timestamp.
* Zenodo: deposit the manifest (or permitted metadata package), retain the
  version-specific DOI/record URL and timestamp, and verify that the deposited
  artifact hash is the one registered.
* Journal/editorial route: ask the editor whether the journal's registered
  report, pre-registration, or hybrid protocol route can preserve the exact
  manifest and a reviewable timestamp. A sent email is not by itself a
  registration receipt.

Another provider is acceptable only if its record is public or independently
reviewable, identifies the exact artifact, and supplies a verifiable timestamp.
No provider is preferred by the code, and no provider account is accessed by
the repository tooling.

## Human handoff procedure

1. Complete the outcome-blind probe, historical data/rights review, prior-
   exposure attestation, and design manifest. Compute and record the manifest
   SHA-256 over exact bytes.
2. Have the owner submit that exact artifact to the chosen provider. Record
   provider name, submission time, identifier, and URL in a private working
   copy of `external_registration_handoff.template.json`.
3. Independently open the provider-controlled record and compare the artifact
   bytes or digest, study identity, identifier, and timezone-aware timestamp.
   Preserve a permitted export or screenshot/PDF as evidence and hash the
   exact retained bytes.
4. Copy only verified values into `registration_receipt.v1`. Keep restricted
   provider evidence private when its terms prohibit redistribution; publish
   the permitted identifier, URL, timestamps, and hashes.
5. After receipt verification, an authorized person completes
   `execution_authorization.v1`. Only then may the blind 2010–2022 outcome
   data be released to the runner.

At the runner release boundary, the completed authorization is consumed once
in a private custodian-controlled directory. The runner atomically creates
`<sha256(canonical execution_authorization bytes)>.consumed.json` (directory
mode `0700`, marker mode `0600`) before loading any quote or fundamental
outcome rows. A second claim for the same authorization hash fails closed, and
a failed or interrupted claim requires a newly signed authorization. This is a
local exclusive-create control, not an external registry, cryptographic
signature, revocation service, or substitute for the human/provider trust
boundaries above; the custodian must preserve the sidecar and protect it from
deletion or replacement.

## Stop conditions

Stop and leave the receipt/authorization templates null if the provider record
is private, the artifact hash cannot be matched, the timestamp is ambiguous,
the manifest changed after submission, or the evidence cannot be retained and
reviewed. A Git commit timestamp, a local file mtime, or a self-authored JSON
file is not a substitute for external registration.

## Current status

As of this handoff, no external registration has been performed. The next
human action is to choose a provider and submit only after the repository's
coverage, data-rights, and design-freeze gates pass. This document deliberately
does not contain a registration identifier or claim that the study is
registered.
