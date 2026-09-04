# Stage-2 historical data acquisition and rights plan

**Current decision: `BLOCKED_FOR_STAGE2` (data and rights not yet attested).**

This document turns the three outstanding data tasks into an executable,
outcome-blind intake sequence.  It is a procurement and metadata plan, not a
claim that any source has already been acquired. No factor return, signal rank,
IC, portfolio result, test statistic, or variant ordering may be computed,
released to the research team, or human-inspected while the steps below are
being completed. Custodial validators may parse raw numeric bytes only to test
schema, finiteness, dates, identifiers, exact endpoint presence, and permitted
aggregate coverage; they must not emit or retain those prohibited outcomes.

## The fixed input contract

The primary panel is fixed before any historical outcome analysis:

| Role | Required interval | Required fields | Additional semantic evidence |
|---|---|---|---|
| Daily quotes | 2009-01-01 through 2023-01-31 | `date`, `symbol`, `close_raw`, `adjustment_factor`, `close`, `price_adjustment_method`, `price_adjustment_convention`, `close_observation_type`, `amount`, `amount_unit`, `is_st`, `is_suspended` | Every row carries exact method `close_equals_close_raw_times_adjustment_factor` and convention `provider_cumulative_backward_adjusted_hfq_no_rebasing`, with `close=close_raw × adjustment_factor` inside the fixed tolerance. `amount` is normalized before binding and every row has exact `amount_unit=CNY`; provider-native unit, conversion rule, cutoff, and provenance are retained for human review; `close_observation_type=traded_close` iff not suspended and `suspension_valuation` iff suspended; each valuation must be supplier-recorded or published for that exact official session; exact `t`, `t+1`, `t+20`, `t+21` rows |
| Stock master | complete lifecycle records for every security active during 2009-01-01 through 2023-01-31 | `symbol`, `listDate`, `delistDate`, `listStatus`, `stockType` | actual list dates before 2009 are retained; current and delisted SH/SZ A-shares; valid list/delist chronology; A0 terminal survivors use the fixed 2023-01-31 cutoff rather than extraction-current status |
| Fundamentals | publication records beginning 2009-01-01 through 2022-12-31 | `symbol`, `roeDiluted`, `publishDate`, `reportPeriodEnd` | vendor field is explicitly defined diluted ROE and maps one-to-one to `roeDiluted`; `publishDate` is actual disclosure date; no scheduled-date substitution; no publication-before-report rows |
| Common calendar | 2009-01 through 2023-01 | one `date` column | every row is an authoritative common SSE/SZSE open session; exact bytes and provenance hash-bound |

Across quotes, stock master, and fundamentals, `symbol` must implement the same
human-reviewed provider-stable identity under the fixed token
`provider_stable_exchange_qualified_security_identifier_with_reviewed_code_change_mapping_v1`.
The provider identifier definition and the historical code-change/reassignment
mapping are separately hash-bound before the canonical inputs are bound. Exact
`NNNNNN.SH`/`NNNNNN.SZ` formatting alone does not prove identity stability, and
this contract makes no revision- or vintage-data claim.

The current runner supports exact provider-recorded traded closes and exact
supplier-recorded or published same-session suspension valuations on the bound
calendar. Research code never creates a suspension valuation by forward-filling
a last price, invents a delisting terminal value, or moves to the next observed quote.
The resulting returns and ICs are valuation diagnostics, not executable trade
returns. A complete private
per-security endpoint-reason ledger is therefore required after authorized
execution, but its rows are never committed to GitHub.

## Workspace evidence status as of 2026-09-04

No qualifying entitlement, contract evidence, or complete delivery was
available in the audited workspace.  This limited workspace finding does not
make a claim about any provider account held elsewhere.  Public documentation
identifies several capability leads, but documentation alone is neither an
entitlement nor a data licence.

