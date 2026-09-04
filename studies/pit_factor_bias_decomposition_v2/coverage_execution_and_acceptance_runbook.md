# Stage 2 Coverage Execution and Acceptance Runbook

## Purpose and decision

This runbook is the operator procedure for deciding whether a contracted data delivery can support the frozen 2010-2022 Stage-2 design. The repository already contains the authoritative execution code in `a_share_quant_agent.data_access` and `a_share_quant_agent.study_v2_coverage`; this document does not define a second coverage implementation.

The procedure may inspect schemas, dates, identifiers, field values needed for type and finiteness checks, exact-session presence, lifecycle consistency, fixed aggregate coverage counts, and documentary rights evidence. It must not calculate, retain, display, or rank factor values, forward returns, information coefficients, portfolio outcomes, test statistics, or variant comparisons. A failed check stops the design. It does not authorize a shorter sample, a lower threshold, or a different factor after results have been viewed.

## Required private inputs

The custodian prepares four canonical UTF-8 CSV files outside every Git worktree:

1. `quotes.csv` with `date`, `symbol`, `close_raw`, `adjustment_factor`, `close`, `price_adjustment_method`, `price_adjustment_convention`, `close_observation_type`, `amount`, `amount_unit`, `is_st`, and `is_suspended`;
2. `stock_master.csv` with `symbol`, `listDate`, `delistDate`, `listStatus`, and `stockType`;
3. `fundamentals.csv` with `symbol`, `roeDiluted`, `publishDate`, and `reportPeriodEnd`; and
4. `official_calendar.csv` with one common SSE and SZSE session `date` per row.

Provider-native fields must be normalized before these files are hashed. The provider's original files, normalization code, field map, evidence, completed rights attestation, completed review attestation, and every generated audit stay private. No tracked template may be overwritten with provider information.

The canonical quote contract is exact. Every quote row uses `amount_unit=CNY`, `price_adjustment_method=close_equals_close_raw_times_adjustment_factor`, and `price_adjustment_convention=provider_cumulative_backward_adjusted_hfq_no_rebasing`. It must also satisfy `close=close_raw*adjustment_factor` within absolute and relative tolerance `1e-12`. A non-suspended row uses `close_observation_type=traded_close`; a suspended row uses `close_observation_type=suspension_valuation`. Human evidence must show that each suspension valuation is a supplier-recorded or supplier-published value for that exact official session. Researcher forward-filling is prohibited.

## Runtime and private directories

Use a clean checkout and a Python version allowed by the repository. The eventual registered Stage-2 run is locked to its manifest runtime; do not assume that a successful coverage audit changes that runtime lock.

Create a private working directory that is outside every Git worktree, including this repository, linked worktrees, an unrelated repository, and the QData checkout. Each command below writes to a new filename and refuses to overwrite an existing file. Adding a path to `.gitignore` does not make a directory private for this purpose.

The examples use `/secure/stage2-intake` only as a non-repository illustration. The operator must replace it with an authorized local path and must not publish the resolved path.

## Pass A Metadata and rights audit

Run the outcome-blind intake audit first:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m a_share_quant_agent.data_access \
  --quotes /secure/stage2-intake/quotes.csv \
  --stock-master /secure/stage2-intake/stock_master.csv \
  --fundamentals /secure/stage2-intake/fundamentals.csv \
  --official-calendar /secure/stage2-intake/official_calendar.csv \
  --rights-attestation /secure/stage2-intake/data_rights_attestation.json \
  --output /secure/stage2-intake/audit/data_access_metadata.json \
  --fail-on-blocked
