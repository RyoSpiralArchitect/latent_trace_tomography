# Output-only bridge v2: content, format, and reference sets

This additive implementation follows the [v1 research checkpoint](../../../reports/output_only_bridge_20261023/README.md).
It does not edit the v1 parser, saved primary abstention, public data, or frozen OSS-1 contract.
There is no model loader, provider client, automatic retry, or live-execution command here.

## Two changes

1. Separate **answer content** from **format compliance**. After outer whitespace
   is stripped, exact `FINAL: A`/`FINAL: B` and bare `A`/`B` supply a content symbol.
   Only the first form is format-compliant. All other output—including empty text,
   multiple markers, explanations, lowercase symbols, and `FINAL: AB`—is unresolved.
   Raw observations remain untouched. A bare symbol is not silently counted as
   successful format compliance.
2. Return **all case-aligned matching references**, not one regime label. Matching
   compares every canonical weak answer at the same case/projection/replicate slot.
   Equal aggregate marginals alone are insufficient. Format counts, model identity,
   and cluster labels do not influence the matches. Cluster labels are declarations
   used only for provenance/accounting, not proof of independence.

Unresolved target content causes abstention. Unresolved references remain in the
reported cohort with an exclusion reason. Complete but nonmatching references are
also reported. An empty support set causes abstention. A single match is still not
evidence of a unique mechanism.

For each challenge slot, the output includes the finite set of observed answers
among matching references, including unresolved answers and separate format labels.
Ambiguity is preserved. These sets are **not calibrated probabilities, confidence
intervals, bounds on API behavior, or guaranteed future coverage**.

## Interface

`latent_trace_tomography.reference_bridge.build_reference_report(bundle)` accepts
exactly these bundle fields:

- `schema_version`: `ltt_output_bridge_v2_inputs_v1`
- `weak_inventory`, `challenge_inventory`: lists of four-field slots
  (`case_id`, `projection_id`, `replicate_id`, `prompt_text`)
- `target_weak`: six-field observations (the slot fields plus `target_id`, `output_text`)
- `reference_weak`, `reference_challenge`: reference ID -> six-field observation list
- `reference_clusters`: reference ID -> declared cluster ID

Inventories must be complete, duplicates are rejected, and prompts must match
exactly. Target challenge outputs, logits, usage, model metadata, and unknown fields
are rejected by the estimator boundary. Input order does not affect the result.
Every input surface, the observation rules, and the implementation bytes are
content-addressed in the report. Repetitions are not counted
as independent subjects. These checks establish data integrity, not worker isolation.

The additive CLI reads one offline bundle and exclusively creates a new output file:

```sh
PYTHONPATH=src python3 -m latent_trace_tomography.reference_bridge \
  --bundle /path/to/input_bundle.json --out /path/to/new_report.json
```

## Development-only demonstration

```sh
python3 -S successors/oss_reliance_regime_v0/output_only_bridge_v2/development_demo.py \
  --out /path/to/new_development_report.json
```

The demonstration uses already-revealed v1 data. It passes only API weak outputs
to the estimator, but the dataset and the design choices are no longer blind.
Expected development matches are `target-01`, `target-02`, and `target-08`; API weak
format counts remain 68 exact markers and 12 bare symbols. This is an implementation
regression, **not prospective transfer validation**. Every v2 report is labeled
`development_only_not_prospective_validation`; it never upgrades the historical v1
abstention or claims a live lock was established by this offline tool.

Before a new live experiment: select fresh content/seed and budget, save the v2 rules
and implementation identity, bind the concrete inventories, and persist the report
before opening target challenge outputs. Keep the separate causal-calibration gap
visible. This PR neither authorizes nor starts that experiment.
