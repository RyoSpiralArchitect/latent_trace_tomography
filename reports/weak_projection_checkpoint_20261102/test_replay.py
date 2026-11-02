from pathlib import Path
import shutil
import tempfile
import unittest

import lexical as l
from records import DATA, parse, read, rows
from replay import observed, recover_lock, replay


class CheckpointTests(unittest.TestCase):
    def test_live_and_retrospective_denominators(self):
        r = replay()
        self.assertEqual(
            (r["twins"]["gpt2"]["controls_eligible"], r["twins"]["smollm2"]["splits"]), (0, 5)
        )
        self.assertEqual(
            r["twins"]["smollm2"]["both_codebooks_by_docket"],
            {"1": "FAIL->PASS", "2": "FAIL->PASS"},
        )
        for k in ("matched", "copy_far", "law"):
            self.assertEqual(r["api"]["methods"][k], {"singleton": 6, "singleton_hit": 6})
        self.assertEqual(r["api"]["methods"]["all_oss"], {"ambiguous": 6, "ambiguous_hit": 6})
        self.assertEqual(
            r["format_on_last_digit_panel"],
            dict(correct=48, requested_marker=24, raw_repeat_changes=10, slots=48),
        )
        h = r["historical"]
        self.assertEqual(
            [
                h[k]
                for k in (
                    "old_exact_hits",
                    "old_exact_scored",
                    "old_bracket_offers",
                    "conditional_offers",
                    "scored_M",
                    "conditional_hits",
                    "exact_support_hits",
                    "unconditional_offers",
                )
            ],
            [0, 2, 0, 6, 4, 3, 2, 0],
        )
        self.assertEqual(
            (h["mean_width_local"], h["mean_width_blind_same_units"]), (15 / 64, 41 / 64)
        )
        self.assertEqual(
            (h["collision_point_error_floor"], h["collision_width_floor"]), ("3/32", "3/16")
        )
        self.assertEqual(
            r["prior_interface_runs"]["bare_only_same_text"],
            {"code_equality": 17, "directed_path": 5},
        )

    def test_untrusted_public_bytes_fail_before_replay(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "data"
            shutil.copytree(DATA, p)
            with (p / "api_near.jsonl").open("a") as f:
                f.write("{}\n")
            with self.assertRaisesRegex(ValueError, "changed public file"):
                replay(p)

    def test_forecast_rejects_future_rows_and_missing_second_lineage(self):
        pl = l.build()
        answers = {r["qid"]: r["expected"] for r in pl}
        refs = {u: dict(answers) for u in l.UNITS}
        controls = {r["qid"]: r["expected"] for r in pl if r["phase"] == "controls"}
        with self.assertRaisesRegex(ValueError, "phase inventory"):
            l.bridge(pl, refs, answers)
        for u in l.PAIRS["smollm2"]:
            refs[u][next(iter(controls))] = "unresolved"
        pred = l.bridge(pl, refs, controls)
        self.assertEqual(pred["global_abstention"], "fewer_than_two_matching_lineages")
        self.assertTrue(all(v["matched"] == [] for v in pred["cases"].values()))

    def test_unstable_matched_reference_is_not_pruned(self):
        pl = l.build()
        a = {q["qid"]: q["expected"] for q in pl}
        ctl = {q["qid"]: q["expected"] for q in pl if q["phase"] == "controls"}
        refs = {u: a.copy() for u in l.UNITS}
        q = next(q for q in pl if q["phase"] == "near")
        refs[l.UNITS[0]][q["qid"]] = "?"
        pred = l.bridge(pl, refs, ctl)
        self.assertEqual(len(pred["matching_ids"]), 4)
        self.assertEqual(pred["cases"][q["cell"]]["matched"], [])

    def test_post_reveal_lock_and_added_telemetry_rejected(self):
        pl = l.build()
        ids = [q["qid"] for q in pl]
        refs = observed(rows(DATA / "oss.jsonl"), ids, True)
        ctl = rows(DATA / "api_controls.jsonl")
        order = [q["qid"] for q in pl if q["phase"] == "controls"]
        data = observed(ctl, order)
        ex = read(DATA / "execution.json")
        lock = read(DATA / "forecast_lock.json")
        lock["locked_at"] = ex["near"]["finished"]
        with self.assertRaisesRegex(ValueError, "pre-dispatch"):
            recover_lock(pl, refs, data, lock, ex)
        with self.assertRaisesRegex(ValueError, "visible text"):
            observed([{**ctl[0], "model": "x"}, *ctl[1:]], order)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            observed(ctl + [ctl[-1]], order)
        with self.assertRaises(ValueError):
            parse('{"a":1,"a":2}')


if __name__ == "__main__":
    unittest.main()
