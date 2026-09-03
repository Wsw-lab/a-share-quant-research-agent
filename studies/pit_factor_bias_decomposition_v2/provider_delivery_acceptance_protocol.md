# Outcome-blind provider delivery operational checklist

## Purpose and claim boundary

This document is an optional private operational checklist for the **actual
contracted delivery**. It does not create a formal acceptance gate and is not a
design-manifest input. The authoritative pre-lock decision comes only from the
human `data_review_attestation` and recomputable Stage-2 coverage report that
the design manifest actually binds. This checklist may report only hashes,
schema facts, date ranges, counts, non-null rates, recognized state
vocabularies, and aggregate pass/fail results. It may not display or compute
factor values, returns, ranks, ICs, portfolios, strategy comparisons, or
result-driven sample changes.

The separate `coverage_probe_spec.v2.json` is a fixed 12-symbol by two-date
exact-route AkShare raw-bar reachability probe. Its dedicated Agent adapter does
not import or call QData; the QData checkout is provenance-only. It does not test a Wind, CSMAR,
RESSET, Choice, Tushare, Investoday, or other contracted delivery and must never
be cited as proof that the purchased data, fundamentals, official calendars, or
rights are adequate.

## Preconditions for the optional operational checklist

All must be true before the acceptance audit or any human inspection of
result-bearing values. The custodian may first read only the bytes needed to
record file identity and structural metadata in the closed delivery manifest:

1. the provider capability workbook reports
   `FORM_COMPLETE_FOR_HUMAN_REVIEW` and is internally consistent; this label
   means form completeness only, not acceptance;
2. the provider/licensor has supplied a written grant, or the licensed
   administrator has cited and confirmed rights already present in the
   controlling contract; an administrator statement does not create a missing
   right;
3. a human reviewer has completed `data_rights_attestation` using the exact
   retained contract/response hashes;
4. the private delivery handoff manifest is closed, hash-verified, outside Git,
   and the result-bearing access boundary remains sealed; the closed manifest
   must never be rewritten with later audit or decision fields;
5. no coverage threshold, interval, factor, variant, or stopping rule has been
   changed in response to delivered values.

## Mechanical intake gates

Record `BLOCKED` in the optional operational receipt if any checklist item
fails. Passing this table is not itself permission to freeze, register, or run
the study.

| Gate | Required rule |
|---|---|
| Closed inputs | Exactly one declared canonical quotes, stock-master, fundamentals, and derived common-calendar input; separate raw SSE/SZSE calendars and the derivation log are also closed and hash-bound in the private manifest. |
| CSV structure | No duplicate headers, short/over-wide rows, blank mandatory fields, or normalized logical-key duplicates in any canonical input; only aggregate error counts may be reported. |
| Quote interval and geometry | File-level range covers 2009-01 through 2023-01 and every observed quote date belongs to the bound common official calendar. In each of the 156 target months, every member of `active master ∩ signal-session quote` must have exact `t`, `t+1`, `t+20`, and `t+21` rows, so exact-endpoint identifiers equal signal-session candidates; at least 1,000 complete-contract identifiers must also satisfy every pre-specified history and endpoint row. A missing observation is never carried forward or shifted. |
| Quote keys and adjusted-close contract | Unique normalized `(symbol, date)` keys; exact uppercase `NNNNNN.SH`/`NNNNNN.SZ` identifiers and exact `YYYY-MM-DD` dates within the runner-safe inclusive range 1677-09-22 through 2262-04-11. Every row has finite positive `close_raw`, finite positive `adjustment_factor`, finite positive `close`, exact `price_adjustment_method=close_equals_close_raw_times_adjustment_factor`, and exact `price_adjustment_convention=provider_cumulative_backward_adjusted_hfq_no_rebasing`; `close=close_raw × adjustment_factor` holds within the frozen `1e-12` relative/absolute tolerances. The factor is exact-symbol/session aligned and used as delivered without rebasing. The reviewer verifies distinct hashes for the provider raw-close/valuation definition, cumulative-factor convention, and exact normalization/adapter record; tokens and arithmetic are not substitutes for provider evidence. Amount is finite and non-negative under the canonical ASCII-decimal grammar; exact `amount_unit=CNY` appears on every row after documented private normalization and before hashing, with retained provider-native unit, conversion rule/cutoff, and conversion-provenance hash. |
| Tradability states | `is_st` and `is_suspended` use only approved true/false encodings and each contains both states over the full panel. `close_observation_type` is exact and non-blank on every row: `traded_close` iff not suspended and `suspension_valuation` iff suspended. Both close-observation types must occur among active-master signal-session candidates, and an authorized reviewer must attest that every suspension valuation was supplier-recorded or published for that exact official session rather than generated by the research code. |
| Lifecycle | Current and delisted SH/SZ A-shares are present; list/delist chronology and status/type vocabulary pass; latest-only reconstruction is rejected. |
| Terminal-survivor and identifier semantics | A0 is frozen to the 2023-01-31 required quote/outcome cutoff: after requiring listing by each historical signal session, retain only null `delistDate` or a date strictly after that cutoff, independent of extraction-current status or acquisition date. The same human-reviewed provider-stable identifier contract token applies across quotes, stock master, and fundamentals; separately hash-bind the provider identifier definition and complete code-change/reassignment mapping. Exact symbol syntax alone is insufficient, and no vintage claim follows. |
| Fundamentals | Required `roeDiluted` semantics are documented and every non-missing value is finite under the canonical ASCII-decimal grammar; canonical symbols and dates use the exact formats above; `(symbol, reportPeriodEnd)` keys follow the declared single-version rule; `publishDate` is the actual recorded disclosure date and never precedes the report-period end anywhere in the delivery. |
| Official calendar | Separate raw SSE and raw SZSE files and source evidence exist; their hashes and ranges are retained. The derived common file contains only dates explicitly open on both exchanges, and a hash-bound intersection/disagreement log exists; unresolved disagreement fails closed. |
| Monthly coverage | Exactly 156 target months; exact-endpoint identifiers equal all signal-session candidates in every month; at least 1,000 complete-contract symbols per month; at least 15 official quote sessions per month; and actual-publication-date non-null coverage of at least 0.95. |
| Rights | Local analysis, permitted aggregates, hashes, exact calendar dates, controlled reviewer rerun, and private ledger retention/hash rights are explicit; provider/source naming and field-map citation are true for every required dataset. The v2 packet binds the exact source name and complete canonical-to-provider mapping for each of the four roles by canonical SHA-256, and each projection exactly matches the declaration; generic approval text cannot substitute for this mapping. Every Conditional restriction has a unique ID and exactly one review with the same ID and exact permission field, a satisfied flag, timestamp, and evidence hash; missing, duplicate, unknown, permission-mismatched, or false-permission mappings fail closed. Finite contracts remain active at exclusive authorization consumption, every monthly execution checkpoint, and receipt publication and separately preserve completed-research publication/review after expiry; raw redistribution and credential sharing remain false. |
| No outcomes | Validators may parse raw numeric bytes for fixed integrity and coverage checks, but audit output contains no prices, accounting values, security-level exceptions, returns, factor ranks, ICs, portfolios, test statistics, or variant comparisons. |

