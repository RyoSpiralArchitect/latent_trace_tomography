import copy
import unittest

import replay as r


class Evidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prompts, cls.rows, cls.api, cls.context = r.load()
        cls.s = r.tally(cls.prompts, cls.rows, cls.api, cls.context)

    def test_inventory_and_historical_controls(self):
        self.assertEqual(self.s["generations"], {"cue": 960, "joint": 2688})
        self.assertEqual(self.s["forwards"], {"cue": 5760, "joint": 16128})
        self.assertEqual(self.s["self_shams"], {"cue": 288, "joint": 192})
        self.assertEqual(self.s["historical_exact_text"], {"base": 96, "T:none:S": 96})
        for u in r.MODELS:
            self.assertEqual(self.s["map_control"][u], {"S": 0, "N": 0, "T": 48})
        self.assertEqual(self.s["joint_semantic_mapped_pass"], 1344)

    def test_directional_output_change_not_donor_transfer_or_constant_symbol(self):
        dirs = self.s["cue_changes"]
        for law in r.SIGNS:
            self.assertEqual(dirs[f"cue/mixed/original/PASS/{law}"], {"S": 0, "N": 0, "T": 12})
            self.assertEqual(dirs[f"cue/semantic/original/PASS/{law}"], {"S": 0, "N": 0, "T": 0})
            self.assertEqual(dirs[f"joint/mixed/balanced/PASS/{law}"], {"S": 0, "N": 0, "T": 12})
        for panel, peak in (("original", 9), ("balanced", 10)):
            self.assertEqual(dirs[f"joint/mixed/{panel}/FAIL/PASS"]["T"], peak)
            self.assertEqual(dirs[f"joint/mixed/{panel}/FAIL/FAIL"]["T"], 0)
        self.assertEqual(dirs["joint/mixed/balanced/FAIL/PASS"]["N"], 1)

    def test_primary_not_rescued_by_historical_or_secondary_results(self):
        f = self.s["factorials"]
        bad = f["mixed/balanced/FAIL/context"]
        self.assertEqual(bad["n"], 12)
        self.assertEqual(set(bad["pass"].values()), {0})
        self.assertIs(bad["primary_gate"], False)
        good = f["mixed/balanced/PASS/context"]
        self.assertEqual(
            [good["pass"][x] for x in ("SS", "ST", "TS", "TT", "TN")], [0, 0, 10, 8, 9]
        )
        self.assertEqual(good["contrasts"], [-2, -2, 0, -1])
        self.assertEqual(good["paired_switches"], {"to_pass": 0, "to_fail": 2, "unchanged": 10})
        self.assertEqual(good["by_map"], {"identity": -1, "swap": -1})
        self.assertEqual(sum(v < 0 for v in good["by_docket"].values()), 2)
        self.assertIs(good["primary_gate"], False)
        for p, start, c, v in (("original", 9, 5, 3), ("balanced", 10, 8, 7)):
            for route, n in (("context", c), ("value", v), ("relay", start)):
                cell = f[f"mixed/{p}/PASS/{route}"]
                self.assertEqual((cell["pass"]["TS"], cell["pass"]["TT"]), (start, n))
            self.assertIsNone(f[f"mixed/{p}/PASS/relay"]["primary_gate"])

    def test_endpoint_format_not_decision_and_forecast_not_issued(self):
        data = self.s["luna_by_arm"].values()
        self.assertEqual(
            [sum(v[k] for v in data) for k in ("correct", "marker", "bare")], [96, 60, 36]
        )
        self.assertEqual(self.s["luna_changed_repeat_texts"], 16)
        ctx = self.context
        cell = ctx["coded_advisory"]["arms"]["coded_task"]
        self.assertEqual((cell["different"], cell["same"], cell["total"]), (7, 2, 24))
        self.assertFalse(ctx["coded_advisory"]["go"])
        self.assertEqual(ctx["coded_advisory"]["clean_coded_splits"], 0)
        witness = ctx["exact_witness"]
        self.assertEqual(witness["selection"]["IN"], ["unit-smollm2-surface"])
        self.assertEqual(
            [len(witness["selection"][k]) for k in ("IN", "OUT", "UNKNOWN")], [1, 9, 2]
        )
        self.assertEqual(
            witness["flip_counts"]["unit-smollm2-surface"],
            {"advisory": 48, "rule": 0, "unresolved": 0},
        )
        self.assertEqual(witness["issued"], {})
        self.assertIsNone(witness["endpoint_accuracy"])
        eleven = ctx["replication"]["eleven"]
        self.assertEqual(
            [eleven[k].get("matched", 0) for k in ("identity", "swap", "both")], [1, 0, 0]
        )

    def test_missing_or_duplicate_trial_is_not_a_null_result(self):
        for bad in (self.rows[:-1], self.rows + [self.rows[0]]):
            with self.subTest(length=len(bad)), self.assertRaises(ValueError):
                r.tally(self.prompts, bad, self.api, self.context)

    def test_decision_must_match_the_written_mapping_and_the_entire_response(self):
        for txt in ("FINAL: A then B", "A.", "", "pass"):
            with self.subTest(txt=txt), self.assertRaises(ValueError):
                r.decode(txt)
        bad = copy.deepcopy(self.prompts)
        k, txt = bad[0]
        bad[0] = [k, txt.replace("- PASS maps to FINAL: A", "- PASS maps to FINAL: B")]
        with self.assertRaises(ValueError):
            r.tally(bad, self.rows, self.api, self.context)


if __name__ == "__main__":
    unittest.main()
