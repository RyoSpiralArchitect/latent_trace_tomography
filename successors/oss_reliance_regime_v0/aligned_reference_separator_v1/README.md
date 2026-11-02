# An aligned placement change separates four of five alternative references

[日本語](README.ja.md) · Executed 2026-11-03 JST. [Parent reference screen](../../../reports/scaled_reference_screen_20261102/README.md).

**Decision: abstain.** Moving a truthful advisory from above the case details to below them produced five different response signatures among six checkpoints. One pair remained identical: Mistral-7B-Instruct-v0.3 and the task-trained GPT-2 mixed anchor. These two had given opposite answers on the previous conflict panel. The new study did not collect any conflicts or any new Luna answers.

The [reference-only protocol](protocol.json), [generator and gate](study.py), acquisition and cell inventories were [committed before inference](https://github.com/RyoSpiralArchitect/latent_trace_tomography/commit/d7e4473). The new development panel used three synthetic dockets, exact versus unequal codes, both answer maps and two runs per text. The reference values always agree with the written rule. Each variant has 12 distinct prompts; these are repeated measures on three dockets, not independent units. We changed only the heading or only the position; the baseline reused the original layout on these new dockets.

| Aligned layout | Distinct 12-symbol signatures among the six | Small references differing somewhere from Mistral |
|---|---:|---:|
| Original baseline | 1 | 0/5 |
| Rename “Advisory ribbon (not law)” to “Filing note (not law)” | 2 | 1/5 |
| Move the advisory below the submitted code | 5 | 4/5 |

All six matched the written rule in 12/12 baseline cells; all 432 outputs parsed and repeats were stable. Mistral and GPT-2 mixed each returned the rule's symbol in 12/12 cells under **each** layout. After the position change, the other four checkpoints differed from Mistral on 5, 3, 6 and 3 of 12 cells (Pythia mixed, Pythia surface, SmolLM2 mixed and SmolLM2 surface). Only Pythia mixed and SmolLM2 mixed differed under both answer maps. Under the heading change only Pythia mixed differed: two dockets, one map.

Passing required stable outputs and a contradiction with **each** of the five alternatives on at least two dockets spanning both maps. Neither candidate passed. Even disregarding that balance rule would not remove the exactly matching GPT-2 mixed anchor. The conditional confirmation panel, reference conflict measurements, conditional forecast table and endpoint calls were therefore skipped. The five signatures are descriptive, not evidence that layout predicts how Luna handles conflict. No earlier forecast or exclusion was revised.

## Replay and boundaries

From this directory run:

```sh
python3 -B -S checkpoint.py replay
python3 -B -S -m unittest -q
```

The [public checkpoint](checkpoint.json) contains the normalized response at each planned repetition and the corresponding per-track counts. Replay regenerates prompts in order, verifies the [frozen method and panel hashes](freeze.json), reconstructs signatures and checks that the result reproduces the retained gate digest. The exporter separately checks private per-response and forward journals. Six checkpoints × 72 completions = **432 new OSS generations; 2,592 measured forwards; zero API calls, downloads of model weights or training runs**. The native Mistral chat renderer and the five small-anchor runtimes are unchanged from the parent; reconstruction requires retained assets and is not part of public replay.

The narrowed open question is the remaining **Mistral / GPT-2 mixed** pair. A new study could change the representation of the advisory value (e.g. a neutral code with an explicit legend) while keeping it truthful and both answer maps balanced. That would be a new probe on untouched dockets, not a replacement for this failed gate; it has not been run. It also introduces a decoding demand, so its matched control should use the same legend without relying on it.
