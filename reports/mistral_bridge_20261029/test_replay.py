import copy
from pathlib import Path
import shutil
import tempfile
import unittest

import export_public as export
import replay as p


class PublicCheckpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = Path(__file__).with_name("data")
        cls.inventory = p.read(cls.data / "inventory.json")
        cls.rows = p.records(cls.data / "observations.jsonl")
        cls.result = p.calculate(cls.inventory, cls.rows)

    def test_replay(self):
        self.assertEqual(p.verify(self.data)["observations"], 1120)

    def test_abstention_not_prediction_failure(self):
        primary = self.result["primary"]
        self.assertEqual(primary["status"], "abstain_outside_reference_support")
        self.assertEqual(primary["conditional"]["available"], 0)
        self.assertEqual(primary["weak_channels"]["unresolved_answers"], 0)

    def test_baseline_is_nondiscriminating(self):
        self.assertEqual(
            self.result["primary"]["baseline_composition"], {"A,B": 22, "A,B,unresolved": 10}
        )
        self.assertEqual(self.result["primary"]["unconditional_baseline"]["singleton_resolved"], 0)

    def test_posthoc_denominators(self):
        post = self.result["posthoc"]
        self.assertEqual(post["task_oracle"]["weak"]["task_correct"], 70)
        self.assertEqual(post["task_oracle"]["challenge"]["task_correct"], 30)
        self.assertEqual(len(post["task_errors"]), 12)
        self.assertEqual(
            len({(v["content"], v["cell"], v["projection_id"]) for v in post["task_errors"]}), 6
        )
        self.assertTrue(
            all(v["expected"] == "A" and v["observed"] == "B" for v in post["task_errors"])
        )
        self.assertEqual(post["repeat_comparison"]["weak"]["answer_disagreements"], 0)

    def test_no_target_challenge_leakage(self):
        changed = copy.deepcopy(self.rows)
        challenge_keys = {p.r._key(q) for q in self.inventory["panel"] if q["phase"] == "challenge"}
        for row in changed:
            if (
                row["target_id"] == self.inventory["api_target_id"]
                and p.r._key(row) in challenge_keys
            ):
                row["output_text"] = "invalid"
        self.assertEqual(
            p.calculate(self.inventory, changed)["reference_report"],
            self.result["reference_report"],
        )

    def test_missing_or_duplicate_row_rejected(self):
        for changed in (self.rows[:-1], self.rows + [self.rows[0]]):
            with self.assertRaises(ValueError):
                p.calculate(self.inventory, changed)

    def test_extra_telemetry_rejected(self):
        changed = copy.deepcopy(self.rows)
        changed[0]["latency"] = "0"
        with self.assertRaises(ValueError):
            p.calculate(self.inventory, changed)

    def test_prompt_oracle_crosscheck(self):
        q = copy.deepcopy(self.inventory["panel"][0])
        q["cell"] = 7 - q["cell"]
        with self.assertRaises(ValueError):
            p.oracle(q)

    def test_manifest_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "data"
            shutil.copytree(self.data, data)
            (data / "analysis.json").write_text("{}\n")
            with self.assertRaises(ValueError):
                p.verify(data)

    def test_export_rejects_unreviewed_input_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "plan.json").write_text('{"private_addition":"do-not-export"}\n')
            with self.assertRaises(ValueError):
                export.export(root, root, root / "output")
            self.assertFalse((root / "output").exists())

    def test_public_data_excludes_private_fields(self):
        for path in self.data.iterdir():
            text = path.read_text()
            for forbidden in ("/Users/", "/home/", "response_id", "Bearer ", "generated_token_ids"):
                self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
