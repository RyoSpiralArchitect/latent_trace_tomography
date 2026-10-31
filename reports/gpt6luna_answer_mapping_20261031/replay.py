"""Replay saved output-only observations; no credentials, model loading or network."""

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PARENT = REPO / "successors/oss_reliance_regime_v0/answer_mapping_probe_v1"
PARENT_SHA = "e7a9cd3aa6aa5c78a6d53fe9274148c81323ab25c2de36deee76a18521cbbf5e"
FILES = {"observations.jsonl", "execution.json", "analysis.json"}
MODEL = "gpt-6-luna"


def check(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def unique(pairs):
    value = {}
    for key, item in pairs:
        check(key not in value, "duplicate JSON field")
        value[key] = item
    return value


def reject_constant(value):
    raise ValueError("non-finite JSON number")


def loads(text):
    return json.loads(text, object_pairs_hook=unique, parse_constant=reject_constant)


def read(path):
    return loads(Path(path).read_text())


def records(path):
    text = Path(path).read_text()
    check(text.endswith("\n"), "truncated records")
    return [loads(line) for line in text.splitlines()]


def write_new(path, value):
    with Path(path).open("x") as stream:
        stream.write(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")


def parent():
    check(digest(PARENT / "design.py") == PARENT_SHA, "frozen parent source changed")
    spec = importlib.util.spec_from_file_location("frozen_answer_mapping", PARENT / "design.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.verify(PARENT / "fixtures")
    return module


def calculate(observations):
    module = parent()
    score = module.score(observations)
    index = {row["query_id"]: row["output_text"] for row in observations}
    groups, pairs = defaultdict(Counter), defaultdict(list)
    for query in module.panel():
        text = index[query["query_id"]]
        answer, fmt = module.parse(text, query["response_mode"])
        groups[query["kind"] + "/" + query["response_mode"]].update(
            {
                "n": 1,
                "correct_under_frozen_parser": int(answer == query["expected_answer"]),
                "exact_marker": int(fmt == "exact_marker"),
                "bare_symbol": int(fmt == "bare_symbol"),
                "unresolved": int(fmt == "unresolved"),
            }
        )
        pairs[query["case_id"]].append((text, fmt))
    totals = Counter()
    for value in groups.values():
        totals.update(value)
    check(len(pairs) == 56 and all(len(v) == 2 for v in pairs.values()), "repeat inventory")
    return {
        "schema_version": "ltt_gpt6luna_public_analysis_v1",
        "score": score,
        "prespecified_format_secondary": {"by_condition": dict(groups), "totals": dict(totals)},
        "posthoc_repeat_format_readout": {
            "label": "additional descriptive readout; not a new prespecified endpoint",
            "pairs": 56,
            "raw_text_disagreements": sum(v[0][0] != v[1][0] for v in pairs.values()),
            "parsed_format_disagreements": sum(v[0][1] != v[1][1] for v in pairs.values()),
        },
        "prior_reference_result": "abstain_outside_reference_support_unchanged",
        "claim_ceiling": "small descriptive behavioral diagnostic; no internal-stage isolation, Mistral replication, calibrated mechanism attribution or cross-family generalization",
        "new_model_calls": 0,
    }


def verify_execution(execution):
    check(execution["model"] == MODEL and execution["status"] == "complete", "execution scope")
    check(execution["attempted_requests"] == execution["completed_requests"] == 112, "call count")
    check(execution["metadata_gets"] == 1 and execution["automatic_retries"] == 0, "extra calls")
    check(
        execution["status_counts"] == {"completed": 112} and execution["refusals"] == 0, "outcomes"
    )
    check(
        execution["request_settings"]
        == {
            "model": MODEL,
            "temperature": 0,
            "reasoning": {"effort": "none"},
            "max_output_tokens": 32,
            "store": False,
            "service_tier": "default",
            "tools": [],
            "stream": False,
            "truncation": "disabled",
        },
        "transport settings changed",
    )
    usage = execution["usage"]
    check(set(usage) == {"input_tokens", "output_tokens", "total_tokens"}, "usage fields")
    check(all(type(v) is int and v >= 0 for v in usage.values()), "usage values")
    check(usage["input_tokens"] + usage["output_tokens"] == usage["total_tokens"], "usage sum")
    prices = execution["historical_rates_per_million_usd"]
    check(prices == {"input": 0.10, "output": 0.50, "conservative_input": 0.25}, "rates changed")
    for field, rate in (
        ("estimated_uncached_cost_usd", 0.10),
        ("conservative_cost_ceiling_usd", 0.25),
    ):
        expected = (usage["input_tokens"] * rate + usage["output_tokens"] * 0.50) / 1_000_000
        check(abs(execution[field] - expected) < 1e-12, "cost accounting")
    check(0 < execution["wall_seconds"] < 945, "elapsed bound")
    check(execution["money_cap_usd"] == 0.50, "budget changed")


def verify(data):
    manifest = read(data / "manifest.json")
    check(manifest["schema_version"] == "ltt_gpt6luna_public_checkpoint_v1", "manifest scope")
    check(manifest["new_model_calls"] == 0, "replay call boundary")
    check(set(manifest["published_files"]) == FILES, "file inventory changed")
    check({p.name for p in data.iterdir()} == FILES | {"manifest.json"}, "unexpected data file")
    check(manifest["parent_generator_sha256"] == PARENT_SHA, "parent pin changed")
    for name, expected in manifest["published_files"].items():
        check(digest(data / name) == expected, "published artifact changed")
    execution = read(data / "execution.json")
    verify_execution(execution)
    observations = records(data / "observations.jsonl")
    result = calculate(observations)
    check(result == read(data / "analysis.json"), "analysis replay differs")
    return {
        "status": "public_replay_passed",
        "observations": len(observations),
        "contrasts": result["score"]["contrasts"],
        "totals": result["prespecified_format_secondary"]["totals"],
        "posthoc_repeat_format_readout": result["posthoc_repeat_format_readout"],
        "new_model_calls": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=HERE / "data")
    print(json.dumps(verify(parser.parse_args().data), sort_keys=True, indent=2))