This is a capability status, not a finding about factor performance.  No
factor, return, IC, portfolio, or variant result was queried during the audit.
The next action is to send the same provider-neutral request to candidate
licensed institutional vendors and obtain completed field/rights responses
before acquiring or inspecting result-bearing rows. Specific outreach order,
negotiation strategy, quotations, and correspondence are private procurement
records outside Git and are not research-design inputs.

## Source decision matrix

The machine-readable version is
[`source_capability_matrix.json`](source_capability_matrix.json).  The short
decision is:

1. **Licensed institutional vendor route:** obtain the exact table names,
   field dictionary, complete 2009--2023 coverage, identifier and
   suspended-session valuation semantics, entitlement evidence, and every
   publication/reviewer permission in the rights form. Public product claims
   or broad terminal coverage do not substitute for that written evidence.
   Named entries in the capability matrix are alternatives, not a public
   ranking or evidence that an entitlement is held.
2. **Candidate retained as a technical cross-check rather than a presumed
   complete contracted panel:** Tushare Pro documents
   historical daily bars (`daily`), adjustment factors (`adj_factor`),
   exchange-parameter calendar rows (`trade_cal`), stock lists (`stock_basic`
   and `bak_basic`), ST records (`stock_st`), suspension records (`suspend_d`),
   and filing-date records (`disclosure_date`). `bak_basic` is documented only
   from 2016, `suspend_d` does not document full 2009--2023 coverage, and
   `trade_cal` documentation does not establish authoritative exchange
   provenance. These endpoints therefore remain candidates or cross-checks,
   not proof of a complete delivery. The service documentation states
   endpoint permissions/points vary, and the service agreement describes a
   personal, non-transferable, non-commercial licence.  Consequently no
   aggregate publication or reviewer right is inferred from an account; the
   provider must give written permission or the source remains unusable for the
   paper.
3. **Probe/cross-check only:** AKShare can test bounded raw-bar reachability
   (`stock_zh_a_hist`) and exposes a Sina-derived calendar.  That calendar is
   not accepted as the sole authoritative common SSE/SZSE calendar.  The
   AKShare MIT software licence applies to the client code, not automatically
   to upstream returned data.  BaoStock is similarly useful as a cross-check,
   but its public adapter does not establish actual filing dates, complete
   historical ST/suspension semantics, adjusted-close construction, or
   publication rights.
4. **Authority cross-check:** official SSE/SZSE calendars and issuer/CNINFO
   filing documents should be retained for a pre-specified sample and for any
   exchange-calendar disagreement.  Public web availability does not itself
   grant bulk extraction or redistribution permission; retain the applicable
   terms evidence.

## Required extraction order

1. **Contract and rights review (no data response inspection).** Obtain the
   provider contract or terms PDF, identify the exact dataset entitlements,
   effective/expiry dates, local-storage rule, research-use rule, aggregate
   publication rule, hash/metadata rule, controlled-review rule, explicit
   source-identity-publication grant, and field-mapping-citation grant. Both
   must be true for every required dataset because provider-supplied strings
   enter the fixed public Stage-2 declaration projection. Fill
   [`data_rights_attestation.template.json`](data_rights_attestation.template.json)
   only after a human reviewer has read the terms. For each of the four roles,
   copy the exact source name and complete canonical-to-provider field map into
   `authorized_public_projection`, compute its canonical SHA-256, and use the
   identical projection in the declaration's `dataset_source_mappings` object.
   Missing/extra fields, swapped roles, generic compliance words, rehashed
   substitutions, or any rights/declaration difference fail closed. Never put
   a token or cookie in the repository or in a receipt.
