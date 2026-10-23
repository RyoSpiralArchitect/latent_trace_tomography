"""Offline tests only: transport is mocked, no key or model is needed."""
from argparse import Namespace
from collections import Counter
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import bridge as b


def response(text="FINAL: A"):
    return {"model": b.MODEL, "id": "fixture-only", "status": "completed",
            "usage": {"input_tokens": 200, "output_tokens": 5, "total_tokens": 205},
            "output": [{"type": "message", "role": "assistant",
                        "content": [{"type": "output_text", "text": text}]}]}


def plan():
    return {"scope": b.SCOPE, "script_sha256": b.digest(b.__file__),
            "contract_sha256": b.digest(Path(b.__file__).with_name("README.md")),
            "panel": b.panel(), "api_model": b.MODEL, "api_target_id": "target-10",
            "api_price_cap_usd": b.PRICE_CAP, "api_reserved_ceiling_usd": b.API_N * b.RESERVATION,
            "targets": [{"target_id": f"target-{i+1:02d}", "base_model_unit_id": f"family-{i//3}"}
                        for i in range(9)]}


def weak_rows(target="target-10", text="FINAL: A"):
    return [b.observation(q, target, text) for q in b.panel() if q["phase"] == "weak"]


def saved_rows(root, p, records):
    root.mkdir()
    with (root / "results.jsonl").open("x") as stream:
        for row in records:
            stream.write(b.canonical(row) + "\n")
    b.write_new(root / "attempt_receipt.json", {"status": "complete", "plan_sha256": b.digest(p),
        "artifacts": {"results.jsonl": b.digest(root / "results.jsonl")}})


