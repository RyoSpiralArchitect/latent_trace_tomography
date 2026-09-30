# OSS-1 execution playbook

Status: `post_freeze_operational_companion`

Parent protocol SHA-256:
`5c49316503b2cec2ad26d4bf47dc59c02f0b61d9f6896b84035e6d0412dced11`

Parent design-manifest SHA-256:
`8c974390ceea3f1defaae19067359c909b4182dd26c321075c9e25ee1518e64b`

Required pre-outcome correction:
`oss1_pre_outcome_correction_0002_minimal_site_report_cardinality`

Required correction-manifest SHA-256:
`4d2282f761c75cfc5b3cd9dcb36ddb624b8982c0eed9076f3a70bf9498787e3a`

Authorization effect: `none`

OSS model calls represented by this document: `0`

## Purpose and authority boundary

This playbook translates the frozen OSS-1 contracts into an execution state
machine. It is not a sixth scientific freeze surface, does not select a model,
and does not authorize a forward pass. If prose here conflicts with a frozen
JSON contract or executable validator, the frozen artifact and executable
validator prevail.

The playbook has three jobs:

1. make the only legal phase order explicit;
2. define the evidence needed to cross each gate;
3. make abort, retry, preservation, and claim-narrowing behavior deterministic.

The following artifacts remain distinct:

| Artifact | Role | Can authorize calls? |
|---|---|---:|
| parent design freeze | scientific design and claim ceiling | no |
| pre-outcome correction 0002 | minimally repairs live site-report cardinality validation | no |
| dependency-cluster registry | pre-discovery evidence and authorization projection | no |
| discovery authorization | exact bounded site-discovery authority | discovery only |
| site-discovery report | immutable discovery evidence and selected sites | no |
| execution lock | exact post-discovery collection authority | named phases only |
| sealed fold authorization | private post-output fitting/scoring authority | no model calls |

No lower row can retroactively change an upper row.

## Non-negotiable preconditions

- The original 37-asset design manifest remains byte-identical.
- Correction 0002 validates and its parent hashes match the original freeze.
- The dependency-cluster registry closes before a discovery authorization is
  issued.
- The registry is an evidence view of the frozen authorization fields, not a
  second split authority.
- `dependency_cluster_id` means a connected component of declared learned-state
  ancestry. It does not mean proven statistical independence.
- Unknown learned-state dependence causes conservative clustering or exclusion;
  it may never split a component or increase effective sample size.
- Training-seed, training-data, and task overlap are recorded as common
  influences. A different seed or checkpoint is never treated as proof of
  independence.
- No real model or API call occurs while discovery authorization remains
  unassigned.

## State machine

### S0 — Parent freeze and correction verification

Required evidence:

- call-free parent preflight reports `ok=true`, `design_ready=true`, and
  `external_calls=0`;
- parent protocol and design-manifest hashes match the values above;
- correction 0002 manifest closes every correction asset;
- the successor site-report schema has no fixture-only `maxItems=1728`;
- the frozen semantic report validator remains byte-identical.

Stop immediately if any parent asset drifts. Do not repair a parent file in
place.

### S1 — Dependency-cluster registry closure

Populate one evidence bundle conforming to
`dependency_cluster_registry.schema.json`, then run
`validate_dependency_cluster_registry`.

The bundle must retain:

- parent hashes for the frozen protocol, design manifest, discovery template,
  and correction-0002 manifest, not correction ID alone;
- every candidate considered before authorization, including excluded or
  unresolved candidates;
- exactly nine eligible model units in the authorization projection;
- complete declared learned-state parent inventory for eligible units;
- the exactly derived graph and three connected components;
- one semantic, one surface-cue, and one mixed anchor per component;
- all 36 unordered pairwise relatedness assessments among the nine units;
- checkpoint, initialization/RNG, training-data, task, and evaluation-exposure
  evidence;
- a binding map whose materiality is derived from actual claim use and that
  distinguishes direct projection-bound, registry-body-bound, and genuinely
  supplementary evidence;
- the explicit statement `independence_certified=false`;
- a canonical self-hash over the registry body.

An exact prompt, generator artifact, or template exposure makes the affected
unit ineligible. Unknown evaluation exposure remains unresolved. A
`no_overlap` claim requires a complete content-addressed scan; partial evidence
may only say `unknown`.

GO condition: the registry validates and its authorization projection contains
three balanced dependency clusters with effective `n=3`.

This GO condition does not certify globally complete provenance.

### G1 — Concrete discovery authorization

Build a new content-addressed discovery authorization from the exact registry
projection plus the remaining frozen runtime, tokenizer, carrier, live-material,
candidate-site, environment, and budget fields.

Before publishing it:

1. require exact equality between the registry projection and authorization via
   `validate_registry_authorization_projection`; this authoring check is not
   the final registry gate;
2. validate the complete authorization and open its live-material commitment
   with frozen `validate_discovery_readiness(..., authority_secret=...)` and
   the trusted parent hashes;
3. verify every-transformer-block candidate inventory closure;
4. atomically write the final bytes and canonical SHA-256;
5. preserve the authority secret outside every auditor realm.

