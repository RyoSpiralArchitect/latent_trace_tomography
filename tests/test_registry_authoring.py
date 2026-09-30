from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from latent_trace_tomography.dependency_registry import (
    DependencyRegistryError,
    canonical_artifact_sha256,
)
from latent_trace_tomography.registry_authoring import (
    REQUIRED_NEXT_GATE,
    _bind_exact_json,
    validate_controlled_anchor_plan_registry_binding,
    validate_registry_authoring_bundle_v2,
)


ROOT = Path(__file__).resolve().parents[1]
INTAKE_PATH = ROOT / "operations" / "oss1_registry_authoring_v2" / "base_model_intake.json"
PLAN_PATH = (
    ROOT
    / "successors"
    / "oss_reliance_regime_v0"
    / "controlled_anchor_phantom_v1"
    / "anchor_construction_plan.json"
)
GENERATOR_SOURCE = ROOT / "src" / "latent_trace_tomography" / "anchor_training.py"


def _raw_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_bound_surfaces(
    directory: str,
    registry: dict,
    receipt: dict,
) -> tuple[Path, Path]:
    root = Path(directory)
    registry_path = root / "dependency_cluster_registry.json"
    receipt_path = root / "postfreeze_anchor_lineage_receipt.json"
    registry_path.write_text(
        json.dumps(registry, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return registry_path, receipt_path


def _surfaces() -> tuple[dict, dict, dict, dict]:
    intake = json.loads(INTAKE_PATH.read_text(encoding="utf-8"))
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    bases = {row["base_model_unit_id"]: row for row in intake["records"]}
    projected_models = []
    candidates = []
    lineage_records = []
    for index, run in enumerate(plan["runs"]):
        base = bases[run["base_model_unit_id"]]
        model_artifact = canonical_artifact_sha256({"descendant": run["model_unit_id"]})
        configuration = canonical_artifact_sha256({"config": run["model_unit_id"]})
        checkpoint_manifest = canonical_artifact_sha256({"checkpoint": run["model_unit_id"]})
        projected_models.append(
            {
                "model_unit_id": run["model_unit_id"],
                "independent_training_run_id": run["training_run_id"],
                "architecture_family_id": run["architecture_family_id"],
                "anchor_condition_id": run["anchor_condition_id"],
                "shared_base_artifact_sha256": base["weight_artifact"]["sha256"],
                "tokenizer_revision": base["tokenizer_bundle"]["revision"],
                "tokenizer_artifact_sha256": base["tokenizer_bundle"]["artifact_sha256"],
                "model_artifact_sha256": model_artifact,
                "configuration_sha256": configuration,
                "anchor_provenance": {
                    "assignment_timing": "pre_outcome_training_condition",
                    "anchor_assignment_manifest_sha256": plan["anchor_assignment_manifest_sha256"],
                    "training_recipe_sha256": run["training_recipe_sha256"],
                    "training_data_sha256": run["raw_training_data_sha256"],
                },
            }
        )
        candidates.append(
            {
                "model_unit_id": run["model_unit_id"],
                "checkpoint_provenance": {
                    "checkpoint_role": "fine_tune",
                    "checkpoint_manifest_sha256": checkpoint_manifest,
                    "training_run_parent_id": run["training_run_id"],
                    "step_or_token_count": run["fixed_optimizer_steps"],
                },
            }
        )
        lineage_records.append(
            {
                "model_unit_id": run["model_unit_id"],
                "training_run_id": run["training_run_id"],
                "anchor_condition_id": run["anchor_condition_id"],
                "attempt_index": 1,
                "completion_status": "complete_fixed_steps",
                "selection_policy": run["selection_policy"],
                "base_model_record_sha256": base["record_sha256"],
                "base_checkpoint_artifact_sha256": base["weight_artifact"]["sha256"],
                "base_tokenizer_artifact_sha256": base["tokenizer_bundle"]["artifact_sha256"],
                "base_checkpoint_created_at": base["revision_last_modified_at"],
                "descendant_checkpoint_manifest_sha256": checkpoint_manifest,
                "descendant_model_artifact_sha256": model_artifact,
                "descendant_configuration_sha256": configuration,
                "descendant_tokenizer_artifact_sha256": base["tokenizer_bundle"]["artifact_sha256"],
                "anchor_assignment_manifest_sha256": plan["anchor_assignment_manifest_sha256"],
                "anchor_assignment_committed_at": plan["frozen_at"],
                "training_recipe_sha256": run["training_recipe_sha256"],
                "training_data_sha256": run["raw_training_data_sha256"],
                "derived_target_inventory_sha256": run["derived_target_inventory_sha256"],
                "fixed_optimizer_step_count": run["fixed_optimizer_steps"],
                "training_forward_call_count": run["training_forward_call_budget"],
                "training_backward_call_count": run["training_backward_call_budget"],
                "record_sha256": canonical_artifact_sha256({"lineage-fixture-index": index}),
            }
        )
    registry = {
        "authorization_projection": {"model_registry": projected_models},
        "candidate_model_units": candidates,
    }
    receipt = {
        "base_model_intake_body_sha256": intake["intake_body_sha256"],
        "base_model_intake_file_sha256": _raw_sha256(INTAKE_PATH),
        "anchor_construction_plan_body_sha256": plan["plan_body_sha256"],
        "anchor_construction_plan_file_sha256": _raw_sha256(PLAN_PATH),
        "records": lineage_records,
    }
    return registry, receipt, intake, plan


class RegistryAuthoringTests(unittest.TestCase):
    def test_plan_intake_and_all_nine_lineage_rows_are_exactly_bound(self) -> None:
        registry, receipt, intake, plan = _surfaces()
        with tempfile.TemporaryDirectory() as directory:
            registry_path, receipt_path = _write_bound_surfaces(directory, registry, receipt)
            result = validate_controlled_anchor_plan_registry_binding(
                registry,
                receipt,
                registry_path=registry_path,
                lineage_receipt_path=receipt_path,
                base_model_intake=intake,
                base_model_intake_path=INTAKE_PATH,
                construction_plan=plan,
                construction_plan_path=PLAN_PATH,
                generator_source_path=GENERATOR_SOURCE,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["model_unit_count"], 9)
        self.assertEqual(result["training_forward_call_count"], 9216)
        self.assertEqual(result["training_backward_call_count"], 9216)
        self.assertFalse(result["model_calls_authorized"])

    def test_plan_binding_rejects_step_base_condition_and_plan_hash_drift(self) -> None:
        for mutation, message in (
            (
                lambda registry, receipt: receipt["records"][0].update(
                    {"fixed_optimizer_step_count": 1}
                ),
                "lineage record",
            ),
            (
                lambda registry, receipt: receipt["records"][0].update(
                    {"base_model_record_sha256": canonical_artifact_sha256({"wrong": "base"})}
                ),
                "lineage record",
            ),
            (
                lambda registry, receipt: registry["authorization_projection"]["model_registry"][
                    0
                ].update({"anchor_condition_id": "semantic_anchor"}),
                "projected model",
            ),
            (
                lambda registry, receipt: receipt.update(
                    {
                        "anchor_construction_plan_file_sha256": canonical_artifact_sha256(
                            {"wrong": "plan"}
                        )
                    }
                ),
                "plan_file_sha256",
            ),
        ):
            with self.subTest(message=message):
                registry, receipt, intake, plan = _surfaces()
                mutation(registry, receipt)
                with tempfile.TemporaryDirectory() as directory:
                    registry_path, receipt_path = _write_bound_surfaces(
                        directory, registry, receipt
                    )
                    with self.assertRaisesRegex(DependencyRegistryError, message):
                        validate_controlled_anchor_plan_registry_binding(
                            registry,
                            receipt,
                            registry_path=registry_path,
                            lineage_receipt_path=receipt_path,
                            base_model_intake=intake,
                            base_model_intake_path=INTAKE_PATH,
                            construction_plan=plan,
                            construction_plan_path=PLAN_PATH,
                            generator_source_path=GENERATOR_SOURCE,
                        )

    def test_registry_and_receipt_files_are_strictly_byte_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload_path = root / "registry.json"
            payload_path.write_text('{"a":1}\n', encoding="utf-8")
            loaded, raw_sha256 = _bind_exact_json({"a": 1}, payload_path, context="registry file")
            self.assertEqual(loaded, {"a": 1})
            self.assertEqual(raw_sha256, _raw_sha256(payload_path))

            with self.assertRaisesRegex(DependencyRegistryError, "differs from bound file"):
                _bind_exact_json({"a": 2}, payload_path, context="registry file")

            payload_path.write_text('{"a":1,"a":2}\n', encoding="utf-8")
            with self.assertRaisesRegex(DependencyRegistryError, "duplicate key"):
                _bind_exact_json({"a": 2}, payload_path, context="registry file")

            target_path = root / "receipt.json"
            target_path.write_text("{}\n", encoding="utf-8")
            symlink_path = root / "receipt-link.json"
            symlink_path.symlink_to(target_path)
            with self.assertRaisesRegex(DependencyRegistryError, "regular file"):
                _bind_exact_json({}, symlink_path, context="lineage receipt file")

    @patch("latent_trace_tomography.registry_authoring.load_source_evidence_catalog")
    @patch(
        "latent_trace_tomography.registry_authoring."
        "validate_controlled_anchor_plan_registry_binding"
    )
    @patch("latent_trace_tomography.registry_authoring.validate_dependency_cluster_registry_v2")
    def test_conjunctive_entrypoint_never_claims_semantic_or_authorization_readiness(
        self,
        temporal_mock,
        plan_mock,
        catalog_mock,
    ) -> None:
        temporal_mock.return_value = {
            "registry_body_sha256": "a" * 64,
            "lineage_receipt_sha256": "b" * 64,
            "postfreeze_model_unit_count": 9,
            "dependency_cluster_count": 3,
        }
        plan_mock.return_value = {
            "registry_file_sha256": "2" * 64,
            "lineage_receipt_file_sha256": "3" * 64,
            "plan_body_sha256": "c" * 64,
            "plan_file_sha256": "d" * 64,
            "base_model_intake_body_sha256": "e" * 64,
            "base_model_intake_file_sha256": "f" * 64,
        }
        catalog_mock.return_value = {"catalog_body_sha256": "1" * 64}
        registry = {"source_records": []}
        receipt = {}
        with tempfile.TemporaryDirectory() as directory:
            registry_path, receipt_path = _write_bound_surfaces(directory, registry, receipt)
            result = validate_registry_authoring_bundle_v2(
                registry,
                receipt,
                registry_path=registry_path,
                lineage_receipt_path=receipt_path,
                source_catalog_path="required-catalog.json",
                base_model_intake={},
                base_model_intake_path=INTAKE_PATH,
                construction_plan={},
                construction_plan_path=PLAN_PATH,
                generator_source_path=GENERATOR_SOURCE,
            )
        temporal_mock.assert_called_once()
        plan_mock.assert_called_once()
        catalog_mock.assert_called_once()
        self.assertTrue(result["source_identity_payloads_closed"])
        self.assertFalse(result["kind_specific_evidence_semantics_validated"])
        self.assertFalse(result["discovery_authorization_ready"])
        self.assertFalse(result["model_calls_authorized"])
        self.assertEqual(result["registry_file_sha256"], "2" * 64)
        self.assertEqual(result["lineage_receipt_file_sha256"], "3" * 64)
        self.assertEqual(result["required_next_gate"], REQUIRED_NEXT_GATE)


if __name__ == "__main__":
    unittest.main()
