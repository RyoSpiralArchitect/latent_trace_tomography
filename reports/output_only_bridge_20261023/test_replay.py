"""Public-data replay and corruption tests. No credentials or network."""

from pathlib import Path
import shutil
import tempfile
import unittest

import replay


class PublicReplayTests(unittest.TestCase):
    def test_retained_checkpoint(self):
        result = replay.replay(Path(__file__).with_name("data"))
        self.assertEqual(result["observations"], 1120)
        self.assertEqual(result["primary_status"], "abstain_outside_exact_reference_support")
        self.assertEqual(result["primary_coverage"], 0)
        self.assertEqual(result["posthoc_feature_matches"], ["target-01", "target-02", "target-08"])

    def test_corruption_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "data"
            shutil.copytree(Path(__file__).with_name("data"), target)
            with (target / "observations.jsonl").open("a") as stream:
                stream.write("{}\n")
            with self.assertRaises(ValueError):
                replay.replay(target)


if __name__ == "__main__":
    unittest.main()
