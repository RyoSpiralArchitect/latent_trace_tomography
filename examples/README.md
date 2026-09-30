# Reference synthetic smoke

reference_seed7_summary.json records the small retrospective bootstrap shown in
the main README. It is a regression example, not evidence about a natural
language model and not a preregistered result.

Reproduce the complete evidence bundle with:

~~~bash
ltt synthetic-demo \
  --out-dir artifacts/synthetic_projection_orbit_v1_seed7 \
  --seed 7
~~~

The generated directory contains a contract-lint result, source/config/split
identity, observation-only plan evidence, locked predictions, phase events, an
evaluation key opened after that lock, subsequently collected challenges,
null-control evidence, and full SHA-256 manifests. Raw generated evidence is
intentionally not committed here.

The run identity includes the Python runtime and derived case/projection/split
hashes, so a different supported Python version may produce a different run ID
even when the reported regression metrics match this reference.
