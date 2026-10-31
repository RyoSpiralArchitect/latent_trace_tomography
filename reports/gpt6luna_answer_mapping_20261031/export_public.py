"""Export only the reviewed retained run, with exact input pins and explicit fields."""

import argparse
from collections import Counter
from pathlib import Path

import replay as p

PINS = {
    "plan.json": "b9feb7e5fc88ff448160ad7cded1987afadb43fa0d486ce41c71bddc988bb1fc",
    "run.py": "6968dbd775c245e897e00faeb26f1b4eafc9fa51c7a62e4d8f2c0df8e0381659",
    "test_run.py": "a7a855f33d184c757ac1547061c0b4cd9411c4f8bc7f7583edc39900a10c4878",
    "metadata_receipt.json": "68318dc41601340b665f4627bfec55f15346623afc8296b6209e4e6c249421f9",
    "analysis.json": "ee9b1de0d0bdd4eb2130e617847355885d0fa3d2f3bae771564be3dd2a7356a5",
    "execution_summary.json": "255d194fc743b19e8455e55b4936b4467bd3aeda53a9e6359c993683e2c9d3e9",
    "live_claim.json": "cfc083420e136f71af78c9a5daaf45c5f6f4f700b76043f2d6433777c7803a1a",
    "attempt-001/attempt_receipt.json": "a2a9909614da307ce95a32b0610382f7985cd261e7e7d5ebfb874a85b5ac908d",
    "attempt-001/results.jsonl": "82d985d865050c06dd8c6a9df95e3480450140636f7904e6b5715b8d65ef1ded",
    "attempt-001/events.jsonl": "77cc9a96f19428c1761ecc87ae0b8305b0b5ddf2e5bf0ac68d943826d663f40a",
}


