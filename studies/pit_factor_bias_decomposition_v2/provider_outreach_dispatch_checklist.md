# Provider outreach dispatch checklist

**Purpose:** send an outcome-blind capability and rights enquiry before any
Stage-2 raw data or research outcome is released. Completing this checklist
does not authorize a coverage probe, historical extraction, or Stage-2 run.

Every provider must receive the same interval, field semantics, and rights
questions. Selection may use only documented capability, coverage, semantics,
rights, delivery controls, and commercial feasibility; factor values, returns,
ICs, portfolios, test statistics, and variant rankings must never be compared
to choose a provider. Provider-specific outreach order, negotiation positions,
quotations, and correspondence remain private outside every Git worktree under
`provider_information_boundary.md`.

## 1. Identify the contracting party

Complete these routing fields in the outgoing email or institutional ticket:

- provider or licensed institution legal name: `[required]`;
- product, database, or entitlement name: `[required]`;
- account owner or institutional licence administrator: `[required]`;
- commercial/data contact: `[required]`;
- licence/legal contact: `[required]`;
- sender name, affiliation, and reply address: `[required before sending]`;
- response deadline: `[optional]`;
- approved private response channel: `[required]`.

The recipient must be able either to grant the requested rights or to cite the
controlling agreement. A library or account administrator may not invent a
right absent from that agreement.

## 2. Send only the first-round enquiry package

Attach these unchanged public files:

1. `stage2_data_procurement_request.md`;
2. `provider_rights_confirmation_form.md`;
3. `provider_capability_and_field_mapping.template.xlsx`;
4. `private_data_handoff_instructions.md`;
5. `provider_delivery_acceptance_protocol.md`.

Ask the provider to save a renamed completed workbook outside Git. The first
response may include a quotation, field dictionary, contract/licence text,
entitlement evidence, written permission answers, and a proposed secure
delivery method. It must not include credentials, raw licensed rows, factor
values, returns, ICs, portfolios, test statistics, or variant rankings.

## 3. Reject incomplete or ambiguous replies

Do not treat any of the following as approval:

- a marketing page or endpoint list without entitlement evidence;
- “academic use permitted” without the exact publication and reviewer-access
  permissions requested in the rights form;
- a current-only security master or an undocumented reconstruction of
  historical membership;
- scheduled, expected, or latest-update dates presented as actual disclosure
  dates;
- a carried-forward price relabelled as a same-session suspension valuation;
- software open-source terms presented as a licence to returned market data;
- a generic permission statement that does not bind the exact four dataset
  roles, source names, and complete canonical-to-provider field mappings.

Any `Conditional` answer must have a unique restriction ID, controlling
permission field, satisfaction evidence, reviewer, and review time. Any `No`
for provider/source-name publication or field-mapping citation blocks the
current public Stage-2 design.

## 4. Intake sequence after a satisfactory paper response

1. A rights reviewer completes a private copy of
   `data_rights_attestation.template.json` and binds the returned evidence by
   SHA-256.
2. A data custodian creates a new private directory outside every Git worktree
   and records the closed delivery manifest before any audit.
3. The provider transfers the four contracted datasets through the approved
   encrypted channel. Raw data are never emailed or committed to GitHub.
4. The custodian runs only the metadata diagnostic and authoritative coverage
   audit. Research outcomes remain sealed.
5. Only after coverage and human review pass may the separate probe timestamp,
   external registration, and execution-authorization sequence begin.

## 5. Dispatch record

Keep the completed record privately; do not commit contact details, account
identifiers, contract numbers, private URLs, or signatures.

| Field | Private value |
|---|---|
| Sent at, including time zone | `[required]` |
| Recipient legal entity | `[required]` |
| Recipient role | `[required]` |
| Outgoing message/evidence SHA-256 | `[required]` |
| Attachment-set manifest SHA-256 | `[required]` |
| Ticket/message identifier | `[required]` |
| Expected response date | `[optional]` |
| Custodian | `[required before data delivery]` |
