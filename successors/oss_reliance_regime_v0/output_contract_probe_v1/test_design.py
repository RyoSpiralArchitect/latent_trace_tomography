from collections import Counter, defaultdict
import json
from pathlib import Path
import tempfile
import unittest

import design as d


class OutputContractDesign(unittest.TestCase):
    def test_replay_and_execution_boundary(self):
        result = d.verify(d.HERE / "fixtures")
        self.assertEqual(result["planned_requests"], 96)
        self.assertEqual(result["new_model_calls"], 0)
        self.assertFalse(result["live_execution_authorized"])
        self.assertIn("not_execution_ready", result["status"])

    def test_balance_and_pairing(self):
        panel = d.panel()
        self.assertEqual(Counter(q["kind"] for q in panel), {"full_task": 64, "mapping_only": 32})
        self.assertEqual(Counter(q["render_mode"] for q in panel), {"marker": 48, "bare": 48})
        pairs = defaultdict(list)
        for q in panel:
            pairs[(q["parent_case_id"], q["replicate_id"])].append(q)
        self.assertEqual(len(pairs), 48)
        for values in pairs.values():
            self.assertEqual({q["render_mode"] for q in values}, {"marker", "bare"})
            self.assertEqual(len({q["expected_answer"] for q in values}), 1)

    def test_marker_prompts_are_retained_parent_bytes(self):
        original = {q["case_id"]: q for q in d.parent().panel()}
        for q in d.panel():
            if q["render_mode"] == "marker":
                self.assertEqual(q["prompt_text"], original[q["parent_case_id"]]["prompt_text"])

    def test_only_format_lines_change(self):
        original = {q["case_id"]: q for q in d.parent().panel()}
        for q in d.panel():
            source = original[q["parent_case_id"]]
            for field in (
                "kind",
                "content",
                "semantic",
                "cue",
                "layout",
                "response_mode",
                "expected_answer",
            ):
                self.assertEqual(q[field], source[field])
            if q["render_mode"] == "bare":
                self.assertNotIn("FINAL:", q["prompt_text"])
                before = source["prompt_text"].splitlines()
                after = q["prompt_text"].splitlines()
                self.assertEqual(len(before), len(after))
                changes = [(a, b) for a, b in zip(before, after) if a != b]
                self.assertEqual(len(changes), 3)
                self.assertTrue(changes[0][0].startswith("- PASS maps"))
                self.assertTrue(changes[1][0].startswith("- FAIL maps"))
                self.assertIn("Emit exactly A or B", changes[2][1])

    def test_request_metadata_boundary(self):
        payload = d.artifacts()
        self.assertTrue(
            all(set(q) == {"query_id", "prompt_text"} for q in payload["requests.json"])
        )
        self.assertTrue(all("prompt_text" not in q for q in payload["scoring_key.json"]))
        self.assertTrue(
            all(q["query_id"] not in q["prompt_text"] for q in payload["requests.json"])
        )

    def test_source_design_is_not_reauthorized(self):
        value = json.loads((d.HERE / "design.json").read_text())
        self.assertEqual(value["limits"]["generation_attempts"], 96)
        self.assertEqual(value["limits"]["money_cap_usd"], 0.50)
        self.assertFalse(value["live_execution_authorized"])
        self.assertIn("new explicit live authorization", value["launch_requirements"])

    def test_no_overwrite_and_mutation_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "fixtures"
            d.prepare(out)
            with self.assertRaises(FileExistsError):
                d.prepare(out)
            (out / "requests.json").write_text("[]\n")
            with self.assertRaises(ValueError):
                d.verify(out)

    def test_fixed_repetitions_are_byte_identical(self):
        pairs = defaultdict(list)
        for q in d.panel():
            pairs[q["case_id"]].append(q["prompt_text"])
        self.assertEqual(len(pairs), 48)
        self.assertTrue(all(len(v) == 2 and v[0] == v[1] for v in pairs.values()))


if __name__ == "__main__":
    unittest.main()
