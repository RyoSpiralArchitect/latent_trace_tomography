"""Verify the published finite-registry screen without model or network access."""

import hashlib
import json
from pathlib import Path

import common as s

ROOT = Path(__file__).resolve().parent
PINS = {
    "data/expected.json": "1c492ea2e80be47c1783703feae588f3445607c8031f08af56bd4d1f35889fd5",
    "data/observations.json": "3dacc6fc7f3f1cab8b14194e8c850eda205024ed1858ada9cea1b464fc333337",
    "common.py": "597bc968e6c962c6d78377d7e74d2cc08549d12854bb209f3bf9d8735a6a98de",
}


def read_panel(stage, item, expected_tracks, measured):
    p = item["panel"]
    ids = [q["qid"] for q in p]
    s.ok(len(ids) == len(set(ids)) == (72 if stage == "B" else 60), "slot inventory")
    s.ok(
        set(item["tracks"]) == expected_tracks and set(item["measured"]) == measured, "track roster"
    )
    s.ok(
        all(q["prompt_sha256"] == hashlib.sha256(q["prompt_text"].encode()).hexdigest() for q in p),
        "prompt hash",
    )
    for q in p:
        s.ok(
            q["phase"] in ("controls", "challenge")
            and q["qid"] == f"{q['cell']}/{q['arm']}/r{q['rep']}",
            "repeat/phase",
        )
    bycell = {}
    for q in p:
        k = q["qid"].rsplit("/", 1)[0]
        desc = q["prompt_text"], q["docket"], q["phase"]
        s.ok(bycell.setdefault(k, desc) == desc, "repeats differ")
    views = {}
    for unit, rows in item["tracks"].items():
        s.ok(len(rows) == len(ids) and all(x in ("A", "B", "?") for x in rows), "symbol rows")
        views[unit] = s.make_view(p, dict(zip(ids, rows)))
    for unit, m in item["measured"].items():
        s.ok(
            m["observed"] == len(ids) and m["observed"] <= m["physical"] <= 16 * len(ids),
            "receipt counts",
        )
    return (
        p,
        views,
        {
            "logical": sum(x["observed"] for x in item["measured"].values()),
            "physical": sum(x["physical"] for x in item["measured"].values()),
        },
    )


def compare(p, t, refs, fam):
    w, h = s.surfaces(p)
    pred = s.weak_predict({k: t[k] for k in w}, refs, fam, w, h)
    return {"forecast_from_weak": pred, **s.score_bank(t, refs, fam, w, h, pred)}


def run(root=ROOT):
    s.ok(
        all(hashlib.sha256((root / k).read_bytes()).hexdigest() == v for k, v in PINS.items()),
        "public integrity check",
    )
    data = s.read(root / "data/observations.json")
    exp = s.read(root / "data/expected.json")
    reg = s.read(root / "registry.json")
    fam = s.family_map(reg)
    old = set(reg["prior"])
    small = old | set(reg["remaining"])
    primary = set(fam)
    raw = {u + "@raw-diagnostic" for u, v in reg["scaled"].items() if v["primary"] == "chat"}
    p, v, bcount = read_panel("B", data["B"], primary | raw | {"target"}, (primary - old) | raw)
    banks = {
        k: compare(p, v["target"], {u: v[u] for u in cohort}, fam)
        for k, cohort in (
            ("prior_four", old),
            ("all_nine_small", small),
            ("expanded_twelve", primary),
        )
    }
    s.ok(banks == exp["banks"], "B results or forecast differ")

    def scoped(p, t, r):
        w, h = s.surfaces(p)
        return {
            k: s.compare(t, r, ix) for k, ix in (("weak", w), ("conflict", h), ("joint", w + h))
        }

    s.ok(
        {u: scoped(p, v["target"], v[u]) for u in raw} == exp["raw_diagnostics"],
        "interface diagnostics",
    )
    selected = set(banks["expanded_twelve"]["joint"]["IN"]) - old
    s.ok(sorted(selected) == exp["selected"], "conditional A roster")
    a, av, acount = read_panel("A", data["A"], selected | {"target"}, selected)
    s.ok({q["docket"] for q in a}.isdisjoint({q["docket"] for q in p}), "overlapping cases")
    s.ok(
        {u: scoped(a, av["target"], av[u]) for u in selected} == exp["replication"], "A replication"
    )
    s.ok(
        exp["counts"] == {"A": acount, "B": bcount} and exp["new_endpoint_calls"] == 0,
        "measured totals",
    )
    return {
        "weak_matches": banks["expanded_twelve"]["weak"]["IN"],
        "joint_matches": sorted(selected),
        "joint_unknown": banks["expanded_twelve"]["joint"]["UNKNOWN"],
        "B_conflict_predictions": banks["expanded_twelve"]["weak_prediction_counts"],
        "counts": exp["counts"],
        "replay_model_calls": 0,
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
