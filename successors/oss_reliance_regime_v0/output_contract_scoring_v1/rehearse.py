"""Exercise frozen output-contract scoring with synthetic replies, never a provider."""

import argparse
from collections import defaultdict, deque
import json
from pathlib import Path

import score as scoring

STOP_SLOT = 12  # One-based, deterministic, chosen only to test a partial outcome.
SCENARIOS = ("perfect", "mixed", "stopped")


def render(symbol, style):
    return "FINAL: " + symbol if style == "marker" else symbol


def _mock_script(requests, key, scenario):
    # This oracle is deliberately synthetic. The simulated transport takes prompt text only.
    by_id = {q["query_id"]: q for q in key}
    script = defaultdict(deque)
    for request in requests:
        q = by_id[request["query_id"]]
        symbol, style = q["expected_answer"], q["render_mode"]
        text = render(symbol, style)
        if scenario == "mixed":
            if q["replicate_id"] == "r0" and style == "marker":
                text = symbol  # Right answer, wrong format.
            elif q["replicate_id"] == "r1" and style == "bare":
                text = (
                    {"A": "B", "B": "A"}[symbol]
                    if q["response_mode"] == "standard"
                    else "undetermined"
                )  # Well-formed wrong answer or unresolved.
        script[request["prompt_text"]].append(text)
    return lambda prompt: script[prompt].popleft()


def _write_new(path, obj):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(obj, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def rehearse(out, scenario):
    scoring.check(scenario in SCENARIOS, "unknown mock scenario")
    requests, key, _, _ = scoring.frozen_inputs()
    reply = _mock_script(requests, key, scenario)
    out.mkdir()  # Never overwrite, reuse, or resume a run directory.
    path = out / "observations.jsonl"
    attempted = recorded = 0
    pending_id = None
    with path.open("x", encoding="utf-8") as stream:
        for request in requests:
            attempted += 1
            if scenario == "stopped" and attempted == STOP_SLOT:
                pending_id = request["query_id"]
                break  # Simulated unknown outcome after attempt; no response and no retry.
            row = {"query_id": request["query_id"], "output_text": reply(request["prompt_text"])}
            stream.write(json.dumps(row, sort_keys=True) + "\n")
            recorded += 1
    files = {path.name: scoring.digest(path)}
    if pending_id is None:
        score_path = out / "score.json"
        _write_new(
            score_path,
            {
                "observation_source": "synthetic_rehearsal_only",
                "scenario": scenario,
                "score": scoring.score(scoring.read_rows(path)),
            },
        )
        files[score_path.name] = scoring.digest(score_path)
    receipt = {
        "schema_version": "ltt_output_contract_rehearsal_v1",
        "evidence": "synthetic model-free rehearsal only; not endpoint behavior",
        "status": "mock_stopped_incomplete" if pending_id else "mock_complete",
        "scenario": scenario,
        "planned_slots": len(requests),
        "simulated_attempts": attempted,
        "recorded_rows": recorded,
        "unknown_outcome_query_id": pending_id,
        "stop_reason": "injected_unknown_outcome_no_response" if pending_id else None,
        "live_execution_authorized": False,
        "model_calls": 0,
        "automatic_retries": 0,
        "design_manifest_sha256": scoring.MANIFEST_SHA,
        "scorer_sha256": scoring.digest(Path(scoring.__file__)),
        "rehearsal_sha256": scoring.digest(Path(__file__)),
        "files_sha256": files,
    }
    _write_new(out / "receipt.json", receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    parser.add_argument("--out", type=Path, required=True, help="new output directory")
    args = parser.parse_args()
    try:
        receipt = rehearse(args.out, args.scenario)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"rehearsal not completed: {exc}\n")
    print(json.dumps(receipt, sort_keys=True))
    raise SystemExit(0 if receipt["status"] == "mock_complete" else 2)
