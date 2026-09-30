# Roadmap

## Phase 0: instrument calibration

Status: implemented.

The synthetic phantom has a shared natural-language renderer and a hidden hard
gate selecting either semantic evidence or a correlated surface cue. Baseline
outputs are matched. Observation projections expose enough information to
identify the route; separate challenge projections test prospective prediction.
A reduced matched-output orbit must trigger abstention.

Because cue mask/rephrase and challenge flips share the same declared route
table, this prospective score validates phase plumbing only. It is not evidence
that unconstrained natural-language residuals reveal an LLM mechanism.

Deliverable: a reproducible, non-overwriting content-addressed run with leakage,
single-projection,
label-permutation, non-identifiability, and heldout-challenge gates.

## Phase 1: one OSS causal axis

Status: design frozen; discovery authorization, final execution lock, and
private post-output sealed-evaluation authorization unassigned. Zero model and
API calls have occurred.

The exact generator produces a complete 2 × 2 × 2 design over semantic
solution, surface cue, and answer codebook for every content seed. Interchange
interventions measure each variable, and every targeted patch has a site-,
count-, source-class-, and norm-matched null. The primary selected-site
intervention-susceptibility profile is:

~~~text
S_v = IIA_targeted_v - IIA_matched_null_v
delta_specific = S_semantic - S_surface_cue
~~~

Raw IIA remains reported. The continuous profile point estimate and interval
are primary and are not a calibrated posterior; anchor AUROC is secondary.
Every component uses the explicit `matched_null_kind=norm_matched_rotation`,
retains count-bound self-sham and control-site evidence, and feeds the
executable 0.25 route, 0.90 self-sham, 0.10 absolute control-site, 0.90
codebook, and 0.75 site-stability gates. Failed records remain serialized and
force the anchor summary to `unresolved`.

The primary weak observation set contains only semantic/cue-aligned cases. Keep
decisive cue masking sealed until a post-prediction-commitment diagnostic
phase. Seal both conflict-stratum challenge renderings for codebook-relative
prospective scoring.

The design freeze covers the exact
[task generator](../protocols/oss_reliance_regime_v0/task_generator_spec.json),
[intervention table](../protocols/oss_reliance_regime_v0/intervention_table.json),
[dependency-cluster split](../protocols/oss_reliance_regime_v0/family_split_rule.json),
[independent unit](../protocols/oss_reliance_regime_v0/independent_unit_definition.json),
and [blind interface](../protocols/oss_reliance_regime_v0/blind_evaluation_contract.json).
The exact prospective scoring contract is nested inside that fifth blind
surface.
Model revisions, tokenizer checks, causal sites, query budget, and the powered
sample are not assigned. The next step is a content-addressed discovery
authorization, not an adapter or model call. That authorization may permit only
bounded site discovery. Its count- and evidence-closed report must then be
content-addressed before a distinct final execution lock can authorize causal
labels, behavior fitting, sealed tests, or diagnostics.

Concretely, the authorization must derive dependency edges from a complete
content-addressed ancestry inventory, regenerate all hidden task material from
the authority secret, bind exact tokenizer/carrier rows, enumerate every
transformer block, and precommit the formula
`576 + 128 * authorized_candidate_site_count` for discovery. The final lock
then fixes exactly 16,992 post-discovery forwards and remains output-independent,
with `authority_commitments=null`. Raw output and per-condition execution-ledger
closure are mandatory; aggregate success tables alone are not an executable
result. Before any auditor fit, the authority must supply the exact regenerated
prompt/raw-output inventory and ledger declaring 8,064 causal-label, 4,320
behavior-fit, and 4,032 sealed-test forwards—16,416 total—while diagnostic
forwards remain zero and pending. This does not attest per-completion runtime
provenance or physical execution.

Do not start with retrieve/decompose/verify/commit as four labels. First test one
continuous selectivity axis. The initial title-sized question is:

> Can output-only behavioral projections estimate one selected-site
> intervention-susceptibility profile on an unseen learned-weight dependency
> cluster, and know when they cannot?

## Phase 2: transfer

Build a preregistered dependency graph from shared learned weights,
teacher/distillation ancestry, and weight merges. Hold out entire connected
components as `dependency_cluster_id`; checkpoints, adapters, fine-tunes,
templates, and case seeds remain nested measurements and cannot inflate `n`.

