# Private data handoff instructions

These instructions apply only after the provider capability and rights review
has passed. They are an operational control, not permission to acquire data and
not Stage-2 execution authorization.

## Roles

- **Provider / licensed administrator:** delivers only the contracted files and
  documentation.
- **Data custodian:** receives, hashes, stores, and seals the files; the
  custodian does not inspect factor or return outcomes.
- **Outcome-blind reviewer:** may inspect schema, hashes, row counts, date
  ranges, duplicate keys, non-null rates, state vocabularies, and documented
  semantics only.
- **Stage-2 runner:** receives outcome access only after external registration
  and execution authorization.

One person may hold more than one role only when the access log and separation
of pre-authorization actions remain independently reviewable.

## Transfer and storage

1. Use an institution-approved encrypted transfer channel. Send any archive
   password through a separate channel.
2. Create a new private directory outside every Git worktree. Restrict access to
   the named custodian and authorized reviewers.
3. Preserve the provider's original files as read-only. Never edit, resave, or
   normalize them in place.
4. Do not place tokens, cookies, credentials, request headers, raw rows,
   completed contracts, or a completed handoff manifest in GitHub.
5. Record the exact file name, byte size, SHA-256, extraction time with UTC
   offset, provider data version, requested/observed date range, row count,
   field-dictionary hash, and failed/incomplete batches.
6. Write the delivery handoff manifest last. After every listed delivery file
   has been independently verified, close and hash the manifest exactly once.
   Do not add later audit hashes or an acceptance decision to it and never
   rewrite or replace the closed bytes.
7. Keep result-bearing access disabled. Metadata tools may read enough bytes to
   validate CSV structure and typed fields but may not compute or display
   factor values, forward returns, ICs, portfolios, or variant rankings.

Suggested private layout:

```text
stage2-private-delivery-YYYYMMDD/
  original/
    daily_quotes.csv
    stock_master.csv
    fundamentals.csv
    sse_calendar.raw
    szse_calendar.raw
  derived/
    official_common_calendar.csv
    calendar_intersection_log.json
  evidence/
    contract_or_terms_evidence.pdf
    provider_field_dictionary.pdf
    provider_close_raw_definition.pdf
    provider_adjustment_factor_definition.pdf
    price_adjustment_normalization_record.json
    provider_rights_confirmation.pdf
    data_rights_attestation.json
  logs/
    extraction_log.json
    transfer_record.txt
  private_handoff_manifest.json
  audit/
    stage2_data_access_audit.json
    data_review_attestation.json
    study_v2_coverage.json
    provider_delivery_acceptance_receipt.json
```

The two raw exchange calendars must retain separate source references, terms
evidence, coverage ranges, and hashes. The common calendar is a derived
artifact, never an original provider file. Its deterministic intersection
program or specification, input hashes, output hash, generation timestamp,
and every SSE/SZSE disagreement must be recorded in
`calendar_intersection_log.json`; any unresolved disagreement blocks intake.

## Required integrity checks

- Recompute every delivery-file SHA-256 before closing the delivery manifest.
- Require `daily_quotes.csv` to retain `close_raw`, `adjustment_factor`, `close`,
  and the exact fixed method/convention tokens. Mechanically verify
  `close=close_raw × adjustment_factor` within the registered `1e-12`
  relative/absolute tolerances; separately hash the provider raw-close
  definition, cumulative-factor convention, and normalization/adapter record.
- Verify the closed manifest hash without changing it. If the custodian elects
  to create the optional operational receipt, record that hash alongside the
  later metadata-audit, review-attestation, and coverage-report hashes in a
  separate `provider_delivery_acceptance_receipt.json`.
- Reject symlinks, archives with path traversal, malformed CSV row widths,
  duplicate logical keys, unexpected files, and reused output directories.
- Confirm that no file path resolves inside the public repository.
- Keep the transfer record and completed manifest private. Publish only hashes
  and aggregates that the signed rights confirmation explicitly permits.

## Outcome-blind intake

Run the provider-neutral metadata intake first:

```bash
PYTHONPATH=src python3 -m a_share_quant_agent.data_access \
  --quotes /private/original/daily_quotes.csv \
  --stock-master /private/original/stock_master.csv \
  --fundamentals /private/original/fundamentals.csv \
  --official-calendar /private/derived/official_common_calendar.csv \
  --rights-attestation /private/evidence/data_rights_attestation.json \
  --output /private/audit/stage2_data_access_audit.json
```

The metadata-audit output is also private rights-controlled evidence. Its
mandatory `--output` must be new and outside every Git worktree; the CLI
atomically creates mode-`0600` bytes, never overwrites, and does not send the
payload to stdout. No redacted public-export command is implemented.

A metadata pass may parse raw numeric bytes for the fixed integrity contract,
but it is not permission to compute, retain, release, or human-inspect factor
returns, ranks, ICs, portfolio results, test statistics, or variant orderings.
Continue with the full
coverage/review gate and then the design freeze, external registration,
independent registration-receipt verification, and one-time execution
authorization in that order. A custodian may also create the separate private
delivery-acceptance receipt as an optional operational record, but it is not a
design-manifest input or formal gate. The delivery manifest remains immutable
throughout.

For the authorized `run-stage2` call, two paths are mandatory and must resolve
outside every Git worktree, including unrelated repositories, linked
checkouts, and the QData checkout:
`--output-dir` is a fresh, nonexistent private result directory that will hold
the receipt and private endpoint ledger, and `--authorization-consumption-dir`
is the protected mode-`0700` marker store. A directory inside a worktree is
forbidden even when `.gitignore` excludes it. The runner checks both locations
before consuming authorization and does not derive a default marker location.
Start the registered CLI with
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m a_share_quant_agent.confirmatory_study run-stage2`
so imports cannot create `__pycache__` before the whole-repository clean check;
the CLI rejects a Stage-2 call when bytecode suppression was not active at
interpreter startup. The result directory is assembled completely in a sibling
staging directory and published by an exclusive atomic rename. If another
entry appears at the target after the initial absence check, the runner keeps
that entry intact, publishes nothing over it, and requires a new authorization
for any retry.
The authoritative coverage-report `--output` follows the same any-Git rule,
must not already exist, and is atomically created with mode `0600`. Its exact
hashes, sizes, and detailed coverage remain private until separately cleared;
no public-export command is currently implemented.

## Retention and destruction

Follow the signed contract and institutional retention schedule. Record any
deletion with timestamp, scope, method, and authorizing person. Never destroy
the evidence or one-time authorization-consumption record merely to enable a
second run; a failed or interrupted authorized run requires a new authorization.
