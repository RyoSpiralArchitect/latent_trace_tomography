import copy
from pathlib import Path
import shutil
import socket
import tempfile
import unittest
from unittest.mock import patch

import export_public as export
import replay as p


class SavedMappingCheckpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = Path(__file__).with_name("data")
        cls.rows = p.records(cls.data / "observations.jsonl")
        cls.result = p.calculate(cls.rows)

    def test_replay_is_call_free(self):
        with patch.object(socket, "create_connection", side_effect=AssertionError("network")):
            result = p.verify(self.data)
        self.assertEqual(result["observations"], 112)
        self.assertEqual(result["new_model_calls"], 0)

    def test_correctness_and_instruction_format_are_separate(self):
        totals = self.result["prespecified_format_secondary"]["totals"]
        self.assertEqual(
            totals,
            {
                "n": 112,
                "correct_under_frozen_parser": 112,
                "exact_marker": 86,
                "bare_symbol": 26,
                "unresolved": 0,
            },
        )
        self.assertEqual(set(self.result["score"]["contrasts"].values()), {0.0})

    def test_format_counts_by_mapping(self):
        groups = self.result["prespecified_format_secondary"]["by_condition"]
        self.assertEqual(groups["full_task/standard"]["bare_symbol"], 19)
        self.assertEqual(groups["full_task/inverted"]["bare_symbol"], 7)
        self.assertEqual(groups["full_task/direct"]["exact_marker"], 32)

    def test_repeat_format_is_explicitly_posthoc(self):
        repeat = self.result["posthoc_repeat_format_readout"]
        self.assertEqual(repeat["raw_text_disagreements"], 8)
        self.assertEqual(repeat["parsed_format_disagreements"], 8)
        self.assertIn("not a new prespecified", repeat["label"])
        self.assertEqual(self.result["score"]["repeat_answer_disagreements"], 0)
        self.assertEqual(self.result["score"]["content_instance_count"], 2)

    def test_missing_duplicate_extra_and_nontext_are_rejected(self):
        extra, bad = copy.deepcopy(self.rows), copy.deepcopy(self.rows)
        extra[0]["model"] = "metadata-not-a-feature"
        bad[0]["output_text"] = None
        for rows in (self.rows[:-1], self.rows[:-1] + [self.rows[0]], extra, bad):
            with self.assertRaises(ValueError):
                p.calculate(rows)

    def test_unresolved_is_retained_in_denominator(self):
        rows = copy.deepcopy(self.rows)
        rows[0]["output_text"] = "ambiguous"
        totals = p.calculate(rows)["prespecified_format_secondary"]["totals"]
        self.assertEqual(totals["n"], 112)
        self.assertEqual(totals["correct_under_frozen_parser"], 111)
        self.assertEqual(totals["unresolved"], 1)

    def test_source_pins_fail_before_export_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "plan.json").write_text("{}\n")
            with self.assertRaises(ValueError):
                export.export(root, root / "public")
            self.assertFalse((root / "public").exists())

    def test_tampering_and_extra_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            shutil.copytree(self.data, root)
            (root / "private.txt").write_text("must not appear")
            with self.assertRaises(ValueError):
                p.verify(root)
            (root / "private.txt").unlink()
            (root / "analysis.json").write_text("{}\n")
            with self.assertRaises(ValueError):
                p.verify(root)

    def test_duplicate_json_and_nonfinite_rejected(self):
        for text in ('{"a":1,"a":2}', '{"a":NaN}'):
            with self.assertRaises(ValueError):
                p.loads(text)

    def test_execution_counts_rates_and_settings_checked(self):
        original = p.read(self.data / "execution.json")
        for field, value in (
            ("completed_requests", 111),
            ("model", "other"),
            ("estimated_uncached_cost_usd", 0.1),
            ("automatic_retries", 1),
        ):
            changed = copy.deepcopy(original)
            changed[field] = value
            with self.assertRaises(ValueError):
                p.verify_execution(changed)

    def test_public_payload_excludes_private_material(self):
        for path in self.data.iterdir():
            text = path.read_text()
            for forbidden in ("/Users/", "/home/", "Bearer ", "response_id", "OPENAI_API_KEY"):
                self.assertNotIn(forbidden, text)
        self.assertTrue(all(set(row) == {"query_id", "output_text"} for row in self.rows))


if __name__ == "__main__":
    unittest.main()
