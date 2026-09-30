# Research contract

## The estimand

Let a target endpoint produce text Y from prompt X under unobserved computation
Z. This project does not estimate Z exactly. On an open model it first estimates
a low-dimensional, selected-site intervention-susceptibility profile C. A
model-level “reliance” interpretation is a downstream hypothesis that requires a
separate comparability bridge; it is not built into the estimand's name.

For each causal variable
`v in {semantic, surface_cue, codebook}`, retain both raw interchange-
intervention accuracies and define the matched-null-specific effect:

~~~text
S_v = IIA_targeted_v - IIA_matched_null_v
g_specific = (S_semantic, S_surface_cue, S_codebook)
delta_specific = S_semantic - S_surface_cue
~~~

IIA is interchange-intervention accuracy on held-out source/base pairs. Every
targeted patch has a matched null with the same site, intervention count, source
class, and norm treatment. Normalized logit-difference restoration is a
secondary internal readout.

The serialized fields use the `matched_null` naming family, with
`matched_null_kind=norm_matched_rotation`; legacy random-null aliases are not
accepted. Every component also retains count-bound
self-sham base-answer preservation and count-bound control-site IIA against the
same matched null. These are inputs to an executable gate, not prose-only
diagnostics.

Each `S_v` is conditional on the frozen, factor-specific site-selection
algorithm, carrier position, candidate set, and source/base stratum. Effects at
different selected positions are not automatically commensurate measures of how
much a model “relies” on each variable. The design may earn that stronger
language only after route specificity, symmetric intervention opportunity, and
cross-site comparability are validated.

Site uncertainty is part of the instrument. The primary point estimate and
within-target interval are explicitly conditional on the full-discovery-data
selected site and use only disjoint causal-label pairs. Separately, rerun the
complete frozen site-selection algorithm eight times, each time leaving out one
of the eight `D_site_discovery` content seeds. Report the full selected-site
histogram, the full-data selected site's frequency in eighths, and its score gap
to the runner-up for every component. The frozen stability threshold is 0.75.
If any component is below it, mark the profile unstable and map any anchor label
to `unresolved`; do not fold this diagnostic into the primary denominator or
silently describe the selected-site interval as selection-unconditional.

The primary OSS result is the point estimate and within-target measurement-
precision interval for the continuous `g_specific` profile and
`delta_specific`. That interval is not a calibrated posterior over hidden
mechanisms or a population interval over models. Discrete anchor labels and
their AUROC are secondary summaries. Predicted probabilities for sealed
challenge responses are a different estimand and are scored prospectively with
cluster-macro log loss and a secondary raw multiclass Brier score; accepted-slot
coverage is descriptive, and abstained slots remain in both scores. They are not
obtained by renaming the susceptibility interval as a probability. Calibration,
selective risk, Brier skill, and per-kind aggregate formulas are not frozen in
OSS-1 and require a successor contract.

The interval is deterministic and conditional on the full-discovery-data
selected site. Delete each of the 16 `D_causal_label` content seeds in turn,
including all nested pairs and decoding replicates, and recompute the estimand.
For delete-one estimates `theta_i`, use
`sqrt((n-1)/n * sum((theta_i - mean(theta_i))^2))` as the jackknife standard
error and `theta_hat ± 1.959963984540054 * SE` as the 95 percent normal interval,
clipped to `[-1, 1]` for each `S_v` and `[-2, 2]` for `delta_specific`.

The serialized profile is count-closed, not a bag of reported rates. Full-data
targeted and matched-null IIAs equal integer successes divided by a shared
trial count. Each of the 16 keyed leave-one records carries the same count
evidence, is a strict subset of the full record, and the leave-one totals close
to 15 times the full totals. All components and `delta_specific` share one
omission-ID set, and every delta leave-one value is recomputed from its semantic
and cue records. Stored interval endpoints must equal the frozen calculation.
Codebook competence is likewise success-count bound and names the exact
`D_causal_label` case set by SHA-256.

Human-readable reliance labels are hypotheses summarizing an operational
susceptibility profile, not ground truth:

- semantic: `S_semantic` is high, `S_surface_cue` is lower, and codebook
  competence holds
- shortcut: `S_surface_cue` is high and `S_semantic` is lower
- mixed: both matched-null-specific route effects are present
- unresolved: confidence intervals overlap, both are weak, or controls are not specific
- codebook failure: semantic state may be present but output binding fails
- regime switching: the selected-site susceptibility profile is not stable over the projection orbit

