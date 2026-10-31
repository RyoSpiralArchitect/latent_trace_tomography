# GPT-6 Luna answer-mapping checkpoint — October 31, 2026

English | [日本語](README.ja.md) · [Replay data](data/manifest.json) · [Next design](../../successors/oss_reliance_regime_v0/output_contract_probe_v1/README.md)

## Result

All 112 generations completed. **All 112 answers were correct under the frozen
parser, but only 86 used the requested `FINAL:` marker.** Bare symbols were
explicitly accepted before execution; the 26 bare responses were not rescued
by a post-hoc parser change.

| Condition | Correct / planned | Exact marker | Bare symbol |
|---|---:|---:|---:|
| Full task: direct PASS/FAIL | 32/32 | 32 | 0 |
| Full task: standard map | 32/32 | 13 | 19 |
| Full task: inverted map | 32/32 | 25 | 7 |
| Mapping-only: standard map | 8/8 | 8 | 0 |
| Mapping-only: inverted map | 8/8 | 8 | 0 |
| Total | 112/112 | 86 | 26 |

Both prespecified inverted-minus-standard error-rate contrasts were **0 percentage
points**. Unresolved responses and refusals were both zero. Parsed answers agreed
in all 56 repeat pairs. An additional **post-hoc** format-repeat readout found
8/56 pairs with different raw text and format: the `FINAL:` prefix appeared in
one response but not the other, without changing the parsed answer.

This is a small behavioral diagnostic, not recovery of an internal computation
stage. The earlier [Mistral reference-support abstention](../mistral_bridge_20261029/README.md)
remains unchanged. No OSS-calibrated reference profile was estimated for this run.

## What was fixed before outputs

The [parent design](../../successors/oss_reliance_regime_v0/answer_mapping_probe_v1/README.md)
provided the exact prompts, ordering, scoring key, parser and descriptive
contrasts. A separately authorized pre-output execution plan changed the target
from the candidate Mistral endpoint to `gpt-6-luna` and pinned its transport.
The parent's design-only authorization field was not rewritten.

There were 96 full tasks and 16 supplied-decision mapping controls: 56 unique
prompts, each repeated twice. Full tasks crossed two content instances, PASS/FAIL,
aligned/conflicting advisory cues, baseline/reordered evidence and direct/
standard/inverted response modes. Mapping controls crossed the two content
instances, supplied PASS/FAIL and standard/inverted maps, without evidence
comparison or an advisory cue.

Only prompt text was sent to the provider, never query IDs or scoring metadata.
The scorer receives only query IDs and visible output strings. Provider name,
token usage, elapsed time, response metadata, internals and logprobs are not
scoring features. Two content instances and dependent factorial/repeat slots
are **not 112 independent subjects**.

The Responses API settings were temperature 0, reasoning effort `none`, max 32
output tokens, default service tier, no tools or streaming, truncation disabled,
and `store:false`. The last setting is not a guarantee of zero provider retention.
Returned model names matched `gpt-6-luna`; an alias is not an immutable checkpoint
identity. There were no retries or substitutions, and one separate metadata GET.

## Execution and practical interpretation

The live attempt took 292.889 seconds. Usage was 11,144 input and 732 output
tokens, 11,876 total. At the retained October 31 rates, the uncached estimate was
USD 0.0014804; reserving all input at the highest pinned short-context cache-write
rate gives USD 0.003152. The execution ceiling was USD 0.50. These are historical
usage-based estimates, not invoices or current quotes.
[Execution record and price source](data/execution.json).

An exact-marker-only consumer would accept 86/112 of these same saved responses;
the frozen research parser accepts 112/112. This is an offline comparison of
acceptance rules, not a new model experiment. It illustrates why answer
correctness and output-format compliance need separate audit fields.
It does not establish that a different prompt or parser improves future behavior.

Temperature 0 did not make formatting invariant in this run. These observations
do not identify whether that variation came from the model, serving system, or
another cause. The model and prompt panel differ from the earlier Mistral run,
so these results do not support a controlled superiority comparison, replication
of the Mistral failure, or cross-family generalization. No inferential confidence
interval or significance claim treats the 112 slots as independent.

## Public evidence and replay

The public data contains all 112 visible responses as exactly `query_id` and
`output_text`. The parent fixtures supply the corresponding prompts and scoring
keys. Aggregate execution metadata is kept in a separate file.

[The exporter](export_public.py) accepts only the reviewed originals' exact
hashes, verifies request/response/record event bindings and the terminal receipt,
then emits explicitly selected fields. Original receipts, host paths, live
runner, credentials, provider response IDs and per-response telemetry remain
private. The [manifest](data/manifest.json) records original and public hashes.
Readers can verify the public data and analysis, but cannot inspect or independently
attest private originals from their hashes alone. This is a derived publication,
not a rewrite of the run or independent proof of provider execution.

From the repository root, using Python 3.10+ without credentials:

```sh
python3 -S reports/gpt6luna_answer_mapping_20261031/replay.py
python3 -S -m unittest discover -s reports/gpt6luna_answer_mapping_20261031 -v
```

Replay verifies the frozen parent source, public file hashes, complete unique
slots, saved analysis and aggregate execution arithmetic. Tests cover missing/
duplicate slots, extra telemetry, unresolved denominators, duplicate JSON keys,
non-finite numbers, mutation detection and the export boundary. Replay performs
zero new model/API calls. Evidence tier:
`descriptive_behavioral_diagnostic_not_mechanistic_validation`.

## Next boundary

The [96-request output-contract design](../../successors/oss_reliance_regime_v0/output_contract_probe_v1/README.md)
compares requests for `FINAL: A/B` against bare `A/B`, keeping the underlying
decision task paired. It separates joint success, normalized correctness and
format compliance. The question was selected after this result; it is not a
pre-existing mechanism hypothesis. The design is unexecuted and not yet live-ready.
Publishing or merging it does not authorize another API run.
