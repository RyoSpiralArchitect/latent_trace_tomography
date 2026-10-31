import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import rehearse as mock
import score as s


class OutputContractScoring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.key, _, _ = s.frozen_inputs()

    def rows(self, output=None):
        return [
            {
                "query_id": q["query_id"],
                "output_text": (
                    output(q)
                    if output
                    else ("FINAL: " if q["render_mode"] == "marker" else "") + q["expected_answer"]
                ),
            }
            for q in self.key
        ]

    def test_perfect_panel_and_denominators(self):
        result = s.score(self.rows())
        self.assertEqual(
            result["totals"],
            {
                "n": 96,
                "answer_correct": 96,
                "answer_errors": 0,
                "format_compliant": 96,
                "format_errors": 0,
                "joint_success": 96,
                "joint_failures": 0,
                "unresolved": 0,
            },
        )
        for kind, n in (("full_task", 32), ("mapping_only", 16)):
            self.assertEqual(result["paired_joint_success"][kind]["both_success"], n)
            self.assertEqual(
                result["repeat_disagreements"][kind],
                {
                    "pairs": n,
                    "answer_disagreements": 0,
                    "format_disagreements": 0,
                },
            )
            self.assertEqual(
                result["primary_contrasts"][kind + "_joint_failure_rate_bare_minus_marker"], 0
            )
            for style in ("bare", "marker"):
                self.assertEqual(result["by_kind_render"][f"{kind}/{style}"]["n"], n)
                for mode in ("standard", "inverted"):
                    self.assertEqual(
                        result["by_kind_map_render"][f"{kind}/{mode}/{style}"]["n"], n // 2
                    )

    def test_format_compliance_is_not_answer_correctness(self):
        rows = self.rows(
            lambda q: (
                ("FINAL: " if q["render_mode"] == "marker" else "")
                + {"A": "B", "B": "A"}[q["expected_answer"]]
            )
        )
        total = s.score(rows)["totals"]
        self.assertEqual(
            (
                total["answer_correct"],
                total["format_compliant"],
                total["joint_success"],
                total["unresolved"],
            ),
            (0, 96, 0, 0),
        )

    def test_unresolved_stays_in_both_denominators_no_repair(self):
        for invalid in ("", "final: A", "FINAL:A", "ANSWER: A", "A.", "A\nexplanation", "PASS"):
            with self.subTest(text=invalid):
                result = s.score(self.rows(lambda q: invalid))
                self.assertEqual(result["totals"]["n"], 96)
                self.assertEqual(result["totals"]["unresolved"], 96)
                self.assertEqual(result["totals"]["format_errors"], 96)
                self.assertEqual(result["totals"]["answer_errors"], 96)
                self.assertEqual(result["paired_joint_success"]["full_task"]["neither"], 32)

    def test_contrasts_have_bare_minus_marker_sign_and_are_kind_specific(self):
        rows = self.rows(
            lambda q: (
                ("  " if q["kind"] == "full_task" else "\tFINAL: ") + q["expected_answer"] + "\n"
            )
        )
        result = s.score(rows)
        self.assertEqual(
            result["primary_contrasts"],
            {
                "full_task_joint_failure_rate_bare_minus_marker": -1,
                "mapping_only_joint_failure_rate_bare_minus_marker": 1,
            },
        )
        self.assertEqual(result["paired_joint_success"]["full_task"]["bare_only"], 32)
        self.assertEqual(result["paired_joint_success"]["mapping_only"]["marker_only"], 16)
        self.assertEqual(result["totals"]["answer_correct"], 96)

    def test_pairs_are_joined_by_id_not_row_order(self):
        rows = self.rows()
        rows[0]["output_text"] = ""
        self.assertEqual(s.score(rows), s.score(rows[::-1]))
        q = self.key[0]
        result = s.score(rows)
        k, style = q["kind"], q["render_mode"]
        expected_delta = (1 if style == "bare" else -1) / (32 if k == "full_task" else 16)
        self.assertEqual(
            result["primary_contrasts"][k + "_joint_failure_rate_bare_minus_marker"], expected_delta
        )
        self.assertEqual(result["repeat_disagreements"][k]["answer_disagreements"], 1)
        self.assertEqual(result["repeat_disagreements"][k]["format_disagreements"], 1)

    def test_complete_unique_two_field_inventory_required(self):
        rows = self.rows()
        for bad in (
            rows[:-1],
            rows + rows[:1],
            rows[:-1] + rows[:1],
            list(range(96)),
            [{**rows[0], "query_id": "unplanned"}] + rows[1:],
            [{**rows[0], "query_id": 0}] + rows[1:],
            [{**rows[0], "output_text": None}] + rows[1:],
            [{**rows[0], "metadata": {}}] + rows[1:],
        ):
            with self.assertRaises(ValueError):
                s.score(bad)

    def test_duplicate_json_field_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.jsonl"
            path.write_text('{"query_id":"x","output_text":"A","output_text":"B"}\n')
            with self.assertRaisesRegex(ValueError, "duplicate JSON"):
                s.read_rows(path)

    def test_changed_design_fails_before_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "design"
            shutil.copytree(s.DESIGN, copy)
            shutil.copytree(
                s.DESIGN.parent / "answer_mapping_probe_v1", copy.parent / "answer_mapping_probe_v1"
            )
            with patch.object(s, "DESIGN", copy):
                with (copy / "fixtures/scoring_key.json").open("a") as stream:
                    stream.write(" ")
                with self.assertRaises(ValueError):
                    s.score(self.rows())
                (copy / "design.py").write_text("raise AssertionError('must not be executed')\n")
                with self.assertRaisesRegex(ValueError, "source mismatch"):
                    s.score(self.rows())