The OSS-1 design is frozen before model selection and before any OSS outcome is
exposed. Its discovery authorization, final execution lock, and private post-
output sealed-evaluation authorization all remain unassigned, so the current
repository authorizes zero model and API calls.

## Freeze state and execution authority

The design freeze has five top-level surfaces: the exact task generator,
intervention table, dependency-cluster split rule, independent-unit definition,
and blind evaluation interface. The prospective scoring contract is nested
inside the blind surface; it is not a sixth opportunity to change the task
after seeing outcomes.

Execution proceeds through separately content-addressed transitions:

1. A discovery authorization binds the exact model and tokenizer registry,
   dependency graph, three-anchor balance, live-seed commitment, discovery-only
   case/pair inventories, candidate-site algorithm, environment, and bounded
   discovery budget. It authorizes site discovery only.
2. A complete site-discovery report closes query counts and exactly one selected
   site for every model-by-causal-variable cell, retains candidate counts and
   winner/runner-up evidence, and binds itself to the authorization.
3. A distinct final execution lock binds the authorization and discovery-report
   hashes, preserves every authorization-bound field, and only then authorizes
   causal labeling, behavior fitting, sealed testing, and diagnostics. It is
   output-independent: `authority_commitments` is `null`, and the lock contains
   no output-derived key, score, or challenge commitment.
4. A pre-auditor ledger and exact regenerated prompt/raw-output inventory
   declare causal labeling, behavior fitting, and sealed testing complete under
   the authority, with diagnostics still pending. Only after those outputs
   exist may the evaluator issue three private, post-output sealed fold
   authorizations. This is content-integrity evidence, not runtime attestation.

The authority-secret reveal regenerates the complete 64-seed material manifest
and its exact `8/16/24/16` content partitions; count-shaped hashes supplied by a
caller are not sufficient. Discovery retains 576 unpatched canonical-prompt
forwards and, for every authorized candidate site at every transformer block,
exactly 32 primary pairs under each of the four conditions. Its total is
therefore `576 + 128 * authorized_candidate_site_count`. The final lock fixes
8,064 causal-label forwards, 4,320 behavior-fit forwards, 4,032 sealed-test
forwards, and 576 diagnostic forwards: exactly 16,992 post-discovery forwards.
The pre-auditor barrier covers the first three phases only: an exact raw-output
inventory and ledger declaring 16,416 forwards. It requires
`diagnostic_forward_passes=0` with diagnostics pending until all three fold
prediction commitments exist.

The sealed-test phase contains exactly 2,880 weak and 1,152 challenge forwards
over the nine targets. Once all 4,032 raw outputs exist, each fold's private
sealed authorization binds those raw evidence roots, the held-out and
development keys and slot inventories derived from them, the fold's opaque
auditor bundle, and nonce-bound authority openings. This private authorization,
the raw model registry, and raw dependency-cluster IDs never enter an auditor
realm. Development target, slot, and cluster identities are HMAC-derived
pseudonyms; in particular, the `dependency_cluster_id` values in development
scoring files are not raw execution-lock IDs.

Every discovery and causal-label condition retains raw output text and a
content-addressed execution record. That record binds the prompt pair, selected
layer/module, factor and control token positions, activation-capture digests,
tensor-role digests, matched-null seed/permutation/sign commitments when
applicable, and one exact runtime-ledger entry. Aggregate scores, free-form
carrier summaries, or orphan ledger digests cannot authorize a profile. The
tokenizer preflight derives marker tokenization from exact token-ID arrays;
decoding is one greedy replicate with `max_new_tokens=16` and no stop strings or
stop-token IDs.

This evidence chain establishes content integrity and replayable operation
metadata under the declared authority. A hash does not by itself prove that a
physical hook fired, that a tensor relation was executed on hardware, or that
an ancestry declaration is omniscient. Stronger runtime attestation requires a
separate runner/attestation contract and is outside the OSS-1 claim ceiling.
Likewise, the three required fold-worker capability IDs and their no-shared-
mount/cache/IPC declarations are not physical isolation attestation. Fold-local
estimator training and replay remain a residual P1; unless independently
verified, the strongest assurance language is prediction-locked, not blind.
Across folds, the frozen estimator source, feature specification, analysis
configuration, and abstention rule must have identical hashes before any
opening. Fitted weights and fold-local calibration status may differ.

