# Output-contract scoring and model-free rehearsal

English | [日本語](README.ja.md) · [Frozen design](../output_contract_probe_v1/README.md)

This companion implements the scoring contract for the frozen 96-slot design. It does not modify the prompts, scoring key, parser or authorization. There is no API client. The 96-slot panel has not been run against an endpoint.

## How to read a score

Suppose a prompt requires `FINAL: A` and the correct symbol is A:

| Visible output | Answer correct | Requested format | Joint success |
|---|---|---|---|
| `FINAL: A` | yes | yes | yes |
| `A` | yes | no | no |
| `FINAL: B` | no | yes | no |
| `A because …` | no | no | no |

In a bare-symbol request the format rule reverses: A or B alone is compliant. The frozen parent parser removes outer whitespace only. Empty or otherwise unresolved answers remain in all denominators.

[The scorer](score.py) accepts exactly one `query_id` and one `output_text` for each of the 96 slots in a saved JSONL file. Order does not matter; missing, duplicate, unplanned slots and extra fields are errors. It verifies the frozen design before joining responses to the key. A complete score does not attest where the text came from.

The two primary contrasts are **bare minus marker joint-failure rates**, one per task: 32 slots per format for full tasks, 16 for mapping controls. Negative means fewer joint failures for bare requests on this panel. Separate tables show answer errors, format errors, unresolved counts, paired outcomes within the same parent case and repeat, and disagreements between repetitions (parsed answer/format category, not raw bytes). These are descriptive counts over two reused contents, not 96 independent measurements.

Under the frozen decision rule, fewer joint failures count as a candidate interface improvement only if normalized-answer errors did not increase. A zero, mixed or worse result is reported as observed; it does not trigger prompt search.

## Try it without a model

From the repository root with Python 3.10+:

```sh
probe=successors/oss_reliance_regime_v0/output_contract_scoring_v1
run_dir=$(mktemp -d)
python3 -S "$probe/rehearse.py" --scenario mixed --out "$run_dir/mixed"
python3 -S "$probe/score.py" "$run_dir/mixed/observations.jsonl"
python3 -S -m unittest discover -s "$probe" -v
```

[The rehearsal](rehearse.py) uses scripted replies drawn from the answer key to exercise the scorer; they are **not** model observations. Each run writes to a new directory only:

- `perfect`: all 96 synthetic replies meet both criteria.
- `mixed`: 72/96 are correct, 60/96 meet the requested format, and 48/96 meet both. Twelve are unresolved. The two aggregate primary contrasts are both zero despite different paired outcomes.
- `stopped`: simulates an unknown outcome on attempt 12, preserves the first 11 rows and a receipt, and exits with status 2. It writes no score and never retries or resumes.

The receipt binds the observations, optional score, scorer, rehearsal and frozen design manifest by hash. The saved mock score is explicitly labeled synthetic. No keys, provider connection or Furnace are needed. Unexpected process or I/O failures may leave an unfinished directory with no terminal receipt; that is not a completed run.

## What remains before live work

A future run requires an independently authorized execution plan, fresh availability/pricing, and pins for the approved scorer and runner. The existing cap stays 96 attempts / USD 0.50, without retries, substitution or automatic resume. This package neither grants permission nor validates causal reliance, mechanism transfer, or endpoint reliability.