Fail closed for ancestry ambiguity, missing candidate blocks, tokenizer/carrier
incompatibility, query-budget mismatch, environment drift, invalid secret
opening, or any field not fixed before the first forward pass.

### G1b — Current registry-authorization gate receipt

Projection equality is necessary but is not sufficient to cross the first-
forward boundary. After the registry and the concrete discovery authorization
have both reached their final bytes, the authority must create a current
registry-authorization gate receipt that binds exactly:

- the validated registry's `registry_body_sha256`;
- the canonical artifact SHA-256 of the exact concrete discovery authorization.

Through those two hashes, the receipt also transitively fixes the parent
protocol, design-manifest, correction-0002-manifest, discovery-template, and
execution-template identities used by the readiness check.

The receipt body is authenticated with the authorization's committed,
authority-held secret under the dedicated HMAC domain
`ltt:registry-authorization-gate-receipt:v1`, and the complete receipt is
content-addressed by canonical SHA-256. The secret remains outside every runner
output and auditor realm. The registry and authorization hashes transitively
bind the parent protocol, design-manifest, correction-0002-manifest, discovery-
template, and execution-template identities rather than copying those fields
into a second authority surface.

Immediately before the first forward pass, the authority must revalidate the
registry, its exact authorization projection, the concrete authorization with
`validate_discovery_readiness(..., authority_secret=...)`, the receipt HMAC,
and the receipt's self-address. The receipt check is performed by
`validate_registry_authorization_binding(..., gate_receipt=...,
authority_secret=...)`. The two receipt-bound hashes must equal the current
registry and authorization hashes byte for byte. A stale, missing, copied,
unauthenticated, or mismatched receipt fails closed even when projection fields
compare equal.

The receipt grants no authority of its own and cannot broaden the discovery
authorization. It is mandatory evidence that the registry reviewed at S1 is
the registry bound to the authorization executed at S2.

### S2 — Site discovery only

Execute only `D_site_discovery` under the exact authorized environment.

Let

```text
C = total authorized candidate-site rows across all 27
    model × causal-variable panels
  = 3 × sum(transformer_block_count over the nine model units)
```

The exact discovery budget is:

```text
unpatched                                      576
targeted_interchange                         32 C
norm_matched_rotation                        32 C
self_sham                                    32 C
control_site_delta                           32 C
total                                   576 + 128 C
```

Forbidden during this state:

- `D_causal_label` calls;
- `D_behavior_fit` calls;
- `D_sealed_test` calls;
- diagnostic cue-mask calls;
- substitute endpoints or model revisions;
- manual site selection or early inspection-based candidate deletion.

Every output, activation-capture digest, typed intervention execution record,
and runtime-ledger row is retained, including parse and control failures.

### G2 — Site-discovery closure

Construct the immutable site-discovery report and require both:

1. validation against correction 0002's successor JSON Schema;
2. `validate_site_discovery_report` against the exact authorization.

The semantic validator is authoritative for dynamic candidate count, raw
evidence closure, integer arithmetic, ordering, argmax/tie-break derivation, and
eight-way leave-one stability.

A valid but unstable selected site is not replaced. Its downstream component is
reported as unresolved under the frozen gate. A more convenient layer may not
be selected after observing stability or downstream transfer.

Preserve the exact report bytes and canonical hash. Under-count, over-count,
wall-clock overrun, missing raw evidence, forged score, incomplete block
inventory, or authorization drift stops execution.

### S3 — Final execution lock

Build and validate the final execution lock. It must bind:

- the exact discovery authorization and site-report hashes;
- selected sites without modification;
- the three non-discovery content partitions;
- the exact primary pair inventories;
- decoding, carrier, runtime, source, feature, prospective, and blind-runtime
  identities;
- the exact post-discovery query plan.

`authority_commitments` remains exactly `null`. No output-derived key, score,
challenge commitment, reveal material, or fold result may enter this lock.

### S4 — Post-discovery collection

Collect the following under the final lock:

```text
D_causal_label                               8,064
D_behavior_fit                              4,320
D_sealed_test                               4,032
pre-auditor subtotal                       16,416
diagnostic cue masks                            0 pending
```

Do not adapt denominators, prompts, projections, selected sites, estimators, or
baselines. Parse failures, abstentions, baseline-incorrect cases, and failed
controls remain in their frozen denominators.

### G4 — Pre-auditor barrier

Before any fold fitting, the authority supplies:

- the exact regenerated prompt inventory;
- all raw causal-label, behavior-fit, and sealed-test outputs;
- a self-addressed ledger closing exactly 16,416 forwards;
- diagnostics declared zero and pending;
- identical global raw sealed roots for all future fold authorizations.

The sealed roots cover exactly:

```text
weak trials                                  2,880
challenge trials                             1,152
sealed forwards                              4,032
```

Ledger and hashes establish content and phase integrity under the declared
authority. They do not prove physical hook execution, model/runtime identity,
or complete external provenance.

### S5 — Private post-output fold authorization

Only after G4 closes, create exactly three private fold authorizations, one per
heldout dependency cluster. Each binds the same global raw roots and a distinct
declared worker capability ID.