The non-circular order is:

1. run the provider-neutral metadata audit, which produces aggregate
   structural counts and exact input hashes only in a mandatory new private
   mode-`0600` file outside every Git worktree. It never overwrites or prints
   the payload, and no redacted public export is implemented;
2. have an authorized human complete `data_review_attestation`, binding the
   same four canonical input hashes plus the field, rights, execution, probe,
   and official-calendar evidence;
3. run the existing four-input Stage-2 coverage audit with that completed
   attestation. The resulting coverage report recomputes the input hashes and
   embeds the attestation hash and status; the attestation does not claim to
   bind a report that did not yet exist. Write it only to a new private file
   outside every Git worktree; the CLI atomically creates mode-`0600` bytes and
   never overwrites. No separately rights-reviewed public export is currently
   implemented;
4. optionally create a separate private
   `provider_delivery_acceptance_receipt` that binds
   the immutable delivery-manifest hash and the later metadata-audit,
   attestation, and coverage-report hashes, records the reviewer-verified
   operational chronology without treating its timestamps as cryptographic
   proof, and
   records only `OPERATIONAL_CHECKLIST_COMPLETE` or `BLOCKED`. This receipt is
   a custody aid, not an executable precondition. The execution plan and design
   manifest bind the coverage report and review-attestation hashes before
   registration; those bound artifacts are the authoritative gates.

A successful metadata audit alone is insufficient. The provider-neutral
scanner mechanically validates required quote and diluted-ROE values through
aggregate invalid counts only; it never publishes prices or accounting values.
Its early `publishDate >= 0.95` check uses the complete canonical fundamental
delivery and is deliberately conservative. It is an operational diagnostic,
not a registered gate. The authoritative coverage report separately recomputes
the same 0.95 threshold on otherwise eligible in-scope fundamental records;
that bound report and the human review must pass before design freeze.

## Optional future provider-specific validation

No provider-specific second-source comparison is a current intake gate, and no
present adequacy claim relies on one. Such a comparison may become a future
additional validation only after a provider-specific specification, runner,
verifier, receipt schema, and hash-binding chain have been implemented and
tested. The exact specification must then be externally timestamped **before**
any compared values are read and must name the authorized comparison source,
immutable seed, permitted identifier/date fields, fixed sample sizes and
strata, unit and adjustment conversions, tolerances, aggregate-only output,
and stop rules.

The comparison program, not a researcher, reads the selected values. Public
output is limited to sample size, matched/mismatched/missing counts, tolerance,
and artifact hashes. Mismatch values and security identifiers remain private.
If that future control is formally frozen into the registered intake design,
any unexplained mismatch blocks acceptance; the sample or tolerance may not be
changed after seeing it. Until those implementation and registration conditions
exist, an ad hoc comparison must not be presented as evidence for this study.

## Decision

The only allowed operational decisions are:

- `OPERATIONAL_CHECKLIST_COMPLETE`: every checklist item passes and the four
  evidence hashes above are retained; this does not establish the formal
  design-freeze preconditions and `authorization_granted` remains `false`.
- `BLOCKED`: at least one gate fails or is unknown; no sample-period shortening,
  provider substitution, threshold relaxation, design freeze, registration, or
  outcome access follows from the failed delivery.

Only a verified coverage report with `ready_to_lock_stage2_plan=true` and a
completed `reviewed_pass` human attestation permit the plan/design freeze. The
resulting design manifest must bind both artifacts. This optional receipt is
not formal acceptance, external registration, or execution authorization.
