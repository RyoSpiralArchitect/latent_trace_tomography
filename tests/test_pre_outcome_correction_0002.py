from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from typing import Any

from jsonschema.validators import validator_for


ROOT = Path(__file__).resolve().parents[1]
PARENT_PROTOCOL = ROOT / "protocols" / "oss_reliance_regime_v0" / "protocol.json"
PARENT_DESIGN_MANIFEST = (
    ROOT / "protocols" / "oss_reliance_regime_v0" / "design_freeze_manifest.json"
)
PARENT_DISCOVERY_TEMPLATE = (
    ROOT / "protocols" / "oss_reliance_regime_v0" / "discovery_authorization.json"
)
PARENT_SITE_SCHEMA = ROOT / "schemas" / "site_discovery_report.schema.json"
CORRECTION_0001_MANIFEST = (
    ROOT / "successors" / "oss_reliance_regime_v0" / "pre_outcome_correction_0001" / "manifest.json"
)
SUCCESSOR_ROOT = ROOT / "successors" / "oss_reliance_regime_v0" / "pre_outcome_correction_0002"
CORRECTION = SUCCESSOR_ROOT / "correction.json"
MANIFEST = SUCCESSOR_ROOT / "manifest.json"
SUCCESSOR_SITE_SCHEMA = SUCCESSOR_ROOT / "schemas" / "site_discovery_report.schema.json"

PARENT_PROTOCOL_SHA256 = "5c49316503b2cec2ad26d4bf47dc59c02f0b61d9f6896b84035e6d0412dced11"
PARENT_DESIGN_MANIFEST_SHA256 = "8c974390ceea3f1defaae19067359c909b4182dd26c321075c9e25ee1518e64b"
PARENT_DISCOVERY_TEMPLATE_SHA256 = (
    "3a80dc38a066c980ecfa3bb4221c65b273fc8acfa44b5ea55ae845fed19eed79"
)
PARENT_SITE_SCHEMA_SHA256 = "433f13ec1425833148c4c44f1385afd838112975d987704eb3d8150578dbda7f"
CORRECTION_0001_MANIFEST_SHA256 = "5cc38fb5d741736f2f8a182aa46aa8e5dd07b6992ce350644d172e7e93f7d9ea"
SUCCESSOR_SITE_SCHEMA_SHA256 = "cf40cc44067847b77ff2315484a5fc90f1fac2128813f67ac5c978e9caed0679"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _escape_pointer_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _parsed_diff(before: Any, after: Any, pointer: str = "") -> list[dict[str, Any]]:
    if isinstance(before, dict) and isinstance(after, dict):
        differences: list[dict[str, Any]] = []
        before_keys = set(before)
        after_keys = set(after)
        for key in sorted(before_keys - after_keys):
            differences.append(
                {
                    "operation": "remove",
                    "json_pointer": f"{pointer}/{_escape_pointer_token(key)}",
                }
            )
        for key in sorted(after_keys - before_keys):
            differences.append(
                {
                    "operation": "add",
                    "json_pointer": f"{pointer}/{_escape_pointer_token(key)}",
                    "value": after[key],
                }
            )
        for key in sorted(before_keys & after_keys):
            differences.extend(
                _parsed_diff(
                    before[key],
                    after[key],
                    f"{pointer}/{_escape_pointer_token(key)}",
                )
            )
        return differences

    if isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            return [{"operation": "replace", "json_pointer": pointer, "value": after}]
        differences = []
        for index, (before_item, after_item) in enumerate(zip(before, after, strict=True)):
            differences.extend(_parsed_diff(before_item, after_item, f"{pointer}/{index}"))
        return differences

    if before != after or type(before) is not type(after):
        return [{"operation": "replace", "json_pointer": pointer, "value": after}]
    return []


def _sort_differences(differences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        differences,
        key=lambda item: (item["json_pointer"], item["operation"]),
    )


