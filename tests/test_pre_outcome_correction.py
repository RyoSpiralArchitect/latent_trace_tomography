from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from jsonschema.validators import validator_for


ROOT = Path(__file__).resolve().parents[1]
PARENT_PROTOCOL = ROOT / "protocols" / "oss_reliance_regime_v0" / "protocol.json"
PARENT_DESIGN_MANIFEST = (
    ROOT / "protocols" / "oss_reliance_regime_v0" / "design_freeze_manifest.json"
)
PARENT_SITE_SCHEMA = ROOT / "schemas" / "site_discovery_report.schema.json"
SUCCESSOR_ROOT = ROOT / "successors" / "oss_reliance_regime_v0" / "pre_outcome_correction_0001"
CORRECTION = SUCCESSOR_ROOT / "correction.json"
MANIFEST = SUCCESSOR_ROOT / "manifest.json"
SUCCESSOR_SITE_SCHEMA = SUCCESSOR_ROOT / "schemas" / "site_discovery_report.schema.json"

PARENT_PROTOCOL_SHA256 = "5c49316503b2cec2ad26d4bf47dc59c02f0b61d9f6896b84035e6d0412dced11"
PARENT_DESIGN_MANIFEST_SHA256 = "8c974390ceea3f1defaae19067359c909b4182dd26c321075c9e25ee1518e64b"
PARENT_SITE_SCHEMA_SHA256 = "433f13ec1425833148c4c44f1385afd838112975d987704eb3d8150578dbda7f"
SUCCESSOR_SITE_SCHEMA_SHA256 = "f8bf4ed72fa3cdfc79113fc787153b7328a8b88348ca30ce05dc8e0842b43aeb"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PreOutcomeCorrectionTests(unittest.TestCase):
    def test_parent_freeze_is_byte_identical(self) -> None:
        self.assertEqual(_sha256(PARENT_PROTOCOL), PARENT_PROTOCOL_SHA256)
        self.assertEqual(_sha256(PARENT_DESIGN_MANIFEST), PARENT_DESIGN_MANIFEST_SHA256)
        self.assertEqual(_sha256(PARENT_SITE_SCHEMA), PARENT_SITE_SCHEMA_SHA256)

    def test_successor_schema_is_valid_and_removes_only_the_false_upper_bound(self) -> None:
        parent = json.loads(PARENT_SITE_SCHEMA.read_text(encoding="utf-8"))
        successor = json.loads(SUCCESSOR_SITE_SCHEMA.read_text(encoding="utf-8"))
        validator_for(successor).check_schema(successor)

        parent_trials = parent["properties"]["candidate_trial_evidence"]
        successor_trials = successor["properties"]["candidate_trial_evidence"]
        self.assertEqual(parent_trials["minItems"], 1728)
        self.assertEqual(parent_trials["maxItems"], 1728)
        self.assertEqual(successor_trials["minItems"], 1728)
        self.assertNotIn("maxItems", successor_trials)
        self.assertEqual(_sha256(SUCCESSOR_SITE_SCHEMA), SUCCESSOR_SITE_SCHEMA_SHA256)

    def test_correction_is_explicitly_parented_call_free_and_non_authorizing(self) -> None:
        correction = json.loads(CORRECTION.read_text(encoding="utf-8"))
        self.assertEqual(correction["parent"]["protocol_sha256"], PARENT_PROTOCOL_SHA256)
        self.assertEqual(
            correction["parent"]["design_manifest_sha256"],
            PARENT_DESIGN_MANIFEST_SHA256,
        )
        self.assertEqual(
            correction["parent"]["site_discovery_report_schema_sha256"],
            PARENT_SITE_SCHEMA_SHA256,
        )
        self.assertEqual(
            correction["successor"]["site_discovery_report_schema_sha256"],
            SUCCESSOR_SITE_SCHEMA_SHA256,
        )
        self.assertEqual(correction["outcome_exposure_at_correction"]["oss_model_calls"], 0)
        self.assertFalse(correction["outcome_exposure_at_correction"]["oss_outcomes_exposed"])
        self.assertFalse(correction["authorization_effect"]["authorizes_model_calls"])
        self.assertFalse(correction["authorization_effect"]["authorizes_discovery"])

    def test_live_validation_requires_schema_and_semantic_validator(self) -> None:
        correction = json.loads(CORRECTION.read_text(encoding="utf-8"))
        composition = correction["successor"]["validation_composition"]
        self.assertEqual(len(composition), 3)
        self.assertIn("successor JSON Schema", composition[0])
        self.assertIn("validate_site_discovery_report", composition[1])
        self.assertIn("both validations", composition[2])

    def test_manifest_closes_every_correction_asset(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["parent"]["protocol_sha256"], PARENT_PROTOCOL_SHA256)
        self.assertEqual(
            manifest["parent"]["design_manifest_sha256"],
            PARENT_DESIGN_MANIFEST_SHA256,
        )
        self.assertEqual(manifest["outcome_exposure"]["oss_model_calls"], 0)
        for asset in manifest["assets"]:
            self.assertEqual(_sha256(ROOT / asset["path"]), asset["sha256"])


if __name__ == "__main__":
    unittest.main()
