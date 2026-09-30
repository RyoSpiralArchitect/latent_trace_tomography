from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from jsonschema.validators import validator_for


ROOT = Path(__file__).resolve().parents[1]
OPERATION_ROOT = ROOT / "operations" / "oss1_execution_v1"
MANIFEST = OPERATION_ROOT / "manifest.json"
PLAYBOOK = OPERATION_ROOT / "docs" / "oss1_execution_playbook.md"
TAXONOMY = OPERATION_ROOT / "docs" / "failure_taxonomy.md"
REGISTRY_SCHEMA = OPERATION_ROOT / "schemas" / "dependency_cluster_registry.schema.json"
GATE_RECEIPT_SCHEMA = OPERATION_ROOT / "schemas" / "registry_authorization_gate_receipt.schema.json"

PARENT_PROTOCOL_SHA256 = "5c49316503b2cec2ad26d4bf47dc59c02f0b61d9f6896b84035e6d0412dced11"
PARENT_DESIGN_MANIFEST_SHA256 = "8c974390ceea3f1defaae19067359c909b4182dd26c321075c9e25ee1518e64b"
CORRECTION_ID = "oss1_pre_outcome_correction_0002_minimal_site_report_cardinality"
CORRECTION_MANIFEST_SHA256 = "4d2282f761c75cfc5b3cd9dcb36ddb624b8982c0eed9076f3a70bf9498787e3a"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class OperationalCompanionTests(unittest.TestCase):
    def test_registry_schema_is_structurally_valid(self) -> None:
        schema = json.loads(REGISTRY_SCHEMA.read_text(encoding="utf-8"))
        validator_for(schema).check_schema(schema)
        self.assertIn("does not certify statistical independence", schema["description"])
        receipt_schema = json.loads(GATE_RECEIPT_SCHEMA.read_text(encoding="utf-8"))
        validator_for(receipt_schema).check_schema(receipt_schema)
        self.assertIn("necessary but not sufficient", receipt_schema["description"])

    def test_playbook_has_ordered_gates_exact_budgets_and_no_authority(self) -> None:
        text = PLAYBOOK.read_text(encoding="utf-8")
        self.assertIn(PARENT_PROTOCOL_SHA256, text)
        self.assertIn(PARENT_DESIGN_MANIFEST_SHA256, text)
        self.assertIn(CORRECTION_ID, text)
        self.assertIn("Authorization effect: `none`", text)
        self.assertIn("OSS model calls represented by this document: `0`", text)
        self.assertIn("576 + 128 C", text)
        self.assertIn("16,416", text)
        self.assertIn("16,992", text)
        self.assertIn("17,568 + 128 C", text)
        self.assertIn("validate_discovery_readiness(..., authority_secret=...)", text)
        self.assertIn("registry-authorization gate receipt", text)
        self.assertIn("development_scoring_key", text)
        self.assertIn("cannot be proven at this pre-reveal gate", text)
        self.assertNotIn("correction 0001", text)
        headings = [
            "### S0",
            "### S1",
            "### G1",
            "### S2",
            "### G2",
            "### S3",
            "### S4",
            "### G4",
            "### S5",
            "### S6",
            "### G6",
            "### S7",
            "### S8",
            "### S9",
        ]
        positions = [text.index(heading) for heading in headings]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("The next legal action is to populate", text)

    def test_taxonomy_separates_observation_inference_and_integrity(self) -> None:
        text = TAXONOMY.read_text(encoding="utf-8")
        self.assertIn(PARENT_PROTOCOL_SHA256, text)
        self.assertIn("Normative for OSS-1: `false`", text)
        for layer in (
            "Behavior Drift Detection",
            "Prospective Failure-Surface Prediction",
            "OSS-Reference Susceptibility Compatibility",
        ):
            self.assertIn(layer, text)
        for axis in (
            "## Measurement validity",
            "## Scientific disposition",
            "## Assurance level",
            "## Claim tier",
        ):
            self.assertIn(axis, text)
        self.assertIn("`surface_cue_consistent` | cue-consistent divergence", text)
        self.assertIn("does not prove cue reliance", text)
        self.assertIn("does not prove codebook-binding failure", text)
        self.assertIn("The current implementation ceiling is `prediction_locked`", text)
        self.assertIn("does not yet\nexist as a validated live product", text)
        self.assertIn("maximum L2 statement remains bounded equivalence-class", text)
        self.assertIn("`abstained` | inference withheld", text)
        self.assertIn("at least three development dependency clusters", text)
        self.assertIn("at least three\nseparately sealed confirmatory", text)

    def test_manifest_is_parented_non_authorizing_and_hash_closed(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["parent"]["protocol_sha256"], PARENT_PROTOCOL_SHA256)
        self.assertEqual(
            manifest["parent"]["design_manifest_sha256"],
            PARENT_DESIGN_MANIFEST_SHA256,
        )
        self.assertEqual(manifest["parent"]["required_correction_id"], CORRECTION_ID)
        self.assertEqual(
            manifest["parent"]["required_correction_manifest_sha256"],
            CORRECTION_MANIFEST_SHA256,
        )
        self.assertEqual(manifest["authorization_effect"], "none")
        self.assertEqual(manifest["outcome_exposure"]["oss_model_calls"], 0)
        for asset in manifest["assets"]:
            self.assertEqual(_sha256(ROOT / asset["path"]), asset["sha256"])


if __name__ == "__main__":
    unittest.main()
