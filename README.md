# Latent Trace Tomography

English | [日本語](README.ja.md) · [Documentation](docs/README.md)

An output-only system-identification research program for behaviorally
identifiable computational regimes in black-box language models.

This repository asks a deliberately narrower question than “can we recover a
model's hidden reasoning?”

> Can a controlled orbit of prompt/output texts estimate an OSS-calibrated,
> selected-site intervention-susceptibility profile on a model from an unseen
> learned-weight dependency cluster, and know when it cannot?

The repository name is the long-horizon flag. The first paper-sized claim is
smaller: output-only estimation of an operational OSS reference profile and
prospective challenge behavior.

## Core idea

~~~mermaid
flowchart LR
    A["OSS controlled interventions"] --> B["Known calibration phantoms"]
    B --> C["Controlled prompt orbit"]
    C --> D["Text outputs only"]
    D --> E["Regime estimator"]
    E --> F["Regime estimate or abstention"]
    F --> G["Held-out failure prediction"]
~~~

Open models provide the calibration bridge: pair a selected-site intervention-
susceptibility profile with its external perturbation signature. A closed API
is then compared with those calibrated signatures. The result is an
observational equivalence class with explicit domain checks and abstention, not
a calibrated probability, recovered activation trace, or hidden chain of
thought.

The CT analogy is useful as research intuition but not as mathematics. Prompt
changes do not implement a known linear Radon operator, and may change the
computation itself. The actual object of study is a causal response surface over
a controlled input orbit.

## What exists now

- An additive [output-only bridge v2](successors/oss_reliance_regime_v0/output_only_bridge_v2/README.md)
  separates answer content from format compliance and returns all case-aligned
  matching references with finite challenge-output sets. It is model-free and
  development-only; it does not revise the v1 checkpoint or establish live
  prospective transfer.
- A [2026-10-23 output-only Furnace/API checkpoint](reports/output_only_bridge_20261023/README.md)
  with 1,008 retained-OSS completions and 112 API calls, public synthetic
  prompt/output records, and offline replay. The primary forecast abstained;
  a separate post-hoc format diagnosis is not a transfer-success claim.
  Three OSS instances had identical observed weak outputs but different
  challenge behavior. This is a bounded successor pilot, not frozen OSS-1
  collection or validated internal-mechanism attribution.
- A standard-library-only synthetic calibration instrument with two genuinely
  known hard routes: semantic evidence and a correlated surface cue.
- Matched baseline outputs, diagnostic observation projections, and challenge
  projections withheld from inference.
- A text-only feature path that excludes logits, logprobs, latency, usage, model
  identity, and provider metadata.
- Single-projection, label-permutation, and reduced-orbit
  non-identifiability controls.
- Prospective prediction of outputs on unseen cue-flip and semantic-flip
  challenges.
- Atomically published, non-overwriting run directories with source, protocol,
  configuration, split, prediction-lock, and phase-order hashes.
- An evaluation key and challenge-output phase that opens only after the
  prediction artifact is written and content-addressed.
- A design-frozen OSS-1 contract covering the exact task generator,
  intervention table, dependency-cluster split, independent unit, and blind
  evaluation interface, including exact prospective challenge scoring.
- A three-fold production coordinator that requires all three prediction
  commitments before any reveal, verifies fold ancestry and cross-fold closure,
  and applies one equal-cluster prospective gate. The single-fold scorer is
  explicitly non-authoritative.
- Two deliberately unassigned pre-output execution boundaries—a content-
  addressed discovery authorization and a separate final execution lock—plus
  an unassigned private post-output sealed-evaluation authorization template.
  These checked-in templates remain unassigned. Separate live successors have
  since run; the checkpoint above does not fill or retroactively authorize
  these templates. `design_ready=true` is not live-execution readiness.
- An append-only [controlled-anchor construction plan](successors/oss_reliance_regime_v0/controlled_anchor_phantom_v1/anchor_construction_plan.json)
  and [registry-authoring companion](operations/oss1_registry_authoring_v2/docs/registry_authoring_successor.md).
  Nine public checkpoint candidates remain `unresolved`; the successor instead
  assigns three controlled descendants per named base family. The retained
  cohort was used in the separate checkpoint above. Nine descendants are not
  nine independent subjects; construction-condition names are not validated
  mechanism labels. The causal-calibration bridge remains unresolved.

