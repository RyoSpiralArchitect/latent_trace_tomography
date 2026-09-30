from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from jsonschema import FormatChecker
from jsonschema.validators import validator_for

from latent_trace_tomography.anchor_plan import validate_anchor_construction_plan


ROOT = Path(__file__).resolve().parents[1]
SUCCESSOR = ROOT / "successors" / "oss_reliance_regime_v0" / "controlled_anchor_phantom_v1"
MANIFEST = SUCCESSOR / "manifest.json"
PLAN = SUCCESSOR / "anchor_construction_plan.json"
PLAN_SCHEMA = SUCCESSOR / "anchor_construction_plan.schema.json"
INTAKE = ROOT / "operations" / "oss1_registry_authoring_v2" / "base_model_intake.json"
PUBLIC_SCREEN = (
    ROOT / "operations" / "oss1_registry_authoring_v2" / "public_candidate_feasibility_screen.json"
)
GENERATOR_SOURCE = ROOT / "src" / "latent_trace_tomography" / "anchor_training.py"

PROTOCOL_SHA256 = "5c49316503b2cec2ad26d4bf47dc59c02f0b61d9f6896b84035e6d0412dced11"
DESIGN_MANIFEST_SHA256 = "8c974390ceea3f1defaae19067359c909b4182dd26c321075c9e25ee1518e64b"
CORRECTION_MANIFEST_SHA256 = "4d2282f761c75cfc5b3cd9dcb36ddb624b8982c0eed9076f3a70bf9498787e3a"
OPERATIONAL_MANIFEST_SHA256 = "d9ea2369a14983756dcb60cb985d4eabea10f2471f934a5c3598478dbf4dc93c"

EXPECTED_ASSET_PATHS = {
    "operations/oss1_registry_authoring_v2/base_model_intake.json",
    "operations/oss1_registry_authoring_v2/schemas/base_model_intake.schema.json",
    "src/latent_trace_tomography/artifact_hash.py",
    "src/latent_trace_tomography/anchor_intake.py",
    "src/latent_trace_tomography/anchor_plan.py",
    "src/latent_trace_tomography/anchor_training.py",
    "successors/oss_reliance_regime_v0/controlled_anchor_phantom_v1/anchor_construction_plan.json",
    "successors/oss_reliance_regime_v0/controlled_anchor_phantom_v1/anchor_construction_plan.schema.json",
    "tests/test_anchor_intake.py",
    "tests/test_anchor_plan.py",
    "tests/test_anchor_training.py",
    "tests/test_controlled_anchor_phantom_successor.py",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ControlledAnchorPhantomSuccessorTests(unittest.TestCase):
    def test_plan_schema_and_semantic_validator_both_pass(self) -> None:
        plan = json.loads(PLAN.read_text(encoding="utf-8"))
        intake = json.loads(INTAKE.read_text(encoding="utf-8"))
        schema = json.loads(PLAN_SCHEMA.read_text(encoding="utf-8"))
        validator_cls = validator_for(schema)
        validator_cls.check_schema(schema)
        validator_cls(schema, format_checker=FormatChecker()).validate(plan)
        result = validate_anchor_construction_plan(
            plan,
            base_model_intake=intake,
            base_model_intake_path=INTAKE,
            generator_source_path=GENERATOR_SOURCE,
        )
        self.assertEqual(result["run_count"], 9)
        self.assertEqual(result["dependency_cluster_count"], 3)
        self.assertFalse(result["model_calls_authorized"])

    def test_manifest_is_append_only_parented_and_strictly_claim_narrowing(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        parent = manifest["parent"]
        self.assertEqual(parent["protocol_sha256"], PROTOCOL_SHA256)
        self.assertEqual(parent["design_manifest_sha256"], DESIGN_MANIFEST_SHA256)
        self.assertEqual(
            parent["required_correction_manifest_sha256"],
            CORRECTION_MANIFEST_SHA256,
        )
        self.assertEqual(parent["operational_manifest_sha256"], OPERATIONAL_MANIFEST_SHA256)
        scope = manifest["scientific_scope"]
        self.assertEqual(scope["claim_ceiling_relation_to_parent"], "strict_subclaim")
        self.assertFalse(scope["natural_checkpoint_anchor_claim_allowed"])
        self.assertFalse(scope["population_generalization_allowed"])
        self.assertFalse(scope["proprietary_internal_truth_claim_allowed"])
        self.assertEqual(manifest["authorization_effect"], "none")

    def test_manifest_discloses_metadata_access_but_zero_model_execution(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        exposure = manifest["outcome_exposure"]
        self.assertTrue(exposure["metadata_network_access_occurred"])
        self.assertEqual(exposure["intake_metadata_requests"], 13)
        self.assertEqual(exposure["configuration_files_downloaded"], 3)
        self.assertEqual(exposure["tokenizer_files_downloaded"], 8)
        for field in (
            "weight_files_downloaded",
            "model_loads",
            "training_forward_calls",
            "training_backward_calls",
            "generation_calls",
            "api_inference_calls",
            "oss1_measurement_calls",
        ):
            self.assertEqual(exposure[field], 0)
        self.assertFalse(exposure["training_started"])
        self.assertFalse(exposure["anchor_construction_authorization_issued"])
        self.assertFalse(exposure["discovery_authorization_issued"])

    def test_bound_inputs_and_exact_asset_set_are_raw_hash_closed(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        bound = {row["input_id"]: row for row in manifest["bound_inputs"]}
        self.assertEqual(set(bound), {"base_model_intake", "public_candidate_feasibility_screen"})
        for input_row in bound.values():
            self.assertEqual(_sha256(ROOT / input_row["path"]), input_row["sha256"])
            payload = json.loads((ROOT / input_row["path"]).read_text(encoding="utf-8"))
            self.assertEqual(payload[input_row["body_hash_field"]], input_row["body_sha256"])

        assets = manifest["assets"]
        paths = [row["path"] for row in assets]
        ids = [row["asset_id"] for row in assets]
        self.assertEqual(set(paths), EXPECTED_ASSET_PATHS)
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(len(ids), len(set(ids)))
        for asset in assets:
            self.assertEqual(_sha256(ROOT / asset["path"]), asset["sha256"])

    def test_public_screen_is_an_unresolved_input_not_an_anchor_assignment(self) -> None:
        screen = json.loads(PUBLIC_SCREEN.read_text(encoding="utf-8"))
        self.assertEqual(screen["summary"]["eligible_count"], 0)
        self.assertEqual(screen["summary"]["retrospective_anchor_assignments"], 0)
        self.assertTrue(all(row["enrollment_status"] == "unresolved" for row in screen["records"]))
        self.assertTrue(all("anchor_condition_id" not in row for row in screen["records"]))


if __name__ == "__main__":
    unittest.main()
