"""Verify a derived public record, reconstruct the controls-only lock, then score the holdout."""

from datetime import datetime
import json

import background
import lexical as l
from records import DATA, FILES, OLD, SOURCE_PIN, checked_pins, read, require, rows, sha

MANIFEST_SHA = "70584363fe90d67915d0599b778892d954990b9af2322df323ae80727149e398"


def observed(records, ids, with_units=False):
    features = {"qid", "output_text"} | ({"unit"} if with_units else set())
    result = {u: {} for u in l.UNITS} if with_units else {"endpoint": {}}
    for row in records:
        require(
            set(row) == features and type(row["output_text"]) is str,
            "visible text and inventory keys only",
        )
        u = row["unit"] if with_units else "endpoint"
        i = row["qid"]
        require(
            u in result and i in ids and i not in result[u],
            "unknown, duplicate or wrong-phase slot",
        )
        result[u][i] = row["output_text"]
    require(all(list(group) == ids for group in result.values()), "missing or misordered slots")
    return result if with_units else result["endpoint"]


def recover_lock(panel, oss, controls, recorded, execution):
    require(
        execution["controls"]["prediction_lock_sha256"] is None
        and execution["near"]["prediction_lock_sha256"] == execution["forecast_sha256"],
        "phase not bound to forecast",
    )
    utc = [
        datetime.fromisoformat(x)
        for x in (
            execution["controls"]["finished"],
            recorded["locked_at"],
            execution["near_first_dispatch"],
            execution["near"]["finished"],
        )
    ]
    require(
        all(x.utcoffset() is not None for x in utc) and utc == sorted(utc) and utc[1] < utc[2],
        "not a pre-dispatch lock",
    )
    require(
        recorded["near_endpoint_slots_seen"] == 0
        and recorded["plan_sha256"] == execution["plan_sha256"],
        "wrong lock scope",
    )
    pred = l.bridge(panel, oss, controls)
    require(
        pred == recorded["prediction"] and not pred["api_intervention_profile_issued"],
        "controls do not reproduce saved forecast",
    )
    return pred


def past_orbits():
    inventory = read(OLD / "inventory.json")
    groups = inventory["reference_clusters"]

    def addr(r):
        return (r["case_id"], r["projection_id"], r["replicate_id"], r["prompt_text"])

    axis = [addr(r) for r in inventory["panel"] if r["phase"] == "weak"]
    by = {u: {} for u in groups}
    for r in rows(OLD / "observations.jsonl"):
        u = r["target_id"]
        a = addr(r)
        if u in by and a in axis:
            require(a not in by[u], "duplicate archived observation")
            by[u][a] = r["output_text"]
    require(
        len(set(axis)) == len(axis) == 80 and all(set(v) == set(axis) for v in by.values()),
        "incomplete archived orbit",
    )
    return {u: [(a, v[a]) for a in axis] for u, v in by.items()}, groups


def replay(root=DATA):
    require(sha(root / "manifest.json") == MANIFEST_SHA, "changed public manifest")
    m = read(root / "manifest.json")
    require(
        m["source_pin_sha256"] == SOURCE_PIN and set(m["files"]) == set(FILES),
        "unrecognized publication",
    )
    for f, h in m["files"].items():
        require(sha(root / f) == h, "changed public file: " + f)
    pins = checked_pins()
    for f, pin in (
        ("observations.jsonl", "prior_public_observations_sha256"),
        ("inventory.json", "prior_public_inventory_sha256"),
    ):
        require(sha(OLD / f) == m[pin], "wrong previous public checkpoint")
    pl = l.build()
    plan_rows = read(root / "panel.json")
    require(
        [{k: r[k] for k in ("qid", "phase", "prompt_text")} for r in pl] == plan_rows
        and read(root / "as_run_protocol.json")["id"] == l.SCOPE,
        "panel or protocol drift",
    )
    ids = [q["qid"] for q in pl]
    oss = observed(rows(root / "oss.jsonl"), ids, True)
    ctl = observed(
        rows(root / "api_controls.jsonl"), [r["qid"] for r in pl if r["phase"] == "controls"]
    )
    run = read(root / "execution.json")
    rec = read(root / "forecast_lock.json")
    require(
        run["plan_sha256"] == pins["weak-twin-lexical-20261102/plan.json"]
        and run["forecast_sha256"] == pins["weak-twin-lexical-20261102/forecast.json"],
        "wrong original hashes",
    )
    pred = recover_lock(pl, oss, ctl, rec, run)
    # No near answer reaches the predictor. File hashes above establish identity, not features.
    near = observed(rows(root / "api_near.jsonl"), [r["qid"] for r in pl if r["phase"] == "near"])
    endpoint = l.close_endpoint(pl, {**ctl, **near}, pred)
    twin = {
        g: {k: v for k, v in t.items() if k != "cases"} for g, t in l.twin_scores(pl, oss).items()
    }
    require(
        run["oss"]["logical_trials_completed"] == sum(map(len, oss.values()))
        and run["oss"]["physical_forwards_completed"]
        == sum(run["oss"]["physical_started_by_kind"].values())
        and all(
            run[p]["recorded"] == run[p]["dispatches"] == n
            for p, n in (("controls", len(ctl)), ("near", len(near)))
        ),
        "accounting drift",
    )
    old, groups = past_orbits()
    historical = background.historical(
        old, groups, read(root / "reference_counts.json"), read(root / "surface_collision.json")
    )
    formats = background.interface(rows(root / "interface.jsonl"))
    responses = {**ctl, **near}
    return {
        "scope": "known OSS collisions and prospective endpoint answers; no endpoint intervention label",
        "twins": twin,
        "matched_oss": pred["matching_ids"],
        "api": endpoint,
        "format_on_last_digit_panel": {
            "correct": sum(l.symbol(responses[q["qid"]]) == q["expected"] for q in pl),
            "requested_marker": sum(
                responses[q["qid"]].strip() == "FINAL: " + q["expected"] for q in pl
            ),
            "raw_repeat_changes": sum(
                v["raw_only_repeat_changes"] for v in endpoint["by_arm"].values()
            ),
            "slots": len(pl),
        },
        "historical": historical,
        "prior_interface_runs": formats,
        "new_model_calls": 0,
    }


if __name__ == "__main__":
    print(json.dumps(replay(), sort_keys=True, indent=2))
