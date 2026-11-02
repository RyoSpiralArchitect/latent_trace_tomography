# One reference matches Luna; weak observations alone do not select it

[日本語](README.ja.md) · Retrospective comparison, 2026-11-02.

The same Mistral-7B-Instruct-v0.3 checkpoint in native chat format matched archived
`gpt-6-luna` answers on 24/24 aligned and 12/12 conflict texts on panel B.
It then matched 18/18 aligned and 12/12 conflict texts on a second set of three
dockets (A). Both repetitions had to resolve to the same symbol. The 66 texts
derive from **six dockets**, not 66 independent participants. Both sets of target
answers were already known; no prospective endpoint test or internal intervention occurred.

| Primary registry on B | Exact aligned matches | After observing conflict | Conflict forecast using only aligned matches |
|---|---:|---|---|
| Original 4 small anchors | 2 | All four contradicted | 12 wrong singletons |
| All 9 small anchors | 5 | All nine contradicted | 12 wrong singletons |
| 12 including three larger checkpoints | 6 | 1 joint witness, 10 contradicted, 1 unresolved | Both A and B on all 12; zero singletons |

The advisory agrees with the written permit rule on weak prompts and is reversed
on conflict. A witness must be **one checkpoint** across all conditions.
Gemma-2-2b-it matched 6/24 and 6/12; SmolLM2-1.7B base was unscorable under
the frozen parser. Removing the chat wrapper from the same Mistral made all 36 B
conditions unscorable under the 16-token contract. Renderings are controls, not extra
models. Do not infer a size effect, capability failure, internal mechanism or a
calibrated out-of-registry detector. A full answer set is not predictive success.

## What the replay verifies

Run `python3 -B -S reports/scaled_reference_screen_20261102/replay.py` from the
repository root. The [public observations](data/observations.json) contain only
synthetic prompts, coded repeats (`A`, `B`, `?` for unparseable), and per-track
acquisition totals. The replay rebuilds the weak-only forecasts, every
per-reference comparison, conditional A selection and score from these records.
Counts and marker decisions were separately checked against private raw
responses and forward journals before export; the public replay sums receipt
counts but does not independently remeasure GPU forwards or recover raw strings.

New on Furnace: B 720 generations (576 primary + 144 raw-format diagnostics),
5,980 forwards; A 60 generations, 360 forwards. Total **780 / 6,340**, no new API
calls or training. The initial environment lacked tokenizer packages; adding
them in an isolated overlay enabled the larger models but caused the five new
small tracks to stop before their first forward. Only those five were run in
the original pinned environment; no completed answer was rerun.

[Frozen design](protocol.json) · [model revisions](registry.json) · [as-run scorer](common.py) ·
[measurement functions](acquisition_core.py) · [allowlisted exporter and private receipt pins](export_public.py).
The public measurement functions are extracted from the frozen private runner;
they are not a standalone redistributable model installation. We release no
weights, private host bootstrap, API logs, credentials, token IDs or timings.
