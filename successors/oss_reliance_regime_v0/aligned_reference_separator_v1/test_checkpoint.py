import copy
import unittest

import checkpoint as c
import study as s
import study_io as io


class TrialMultiplicityTests(unittest.TestCase):
    def test_each_planned_id_has_one_ordered_start_and_matching_completion(self):
        start = {"event": "trial_started", "payload": {"job_id": "u/k"}}
        end = {"event": "trial_completed", "payload": {"job_id": "u/k", "result_sha256": "right"}}
        c.require_one_trial_per_id([start, end], {"u/k": "right"})
        for events in (
            [start, start, end],
            [start, end, end],
            [end, start],
            [start],
            [],
            [
                start,
                {
                    "event": "trial_completed",
                    "payload": {"job_id": "u/k", "result_sha256": "other"},
                },
                end,
            ],
            [{"event": "trial_started", "payload": {"job_id": "other"}}, start, end],
        ):
            with self.subTest(events=events), self.assertRaises(ValueError):
                c.require_one_trial_per_id(events, {"u/k": "right"})


class PublicCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.path = c.ROOT / "checkpoint.json"
        self.data = io.read(self.path)
        self.pin = io.digest(c.ROOT / "freeze.json")

    def test_replay_closes_actual_stage_prefix(self):
        self.assertEqual(io.digest(self.path), (c.ROOT / "checkpoint.sha256").read_text().strip())
        x = c.replay(self.data, self.pin)
        self.assertIn("development", x["stages"])
        self.assertEqual(x["new_endpoint_calls"], 0)
        self.assertGreaterEqual(x["generations"], 432)

    def test_reject_foreign_stage_and_substituted_output(self):
        for change in ("foreign", "symbol"):
            d = copy.deepcopy(self.data)
            if change == "foreign":
                d["stages"]["unexpected"] = {}
            else:
                tr = d["stages"]["development"]["observations"]
                tr[s.M] = ("A" if tr[s.M][0] != "A" else "B") + tr[s.M][1:]
            with self.assertRaises(ValueError):
                c.replay(d, self.pin)