The synthetic panel is a regression test for the instrument. It uses only
parsed final decisions, and its challenge generator shares the same hard-route
semantics as the observation generator. It therefore tests leakage, phase,
abstention, and prediction plumbing; it is not evidence that natural-language
residuals reveal a mechanism or that a natural model contains either route.

## Quick start

~~~bash
git clone https://github.com/RyoSpiralArchitect/latent_trace_tomography.git
cd latent_trace_tomography

python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"

ltt preflight \
  --protocol protocols/oss_reliance_regime_v0/protocol.json

ltt oss-design-summary

ltt synthetic-demo \
  --out-dir artifacts/synthetic_projection_orbit_v1_seed7 \
  --seed 7
~~~

Both OSS commands are call-free. Preflight validates frozen asset hashes and
executable invariants; the summary reproduces the public 64-seed generator
conformance hashes. At the current boundary they stop before model execution.
Live successors require separate, content-addressed authorization closing
environment, verified-byte, RNG, module, tokenization, and output prerequisites.
Construction, registry evidence closure, discovery authorization, and the final
execution lock are distinct gates. Publishing this repository or passing
preflight does not authorize weight downloads, training, or model/API calls.

The runner uses an output-specific lock, refuses an existing path, writes to a
sibling staging directory, verifies manifest closure, and then atomically
publishes. SHA-256 manifests detect later mutation; the operating system does
not make the published directory cryptographically immutable.

The reference seed currently yields:

| Readout | Value |
|---|---:|
| Full projection-panel accuracy | 1.000 |
| Single baseline-projection accuracy | 0.500 |
| Label-permutation mean accuracy | 0.375 |
| Reduced matched-output orbit coverage | 0.000 |
| Held-out challenge prediction accuracy | 0.971 |

These are synthetic bootstrap outcomes and are explicitly recorded as
retrospective, not preregistered.

With only 12 calibration targets, the 64-shuffle label null has an empirical
tail probability of 0.108 and a maximum accuracy of 1.0. `R4` is therefore a
pipeline regression on the prespecified mean gap, not a statistical-significance
claim. Natural-model work requires independent dependency clusters and a
powered null.

## Scientific contract

The primary independent unit is `dependency_cluster_id`, derived from the graph
of shared learned weights, teacher/distillation ancestry, and weight merges.
Checkpoints, adapters, fine-tunes, decoding runs, prompts, and cases are nested
measurements and do not increase the effective sample size.

For OSS calibration, the target is a continuous selected-site intervention-
susceptibility profile such as:

~~~text
S_v = IIA_targeted_v - IIA_matched_null_v
delta_specific = S_semantic - S_surface_cue
~~~

Raw targeted and matched-null IIA are retained. The primary result is the
continuous profile's point estimate and interval, not a calibrated posterior.
Anchor labels and AUROC are secondary summaries. Challenge-response
probabilities are a separately frozen prospective target over the codebook-
relative outcomes `semantic_consistent`, `surface_cue_consistent`, and
`parse_failure`; cluster-macro log loss is the sole prospective pass metric.

Every causal-profile component is count-bound and names
`matched_null_kind=norm_matched_rotation`. Count-bound self-sham and
control-site evidence feed an executable gate report at the frozen 0.25 route,
0.90 self-sham, 0.10 absolute control-site, 0.90 codebook, and 0.75 site-
stability thresholds. Failed evidence remains serialized and forces the anchor
summary to `unresolved`; it is never dropped from the record.

The exact OSS-1 task is a complete 2 × 2 × 2 factorial over semantic decision,
surface cue, and answer codebook for each content seed. The weak observation
set contains only semantic/cue-aligned cells and non-decisive transformations.
Cue masking is a post-prediction-commitment diagnostic. Both conflict-stratum
challenge renderings and their relational scoring keys stay sealed until the
appropriate evaluation phase.

