# Provider information boundary

This policy applies to data-provider outreach, procurement, rights review, and
delivery records for Stage 2. It prevents research transparency from being
confused with disclosure of negotiations, personal information, contractual
records, or licensed data.

## Public repository

Only provider-neutral research materials belong in GitHub:

- the research protocol and statistical analysis plan;
- canonical field and coverage requirements;
- blank, provider-neutral capability and rights-enquiry forms;
- outcome-blind data-review, coverage-audit, registration, and execution rules;
- synthetic fixtures, public code, and documentation that contain no private
  provider response or licensed row.

Public capability notes may cite public product documentation, but they must
not disclose outreach priority, negotiation position, quotation, private
reply, entitlement, account, contact, or contract content.

## Private, outside every Git worktree

The following working materials must be stored outside Git:

- provider-specific outreach letters and sponsorship pitches;
- researcher identity, affiliation, correspondence address, and signatures;
- provider-contact order and negotiation strategy;
- quotations, commercial options, and provider correspondence;
- completed capability workbooks and completed rights forms.

Private does not mean suitable for arbitrary local storage. Use the approved
access-controlled location, keep the smallest necessary recipient list, and do
not place these files in a public issue, pull request, action log, or receipt.

## Never public

The following must never be committed, attached to a public issue, or copied
into a public research artifact:

- contracts, licence text, amendments, signatures, and legal evidence;
- named provider contacts and their personal contact details;
- account identifiers, entitlement records, cookies, tokens, passwords,
  private URLs, access keys, and delivery credentials;
- raw or sampled licensed data rows and any unauthorized derivative capable of
  reconstructing them;
- private transfer records, extraction logs, and custody evidence.

Any eventual publication of aggregate research results, non-identifying
coverage statistics, or cryptographic hashes is governed separately by the
frozen research plan and the provider's written permissions. This policy never
turns a private procurement record into a public artifact.

## Operating rule

Create the private workspace before drafting a targeted message. The public
repository may link only to the neutral request and blank templates; it must
not link to or name a local private path. If a private item is accidentally
committed, remove it from the current branch immediately, assess whether it
contained secrets or personal data, and decide separately whether Git-history
rewriting and credential rotation are required.
