# A-share Research Auditor implementation plan

## Context

Turn the public repository into an installable, deterministic research auditor
that consumes frozen QData snapshots and cannot use completed daily bars for a
same-bar fill.  Legacy local reports are evidence records only, not public
performance claims.

## Global Constraints

- Work only on `codex/reproducible-research-chain`; do not push or publish.
- Formal daily timing is `t close signal -> t+1 raw open fill`.
- Critical PIT/tradability fields fail closed; no optimistic `False`/`NaT`
  defaults on the snapshot path.
- Every behavior change has a regression test, written and observed failing
  before the production change.
- Public demos are deterministic and require neither network nor licensed data.
- Do not fabricate historical commits or claim legacy metrics are reproducible.
- Preserve unrelated user work and avoid destructive commands.

## Task 1: Repair the core package and daily execution model

- Add Python packaging and complete minimum runtime dependencies.
- Supply a deterministic sample dataset and a real example strategy spec so the
  public demo runs from a fresh checkout.
- Change the default engine to after-close decisions with next-session open
  fills, including blocked fills, T+1 behavior, and unfilled final signals.
- Fix price-limit fallback precedence and map QData snake_case stock-master
  fields explicitly.
- Add focused tests for timing, price limits, T+1, and lifecycle mappings.
- Verify the focused suite and public demo.

## Task 2: Add the strict QData snapshot adapter

- Read and verify `research_snapshot_v1` manifests and file hashes.
- Explicitly map and join prices, tradability, security membership, and PIT
  fundamentals by their contract keys.
- Reject unknown schemas, duplicates, hash changes, late availability, and
  missing critical constraints.
- Preserve snapshot ID, dataset versions, and source lineage in load metadata.
- Add consumer-driven tests using the deterministic QData fixture.

## Task 3: Add a reproducible cross-repository experiment

- Run one deliberately small baseline against a frozen synthetic snapshot.
- Emit a canonical experiment receipt with both repository SHAs, snapshot ID,
  config hash, timing rule, costs, environment information, and verdict.
- Re-run and prove deterministic trades and metrics hashes.
- Emit a failure card; the fixture result is not a performance claim.

## Task 4: Align public documentation and CI with verified behavior

- Replace the oversized README with a short capability matrix and one green
  fresh-clone path.
- Move legacy result claims behind explicit non-reproducible labels and remove
  local absolute paths from tracked artifacts.
- Add CI for packaging, tests, demo, README-link checks, and cross-contract
  fixture verification.
- Add project boundaries, known limitations, and ADR links.

## Task 5: Whole-branch verification and review

- Run the full Agent suite, fresh-install demo, cross-repository reproduction,
  static path/reference checks, and git diff checks.
- Review for look-ahead, fail-open behavior, accidental data claims, secrets,
  and unrelated edits.
- Prepare local commits on the feature branch only; do not push or merge.