2. **Bounded source probe.** Use the already frozen
   `coverage_probe_spec.v2.json` exactly as written. First finish the
   prior-specification inventory without viewing outcomes: populate its
   preparer and timezone-aware chronology fields, verify its entries hash, and
   set `status` to `manifest_eligible_outcome_blind`. Its
   `repository_snapshot.head_commit` is the already-existing audited base
   commit and must be an ancestor of the commit that later contains the final
   inventory; equality with a self-embedded future commit is neither required
   nor possible. Commit those exact inventory bytes and the probe spec in a
   descendant commit, then create a canonical timestamp package binding both
   exact hashes and that containing Agent commit. Obtain an external timestamp
   after `generated_at` and have it independently verified before any request.
   The runtime then queries only the 12 fixed symbols on the two fixed dates
   through the dedicated Agent exact-date adapter. The adapter never
   imports or calls the QData provider path; it verifies the pinned AkShare
   source module, permits one non-redirected HTTPS request per cell with
   `start_date=end_date`, rejects lookback/fallback/other endpoints, and derives
   the recorded upstream identity from the observed final response host. The
   QData checkout is retained only as a clean, hash-bound provenance input. The
   probe checks request scope and raw field reachability; it cannot authorize a
   full extraction or establish factor evidence. Before publication, the rights
   reviewer must separately approve artifact hashes, filenames, sizes, row
   counts, symbol/date-range summaries, route metadata, timestamp provider and
   identifier, timestamp evidence hash, verifier identity, and verification URI.
   The v3 review binds the exact raw timestamp-proof SHA-256 and carries
   timezone-aware contract effective/expiry evidence. The contract must be
   effective by review and active at probe preflight, the first provider
   request, and receipt publication. A finite term must separately hash-bind
   permission to retain the private probe artifacts and keep the already
   published aggregate receipt and metadata available after expiry. Null
   expiry requires explicit no-expiry confirmation and false/null post-expiry
   fields; proof substitution, contradictory term fields, or expiry at any
   checkpoint stops without a receipt. The public receipt and private manifest
   bind the exact rights-review SHA-256 for later verification. The completed
   staging directory is published by an atomic exclusive no-replace rename;
   a racing file, symlink, or empty directory is never overwritten.
3. **Calendar assembly.** Retrieve separate SSE and SZSE rows for every date
   from January 2009 through January 2023.  Keep the raw exchange responses and
   terms evidence privately.  Form the intersection only when both exchanges
   explicitly report open; fail closed on a disagreement.  Export the exact
   one-column UTF-8 CSV required by `official_calendar/calendar.schema.json`.
4. **Historical panel extraction.** Extract daily raw bars and adjustment
   factors for all strict SH/SZ A-shares, then join on exact symbol/date keys.
   The bound file must retain `close_raw` and `adjustment_factor`, carry exact
   `price_adjustment_method=close_equals_close_raw_times_adjustment_factor` and
   `price_adjustment_convention=provider_cumulative_backward_adjusted_hfq_no_rebasing`,
   and materialize `close=close_raw × adjustment_factor` within the fixed
   `1e-12` relative/absolute tolerances before hashing. Extract a required
   `close_observation_type` for every row: `traded_close` only for non-suspended
   rows and `suspension_valuation` only for suspended rows. The latter must be
   recorded or published by the supplier for that exact official session; the
   research adapter must never generate it by last-price carry-forward. Extract
   lifecycle membership, ST and suspension states, amount, and actual filing dates
   in separate immutable batches.  Do
   not use a latest-only stock list to reconstruct historical membership. Bind
   the provider-stable identifier definition and every historical code-change or
   reassignment mapping across the three symbol-bearing inputs. For A0, retain a
   security at a historical signal session only when it was already listed and
   its `delistDate` is null or strictly after the fixed terminal cutoff
   2023-01-31; do not use extraction-current `listStatus` or acquisition date to
   move that cutoff.
