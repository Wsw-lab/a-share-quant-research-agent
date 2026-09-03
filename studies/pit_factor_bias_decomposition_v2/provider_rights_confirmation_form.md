# Provider / licensed data administrator rights confirmation

This form records either a provider/licensor's written grant or a licensed
institution administrator's confirmation of permissions already present in
the controlling contract. It is external evidence for the repository's private
`data_rights_attestation`; it does not itself freeze the design, register the
study, or authorize Stage-2 execution.

A provider/licensor may grant a new permission or addendum. A licensed
institution administrator may only confirm rights already present in the
controlling contract unless that contract expressly delegates amendment
authority. An administrator statement cannot supply a right absent from the
licence.

Before completion, save or export a renamed
`provider_rights_confirmation.completed.pdf` copy outside every Git worktree.
Never enter commercial terms, names, signatures, ticket identifiers, or
contract excerpts into this tracked blank form.

## Study and authority

| Field | Response |
|---|---|
| Study ID | `a-share-factor-timing-bias-decomposition-v2` |
| Provider / licensor |  |
| Licensed institution or account class |  |
| Product(s) and dataset(s) |  |
| Contract / terms name and version |  |
| Contract / licence reference |  |
| Effective date and time zone |  |
| Expiry date and time zone |  |
| Authorized confirmer name |  |
| Title and authority to confirm |  |
| Verifiable provider email, ticket, or record URL |  |

## Permission responses

Enter **Yes**, **No**, or **Conditional**. A Conditional response must state the
exact restriction. Silence and informal sales statements are treated as
Unknown and fail closed. Before the private machine attestation can mark a
Conditional permission as granted, an authorized reviewer must separately
record that its conditions are satisfied, the review time, and the SHA-256 of
the supporting evidence. Merely copying a restriction into the attestation is
not sufficient. Give every distinct restriction a unique identifier derived
from the permission-row ID, for example `R-AGG-PUB-01` and
`R-AGG-PUB-02`. Multiple restrictions on one permission remain separate.

In the private machine attestation, each Conditional item is represented by
one `restrictions` object containing its unique `restriction_id`, the exact
dataset boolean `permission` field, and its `description`. It must have exactly
one `conditional_permission_reviews` object with the same `restriction_id` and
`permission`, plus `conditions_satisfied=true`, `reviewed_at`, and
`condition_evidence_sha256`. One review cannot cover two restrictions.
Missing, duplicate, unknown, or permission-mismatched links fail closed, as
does a mapped dataset permission that is not `true`.

| ID | Requested use or output | Required | Response | Controlling clause / written grant | Restrictions |
|---|---|---:|---|---|---|
| R-STORE | Store licensed data in encrypted, access-controlled local or institutional storage | Yes |  |  |  |
| R-ANALYZE | Conduct non-commercial academic analysis for the named study | Yes |  |  |  |
| R-AGG-PUB | Publish aggregate estimates, tables, and figures without raw rows | Yes |  |  |  |
| R-COVERAGE | Publish aggregate date/symbol coverage and non-null rates | Yes |  |  |  |
| R-MISSING | Publish aggregate missingness and endpoint-reason counts | Yes |  |  |  |
| R-HASH | Publish SHA-256 hashes of licensed input files and retained evidence | Yes |  |  |  |
| R-CALENDAR | Publish the exact dates in the official SSE/SZSE common-session calendar | Yes |  |  |  |
| R-REVIEW | Permit an editor/reviewer to reproduce the analysis through provider-issued access or a contract-covered controlled licensed environment | Yes |  |  |  |
| R-SOURCE-DISCLOSE | Name the provider, product, and source table represented in the fixed public Stage-2 declaration projection | Yes |  |  |  |
| R-FIELD-MAP-CITE | Cite or reproduce the exact provider field dictionary/mapping represented in the fixed public Stage-2 declaration projection | Yes |  |  |  |
| R-LEDGER-KEEP | Retain a private per-security endpoint-resolution reason ledger | Yes |  |  |  |
| R-LEDGER-HASH | Bind that private ledger by a publicly reported hash | Yes |  |  |  |
| R-RAW-PUBLIC | Publish raw licensed rows or transfer them to an unauthorized person | **No** |  |  |  |
| R-CREDENTIALS | Share credentials, tokens, cookies, or account access | **No** |  |  |  |

## Dataset applicability

Confirm whether the responses above cover every delivered role. Record any
different upstream licensor, pass-through restriction, source-name
restriction, or field-dictionary restriction against the specific role. The
completed private v2 rights packet must contain the exact public projection
for each role and its canonical SHA-256; the private data declaration must use
the identical four projections. A general statement such as "mapping
approved" is not a field mapping and cannot satisfy this requirement.

| Dataset role | Product / table | Upstream rights owner, if different | Covered by this confirmation? | Exceptions |
|---|---|---|---|---|
| Daily quotes and adjustment data |  |  |  |  |
| Historical listing/delisting master |  |  |  |  |
| Historical ST and suspension states |  |  |  |  |
| Fundamental values and actual disclosure dates |  |  |  |  |
| SSE/SZSE calendars |  |  |  |  |

## Evidence and signature

The research custodian will hash the exact contract/letter bytes and retain
them privately. Do not put confidential contract pages in the public
repository. A No response to either R-SOURCE-DISCLOSE or R-FIELD-MAP-CITE
blocks Stage 2 under the current registered design because the fixed public
result receipt embeds the declaration projection, whose provider-supplied
strings can contain exact source identities and field mappings.

| Field | Response |
|---|---|
| Evidence file name(s) |  |
| Evidence SHA-256 |  |
| Confirmation timestamp with UTC offset |  |
| Confirmation method | signed provider/licensor document; provider ticket; or institutional licence-administrator letter that cites existing contract rights and does not purport to create new rights |
| Authorized signature or provider-controlled verification record |  |

By completing this section, the confirmer states that the responses describe
the named licence and datasets. The research team will not infer any right that
is not explicitly granted.
