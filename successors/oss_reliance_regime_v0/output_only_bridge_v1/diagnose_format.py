"""Explicitly post-hoc format diagnosis. Does not change primary features or lock."""
import argparse
from collections import Counter, defaultdict
from pathlib import Path

import bridge as b
import analyze_saved as a


def diagnose(root):
    plan = b.read(root / "plan.json")
    b.validate(plan)
    plan_sha = b.digest(root / "plan.json")
    saved = b.checked_results(root / "furnace-attempt-001", plan_sha)
    saved += b.checked_results(root / "api-weak-attempt-001", plan_sha)
    saved += b.checked_results(root / "api-challenge-attempt-001", plan_sha)
    panel = {q["query_id"]: q for q in plan["panel"]}
    summary, normalized_weak = defaultdict(Counter), defaultdict(list)
    malformed = []
    for row in saved:
        q, obs = panel[row["query_id"]], row["observation"]
        strict = b.marker(obs["output_text"])
        bare = obs["output_text"].strip()
        canonicalized = bare if bare in ("A", "B") else strict
        semantic, cue, identity = b.CELLS[q["cell"]]
        group = summary[(obs["target_id"], q["phase"])]
        group["n"] += 1
        group["strict_parseable"] += int(strict != "parse_failure")
        group["bare_marker_only"] += int(strict == "parse_failure" and bare in ("A", "B"))
        group["canonicalized_parseable"] += int(canonicalized != "parse_failure")
        group["canonicalized_semantic_consistent"] += int(canonicalized == a.expected_marker(semantic, identity))
        group["canonicalized_cue_consistent"] += int(canonicalized == a.expected_marker(cue, identity))
        if row["phase"] == "weak":
            normalized_weak[obs["target_id"]].append({**obs, "output_text": "FINAL: " + canonicalized if canonicalized in ("A", "B") else obs["output_text"]})
        if strict == "parse_failure":
            malformed.append({"target_id": obs["target_id"], "query_id": q["query_id"],
                              "raw_output": obs["output_text"], "bare_marker_only": bare in ("A", "B")})
    feature = {target: b.features(records) for target, records in normalized_weak.items()}
    matches = [u["target_id"] for u in plan["targets"] if feature[u["target_id"]] == feature[plan["api_target_id"]]]
    # No post-hoc probabilities or scores: this is a failure-source diagnostic.
    return {"analysis_tier": "post_hoc_format_diagnostic_not_prospective", "source_plan_sha256": plan_sha,
            "source_lock_sha256": b.digest(root / "forecast_lock.json"), "script_sha256": b.digest(__file__),
            "canonicalization_rule": "accept exact stripped A or B in addition to the frozen FINAL marker parser",
            "primary_lock_unchanged": True, "new_model_calls": 0,
            "canonicalized_weak_feature_matches": matches,
            "not_a_mechanism_label": True,
            "per_target_phase": [{"target_id": target, "phase": phase, **dict(counts)} for (target, phase), counts in sorted(summary.items())],
            "strict_parse_failures": malformed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = diagnose(args.root)
    b.write_new(args.output, value)
    print(b.canonical({"analysis_tier": value["analysis_tier"], "new_model_calls": 0,
                       "canonicalized_weak_feature_matches": value["canonicalized_weak_feature_matches"],
                       "api": [r for r in value["per_target_phase"] if r["target_id"] == "target-10"],
                       "failures": value["strict_parse_failures"]}))


if __name__ == "__main__":
    main()
