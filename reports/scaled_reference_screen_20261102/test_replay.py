import copy
import unittest
import common as s
import replay


class ScreenReplayTests(unittest.TestCase):
    def test_archived_witness_is_not_a_weak_only_prediction(self):
        r = replay.run()
        self.assertEqual(len(r["weak_matches"]), 6)
        self.assertEqual(r["joint_matches"], ["mistral-7b-instruct-v0.3"])
        self.assertEqual(r["joint_unknown"], ["smollm2-1.7b-base"])
        self.assertEqual(r["B_conflict_predictions"], {"both_hit": 12})

    def test_missing_repeat_is_not_an_exclusion_or_a_hit(self):
        t = {"w": {"state": "stable", "answer": "A"}}
        v = {"w": {"state": "unresolved", "answer": None}}
        self.assertEqual(s.compare(t, v, ["w"])["verdict"], "UNKNOWN")

    def test_changed_prompt_or_missing_row_is_rejected(self):
        a = s.read(replay.ROOT / "data/observations.json")["A"]
        for defect in ("prompt", "row"):
            bad = copy.deepcopy(a)
            if defect == "prompt":
                bad["panel"][0]["prompt_text"] += "x"
            else:
                bad["tracks"]["target"].pop()
            with self.assertRaises(ValueError):
                replay.read_panel("A", bad, set(a["tracks"]), set(a["measured"]))
