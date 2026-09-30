from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jsonschema.validators import validator_for

from latent_trace_tomography.demo import run_synthetic_demo


REPO_ROOT = Path(__file__).resolve().parents[1]


def _validator(schema_name: str):
    schema = json.loads((REPO_ROOT / "schemas" / schema_name).read_text(encoding="utf-8"))
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    return validator_class(schema)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class EmittedSchemaTests(unittest.TestCase):
    def test_emitted_primary_records_validate_against_checked_in_schemas(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            run_synthetic_demo(
                output,
                seed=23,
                cases=8,
                samples=1,
                calibration_targets_per_regime=2,
                evaluation_targets_per_regime=1,
            )

            contracts = {
                "text_observation.schema.json": (
                    _jsonl(output / "observations.jsonl")
                    + _jsonl(output / "heldout_challenge_observations.jsonl")
                ),
                "calibration_label.schema.json": (
                    _jsonl(output / "calibration_labels.jsonl")
                    + _jsonl(output / "sealed_evaluation_key.jsonl")
                ),
                "audit_prediction.schema.json": _jsonl(output / "audit_predictions.jsonl"),
                "run_manifest.schema.json": [
                    json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
                ],
            }
            for schema_name, instances in contracts.items():
                validator = _validator(schema_name)
                self.assertTrue(instances, schema_name)
                for instance in instances:
                    validator.validate(instance)


if __name__ == "__main__":
    unittest.main()
