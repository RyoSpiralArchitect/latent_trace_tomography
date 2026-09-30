# Architecture

## Evidence flow

~~~text
protocol
  -> case and projection plan
  -> completion provider
  -> immutable raw completion records
  -> text-only observations
  -> panel features
  -> reference-fitted estimator
  -> estimator and predictions committed
  -> authority releases diagnostic/evaluation capability
  -> evaluation and manifest
~~~

OSS-only internal observation is a sibling path:

~~~text
local model + intervention plan
  -> InternalObserver
  -> InterventionTrial
  -> SelectedSiteInterventionSusceptibilityProfile
  -> calibration labels
~~~

The live OSS-1 authority path has two distinct locks:

~~~text
frozen design
  -> content-addressed discovery authorization
  -> bounded site discovery only
  -> count- and evidence-closed site-discovery report
  -> output-independent final execution lock binding both parent artifacts
  -> causal labels + behavior fit + sealed test: 16,416 forwards
  -> diagnostic count remains zero and pending
  -> three private post-output sealed fold authorizations
  -> three isolated fold prediction commitments
  -> common-root and cross-fold closure before any reveal
  -> global prospective score
  -> diagnostic release
~~~

The checked-in discovery-authorization and final-execution templates are both
unassigned, and the private post-output sealed-evaluation authorization template
is unassigned as well. Consequently the repository has made zero model and API
calls; a design freeze alone grants no execution capability.

The completion provider never exposes activations, and the InternalObserver is
never attached to a proprietary endpoint. This prevents accidental collapse of
calibration evidence and black-box evidence.

## Current modules

- collection.py: future provider request/response and capability contracts
- schema.py: text observation/projection records plus Phantom-0-only binary
  label and prediction records
- synthetic.py: hard-routed dual-route calibration phantom
- oss_design.py: exact 2 × 2 × 2 OSS-1 task, projection roles, and directed
  single-factor intervention pairs
- causal_profile.py: local arithmetic validation plus the authoritative bridge
  from a validated execution lock, discovery report, raw causal-label outputs,
  carrier bindings, and per-condition execution ledgers to an OSS reference
  profile
- blind.py: raw `D_sealed_test` regeneration, private post-output fold
  authorizations, auditor field allowlist, three-fold commitment barrier,
  commitment closure, global prospective coordination, and explicit
  capability-security warning
- prospective.py: exact challenge-slot closure, probability validation,
  cluster-macro scoring, internally reconstructed frozen baselines, and the
  primary skill gate
- split.py: deterministic learned-state dependency clustering, outer folds, and
  disjoint 8/16/24/16 content-seed partitions
- execution.py: unassigned-template checks, authority-secret material
  regeneration, ancestry-derived dependency closure, every-block candidate and
  exact carrier inventories, raw per-pair site-discovery evidence, hook-ledger
  validation, and final-lock ancestry/budget closure
- features.py: deterministic text-to-panel contrast extraction
- inference.py: transparent standardized nearest-centroid baseline with abstention
- protocol.py: call-free design-freeze, discovery-authorization-template, and
  final-execution-template validation
- demo.py: staged synthetic collection, prediction lock, challenge evaluation,
  atomic publication, and manifests
- cli.py: preflight, call-free OSS design summary, and synthetic-demo entry points

The nearest-centroid model is intentionally not a research contribution. Its
separation and OOD thresholds are transparent heuristics, not probability
calibration. It makes label leakage and projection behavior inspectable.

## Evidence separation

Raw CompletionRecord retains provider/model aliases, transmitted parameters,
usage, latency, response identifiers, timestamps, and raw response payloads.
Those fields are essential for provenance and drift analysis.

TextObservation contains only:

- run and opaque target identity
- split, case, projection, and replicate identity
- prompt text
- output text

Route/intervention labels live in separate authority-held files. For OSS-1, the
authority also seals evaluation target identity and dependency-cluster
membership, the causal site map and profile, cue-mask material, held-out
challenges, and all internal intervention records. The auditor receives only
the exact text/opaque-ID allowlist in the
[blind evaluation contract](../protocols/oss_reliance_regime_v0/blind_evaluation_contract.json).

