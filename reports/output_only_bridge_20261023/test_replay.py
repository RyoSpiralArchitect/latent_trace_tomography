"""Public-data replay and corruption tests. No credentials or network."""

from pathlib import Path
import json
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

    def test_rehashed_structural_corruption_is_rejected(self):
        # A matching file hash is not enough: the public interface must also close.
        for corruption in ("extra_field", "missing_slot", "wrong_prompt"):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary) / "data"
                shutil.copytree(Path(__file__).with_name("data"), target)
                path = target / "observations.jsonl"
                rows = [json.loads(line) for line in path.read_text().splitlines()]
                if corruption == "extra_field":
                    rows[0]["usage"] = 1
                elif corruption == "missing_slot":
                    rows.pop()
                else:
                    rows[0]["prompt_text"] += " changed"
                path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
                manifest_path = target / "manifest.json"
                manifest = json.loads(manifest_path.read_text())
                manifest["published_files"][path.name] = replay.digest(path)
                manifest_path.write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):
                    replay.replay(target)


if __name__ == "__main__":
    unittest.main()
