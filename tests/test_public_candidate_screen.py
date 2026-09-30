from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import FormatChecker
from jsonschema.validators import validator_for

from latent_trace_tomography.dependency_registry import canonical_artifact_sha256


ROOT = Path(__file__).resolve().parents[1]
SCREEN = (
    ROOT / "operations" / "oss1_registry_authoring_v2" / "public_candidate_feasibility_screen.json"
)
SCREEN_SCHEMA = (
    ROOT
    / "operations"
    / "oss1_registry_authoring_v2"
    / "schemas"
    / "public_candidate_feasibility_screen.schema.json"
)


class PublicCandidateScreenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.screen = json.loads(SCREEN.read_text(encoding="utf-8"))

    def test_all_nine_public_candidates_remain_unresolved(self) -> None:
        records = self.screen["records"]
        self.assertEqual(len(records), 9)
        self.assertEqual({row["enrollment_status"] for row in records}, {"unresolved"})
        self.assertTrue(
            all("missing_pre_outcome_anchor_assignment" in row["reason_ids"] for row in records)
        )
        self.assertEqual(self.screen["summary"]["eligible_count"], 0)
        self.assertEqual(self.screen["summary"]["retrospective_anchor_assignments"], 0)
        self.assertTrue(all("anchor_condition_id" not in row for row in records))

    def test_screen_is_sorted_and_self_addressed(self) -> None:
        records = self.screen["records"]
        self.assertEqual(
            [row["candidate_id"] for row in records],
            sorted(row["candidate_id"] for row in records),
        )
        for row in records:
            self.assertEqual(row["reason_ids"], sorted(set(row["reason_ids"])))
            self.assertLess(row["revision_last_modified_at"], "2026-07-17T00:00:00Z")
        expected = canonical_artifact_sha256(
            {key: value for key, value in self.screen.items() if key != "screen_body_sha256"}
        )
        self.assertEqual(self.screen["screen_body_sha256"], expected)

    def test_screen_performed_no_model_or_inference_calls(self) -> None:
        summary = self.screen["summary"]
        self.assertEqual(summary["model_weight_downloads"], 0)
        self.assertEqual(summary["model_loads"], 0)
        self.assertEqual(summary["inference_calls"], 0)

    def test_screen_schema_is_valid_and_rejects_retrospective_labels(self) -> None:
        schema = json.loads(SCREEN_SCHEMA.read_text(encoding="utf-8"))
        validator_cls = validator_for(schema)
        validator_cls.check_schema(schema)
        validator_cls(schema, format_checker=FormatChecker()).validate(self.screen)


if __name__ == "__main__":
    unittest.main()
