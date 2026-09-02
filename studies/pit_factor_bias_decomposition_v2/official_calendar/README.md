# Official calendar input contract

Stage 2 requires a separate, authoritative common-session calendar. The repository contains only this contract and no calendar observations. Do not infer sessions from whichever securities happen to have quote rows.

## Input format

The private input is a UTF-8 CSV with exactly one required column:

```csv
date
2009-01-05
2009-01-06
```

Each row represents one official session on which both the Shanghai Stock Exchange and Shenzhen Stock Exchange were open. Dates use ISO `YYYY-MM-DD` in the `Asia/Shanghai` timezone, are unique, and are strictly increasing. Closed dates are omitted. Any SSE/SZSE calendar disagreement is a blocking condition until it is resolved against retained authoritative evidence.

The calendar must include every common session from January 2009 through the end of January 2023, cover every month from January 2010 through December 2022, and provide the fixed positions for all `t`, `t+1`, `t+20`, and `t+21` IC endpoints. Every quote date used by the study must be a member of this calendar. A calendar position does not itself resolve a per-security endpoint: under the current IC adapter an exact adjusted-close quote must exist for the security on every required session. Missing endpoints cannot shift to another quote, use an unattested last price, or receive a default recovery; they make the cell non-estimable and the study `INSUFFICIENT_EVIDENCE`.

## Binding and review

Before the plan core is frozen, an authorized reviewer must record the source name, source reference, extraction or generation timestamp, timezone, byte size, row count, minimum and maximum dates, and SHA-256 of the exact CSV bytes. The same SHA-256 must agree across the data-review attestation, coverage evidence, plan core, design manifest, and execution authorization.

No normalization is allowed after freeze: changing row order, line endings, whitespace, or serialization produces a different input. The external registration binds the design manifest, not an unverified filename.

The machine-readable contract in `calendar.schema.json` defines the tabular and semantic requirements. Structural validation alone cannot prove source authority, chronological ordering, membership completeness, or the conjunction of SSE and SZSE open status; those checks remain explicit review gates.

These contract files do not acquire, register, or use any Stage-2 calendar input.
