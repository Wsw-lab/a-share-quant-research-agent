# Stage-2 historical data acquisition and rights plan

**Current decision: `BLOCKED_FOR_STAGE2` (data and rights not yet attested).**

This document turns the three outstanding data tasks into an executable,
outcome-blind intake sequence.  It is a procurement and metadata plan, not a
claim that any source has already been acquired.  No factor value, forward
return, rank, IC, portfolio result, or variant ordering may be inspected while
the steps below are being completed.

## The fixed input contract

The primary panel is fixed before any historical outcome analysis:

| Role | Required interval | Required fields | Additional semantic evidence |
|---|---|---|---|
| Daily quotes | 2009-01-01 through 2023-01-31 | `date`, `symbol`, `close`, `amount`, `is_st`, `is_suspended` | `close` must be explicitly adjusted close; amount units and cutoff timing; exact `t`, `t+1`, `t+20`, `t+21` rows |
| Stock master | lifecycle history covering the target panel | `symbol`, `listDate`, `delistDate`, `listStatus`, `stockType` | current and delisted SH/SZ A-shares; valid list/delist chronology |
| Fundamentals | publication records beginning 2009-01-01 through 2022-12-31 | `symbol`, `roeDiluted`, `publishDate`, `reportPeriodEnd` | `publishDate` is actual disclosure date; no scheduled-date substitution; no publication-before-report rows |
| Common calendar | 2009-01 through 2023-01 | one `date` column | every row is an authoritative common SSE/SZSE open session; exact bytes and provenance hash-bound |

The current runner supports only exact adjusted-close endpoints on the bound
calendar.  It does not carry a suspended price forward, invent a delisting
terminal value, or move to the next observed quote.  A complete private
per-security endpoint-reason ledger is therefore required after authorized
execution, but its rows are never committed to GitHub.

## Source decision matrix

The machine-readable version is
[`source_capability_matrix.json`](source_capability_matrix.json).  The short
decision is:

1. **Preferred primary:** a licensed institutional vendor (for example Wind,
   CSMAR, Choice, or an equivalent provider) whose contract explicitly covers
   the full historical range, point-in-time lifecycle and filing fields,
   adjusted prices, local research, aggregate publication, and controlled
   reviewer access.  Vendor names are alternatives, not evidence that a
   contract is held.
2. **Viable candidate subject to a written contract:** Tushare Pro exposes
   historical daily bars (`daily`), adjustment factors (`adj_factor`),
   exchange-specific calendars (`trade_cal`), stock lists (`stock_basic` and
   `bak_basic`), ST history (`stock_st`), suspension history (`suspend_d`),
   and filing dates (`disclosure_date`).  The service documentation states
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
   publication rule, hash/metadata rule, and controlled-review rule.  Fill
   [`data_rights_attestation.template.json`](data_rights_attestation.template.json)
   only after a human reviewer has read the terms.  Never put a token or cookie
   in the repository or in a receipt.
2. **Bounded source probe.** Use the already frozen
   `coverage_probe_spec.v2.json` exactly as written.  First obtain an external
   timestamp for the commit containing that file and the prior-specification
   inventory.  Then run only the 12 fixed symbols on the two fixed dates.  The
   probe checks request scope and raw field reachability; it cannot authorize a
   full extraction or establish factor evidence.  The repository's provider
   normalizers are pure frame adapters and do not make network requests.
3. **Calendar assembly.** Retrieve separate SSE and SZSE rows for every date
   from January 2009 through January 2023.  Keep the raw exchange responses and
   terms evidence privately.  Form the intersection only when both exchanges
   explicitly report open; fail closed on a disagreement.  Export the exact
   one-column UTF-8 CSV required by `official_calendar/calendar.schema.json`.
4. **Historical panel extraction.** Extract daily raw bars and adjustment
   factors for all strict SH/SZ A-shares, then join on exact symbol/date keys to
   create adjusted close.  Extract lifecycle membership, ST and suspension
   states, amount, and actual filing dates in separate immutable batches.  Do
   not use a latest-only stock list to reconstruct historical membership.
5. **Metadata-only coverage audit.** Run the independent metadata scanner in
   `a_share_quant_agent.data_access` over the four files.  It records exact
   bytes, hashes, row counts, date ranges, key duplicates, non-null rates, and
   ST/suspension distinct values without reading factor outcomes.  The scanner
   canonicalizes date keys (so `YYYYMMDD` and `YYYY-MM-DD` duplicates cannot
   hide), rejects malformed CSV row widths, requires explicit `true` and
   `false` states (with no third/unknown value) for ST/suspension fields, and reports strict lifecycle
   checks (recognized active/delisted status, A-share type, non-null delist
   dates for delisted rows, no active row with a delist date, and chronology).
   Calendar rows must be strictly increasing; actual filing dates and numeric
   quote fields are validated by the pure provider adapters.  Then run the
   existing Stage-2 coverage audit with the human data-review attestation.
6. **Independent spot checks.** Before registration, compare a pre-specified
   random sample of adjusted prices, listing/delisting dates, actual filing
   dates, ST states, suspension rows, amount units, and calendar dates against a
   second authorized source.  Record only aggregate pass/fail counts and hashes
   in public evidence.
7. **Registration and authorization.** Only after the metadata gates pass:
   `prior-exposure attestation → frozen plan → design manifest → external
   registration receipt → execution authorization → one Stage-2 run`.

## Provider-specific field mapping

For a Tushare candidate, the following mapping is fixed and implemented in the
pure adapter module:

| Canonical field | Provider field(s) | Rule |
|---|---|---|
| `close` | `daily.close × adj_factor.adj_factor` | exact key join; missing/non-positive factor fails closed |
| `amount` | `daily.amount` | convert documented thousand-CNY units to CNY; retain unit evidence |
| `volume` (optional) | `daily.vol` | convert documented lots to shares; not an IC-core gate |
| `publishDate` | `disclosure_date.actual_date` | scheduled `pre_date` and latest `ann_date` are never substitutes |
| `reportPeriodEnd` | `disclosure_date.end_date` | exact report-period key; duplicate periods fail without a vintage schema |
| calendar `date` | `trade_cal` rows for `SSE` and `SZSE` | intersection of two explicit `is_open=1` rows only |
| `is_st` | `stock_st` | absence is unknown until a complete date-by-date universe join is reviewed |
| `is_suspended` | `suspend_d` | suspension rows map to true; absence is not silently false without evidence |
| lifecycle | historical list/master feed | current `stock_basic` alone is insufficient |

The adapter intentionally does not normalize a provider's raw rows into an
investor-observed vintage.  A single-version `roeDiluted` export supports only
the paper's recorded-publication-date specification effect.

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
- obtain an external timestamp for the frozen probe specification and register
  the design with the chosen journal/registry;
- sign the human data-review, prior-exposure, and execution-authorization
  attestations.

Until every item is evidenced, the correct status remains
`BLOCKED_FOR_STAGE2`; no shorter interval, substitute calendar, or free-source
snapshot may be promoted after seeing outcomes.
