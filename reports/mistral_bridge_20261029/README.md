# Mistral bridge checkpoint — October 29, 2026

English | [日本語](README.ja.md) · [Replay data](data/manifest.json) · [Next small design](../../successors/oss_reliance_regime_v0/answer_mapping_probe_v1/README.md)

## Result

All 112 API generations completed. **The primary result is abstention outside
the reference support**, not successful reference-based prediction.

Every weak output resolved to A/B, but none of the nine references matched the
entire case-aligned answer trace. The unchanged v2 matcher produced an empty
support set, saved before the 32 target challenge responses were collected.
This checkpoint does not demonstrate selective prospective transfer.

A separate post-hoc diagnosis found task-oracle agreement of **70/80 weak
observations and 30/32 challenges**. All twelve errors required `FAIL → A` under
the inverted response map. They represent six unique prompts repeated twice.
This motivates an answer-mapping probe; it does not identify an internal
codebook mechanism, cue circuit, or hidden reasoning trace.

## Experiment and execution

The fresh-content panel contains two content instances, forty unique weak
prompts and sixteen unique challenge prompts, each repeated twice. Weak
observations keep semantic evidence and the advisory cue aligned. Challenges
introduce cue conflict, with ordinary and table renderings. Both phases cross
PASS/FAIL decisions and standard/inverted A/B response maps.

The reference cohort contains nine controlled descendants of three declared
base lineages. They are **not nine independent model families**, and construction
condition names are not validated mechanism labels. The same prompt strings
were used for OSS and API measurements, but raw OSS completion and provider
chat execution are different runtime conditions, not a controlled comparison
of weights alone. The causal-calibration bridge remains unresolved.

| Measurement | Retained reference run | Mistral target run |
|---|---:|---:|
| Completed generations | 1,008 | 112: 80 weak + 32 challenge |
| Physical forward count | 6,112 | Not observable through this API |
| Recorded elapsed seconds | 136.980 receipt wall time | 398.579, summed generation phases |

The reference ledger separately records 136.989 seconds; its timing boundary
differs slightly from the receipt. These timings do not establish comparative
model speed. The reference run preceded the API run; this report and its replay
perform **zero new model/API calls**.

The API run used `mistral-large-4`, temperature 0, max 32 output tokens,
reasoning effort none, one completion per request and `standard_only` service.
All returned model IDs matched that name; all finish reasons were `stop`.
There were no retries or model substitutions, and one separate model-metadata
GET. A returned model name does not identify an immutable weight snapshot.
Changing provider makes this a new target experiment, not a same-endpoint
replication of an earlier provider result.

