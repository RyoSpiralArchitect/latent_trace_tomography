"""One reviewed checkpoint only: exact-byte input pins plus allowlisted output."""

import argparse
import json
from pathlib import Path

from replay import V2_SHA, calculate, check, digest, r, read, records, write_new

API_PINS = {
    "plan.json": "8ac9218fcca0382d0d8490cd174bfe03cccaa6a25c6dcdbb5bbba93621ba2832",
    "commitment.json": "1f38e538b56ec3224da34c702f352affb9f0ccadcc2e4687843d10ec8b9a878b",
    "evaluation.json": "85d8a99d428f733f068be56de9a7ef96cd9cc3fe553fe8fe7607510be49f9c81",
    "posthoc_diagnostics.json": "3c46726b15b58e0801cb34c47c4d0584626d3cb20d16dab47b1706ac74f6dc5a",
    "api-weak-attempt-001/attempt_receipt.json": "2ba52d2375c0b327136e2db6eec9edfc55024ba6925d466f09060e4907c05004",
    "api-challenge-attempt-001/attempt_receipt.json": "7b35fd1a38a97f354d039f9f9231de5ee83b9f354865d9e0070be68a29d5c179",
    "api-challenge.claim.json": "e81068d97517fc241971239004d3d9dc798533619bd7391c72f12ddafe0449e1",
}
REFERENCE_PINS = {
    "plan.json": "8ba8eb101aec7ea4b355efbb3a5f7bc5c561e1806bba8350bfd9bfecf084ab1b",
    "furnace-attempt-001/attempt_receipt.json": "b8f2f1b3832caf9095515a082891686b1fd41b3f8af20cd631eeb07448e728fb",
}
QUERY_FIELDS = {
    "query_id",
    "phase",
    "content",
    "cell",
    "case_id",
    "replicate_id",
    "projection_id",
    "prompt_text",
    "prompt_sha256",
}


def pinned(root, pins):
    for name, expected in pins.items():
        check(digest(root / name) == expected, "unreviewed retained input: " + name)


def verified_rows(root, stage, api=False):
    directory = root / (stage + "-attempt-001")
    receipt = read(directory / "attempt_receipt.json")
    check(receipt["status"] == "complete" and receipt["error"] is None, "incomplete receipt")
    check(set(receipt["artifacts"]) == {"results.jsonl", "events.jsonl"}, "unexpected artifacts")
    for name, expected in receipt["artifacts"].items():
        check(digest(directory / name) == expected, "retained artifact changed")
    previous, field = "0" * 64, "sha256" if api else "event_sha256"
    events = records(directory / "events.jsonl")
    for i, event in enumerate(events):
        check(
            event["sequence"] == i
            and event["previous_sha256"] == previous
            and event[field] == r._hash({k: v for k, v in event.items() if k != field}),
            "broken chain",
        )
        previous = event[field]
    result = records(directory / "results.jsonl")
    if api:
        check(
            len(result) == receipt["attempted_requests"] == receipt["completed_requests"],
            "API counts",
        )
    else:
        check(receipt["counts"]["logical_trials_completed"] == len(result) == 1008, "OSS counts")
        check(
            receipt["event_chain"] == {"event_count": len(events), "final_event_sha256": previous},
            "OSS chain binding",
        )
    return result, receipt


