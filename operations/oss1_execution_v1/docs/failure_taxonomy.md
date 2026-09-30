# LTT failure taxonomy and product-language boundary

Status: `post_freeze_derived_vocabulary`

Parent protocol SHA-256:
`5c49316503b2cec2ad26d4bf47dc59c02f0b61d9f6896b84035e6d0412dced11`

Normative for OSS-1: `false`

Authorization effect: `none`

## Why the taxonomy is factorized

An observed output, an inference about a failure surface, an OSS-reference
compatibility hypothesis, and the integrity state of the instrument are
different objects. A single enum such as `semantic_failure` would collapse all
four and invite causal overstatement.

Every future report should therefore represent at least five independent axes:

1. evidence layer;
2. measurement validity;
3. scientific disposition;
4. assurance level;
5. claim tier.

An event is not classified scientifically when measurement validity is
`fail_closed`.

## Evidence layers are separate contracts

The layers are not a maturity staircase. Evidence at one layer does not
automatically promote a report to the next.

| Layer | Name | Estimand | Maximum safe statement |
|---|---|---|---|
| L0 | Behavior Drift Detection | change in a frozen response surface | a material response-surface shift was detected under the frozen panel |
| L1 | Prospective Failure-Surface Prediction | sealed future challenge-outcome distribution | weak observations prospectively predicted the named failure surface |
| L2 | OSS-Reference Susceptibility Compatibility | consistency with a causally calibrated OSS reference equivalence class | under protocol P and calibration C, the endpoint is consistent with reference class R at uncertainty U |

`LTT Sentinel` is a plausible product label for L0 and L1. It does not yet
exist as a validated live product. `LTT Attribution` may remain a roadmap label,
but scientific outputs at L2 must say `OSS-reference susceptibility
compatibility` until a successor freezes and passes a cross-site/model
comparability bridge.

### L0 — Behavior Drift Detection

L0 requires a separate outcome-naive drift contract that freezes, before the
comparison:

- panel, parser, metric, and materiality threshold;
- baseline and current query plans;
- decoding, retry, time-block, router, RAG, tool, and postprocessor provenance;
- raw-text and parse content addressing;
- query budget and endpoint-version policy;
- provider nonstationarity and confound handling.

Passing language:

> A shift at or above the frozen materiality threshold was detected on panel P
> between blocks B and C.

Non-passing language:

> No material shift was detected at this instrument's frozen sensitivity.

Do not render `no drift` or `nothing changed`.

### L1 — Prospective Failure-Surface Prediction

Minimum evidence:

- features come only from the frozen weak observation surface;
- challenge material remains sealed until all three prediction commitments;
- semantic-consistent, surface-cue-consistent, and parse-failure probabilities
  close every slot;
- abstention and parse failure remain in scoring;
- candidate and baselines use equal-cluster global aggregation;
- the candidate improves at least 10% over the stronger global frozen baseline;
- no single-fold score is called authoritative.

If the prospective gate fails, the result may remain a robustness audit or a
negative scientific result. It does not support L2 attribution language.

### L2 — OSS-Reference Susceptibility Compatibility

Minimum evidence for the current engineering pilot:

- targeted interchange against the identical-site norm-matched null;
- self-sham, control-site, and codebook-competence controls;
- discovery/evaluation separation and immutable selected sites;
- site-selection stability evidence;
- leave-dependency-cluster-out transfer;
- prospective challenge validity;
- exact calibration-domain and abstention language.

For a closed endpoint without a separately frozen comparability bridge, the
maximum L2 statement remains bounded equivalence-class consistency under the
named protocol and OSS calibration set. The bridge is required only to upgrade
that compatibility statement into direct susceptibility or reliance
attribution. A calibrated posterior, open-set guarantee, or proprietary
internal-truth claim requires a successor contract.

## Measurement validity

```text
valid
not_evaluable
fail_closed
```