Three clusters are an engineering pilot only. Confirmatory evidence requires a
fresh outcome-naive execution with at least three development clusters and at
least three separately sealed confirmatory clusters, subject to a frozen power
analysis. Balance causal anchors across clusters so a model fingerprint cannot
solve the task.

The OSS-1 pilot balance is exact: three dependency clusters by one
`semantic_anchor`, one `surface_cue_anchor`, and one `mixed_anchor` each, for
nine model units. The three anchors within a cluster share architecture family
and tokenizer identity. Every fold therefore contains all anchors on both
sides; effective `n` remains three and identity cannot directly decode the
anchor.

Add nested baselines:

- correctness and response length
- canonical decision contrasts
- embeddings or text representation
- model-identity classifier
- white-box selected-site susceptibility oracle ceiling

## Phase 3: prospective prediction

Freeze the estimator and predictions before exposing the cue-mask diagnostic or
either conflict-stratum challenge rendering. Predict the three codebook-relative
outcomes `semantic_consistent`, `surface_cue_consistent`, and `parse_failure`.
These probabilities are distinct from the susceptibility interval. OSS-1 scores
cluster-macro log loss, reports raw multiclass Brier and accepted-slot coverage,
and keeps abstained slots in both scores. Calibration, selective-risk,
Brier-skill, and per-kind aggregate formulas require a successor contract.

After the 4,032 `D_sealed_test` outputs exist, issue one private sealed
authorization for each leave-one-cluster-out fold. Every authorization binds
the common raw 2,880 weak and 1,152 challenge trials, the output-derived keys,
one opaque held-out auditor surface, and development material derived from the
other two clusters. Raw model and dependency-cluster IDs and the authorization
itself never enter the fold worker; development cluster IDs are HMAC-derived
pseudonyms.

Run exactly three capability-separated fold workers and close every prediction
commitment before accepting any reveal. The coordinator verifies common design,
execution, ledger, prospective-contract, raw-evidence, and barrier roots plus
all bundles, predictions, and redaction surfaces. `fold_runs` carry no reveal
bytes or nonces. Only after that barrier does the coordinator invoke the exact
four-field opening provider and independently rederive every returned byte; it
then proves that each fold's development material is the other two folds'
held-out material after cluster IDs are rekeyed into the receiving fold's
private HMAC namespace. Distinct capability IDs and declarations of no
shared mounts, caches, or IPC are audit claims rather than physical attestation.
Fold-local estimator training/replay is the remaining P1, so an implementation
without separate proof is described only as prediction-locked.

Failure here reframes the result as a useful robustness audit rather than latent
system identification.

Each fold gate opens and validates six normalized inputs: weak records and
inventory, development key and slot inventory, and held-out key and slot
inventory. It reconstructs both frozen add-one baselines internally; candidate
code cannot inject a baseline vector or score. The production gate averages
candidate loss, Brier, and coverage and the corresponding baseline readouts
separately and equally across all three held-out clusters, selects the lower
global baseline loss only afterward, and applies the 10 percent gate. A single-fold score is non-authoritative. Any closure
failure stops scoring, and cue-mask diagnostics remain deferred until all three
commitments are closed.

## Phase 4: closed endpoints

Add documented API adapters only after the leave-dependency-cluster-out and
prospective gates pass under their frozen contracts. Open-set validation is not
an OSS-1 gate: any unknown-regime, selective-risk, or open-set claim requires a
fresh successor contract. Preserve request parameters, returned
model/version fingerprints,
timestamps, and retries as provenance, while excluding them from primary
features.

Outputs:

- calibrated class probabilities only if a later calibration gate supports
  them; otherwise a consistency class with an uncertainty interval
- coverage and abstention reason
- evidence projection IDs
- predicted heldout failure distribution
- calibration-range and endpoint-drift warnings

No internal truth claim is made without independent vendor-side validation.

## Phase 5: richer computation classes

Only after the operational susceptibility profile remains prospectively
predictive across independent dependency clusters and a separately frozen
cross-site/model comparability bridge succeeds:

- verification-mediated versus answer-first behavior
- retrieval versus in-context derivation
- decomposition versus direct pattern completion
- contradiction suppression and repair

Every new class requires its own causal operationalization, nulls, matched
controls, prospective challenge, and claim ceiling. Psychological language is
introduced only after a validated bridge condition.
