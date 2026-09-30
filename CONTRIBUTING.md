# Contributing

Latent Trace Tomography is an evidence-first research repository. A change is
complete only when its scientific claim, artifact identity, and failure surface
remain inspectable.

## Before implementation

1. Name the estimand and its operational ground truth.
2. Separate observation projections from heldout challenge projections.
3. Specify positive anchors, negative anchors, matched nulls, and abstention.
4. Freeze model, tokenizer, task, case, projection, split, decoding, and feature
   identities before outcome exposure.
5. Run structural preflight lint with zero model/API calls, then lock the plan
   prediction artifact before exposing evaluation labels or challenge outputs.

The current preflight command checks contract shape, phase order, frozen asset
hashes, and executable design invariants. A successful design check is not a
live execution authorization: concrete construction/discovery prerequisites,
registry evidence, model availability, provider capabilities, and budget
feasibility still need to be closed at the corresponding execution boundary.

Do not call a protocol preregistered if outcomes informed its thresholds or
factor grid. The current synthetic protocol is intentionally marked
retrospective.

## Evidence rules

- Raw responses are append-only.
- Reviewed run directories are never overwritten.
- Use full SHA-256 digests for protocol, prompt, response, split, and manifest
  identities.
- Corrections create a successor artifact with parent hash, reason, and
  superseded IDs.
- Keep parse failures, abstentions, API errors, and every planned case in
  reports.
- Keep credentials outside configs and artifacts.
- Apply the authorization, retention, redaction, and disclosure requirements in
  RESPONSIBLE_USE.md before adding any live target.

## Feature boundary

The primary detector may use prompt/output text and pairing metadata only.
Provider/model identity, latency, usage, request IDs, system fingerprints,
logprobs, and internal observations are provenance or control variables, not
primary features.

OSS internal intervention data belongs behind InternalObserver and enters only
through a frozen causal profile or calibration label. Never make an internal
observer available to a proprietary backend abstraction.

## Testing

~~~bash
make test
make preflight
make smoke
~~~

New live backends require mocked payload/extraction tests, retry and resume
tests, transmitted-versus-requested parameter capture, provider capability
snapshots, and a zero-call preflight test.

Ruff and its lint rule set are pinned in `pyproject.toml` to keep checks
reproducible across machines. Tool upgrades require a separate review; never
reformat a content-addressed source file merely to satisfy changed defaults.

## Claim language

Prefer “consistent with a calibrated equivalence class” and “predicts heldout
failure behavior.” Do not use “recovered thought,” “read the model's mind,” or
“proved the internal circuit” for output-only evidence.

## License

Contributions to the project code and documentation are provided under
`AGPL-3.0-only` (GNU Affero General Public License, version 3 only).
Do not add third-party material without preserving its provenance and checking
that its license permits the intended redistribution.