The synthetic runner writes and hashes predictions before it materializes the
evaluation key or collects held-out challenge outputs. That ordering is useful
audit evidence, but a same-process run is only prediction-locked. Hashes do not
create blindness.

For OSS-1, the final execution lock is output-independent and requires
`authority_commitments=null`. The authority supplies the exact regenerated
prompt/raw-output inventory and self-addressed ledger declaring 8,064
causal-label, 4,320 behavior-fit, and 4,032 sealed-test forwards—16,416
pre-auditor forwards in total—while recording zero diagnostic forwards and
keeping diagnostics pending. This is inventory integrity under the declared
authority, not runtime attestation. Only then does it derive one private sealed
authorization per held-out fold from the raw `D_sealed_test` evidence. Each authorization binds all 2,880
weak and 1,152 challenge trials, derived keys and slots, the opaque auditor
surface, and nonce-bound evaluation-key and challenge-bundle commitments.

Blind OSS-1 evaluation requires three separate fold-worker capability realms,
implemented through distinct OS principals, containers, or controlled mounts,
and a production coordinator that accepts all three immutable prediction
commitments before any reveal. The required distinct capability IDs and
no-shared-mount/cache/IPC fields are declarations supplied by the authority;
they are audit evidence, not physical isolation attestation. Fold-local
estimator training and replay are not yet independently attested, so the
current implementation earns prediction-lock language unless that residual P1
is closed separately. Authority commitments use domain-separated SHA-256 over
u64be-length-prefixed domain, nonce, and payload fields with an operating-system-
CSPRNG nonce of at least 32 bytes; concatenation boundaries are therefore
unambiguous.

## Frozen OSS-1 design surface

The current design freeze binds five independently reviewable assets:

1. [exact task generator](../protocols/oss_reliance_regime_v0/task_generator_spec.json)
2. [single-factor intervention table](../protocols/oss_reliance_regime_v0/intervention_table.json)
3. [dependency-cluster split rule](../protocols/oss_reliance_regime_v0/family_split_rule.json)
4. [independent-unit
   definition](../protocols/oss_reliance_regime_v0/independent_unit_definition.json)
5. [blind evaluation contract](../protocols/oss_reliance_regime_v0/blind_evaluation_contract.json)

The exact prospective scoring contract is nested inside item 5. It fixes the
challenge inventory, relational outcome space, committed inputs, internally
reconstructed baselines, and pass metric without creating a sixth mutable
top-level surface.

The design is frozen while discovery authorization, final execution, and private
sealed-evaluation authorization remain unassigned. In particular, no model,
tokenizer, causal site, query budget, or evaluation outcome is bound, and zero
model or API calls have occurred. The next state transition is a content-
addressed discovery authorization; API provider adapters remain a later phase.

The live material manifest is regenerated from the authority secret and closes
the `8/16/24/16` content partitions, prompt inventories, pair inventories, and
query denominators. Discovery must retain every candidate block and all four
conditions for every primary pair; causal labeling separately retains all raw
outputs and execution records on `D_causal_label`. The fixed post-discovery
plan is 16,992 forwards, including 576 diagnostics. Its pre-auditor barrier is
the output-producing 16,416-forward prefix, with diagnostics fixed at zero and
pending until all fold commitments close. Runtime-ledger hashes and tensor-role
digests make mutation and relabeling detectable under the authority, but do not
claim physical hardware attestation.

`dependency_cluster_id` is computed from the learned-weight, teacher/
distillation, and merge dependency graph. It defines the effective independent
sample size. Checkpoints, adapters, fine-tunes, prompts, cases, templates, and
decoding replicates are nested observations inside a cluster.

