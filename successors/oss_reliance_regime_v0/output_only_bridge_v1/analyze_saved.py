"""Offline artifact audit and descriptive analysis. Never calls a model or API."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
from itertools import combinations
import math
from pathlib import Path

import bridge as b


def chain(path, hash_key):
    records = b.rows(path)
    previous = "0" * 64
    for index, source in enumerate(records):
        row = dict(source)
        seal = row.pop(hash_key)
        b.check(row["sequence"] == index and row["previous_sha256"] == previous
                and b.seal(row) == seal, "event chain mismatch")
        previous = seal
    return records, {"event_count": len(records), "final_event_sha256": previous}


def verify_observation(row, query, target):
    obs = row["observation"]
    b.check(set(obs) == b.FIELDS and type(obs["output_text"]) is str, "invalid public interface")
    b.check(obs == b.observation(query, target, obs["output_text"]), "observation differs from planned prompt")
    b.check(row["phase"] == query["phase"] and row["query_id"] == query["query_id"], "query identity mismatch")


def verify_furnace(root, plan, plan_sha):
    directory = root / "furnace-attempt-001"
    rows = b.checked_results(directory, plan_sha)
    receipt = b.read(directory / "attempt_receipt.json")
    events, report = chain(directory / "events.jsonl", "event_sha256")
    b.check(report == receipt["event_chain"], "Furnace event chain receipt differs")
    expected = [(unit, q) for unit in plan["targets"] for q in plan["panel"]]
    b.check(len(rows) == len(expected) == b.OSS_N, "reference inventory incomplete")
    finished = [e["payload"] for e in events if e["event"] == "trial_completed"]
    starts = [e["payload"]["job_id"] for e in events if e["event"] == "trial_started"]
    b.check(len(finished) == b.OSS_N and starts == [r["job_id"] for r in rows], "reference logical event inventory mismatch")
    physical = 0
    for row, (unit, query), end in zip(rows, expected, finished):
        verify_observation(row, query, unit["target_id"])
        b.check(row["job_id"] == unit["model_unit_id"] + ":" + query["query_id"], "job mismatch")
        b.check(end["job_id"] == row["job_id"] and end["result_sha256"] == b.seal(row), "result commitment mismatch")
        count = row["telemetry"]["physical_forward_calls"]
        b.check(1 <= count <= 16 and end["physical_forward_count"] == count, "forward count mismatch")
        physical += count
    begun = [e["payload"] for e in events if e["event"] == "forward_started"]
    ended = [e["payload"] for e in events if e["event"] == "forward_completed"]
    b.check(len(begun) == len(ended) == physical, "physical event count mismatch")
    b.check([r["reservation_id"] for r in begun] == list(range(physical))
            and [r["reservation_id"] for r in ended] == list(range(physical)), "physical reservation mismatch")
    b.check(events[-1]["event"] == "attempt_completed", "missing terminal reference event")
    b.check(receipt["counts"]["logical_trials_completed"] == b.OSS_N
            and receipt["counts"]["physical_forwards_started"] == receipt["counts"]["physical_forwards_completed"] == physical,
            "reference receipt count mismatch")
    return rows, {"logical_completions": len(rows), "physical_forwards": physical,
                  "wall_seconds": receipt["wall_seconds"], "event_chain": report,
                  "receipt_sha256": b.digest(directory / "attempt_receipt.json")}


def verify_api(root, phase, plan, plan_sha, lock_sha):
    directory = root / ("api-" + phase + "-attempt-001")
    rows = b.checked_results(directory, plan_sha)
    receipt = b.read(directory / "attempt_receipt.json")
    events, report = chain(directory / "events.jsonl", "sha256")
    queries = [q for q in plan["panel"] if q["phase"] == phase]
    b.check(len(rows) == len(queries) == receipt["attempted_requests"] == receipt["completed_requests"], "API inventory mismatch")
    b.check(receipt["lock_sha256"] == lock_sha, "API receipt lock mismatch")
    b.check([e["event"] for e in events] == ["phase_opened"] + [name for _ in queries for name in ("request_reserved", "response_saved")] + ["phase_closed"], "API event ordering mismatch")
    b.check(events[0]["payload"] == {"phase": phase, "plan_sha256": plan_sha, "lock_sha256": lock_sha}, "API event lock mismatch")
    usage, cost = Counter(), 0.0
    for row, query, reserve, saved in zip(rows, queries, events[1:-1:2], events[2:-1:2]):
        verify_observation(row, query, plan["api_target_id"])
        b.check(reserve["payload"] == {"query_id": query["query_id"], "request_sha256": b.seal(b.request_body(query)), "reserved_usd": b.RESERVATION}, "API request reservation changed")
        b.check(saved["payload"] == {"query_id": query["query_id"], "result_sha256": b.seal(row)}, "API response commitment changed")
        meta = row["telemetry"]
        b.check(meta["model"] == b.MODEL and meta["status"] in ("completed", "incomplete"), "API runtime identity changed")
        tokens = meta["usage"]
        b.check(tokens["total_tokens"] == tokens["input_tokens"] + tokens["output_tokens"]
                and 0 <= tokens["input_tokens"] <= b.INPUT_BOUND and 0 <= tokens["output_tokens"] <= b.OUTPUT_CAP, "API usage invalid")
        calculated = tokens["input_tokens"] * b.INPUT_RATE + tokens["output_tokens"] * b.OUTPUT_RATE
        b.check(math.isclose(calculated, meta["estimated_uncached_cost_usd"], abs_tol=1e-12), "API cost mismatch")
        usage.update(tokens)
        cost += calculated
    b.check(dict(usage) == receipt["usage"] and math.isclose(cost, receipt["estimated_uncached_cost_usd"], abs_tol=1e-12), "API usage/cost receipt mismatch")
    b.check(events[-1]["payload"] == {"attempted": len(rows), "completed": len(rows), "error": None}, "API terminal mismatch")
    b.check(math.isclose(receipt["reserved_cost_ceiling_usd"], len(rows) * b.RESERVATION, abs_tol=1e-12), "API reservation receipt mismatch")
    return rows, {"requests": len(rows), "usage": dict(usage), "estimated_uncached_cost_usd": cost,
                  "reserved_ceiling_usd": receipt["reserved_cost_ceiling_usd"], "wall_seconds": receipt["wall_seconds"],
                  "event_chain": report, "receipt_sha256": b.digest(directory / "attempt_receipt.json")}


def replay_forecast(plan, reference, weak):
    feature = b.features([r["observation"] for r in weak])
    reference_features = {u["target_id"]: b.features([r["observation"] for r in reference
                          if r["phase"] == "weak" and r["observation"]["target_id"] == u["target_id"]]) for u in plan["targets"]}
    support = [u for u in plan["targets"] if reference_features[u["target_id"]] == feature]
    predictions = []
    for query in (q for q in plan["panel"] if q["phase"] == "challenge"):
        by_family = defaultdict(Counter)
        for row in reference:
            units = [u for u in support if u["target_id"] == row["observation"]["target_id"]]
            if units and row["query_id"].rsplit(":r", 1)[0] == query["query_id"].rsplit(":r", 1)[0]:
                by_family[units[0]["base_model_unit_id"]][b.marker(row["observation"]["output_text"])] += 1
        probabilities = None
        if support:
            probabilities = [sum((counts[state] + 1) / (sum(counts.values()) + 3) for counts in by_family.values()) / len(by_family) for state in b.STATES]
        predictions.append({"query_id": query["query_id"], "probabilities_A_B_failure": probabilities})
    return {"api_feature": feature, "reference_features": reference_features,
            "support_targets": [u["target_id"] for u in support], "predictions": predictions,
            "status": "behavior_only_forecast" if support else "abstain_outside_exact_reference_support"}


def expected_marker(decision, identity):
    return "A" if decision == identity else "B"


def describe(plan, rows, lock):
    panel = {q["query_id"]: q for q in plan["panel"]}
    grouped, repeats, weak_orbits = defaultdict(Counter), defaultdict(dict), defaultdict(dict)
    for row in rows:
        q, o = panel[row["query_id"]], row["observation"]
        semantic, cue, identity = b.CELLS[q["cell"]]
        state = b.marker(o["output_text"])
        group = grouped[(o["target_id"], o["projection_id"])]
        group["n"] += 1
        group["parseable"] += int(state != "parse_failure")
        group["semantic_consistent"] += int(state == expected_marker(semantic, identity))
        group["cue_consistent"] += int(state == expected_marker(cue, identity))
        group["mixed_and_consistent"] += int(state == expected_marker(semantic and cue, identity))
        group[state] += 1
        repeats[(o["target_id"], row["query_id"].rsplit(":r", 1)[0])][o["replicate_id"]] = o["output_text"]
        if q["phase"] == "weak":
            weak_orbits[o["target_id"]][row["query_id"]] = o["output_text"]
    repeat_counts = defaultdict(Counter)
    for (target, _), pair in repeats.items():
        b.check(set(pair) == {"r0", "r1"}, "repeat pairing incomplete")
        repeat_counts[target]["pairs"] += 1
        repeat_counts[target]["raw_equal"] += int(pair["r0"] == pair["r1"])
        repeat_counts[target]["parsed_equal"] += int(b.marker(pair["r0"]) == b.marker(pair["r1"]))
    features = {**lock["reference_features"], plan["api_target_id"]: lock["api_feature"]}
    feature_groups = defaultdict(list)
    for target, values in features.items():
        feature_groups[b.seal(values)].append(target)
    pairwise = []
    for first, second in combinations(sorted(weak_orbits), 2):
        a, z = weak_orbits[first], weak_orbits[second]
        b.check(set(a) == set(z), "weak query inventory mismatch")
        raw_equal = sum(a[key] == z[key] for key in a)
        parsed_equal = sum(b.marker(a[key]) == b.marker(z[key]) for key in a)
        if features[first] == features[second] or raw_equal == 80:
            pairwise.append({"targets": [first, second], "feature_equal": features[first] == features[second],
                             "weak_raw_equal": raw_equal, "weak_parsed_equal": parsed_equal, "n": 80})
    predicted = {p["query_id"]: p["probabilities_A_B_failure"] for p in lock["predictions"]}
    actual = [r for r in rows if r["phase"] == "challenge" and r["observation"]["target_id"] == plan["api_target_id"]]
    losses = []
    for row in actual:
        probabilities = predicted[row["query_id"]]
        if probabilities is not None:
            observed = b.STATES.index(b.marker(row["observation"]["output_text"]))
            losses.append({"query_id": row["query_id"], "observed": b.STATES[observed],
                           "probabilities_A_B_failure": probabilities,
                           "log_loss_nats": -math.log(probabilities[observed]),
                           "brier_sum_3class": sum((p - int(i == observed))**2 for i, p in enumerate(probabilities))})
    score = {"predicted": len(losses), "challenge_n": len(actual), "coverage": len(losses) / len(actual),
             "mean_log_loss_nats": sum(r["log_loss_nats"] for r in losses)/len(losses) if losses else None,
             "mean_brier_sum_3class": sum(r["brier_sum_3class"] for r in losses)/len(losses) if losses else None,
             "uniform_3class_log_loss_nats": math.log(3), "uniform_3class_brier_sum": 2/3}
    return {"per_projection": [{"target_id": target, "projection_id": role, **dict(counts)}
                               for (target, role), counts in sorted(grouped.items())],
            "repeatability": dict(repeat_counts), "feature_equivalence_groups": list(feature_groups.values()),
            "matching_pair_checks": pairwise, "locked_forecast_score": score, "query_scores": losses}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root, args.output
    plan = b.read(root / "plan.json")
    b.validate(plan)
    plan_sha = b.digest(root / "plan.json")
    reference, reference_audit = verify_furnace(root, plan, plan_sha)
    weak, weak_audit = verify_api(root, "weak", plan, plan_sha, None)
    lock = b.read(root / "forecast_lock.json")
    lock_sha = b.digest(root / "forecast_lock.json")
    b.check(lock["plan_sha256"] == plan_sha and lock["furnace_receipt_sha256"] == reference_audit["receipt_sha256"]
            and lock["weak_receipt_sha256"] == weak_audit["receipt_sha256"], "lock inputs changed")
    replay = replay_forecast(plan, reference, weak)
    for key, value in replay.items():
        b.check(lock[key] == value, "forecast replay mismatch: " + key)
    challenge, challenge_audit = verify_api(root, "challenge", plan, plan_sha, lock_sha)
    weak_receipt = b.read(root / "api-weak-attempt-001/attempt_receipt.json")
    challenge_receipt = b.read(root / "api-challenge-attempt-001/attempt_receipt.json")
    b.check(datetime.fromisoformat(weak_receipt["completed_at"]) < datetime.fromisoformat(lock["created_at"])
            < datetime.fromisoformat(challenge_receipt["started_at"]), "local forecast chronology invalid")
    total_cost = weak_audit["estimated_uncached_cost_usd"] + challenge_audit["estimated_uncached_cost_usd"]
    b.check(total_cost <= b.PRICE_CAP, "API budget exceeded")
    verification = {"status": "verified", "plan_sha256": plan_sha, "script_sha256": plan["script_sha256"],
                    "analysis_script_sha256": b.digest(__file__), "forecast_lock_sha256": lock_sha,
                    "furnace": reference_audit, "api_weak": weak_audit, "api_challenge": challenge_audit,
                    "api_total_requests": weak_audit["requests"] + challenge_audit["requests"],
                    "api_estimated_uncached_cost_usd": total_cost,
                    "forecast_replay": "exact", "local_chronology": "weak_complete < lock < challenge_started",
                    "new_model_calls": 0,
                    "limitations": ["self-recorded evidence, not independent execution attestation",
                                    "price estimate, not an invoice", "shared Furnace GPU; latency is not a comparison metric"]}
    analysis = describe(plan, reference + weak + challenge, lock)
    output.mkdir(mode=0o700)
    b.write_new(output / "verification.json", verification)
    b.write_new(output / "analysis.json", analysis)
    print(b.canonical({"verification": verification, "forecast_status": lock["status"],
                       "support_targets": lock["support_targets"], "feature_groups": analysis["feature_equivalence_groups"],
                       "score": analysis["locked_forecast_score"]}))


if __name__ == "__main__":
    main()
