# Responsible use

English | [日本語](RESPONSIBLE_USE.ja.md)

Latent Trace Tomography is intended for authorized model evaluation, research,
incident diagnosis, and governance.

## Required authorization

Use a target only when you own it, operate it, have explicit permission to
audit it, or are using a public endpoint in a manner allowed by its documented
terms. Do not bypass authentication, rate limits, safety controls, billing
controls, or technical restrictions. Do not use this project to extract model
weights, secrets, private chain of thought, training records, or personal data.

## Data handling

Prompts and outputs may contain confidential, regulated, copyrighted, or
personal information. A live deployment must define:

- collection purpose and lawful/contractual basis
- retention and deletion periods
- encryption at rest and in transit
- role-based access to raw evidence
- redaction rules for public artifacts
- an allowlist of provider response fields
- removal of credentials, cookies, and authorization headers before storage

A SHA-256 manifest provides integrity, not confidentiality or access control.

## Reporting boundary

Report observable response surfaces, calibrated equivalence classes,
uncertainty, and abstention reasons. Do not present output-only inference as
proof of a private internal circuit, hidden thought, mental state, or intent.

For high-stakes medical, legal, financial, employment, education, safety, or
critical-infrastructure decisions, this instrument is supporting evidence only.
Require domain review and an appeal/escalation path.

## Dual-use review

Active querying can also fingerprint models or inference stacks. Before a live
study, document why the query plan is necessary, minimize its budget, disclose
the audit to the target owner when appropriate, and assess whether publishing
exact probes would enable abuse. Coordinated disclosure takes precedence over
public release of a sensitive endpoint fingerprint.