Per fold:

```text
heldout material       3 targets, 960 weak rows, 6 slots, 384 challenge trials
development material   6 targets, 12 slots, 768 challenge trials
```

Private raw model, lineage, tokenizer, family, run, checkpoint, and cluster
identities never enter an auditor realm. Development cluster tokens are
fold-private domain-separated HMAC pseudonyms.

Capability IDs and no-shared-resource declarations are audit evidence, not
physical isolation attestation.

### S6 — Fold fitting and commitment

Each worker receives only:

- its opaque heldout weak-observation bundle;
- fold-private development material from the other two heldout clusters,
  including its authorized `development_scoring_key`;
- the common frozen feature, estimator, calibration, and abstention method.

It emits a prediction plus every required auditor artifact and a self-addressed
commitment. Fold fitting performs no model forward calls.

No challenge prompt, challenge output, heldout scoring key, raw identity,
private authorization, or diagnostic observation may enter fitting. The
fold-private `development_scoring_key` is the only scoring-key material allowed
in the worker realm.

### G6 — All-fold commitment barrier

All three commitments must close before any reveal provider call. Verify:

- one unique heldout cluster per fold;
- common raw roots and method-defining hashes;
- prediction and all auditor-artifact hashes;
- complete opaque slot coverage;
- identity-redaction scans;
- no reveal bytes or nonces in `fold_runs`;
- each committed development artifact's byte and canonical-record hashes equal
  the hashes bound by its private sealed authorization.

One missing, duplicate, or invalid commitment means zero opening-provider calls.
The cross-fold other-two-heldout union cannot be proven at this pre-reveal gate;
that proof is mandatory in S8 after the authority openings are validated.

### S7 — Diagnostic execution

After all three prediction commitments close, execute the 576 diagnostic
cue-mask forwards authority-side. Keep them unreleased through primary scoring.
They may diagnose a completed result; they may not alter predictions, fitting,
or the primary gate.

### S8 — Reveal and scoring

Invoke only the exact four-field authority opening provider. After independently
validating every opening, re-derive the development and scoring material and
prove that each fold's development slot inventory and scoring key are exactly
the other two folds' heldout material after rekeying into the receiving fold's
private HMAC namespace. Only then evaluate the global production gate.

Candidate and each named baseline loss are averaged equally across the three
dependency clusters. Select the stronger global baseline, then apply the frozen
10% log-loss improvement threshold. A single-fold pass is never authoritative.

The completed post-discovery budget is:

```text
pre-auditor subtotal                       16,416
diagnostics                                   576
post-discovery total                       16,992
```

The complete OSS-1 forward budget is:

```text
17,568 + 128 C
```

### S9 — Final audit and release

Release only an append-only evidence package containing successes, failures,
abstentions, limitations, and the complete query ledger. Do not overwrite or
splice partial attempts.

The maximum current assurance level is `prediction_locked` unless separate
evidence proves physical worker isolation and fold-local estimator training and
replay. Hashes, capability identifiers, and same-process barriers alone do not
license `blind_attested`.

## Abort and retry policy

- Preserve every partial attempt with its own run identity and stop reason.
- Never fill missing rows from a later run.
- Never reuse a failed attempt's outputs to redesign a successor and then call
  the successor outcome-naive.
- A retry is a new append-only artifact with a parent attempt ID and exact
  supersession mapping.
- Scientific gate failure narrows or negates the claim; it does not permit
  record deletion, denominator changes, or method adaptation.

## Evidence retention minimum

Retain at least:

- parent freeze, correction, and operational-manifest bytes and hashes;
- dependency registry, source catalog, overlap scans, exposure scans, and
  authorization projection;
- discovery authorization and authority-secret commitment;
- raw discovery outputs, activation digests, intervention records, and runtime
  ledger;
- site-discovery report and final execution lock;
- raw causal-label, behavior-fit, sealed-test, and diagnostic inventories;
- all nine causal-profile validations, including failed gates;
- pre-auditor ledger and raw sealed roots;
- three private fold authorizations and blind-bundle manifests;
- three predictions, every auditor artifact, development artifact, and
  commitment;
- coordinator result and complete final ledger;
- environment, source, model, tokenizer, and declared physical-assurance
  limitations.

## Claims this playbook never licenses

- recovery of a hidden trace, thought, or chain of thought;
- proof that a model uses a named layer, head, or circuit;
- unconditional model-level reliance from a selected site;
- statistical independence from different seeds or checkpoints;
- model-family or population generalization from three clusters;
- a population confidence interval from within-target case resampling;
- a calibrated posterior when `probability_status=not_calibrated`;
- certified blindness from same-process prediction locking;
- omission of parse failures, failed controls, or abstentions;
- a proprietary endpoint attribution without a separately frozen comparability
  bridge.

## Current executable surface

The checked-in CLI currently exposes call-free preflight, design summary, and
the synthetic demonstration. Live artifact builders and the full orchestration
state machine are not production CLI entry points yet. This playbook therefore
names the existing Python validators and evidence gates rather than presenting
commands that do not exist.

The next legal action is to populate and validate a dependency-cluster registry.
It is not to run site discovery.
