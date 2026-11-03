# Where the advisory changes the answer

[日本語](README.ja.md) · Research checkpoint · 3–4 November 2026 (JST)

The two task-trained GPT-2 checkpoints sometimes gave the same *approval* despite different response patterns: across the panel **mixed** followed the advisory, whereas **semantic** always returned the symbol mapped to PASS. At one fixed layer, transplanting a rejection advisory into an initially approving recipient changed mixed to FAIL in **24/24** conditions and semantic in **0/24**. On six fresh dockets, moving an approval-advisory vector into mixed did not reverse a mismatching filing, even when we also transplanted the final candidate-code token from a matching context (**0/12**). The endpoint result is separate: the measured API alias `gpt-6-luna` answered aligned questions; we **abstained** from forecasting its answers on their advisory-flipped siblings.

## From API observations to the two open-weight references

In this permit task, the written rule is “PASS if and only if the submitted and required codes are identical.” The advisory may agree or disagree with that rule. Each answer map assigns PASS/FAIL to A/B or B/A; a fixed decision is not a fixed letter. Here is what changed since the [previous reference-only no-go](../../successors/oss_reliance_regime_v0/aligned_reference_separator_v1/README.md):

| Study | Observation | What it supports |
|---|---|---|
| Truthful coded advisory (three dockets) | In 24 coded-task conditions, Mistral-7B-Instruct-v0.3 and GPT-2 mixed had 7 stable disagreements, 2 agreements and 15 unscorable pairs. **None** of the seven differences had a scorable Mistral literal-with-legend control. | The decision discriminator abstained. A format failure is not a disagreement. |
| Literal advisory, measured on Luna | 48 distinct aligned texts, two requests per text: **96/96** rule-correct; **60/96** used the requested `FINAL:` marker, 36 used a bare symbol. Repeat text differed on 16/48 with no decision change. | Output format and decision can vary independently on this panel. Because the cue equalled the rule, this does not tell us which Luna followed. |
| Reuse those 48 texts on 12 open-weight references | One exact witness (SmolLM2 surface), nine contradicted, two unresolved. That witness followed the misleading advisory on **48/48** flipped siblings. The other still-compatible Mistral reference gave 18 rule, 7 advisory and 23 unresolved answers. | Only one declared family supported the exact weak match. **Zero forecasts issued; no Luna response collected on these 48 flipped siblings; forecast accuracy is undefined.** |
| Replicate a post-hoc eleven-way agreement | On six fresh mismatching dockets, all eleven previously scorable references followed the false approval on **1/6** dockets with the original answer map, **0/6** with the swapped map, **0/6** on both. The twelfth reference was unscorable, not dropped. | The eleven-way conclusion did not replicate across maps. On all eight conditions of all six dockets, GPT-2 mixed followed the advisory and GPT-2 semantic returned mapped PASS. These two named checkpoints motivate the intervention below; they are not random independent families. |

## Intervening on the same advisory location

On the 48 texts of the six-docket replication, we used the final token of the advisory value at zero-based layer 6 (residual stream after the layer). The prompt stayed fixed. A target intervention copied the vector from the opposite-advisory text **within the same model**; a control permuted the change with signs while preserving its norm. A self replacement rewrote the original vector. These were input-processing interventions, not edits to model weights or generated text.

| Original advisory → donor advisory | Mixed: target / matched control | Semantic: target / matched control |
|---|---:|---:|
| L6 PASS → FAIL, primary | 24/24 → FAIL / 0/24 | 0/24 changes / 0/24 |
| L6 FAIL → PASS, secondary | 9/24 → PASS / 0/24 | 0/24 changes / 0/24 |
| L3 PASS → FAIL, secondary | 24/24 → FAIL / 0/24 | 0/24 changes / 0/24 |
| L3 FAIL → PASS, secondary | 12/24 → PASS / 1/24 | 0/24 changes / 0/24 |

All 24 primary recipients started at mapped PASS in both models. The table shows *all actual decision changes*; the observed mixed changes also went in the intended direction. For semantic, both donor and recipient gave natural PASS: **zero informative pairs; conditional transfer rate undefined**, not a measured rate of zero. The replay reports all changes, changes toward the donor advisory, and changes to an initially different natural donor answer separately. The prespecified L3 secondary results show the effect was not unique to L6. As a positive control, transplanting the response map at L3 changed the symbol as predicted in **48/48 per model**, versus 0/48 under the matched null. The advisory precedes the case codes: only **two distinct directed cue-vector pairs** per model were used in the primary comparison. The 24 rows are repeated contexts. L6 had previously been selected for mixed.

## Does the final candidate-code token explain the asymmetry?

The historical reverse patch gave mixed 9/12 approvals on matching codes, 0/12 on mismatches. On **six new dockets**, cue-only gave 10/12 and 0/12, respectively; the other direction again gave 24/24 rejections. The table counts **mapped PASS** on recipients whose written advisory is FAIL. In the primary CONTEXT donor only the *required* code changes. The candidate literal, its terminal token ID and absolute position stay identical; the endpoint now comes from the opposite equality context. Both sites are patched at L6 simultaneously. Each stratum is six dockets × two answer maps.

