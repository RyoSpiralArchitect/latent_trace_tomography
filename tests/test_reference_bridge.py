"""Output-only v2 tests. No provider credentials, models, or live calls."""

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

from latent_trace_tomography import reference_bridge as r

ROOT = Path(__file__).resolve().parents[1]


def slots(roles):
    return [
        {
            "case_id": case,
            "projection_id": role,
            "replicate_id": "r0",
            "prompt_text": case + "/" + role,
        }
        for case in ("case-0", "case-1")
        for role in roles
    ]


def observations(inventory, target, bare=False, reverse=False):
    result = []
    for slot in inventory:
        answer = "A" if (slot["case_id"] == "case-0") != reverse else "B"
        result.append(
            {**slot, "target_id": target, "output_text": answer if bare else "FINAL: " + answer}
        )
    return result


def bundle():
    weak, challenge = slots(r.WEAK_ROLES), slots(r.CHALLENGE_ROLES)
    return {
        "schema_version": "ltt_output_bridge_v2_inputs_v1",
        "weak_inventory": weak,
        "challenge_inventory": challenge,
        "target_weak": observations(weak, "target", bare=True),
        "reference_weak": {key: observations(weak, key) for key in ("ref1", "ref2")},
        "reference_challenge": {
            "ref1": observations(challenge, "ref1"),
            "ref2": observations(challenge, "ref2", reverse=True),
        },
        "reference_clusters": {"ref1": "cluster1", "ref2": "cluster2"},
    }