class PreOutcomeCorrection0002Tests(unittest.TestCase):
    def test_parent_and_correction_0001_are_byte_identical(self) -> None:
        self.assertEqual(_sha256(PARENT_PROTOCOL), PARENT_PROTOCOL_SHA256)
        self.assertEqual(_sha256(PARENT_DESIGN_MANIFEST), PARENT_DESIGN_MANIFEST_SHA256)
        self.assertEqual(
            _sha256(PARENT_DISCOVERY_TEMPLATE),
            PARENT_DISCOVERY_TEMPLATE_SHA256,
        )
        self.assertEqual(_sha256(PARENT_SITE_SCHEMA), PARENT_SITE_SCHEMA_SHA256)
        self.assertEqual(
            _sha256(CORRECTION_0001_MANIFEST),
            CORRECTION_0001_MANIFEST_SHA256,
        )

    def test_successor_has_exactly_the_allowlisted_parsed_schema_diff(self) -> None:
        parent = json.loads(PARENT_SITE_SCHEMA.read_text(encoding="utf-8"))
        successor = json.loads(SUCCESSOR_SITE_SCHEMA.read_text(encoding="utf-8"))
        correction = json.loads(CORRECTION.read_text(encoding="utf-8"))

        actual = _sort_differences(_parsed_diff(parent, successor))
        expected = _sort_differences(correction["exact_parsed_schema_diff_allowlist"])
        self.assertEqual(actual, expected)
        self.assertEqual(parent["$defs"], successor["$defs"])
        self.assertEqual(
            parent["properties"]["candidate_trial_evidence"]["minItems"],
            successor["properties"]["candidate_trial_evidence"]["minItems"],
        )
        self.assertNotIn(
            "maxItems",
            successor["properties"]["candidate_trial_evidence"],
        )

    def test_successor_schema_is_valid_and_content_addressed(self) -> None:
        successor = json.loads(SUCCESSOR_SITE_SCHEMA.read_text(encoding="utf-8"))
        validator_for(successor).check_schema(successor)
        self.assertEqual(_sha256(SUCCESSOR_SITE_SCHEMA), SUCCESSOR_SITE_SCHEMA_SHA256)

    def test_correction_is_call_free_non_authorizing_and_supersedes_0001(self) -> None:
        correction = json.loads(CORRECTION.read_text(encoding="utf-8"))
        self.assertEqual(
            correction["parent"]["correction_0001_manifest_sha256"],
            CORRECTION_0001_MANIFEST_SHA256,
        )
        exposure = correction["outcome_exposure_at_correction"]
        self.assertEqual(exposure["oss_model_calls"], 0)
        self.assertFalse(exposure["oss_outcomes_exposed"])
        self.assertFalse(exposure["discovery_authorization_issued"])
        self.assertFalse(correction["authorization_effect"]["authorizes_model_calls"])
        self.assertFalse(correction["authorization_effect"]["authorizes_discovery"])
        self.assertIn(
            "not accepted for future live validation",
            correction["supersession"]["correction_0001_role"],
        )
        self.assertIn(
            "required minimal structural correction",
            correction["supersession"]["correction_0002_role"],
        )

    def test_manifest_closes_every_correction_asset(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["parent"]["protocol_sha256"], PARENT_PROTOCOL_SHA256)
        self.assertEqual(
            manifest["parent"]["design_manifest_sha256"],
            PARENT_DESIGN_MANIFEST_SHA256,
        )
        self.assertEqual(
            manifest["parent"]["correction_0001_manifest_sha256"],
            CORRECTION_0001_MANIFEST_SHA256,
        )
        self.assertEqual(manifest["outcome_exposure"]["oss_model_calls"], 0)
        self.assertEqual(manifest["authorization_effect"], "none")
        for asset in manifest["assets"]:
            self.assertEqual(_sha256(ROOT / asset["path"]), asset["sha256"])


if __name__ == "__main__":
    unittest.main()