5. **Metadata diagnostic and authoritative coverage audit.** First run the
   independent metadata scanner in
   `a_share_quant_agent.data_access` over the four files.  It reads the exact
   input bytes and records hashes, row counts, date ranges, key duplicates,
   non-null rates, and
   ST/suspension distinct values and the close-observation mapping without computing research outcomes. The scanner
   canonicalizes date keys (so `YYYYMMDD` and `YYYY-MM-DD` duplicates cannot
   hide), rejects malformed CSV row widths, requires explicit `true` and
   `false` states (with no third/unknown value) for ST/suspension fields, and
   reports strict lifecycle checks (recognized active/delisted status, A-share
   type, non-null delist dates for delisted rows, no active row with a delist
   date, and chronology).
   The scanner and authoritative audit mechanically reject missing or wrong
   price-adjustment tokens, non-finite/non-positive raw close or factor values,
   and formula mismatches. A human reviewer must separately bind evidence hashes
   for the provider `close_raw` definition, cumulative-factor convention, and
   exact normalization/adapter record; row arithmetic cannot prove provider
   semantics. Calendar rows must be strictly increasing; date parseability, numeric quote
   fields, and finite numeric `roeDiluted` values are validated without
   publishing values. Every canonical quote row must carry exact
   `amount_unit=CNY`; provider-native thousand-CNY or any other unit must be
   normalized by the private adapter before raw bytes are hashed, and its
   mapping/provenance must be retained for the human review. Whether
   `publishDate` truly means the actual recorded
   disclosure date remains a field-dictionary and human-review assertion, not
   something date parsing can prove. This diagnostic is deliberately
   conservative but is not itself bound by the design manifest. Its exact
   metadata output is private, requires a new target outside every Git
   worktree, is atomically created mode `0600` without overwrite, and cannot be
   printed or publicly exported by the current CLI. Then run the
   authoritative Stage-2 coverage audit with the human data-review attestation;
   the design manifest binds both that recomputable report and the attestation.
   Its exact hashes, byte sizes, and detailed counts make it private
   rights-controlled evidence: the CLI requires a new output outside every Git
   worktree, atomically creates it with mode `0600`, and does not implement a
   public export.
   The bound coverage report independently enforces malformed-row, normalized
   duplicate-key, required-non-null, finite quote/ROE, and runner-compatible
   non-degenerate ST/suspension gates. It also requires both close-observation
   types among active-master signal-session candidates, exact agreement between
   `close_observation_type` and `is_suspended` on every row, and—in every target
   month—exact endpoint coverage for every member of `active master ∩ signal-session
   quote`, so `exact_endpoint_symbol_count == signal_session_candidate_symbol_count`.
   The separate minimum of 1,000 complete quote-contract identifiers still applies.
   It also requires every non-blank
   canonical date to be an exact valid `YYYY-MM-DD` token, every canonical
   security identifier to be exact uppercase `NNNNNN.SH` or `NNNNNN.SZ`, and
   quote/ROE numbers to use the fixed ASCII-decimal grammar accepted by the
   runner. It rejects any comparable fundamental row anywhere in the delivered
   file whose `publishDate` precedes `reportPeriodEnd`; it does not rely on the
   unbound metadata diagnostic for those controls.
6. **Optional future provider-specific validation.** No second-source sample is
   a current gate.  It can become an additional prospective control only after
   a provider-specific specification, runner, verifier, receipt schema, tests,
   external timestamp, and hash binding are in place before any compared values
   are read.  Ad hoc adjusted-price, lifecycle, filing-date, ST, suspension,
   amount, or calendar comparisons cannot support the present study.
7. **Registration and authorization.** Only after the authoritative coverage
   report and bound human review pass:
   `prior-exposure attestation → frozen plan → design manifest → external
   registration receipt → execution authorization → one Stage-2 run`.

## Provider-specific field mapping

For a Tushare candidate, the component adapters below are fixed where the
table says so. The repository implements the daily/adjustment, amount,
calendar-candidate, disclosure-date, ST-positive, and suspension-positive
normalizers, but it does **not** yet implement a canonical provider-specific
join that supplies an independently recorded same-session suspension valuation.
That join remains blocked until a supplier delivers and documents the valuation
series. None of these component adapters establishes entitlement, historical
completeness, official provenance, or publication rights:

