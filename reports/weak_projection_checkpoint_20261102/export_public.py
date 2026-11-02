"""Maintainer-only, offline projection of exact reviewed local originals. Never copies a run tree."""

import argparse
import json
from pathlib import Path
import re

import lexical
from records import FILES, FORMAT, OLD, SOURCE_PIN, checked_pins, layers, read, require, rows, sha


def safe_text(value):
    require(
        type(value) is str and re.fullmatch(r"\n?(?:FINAL: )?[AB]", value),
        "not a reviewed synthetic answer",
    )
    return value


def export(source, dest):
    pins = checked_pins()
    for name, pin in pins.items():
        require(sha(source / name) == pin, "source mismatch: " + name)
    live = source / "weak-twin-lexical-20261102"
    plan = read(live / "plan.json")
    f = read(live / "forecast.json")
    require(
        lexical.build() == plan["panel"] and f["plan_sha256"] == sha(live / "plan.json"),
        "wrong panel or saved forecast",
    )
    scored = read(live / "score.json")
    audit = read(live / "independent_recount.json")
    pf = read(live / "preflight.json")
    require(
        scored["forecast_sha256"] == sha(live / "forecast.json")
        and audit["score_sha256"] == sha(live / "score.json")
        and f["near_endpoint_slots_seen"] == 0
        and not f["prediction"]["api_intervention_profile_issued"]
        and pf["plan_sha256"] == sha(live / "plan.json")
        and pf["passed"],
        "unclosed original audit",
    )
    out = {
        "as_run_protocol.json": read(live / "protocol.json"),
        "panel.json": [layers(q, ("qid", "phase", "prompt_text")) for q in plan["panel"]],
        "forecast_lock.json": layers(
            f, ("plan_sha256", "locked_at", "near_endpoint_slots_seen", "prediction")
        ),
    }
    agg = {
        "endpoint": plan["transport"]["model"],
        "sampling": layers(
            plan["transport"], ("temperature", "reasoning", "max_output_tokens", "store")
        ),
        "training_prompt_overlap": layers(
            pf["overlap"]["training"], ("reference_prompts", "exact_text", "docket_hits")
        ),
        "furnace_receipt_sha256": f["furnace_receipt_sha256"],
        "control_receipt_sha256": f["controls_receipt_sha256"],
        "plan_sha256": sha(live / "plan.json"),
        "forecast_sha256": sha(live / "forecast.json"),
        "near_first_dispatch": rows(live / "api-near/events.jsonl")[0]["at"],
    }
    for phase, directory, name in (
        ("oss", "furnace-001", "oss.jsonl"),
        ("controls", "api-controls", "api_controls.jsonl"),
        ("near", "api-near", "api_near.jsonl"),
    ):
        base = live / directory
        rec = read(base / "receipt.json")
        require(
            rec["plan_sha256"] == agg["plan_sha256"]
            and rec["status"] == "complete"
            and all(sha(base / k) == v for k, v in rec["artifacts"].items()),
            "receipt/artifact mismatch",
        )
        out[name] = [
            {
                **({"unit": v["unit"]} if phase == "oss" else {}),
                "qid": v["qid"],
                "output_text": safe_text(v["text"]),
            }
            for v in rows(base / "observations.jsonl")
        ]
        if phase == "oss":
            require(
                sha(base / "receipt.json") == agg["furnace_receipt_sha256"], "wrong OSS receipt"
            )
            agg["oss"] = layers(
                rec["counts"],
                (
                    "logical_trials_completed",
                    "physical_forwards_completed",
                    "physical_started_by_kind",
                ),
            )
        else:
            agg[phase] = layers(
                rec,
                (
                    "recorded",
                    "dispatches",
                    "finished",
                    "transport_retries",
                    "dispatch_outcome_unknown",
                    "prediction_lock_sha256",
                ),
            )
            if phase == "controls":
                require(
                    sha(base / "receipt.json") == agg["control_receipt_sha256"],
                    "wrong control receipt",
                )
    out["execution.json"] = agg
    original = read(source / "matched-tomography-20261023/attempt-001/summary.json")["causal"]
    targets = read(source / "reference-replication-20261029/run/plan.json")["targets"]
    counts = {}
    rename = {
        "pairs": "pairs",
        "informative": "informative_pairs",
        "unparseable": "unparseable_base_or_donor",
        "targeted": "targeted_interchange_credit",
        "matched_null": "norm_matched_rotation_credit",
        "targeted_parsed": "targeted_interchange_parse",
        "null_parsed": "norm_matched_rotation_parse",
    }
    for t in targets:
        parts = [
            v
            for v in original
            if (v["partition"], v["factor"], v["model_unit_id"])
            == ("evaluation", "surface_cue", t["model_unit_id"])
        ]
        require(
            sorted(v["content"] for v in parts) == [3, 4] and all(v["pairs"] == 8 for v in parts),
            "wrong cue slices",
        )
        counts[t["target_id"]] = {
            "unit": t["model_unit_id"],
            **{k: sum(v[f] for v in parts) for k, f in rename.items()},
        }
    out["reference_counts.json"] = counts
    pair = source / "cue-omission-witness-20261102"
    key = read(pair / "negative_control.json")
    bound = read(pair / "collision_bound.json")
    require(
        key["input_sha256"] == sha(pair / "common_orbit.json")
        and bound["same_committed_checkpoints_and_decode"],
        "wrong historical witness",
    )
    members = sorted(key["members"])
    orbit = read(pair / "common_orbit.json")
    out["surface_collision.json"] = {
        "members": members,
        "net_transfers": [key["members"][m]["net_donor_transfers"] for m in members],
        "common_orbit": [
            {"prompt_text": r["prompt_text"], "output_text": safe_text(r["output_text"])}
            for r in orbit
        ],
        "archived_equal": bound["previous_exact_text_matches"],
        "new_equal": bound["new_exact_text_matches"],
    }
    formats = []
    for name, dirname, keys, requests in (
        (
            "equality",
            "gpt6luna-output-contract-20261101",
            FORMAT / "scoring_key.json",
            FORMAT / "requests.json",
        ),
        (
            "fresh_rules",
            "gpt6luna-rule-transfer-20261101",
            source / "gpt6luna-rule-transfer-20261101/scoring_key.json",
            source / "gpt6luna-rule-transfer-20261101/requests.json",
        ),
    ):
        root = source / dirname / "live-001"
        inputs = {q["query_id"]: q["prompt_text"] for q in read(requests)}
        ks = {v["query_id"]: v for v in read(keys)}
        rec = read(root / "receipt.json")
        raw = rows(root / "observations.jsonl")
        require(
            rec["status"] == "complete"
            and rec["artifacts_sha256"]["observations.jsonl"] == sha(root / "observations.jsonl")
            and len(inputs) == len(ks) == len(raw) == len({r["query_id"] for r in raw}) == 96,
            "incomplete format run",
        )
        for v in raw:
            i = v["query_id"]
            k = ks[i]
            formats.append(
                {
                    **layers(
                        k,
                        (
                            "query_id",
                            "parent_case_id",
                            "replicate_id",
                            "kind",
                            "render_mode",
                            "expected_answer",
                        ),
                    ),
                    "study": name,
                    "family": k.get("family", "code_equality"),
                    "prompt_text": inputs[i],
                    "output_text": safe_text(v["output_text"]),
                }
            )
    out["interface.jsonl"] = formats
    require(set(out) == set(FILES), "wrong allowlist")
    dest.mkdir(exist_ok=True, parents=True)
    require(not any(dest.iterdir()), "use a new or empty export directory")
    for name, obj in out.items():
        with (dest / name).open("x", encoding="utf8") as stream:
            if name.endswith(".jsonl"):
                for row in obj:
                    stream.write(
                        json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                        + "\n"
                    )
            else:
                json.dump(obj, stream, indent=2, sort_keys=True, ensure_ascii=False)
                stream.write("\n")
    manifest = {
        "schema": "weak_projection_public_replay_v1",
        "source_pin_sha256": SOURCE_PIN,
        "files": {k: sha(dest / k) for k in FILES},
        "prior_public_observations_sha256": sha(OLD / "observations.jsonl"),
        "prior_public_inventory_sha256": sha(OLD / "inventory.json"),
    }
    with (dest / "manifest.json").open("x") as f0:
        json.dump(manifest, f0, indent=2, sort_keys=True)
        f0.write("\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path)
    ap.add_argument("new_directory", type=Path)
    a = ap.parse_args()
    export(a.source, a.new_directory)