- `valid`: every applicable contract and evidence-closure check passed.
- `not_evaluable`: the comparison lacks enough comparable evidence, such as an
  endpoint version, baseline, or required observation.
- `fail_closed`: authorization, manifest, phase order, leakage, budget, slot,
  hash, or evidence closure failed.

`fail_closed` artifacts contain reason codes and preserved evidence only. They
must not contain a scientific class, compatibility profile, or confidence
statement.

## Scientific disposition

```text
supported
not_supported
unresolved
abstained
```

- `supported`: the prespecified scientific gate passed.
- `not_supported`: a valid experiment failed the prespecified gate. This is a
  legitimate negative result, not an integrity failure.
- `unresolved`: controls, site stability, identifiability, or evidence quality
  prevent the estimand from receiving a resolved interpretation.
- `abstained`: the instrument deliberately withheld class assignment. This is a
  product behavior, not a product crash.

`unresolved` is an epistemic status, not a failure type.

## Assurance level

```text
descriptive
integrity_checked
prediction_locked
blind_attested
```

- `descriptive`: an observation is recorded without a full integrity chain.
- `integrity_checked`: content, schema, budget, and phase closure passed.
- `prediction_locked`: all predictions were committed before reveal under the
  implemented coordinator barrier.
- `blind_attested`: physical worker isolation and fold-local estimator training
  and replay were independently evidenced.

The current implementation ceiling is `prediction_locked` unless separate
physical evidence is supplied. Capability IDs, hashes, and no-shared-resource
declarations do not alone establish `blind_attested`.

## Claim tier

```text
named_endpoint_observation
named_dependency_cluster_engineering_pilot
sealed_confirmatory
```

The OSS-1 three-cluster/nine-model design is always
`named_dependency_cluster_engineering_pilot`; effective `n=3`. Prompts, cases,
templates, checkpoints, anchors, and responses do not increase this `n`.

`sealed_confirmatory` is eligible only after a fresh, outcome-naive execution
with at least three development dependency clusters and at least three
separately sealed confirmatory dependency clusters, subject to a frozen power
analysis that may require more than this hard minimum.

## Observable outcome vocabulary

The challenge-outcome terms remain exactly:

```text
semantic_consistent
surface_cue_consistent
parse_failure
```

They describe outputs, not causes.

| Machine term | Customer-facing rendering | Explicit non-inference |
|---|---|---|
| `semantic_consistent` | task-rule-consistent response | does not prove semantic reasoning |
| `surface_cue_consistent` | cue-consistent divergence | does not prove cue reliance |
| `parse_failure` | unscorable output | does not prove codebook-binding failure |
| `abstained` | inference withheld | does not mean the endpoint is safe or unsafe |

Avoid `semantic failure`: it conflates the observed answer relation with its
internal cause.

## OSS-reference profile vocabulary

Research-side profile hypotheses may use:

```text
semantic_dominant_profile
cue_dominant_profile
mixed_profile
codebook_ineligible
projection_unstable
unresolved
```

For a closed endpoint, prefix the rendered claim with
`consistent_with_..._under_calibration`. Do not emit the profile as direct
internal fact.

Recommended translations:

| Tempting phrase | Bounded phrase |
|---|---|
| shortcut | cue-dominant reference compatibility |
| semantic failure | task-rule inconsistency observed |
| codebook failure | codebook-ineligible under the frozen competence gate |
| regime switching | projection-unstable response surface |
| unknown mechanism | compatibility attribution withheld |

## Reason-code namespaces

Reason codes identify instrument state and evidence boundaries. They do not
replace the scientific disposition.

- `AUTH_*`: authorization missing, invalid, or budget exceeded;
- `INTEGRITY_*`: schema, hash, manifest, raw-evidence, or slot closure failure;
- `LEAKAGE_*`: forbidden feature, identity leakage, or premature reveal;
- `PROVENANCE_*`: endpoint, ancestry, training, or time-block ambiguity;
- `MEASUREMENT_*`: self-sham, control-site, site-stability, parse, or codebook
  gate issue;
