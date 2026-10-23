"""Offline checks for the saved-evidence analyzer; no live reruns."""
from pathlib import Path
import tempfile
import unittest

import analyze_saved as a
import bridge as b
import diagnose_format as d
from test_bridge import plan, saved_rows


def reference_rows(p):
    return [{"query_id": q["query_id"], "phase": q["phase"],
             "observation": b.observation(q, u["target_id"], "FINAL: A")}
            for u in p["targets"] for q in p["panel"]]


def api_rows(p, text="FINAL: A"):
    return [{"query_id": q["query_id"], "phase": q["phase"],
             "observation": b.observation(q, p["api_target_id"], text)} for q in p["panel"]]


class AnalysisTests(unittest.TestCase):
    def test_replay_and_probability_mass(self):
        p = plan()
        replay = a.replay_forecast(p, reference_rows(p), [r for r in api_rows(p) if r["phase"] == "weak"])
        self.assertEqual(len(replay["support_targets"]), 9)
        self.assertEqual(replay["status"], "behavior_only_forecast")
        for item in replay["predictions"]:
            self.assertAlmostEqual(sum(item["probabilities_A_B_failure"]), 1)
            self.assertAlmostEqual(item["probabilities_A_B_failure"][0], 7/9)

    def test_abstention_remains_unscored(self):
        p = plan()
        api = api_rows(p, "B")
        reference = reference_rows(p)
        lock = a.replay_forecast(p, reference, [r for r in api if r["phase"] == "weak"])
        self.assertEqual(lock["status"], "abstain_outside_exact_reference_support")
        analysis = a.describe(p, reference + api, lock)
        self.assertEqual(analysis["locked_forecast_score"]["coverage"], 0)
        self.assertIsNone(analysis["locked_forecast_score"]["mean_log_loss_nats"])
        self.assertEqual(analysis["query_scores"], [])

    def test_repeatability_and_full_text_distinguished(self):
        p = plan()
        api = api_rows(p, "Rationale\nFINAL: A")
        reference = reference_rows(p)
        lock = a.replay_forecast(p, reference, [r for r in api if r["phase"] == "weak"])
        analysis = a.describe(p, reference + api, lock)
        self.assertEqual(analysis["repeatability"]["target-10"], {"pairs": 56, "raw_equal": 56, "parsed_equal": 56})
        pairs = [r for r in analysis["matching_pair_checks"] if "target-10" in r["targets"]]
        self.assertEqual(len(pairs), 9)
        self.assertTrue(all(r["weak_raw_equal"] == 0 and r["weak_parsed_equal"] == 80 for r in pairs))

    def test_weak_features_do_not_read_challenge(self):
        p = plan()
        reference = reference_rows(p)
        weak = [r for r in api_rows(p) if r["phase"] == "weak"]
        old = a.replay_forecast(p, reference, weak)
        for row in reference:
            if row["phase"] == "challenge":
                row["observation"]["output_text"] = "FINAL: B"
        new = a.replay_forecast(p, reference, weak)
        self.assertEqual(old["api_feature"], new["api_feature"])
        self.assertEqual(old["reference_features"], new["reference_features"])
        self.assertEqual(old["support_targets"], new["support_targets"])
        self.assertNotEqual(old["predictions"], new["predictions"])

    def test_prompt_tamper_detected(self):
        p = plan()
        row = api_rows(p)[0]
        a.verify_observation(row, p["panel"][0], p["api_target_id"])
        row["observation"]["prompt_text"] += "corruption"
        with self.assertRaises(ValueError):
            a.verify_observation(row, p["panel"][0], p["api_target_id"])

    def test_chain_tamper_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "events.jsonl"
            journal = b.Journal(path)
            journal.add("phase_opened", {"n": 0})
            journal.add("phase_closed", {"n": 1})
            journal.close()
            a.chain(path, "sha256")
            text = path.read_text().replace('"n":1', '"n":2')
            path.write_text(text)
            with self.assertRaises(ValueError):
                a.chain(path, "sha256")

    def test_semantic_and_cue_are_distinct_in_conflict(self):
        p = plan()
        reference = reference_rows(p)
        api = api_rows(p)
        for row, query in zip(api, p["panel"]):
            semantic, cue, identity = b.CELLS[query["cell"]]
            row["observation"]["output_text"] = "FINAL: " + a.expected_marker(semantic, identity)
        lock = a.replay_forecast(p, reference, [r for r in api if r["phase"] == "weak"])
        stats = a.describe(p, reference + api, lock)["per_projection"]
        selected = [r for r in stats if r["target_id"] == "target-10" and r["projection_id"] in b.CHALLENGES]
        self.assertEqual(sum(r["semantic_consistent"] for r in selected), 32)
        self.assertEqual(sum(r["cue_consistent"] for r in selected), 0)

    def test_posthoc_diagnostic_does_not_rewrite_primary_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            p = plan()
            b.write_new(root / "plan.json", p)
            api = api_rows(p, "A")
            api[-1]["observation"]["output_text"] = "FINAL: AB"
            saved_rows(root / "furnace-attempt-001", root / "plan.json", reference_rows(p))
            for phase in ("weak", "challenge"):
                saved_rows(root / ("api-" + phase + "-attempt-001"), root / "plan.json", [r for r in api if r["phase"] == phase])
            b.write_new(root / "forecast_lock.json", {"status": "abstain"})
            before = {str(path): b.digest(path) for path in root.rglob("*") if path.is_file()}
            diagnosed = d.diagnose(root)
            after = {str(path): b.digest(path) for path in root.rglob("*") if path.is_file()}
            self.assertEqual(before, after)
            self.assertEqual(diagnosed["analysis_tier"], "post_hoc_format_diagnostic_not_prospective")
            self.assertEqual(len(diagnosed["canonicalized_weak_feature_matches"]), 9)
            self.assertNotIn("predictions", diagnosed)
            counts = next(r for r in diagnosed["per_target_phase"] if r["target_id"] == "target-10" and r["phase"] == "challenge")
            self.assertEqual(counts["canonicalized_parseable"], 31)


if __name__ == "__main__":
    unittest.main()
