import copy
import unittest

import checkpoint as c
import study as s
import study_io as io


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