class OutputContractRehearsal(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_mixed_rehearsal_joint_answer_format_and_repeat_counts(self):
        out = self.root / "mixed"
        with patch.object(socket, "socket", side_effect=AssertionError("network")):
            receipt = mock.rehearse(out, "mixed")
        self.assertFalse(receipt["live_execution_authorized"])
        self.assertEqual(receipt["model_calls"], 0)
        self.assertEqual(receipt["status"], "mock_complete")
        self.assertEqual(receipt["simulated_attempts"], 96)
        self.assertEqual(receipt["recorded_rows"], 96)
        self.assertIsNone(receipt["unknown_outcome_query_id"])
        self.assertEqual(receipt["scorer_sha256"], s.digest(Path(s.__file__)))
        for name, digest in receipt["files_sha256"].items():
            self.assertEqual(s.digest(out / name), digest)
        saved = json.loads((out / "score.json").read_text())
        self.assertEqual(saved["observation_source"], "synthetic_rehearsal_only")
        result = saved["score"]
        self.assertEqual(result, s.score(s.read_rows(out / "observations.jsonl")))
        self.assertEqual(
            result["totals"],
            {
                "n": 96,
                "answer_correct": 72,
                "answer_errors": 24,
                "format_compliant": 60,
                "format_errors": 36,
                "joint_success": 48,
                "joint_failures": 48,
                "unresolved": 12,
            },
        )
        for kind, n in (("full_task", 32), ("mapping_only", 16)):
            self.assertEqual(
                result["paired_joint_success"][kind],
                {
                    "both_success": 0,
                    "marker_only": n // 2,
                    "bare_only": n // 2,
                    "neither": 0,
                },
            )
            self.assertEqual(
                result["repeat_disagreements"][kind],
                {
                    "pairs": n,
                    "answer_disagreements": n // 2,
                    "format_disagreements": 3 * n // 4,
                },
            )

    def test_stopped_keeps_prefix_and_unknown_outcome_without_score(self):
        out = self.root / "stopped"
        receipt = mock.rehearse(out, "stopped")
        self.assertEqual(receipt["status"], "mock_stopped_incomplete")
        self.assertEqual(
            (receipt["simulated_attempts"], receipt["recorded_rows"], receipt["automatic_retries"]),
            (12, 11, 0),
        )
        requests, _, _, _ = s.frozen_inputs()
        self.assertEqual(receipt["unknown_outcome_query_id"], requests[11]["query_id"])
        self.assertEqual(receipt["stop_reason"], "injected_unknown_outcome_no_response")
        self.assertEqual(set(receipt["files_sha256"]), {"observations.jsonl"})
        self.assertFalse((out / "score.json").exists())
        rows = s.read_rows(out / "observations.jsonl")
        self.assertEqual([r["query_id"] for r in rows], [r["query_id"] for r in requests[:11]])
        with self.assertRaisesRegex(ValueError, "complete 96-slot"):
            s.score(rows)
        with self.assertRaises(FileExistsError):
            mock.rehearse(out, "perfect")
        self.assertEqual(receipt, json.loads((out / "receipt.json").read_text()))

    def test_mock_is_deterministic_and_score_cli_fails_closed(self):
        a, b = self.root / "a", self.root / "b"
        self.assertEqual(mock.rehearse(a, "perfect"), mock.rehearse(b, "perfect"))
        run = subprocess.run(
            [sys.executable, "-S", s.__file__, str(a / "observations.jsonl")],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(json.loads(run.stdout)["totals"]["joint_success"], 96)
        mock.rehearse(self.root / "stopped", "stopped")
        run = subprocess.run(
            [sys.executable, "-S", s.__file__, str(self.root / "stopped/observations.jsonl")],
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(run.stdout, "")
        self.assertIn("not scored", run.stderr)


if __name__ == "__main__":
    unittest.main()