def export(api_root, reference_root, output):
    pinned(api_root, API_PINS)
    pinned(reference_root, REFERENCE_PINS)
    plan, original = read(api_root / "plan.json"), read(api_root / "evaluation.json")
    reference_plan, committed = (
        read(reference_root / "plan.json"),
        read(api_root / "commitment.json"),
    )
    check(plan["panel"] == reference_plan["panel"], "panels differ")
    check(all(set(q) == QUERY_FIELDS for q in plan["panel"]), "unexpected panel fields")
    reference, furnace = verified_rows(reference_root, "furnace")
    weak, weak_receipt = verified_rows(api_root, "api-weak", True)
    challenge, challenge_receipt = verified_rows(api_root, "api-challenge", True)
    observations = []
    for row in reference + weak + challenge:
        obs = row["observation"]
        check(set(obs) == r.TEXT_FIELDS, "extra observation fields")
        observations.append(obs)
    inventory = {
        "schema_version": "ltt_mistral_public_inventory_v1",
        "panel": plan["panel"],
        "api_target_id": plan["api_target_id"],
        "api_model": plan["model"],
        "request_settings": plan["request_settings"],
        "reference_clusters": committed["bundle"]["reference_clusters"],
    }
    analysis = calculate(inventory, observations)
    check(
        analysis["reference_report"] == committed["report"]
        and analysis["unconditional_baseline"] == committed["unconditional_baseline"],
        "retained forecast differs",
    )
    for key in ("conditional", "unconditional_baseline"):
        check(analysis["primary"][key] == original[key], "retained score differs")
    diagnostic = read(api_root / "posthoc_diagnostics.json")
    for key in ("task_oracle", "task_errors"):
        check(analysis["posthoc"][key] == diagnostic[key], "retained diagnostic differs")
    forecast = {
        "schema_version": "ltt_mistral_public_forecast_v1",
        "created_at": committed["created_at"],
        "retained_commitment_sha256": API_PINS["commitment.json"],
        "reference_report": analysis["reference_report"],
        "unconditional_baseline": analysis["unconditional_baseline"],
    }
    claim = read(api_root / "api-challenge.claim.json")
    execution = {
        "schema_version": "ltt_mistral_public_execution_v1",
        "model": plan["model"],
        "generation_requests": original["api_totals"]["completed_requests"],
        "metadata_gets": 1,
        "automatic_retries": 0,
        "usage": original["usage"],
        "pricing": plan["pricing"],
        "estimated_uncached_cost_usd": original["api_totals"]["estimated_uncached_cost_usd"],
        "reserved_cost_ceiling_usd": plan["limits"]["reserved_ceiling_usd"],
        "money_cap_usd": plan["limits"]["money_cap_usd"],
        "api_wall_seconds": {
            "weak": weak_receipt["wall_seconds"],
            "challenge": challenge_receipt["wall_seconds"],
        },
        "reference_counts": furnace["counts"],
        "reference_wall_seconds": furnace["wall_seconds"],
        "times": {
            "weak_completed": weak_receipt["completed_at"],
            "challenge_claimed": claim["created_at"],
            "challenge_started": challenge_receipt["started_at"],
            "challenge_completed": challenge_receipt["completed_at"],
        },
        "attestation_limit": "self-recorded local evidence; not independent execution attestation",
    }
    output.mkdir(mode=0o700)
    for name, value in {
        "inventory.json": inventory,
        "forecast.json": forecast,
        "execution.json": execution,
        "analysis.json": analysis,
    }.items():
        write_new(output / name, value)
    with (output / "observations.jsonl").open("x") as stream:
        for row in observations:
            stream.write(
                json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
            )
    write_new(
        output / "manifest.json",
        {
            "schema_version": "ltt_mistral_public_checkpoint_v1",
            "v2_sha256": V2_SHA,
            "published_files": {p.name: digest(p) for p in sorted(output.iterdir())},
            "retained_input_sha256": {"api": API_PINS, "reference": REFERENCE_PINS},
            "export_policy": "pinned allowlist; six-field synthetic observations, no credentials, host paths, response IDs, tensor/token telemetry",
            "evidence_tier": "prospective_engineering_pilot_not_causal_validation",
            "scope": "derived public projection, not rewritten original receipts",
            "new_model_calls": 0,
        },
    )
    print(
        json.dumps({"status": "exported", "observations": len(observations), "new_model_calls": 0})
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-root", type=Path, required=True)
    parser.add_argument("--reference-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.api_root, args.reference_root, args.output)