def export(root, output):
    for name, expected in PINS.items():
        p.check(p.digest(root / name) == expected, "unreviewed retained input: " + name)
    plan, original = p.read(root / "plan.json"), p.read(root / "analysis.json")
    summary = p.read(root / "execution_summary.json")
    receipt = p.read(root / "attempt-001/attempt_receipt.json")
    claim, metadata = p.read(root / "live_claim.json"), p.read(root / "metadata_receipt.json")
    p.check(claim["plan_sha256"] == PINS["plan.json"], "claim binding")
    p.check(receipt["plan_sha256"] == p.sha(plan), "canonical plan binding")
    p.check(
        plan["script_sha256"] == PINS["run.py"] and plan["tests_sha256"] == PINS["test_run.py"],
        "runtime binding",
    )
    p.check(plan["metadata_receipt_sha256"] == PINS["metadata_receipt.json"], "metadata binding")
    p.check(plan["requests"] == p.parent().request_rows(), "panel changed")
    p.check(plan["scoring_key_sha256"] == p.sha(p.parent().scoring_key()), "scorer changed")
    bodies = [{**plan["request_settings"], "input": q["prompt_text"]} for q in plan["requests"]]
    p.check(plan["request_bodies_sha256"] == p.sha(bodies), "request body binding")
    p.check(
        receipt["mode"] == "live" and receipt["status"] == "complete" and receipt["error"] is None,
        "incomplete run",
    )
    p.check(
        metadata["status"] == "available"
        and metadata["http_status"] == 200
        and metadata["model_id_matches"] is True,
        "model availability",
    )
    p.check(
        metadata["model_requested"] == p.MODEL and metadata["generation_requests"] == 0,
        "metadata scope",
    )
    for name, expected in receipt["artifacts"].items():
        p.check(name in ("events.jsonl", "results.jsonl"), "artifact scope")
        p.check(p.digest(root / "attempt-001" / name) == expected, "receipt artifact binding")
    rows, events = (
        p.records(root / "attempt-001/results.jsonl"),
        p.records(root / "attempt-001/events.jsonl"),
    )
    p.check(
        len(rows)
        == receipt["attempted_requests"]
        == receipt["received_responses"]
        == receipt["completed_requests"]
        == 112,
        "request count",
    )
    p.check(
        receipt["retries"] == receipt["unresolved_request_outcomes"] == 0, "retry/outcome boundary"
    )
    previous = "0" * 64
    for i, event in enumerate(events):
        p.check(event["sequence"] == i and event["previous_sha256"] == previous, "event order")
        p.check(
            event["sha256"] == p.sha({k: v for k, v in event.items() if k != "sha256"}),
            "event hash",
        )
        previous = event["sha256"]
    p.check(
        receipt["event_chain"] == {"events": len(events), "final_sha256": previous}, "chain closure"
    )
    p.check(
        len(events) == 337
        and events[-1]["event"] == "completed"
        and events[-1]["payload"] == {"completed": 112},
        "terminal event",
    )
    usage, statuses, observations = Counter(), Counter(), []
    for i, (row, query, body) in enumerate(zip(rows, plan["requests"], bodies)):
        obs, audit = row["observation"], row["telemetry"]
        p.check(set(obs) == {"query_id", "output_text"}, "extra observation fields")
        p.check(
            obs["query_id"] == query["query_id"] and type(obs["output_text"]) is str,
            "observation binding",
        )
        start, receive, record = events[3 * i : 3 * i + 3]
        p.check(
            [v["event"] for v in (start, receive, record)]
            == ["request_started", "response_received", "request_recorded"],
            "event phase",
        )
        p.check(
            all(v["payload"]["query_id"] == query["query_id"] for v in (start, receive, record)),
            "event query",
        )
        p.check(start["payload"]["body_sha256"] == p.sha(body), "event body")
        p.check(receive["payload"]["response_sha256"] == audit["response_sha256"], "response hash")
        p.check(record["payload"]["row_sha256"] == p.sha(row), "record binding")
        p.check(
            audit["model"] == p.MODEL and audit["status"] == "completed" and not audit["refusal"],
            "unexpected outcome",
        )
        p.check(audit["usage"]["reasoning_tokens"] in (None, 0), "reasoning telemetry")
        usage.update(
            {k: audit["usage"][k] for k in ("input_tokens", "output_tokens", "total_tokens")}
        )
        statuses.update([audit["status"]])
        observations.append(obs)
    p.check(dict(usage) == receipt["usage"] == original["usage"], "usage closure")
    analysis = p.calculate(observations)
    p.check(analysis["score"] == original["score"], "retained score differs")
    p.check(
        analysis["posthoc_repeat_format_readout"] == summary["posthoc_repeat_format_readout"],
        "retained format readout differs",
    )
    # Public output explicitly excludes private paths, environment and raw response metadata.
    execution = {
        "schema_version": "ltt_gpt6luna_public_execution_v1",
        "model": p.MODEL,
        "run_date_jst": "2026-10-31",
        "status": "complete",
        "attempted_requests": receipt["attempted_requests"],
        "completed_requests": receipt["completed_requests"],
        "metadata_gets": metadata["metadata_gets"],
        "automatic_retries": receipt["retries"],
        "wall_seconds": receipt["wall_seconds"],
        "request_settings": plan["request_settings"],
        "usage": dict(usage),
        "status_counts": dict(statuses),
        "refusals": original["refusals"],
        "historical_rates_per_million_usd": {
            "input": 0.10,
            "output": 0.50,
            "conservative_input": 0.25,
        },
        "price_checked_on_jst": plan["pricing"]["checked_on_jst"],
        "price_source": plan["pricing"]["source"],
        "estimated_uncached_cost_usd": original["estimated_uncached_cost_usd"],
        "conservative_cost_ceiling_usd": original["conservative_cost_ceiling_usd"],
        "money_cap_usd": plan["limits"]["money_cap_usd"],
        "attestation_limit": "Derived from self-recorded retained evidence; not independent provider attestation, an immutable model snapshot or an invoice.",
        "pre_output_amendment": "Explicitly authorized target and transport switch to gpt-6-luna; parent prompts, order and scorer unchanged. The parent design-only authorization is unchanged.",
    }
    p.verify_execution(execution)
    output.mkdir()
    for name, value in (("execution.json", execution), ("analysis.json", analysis)):
        p.write_new(output / name, value)
    with (output / "observations.jsonl").open("x") as stream:
        for row in observations:
            stream.write(p.canonical(row) + "\n")
    p.write_new(
        output / "manifest.json",
        {
            "schema_version": "ltt_gpt6luna_public_checkpoint_v1",
            "new_model_calls": 0,
            "parent_generator_sha256": p.PARENT_SHA,
            "published_files": {name: p.digest(output / name) for name in sorted(p.FILES)},
            "retained_input_sha256": PINS,
            "evidence_tier": "descriptive_behavioral_diagnostic_not_mechanistic_validation",
            "export_policy": "Exact-byte reviewed sources; explicit observation and aggregate-audit fields. No credentials, local paths, response IDs, live runner, private receipts or per-response telemetry.",
            "scope": "Derived public projection; originals retained unchanged. Hashes alone do not expose or independently attest private originals.",
        },
    )
    return p.verify(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(p.canonical(export(args.source, args.output)))