Recorded usage was 12,096 input and 422 output tokens, 12,518 total. The estimated
uncached list-price cost was **$0.01821452**, against a $0.32693248 reservation
and $0.50 cap. These are historical estimates, not an invoice or current quote;
the retained pricing record names the [official model card](https://docs.mistral.ai/models/mistral-large-4-0)
and the October 29 price-check date. [Execution summary](data/execution.json).

## Primary evaluation: preserve the abstention

The forecast was recorded at 04:46:16 JST, and target challenge collection
started at 04:46:35 JST on October 29. The exported timestamps and source hashes
support the retained local ordering; they are **not independent execution
attestation**. The public replay does not recreate a blind execution environment.

| Readout | Conditional reference prediction | All-nine-reference baseline |
|---|---:|---:|
| Available challenge sets | 0/32: abstention | 32/32 |
| Containment | Not evaluated: no predictions | 32/32 |
| Resolved singleton sets | 0 | 0 |
| Composition | Empty | 22 `{A,B}`; 10 `{A,B,unresolved}` |

Every baseline set includes both A and B. Since every target challenge response
resolved to A/B, its 32/32 containment offers **no answer discrimination** here.
The conditional JSON field `contained: 0` means no predictions were issued, not
32 incorrect predictions. These finite observed sets are not probabilities or
guaranteed future coverage. [Saved forecast](data/forecast.json).

Weak output formats were 45 exact markers and 35 bare symbols; challenge formats
were 21 exact markers and 11 bare symbols. Both phases had zero unresolved
responses. The unchanged v2 parser accepts both forms as content, while keeping
format compliance separate. **This abstention was content-driven, not a format
failure.** Logprobs, internals, provider identity, latency and token usage were
not matching features. The v2 module retains its conservative
`development_only_not_prospective_validation` label; the surrounding run's
commitment does not turn that label into a transfer-success claim.

## Post-hoc diagnosis: inverted answer mapping

The following analyses were selected after collection. They do not replace the
primary evaluation or change its matcher. The task oracle is calculated from
the frozen generator's cell definitions and cross-checked against each actual
prompt's code comparison and response map.

| Projection | Task-oracle agreement |
|---|---:|
| Weak baseline | 16/16 |
| Rule paraphrase | 16/16 |
| Evidence reorder | 12/16 |
| Irrelevant distractor | 12/16 |
| Cue salience attenuation | 14/16 |
| Challenge conflict | 14/16 |
| Challenge table | 16/16 |

The ten weak errors occurred where semantic and cue values were both FAIL under
`PASS → B / FAIL → A`. Both routes prescribe A there, so the observed B answers
cannot by themselves establish cue reliance. The two challenge errors also
required `FAIL → A`, but their cue conflicted with the semantic evidence.
Mapping sensitivity, cue sensitivity and context interactions remain competing
explanations. There was no targeted internal intervention in this API test.

Canonical answers agreed in all 40 weak and 16 challenge repeat pairs. Format
changed in five pairs per phase. Twelve erroneous measurements are six unique
prompts, not twelve independent failures; this small panel establishes neither
general determinism nor general failure prevalence.

Nearest references 01 and 02 each differed on 10/80 weak slots. Distances for
the others were 22 (03), 20 (04), 16 (05), 14 (06/09) and 12 (07/08).
Nearest is not support under the saved exact-match rule. No approximate-match
rescue was applied. [Recomputed analysis and error records](data/analysis.json).

## Next small design and practical relevance

Before expanding the reference cohort, compare direct PASS/FAIL answers against
standard and inverted A/B maps on new content. Add controls that supply the
decision explicitly, so no evidence comparison is needed. The
[answer-mapping design](../../successors/oss_reliance_regime_v0/answer_mapping_probe_v1/README.md)
fixes **96 full-task requests + 16 mapping-only controls = at most 112**, with
two repetitions and a separate $0.50 ceiling. It has no API client and explicitly
sets `live_execution_authorized: false`.

The two primary descriptive contrasts are inverted minus standard error rate,
separately for full tasks and mapping-only controls. Direct-answer comparisons,
semantic/cue/layout breakdowns and unresolved outcomes remain visible. A null
or mixed result is retained without automatically retuning the panel.

This also frames a practical API question: **response instructions are part of
both the measurement conditions and the application interface**. A lower-error
response format, if established on fresh tasks, could inform interface design
without recovering any hidden mechanism. Direct PASS/FAIL has not yet been
tested here; it is a hypothesis, not a recommended fix or production-readiness
claim. Changing instructions can change the computation itself, so these
controls do not isolate an internal stage.

## Public evidence and offline replay

The public export contains all **1,120 synthetic prompt/output observations**:
1,008 reference completions and 112 API completions. Each observation has only
`target_id`, `case_id`, `projection_id`, `replicate_id`, `prompt_text`, `output_text`.
The inventory holds design factors and provenance separately; target challenge
outputs never enter the predictor's input bundle.

[export_public.py](export_public.py) accepts only this reviewed checkpoint's
exact-byte source hashes. It verifies original receipt/artifact bindings and
event chains, then copies allowlisted fields. Original receipts, live runners,
credentials, host paths, provider response IDs and tensor/token-level telemetry
are not published. The [public manifest](data/manifest.json) preserves hashes
of retained originals and exported files; public readers can verify the
exported dataset, but cannot independently inspect the private originals from
their hashes alone. This is a derived publication, not a rewrite of the run.

From the repository root, with Python 3.10+ and no credentials:

```sh
python3 -S reports/mistral_bridge_20261029/replay.py
python3 -S -m unittest discover -s reports/mistral_bridge_20261029 -v
```

Replay checks exported hashes, the pinned v2 source, complete slot inventories,
the saved forecast, local ordering and the primary/post-hoc calculations.
Tests include target-challenge isolation, duplicate/missing-slot rejection,
extra telemetry rejection, task-oracle cross-checking and tamper detection.
This is reproducible **analysis of saved observations**, not a fresh inference
reproduction or independent provider attestation.

Evidence tier: `prospective_engineering_pilot_not_causal_validation`. The frozen
OSS-1 contracts and the [October 23 checkpoint](../output_only_bridge_20261023/README.md)
remain unchanged. Two content instances and repeated measurements do not
establish mechanism recovery, calibrated probabilities, or cross-family
generalization.
