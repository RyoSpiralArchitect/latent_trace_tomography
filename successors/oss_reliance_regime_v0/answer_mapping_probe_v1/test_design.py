import copy
from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest

import design as d


def perfect():
    return [
        {"query_id": q["query_id"], "output_text": "FINAL: " + q["expected_answer"]}
        for q in d.panel()
    ]


class Design(unittest.TestCase):
    def test_counts(self):
        panel = d.panel()
        self.assertEqual(Counter(q["kind"] for q in panel), {"full_task": 96, "mapping_only": 16})
        self.assertEqual(len({q["prompt_text"] for q in panel}), 56)
        self.assertEqual(len({q["query_id"] for q in panel}), 112)
        self.assertEqual(panel, d.panel())

    def test_factor_balance(self):
        full = [q for q in d.panel() if q["kind"] == "full_task"]
        self.assertEqual(Counter(q["response_mode"] for q in full), dict.fromkeys(d.MODES, 32))
        for mode in d.MODES:
            cells = Counter(
                (q["semantic"], q["cue"], q["layout"]) for q in full if q["response_mode"] == mode
            )
            self.assertEqual(len(cells), 8)
            self.assertEqual(set(cells.values()), {4})

    def test_mapping_control_excludes_task(self):
        for q in d.panel():
            if q["kind"] == "mapping_only":
                self.assertNotIn("Candidate code", q["prompt_text"])
                self.assertNotIn("Advisory ribbon", q["prompt_text"])
                self.assertIn("already-decided result is " + q["semantic"], q["prompt_text"])

    def test_no_answers_in_request_metadata(self):
        self.assertTrue(all(set(q) == {"query_id", "prompt_text"} for q in d.request_rows()))
        self.assertTrue(all("prompt_text" not in q for q in d.scoring_key()))

    def test_exact_nonoverlap_with_public_development(self):
        repo = Path(__file__).resolve().parents[3]
        prompts = {q["prompt_text"] for q in d.panel()}
        for checkpoint in ("output_only_bridge_20261023", "mistral_bridge_20261029"):
            rows = [
                json.loads(line)
                for line in (repo / "reports" / checkpoint / "data/observations.jsonl")
                .read_text()
                .splitlines()
            ]
            self.assertFalse(prompts & {q["prompt_text"] for q in rows})

    def test_perfect_readout(self):
        result = d.score(perfect())
        self.assertEqual(set(result["contrasts"].values()), {0.0})
        self.assertEqual(result["repeat_pairs"], 56)
        self.assertEqual(result["repeat_answer_disagreements"], 0)

    def test_declared_contrasts_match_scorer(self):
        design, _, _ = d.artifacts()
        self.assertEqual(set(design["primary_contrasts"]), set(d.score(perfect())["contrasts"]))

    def test_inversion_failures(self):
        observations = perfect()
        for q, row in zip(d.panel(), observations):
            if q["response_mode"] == "inverted":
                row["output_text"] = d.expected(q["semantic"], "standard")
        result = d.score(observations)
        self.assertEqual(set(result["contrasts"].values()), {1.0})
        self.assertEqual(result["paired_tables"]["inverted"], {"direct_1_encoded_0": 32})

    def test_unresolved_is_not_dropped(self):
        values = [{"query_id": q["query_id"], "output_text": "ambiguous"} for q in d.panel()]
        result = d.score(values)
        self.assertEqual(result["groups"]["full_task/direct"]["errors"], 32)
        self.assertEqual(result["groups"]["full_task/direct"]["unresolved"], 32)

    def test_mode_specific_parser(self):
        self.assertEqual(d.parse("A", "direct"), (None, "unresolved"))
        self.assertEqual(d.parse("PASS", "inverted"), (None, "unresolved"))
        self.assertEqual(d.parse(" FINAL: FAIL\n", "direct"), ("FAIL", "exact_marker"))

    def test_incomplete_duplicate_and_extra_fields_rejected(self):
        values = perfect()
        duplicate = values[:-1] + [values[0]]
        extra = copy.deepcopy(values)
        extra[0]["logprobs"] = []
        for invalid in (values[:-1], duplicate, extra):
            with self.assertRaises(ValueError):
                d.score(invalid)

    def test_artifacts_replay_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "new"
            d.prepare(out)
            self.assertFalse(d.verify(out)["live_execution_authorized"])
            with self.assertRaises(FileExistsError):
                d.prepare(out)
            (out / "requests.json").write_text("[]\n")
            with self.assertRaises(ValueError):
                d.verify(out)

    def test_checked_in_design_matches(self):
        self.assertEqual(d.verify(d.HERE / "fixtures")["requests"], 112)

    def test_manifest_accounting_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "new"
            d.prepare(out)
            path = out / "manifest.json"
            manifest = json.loads(path.read_text())
            manifest["request_count"] = 0
            path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                d.verify(out)


if __name__ == "__main__":
    unittest.main()
