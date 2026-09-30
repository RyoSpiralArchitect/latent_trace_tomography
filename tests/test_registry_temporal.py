from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import FormatChecker
from jsonschema.exceptions import ValidationError
from jsonschema.validators import validator_for

from latent_trace_tomography.dependency_registry import (
    DependencyRegistryError,
    canonical_artifact_sha256,
)
from latent_trace_tomography.registry_temporal import (
    POLICY_ID,
    RECEIPT_TYPE,
    SCHEMA_VERSION,
    STATUS,
    validate_dependency_cluster_registry_v2,
)

try:
    from test_dependency_registry import _registry
except ModuleNotFoundError:
    from tests.test_dependency_registry import _registry


ROOT = Path(__file__).resolve().parents[1]
LINEAGE_SCHEMA = (
    ROOT
    / "operations"
    / "oss1_registry_authoring_v2"
    / "schemas"
    / "postfreeze_anchor_lineage_receipt.schema.json"
)


def _close(value: dict, field: str) -> None:
    value[field] = canonical_artifact_sha256(
        {key: item for key, item in value.items() if key != field}
    )


def _postfreeze_registry() -> dict:
    registry = _registry()
    for index, candidate in enumerate(registry["candidate_model_units"]):
        candidate["checkpoint_provenance"]["created_at"] = f"2026-07-18T00:{index:02d}:30Z"
        base = next(
            row
            for row in registry["authorization_projection"]["model_registry"]
            if row["model_unit_id"] == candidate["model_unit_id"]
        )["shared_base_artifact_sha256"]
        candidate["checkpoint_provenance"]["parent_checkpoint_artifact_sha256"] = [base]
    for exposure in registry["evaluation_exposure_assessments"]:
        exposure["checkpoint_precedes_design_freeze"] = False
    registry["evidence_cutoff_at"] = "2026-07-18T01:00:00Z"
    registry["created_at"] = "2026-07-18T01:05:00Z"
    for source in registry["source_records"]:
        source["recorded_at"] = "2026-07-18T00:50:00Z"
        _close(source, "source_record_sha256")
    source_hash_by_id = {
        source["source_record_id"]: source["source_record_sha256"]
        for source in registry["source_records"]
    }
    for candidate in registry["candidate_model_units"]:
        model_id = candidate["model_unit_id"]
        candidate["checkpoint_provenance"]["source_record_sha256"] = source_hash_by_id[
            f"checkpoint:{model_id}"
        ]
        candidate["training_randomness"]["source_record_sha256"] = source_hash_by_id[
            f"rng:{model_id}"
        ]
        candidate["training_data_stages"][0]["source_record_sha256"] = source_hash_by_id[
            f"training-data:{model_id}"
        ]
        candidate["task_provenance"]["source_record_sha256"] = source_hash_by_id[f"task:{model_id}"]
    shared = {
        "ancestry": source_hash_by_id["shared-ancestry"],
        "exposure": source_hash_by_id["shared-exposure"],
        "overlap": source_hash_by_id["shared-overlap"],
        "pair_rng": source_hash_by_id["shared-pair-rng"],
        "task": source_hash_by_id["shared-task-relation"],
    }
    for pair in registry["pairwise_relatedness"]:
        pair["learned_state"]["evidence_record_sha256"] = [shared["ancestry"]]
        pair["training_randomness"]["evidence_record_sha256"] = shared["pair_rng"]
        pair["training_data"]["evidence_record_sha256"] = shared["overlap"]
        pair["task_relation"]["evidence_record_sha256"] = shared["task"]
    for exposure in registry["evaluation_exposure_assessments"]:
        exposure["evidence_record_sha256"] = shared["exposure"]
    for binding in registry["binding_map"]:
        source_id = binding["assertion_id"].removeprefix("classify:")
        binding["source_record_sha256"] = source_hash_by_id[source_id]
    _close(registry, "registry_body_sha256")
    return registry


def _receipt(registry: dict) -> dict:
    projected = {
        row["model_unit_id"]: row for row in registry["authorization_projection"]["model_registry"]
    }
    records = []
    for index, candidate in enumerate(registry["candidate_model_units"]):
        model_id = candidate["model_unit_id"]
        model = projected[model_id]
        record = {
            "model_unit_id": model_id,
            "training_run_id": model["independent_training_run_id"],
            "anchor_condition_id": model["anchor_condition_id"],
            "attempt_index": 1,
            "completion_status": "complete_fixed_steps",
            "selection_policy": "retain_first_complete_attempt_no_outcome_selection",
            "base_model_record_sha256": canonical_artifact_sha256(
                {"base": model["shared_base_artifact_sha256"]}
            ),
            "base_checkpoint_artifact_sha256": model["shared_base_artifact_sha256"],
            "base_tokenizer_artifact_sha256": model["tokenizer_artifact_sha256"],
            "base_checkpoint_created_at": "2025-01-01T00:00:00Z",
            "descendant_checkpoint_manifest_sha256": candidate["checkpoint_provenance"][
                "checkpoint_manifest_sha256"
            ],
            "descendant_model_artifact_sha256": model["model_artifact_sha256"],
            "descendant_configuration_sha256": model["configuration_sha256"],
            "descendant_tokenizer_artifact_sha256": model["tokenizer_artifact_sha256"],
            "anchor_assignment_manifest_sha256": model["anchor_provenance"][
                "anchor_assignment_manifest_sha256"
            ],
            "anchor_assignment_committed_at": "2026-07-17T12:00:00Z",
            "training_recipe_sha256": model["anchor_provenance"]["training_recipe_sha256"],
            "training_data_sha256": model["anchor_provenance"]["training_data_sha256"],
            "derived_target_inventory_sha256": canonical_artifact_sha256(
                {"target-inventory": model_id}
            ),
            "training_started_at": f"2026-07-17T13:{index:02d}:00Z",
            "training_completed_at": f"2026-07-18T00:{index:02d}:00Z",
            "descendant_checkpoint_created_at": candidate["checkpoint_provenance"]["created_at"],
            "fixed_optimizer_step_count": 100,
            "training_forward_call_count": 100,
            "training_backward_call_count": 100,
            "outcome_access_before_checkpoint": False,
            "exact_live_prompt_exposed_to_training_runtime": False,
            "frozen_evaluation_generator_imported_by_training_runtime": False,
            "frozen_evaluation_template_exposed_to_training_runtime": False,
        }
        _close(record, "record_sha256")
        records.append(record)
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "receipt_type": RECEIPT_TYPE,
        "status": STATUS,
        "policy_id": POLICY_ID,
        "receipt_id": "postfreeze-lineage-fixture-a",
        "created_at": "2026-07-18T01:06:00Z",
        "registry_id": registry["registry_id"],
        "registry_body_sha256": registry["registry_body_sha256"],
        "base_model_intake_body_sha256": canonical_artifact_sha256({"intake": "fixture-body"}),
        "base_model_intake_file_sha256": canonical_artifact_sha256({"intake": "fixture-file"}),
        "anchor_construction_plan_body_sha256": canonical_artifact_sha256({"plan": "fixture-body"}),
        "anchor_construction_plan_file_sha256": canonical_artifact_sha256({"plan": "fixture-file"}),
        "records": records,
        "training_model_calls_disclosed": True,
        "evaluation_model_calls_before_registry": 0,
        "outcomes_exposed_before_registry": False,
        "authorization_effect": "none",
    }
    _close(receipt, "receipt_sha256")
    return receipt


