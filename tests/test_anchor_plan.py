from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import FormatChecker
from jsonschema.validators import validator_for

from latent_trace_tomography.anchor_plan import validate_anchor_construction_plan
from latent_trace_tomography.dependency_registry import (
    DependencyRegistryError,
    canonical_artifact_sha256,
)


ROOT = Path(__file__).resolve().parents[1]
PLAN = (
    ROOT
    / "successors"
    / "oss_reliance_regime_v0"
    / "controlled_anchor_phantom_v1"
    / "anchor_construction_plan.json"
)
INTAKE = ROOT / "operations" / "oss1_registry_authoring_v2" / "base_model_intake.json"
GENERATOR_SOURCE = ROOT / "src" / "latent_trace_tomography" / "anchor_training.py"
PLAN_SCHEMA = PLAN.with_name("anchor_construction_plan.schema.json")


class AnchorPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = json.loads(PLAN.read_text(encoding="utf-8"))
        self.intake = json.loads(INTAKE.read_text(encoding="utf-8"))

    def test_frozen_plan_has_nine_balanced_runs_and_no_authority(self) -> None:
        result = validate_anchor_construction_plan(
            self.plan,
            base_model_intake=self.intake,
            base_model_intake_path=INTAKE,
            generator_source_path=GENERATOR_SOURCE,
        )
        self.assertEqual(result["run_count"], 9)
        self.assertEqual(result["dependency_cluster_count"], 3)
        self.assertEqual(result["training_forward_call_budget"], 9216)
        self.assertFalse(result["training_started"])
        self.assertEqual(result["measurement_calls"], 0)
        self.assertFalse(result["model_calls_authorized"])

    def test_anchor_reassignment_fails_closed(self) -> None:
        drift = copy.deepcopy(self.plan)
        drift["runs"][0]["anchor_condition_id"] = "semantic_anchor"
        with self.assertRaisesRegex(DependencyRegistryError, "run inventory"):
            validate_anchor_construction_plan(
                drift,
                base_model_intake=self.intake,
                base_model_intake_path=INTAKE,
                generator_source_path=GENERATOR_SOURCE,
            )

    def test_outcome_selection_and_validation_calls_are_forbidden(self) -> None:
        drift = copy.deepcopy(self.plan)
        drift["global_training_contract"]["early_stopping"] = True
        with self.assertRaisesRegex(DependencyRegistryError, "training contract"):
            validate_anchor_construction_plan(
                drift,
                base_model_intake=self.intake,
                base_model_intake_path=INTAKE,
                generator_source_path=GENERATOR_SOURCE,
            )

        calls = copy.deepcopy(self.plan)
        calls["query_budget"]["validation_forward_call_count"] = 1
        with self.assertRaisesRegex(DependencyRegistryError, "query budget"):
            validate_anchor_construction_plan(
                calls,
                base_model_intake=self.intake,
                base_model_intake_path=INTAKE,
                generator_source_path=GENERATOR_SOURCE,
            )

    def test_plan_cannot_authorize_training(self) -> None:
        drift = copy.deepcopy(self.plan)
        drift["authorization_effect"] = "anchor_training"
        with self.assertRaisesRegex(DependencyRegistryError, "does not authorize"):
            validate_anchor_construction_plan(
                drift,
                base_model_intake=self.intake,
                base_model_intake_path=INTAKE,
                generator_source_path=GENERATOR_SOURCE,
            )

    def test_plan_schema_is_valid_and_accepts_the_frozen_plan(self) -> None:
        schema = json.loads(PLAN_SCHEMA.read_text(encoding="utf-8"))
        validator_cls = validator_for(schema)
        validator_cls.check_schema(schema)
        validator_cls(schema, format_checker=FormatChecker()).validate(self.plan)

    def test_plan_is_bound_to_actual_intake_and_generator_bytes(self) -> None:
        intake_drift = copy.deepcopy(self.intake)
        intake_drift["limitations"].append("synthetic mutation")
        intake_drift["limitations"].sort()
        intake_drift["intake_body_sha256"] = canonical_artifact_sha256(
            {key: value for key, value in intake_drift.items() if key != "intake_body_sha256"}
        )
        with self.assertRaisesRegex(DependencyRegistryError, "body hash drifted"):
            validate_anchor_construction_plan(
                self.plan,
                base_model_intake=intake_drift,
                base_model_intake_path=INTAKE,
                generator_source_path=GENERATOR_SOURCE,
            )


if __name__ == "__main__":
    unittest.main()