```

Exit code `0` means the metadata and supplied rights packet passed this diagnostic. Exit code `2` means the output was written but at least one metadata or rights condition remains blocked. An exception or missing output means the audit itself did not complete. Even a `pass_metadata_only` status is not final data acceptance and does not authorize result access.

Review only the audit status, schema findings, malformed or duplicate-key counts, required-field completeness, date ranges, boolean and numeric typing, source-mapping status, and rights reasons. Do not join these rows to future outcomes or construct factors during intake.

## Pass B Authoritative fixed-design coverage audit

### Preliminary coverage report

Run the fixed design audit without a completed review attestation to produce the evidence that the human reviewer needs:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m a_share_quant_agent.study_v2_coverage \
  --quotes /secure/stage2-intake/quotes.csv \
  --stock-master /secure/stage2-intake/stock_master.csv \
  --fundamentals /secure/stage2-intake/fundamentals.csv \
  --official-calendar /secure/stage2-intake/official_calendar.csv \
  --minimum-history-years 13 \
  --minimum-publish-date-rate 0.95 \
  --minimum-monthly-observations 156 \
  --minimum-symbols-per-month 1000 \
  --minimum-sessions-per-month 15 \
  --analysis-start 2010-01-01 \
  --analysis-end 2022-12-31 \
  --required-quote-start 2009-01-01 \
  --required-quote-end 2023-01-31 \
  --required-fundamental-start 2009-01-01 \
  --required-fundamental-end 2022-12-31 \
  --output /secure/stage2-intake/audit/coverage_pre_review.json
```

Exit code `1` and status `BLOCKED` are expected before the human review exists. This preliminary file may establish structural coverage and enumerate remaining reason codes, but it cannot pass `ready_to_lock_stage2_plan`.

The reviewer uses the exact input hashes, byte sizes, row counts, date boundaries, and calendar provenance from the preliminary report to prepare a private copy of `data_review_attestation.template.json`. The reviewer must inspect provider definitions, licence terms, historical membership completeness, actual publication-date meaning, amount normalization, identifier stability and code changes, adjusted-close semantics, exact endpoint handling, ST and suspension history, supplier-recorded suspension valuations, calendar provenance, aggregate publication rights, endpoint-ledger retention, and controlled reviewer access. Every evidence hash and assertion must be supported; a generic approval sentence is insufficient.

### Final reviewed coverage report

Run the same audit against the same four files with the completed attestation and a new output filename:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m a_share_quant_agent.study_v2_coverage \
  --quotes /secure/stage2-intake/quotes.csv \
  --stock-master /secure/stage2-intake/stock_master.csv \
  --fundamentals /secure/stage2-intake/fundamentals.csv \
  --official-calendar /secure/stage2-intake/official_calendar.csv \
  --minimum-history-years 13 \
  --minimum-publish-date-rate 0.95 \
  --minimum-monthly-observations 156 \
  --minimum-symbols-per-month 1000 \
  --minimum-sessions-per-month 15 \
  --analysis-start 2010-01-01 \
  --analysis-end 2022-12-31 \
  --required-quote-start 2009-01-01 \
  --required-quote-end 2023-01-31 \
  --required-fundamental-start 2009-01-01 \
  --required-fundamental-end 2022-12-31 \
  --review-attestation /secure/stage2-intake/review/data_review_attestation.json \
  --output /secure/stage2-intake/audit/coverage_reviewed.json