class RegistryTemporalTests(unittest.TestCase):
    def test_controlled_postfreeze_descendants_keep_all_v1_checks(self) -> None:
        registry = _postfreeze_registry()
        result = validate_dependency_cluster_registry_v2(registry, _receipt(registry))
        self.assertTrue(result["ok"])
        self.assertEqual(result["postfreeze_model_unit_count"], 9)
        self.assertEqual(result["evaluation_model_calls_before_registry"], 0)
        self.assertFalse(result["model_calls_authorized"])

    def test_v1_still_rejects_postfreeze_registry(self) -> None:
        from latent_trace_tomography.dependency_registry import (
            validate_dependency_cluster_registry,
        )

        with self.assertRaisesRegex(DependencyRegistryError, "precede"):
            validate_dependency_cluster_registry(_postfreeze_registry())

    def test_assignment_must_precede_training(self) -> None:
        registry = _postfreeze_registry()
        receipt = _receipt(registry)
        receipt["records"][0]["anchor_assignment_committed_at"] = receipt["records"][0][
            "training_started_at"
        ]
        _close(receipt["records"][0], "record_sha256")
        _close(receipt, "receipt_sha256")
        with self.assertRaisesRegex(DependencyRegistryError, "chronology"):
            validate_dependency_cluster_registry_v2(registry, receipt)

    def test_exposure_or_outcome_access_fails_closed(self) -> None:
        registry = _postfreeze_registry()
        receipt = _receipt(registry)
        receipt["records"][0]["frozen_evaluation_template_exposed_to_training_runtime"] = True
        _close(receipt["records"][0], "record_sha256")
        _close(receipt, "receipt_sha256")
        with self.assertRaisesRegex(DependencyRegistryError, "access flag"):
            validate_dependency_cluster_registry_v2(registry, receipt)

    def test_stale_registry_binding_fails(self) -> None:
        registry = _postfreeze_registry()
        receipt = _receipt(registry)
        registry["limitations"].append("a later mutation")
        registry["limitations"].sort()
        _close(registry, "registry_body_sha256")
        with self.assertRaisesRegex(DependencyRegistryError, "registry hash"):
            validate_dependency_cluster_registry_v2(registry, receipt)

    def test_base_must_predate_freeze_and_match_projection(self) -> None:
        registry = _postfreeze_registry()
        receipt = _receipt(registry)
        receipt["records"][0]["base_checkpoint_created_at"] = "2026-07-17T00:00:00Z"
        _close(receipt["records"][0], "record_sha256")
        _close(receipt, "receipt_sha256")
        with self.assertRaisesRegex(DependencyRegistryError, "pre-freeze base"):
            validate_dependency_cluster_registry_v2(registry, receipt)

    def test_lineage_schema_and_runtime_share_utc_and_nonzero_hash_rules(self) -> None:
        registry = _postfreeze_registry()
        receipt = _receipt(registry)
        schema = json.loads(LINEAGE_SCHEMA.read_text(encoding="utf-8"))
        validator_cls = validator_for(schema)
        validator_cls.check_schema(schema)
        validator = validator_cls(schema, format_checker=FormatChecker())
        validator.validate(receipt)

        offset = copy.deepcopy(receipt)
        offset["created_at"] = "2026-07-18T01:06:00+00:00"
        with self.assertRaises(ValidationError):
            validator.validate(offset)
        with self.assertRaisesRegex(DependencyRegistryError, "RFC3339 UTC"):
            validate_dependency_cluster_registry_v2(registry, offset)

        zero = copy.deepcopy(receipt)
        zero["base_model_intake_body_sha256"] = "0" * 64
        _close(zero, "receipt_sha256")
        with self.assertRaises(ValidationError):
            validator.validate(zero)
        with self.assertRaisesRegex(DependencyRegistryError, "all-zero"):
            validate_dependency_cluster_registry_v2(registry, zero)


if __name__ == "__main__":
    unittest.main()