- `IDENTIFIABILITY_*`: observational equivalence, insufficient observations, or
  out-of-calibration surface;
- `TRANSFER_*`: heldout-cluster collapse or identity/style-only signal;
- `PREDICTION_*`: prospective baseline gate not passed;
- `ASSURANCE_*`: runtime, isolation, or fold training/replay not attested.

Representative codes:

```text
AUTH_DISCOVERY_UNASSIGNED
AUTH_QUERY_BUDGET_EXCEEDED
INTEGRITY_RAW_LEDGER_MISMATCH
INTEGRITY_SITE_REPORT_CARDINALITY
LEAKAGE_PRIVATE_IDENTITY
LEAKAGE_PREMATURE_REVEAL
PROVENANCE_ANCESTRY_UNRESOLVED
PROVENANCE_ENDPOINT_VERSION_UNKNOWN
MEASUREMENT_SITE_UNSTABLE
MEASUREMENT_CODEBOOK_INELIGIBLE
IDENTIFIABILITY_EQUIVALENCE_CLASS_UNRESOLVED
IDENTIFIABILITY_OUT_OF_CALIBRATION
TRANSFER_HELDOUT_CLUSTER_COLLAPSE
PREDICTION_GLOBAL_GATE_NOT_PASSED
ASSURANCE_PHYSICAL_ISOLATION_UNATTESTED
ASSURANCE_FOLD_TRAINING_REPLAY_UNATTESTED
```

## Report record shape

A future machine-readable report should factor fields approximately as:

```json
{
  "evidence_layer": "L1",
  "measurement_validity": "valid",
  "scientific_disposition": "not_supported",
  "assurance_level": "prediction_locked",
  "claim_tier": "named_dependency_cluster_engineering_pilot",
  "observable_outcomes": [],
  "compatibility_statement": null,
  "reason_codes": ["PREDICTION_GLOBAL_GATE_NOT_PASSED"],
  "limitations": []
}
```

The taxonomy is presently derived vocabulary, not an OSS-1 output schema. A
future report generator must freeze a successor schema and table-driven
compatibility rules before using it normatively.

## Required renderer and linter behavior

- A `fail_closed` report rejects inference and classification fields.
- An L0 report rejects prediction and attribution fields.
- An L1 report rejects causal-profile and reliance fields.
- A closed-endpoint L2 report uses only
  `consistent_with_equivalence_class` language.
- `parse_failure` never maps automatically to `codebook failure`.
- An abstention includes a reason while preserving the frozen probability
  simplex and scoring treatment.
- An uncalibrated artifact rejects `posterior`, `70% semantic`, and equivalent
  calibrated-confidence language.
- The three-cluster tier rejects `population`, `general`, `model-independent`,
  and equivalent claims.
- `blind` is rejected unless physical isolation and fold-training/replay
  evidence are present.
- A single-fold score cannot be rendered as the production result.
- L0 requires panel, metric, threshold, endpoint version, and time-block hashes.
- `no drift` is rejected; use the bounded non-detection language above.
- Customer-facing artifacts are scanned for raw model, run, checkpoint,
  lineage, tokenizer, family, and dependency-cluster identities where the
  relevant privacy boundary applies.

## Claims forbidden at every layer

- hidden trace, thought, or chain-of-thought recovery;
- proof of a proprietary model's specific layer, head, or circuit use;
- a mechanism change inferred from L0 drift alone;
- cue reliance inferred from a cue-consistent output alone;
- codebook-binding failure inferred from parse failure alone;
- model-family independence or population generalization from three clusters;
- population confidence intervals from case or prompt resampling;
- calibrated posterior language under an uncalibrated contract;
- certified blindness from same-process prediction locking;
- validated open-set safety without a successor protocol;
- absence of change inferred from non-detection;
- a claim that LTT Sentinel or an API product is already live-validated.
