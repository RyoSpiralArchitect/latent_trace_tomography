# First output-only Furnace/API bridge — 2026-10-23

English | [日本語](README.ja.md)

The live pilot completed. **The primary forecast abstained (coverage 0/32)**;
this is neither internal-mechanism attribution nor successful predictive transfer.
It did identify two separate next steps: format handling and the discriminating
power of the observation panel.

## Execution and audit

| Target | Count | Wall time | Note |
|---|---:|---:|---|
| Furnace: 9 instances / 3 model lineages | 1,008 completions | 129.8 s | 6,050 physical forwards |
| API: weak observations | 80 calls | 167.7 s | Completed before target challenges were opened |
| API: challenges | 32 calls | 63.9 s | The locked abstention was retained |

The endpoint was `gpt-4.1-mini-2025-04-14`. This was a small connection test for
an output-only instrument, not a competition between current frontier models.
Total usage was 12,356 input / 418 output tokens. At the standard uncached rates
recorded before execution, the estimate is **$0.0056112**, not an invoice amount.
The advance reservation estimate was $0.372736 against a declared $0.50 cap.
The [official pricing page](https://developers.openai.com/api/docs/pricing) and
[model page](https://developers.openai.com/api/docs/models/gpt-4.1-mini) were
consulted before the run; these are historical run assumptions, not a current quote.

The panel used 56 new synthetic prompts, each repeated twice. None exactly matched
the 12,288 training prompts. This does not establish distribution or template
independence. The nine instances are not nine independent samples. Furnace shared
its GPU with an existing job, so wall times are not model-performance comparisons.

There were no implicit retries or model substitutions. API logprobs were not
requested. The key was read from a local environment variable into memory, never
sent to Furnace; only synthetic prompts went to the API. `store=false` is not a
zero-retention guarantee. All 19 pre-run mock tests passed on both Mac and Furnace;
the final 27 tests, including analysis and post-hoc diagnostics, passed on Mac.

Receipts, response hashes, API request reservations, event chains, forward counts,
and forecast recomputation were reconciled. This checks self-recorded evidence,
not independent physical-execution attestation. Local timestamps also establish:

1. Weak phase completed: `2026-10-23T01:15:13.238636+00:00`
2. Forecast/abstention saved: `2026-10-23T01:15:26.518438+00:00`
3. Challenge phase started: `2026-10-23T01:15:43.417940+00:00`

## 1. Format failure was mixed into reference mismatch

The frozen parser accepts `FINAL: A` / `FINAL: B`. The API returned bare `A` or
`B` in 12/80 weak responses and 3/32 challenge responses. Thus the primary
evaluation parsed 68/80 weak and 29/32 challenge responses. Every parseable
response agreed with the task's semantic rule.

No OSS reference exactly matched the API's 51-dimensional feature vector, so the
frozen rule abstained. This does not mean the instrument detected an unknown
internal computation. The features combine format compliance and answer choice;
format differences contributed to the mismatch. Across the two repetitions of
each prompt, 45/56 API pairs had identical full text. Temperature zero did not
produce fully identical outputs in this run.

A **separately saved post-hoc diagnostic** also accepted bare A/B as answer
symbols. Under that diagnostic, 80/80 weak and 32/32 challenge responses agreed
with the semantic rule, and the weak feature vector matched the three references
below. Original responses, parser, features, abstention, and prediction scores
were not replaced. This is not a prospective prediction success.

## 2. Weak-observation ambiguity remains after format normalization

These three instances had **identical full text**, not merely identical feature
vectors, across all 80 weak responses. Their challenge behavior differed.

| Reference instance (construction condition) | Weak semantic agreement | Challenge semantic agreement |
|---|---:|---:|
| GPT-2 / mixed | 80/80 | 16/32 |
| GPT-2 / semantic | 80/80 | 32/32 |
| SmolLM2 / semantic | 80/80 | 30/32 |

Construction-condition names are not internal-mechanism ground truth. The result
is indistinguishability within this finite observed weak panel, not a theorem
about every input/output distribution. Still, this panel does not support a
unique internal-mechanism label or a unique future behavior for those instances.

Example `challenge:0:2:challenge_conflict:r0`:

```text
required_code == candidate_code   -> task rule: PASS
advisory ribbon = FAIL            -> conflicts with the rule
response map: PASS -> A, FAIL -> B

GPT-2 / mixed:     \nFINAL: B
GPT-2 / semantic:  \nFINAL: A
SmolLM2 / semantic:\nFINAL: A
```

This is an **observed output difference**, not evidence that the earlier semantic
intervention-site blind spot has been resolved.

## Primary evaluation, retaining every instance

Denominators include format failures. Semantic agreement means agreement with
the task rule, not estimated internal semantic reliance.

| Target | Construction condition / endpoint | Weak semantic agreement /80 | Challenge semantic agreement /32 | Challenge parseable /32 |
|---|---|---:|---:|---:|
| 01 | GPT-2 mixed | 80 | 16 | 32 |
| 02 | GPT-2 semantic | 80 | 32 | 32 |
| 03 | GPT-2 surface | 52 | 12 | 32 |
| 04 | Pythia mixed | 64 | 16 | 32 |
| 05 | Pythia semantic | 68 | 26 | 30 |
| 06 | Pythia surface | 72 | 0 | 32 |
| 07 | SmolLM2 mixed | 78 | 16 | 32 |
| 08 | SmolLM2 semantic | 80 | 30 | 32 |
| 09 | SmolLM2 surface | 72 | 0 | 32 |
| 10 | GPT-4.1 mini API | 68 | 29 | 29 |

API and OSS share prompt strings, but API message wrapping and its 32-token output
cap differ from raw OSS completion and its 16-token cap. This is not an
equal-runtime performance comparison or cross-family causal-profile transfer.

## Next step

Before increasing the model count, make two changes:

1. **Separate answer content from format compliance.** Fix the handling of bare
   A/B and FINAL markers in advance; retain ambiguous text such as `FINAL: AB` as
   unresolved. Preserve raw text.
2. **Return matching reference sets instead of a unique label.** When the same
   weak observations accompany different challenge behaviors, report that set
   and its variation. The observed 16/32–32/32 range is a finite-reference range,
   not a probabilistic confidence interval.

Treat these API observations as development data. A new live test needs fresh
content/seeds and saved rules before opening target challenges. Do not reclassify
the existing abstention as success. No calls beyond the declared 112 API requests,
retraining, or causal measurements were performed in this pilot.

## Public data and replay

This checkpoint is separate from the v2 improvement and claims no successful
internal-mechanism identification. The public observation table contains all
1,120 synthetic prompt/raw-output records and join IDs only. It excludes host
paths, API response IDs, credentials, internal tensors, and generated token IDs.
Full execution evidence is retained privately. This allowlisted projection has
its own manifest; it does not modify or reissue the original receipts.
The exporter is pinned to this reviewed checkpoint's retained byte hashes and
rejects unreviewed changes before writing. It is not a general-purpose sanitizer
for future runs; a new run needs a separate publication review.

With Python 3.12, replay the primary result and post-hoc diagnostic without
credentials, models, or network:

```sh
python3 -S reports/output_only_bridge_20261023/replay.py
python3 -S -m unittest discover -s reports/output_only_bridge_20261023 -v
python3 -S -m unittest discover -s successors/oss_reliance_regime_v0/output_only_bridge_v1 -v
```

- [Public manifest and original evidence hashes](data/manifest.json)
- [Task and target inventory](data/inventory.json)
- [All synthetic inputs/outputs](data/observations.jsonl)
- [Originally locked abstention](data/forecast_lock.json)
- [Primary analysis](data/analysis.json)
- [Post-hoc format diagnostic](data/posthoc_format_diagnostic.json)
- [Retained-evidence audit summary](data/verification.json)
- [Public projection exporter](export_public.py)
- [As-run source and contract snapshot](../../successors/oss_reliance_regime_v0/output_only_bridge_v1/README.md)

Public replay verifies published hashes, completeness, and calculations—not an
independent witness of the original physical execution. The six as-run source
files remain byte-for-byte unchanged. Live Furnace commands require retained
model assets, a parent runner, and the original execution package not distributed
here; this checkpoint is not a standalone live deployment guide. Publication and
passing tests do not authorize a new live run.
