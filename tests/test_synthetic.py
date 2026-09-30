from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from latent_trace_tomography.demo import run_synthetic_demo
from latent_trace_tomography.io import sha256_json
from latent_trace_tomography.schema import ProjectionKind, SyntheticRegime
from latent_trace_tomography.synthetic import SyntheticPhantom, generate_cases


class SyntheticPhantomTests(unittest.TestCase):
    def test_baseline_is_matched_but_diagnostic_projection_separates_routes(self) -> None:
        case = generate_cases(4, 7, prefix="test")[0]
        projections = {projection.kind: projection for projection in case.projections()}
        semantic = SyntheticPhantom(
            target_id="opaque-a",
            regime=SyntheticRegime.SEMANTIC_ROUTE,
            noise_rate=0.0,
            seed=1,
        )
        cue = SyntheticPhantom(
            target_id="opaque-b",
            regime=SyntheticRegime.SURFACE_CUE_ROUTE,
            noise_rate=0.0,
            seed=2,
        )

        self.assertEqual(
            semantic.complete(projections[ProjectionKind.BASELINE]),
            cue.complete(projections[ProjectionKind.BASELINE]),
        )
        self.assertNotEqual(
            semantic.complete(projections[ProjectionKind.CUE_MASK]),
            cue.complete(projections[ProjectionKind.CUE_MASK]),
        )
        self.assertNotEqual(
            semantic.complete(projections[ProjectionKind.CUE_FLIP]),
            cue.complete(projections[ProjectionKind.CUE_FLIP]),
        )

    def test_demo_is_text_only_reproducible_and_passes_gates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            summary = run_synthetic_demo(output, seed=11, cases=32, samples=3)
            self.assertTrue(summary["all_regression_gates_passed"])
            self.assertIn("same-process", summary["phase_sealing"])
            self.assertEqual(summary["decision_contrast_panel"]["accuracy"], 1.0)
            self.assertGreaterEqual(summary["prospective_heldout_challenges"]["accuracy"], 0.90)
            self.assertEqual(summary["reduced_orbit_nonidentifiability"]["coverage"], 0.0)

            rows = [
                json.loads(line)
                for line in (output / "observations.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            forbidden = {
                "regime",
                "intervention_id",
                "hidden_route",
                "logprobs",
                "latency_ms",
                "usage",
                "model_id",
            }
            self.assertTrue(rows)
            self.assertTrue(all(not (forbidden & row.keys()) for row in rows))
            self.assertTrue(all(row["projection_role"] == "observation" for row in rows))

            challenge_rows = [
                json.loads(line)
                for line in (output / "heldout_challenge_observations.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertTrue(challenge_rows)
            self.assertTrue(
                all(row["projection_role"] == "heldout_challenge" for row in challenge_rows)
            )

            phase_events = [
                json.loads(line)
                for line in (output / "phase_events.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                [event["event"] for event in phase_events],
                [
                    "contract_lint_passed",
                    "started",
                    "predictions_written",
                    "evaluation_key_opened",
                    "challenge_collected",
                    "completed",
                ],
            )
            prediction_payload = (output / "audit_predictions.jsonl").read_bytes()
            prediction_sha256 = hashlib.sha256(prediction_payload).hexdigest()
            self.assertEqual(phase_events[2]["audit_predictions_sha256"], prediction_sha256)
            self.assertEqual(phase_events[3]["locked_prediction_sha256"], prediction_sha256)

            run_config = json.loads((output / "run_config.json").read_text(encoding="utf-8"))
            preflight_result = json.loads(
                (output / "preflight_result.json").read_text(encoding="utf-8")
            )
            self.assertEqual(preflight_result["preflight_level"], "contract_lint")
            self.assertFalse(preflight_result["execution_ready"])
            self.assertEqual(
                preflight_result["protocol_path"],
                "protocols/synthetic_projection_orbit_v1/protocol.json",
            )
            hash_input = {
                key: value
                for key, value in run_config.items()
                if key not in {"config_sha256", "run_id"}
            }
            self.assertEqual(run_config["config_sha256"], sha256_json(hash_input))
            self.assertTrue(run_config["run_id"].endswith(run_config["config_sha256"][:16]))
            run_manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
            for key in (
                "protocol_sha256",
                "source_tree_sha256",
                "case_set_sha256",
                "projection_set_sha256",
                "split_manifest_sha256",
            ):
                self.assertRegex(run_manifest[key], r"^[0-9a-f]{64}$")
            self.assertEqual(run_manifest["python_runtime"], run_config["python_runtime"])
            self.assertIn(run_manifest["git_dirty"], {True, False, None})
            evaluation_manifest = json.loads(
                (output / "evaluation_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(evaluation_manifest["locked_prediction_sha256"], prediction_sha256)
            self.assertEqual(
                evaluation_manifest["plan_manifest_sha256"],
                hashlib.sha256((output / "plan_manifest.json").read_bytes()).hexdigest(),
            )
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["files"])
            for entry in manifest["files"]:
                payload = (output / entry["path"]).read_bytes()
                self.assertEqual(hashlib.sha256(payload).hexdigest(), entry["sha256"])

    def test_run_identity_changes_with_execution_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = run_synthetic_demo(root / "first", seed=17, cases=8, samples=1)
            second = run_synthetic_demo(root / "second", seed=17, cases=12, samples=1)
            self.assertNotEqual(first["config_sha256"], second["config_sha256"])
            self.assertNotEqual(first["run_id"], second["run_id"])

    def test_invalid_arguments_leave_no_output_or_staging_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "invalid"
            with self.assertRaises(ValueError):
                run_synthetic_demo(output, cases=3)
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".invalid.staging-*")), [])

    def test_publish_lock_rejects_a_concurrent_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "run"
            lock = root / ".run.publish.lock"
            lock.write_text("owner", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                run_synthetic_demo(output, seed=5, cases=8, samples=1)
            self.assertFalse(output.exists())
            self.assertEqual(lock.read_text(encoding="utf-8"), "owner")

    def test_existing_run_directory_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            run_synthetic_demo(output, seed=5, cases=16, samples=3)
            with self.assertRaises(FileExistsError):
                run_synthetic_demo(output, seed=5, cases=16, samples=3)


if __name__ == "__main__":
    unittest.main()