The five top-level design-frozen surfaces are the
[task generator specification](protocols/oss_reliance_regime_v0/task_generator_spec.json),
[intervention table](protocols/oss_reliance_regime_v0/intervention_table.json),
[dependency-cluster split rule](protocols/oss_reliance_regime_v0/family_split_rule.json),
[independent-unit definition](protocols/oss_reliance_regime_v0/independent_unit_definition.json),
and [blind evaluation contract](protocols/oss_reliance_regime_v0/blind_evaluation_contract.json),
which incorporates the exact
[prospective scoring contract](protocols/oss_reliance_regime_v0/prospective_scoring_contract.json).

The pilot registry is exactly nine model units: three learned-weight dependency
clusters, each containing one `semantic_anchor`, one `surface_cue_anchor`, and
one `mixed_anchor`. The three anchors within a cluster share the same
architecture family and tokenizer identity. Because every cluster contains the
complete anchor set, architecture, tokenizer, or cluster identity cannot by
itself decode the anchor; effective `n` is three, not nine.

Each fold's prospective closure has six normalized inputs: weak observation
records and inventory, development scoring key and slot inventory, and held-out
scoring key and slot inventory. The production coordinator accepts exactly
three isolated fold commitments before any reveal, validates that each fold's
development material is the other two held-out folds after cluster IDs are
rekeyed into the receiving fold's private HMAC namespace, and
reconstructs both frozen baselines internally. Candidate code cannot supply
baseline vectors or scores. Candidate loss and each named baseline loss are
first averaged equally over the three held-out dependency clusters; only then
is the lower-loss baseline selected and the frozen 10 percent gate applied.

Execution is deliberately two-stage. A discovery authorization first binds the
exact nine-unit registry, dependency graph, tokenizer checks, live-seed
commitment, candidate-site inventory, algorithm, environment, and bounded
discovery budget. The resulting count- and evidence-closed site-discovery
report is content-addressed. Only then may a distinct final lock bind both
artifacts and authorize the remaining causal-label, behavior-fit, sealed-test,
and diagnostic work. That lock is output-independent:
`authority_commitments` must be `null`, and no output-derived scoring key or
challenge commitment may enter it. All three checked-in templates—discovery,
final execution, and private sealed evaluation—are currently unassigned; the
last can only be instantiated after sealed outputs exist.

The authorization regenerates the hidden 64-seed `8/16/24/16` partition and
derives dependency edges from content-addressed learned-state ancestry rather
than trusting a free graph. Discovery covers every transformer-block candidate
and every primary pair; causal profiles are recomputed from exact raw outputs,
carrier bindings, and per-condition hook-ledger records. The full fixed
post-discovery plan is 16,992 forwards. The pre-auditor barrier accepts only the
exact regenerated prompt/raw-output inventory and self-addressed ledger
declaring 8,064 causal-label, 4,320 behavior-fit, and 4,032 sealed-test forwards:
exactly 16,416, with diagnostic forwards fixed at zero and pending. That closes
inventory integrity and derived outcomes under the declared authority, not
per-completion locked-model provenance or physical execution.

Only after all 4,032 `D_sealed_test` outputs exist may the evaluator create one
private sealed authorization per fold. Each authorization binds the raw 2,880
weak and 1,152 challenge trials across all nine targets, the keys and opaque
auditor surface derived from those outputs, and one fold worker. Raw model and
dependency-cluster IDs and the private authorization never enter that worker's
realm; dependency-cluster IDs in development scoring files are HMAC-derived
pseudonyms. Three distinct capability IDs and no-shared-mount/cache/IPC
declarations are required, but they are authority declarations—not physical
isolation attestation. Fold-local estimator training and replay remain a
residual P1: absent separate proof, the result is prediction-locked rather than
certified blind. The `estimator_source`, `feature_spec`, `analysis_config`, and
`abstention_rule` hashes must be identical across all folds; fitted estimator
weights and fold calibration status may differ. Production `fold_runs` contain
no reveal bytes or nonces; only after every commitment, bundle, prediction,
redaction, and common-root check
closes may the coordinator invoke the exact four-field authority opening
provider, whose bytes are independently rederived and verified. Cue-mask
diagnostics run only after all three prediction commitments close. These hashes
provide evidence integrity under the declared authority, not physical runtime
attestation.

