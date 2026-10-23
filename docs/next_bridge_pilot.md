# Next bridge pilot: test usefulness before adding complexity

English | [日本語](next_bridge_pilot.ja.md)

Status: proposal after the 2026-10-23 checkpoint, **not a frozen protocol or live
authorization**. This document starts no inference, training, or causal measurement.

## What the checkpoint changed

V1 abstained on all 32 API challenge slots. Its post-hoc diagnostic exposed a
format mismatch and three indistinguishable weak-output references with different
challenge behavior. V2 separates content and format and retains all three
references. On the already-revealed development data, 18/32 challenge slots remain
ambiguous within that reference set.

The next question is therefore not “did we recover the mechanism?” It is:

> On fresh content, does matching weak answer traces produce a useful, honestly
> limited reference set before target challenge outputs are opened?

## One small implementation PR, then a separately authorized live pilot

1. **Build an offline prospective coordinator.** Reuse v2 without changing its
   parser or exact-match rule. Save rules, implementation, concrete inventories,
   reference evidence, target weak outputs, and the resulting reference report
   in a non-overwriting commitment artifact. A separate evaluator receives target
   challenges only after that commitment. Keep the existing v2 report's
   development-only label; any prospective evidence tier belongs to a separately
   versioned coordinator receipt, not a relabeled development report.
2. **Rehearse the full sequence with fixtures.** Test interruption, unknown request
   outcomes, output-path collisions, stale hashes, missing slots, and attempts to
   open target challenges early. Bind every completed or attempted request to the
   budget ledger. No implicit retry, restart credit, or model fallback.
3. **Review a concrete new run manifest.** Use fresh content/seeds, pin the endpoint
   and runtime, confirm retained model availability, and refresh price/capability
   assumptions. Obtain live authorization only after the mock path passes.
4. **Run once, lock, reveal, score.** Keep all nine retained OSS references and all
   planned API outcomes, including unresolved text, exclusions, errors, and
   abstention. A stopped or incomplete run remains visible and is not silently
   replaced.

Do not introduce new models, retraining, site search, or a broader weak-probe
search into this pilot. Those would make the source of any change harder to isolate.

## Proposed scale, not a granted budget

Use the same small factorial structure: 2 fresh contents, 8 aligned weak cases ×
5 weak projections × 2 repetitions = 80 API weak requests; 8 conflict cases ×
2 challenge renderings × 2 repetitions = 32 API challenge requests. That is 112
API requests and 1,008 OSS completions across nine references.

If the old decoding limits are retained, the proposed OSS cap is 16,128 physical
forwards / 600 seconds. The proposed API money cap remains $0.50, but the reservation
must be recomputed from verified prices and request limits before authorization;
the old $0.372736 estimate is not a current quote. Stop before execution if the
new reservation exceeds the cap. Preserve the API/OSS runtime differences in the
report rather than presenting an equal-runtime comparison.

New content must have zero exact overlap with retained training and development
prompts. Passing that check does not establish distribution independence. Two
repetitions do not estimate a reliable output distribution, and nine descendants
do not become nine independent samples.

## Readouts to commit before exposure

Keep this an engineering pilot with descriptive counts, not a significance claim.
Freeze the definitions and concrete evaluator bytes before new outputs. The minimal
readout is:

| Readout | Required interpretation |
|---|---|
| Content resolution and format compliance | Separate denominators; bare A/B is not format success |
| Reference support | Every retained instance and exclusion reason; declared lineage counts, not an independence certificate |
| Set availability | Nonempty reference sets / all planned challenge slots; not the same as correct prediction |
| Set containment | Target canonical answer, including `unresolved`, belongs to the committed set; report counts and denominators |
| Set size and singleton performance | `{A, B, unresolved}` trivially contains every outcome and is uninformative; retain misses and unresolved singleton states |
| Unconditional reference baseline | Build the same per-slot sets from all nine references; compare containment and set size without choosing a baseline after reveal |

Report singleton-resolved prediction count over all planned slots and correctness
within that subset. Do not count an `unresolved` singleton as a resolved answer.
Also report content and format failures by challenge class and repetition. Do not
convert reference frequencies into calibrated probabilities or intervals.

Missing slots or a broken commitment chain make prospective scoring incomplete;
they are not scientific abstention. Empty support or unresolved target weak
content causes the declared scientific abstention. Keep these failure categories
separate. Any partial descriptive output must carry its actual denominators and
must not be presented as the planned complete pilot.

## How the next decision follows from the result

- If v2 mostly fixes format handling but sets remain broad, keep that as a useful
  boundary result. Develop more informative weak projections on OSS development
  data, then freeze a separate successor and test on new target data. Do not use
  these target challenges to tune and then validate the same successor.
- If conditional sets narrow relative to the unconditional baseline while retaining
  observed containment, repeat on fresh independently held-out material before
  claiming stable predictive value. A single pilot does not establish general transfer.
- If answers fall outside the sets, report the failures. Do not expand support or
  normalize additional output forms after reveal and call that primary success.
- If support is empty, investigate the domain mismatch offline; do not automatically
  buy more calls or lower the exact-match threshold.

## Separate mechanistic track

The selected semantic carrier's targeted/null zero scores remain a calibration
gap. An independently scoped carrier/intervention diagnostic must establish a
usable causal reference before attaching `semantic reliance` to API observations.
Construction conditions alone cannot supply that label. This track is separate
from the behavior pilot; improving one does not establish the other.

The practical audit path is: behavior drift first, failure-surface prediction
next, OSS-calibrated attribution only after its own evidence closes. The current
repository is a research instrument, not a production monitoring guarantee.