class BridgeTests(unittest.TestCase):
    def test_panel_counts_and_balancing(self):
        p = b.panel()
        self.assertEqual(Counter(q["phase"] for q in p), {"weak": 80, "challenge": 32})
        self.assertEqual(len({q["prompt_text"] for q in p}), 56)
        for q in p:
            semantic, cue, identity = b.CELLS[q["cell"]]
            self.assertEqual(semantic == cue, q["phase"] == "weak")
        self.assertEqual(b.OSS_N, 1008)

    def test_fixed_fresh_content(self):
        self.assertEqual(b.panel(), b.panel())
        self.assertNotEqual(b.content(0), b.content(1))
        self.assertNotEqual(b.content(0)["required"], b.content(0)["alternate"])
        self.assertTrue(all(q["prompt_text"].isascii() for q in b.panel()))

    def test_projected_content_is_preserved(self):
        for q in b.panel():
            c = b.content(q["content"])
            self.assertIn(c["required"], q["prompt_text"])
            self.assertIn(c["entity"], q["prompt_text"])
            if not b.CELLS[q["cell"]][0]:
                self.assertIn(c["alternate"], q["prompt_text"])
        attenuated = b.render(0, 0, "weak_cue_salience_attenuation")
        self.assertIn("faded lettering: p a s s", attenuated)
        table = b.render(0, 2, "challenge_table")
        self.assertIn("required_code | candidate_code", table)
        self.assertNotIn("mismatch", table.lower())

    def test_marker_rules(self):
        for text in ("FINAL: A", "reasoning\nFINAL: A\n", "  FINAL: A  "):
            self.assertEqual(b.marker(text), "A")
        for text in ("", "A", "FINAL: C", "FINAL: A\nFINAL: B", "FINAL: A\nafter"):
            self.assertEqual(b.marker(text), "parse_failure")

    def test_features_dimension_and_mass(self):
        f = b.features(weak_rows())
        self.assertEqual(len(f["counts"]), 51)
        self.assertEqual(f["denominator"], 16)
        for start in range(0, 15, 3):
            self.assertEqual(sum(f["counts"][start:start+3]), 16)
        for start in range(15, 51, 9):
            self.assertEqual(sum(f["counts"][start:start+9]), 16)

    def test_features_ignore_identity_and_style(self):
        self.assertEqual(b.features(weak_rows("opaque1")),
                         b.features(weak_rows("opaque2", "Some rationale\nFINAL: A")))

    def test_features_reject_telemetry_and_challenge(self):
        for field, value in (("model", "secret"), ("logprobs", [0.1]), ("latency", 1)):
            rows = weak_rows()
            rows[0][field] = value
            with self.assertRaises(ValueError):
                b.features(rows)
        rows = weak_rows()
        rows[0]["projection_id"] = "challenge_conflict"
        with self.assertRaises(ValueError):
            b.features(rows)

    def test_features_reject_incomplete_duplicate(self):
        with self.assertRaises(ValueError):
            b.features(weak_rows()[:-1])
        rows = weak_rows()
        rows[1] = copy.deepcopy(rows[0])
        with self.assertRaises(ValueError):
            b.features(rows)

    def test_request_budget_and_no_optional_observables(self):
        self.assertAlmostEqual(b.API_N * b.RESERVATION, 0.372736)
        self.assertLess(b.API_N * b.RESERVATION, 0.50)
        body = b.request_body(b.panel()[0])
        self.assertEqual(body["model"], b.MODEL)
        self.assertEqual(body["tools"], [])
        self.assertFalse(body["store"])
        self.assertFalse(body["stream"])
        self.assertNotIn("include", body)
        self.assertNotIn("logprobs", body)
        self.assertNotIn("previous_response_id", body)

    def test_extract_only_visible_text(self):
        r = response()
        r["output"][0]["content"][0]["logprobs"] = [{"token": "private"}]
        text, meta = b.decode_response(r)
        self.assertEqual(text, "FINAL: A")
        self.assertNotIn("private", b.canonical(meta))
        self.assertAlmostEqual(meta["estimated_uncached_cost_usd"], 0.000088)

    def test_refusal_and_incomplete_are_observations(self):
        r = response()
        r["status"] = "incomplete"
        r["output"][0]["content"] = [{"type": "refusal", "refusal": "Cannot answer"}]
        text, meta = b.decode_response(r)
        self.assertEqual(b.marker(text), "parse_failure")
        self.assertTrue(meta["refusal"])

    def test_reject_model_drift_and_tools(self):
        r = response()
        r["model"] = "different-model"
        with self.assertRaises(ValueError):
            b.decode_response(r)
        r = response()
        r["output"] = [{"type": "function_call"}]
        with self.assertRaises(ValueError):
            b.decode_response(r)

    def test_reject_bad_usage(self):
        for usage in ({}, {"input_tokens": 200, "output_tokens": 5, "total_tokens": 206},
                      {"input_tokens": 200, "output_tokens": 33, "total_tokens": 233},
                      {"input_tokens": True, "output_tokens": 5, "total_tokens": 6}):
            r = response()
            r["usage"] = usage
            with self.assertRaises(ValueError):
                b.decode_response(r)

    def test_transport_no_retry_redirect_or_error_body_leak(self):
        for status in (302, 401, 429, 500):
            connection = MagicMock()
            connection.getresponse.return_value.status = status
            connection.getresponse.return_value.read.return_value = b"PRIVATE_ERROR_BODY"
            with patch.object(b.http.client, "HTTPSConnection", return_value=connection):
                with self.assertRaises(b.SafeAPIError) as caught:
                    b.http_request(b.request_body(b.panel()[0]), "fixture-key")
            self.assertEqual(connection.request.call_count, 1)
            self.assertNotIn("PRIVATE", str(caught.exception))
            self.assertEqual(caught.exception.status, status)
            connection.close.assert_called_once()

    def test_exclusive_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "receipt.json"
            b.write_new(target, {"a": 1})
            with self.assertRaises(FileExistsError):
                b.write_new(target, {"a": 2})
            self.assertEqual(b.read(target), {"a": 1})

    def test_journal_chain(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "events.jsonl"
            journal = b.Journal(p)
            journal.add("a", {"b": 2})
            journal.add("c", {"d": 3})
            journal.close()
            previous = "0" * 64
            for i, row in enumerate(b.rows(p)):
                sha = row.pop("sha256")
                self.assertEqual(b.seal(row), sha)
                self.assertEqual(row["sequence"], i)
                self.assertEqual(row["previous_sha256"], previous)
                previous = sha

    def test_pinned_plan(self):
        p = plan()
        b.validate(p)
        p["panel"][0]["prompt_text"] += "changed"
        with self.assertRaises(ValueError):
            b.validate(p)

    def test_end_to_end_mock_forecast_chronology(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            root = Path(folder)
            p = root / "plan.json"
            b.write_new(p, plan())
            b.rehearse(Namespace(plan=p, output=root / "rehearsal.json"))
            env = {"OPENAI_API_KEY": "sk-test-fixture-not-a-real-key", "OPENAI_BASE_URL": ""}
            args = Namespace(plan=p, expected_plan_sha256=b.digest(p), execute=True,
                             phase="weak", output=root / "api-weak-attempt-001", lock=None, expected_lock_sha256=None)
            with patch.dict(b.os.environ, env), patch.object(b, "http_request", return_value=response()) as mocked:
                b.api(args)
                self.assertEqual(mocked.call_count, 80)
                with self.assertRaises(FileExistsError):
                    b.api(args)
                self.assertEqual(mocked.call_count, 80)
            reference = []
            for unit in plan()["targets"]:
                tid = unit["target_id"]
                for q in b.panel():
                    text = "FINAL: A" if tid in ("target-01", "target-02") else "unparseable"
                    if q["phase"] == "challenge" and tid == "target-02":
                        text = "FINAL: B"
                    reference.append({"phase": q["phase"], "query_id": q["query_id"], "observation": b.observation(q, tid, text)})
            saved_rows(root / "furnace-attempt-001", p, reference)
            lockpath = root / "forecast_lock.json"
            b.lock_forecast(Namespace(plan=p, furnace=root / "furnace-attempt-001", weak=args.output, output=lockpath))
            lock = b.read(lockpath)
            self.assertEqual(lock["support_targets"], ["target-01", "target-02"])
            self.assertEqual(lock["predictions"][0]["probabilities_A_B_failure"], [3/7, 3/7, 1/7])
            args.phase, args.output, args.lock = "challenge", root / "api-challenge-attempt-001", lockpath
            args.expected_lock_sha256 = b.digest(lockpath)
            with patch.dict(b.os.environ, env), patch.object(b, "http_request", return_value=response()) as mocked:
                b.api(args)
                self.assertEqual(mocked.call_count, 32)
            receipt = b.read(args.output / "attempt_receipt.json")
            self.assertEqual(receipt["lock_sha256"], b.digest(lockpath))
            self.assertLess(lock["created_at"], receipt["started_at"])
            with self.assertRaises(ValueError):
                b.lock_forecast(Namespace(plan=p, furnace=root / "furnace-attempt-001", weak=root / "api-weak-attempt-001", output=root / "new_lock.json"))

    def test_unknown_api_outcome_stops_without_retry(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            root = Path(folder)
            p = root / "plan.json"
            b.write_new(p, plan())
            b.rehearse(Namespace(plan=p, output=root / "rehearsal.json"))
            args = Namespace(plan=p, expected_plan_sha256=b.digest(p), execute=True,
                             phase="weak", output=root / "api-weak-attempt-001")
            with patch.dict(b.os.environ, {"OPENAI_API_KEY": "sk-test-fixture-not-a-real-key", "OPENAI_BASE_URL": ""}), \
                    patch.object(b, "http_request", side_effect=b.SafeAPIError("network_or_response_unknown")) as mocked:
                with self.assertRaises(SystemExit):
                    b.api(args)
            self.assertEqual(mocked.call_count, 1)
            receipt = b.read(args.output / "attempt_receipt.json")
            self.assertEqual(receipt["status"], "failed")
            self.assertEqual(receipt["attempted_requests"], 1)
            self.assertEqual(receipt["completed_requests"], 0)
            self.assertTrue(receipt["error"]["outcome_may_be_unknown"])
            self.assertEqual(receipt["reserved_cost_ceiling_usd"], b.RESERVATION)


if __name__ == "__main__":
    unittest.main()
