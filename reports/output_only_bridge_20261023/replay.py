"""Reproduce the public checkpoint without credentials, network, or models (Python 3.12)."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

REPOSITORY = Path(__file__).resolve().parents[2]
ARCHIVE = REPOSITORY / "successors/oss_reliance_regime_v0/output_only_bridge_v1"
sys.path.insert(0, str(ARCHIVE))
import bridge as b  # noqa: E402
import analyze_saved as a  # noqa: E402


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(data):
    manifest = b.read(data / "manifest.json")
    b.check(manifest["format"] == "ltt_public_checkpoint_v1", "unknown export format")
    expected = {
        "inventory.json",
        "observations.jsonl",
        "forecast_lock.json",
        "analysis.json",
        "verification.json",
        "posthoc_format_diagnostic.json",
    }
    b.check(set(manifest["published_files"]) == expected, "public artifact inventory changed")
    for name, sha in manifest["published_files"].items():
        b.check(digest(data / name) == sha, "published artifact changed: " + name)
    b.check(
        set(manifest["archived_source_sha256"])
        == {
            "README.md",
            "bridge.py",
            "analyze_saved.py",
            "diagnose_format.py",
            "test_bridge.py",
            "test_analysis.py",
        },
        "source inventory changed",
    )
    for name, sha in manifest["archived_source_sha256"].items():
        b.check(digest(ARCHIVE / name) == sha, "archived source changed: " + name)
    plan = b.read(data / "inventory.json")
    b.validate(plan)
    observations = b.rows(data / "observations.jsonl")
    by_key = {(q["case_id"], q["projection_id"], q["replicate_id"]): q for q in plan["panel"]}
    targets = [u["target_id"] for u in plan["targets"]] + [plan["api_target_id"]]
    expected_keys = {(target, *key) for target in targets for key in by_key}
    actual_keys, records = set(), []
    for obs in observations:
        b.check(set(obs) == b.FIELDS, "observation contains non-public fields")
        key = (obs["case_id"], obs["projection_id"], obs["replicate_id"])
        full_key = (obs["target_id"], *key)
        b.check(
            full_key in expected_keys and full_key not in actual_keys,
            "unexpected or duplicate observation",
        )
        q = by_key[key]
        b.check(
            obs["prompt_text"] == q["prompt_text"] and type(obs["output_text"]) is str,
            "prompt/output mismatch",
        )
        records.append({"query_id": q["query_id"], "phase": q["phase"], "observation": obs})
        actual_keys.add(full_key)
    b.check(actual_keys == expected_keys, "public inventory incomplete")
    return manifest, plan, records


def replay(data):
    manifest, plan, records = load(data)
    lock = b.read(data / "forecast_lock.json")
    b.check(lock["plan_sha256"] == manifest["retained_plan_sha256"], "wrong retained lock")
    reference = [r for r in records if r["observation"]["target_id"] != plan["api_target_id"]]
    weak = [
        r
        for r in records
        if r["observation"]["target_id"] == plan["api_target_id"] and r["phase"] == "weak"
    ]
    computed = a.replay_forecast(plan, reference, weak)
    for key, value in computed.items():
        b.check(lock[key] == value, "primary forecast replay mismatch: " + key)
    analysis = a.describe(plan, records, lock)
    b.check(analysis == b.read(data / "analysis.json"), "primary analysis replay mismatch")

    # This is intentionally separate from the frozen primary parser/forecast.
    diagnostic = b.read(data / "posthoc_format_diagnostic.json")
    panel = {q["query_id"]: q for q in plan["panel"]}
    counts, normalized_weak = defaultdict(Counter), defaultdict(list)
    for row in records:
        obs, q = row["observation"], panel[row["query_id"]]
        raw, strict = obs["output_text"].strip(), b.marker(obs["output_text"])
        answer = raw if raw in ("A", "B") else strict
        semantic, cue, identity = b.CELLS[q["cell"]]
        group = counts[(obs["target_id"], row["phase"])]
        group.update(
            {
                "n": 1,
                "strict_parseable": int(strict != "parse_failure"),
                "bare_marker_only": int(strict == "parse_failure" and raw in ("A", "B")),
                "canonicalized_parseable": int(answer != "parse_failure"),
                "canonicalized_semantic_consistent": int(
                    answer == a.expected_marker(semantic, identity)
                ),
                "canonicalized_cue_consistent": int(answer == a.expected_marker(cue, identity)),
            }
        )
        if row["phase"] == "weak":
            normalized_weak[obs["target_id"]].append(
                {
                    **obs,
                    "output_text": "FINAL: " + answer
                    if answer in ("A", "B")
                    else obs["output_text"],
                }
            )
    recomputed = [
        {"target_id": target, "phase": phase, **dict(count)}
        for (target, phase), count in sorted(counts.items())
    ]
    b.check(recomputed == diagnostic["per_target_phase"], "post-hoc diagnostic replay mismatch")
    feature = b.features(normalized_weak[plan["api_target_id"]])
    matches = [
        u["target_id"]
        for u in plan["targets"]
        if b.features(normalized_weak[u["target_id"]]) == feature
    ]
    b.check(
        matches == diagnostic["canonicalized_weak_feature_matches"], "post-hoc support mismatch"
    )
    return {
        "status": "public_analysis_reproduced",
        "observations": len(records),
        "primary_status": lock["status"],
        "primary_coverage": analysis["locked_forecast_score"]["coverage"],
        "posthoc_feature_matches": matches,
        "new_model_calls": 0,
        "execution_attestation": "not_provided; retained execution audit is a provenance statement",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(__file__).with_name("data"))
    args = parser.parse_args()
    print(json.dumps(replay(args.data), indent=2))