Failure, budget overrun, incomplete inventory, or ancestry drift fails closed
and remains evidence; it does not become an implicit permission to continue.
The next permitted project step is to assign and freeze the discovery
authorization. It is not to implement an API adapter or call a model.

## Exact task generator

For every content seed, OSS-1 generates the complete 2 × 2 × 2 factorial:

| Factor | Levels |
|---|---|
| semantic solution | ACCEPT, REJECT |
| surface cue | ACCEPT, REJECT |
| answer codebook | identity, swap |

The semantic rule, cue, and answer mapping are independently manipulable. The
complete factorial is required for causal pairing even though not every cell is
auditor-visible in the weak observation phase. The frozen definitions are in
the [task generator specification](../protocols/oss_reliance_regime_v0/task_generator_spec.json)
and [intervention table](../protocols/oss_reliance_regime_v0/intervention_table.json).
Each factorial case also has exactly one authority-only canonical intervention
prompt. Every directed pair binds both canonical prompt IDs and hashes; weak,
diagnostic, and challenge projection records cannot be substituted as causal
capture identities.

## Observation unit

The scientific independent unit is `dependency_cluster_id`. It is the connected
component induced by a preregistered dependency graph whose edges include:

- shared or inherited learned weights
- teacher/student or distillation ancestry
- weight merges or mixtures constructed from an ancestor

The graph is not accepted as an independent declaration. The discovery
authorization contains one content-addressed, complete and unambiguous
learned-state ancestry record per model plus all external base, teacher, merge,
and adapter-base artifacts. The validator derives the exact graph edges from
those parent rows and shared parent artifacts. Unknown or ambiguous ancestry
fails the three-cluster claim rather than silently creating a new independent
unit.

Architecture names and vendor labels do not define independence. Within a
dependency cluster, the measurement unit is:

~~~text
(model revision, task, base-case orbit, decoding configuration)
~~~

A checkpoint, adapter, fine-tune, merged descendant, response, prompt, case,
template, or decoding replicate is a nested repeated measurement. Prompt-level
random splits are forbidden. Aggregating nested measurements improves
precision but does not increase effective `n`, which is the number of eligible
dependency clusters.

OSS-1 fixes exactly three clusters and nine model units. Each cluster contains
exactly one `semantic_anchor`, one `surface_cue_anchor`, and one `mixed_anchor`.
Those three units share one architecture family, tokenizer revision, and
tokenizer artifact within the cluster while retaining anchor-specific model and
configuration artifacts. Therefore every leave-one-cluster-out fold sees the
complete anchor set on both sides: architecture, tokenizer, or cluster identity
cannot directly solve the anchor task. The effective independent `n` is three,
not nine.

Three dependency clusters support an engineering pilot only. A confirmatory
claim requires a fresh, outcome-naive execution with at least three development
clusters and at least three separately sealed confirmatory clusters, and may
require more under the frozen power analysis. Cluster membership and holdout
assignment must be committed before outcomes. See the
[dependency-cluster split rule](../protocols/oss_reliance_regime_v0/family_split_rule.json)
and
[independent-unit definition](../protocols/oss_reliance_regime_v0/independent_unit_definition.json).

At the three-cluster pilot tier, selected-site susceptibility intervals quantify repeated
measurement precision within named targets only. They must not be labeled as
population confidence intervals. Cross-cluster transfer is summarized by
heldout error on those named clusters; population uncertainty requires a fresh,
powered confirmatory successor and a declared sampling population.

## Projection sets

The primary observation set Q_obs contains only semantic/cue-aligned task cells.
It may include replicates, paraphrases, evidence reorder, irrelevant
distractors, and non-decisive cue-salience changes that preserve that alignment.
Decisive cue masking is sealed during estimation and exposed only as a
post-prediction-lock diagnostic. Both frozen Q_challenge kinds contain only
semantic/cue-conflict cells. One uses the held-out ordinary rendering and one
uses the held-out mismatch-table rendering; neither transformation is used in
fitting.

Q_challenge is never used to fit the estimator. The decisive chain is:

~~~text
Q_obs outputs
    -> estimated selected-site susceptibility profile
    -> predicted codebook-relative Q_challenge distribution
    -> observed semantic-consistent / surface-cue-consistent / parse-failure distribution
~~~

