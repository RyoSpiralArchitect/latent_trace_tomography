# Output-contract probe v1 — design only

English | [日本語](README.ja.md) · [Definition](design.json) · [Manifest](fixtures/manifest.json)

The [GPT-6 Luna checkpoint](../../../reports/gpt6luna_answer_mapping_20261031/README.md)
had 112/112 correct normalized answers, 86/112 requested markers, and 8/56 repeat
pairs with format variation. This follow-up asks whether explicitly requesting
a bare symbol changes **joint answer correctness and instruction-format compliance**.
It is a post-result design, not a pre-existing mechanism hypothesis.

## Fixed panel

| Task | Factors | Unique prompts | Two repetitions |
|---|---|---:|---:|
| Full task | 2 content × 2 decision × 2 cue × 2 map × 2 requested format | 32 | 64 |
| Mapping-only | 2 content × 2 supplied decision × 2 map × 2 requested format | 16 | 32 |
| Total | | 48 | 96 |

The two requested formats are exact `FINAL: A/B` and bare `A/B`. Both standard
and inverted answer maps are retained. Full-task layout is baseline only;
direct PASS/FAIL and reorder are excluded to keep this probe bounded.

All matching parent cases are included, irrespective of their observed output.
Marker prompts retain the parent bytes. Bare prompts change only the two map
lines and the final output instruction. Evidence, docket, cue, mapping and
expected answer remain unchanged. The same two content instances are deliberately
reused for pairing: this is not an independent new content sample. Repetitions
have identical prompts; ordering is fixed by the generator's hash rule.

The retained definition, 96 request bytes and scoring-key bytes are unchanged
from the local post-result design. Only the generator has been re-expressed
without private runtime imports. Its public manifest pins that new source and
the unchanged parent generator. IDs encode design factors and are audit joins,
not model input: any future transport sends `prompt_text` only.

## Scoring contract, not yet an implemented live scorer

- Normalized answer: the parent's parser accepts exact `FINAL: A/B` or bare A/B,
  stripping outer whitespace only. Anything else is unresolved.
- Format compliance: after stripping outer whitespace, marker requests require exactly `FINAL: A` or `FINAL: B`;
  bare requests require exactly A or B. Wrong but well-formed symbols still
  comply with the format.
- Joint success: normalized answer correct **and** requested format satisfied.
  Unresolved responses fail both checks and remain in denominators.

The two primary descriptive contrasts are **bare joint-failure rate minus marker
joint-failure rate**, separately for full tasks (32 slots per format) and
mapping-only (16 per format). Secondary readouts keep answer errors, format errors,
unresolved counts, paired joint outcomes and repeat differences separate.
Pair formats within parent case and repetition; do not treat 96 dependent slots
as independent subjects or report significance from them.

Fewer observed joint failures without more observed normalized-answer errors
would be only a candidate interface improvement on this panel. Null, mixed or
worse results remain results; no automatic prompt search or panel expansion.
Prompt changes can change computation, so this is not surgical intervention on
an internal stage. Structured-output constraints and parser repair are outside
scope, as are model comparisons and causal attribution.

## Launch boundary and next PR

The candidate remains `gpt-6-luna`, temperature 0, reasoning effort none, 32 output
tokens and no tools. The ceiling is 96 generation attempts and USD 0.50, with no
retry, substitution, automatic resume or Furnace work. Availability and pricing
must be checked again before reserving a future run.

`live_execution_authorized` is **false**, and status is
`design_only_not_execution_ready`. This package has no API client or live scorer.
The next implementation PR should add the specified three readouts and boundary
tests, then exercise a model-free rehearsal. Only after that should a separately
authorized, pinned execution plan enable this exact panel. Publishing this design
does not authorize any inference, prompt tuning or OSS work.

From the repository root, Python 3.10+:

```sh
python3 -S successors/oss_reliance_regime_v0/output_contract_probe_v1/design.py verify
python3 -S -m unittest discover -s successors/oss_reliance_regime_v0/output_contract_probe_v1 -v
```

`prepare --out NEW_DIRECTORY` reproduces request/scoring artifacts without
overwriting. All commands are call-free. This is an interface-diagnostic branch;
the unresolved OSS causal-calibration bridge remains a separate research task.