```

Exit code `0`, printed status `READY`, and `gates.ready_to_lock_stage2_plan=true` are all required. Exit code `1`, `BLOCKED`, any false gate, or any nonempty `blocking_reason_codes` list stops design freeze. A shell success alone is insufficient; the operator must retain and hash the exact canonical report bytes.

## Acceptance matrix

| Dimension | Fixed acceptance criterion | Report or review evidence | Failure action |
|---|---|---|---|
| Quote interval | Exact official-session support from 2009-01 through 2023-01, including the last 20-session horizon | `target_quote_interval_available`; required session start and end | Stop |
| Historical analysis panel | First common official session for all 156 months from 2010-01 through 2022-12 | `expected_analysis_month_count=156`; `target_observed_month_count=156`; no missing months | Stop |
| Monthly session density | At least 15 quote dates that are members of the bound official calendar in every target month | `minimum_sessions_per_month_met` | Stop |
| Exact candidate endpoints | Every lifecycle-eligible signal-session candidate with a close observation has rows at `t`, `t+1`, `t+20`, and `t+21` | `all_signal_session_candidates_have_exact_endpoints` | Stop; do not chase a later quote or drop a security |
| Complete quote contract | At least 1,000 strict SH or SZ A-share identifiers per month have every required `t-60..t`, `t-20..t`, `t-19..t`, and endpoint row | `minimum_symbols_per_month_met`; `complete_quote_contract_coverage_met` | Stop |
| Publication dates | At least 95 percent valid recorded publication dates among otherwise usable fundamentals; no publication date precedes its report-period end | `publication_date_coverage_met`; both publication-order integrity gates | Stop |
| Fundamental continuity | Nonstale eligible `roeDiluted` support exists in every target month and intersects the complete quote contract | four fundamental interval, continuity, staleness, and joint-support gates | Stop |
| Historical membership | Master is not latest-only and covers every strict A-share active during the required interval with coherent list, delist, status, and type fields | `point_in_time_membership_available`; `historical_membership_completeness_verified` | Stop |
| Terminal-survivor comparator | A0 uses listing by each signal session and `delistDate` null or strictly after 2023-01-31, independent of acquisition date | `terminal_survivor_comparator_verified` | Stop |
| Identifier history | Quotes, master, and fundamentals use the same stable exchange-qualified identity, with every code change or reassignment reviewed before hashing | `security_identifier_contract_verified` plus evidence hashes | Stop |
| Official calendar | Unique, strictly increasing common SSE and SZSE sessions cover 2009-01 through 2023-01; every quote date is a member | calendar integrity, interval, membership, and human-review gates | Stop |
| Price adjustment | Positive finite `close_raw` and `adjustment_factor`; exact method and convention tokens; row-wise formula within `1e-12` | `price_adjustment_contract_met`; `price_adjustment_semantics_verified` | Stop |
| Amount | Every quote amount is finite, nonnegative, normalized to exact CNY, and documented before input hashing | `canonical_amount_unit_met`; `amount_unit_normalization_semantics_verified` | Stop |
| ST and suspension | Both boolean fields are complete, valid, historically effective, and non-degenerate | quote boolean and tradability gates | Stop |
| Close observation | `traded_close` iff non-suspended and `suspension_valuation` iff suspended; both types occur among signal-session candidates | close-observation contract and non-degeneracy gates | Stop |
| Suspension valuation provenance | Provider evidence proves same-session recorded or published valuation and no researcher forward-fill | `suspension_valuation_semantics_verified` plus evidence hash | Stop; the 18-variant design remains blocked |
| Input integrity | No malformed CSV rows, duplicate logical keys, invalid canonical dates, invalid symbols, missing required values, or non-finite numeric values | structural, uniqueness, format, and numeric gates | Stop |
| Data rights | Local analysis, aggregate output, required source and field-map citation, calendar publication, hashes, private endpoint ledger, and controlled review are expressly permitted | completed rights packet and `data_rights_verified` | Stop |
| Human review | Reviewer identity, authority basis, timezone-aware chronology, exact file identities, evidence hashes, assertions, and signature all validate | completed `stage2_data_review_attestation_v1` | Stop |
| Revision claim | No revision or vintage conclusion unless a separately validated revision-vintage adapter exists | `revision_history_claim_allowed` | Keep the revision claim excluded; this does not block the current single-version timing design |

## Outcome-blind review boundary

The coverage decision may reveal whether required data exist and how many identifiers satisfy fixed presence rules. It must not reveal whether ROE predicts returns or which implementation variant performs best. The following items are prohibited before external registration and authorization:

- factor construction or cross-sectional ranks;
- forward-return values or summaries;
- ICs, t-statistics, p-values, confidence intervals, portfolio spreads, or Sharpe ratios;
- comparisons among A0, A1, or any `Ixxxx` variant;
- changing the study interval, thresholds, factors, direction, or reporting family in response to an observed outcome; and
- copying private audit details into Git without a separate rights-reviewed export mechanism.

The preliminary and final audit reports contain exact hashes, byte sizes, date extrema, and detailed aggregate counts. Both remain private even if the provider permits publication of some later aggregate results. The design manifest binds their exact SHA-256 values after review.

## Decision record

Only the final reviewed report can support the statement that the data gate passed. Record one of two outcomes:

- `READY_FOR_DESIGN_FREEZE`: every fixed gate is true, the blocking-reason list is empty, the exact report and attestation bytes are retained privately, and their hashes have been independently checked; or
- `BLOCKED_FOR_STAGE2`: at least one gate failed, evidence is missing, rights are conditional but unresolved, or the audit did not complete.

Neither outcome is a research result. A `READY_FOR_DESIGN_FREEZE` decision permits the prior-exposure attestation and design-manifest sequence; it does not permit Stage-2 execution.
