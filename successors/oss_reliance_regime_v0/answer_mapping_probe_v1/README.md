# Answer-mapping probe v1 — design only

English | [日本語](README.ja.md)

This is a small follow-up to the [Mistral checkpoint](../../../reports/mistral_bridge_20261029/README.md),
not a new live experiment or a relaxation of its abstention. All twelve observed errors there
required `FAIL → A`. The next question is whether a similar output pattern persists when the
decision is given explicitly, or appears only when evidence evaluation and answer coding are combined.

## Exact panel

| Component | Factors | Unique prompts | Two repetitions |
|---|---|---:|---:|
| Full task | 2 content × 2 semantic × 2 cue × 2 layout × 3 response modes | 48 | 96 |
| Mapping-only control | 2 content × 2 provided decisions × 2 maps | 8 | 16 |
| Total | | 56 | 112 |

- Semantic decision: PASS if candidate code equals required code, otherwise FAIL.
- Cue: PASS or FAIL, independently crossed with the semantic decision.
- Layout: baseline required/candidate order, or its reversal. Distractor and attenuation
  variants are intentionally outside this first probe to keep the panel small.
- Full-task modes: direct `PASS/FAIL`; standard `PASS→A, FAIL→B`; inverted `PASS→B, FAIL→A`.
- Mapping-only controls supply PASS or FAIL explicitly; they contain no code-comparison task
  and no advisory cue. They retain the same standard/inverted response map.
- Map line order remains PASS then FAIL. This experiment does not disentangle map-line order
  from symbol priors; a subsequent control may be needed if an effect remains.

The generator fixes two fresh deterministic content codes and a hash-sorted schedule inside
each repetition block. Both repetitions have byte-identical prompts. Tests reject exact prompt
overlap with the two published development panels; no claim is made about unavailable training
data or distribution independence. The content generator and template remain related to the
earlier tasks. Two content instances are not a powered or cross-family confirmatory sample.

## Fixed readouts

The primary contrasts are **inverted error rate minus standard error rate**, separately for
full tasks (32 observations per mode) and mapping-only controls (8 per mode).
Report counts and denominators, not a statistical significance or mechanistic-success label.

Secondary readouts are paired direct-correct versus encoded-correct tables (32 dependent pairs
per encoded mode), semantic-decision, cue-conflict and layout breakdowns, format/unresolved
counts, and repeat disagreements. Direct responses accept only bare PASS/FAIL or exact
`FINAL: PASS`/`FINAL: FAIL`; encoded responses accept bare A/B or `FINAL: A`/`FINAL: B`. Outer whitespace is
stripped; all other responses remain unresolved and count as errors in the planned denominator.
Missing/duplicate slots are execution failures, not scientific abstention or zero-error cases.

| Observation | Bounded interpretation |
|---|---|
| An inverted-minus-standard error gap also appears with a supplied decision | Mapping-sensitive behavior persists without the evidence-comparison task |
| Direct and mapping-only controls are correct, but encoded full tasks fail | Compatible with a composition/context-sensitive failure |
| Direct full-task output fails | The error is not confined to A/B coding |
| No contrast, mixed results, or unresolved responses | Report the null/mixed outcome; do not expand or retune automatically |

These possibilities can coexist. Changing output instructions changes the full prompt and may
change the computation. The controls do **not** surgically isolate an internal stage, identify
cue circuitry, or provide calibrated mechanism labels. The hypothesis was selected after the
October 29 results; a future run is a fresh behavioral diagnostic, not confirmation of a hypothesis
selected before that checkpoint.

## Launch boundary

[design.json](design.json) and the checked-in [manifest](fixtures/manifest.json) fix requests,
scoring keys and generator bytes. They explicitly set `live_execution_authorized: false`.
This package has no API client and neither reads credentials nor calls Furnace.

A later live run needs explicit authorization, current endpoint availability/pricing, a pinned
transport configuration and a model-free rehearsal. Proposed settings are `mistral-large-4`,
temperature 0, max 32 output tokens, reasoning effort none, standard tier, one completion/request.
The ceiling remains 112 generations and $0.50, with no retry, substitution or continuation after
a technical failure. Recheck prices before reserving the 2,048-input/32-output allowance; the
previous $0.32693248 estimate is historical, not a current quote. No OSS retraining or additional
model family is part of this design.

```sh
python3 -S successors/oss_reliance_regime_v0/answer_mapping_probe_v1/design.py verify \
  --out successors/oss_reliance_regime_v0/answer_mapping_probe_v1/fixtures
python3 -S -m unittest discover -s successors/oss_reliance_regime_v0/answer_mapping_probe_v1 -v
```

`prepare --out NEW_DIRECTORY` creates the same request/scoring artifacts without overwriting.
`requests.json` contains only query IDs and prompt strings; scoring metadata is separate.
The public query IDs encode design factors, so they are audit joins, not blind model input:
any future transport must send **prompt_text only**, never IDs or the scoring key. The frozen
v2 reference-matching result remains unchanged regardless of this follow-up's outcome.
