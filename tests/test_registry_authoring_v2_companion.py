from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from jsonschema.validators import validator_for


ROOT = Path(__file__).resolve().parents[1]
OPERATION_ROOT = ROOT / "operations" / "oss1_registry_authoring_v2"
MANIFEST = OPERATION_ROOT / "manifest.json"
DOC = OPERATION_ROOT / "docs" / "registry_authoring_successor.md"
SUCCESSOR_MANIFEST = (
    ROOT
    / "successors"
    / "oss_reliance_regime_v0"
    / "controlled_anchor_phantom_v1"
    / "manifest.json"
)

PROTOCOL_SHA256 = "5c49316503b2cec2ad26d4bf47dc59c02f0b61d9f6896b84035e6d0412dced11"
DESIGN_MANIFEST_SHA256 = "8c974390ceea3f1defaae19067359c909b4182dd26c321075c9e25ee1518e64b"
CORRECTION_MANIFEST_SHA256 = "4d2282f761c75cfc5b3cd9dcb36ddb624b8982c0eed9076f3a70bf9498787e3a"
OPERATIONAL_MANIFEST_SHA256 = "d9ea2369a14983756dcb60cb985d4eabea10f2471f934a5c3598478dbf4dc93c"

EXPECTED_SCHEMA_PATHS = {
    "operations/oss1_registry_authoring_v2/schemas/base_model_intake.schema.json",
    "operations/oss1_registry_authoring_v2/schemas/postfreeze_anchor_lineage_receipt.schema.json",
    "operations/oss1_registry_authoring_v2/schemas/public_candidate_feasibility_screen.schema.json",
    "operations/oss1_registry_authoring_v2/schemas/source_evidence_catalog.schema.json",
}
EXPECTED_ASSET_PATHS = {
    "operations/oss1_registry_authoring_v2/base_model_intake.json",
    "operations/oss1_registry_authoring_v2/docs/registry_authoring_successor.md",
    "operations/oss1_registry_authoring_v2/public_candidate_feasibility_screen.json",
    *EXPECTED_SCHEMA_PATHS,
    "src/latent_trace_tomography/artifact_hash.py",
    "src/latent_trace_tomography/registry_authoring.py",
    "src/latent_trace_tomography/registry_evidence.py",
    "src/latent_trace_tomography/registry_temporal.py",
    "tests/test_public_candidate_screen.py",
    "tests/test_registry_authoring.py",
    "tests/test_registry_authoring_v2_companion.py",
    "tests/test_registry_evidence.py",
    "tests/test_registry_temporal.py",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RegistryAuthoringV2CompanionTests(unittest.TestCase):
    def test_manifest_parent_dag_and_non_authority_boundary(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        parent = manifest["parent"]
        self.assertEqual(parent["protocol_sha256"], PROTOCOL_SHA256)
        self.assertEqual(parent["design_manifest_sha256"], DESIGN_MANIFEST_SHA256)
        self.assertEqual(
            parent["required_correction_manifest_sha256"],
            CORRECTION_MANIFEST_SHA256,
        )
        self.assertEqual(
            parent["predecessor_operational_manifest_sha256"],
            OPERATIONAL_MANIFEST_SHA256,
        )
        self.assertEqual(
            parent["controlled_anchor_successor_manifest_sha256"],
            _sha256(SUCCESSOR_MANIFEST),
        )
        self.assertEqual(manifest["authorization_effect"], "none")
        self.assertEqual(manifest["status"], "pre_registry_authoring_companion_frozen")

    def test_scope_explicitly_stops_before_real_evidence_or_authorization(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        scope = manifest["scope"]
        for field in (
            "real_registry_present",
            "lineage_receipt_present",
            "source_catalog_instance_present",
            "kind_specific_semantic_validation_present",
            "discovery_authorization_ready",
        ):
            self.assertFalse(scope[field])
        self.assertEqual(
            scope["evidence_catalog_assurance"],
            "typed identity and byte/content closure only",
        )
        self.assertTrue(manifest["outcome_exposure"]["metadata_network_access_occurred"])
        self.assertEqual(manifest["outcome_exposure"]["weight_files_downloaded"], 0)
        self.assertEqual(manifest["outcome_exposure"]["model_loads"], 0)
        self.assertEqual(manifest["outcome_exposure"]["training_forward_calls"], 0)
        self.assertEqual(manifest["outcome_exposure"]["oss1_measurement_calls"], 0)

    def test_all_schemas_are_structurally_valid(self) -> None:
        for relative_path in sorted(EXPECTED_SCHEMA_PATHS):
            schema = json.loads((ROOT / relative_path).read_text(encoding="utf-8"))
            with self.subTest(schema=relative_path):
                validator_for(schema).check_schema(schema)

    def test_manifest_closes_the_exact_asset_set(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        assets = manifest["assets"]
        paths = [row["path"] for row in assets]
        ids = [row["asset_id"] for row in assets]
        self.assertEqual(set(paths), EXPECTED_ASSET_PATHS)
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(len(ids), len(set(ids)))
        for asset in assets:
            self.assertEqual(_sha256(ROOT / asset["path"]), asset["sha256"])

    def test_authoring_document_freezes_conjunctive_order_and_non_proofs(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        headings = (
            "validate_dependency_cluster_registry_v2(...)",
            "validate_controlled_anchor_plan_registry_binding(...)",
            "load_source_evidence_catalog(...)",
            "Kind-specific evidence-body semantic validators",
        )
        positions = [text.index(fragment) for fragment in headings]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("discovery_authorization_ready = false", text)
        self.assertIn("model_calls_authorized = false", text)
        self.assertIn("do not prove evidence-body truth", text)
        self.assertIn(
            "Effective independent `n` is therefore three, not nine",
            " ".join(text.split()),
        )
        self.assertIn("Do not download weights", text)

    def test_no_real_registry_catalog_or_lineage_instance_is_misrepresented(self) -> None:
        for filename in (
            "dependency_cluster_registry.json",
            "postfreeze_anchor_lineage_receipt.json",
            "source_evidence_catalog.json",
        ):
            self.assertFalse((OPERATION_ROOT / filename).exists())


if __name__ == "__main__":
    unittest.main()