| Canonical field | Provider field(s) | Rule |
|---|---|---|
| `close_raw`, `adjustment_factor`, `price_adjustment_method`, `price_adjustment_convention`, `close` | `daily.close`, `adj_factor.adj_factor`, fixed tokens, and their product | the component adapter materializes exact-symbol/date `hfq` rows with `close=close_raw × adjustment_factor`, no rebasing, and the two fixed tokens; missing/non-positive factors fail closed. This does not prove a complete production delivery or implement the suspended-session valuation join. Distinct provider-definition and adapter evidence hashes remain mandatory. |
| `close_observation_type` | provider close/valuation record plus `suspend_d` | **required target contract; canonical join not yet implemented.** `traded_close` iff `is_suspended=false`; `suspension_valuation` iff `is_suspended=true`; provider documentation must prove the value was recorded or published for that exact official session, and the private adapter may not manufacture it by forward-fill |
| `amount`, `amount_unit` | `daily.amount` plus private conversion record | **required target contract; production Stage-2 conversion not yet claimed.** A documented private adapter must convert provider thousand-CNY to CNY before input binding, set exact `amount_unit=CNY` on every row, and retain the raw-unit, multiplier, cutoff, and provenance evidence. The existing component normalizer is not proof that a complete provider delivery was converted. |
| `volume` (optional) | `daily.vol` | convert documented lots to shares; not an IC-core gate |
| `publishDate` | `disclosure_date.actual_date` | preferred over `pre_date` and `disclosure_date.ann_date` for this endpoint; provider confirmation must establish whether it is the first actual public date or a current single-version record, and it is never called first-release/PIT without that evidence |
| `reportPeriodEnd` | `disclosure_date.end_date` | exact report-period key; duplicate periods fail without a vintage schema |
| calendar `date` | `trade_cal` rows for `SSE` and `SZSE` | deterministic candidate intersection of two explicit `is_open=1` rows only; it cannot satisfy the authoritative-calendar gate without written upstream provenance/rights or separate exchange/licensed-source evidence |
| `is_st` | `stock_st` | absence is unknown until a complete date-by-date universe join is reviewed |
| `is_suspended` | `suspend_d` | candidate suspension rows map to true; historical start/completeness must be verified, and absence is not silently false without a complete universe join |
| lifecycle | historical list/master feed | current `stock_basic` alone is insufficient |

The adapter intentionally does not normalize a provider's raw rows into an
investor-observed vintage.  A single-version `roeDiluted` export supports only
the paper's recorded-publication-date specification effect.

## Suspension-evidence contingency before registration

The current target remains the full 18-variant, 72-cell lattice. If the supplier
cannot prove the same-session provenance of `suspension_valuation`, the study stays
`BLOCKED_FOR_STAGE2`; the repository must not relabel a carried-forward value as a
valuation. The only permissible fallback is a prospective amendment **before**
external registration and before any Stage-2 outcome access: remove all eight
factorial variants containing the suspension component, leaving 10 variants
(the two timing/universe comparators plus eight suspension-off factorial variants)
and 40 factor–variant cells. That change requires a newly timestamped and frozen
plan, SAP, manifest, estimand/multiplicity inventory, and authorization. It is not
available after registration or after outcomes have been viewed.

## User actions that remain external blockers

The repository can validate structure and hashes, but it cannot perform these
actions on the user's behalf:

- obtain a qualifying data contract or written permission for local analysis,
  aggregate reporting, exact calendar-date publication, and controlled review;
- obtain credentials/entitlements and quota sufficient for the full historical
  extraction (credentials must remain outside GitHub);
- obtain or generate an authoritative common SSE/SZSE calendar and retain its
  provenance;
- supply complete historical publication dates, lifecycle, ST, suspension,
  adjusted-price and amount semantics;
- create the canonical probe timestamp package, obtain an external timestamp
  for that package, have it independently verified before the first request,
  and later register the full design with the chosen journal/registry;
- sign the human data-review, prior-exposure, and execution-authorization
  attestations.

Until every item is evidenced, the correct status remains
`BLOCKED_FOR_STAGE2`; no shorter interval, substitute calendar, or free-source
snapshot may be promoted after seeing outcomes.