class ReferenceBridgeTests(unittest.TestCase):
    def test_content_and_format_are_separate(self):
        self.assertEqual(
            r.parse_channels(" \nFINAL: A\n"), {"answer": "A", "format": "exact_marker"}
        )
        self.assertEqual(r.parse_channels("A"), {"answer": "A", "format": "bare_symbol"})

    def test_ambiguous_or_extra_text_is_unresolved(self):
        for value in (
            "",
            "a",
            "FINAL: AB",
            "FINAL:A",
            "FINAL: A\nFINAL: B",
            "Maybe A",
            "Reason\nFINAL: A",
        ):
            with self.subTest(value=value):
                self.assertEqual(r.parse_channels(value), {"answer": None, "format": "unresolved"})

    def test_nonstring_is_rejected(self):
        with self.assertRaises(ValueError):
            r.parse_channels(None)

    def test_matching_ignores_format_but_preserves_counts(self):
        report = r.build_reference_report(bundle())
        self.assertEqual(report["support_targets"], ["ref1", "ref2"])
        self.assertEqual(
            report["target_channels"]["formats"],
            {"exact_marker": 0, "bare_symbol": 10, "unresolved": 0},
        )
        self.assertEqual(report["reference_channels"]["ref1"]["formats"]["exact_marker"], 10)
        self.assertEqual(report["evidence_tier"], "development_only_not_prospective_validation")

    def test_finite_reference_ambiguity_is_kept(self):
        report = r.build_reference_report(bundle())
        for item in report["challenge_envelope"]:
            self.assertEqual(item["observed_answer_set"], ["A", "B"])
            self.assertTrue(item["ambiguous_within_reference_set"])
            self.assertNotIn("probabilities", item)

    def test_content_match_is_case_aligned_not_aggregate(self):
        data = bundle()
        for key in data["reference_weak"]:
            data["reference_weak"][key] = observations(data["weak_inventory"], key, reverse=True)
        report = r.build_reference_report(data)
        self.assertEqual(report["status"], "abstain_outside_reference_support")
        self.assertEqual(report["support_targets"], [])
        self.assertTrue(
            all(item["observed_answer_set"] is None for item in report["challenge_envelope"])
        )

    def test_unresolved_target_abstains(self):
        data = bundle()
        data["target_weak"][0]["output_text"] = "FINAL: AB"
        report = r.build_reference_report(data)
        self.assertEqual(report["status"], "abstain_unresolved_target_answers")
        self.assertEqual(report["support_targets"], [])
        self.assertEqual(report["target_channels"]["unresolved_answers"], 1)

    def test_unresolved_reference_remains_in_accounting(self):
        data = bundle()
        data["reference_weak"]["ref1"][0]["output_text"] = "unknown"
        report = r.build_reference_report(data)
        self.assertEqual(report["reference_count"], 2)
        self.assertEqual(report["support_targets"], ["ref2"])
        self.assertEqual(
            report["reference_channels"]["ref1"]["excluded_reason"], "unresolved_reference_answers"
        )
        self.assertEqual(report["mechanism_attribution"], "not_attempted_even_for_single_match")

    def test_unresolved_challenge_is_not_dropped(self):
        data = bundle()
        data["reference_challenge"]["ref1"][0]["output_text"] = "FINAL: AB"
        report = r.build_reference_report(data)
        self.assertTrue(
            any("unresolved" in row["observed_answer_set"] for row in report["challenge_envelope"])
        )

    def test_reference_challenge_answers_cannot_select_support(self):
        data = bundle()
        before = r.build_reference_report(data)
        for rows in data["reference_challenge"].values():
            for row in rows:
                row["output_text"] = "FINAL: AB"
        after = r.build_reference_report(data)
        self.assertEqual(before["support_targets"], after["support_targets"])
        self.assertEqual(before["status"], after["status"])
        self.assertNotEqual(before["challenge_envelope"], after["challenge_envelope"])
        self.assertNotEqual(
            before["input_commitments"]["reference_challenge_sha256"],
            after["input_commitments"]["reference_challenge_sha256"],
        )

    def test_invalid_target_content_never_uses_a_matching_failure_reference(self):
        data = bundle()
        data["target_weak"][0]["output_text"] = "unknown"
        for rows in data["reference_weak"].values():
            rows[0]["output_text"] = "unknown"
        report = r.build_reference_report(data)
        self.assertEqual(report["status"], "abstain_unresolved_target_answers")
        self.assertEqual(report["support_targets"], [])
        self.assertTrue(
            all(row["observed_answer_set"] is None for row in report["challenge_envelope"])
        )

    def test_v2_full_response_contract_does_not_reinterpret_v1(self):
        script = ROOT / "successors/oss_reliance_regime_v0/output_only_bridge_v1/bridge.py"
        spec = importlib.util.spec_from_file_location("archived_v1_parser", script)
        archived = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(archived)
        raw = "Explanation\nFINAL: A"
        self.assertEqual(archived.marker(raw), "A")
        self.assertEqual(r.parse_channels(raw), {"answer": None, "format": "unresolved"})

    def test_raw_inputs_are_unchanged(self):
        data = bundle()
        before = copy.deepcopy(data)
        r.build_reference_report(data)
        self.assertEqual(data, before)

    def test_row_and_inventory_order_are_irrelevant(self):
        data = bundle()
        before = r.build_reference_report(data)
        for key in ("weak_inventory", "challenge_inventory", "target_weak"):
            data[key].reverse()
        for key in ("reference_weak", "reference_challenge"):
            for rows in data[key].values():
                rows.reverse()
        self.assertEqual(r.build_reference_report(data), before)

    def test_clusters_cannot_change_content_matches(self):
        data = bundle()
        before = r.build_reference_report(data)
        data["reference_clusters"] = {"ref1": "renamed", "ref2": "renamed"}
        after = r.build_reference_report(data)
        self.assertEqual(before["support_targets"], after["support_targets"])
        self.assertEqual(before["challenge_envelope"], after["challenge_envelope"])
        self.assertEqual(after["declared_reference_cluster_count"], 1)

    def test_target_challenges_and_extra_bundle_fields_are_rejected(self):
        for key in ("target_challenge", "provider", "model", "latency"):
            data = bundle()
            data[key] = []
            with self.assertRaises(ValueError):
                r.build_reference_report(data)

    def test_metadata_is_rejected_at_observation_boundary(self):
        for key in ("logprobs", "model", "usage", "activations"):
            data = bundle()
            data["target_weak"][0][key] = 1
            with self.assertRaises(ValueError):
                r.build_reference_report(data)

    def test_missing_observation_is_an_error_not_abstention(self):
        data = bundle()
        data["target_weak"].pop()
        with self.assertRaises(ValueError):
            r.build_reference_report(data)

    def test_duplicate_observation_is_rejected(self):
        data = bundle()
        data["target_weak"][1] = copy.deepcopy(data["target_weak"][0])
        with self.assertRaises(ValueError):
            r.build_reference_report(data)

    def test_incomplete_and_duplicate_inventory_are_rejected(self):
        for duplicate in (True, False):
            data = bundle()
            if duplicate:
                data["weak_inventory"][1] = data["weak_inventory"][0]
            else:
                data["weak_inventory"].pop()
            with self.assertRaises(ValueError):
                r.build_reference_report(data)

    def test_prompt_drift_is_rejected(self):
        data = bundle()
        data["reference_weak"]["ref1"][0]["prompt_text"] += " altered"
        with self.assertRaises(ValueError):
            r.build_reference_report(data)

    def test_wrong_phase_is_rejected(self):
        data = bundle()
        data["weak_inventory"][0]["projection_id"] = "challenge_conflict"
        with self.assertRaises(ValueError):
            r.build_reference_report(data)

    def test_target_cannot_be_its_own_reference(self):
        data = bundle()
        for row in data["target_weak"]:
            row["target_id"] = "ref1"
        with self.assertRaises(ValueError):
            r.build_reference_report(data)

    def test_reference_cohort_must_be_complete(self):
        data = bundle()
        del data["reference_challenge"]["ref2"]
        with self.assertRaises(ValueError):
            r.build_reference_report(data)

    def test_target_challenge_cannot_hide_under_reference_identity(self):
        data = bundle()
        data["reference_challenge"]["ref1"][0]["target_id"] = "target"
        with self.assertRaises(ValueError):
            r.build_reference_report(data)

    def test_cli_exclusive_output_and_duplicate_json_rejection(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            source, output = root / "bundle.json", root / "report.json"
            source.write_text(json.dumps(bundle()))
            self.assertEqual(r.main(["--bundle", str(source), "--out", str(output)]), 0)
            before = output.read_bytes()
            with self.assertRaises(FileExistsError):
                r.main(["--bundle", str(source), "--out", str(output)])
            self.assertEqual(output.read_bytes(), before)
            source.write_text('{"schema_version": 1, "schema_version": 2}')
            with self.assertRaises(ValueError):
                r.main(["--bundle", str(source), "--out", str(root / "unused.json")])

    def test_revealed_checkpoint_is_development_only_and_unchanged(self):
        script = (
            ROOT / "successors/oss_reliance_regime_v0/output_only_bridge_v2/development_demo.py"
        )
        spec = importlib.util.spec_from_file_location("reference_bridge_demo", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        data = ROOT / "reports/output_only_bridge_20261023/data"
        before = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in data.iterdir()
        }
        report = r.build_reference_report(module.development_bundle(data))
        self.assertEqual(report["support_targets"], ["target-01", "target-02", "target-08"])
        self.assertEqual(
            report["target_channels"]["formats"],
            {"exact_marker": 68, "bare_symbol": 12, "unresolved": 0},
        )
        self.assertEqual(report["evidence_tier"], "development_only_not_prospective_validation")
        self.assertEqual(
            before,
            {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in data.iterdir()},
        )
        original_lock = json.loads((data / "forecast_lock.json").read_text())
        self.assertEqual(original_lock["status"], "abstain_outside_exact_reference_support")


if __name__ == "__main__":
    unittest.main()
