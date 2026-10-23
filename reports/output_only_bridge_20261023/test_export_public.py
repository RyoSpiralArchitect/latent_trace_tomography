"""The checkpoint exporter must not silently publish unreviewed additions."""

import json
from pathlib import Path
import tempfile
import unittest

import export_public as e


class ExportBoundaryTests(unittest.TestCase):
    def fixture(self, root):
        manifest = {
            "format": "ltt_public_checkpoint_v1",
            "retained_plan_sha256": "",
            "retained_result_sha256": {},
            "published_files": {},
        }
        (root / "plan.json").write_text('{"targets": []}\n')
        manifest["retained_plan_sha256"] = e.digest(root / "plan.json")
        for name in ("furnace-attempt-001", "api-weak-attempt-001", "api-challenge-attempt-001"):
            directory = root / name
            directory.mkdir()
            path = directory / "results.jsonl"
            path.write_text("{}\n")
            manifest["retained_result_sha256"][name] = e.digest(path)
        (root / "analysis-v1").mkdir()
        for name in (
            "forecast_lock.json",
            "analysis.json",
            "verification.json",
            "posthoc_format_diagnostic.json",
        ):
            path = root / name if name == "forecast_lock.json" else root / "analysis-v1" / name
            path.write_text("{}\n")
            manifest["published_files"][name] = e.digest(path)
        return manifest

    def test_exact_reviewed_bytes_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            e.verify_retained_bytes(root, self.fixture(root))

    def test_unreviewed_nested_metadata_and_summaries_are_rejected(self):
        for name in (
            "plan.json",
            "furnace-attempt-001/results.jsonl",
            "forecast_lock.json",
            "analysis-v1/verification.json",
            "analysis-v1/analysis.json",
            "analysis-v1/posthoc_format_diagnostic.json",
        ):
            with self.subTest(path=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                manifest = self.fixture(root)
                path = root / name
                value = json.loads(path.read_text())
                value["private_test_metadata"] = {"not_for_publication": "fixture"}
                path.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, "unreviewed retained export input"):
                    e.verify_retained_bytes(root, manifest)

    def test_wrong_run_is_rejected_before_output_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "plan.json").write_text("{}\n")
            output = root / "public-output"
            with self.assertRaisesRegex(ValueError, "unreviewed retained export input"):
                e.export(root, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