If this prospective link fails, the operational profile has not added explanatory
power over a robustness score. The exact slot inventory, three-outcome
probability simplex, aggregation, add-one baselines, and skill gate are frozen
in the [prospective scoring contract](../protocols/oss_reliance_regime_v0/prospective_scoring_contract.json).

The production prospective gate accepts exactly three fold runs and no caller-
supplied baseline predictions or scores. Before any reveal it validates all
three immutable prediction commitments against one common design, execution
lock, pre-auditor ledger, prospective contract, raw-evidence roots, and pilot
barrier, plus every bundle, prediction, and redaction surface. `fold_runs`
contain no reveal bytes or nonces. Only after this closure does the coordinator
invoke an authority opening provider that must return exactly the evaluation-
key bytes, challenge-bundle bytes, evaluation nonce, and challenge nonce; every
byte is independently opened and rederived. It then regenerates each fold and
requires the development key and slot inventory to equal the other two folds'
held-out material after cluster IDs are rekeyed into the receiving fold's
private HMAC namespace. For each fold it hash-closes six normalized inputs: weak
observation records, weak composite inventory, development scoring key,
development slot inventory, held-out scoring key, and held-out slot inventory.
It constructs both frozen add-one baselines internally and rescores candidate
and baselines on the same fold key.

The coordinator then averages candidate loss, Brier, and coverage equally over
the three held-out dependency clusters and separately averages the same
readouts for each named baseline. Only the global losses select the stronger
baseline and enter `candidate <= 0.90 * stronger_baseline`. A single-fold score
is descriptive and non-authoritative. A malformed, missing, extra, duplicated,
overlapping, cross-root, or hash-mismatched input fails closed before the global
gate.

## Blind evaluation interface

After every `D_sealed_test` output exists but before a fold auditor fits its
estimator, the evaluation authority privately seals for that fold:

- evaluation target identity and dependency-cluster membership
- causal site map and selected-site susceptibility labels
- cue-mask prompts and outputs
- held-out challenge prompts, outputs, and scoring keys
- all internal intervention records and telemetry

The auditor receives only the allowlisted prompt/output text, HMAC-pseudonymous
pairing identifiers, HMAC-pseudonymous development scoring material, and opaque
challenge slots. It never receives the private fold authorization, raw model or
cluster identities, raw challenge evidence, authority secret, or reveal bytes.
Exactly three separately declared fold-worker capability realms must commit
before the coordinator invokes the authority opening provider; reveal bytes and
nonces are absent from the fold-run records themselves. Diagnostics are also
forbidden until that barrier closes. Hashes and ordering make later mutation detectable,
but do not create capability security. Distinct capability IDs are declarations,
not proof of physical separation, and fold-local estimator training/replay is
not yet attested. A same-process or otherwise unproven implementation is only
prediction-locked. A blind claim requires the sealed material to be unavailable
to the auditor through a separate OS principal, container, or controlled mount
until commitment, plus separate evidence closing the residual training/replay
boundary. The exact contract is in the
[blind evaluation contract](../protocols/oss_reliance_regime_v0/blind_evaluation_contract.json).

## Primary feature boundary

Allowed:

- prompt and response text
- case, projection, replicate, and pairing identities
- deterministic parses of decisions, abstentions, and references
- condition-wise distributions and transition matrices

Excluded from the primary estimator:

- logprobs, logits, gradients, activations, attention, and weights
- latency, token usage, finish reason, request ID, and system fingerprint
- provider, model, architecture-lineage, dependency-cluster, and endpoint identifiers
- OSS selected-site susceptibility labels for evaluation units

Collection telemetry is still preserved outside the feature table so endpoint
drift and audit provenance can be checked.

## Nested views

Three nested feature views prevent the project from relabeling model
fingerprinting as mechanism inference:

1. one baseline projection
2. canonical decision-contrast vector across the orbit
3. decision vector plus lexical/syntactic text representation

Raw language earns a stronger computation-class claim only if view 3 improves
leave-dependency-cluster-out prospective prediction over view 2 after style,
length, and identity controls.
The current synthetic implementation covers only views 1 and 2.

## Identifiability

Identifiability is relative to a probe set. If two causal regimes induce the
same output distribution over Q, they belong to the same observational
equivalence class. The estimator must return a set or abstain rather than force
a unique label.

The synthetic harness includes a reduced orbit on which the two hidden routes
are output-matched. Zero coverage is the expected result there.

## Gates

### G0: harness

