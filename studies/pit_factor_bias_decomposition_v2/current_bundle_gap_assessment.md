# Current licensed bundle: Stage-2 gap assessment

**Decision:** `BLOCKED_FOR_STAGE2`<br>
**Assessment date:** 1 September 2026

The retained `current_bundle_coverage.json` is a legacy three-file diagnostic hash-bound to the local pilot inputs. It predates the mandatory official-calendar input and the strict `roeDiluted` adapter, so the current four-input validator will reject it rather than treat it as an executable Stage-2 gate. Its descriptive counts confirm that the bundle can support the disclosed short pilot but cannot support the journal protocol.

## Verified coverage

| Dataset | Coverage | Scale | Stage-2 interpretation |
|---|---|---:|---|
| Daily quotes | 3 Jan 2023-24 Jul 2026 | 3,894,242 rows; 4,735 symbols | No quote coverage for the fixed 2009 warm-up or 2010-2022 primary interval |
| Stock master | Listing dates from 1 Dec 1990; delist dates through 17 Jul 2026 | 4,924 symbols; 333 marked delisted | Supports SH/SZ membership reconstruction; no Beijing Stock Exchange |
| Fundamentals | Report periods 2020Q1-2026Q2; publication dates 8 Apr 2020-24 Jul 2026 | 99,628 rows; 4,795 symbols | Supports first-publication timing only; history is too short for the target panel |

The legacy coverage audit reports complete column presence under its older three-file schema and a 100% non-null publication-date rate in the normalized fundamental file. Those facts do not establish revision vintages, historical data correctness, adjusted-close return semantics, or any future portfolio execution semantics. In particular, the old diagnostic's inspection of `open` and `volume` does not make either field an IC-core requirement.

## Hard blockers

1. **The fixed primary quote interval is absent.** The design requires a 2009 warm-up, all 156 monthly rebalances from January 2010 through December 2022, and forward prices through January 2023. The current quote file starts on 3 January 2023, so it cannot contribute Stage-2 return outcomes.
2. **The fixed fundamental interval is incomplete.** The fundamental file begins at the 2020Q1 report period. It contains outcome-blind feasibility information for the final part of the target interval but not publication-dated fundamentals from 2009 onward.
3. **No bound official exchange calendar.** The current bundle has no separately sourced, authoritative common SSE/SZSE calendar covering January 2009 through January 2023. Quote dates therefore cannot yet be proved to be official sessions, and monthly rebalance and t+20 endpoints cannot be authorized.
4. **The retained fundamental diagnostic is not a runner input.** It uses a normalized `roe` column, whereas the strict Stage-2 adapter requires the provider's raw `roeDiluted` field, decimal-unit documentation, and a hash-bound mapping to normalized `roe`.
5. **IC-return semantics are not independently attested.** The current declaration permits vendor-adjusted prices for factor-return research but does not independently document adjusted-close construction, corporate-action handling, or the fixed official-session endpoints. The quote file's `open` and `volume` columns are not IC-core requirements; their unadjusted execution meaning would matter only for the planned portfolio extension.
6. **The registered suspension field may be uninformative.** ST has positive observations, but the suspension flag contains no positive observations. Roughly 10,054 symbol-days are missing inside observed listing lifecycles, but no field definition proves that missing rows encode suspension. The suspension component may therefore be degenerate on this bundle. Price-limit levels and nonfill semantics belong to the planned portfolio extension and do not form an IC-core gate.
7. **Upstream historical retrieval is unproven.** Existing cache manifests show only a 43-symbol quote probe from 2021 and financial requests from 2020. The data-source code also floors financial retrieval at 2020. The immutable `coverage_probe_spec.v1.json` therefore fixes an outcome-blind 2016/2018 price probe, but it must not run until the spec is included in a committed, externally timestamped revision. Even a successful probe would establish only price-row availability, not fundamentals, execution semantics, or data rights.
8. **No completed review attestation.** The current diagnostic has no hash-bound approval of adjusted-close return semantics, ST/suspension-field informativeness, official-calendar provenance, rights to publish aggregate results, or rights to embed exact official-calendar session dates in a receipt. Those IC-core gates remain false even though some column names are present.

## Claim boundary, not an IC-core blocker

The raw and normalized fundamental schemas contain no `revision_id`, `first_seen_at`, `available_at`, restatement flag, or historical vintage value. Each symbol-report-period has one row. This prohibits any revision-history claim, but revision-history analysis is outside the registered IC core and its absence does not itself block that narrower study.

## Minimum acquisition sequence

1. Commit and externally timestamp `coverage_probe_spec.v1.json`; only then run its bounded, outcome-blind fixed-symbol probes for 2016 and 2018, without changing dates or symbols after observing responses.
2. For the IC core, confirm adjusted-close construction, corporate-action handling, amount units and timing, publication timestamps, ST/suspension semantics, and redistribution rights. Review unadjusted open, volume, price-limit, and nonfill semantics only if the planned portfolio extension is later implemented and separately frozen.
3. If probes pass, obtain the complete SH/SZ quote panel from January 2009 through January 2023 and publication-dated fundamentals beginning in 2009. Do not substitute the already observed 2023-2026 pilot interval.
4. Store an immutable request and response manifest for each extraction: query interval, retrieval timestamp, source, schema, raw hash, normalized hash, annual coverage, and failures.
5. Cross-check a pre-specified random sample of publication dates, delisted securities, and corporate-action adjustments against a second authorized source.
6. Re-run the outcome-blind coverage and field-informativeness audits with the fixed 2010-2022 target. Every one of the 156 target months must have at least 15 official sessions and 1,000 quoted symbols. Only then may the plan core be frozen, followed in order by the design manifest, external registration receipt, execution authorization, and final execution envelope.
7. After authorized execution, apply the separate evidence-eligibility stop: every registered factor-variant cell in every target month must contain at least 1,000 finite signal-outcome pairs. Failure yields `INSUFFICIENT_EVIDENCE`; it does not reopen the design or permit a shorter sample.

If the study is expanded to actual data-revision history, a normal backfill is insufficient. The data must contain historical `published_at`, `first_seen_at` or `available_at`, a revision identifier, restatement state, filing identifier, and the value observed at each vintage.
