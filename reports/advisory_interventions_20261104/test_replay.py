import copy
import unittest

import next_design as proposal
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
            self.assertEqual(
                dirs[f"cue/mixed/original/cue6/PASS/{law}"]["toward_donor_advice"],
                {"S": 0, "N": 0, "T": 12},
            )
            self.assertEqual(
                dirs[f"cue/semantic/original/cue6/PASS/{law}"]["all_changes"],
                {"S": 0, "N": 0, "T": 0},
            )
            self.assertEqual(
                dirs[f"joint/mixed/balanced/cue6/PASS/{law}"]["all_changes"],
                {"S": 0, "N": 0, "T": 12},
            )
        for panel, peak in (("original", 9), ("balanced", 10)):
            self.assertEqual(dirs[f"joint/mixed/{panel}/cue6/FAIL/PASS"]["all_changes"]["T"], peak)
            self.assertEqual(dirs[f"joint/mixed/{panel}/cue6/FAIL/FAIL"]["all_changes"]["T"], 0)
        self.assertEqual(dirs["joint/mixed/balanced/cue6/FAIL/PASS"]["all_changes"]["N"], 1)
        self.assertEqual(
            dirs["cue/mixed/original/cue3/PASS/ALL"]["all_changes"], {"S": 0, "N": 0, "T": 24}
        )
        self.assertEqual(
            dirs["cue/mixed/original/cue3/FAIL/ALL"]["all_changes"], {"S": 0, "N": 1, "T": 12}
        )
        for layer in ("cue3", "cue6"):
            for sign in r.SIGNS:
                zero = dirs[f"cue/semantic/original/{layer}/{sign}/ALL"]
                self.assertEqual(zero["informative_pairs"], 0)
                self.assertIsNone(zero["conditional_donor_rate"]["T"])
                self.assertEqual(zero["all_changes"], dict.fromkeys("STN", 0))

    def test_wrong_way_move_counts_even_if_natural_donors_always_approve(self):
        bad = copy.deepcopy(self.rows)
        row = next(
            x for x in bad if x[:4] == ["cue", "semantic", "original/0/X/Y/identity/FAIL", "cue3:T"]
        )
        row[4] = "FINAL: B"
        v = r.tally(self.prompts, bad, self.api, self.context)["cue_changes"][
            "cue/semantic/original/cue3/FAIL/ALL"
        ]
        self.assertEqual(v["all_changes"]["T"], 1)
        self.assertEqual(v["toward_donor_advice"]["T"], 0)
        self.assertEqual(v["to_donor_on_informative"]["T"], 0)
        self.assertIsNone(v["conditional_donor_rate"]["T"])

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

    def test_reversed_written_law_and_duplicate_or_swapped_endpoint_presentations_rejected(self):
        texts = dict(self.prompts)
        wrong_law = [
            (k, v.replace(r.LAW_LINE, r.LAW_LINE.replace("equals", "differs from")))
            for k, v in self.prompts
        ]
        dup = [
            (
                k,
                texts[k.rsplit("/", 1)[0] + "/original"]
                if k.startswith("luna/") and k.endswith("/neutral")
                else v,
            )
            for k, v in self.prompts
        ]
        swapped = [
            (
                k,
                texts[
                    k.rsplit("/", 1)[0] + ("/ket_pass" if k.endswith("/vor_pass") else "/vor_pass")
                ]
                if k.startswith("luna/") and k.endswith(("/ket_pass", "/vor_pass"))
                else v,
            )
            for k, v in self.prompts
        ]
        for bad in (wrong_law, dup, swapped):
            with self.assertRaises(ValueError):
                r.tally(bad, self.rows, self.api, self.context)


class UnexecutedSpanProposal(unittest.TestCase):
    @staticmethod
    def grid(whole, last, cue, null):
        return {k: dict(zip(proposal.ARMS, (whole, cue, last, null))) for k in proposal.CELLS}

    def test_cue_ceiling_and_tied_endpoint_are_not_span_specific_recovery(self):
        for grid in (self.grid(1, 0, 1, 0), self.grid(1, 1, 0, 0), self.grid(1, 0, 0, 1)):
            out = proposal.assess(grid, controls_valid=True)
            self.assertEqual(out["status"], "NO_INCREMENT_DEMONSTRATED")
            self.assertEqual(out["approvals"]["cue_plus_span"], 12)

    def test_increment_requires_both_maps_and_four_common_dockets(self):
        grid = self.grid(1, 0, 0, 0)
        self.assertEqual(proposal.assess(grid, controls_valid=True)["status"], "ADVANCE_INCREMENT")
        for n in range(6):
            grid[n, "swap"]["cue_only"] = 1
        self.assertEqual(
            proposal.assess(grid, controls_valid=True)["status"], "NO_INCREMENT_DEMONSTRATED"
        )
        grid = self.grid(1, 0, 0, 0)
        for (n, _), v in grid.items():
            for i, a in enumerate(proposal.COMPARATORS):
                v[a] = int(n // 2 == i)
        self.assertEqual(proposal.assess(grid, controls_valid=True)["common_dockets"], [])
        self.assertEqual(
            proposal.assess(grid, controls_valid=True)["status"], "NO_INCREMENT_DEMONSTRATED"
        )

    def test_invalid_controls_or_missing_data_are_inconclusive(self):
        grid = self.grid(1, 0, 0, 0)
        self.assertEqual(proposal.assess(grid, controls_valid=False)["status"], "INCONCLUSIVE")
        del grid[0, "swap"]
        self.assertEqual(proposal.assess(grid, controls_valid=True)["status"], "INCONCLUSIVE")


if __name__ == "__main__":
    unittest.main()