- oracle invariance/equivariance checks pass
- IDs and full SHA-256 manifests agree
- no model call occurs in preflight
- a capability-separated plan process cannot read evaluation labels or collect
  held-out challenge outputs
- exactly three fold commitments close before any held-out reveal, with raw
  model/cluster identities absent from all auditor-visible bytes
- latent labels do not appear in observation records

The current Phantom-0 runner implements same-process prediction locking and
calls its checks `R0` through `R5`. Those regression checks do not certify this
complete G0 or blind evaluation.

### G1: synthetic phantom

- held-out case accuracy at least 0.90
- advantage over one baseline projection at least 0.25
- matched-output reduced orbit produces abstention
- held-out challenge prediction at least 0.90

### G2: OSS reference profiles

- targeted IIA minus `matched_null_kind=norm_matched_rotation` IIA is at least
  0.25 on each induced route: semantic for `semantic_anchor`, surface cue for
  `surface_cue_anchor`, and both for `mixed_anchor`; answer-codebook
  susceptibility is reported but is not a route-specificity threshold
- count-bound self-sham preserves the base answer on at least 0.90 of every
  measured component's primary pairs
- the absolute count-bound control-site specific effect is at most 0.10 for
  every measured component
- codebook competence is at least 0.90
- causal-site discovery and evaluation cases are disjoint
- site rediscovery frequency and winner/runner-up score gaps are reported for
  every component; an unstable component forces the anchor summary to
  `unresolved`
- the machine-checked gate serializes every threshold result; any failure is
  retained and makes the overall anchor eligibility `unresolved`

### G3: within-development-cluster

- grouped AUROC at least 0.80
- at least 0.10 improvement over accuracy-only

### G4: leave-dependency-cluster-out

- primary `delta_specific` mean absolute error at most 0.25 on the named heldout
  dependency clusters
- primary component-wise mean absolute error for all three `g_specific`
  components, with no post-outcome component selection
- secondary anchor macro AUROC at least 0.70, with every named fold above 0.60
- no population confidence interval is reported for the three-cluster pilot;
  case- or pair-resampling intervals are within-target measurement precision
  only

### G5: prospective

- at least 10 percent lower codebook-relative held-out-challenge log loss than
  the lower globally averaged loss of the frozen route-agnostic weak-orbit split
  and cluster-equal development challenge marginal add-one baselines, after
  candidate and each baseline have each been averaged equally over all three
  held-out clusters
- all three commitments close before any reveal; every fold's development key
  and slots equal the other two folds' held-out union; a single-fold pass has no
  authoritative status
- raw cluster-macro Brier score and accepted-slot coverage are reported without
  a pass threshold; abstained slots remain in both primary scores

### G6: open set (successor only)

OSS-1 records an abstention flag and accepted-slot coverage but does not freeze
an unknown-regime generator, selective-risk formula, or open-set pass gate. A
fresh outcome-naive successor must define all three before making an open-set
claim.

The numerical criteria are engineering gates until a powered final execution
lock is assigned. Confirmatory use requires a fresh outcome-naive run with the
sealed development/confirmation split described above; the present design
freeze has seen zero OSS outcomes.

The synthetic challenge is generated from the same declared hard-route table as
the observation panel. Its prospective score is a pipeline regression, not an
independent mechanistic validation. Its target replicates share one generator
and are not independent model samples. G5 applies only when the challenge
transformation family and natural-model susceptibility profile were not used to define
or fit the estimator.

## Stop and reframe lines

Stop or reduce the claim if:

- accuracy matching removes the signal
- norm-matched rotation nulls match the intended causal intervention
- only raw style/model identity features work
- explicit conflict must be observed before classification succeeds
- template, checkpoint, or dependency-cluster holdout collapses performance
- unknown regimes receive confident known labels
- the selected-site susceptibility profile switches across the supposed projection orbit

Negative results remain valuable: they identify which computation properties do
not survive projection into language under the tested query budget.

## Proprietary endpoint language

Without a vendor-held internal key or an independently known routing
intervention, a closed endpoint has no internal ground truth. The maximum
allowed conclusion is:

> Under protocol P and OSS calibration set C, this endpoint's projection orbit
> is consistent with equivalence class R at uncertainty U, and predicts heldout
> behavior F.

That statement is falsifiable and useful without pretending to open the model.
“Tomography” remains an analogy for controlled inverse measurement: prompt
perturbations are not a known linear Radon operator, can alter the computation,
and do not justify exact reconstruction language.