| Written codes | Both sites self | Candidate only | PASS cue only | PASS cue + candidate | PASS cue + norm-matched candidate null |
|---|---:|---:|---:|---:|---:|
| Mismatch; endpoint from matching context | 0/12 | 0/12 | 0/12 | **0/12** | 0/12 |
| Match; endpoint from mismatching context | 0/12 | 0/12 | 10/12 | **8/12** | 9/12 |

Neither frozen primary gate passed. In the mismatch stratum **all nine** target/self/null combinations returned zero approvals. In the match stratum two approvals switched to rejection (none back), one under each map but on only **2/6 dockets**. The increment over cue-only, interaction versus self, interaction versus both matched nulls, and contrast with the candidate null were **−2, −2, 0, −1** decisions. The rule required all four contrasts, both maps and ≥4/6 dockets in the expected direction. The observed two switches do not qualify the endpoint as a specific equality signal.

Changing the candidate value instead of the required line (secondary VALUE) gave 7/12 approvals for originally matching codes and 0/12 for mismatches. A donor differing only in the preceding advisory (RELAY) left the same decisions as cue-only; its candidate position shifts by one token, so this arm is descriptive only. The [first tokenizer preflight](data/preflight_amendment.json) stopped with **zero forwards**; this qualification preceded inference and did not relax the primary comparison. The historical dockets had stronger CONTEXT suppression (9→5/12) but not uniformly matched positions. They do not substitute for the fresh panel. Semantic gave mapped PASS in **1,344/1,344** clean and patched generations of this second experiment, leaving no room for further movement toward PASS.

**Claim boundary.** The rejection patch was sufficient to change mixed's decision on these initial approvals. The opposite patch plus this candidate endpoint was not sufficient to approve the mismatches tested. Neither finding identifies a unique or necessary computation; a decision that stays fixed need not mean the underlying state is unchanged. No proprietary internals, calibrated transfer, or general veto were demonstrated. The [tomography readiness criteria](../../docs/tomography_readiness.md) remain in force.

## Next move — proposed, not run or frozen

Keep GPT-2 mixed, L6, the cue intervention and the renderer fixed. Compare **last candidate token vs. the whole candidate-code span** on fresh, non-overlapping dockets and both answer maps. Use a required-line-only donor: the recipient and donor must have the identical candidate string, token IDs and absolute positions **at every copied token**. Define the span by the literal value, not the field label. A boundary-straddling token or failed alignment is an invalid input, not a failed rescue.

Before measuring, lock the texts, positions, scorer, seeds, inventories and decision rule. Include cue-only, candidate-only, self replacements and an equal-width, per-token norm-matched control for both spans. The proposed question is **incremental**: on the same mismatching recipients, does targeting the cue **and** the whole span yield more approvals than each of (1) the **cue alone**, (2) cue + final token and (3) cue + width-matched span null? Require positive paired differences against all three on each answer map and on at least four **common** dockets out of six. Require exact shams, stable natural controls and no unscorable arms. Report both directions of every paired change and the absolute approval counts.

If the cue alone already gives 12/12 approvals, the span cannot earn credit for them. If the last token and the span both recover 12/12, report that both recover the cases, not that the span is ineffective. A valid no-go closes only the search for a **span-specific increment above all three comparators on this panel**. A technical-control failure is inconclusive. The [decision-rule examples](next_design.py) exercise these distinctions on synthetic numbers only. No new layer search, Luna calls or model runs are part of this publication.

## What can be verified from this PR?

- The [synthetic texts](data/prompts.jsonl), [3,648 open-weight trial rows](data/trials.jsonl), and [96 already-recorded Luna responses](data/luna.jsonl) are public. The replay reads the rule, codes, advisory and response map from each prompt, checks trial inventory, parses the entire visible answer, and counts paired effects and both gates. **960 generations / 5,760 forwards** in the cue assay; **2,688 / 16,128** in the joint assay. Both used zero endpoint calls. The repeat comparisons are not independent dockets.
- [Context and local verification receipts](data/context.json) contain the earlier reference summaries and the local CPU replay attestations: 864 cue-assay interventions and 2,304 joint interventions (4,608 site replacements). The public symbol replay does **not** reproduce the tensors, the full earlier reference acquisition, or provider-side execution. It verifies visible text for 288 and 192 self replacements and the 96 historical clean + 96 cue-patch repeats. Model weights, activations, provider metadata and raw operational journals are not distributed.
- [Cue protocol](data/cue_protocol.json) · [joint protocol](data/joint_protocol.json) · [source SHA-256 inventory](data/source_hashes.json) · [public file digests](data/manifest.json). See the [data key](DATA.md) for row layouts and contrast definitions. Fingerprints identify the retained files; they are not signatures from the provider.

From the repository root, offline, with no dependencies:

```sh
python3 -B -S reports/advisory_interventions_20261104/replay.py
python3 -B -S -m unittest discover -s reports/advisory_interventions_20261104 -v
```
