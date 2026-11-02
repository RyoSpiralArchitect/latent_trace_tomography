"""Export only allowlisted symbol classes, synthetic prompts and measurements."""

import argparse
import hashlib
import json
from pathlib import Path

import common as s

HERE = Path(__file__).resolve().parent
PINS = {
    "plan.json": "b056387e3864a74d5e88aaf773c2466360f7f25e5aabb0e71d0088006b0e002b",
    "score.json": "817c4976d8508df666ad2b42c0550e762e391017828cbdc3996436c3db43c70f",
    "independent.json": "218bc35d5ce4d3e983235ec990b8b5ed445e1dabea07f8815e615698ce1e1abb",
    "selection.json": "2b2dfd6875b246be17720b8e7fe997039a40616b71c6df5269856119d245e5e5",
}


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def export(source, output):
    s.ok(all(digest(source / k) == v for k, v in PINS.items()), "different study")
    plan = s.read(source / "plan.json")
    score = s.read(source / "score.json")
    b = s.read(source / "B_analysis.json")
    s.ok(digest(source / "B_analysis.json") == score["B_analysis_sha256"], "B score")
    archive = source / "archive"
    s.ok(all(digest(archive / k) == v for k, v in plan["archive_sha256"].items()), "parent archive")
    s.ok(
        all(
            digest(HERE / k) == plan["source_hashes"][k]
            for k in ("common.py", "registry.json", "protocol.json")
        ),
        "frozen methods",
    )
    proof = s.read(source / "independent.json")
    payload = {}
    for stage in ("B", "A"):
        panel = plan["panels"][stage]
        ids = {q["qid"]: q for q in panel}
        tracks = {}
        metrics = {}

        def add(unit, row):
            q = ids[row["qid"]]
            dest = tracks.setdefault(unit, {})
            s.ok(
                q["qid"] not in dest and q["prompt_sha256"] == row["prompt_sha256"],
                "duplicate/foreign observation",
            )
            dest[q["qid"]] = s.symbol(row["text"]) or "?"

        for name in (
            ("api-base", "api-added", "api-challenge", "furnace-001")
            if stage == "B"
            else ("api-direct",)
        ):
            r = archive / name
            s.ok(
                digest(r / "observations.jsonl")
                == s.read(r / "receipt.json")["artifacts"]["observations.jsonl"],
                "parent observations",
            )
            for row in s.lines(r / "observations.jsonl"):
                add(row["unit"] if name == "furnace-001" else "target", row)
        if stage == "A":
            for row in s.lines(archive / "prior/prior_controls.jsonl"):
                add("target", row)
        root = source / ("run-" + stage)
        rec = s.read(root / "receipt.json")
        s.ok(rec == score[stage + "_run"], "acquisition closure")
        for unit, h in rec["track_receipts"].items():
            r = root / unit
            meas = s.read(r / "receipt.json")
            s.ok(
                h == digest(r / "receipt.json")
                and meas["status"] == "complete"
                and digest(r / "observations.jsonl") == meas["artifacts"]["observations.jsonl"],
                "measurements",
            )
            for row in s.lines(r / "observations.jsonl"):
                add(unit, row)
            metrics[unit] = {k: meas[k] for k in ("observed", "physical", "mode")}
        s.ok(all(set(x) == set(ids) for x in tracks.values()), "incomplete track")
        payload[stage] = {
            "panel": panel,
            "tracks": {u: [x[i] for i in ids] for u, x in tracks.items()},
            "measured": metrics,
        }
    expected = {
        "banks": b["banks"],
        "raw_diagnostics": b["raw_diagnostics"],
        "selected": s.read(source / "selection.json")["replicate_A"],
        "replication": score["A_readout"],
        "counts": {p: proof[p + "_counts"] for p in ("A", "B")},
        "new_endpoint_calls": score["new_API_calls"],
    }
    output.mkdir(exist_ok=True, parents=True)
    for name, obj in (("observations.json", payload), ("expected.json", expected)):
        dest = output / name
        with dest.open("x") as f:
            json.dump(obj, f, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            f.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    export(args.source, args.output)