The detector uses an observation set. Explicit cue conflicts and the held-out
mismatch-table rendering are not features. In the OSS study, cue masking is a
post-prediction-commitment diagnostic rather than part of the primary weak
observation set.
Success requires the inferred profile to predict the sealed relational outcome
distributions. If it only recognizes a route after seeing a decisive cue
intervention, the result is behavioral stress testing, not tomography.

Read [the research contract](docs/research_contract.md), [the architecture](docs/architecture.md),
and [the design-frozen OSS protocol](protocols/oss_reliance_regime_v0/protocol.json)
before adding a live backend.

## Claim boundary

Permitted when the corresponding evidence is established, not as blanket claims
of current achievement:

- “Outputs are behaviorally consistent with regime class R under calibration C.”
- “The estimator predicts failure pattern F on held-out perturbations.”
- “These two regimes are not identifiable under probe set Q.”

Not permitted:

- “We recovered the model's true hidden trace or chain of thought.”
- “A proprietary model uses a particular layer, head, or circuit.”
- “The model verified, remembered, believed, or rationalized” without a separate
  validated bridge from the operational construct to that language.
- “Tomographic reconstruction” as if the forward operator were known and
  injective.

## Roadmap

1. Phantom-0: validate schemas, leakage controls, nulls, and abstention.
2. OSS-1: close and authorize the controlled-anchor construction prerequisites,
   retain all planned outcomes, and validate the resulting registry and source
   evidence. Only then assign a separate discovery authorization, execute its
   bounded site discovery, close the evidence report, and assign the final
   execution lock before remaining measurement work.
3. Transfer-1: leave entire learned-weight dependency clusters out; checkpoints
   and task cases remain nested measurements.
4. Prospective-1: run three capability-separated fold workers, close all three
   prediction commitments before reveal, then score the equal-cluster global
   gate and only afterward release diagnostics.
5. API-1: report consistency classes, uncertainty, and drift, never an
   unverified internal truth; probability calibration remains a separate gate.

See [the full roadmap](docs/roadmap.md) and [the industrial thesis](docs/industrial_thesis.md).

## Scope and ethics

This is a model-auditing and system-identification project. It does not evade
access controls, extract weights, recover secrets, bypass rate limits, or claim
access to private chain of thought. Live adapters must use documented APIs,
respect provider terms and budgets, keep credentials in environment-backed
secret stores, and retain provider/version metadata only as audit provenance.
That telemetry is never part of the primary mechanism estimator.

Live work must also follow [RESPONSIBLE_USE.md](RESPONSIBLE_USE.md), including
target authorization, data-retention, redaction, and high-stakes human-review
requirements.

## Development

~~~bash
make test
make smoke
~~~

The core package has no runtime dependencies beyond Python 3.10 or newer.
The archived live-checkpoint replay requires Python 3.12.
See [CONTRIBUTING.md](CONTRIBUTING.md) for evidence and amendment rules.

## Prior work

Black-box perturbation auditing, model fingerprinting, hidden-behavior audits,
causal-variable benchmarks, and identifiability limits are all established
research areas. The intended contribution is their specific composition:

> an OSS-calibrated, output-only estimator of selected-site intervention-
> susceptibility equivalence classes, evaluated by
> leave-dependency-cluster-out transfer and prospective failure prediction,
> with explicit abstention bookkeeping. Open-set validation and probability
> calibration are successor-only gates, not current OSS-1 claims.

The mapped boundary and corrected references are in
[docs/prior_art.md](docs/prior_art.md).

## License

[GNU Affero General Public License, version 3 only](LICENSE)
(`AGPL-3.0-only`), not “version 3 or any later version.”

This license applies to the project code and documentation at this revision.
Historical commits retain their recorded license notices. Third-party models,
datasets, and referenced works retain their own licenses; a recorded upstream
license identifier is not changed by this repository's license.
