from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import FormatChecker
from jsonschema.validators import validator_for

from latent_trace_tomography.anchor_intake import validate_anchor_base_model_intake
from latent_trace_tomography.dependency_registry import DependencyRegistryError


ROOT = Path(__file__).resolve().parents[1]
OPERATION_ROOT = ROOT / "operations" / "oss1_registry_authoring_v2"
INTAKE = OPERATION_ROOT / "base_model_intake.json"
SCHEMA = OPERATION_ROOT / "schemas" / "base_model_intake.schema.json"


class AnchorIntakeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.intake = json.loads(INTAKE.read_text(encoding="utf-8"))

    def test_real_metadata_intake_closes_without_model_calls(self) -> None:
        result = validate_anchor_base_model_intake(self.intake)
        self.assertTrue(result["ok"])
        self.assertEqual(result["base_model_count"], 3)
        self.assertEqual(result["tokenizer_preflight_pass_count"], 3)
        self.assertEqual(result["weight_files_downloaded"], 0)
        self.assertEqual(result["model_loads"], 0)
        self.assertFalse(result["model_calls_authorized"])

    def test_json_schema_accepts_the_intake(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        validator_cls = validator_for(schema)
        validator_cls.check_schema(schema)
        validator_cls(schema, format_checker=FormatChecker()).validate(self.intake)

    def test_weight_download_or_model_call_fails_closed(self) -> None:
        drift = copy.deepcopy(self.intake)
        drift["retrieval_boundary"]["weight_files_downloaded"] = 1
        with self.assertRaisesRegex(DependencyRegistryError, "weight_files_downloaded"):
            validate_anchor_base_model_intake(drift)

    def test_retrospective_anchor_label_has_no_intake_surface(self) -> None:
        drift = copy.deepcopy(self.intake)
        drift["records"][0]["anchor_condition_id"] = "semantic_anchor"
        with self.assertRaisesRegex(DependencyRegistryError, "fields are not exact"):
            validate_anchor_base_model_intake(drift)

    def test_tokenizer_continuation_is_recomputed(self) -> None:
        drift = copy.deepcopy(self.intake)
        drift["records"][0]["tokenizer_bundle"]["preflight"]["a_token_ids"][-1] = drift["records"][
            0
        ]["tokenizer_bundle"]["preflight"]["b_token_ids"][-1]
        with self.assertRaisesRegex(DependencyRegistryError, "continuation preflight"):
            validate_anchor_base_model_intake(drift)

    def test_tokenizer_ids_match_schema_types_and_minimum_lengths(self) -> None:
        for field, value in (
            ("prefix_token_ids", "A"),
            ("prefix_token_ids", []),
            ("a_token_ids", [1, -1]),
            ("b_token_ids", [1, False]),
        ):
            with self.subTest(field=field, value=value):
                drift = copy.deepcopy(self.intake)
                drift["records"][0]["tokenizer_bundle"]["preflight"][field] = value
                with self.assertRaisesRegex(DependencyRegistryError, "token IDs"):
                    validate_anchor_base_model_intake(drift)

    def test_config_and_weight_paths_match_the_schema_constants(self) -> None:
        for section, value, message in (
            ("model_config", "other-config.json", "model config relative path"),
            ("weight_artifact", "other.safetensors", "weight artifact relative path"),
        ):
            with self.subTest(section=section):
                drift = copy.deepcopy(self.intake)
                drift["records"][0][section]["relative_path"] = value
                with self.assertRaisesRegex(DependencyRegistryError, message):
                    validate_anchor_base_model_intake(drift)


if __name__ == "__main__":
    unittest.main()
