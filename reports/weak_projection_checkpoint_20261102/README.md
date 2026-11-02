# What did a new view distinguish? The last-digit checkpoint

English | [日本語](README.ja.md) · November 1–2, 2026 · [Offline replay](replay.py) · [Public data manifest](data/manifest.json)

Two within-lineage pairs of OSS anchors gave identical raw answers on an earlier 80-slot panel. A new, cue-aligned panel separated both pairs, but at different contrasts. Matching the endpoint's control answers also narrowed six **future Luna answers** from two candidates to one. The written task rule and copying the corresponding control answer achieved the same 6/6. No intervention effect or internal mechanism was estimated for Luna.

## Which edit separated the twins?

The synthetic permit rule says PASS only if the submitted and required codes match exactly. The advisory always agreed with that rule. For three fresh dockets and two reversed answer maps we used four inputs per cell: exact match, different prefix plus 12 different suffix digits, same prefix plus those same 12 different digits, and same prefix with only the last digit different. The last three legal decisions are all FAIL. Each prompt was dispatched twice. These are six dependent docket/map cells, not six model families. One edited character need not be one edited token.

| Stable disagreements within an OSS pair | Exact PASS | Different prefix, FAIL | Same prefix, 12 digits differ | Only last digit differs | Last-digit-only split after **three stable, correct** controls |
|---|---:|---:|---:|---:|---|
| GPT-2 mixed / semantic | 0/6 | 0/6 | 6/6 | 6/6 | No eligible cells; not estimable |
| SmolLM2 mixed / semantic | 0/6 | 0/6 | 1/6 | 6/6 | 5/5 eligible (5 of 6 planned) |

For SmolLM2, mixed said FAIL and semantic said PASS in all five incremental splits. Two dockets reproduced that direction under both codebooks. GPT-2 had already separated at the prefix control. The anchor names describe their training; they do not identify the endpoint's strategy.

## What was predicted before the API answered?

We sent only the 18 distinct control prompts (36 calls) to `gpt-6-luna` first. Both repeats on all 18 had to match in normalized A/B, with at least two distinct OSS base lineages represented. All matches were retained: GPT-2 mixed and SmolLM2 mixed. The [saved forecast](data/forecast_lock.json) preceded the first of the 12 last-digit calls. A failed support check means abstention, not a fallback guess.

| Predictor for the six held cells | Predictions before reveal | Observed containment |
|---|---|---:|
| OSS anchors matching the endpoint controls | One symbol per cell (the FAIL-mapped symbol) | 6/6 |
| All four OSS anchors without endpoint controls | Both A and B in every cell | 6/6, **zero** singleton predictions |
| Apply the stated law | One symbol per cell | 6/6 |
| Copy the endpoint's stable same-prefix far answer | One symbol per cell | 6/6 |

All 48 API answers were correct after normalization; only 24/48 used the requested marker. Ten of 24 identical-prompt repeat pairs changed raw text; zero changed normalized judgment. A strict parser and a decision audit measure different failures. The OSS arm completed 192/192 generations in 1,152 physical forwards (192 prefill, 960 decode). The API arm completed 36 + 12 generation dispatches with no retries or unknown dispatch outcomes. [Execution summary](data/execution.json).

## Evidence that did **not** establish reconstruction

- **Format probes, November 1.** On the equality panel, all 96 normalized answers were correct. Full-task joint successes (right answer *and* requested format) were 16/32 for the marker and 32/32 for bare output; supplied-decision controls were 15/16 and 16/16. All 17 bare-only success pairs actually had identical text across instructions (post-hoc check). On a separate 96-slot fresh-rule panel, bare won on directed paths (full task 13/16 vs 16/16; supplied decision 6/8 vs 8/8) but tied on the sum rule (16/16 and 8/8 for both formats). Normalized correctness was again 96/96. This is **partial recurrence**, not a general bare-format advantage. The original [call-free format specification](../../successors/oss_reliance_regime_v0/output_contract_probe_v1/README.md) was not edited to authorize these later runs.
- **A known collision, a different pair.** Pythia and SmolLM2 *surface* anchors returned the same visible texts on 16 prior and 24 new distinct prompts, including the omission probe. Their empirical targeted-minus-null donor-transfer counts were 9 and 12 out of 16 fixed evaluation pairs. For a deterministic point rule given just this common orbit, worst-case absolute error on these two measured values is at least **3/32**; an interval covering both must span at least **3/16**. The [fixture](data/surface_collision.json) includes one shared orbit and the two reference values, not two independent new traces or a population bound.
- **Retrospective nine-anchor transfer attempt.** With one of three base lineages held out, exact 80-slot matches issued two point ranges and missed both (the reciprocal directions of one pair). A stricter two-lineage bracket abstained on all nine. Separating *measurable on this panel* from *value if measurable* returned six conditional brackets, zero unconditional numerical offers, and zero singleton measurement-state decisions. Four of the six measurable anchors had a bracket; 3/4 fell inside and only 2/4 equaled an observed support value. The other two issued brackets were on non-distinguishing panels, not numerical hits. On the same four scored anchors the mean width fell from 41/64 to 15/64 against behavior-blind calibration; **both methods missed the same target**, whose 12/16 exceeded the training maximum 9/16. The no-misses narrowing criterion failed.

In that last comparison the numerical label is an integer targeted-minus-norm-matched-null donor-transfer count divided by **all 16** evaluation pairs. With zero distinguishing base/donor answers despite a complete parsed panel the value is undefined, not a measured zero. Missing records would not establish non-measurability. These are small, selected-site reference measurements, not the complete frozen OSS-1 profile. The joins use declared historical unit/training/base identities; this retrospective archive join does not independently attest checkpoint bytes across sessions. The November 2 live run separately verified its four base-plus-adapter identities. Earlier Mistral and v1 primary abstentions remain intact.

## What the public replay verifies

From the repository root, Python 3.10+ and the standard library suffice:

```sh
python3 -B -S reports/weak_projection_checkpoint_20261102/replay.py
python3 -B -S -m unittest discover -s reports/weak_projection_checkpoint_20261102 -v
```

The replay checks data hashes, regenerates the exact panel, uses only controls to reproduce the lock, checks recorded phase ordering, and then scores held answers. It also recomputes the historical fold summaries from the [published weak observations](../mistral_bridge_20261029/data/observations.jsonl) and [cue counts](data/reference_counts.json). For the format studies it recounts visible outputs against their own keys. The [exporter](export_public.py) accepts only [pinned originals](source_pins.json) and selects public fields. Private journals, machine paths, keys, provider IDs and per-response telemetry are not distributed. An original's hash and a local timestamp are provenance, not independent provider or hardware attestation. No new model calls are made by replay or authorized by publication.