The OSS-1 pilot fixes exactly three dependency clusters and nine model units.
Each cluster contains exactly one `semantic_anchor`, one `surface_cue_anchor`,
and one `mixed_anchor`; all three share that cluster's architecture family,
tokenizer revision, and tokenizer artifact. Thus each train and held-out side
contains the complete anchor set, preventing architecture, tokenizer, or
dependency-cluster identity from directly decoding the anchor. Effective `n`
remains three.

The internal reference record is deliberately named a selected-site
intervention-susceptibility profile. Each component is conditional on its frozen
site-selection algorithm, carrier position, candidate set, and intervention
stratum. Its arithmetic is checked in code: integer successes close each raw
IIA to its shared denominator, `specific_iia` equals targeted minus matched-null
IIA, and `delta_specific` equals semantic minus cue susceptibility. Sixteen
keyed leave-one count records must be strict subsets, close back to the full
totals, share one omission-ID set, and reproduce the stored jackknife interval
exactly. Codebook competence is also count-bound and content-addressed.

Each component additionally serializes `matched_null_kind` as
`norm_matched_rotation` and retains count-bound self-sham and control-site
evidence. The executable gate report recomputes route specificity (at least
0.25 for the anchor's induced route), self-sham (at least 0.90), absolute
control-site specificity (at most 0.10), codebook competence (at least 0.90),
and site stability (at least 0.75). Failures remain in the profile and force the
anchor summary to `unresolved`; they are not filtered away.

Winner selection is rerun in each of the eight frozen leave-one-content-seed-out
discovery diagnostics. The record includes all eight keyed selections, their
complete derived histogram, the full-data selected site's frequency in eighths,
candidate count, and winner/runner-up gap for every component. A frequency
below 0.75 changes the profile status to unstable and precludes a resolved
reliance label. The primary point and interval remain
explicitly conditional on the full-discovery-data selected site. At the
engineering-pilot tier, intervals mean within-target measurement precision
only; they are never population confidence intervals over models.

Prospective scoring is nested inside the blind surface. Each fold worker sees
only its HMAC-pseudonymized held-out weak bundle and challenge-slot inventory,
plus development files whose target, slot, and dependency-cluster IDs are
HMAC-derived pseudonyms. The private sealed authorization, raw model IDs, raw
cluster IDs, raw outputs, and authority secret are never mounted in an auditor
realm.

The production coordinator validates one common design, execution lock,
pre-auditor ledger, prospective contract, pilot barrier, and raw-evidence roots
across exactly three folds. Before reveal it closes every prediction
commitment, bundle, prediction, and redaction surface. `fold_runs` contain no
reveal bytes or nonces. Only after that barrier does it invoke the exact four-
field authority opening provider; all returned bytes are independently opened
and rederived. It then regenerates each private fold material and proves that a
fold's development slots and scoring key are the other two folds' held-out
material after cluster IDs are rekeyed into the receiving fold's private HMAC
namespace. It closes six normalized inputs per fold, constructs both add-one
baselines internally, and computes one held-out loss, Brier score, and coverage
for the candidate and each baseline. Each readout is averaged equally over the
three clusters; the lower global baseline loss is selected only after those
averages, and the candidate must improve on it by at least 10 percent. A single-
fold pass is descriptive and non-authoritative, and the retired single-fold
production entry point fails closed.

## Non-overwriting identity

The intended trial identity is:

~~~text
(run_id, case_sha256, projection_id, provider_fingerprint, replicate_index)
~~~

The runner refuses an existing output path and coordinates concurrent runners
with an output-specific lock. Manifests detect later mutation, but filesystem
immutability is not enforced. Corrections should create a successor run with a
full manifest, parent run ID, reason, and supersession mapping; that successor
schema remains future work.

## Future package boundaries

~~~text
contracts/     design freeze, discovery authorization, final lock, preflight, manifests
providers/     documented API and local completion adapters
storage/       append-only JSONL and indexed derived stores
projections/   semantic factor transforms and pairing identities
observers/     OSS causal interventions only
analysis/      features, calibration, abstention, prospective scoring
protocols/     versioned experiment contracts
~~~

The repository begins smaller so these packages are added only when a live OSS
panel requires them.
