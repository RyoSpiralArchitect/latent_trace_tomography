"""Freeze a plan; verify acquisition records and emit a gate or a conditional table."""

import argparse
from collections import Counter
import json
from pathlib import Path
import study as s

ROOT = Path(__file__).resolve().parent
SOURCES = ("study.py", "study_io.py", "acquire.py", "protocol.json")


def digest(p):
    return s.sha(p.read_bytes())


def read(p):
    return json.loads(p.read_text())


def put(p, x):
    with p.open("x") as f:
        json.dump(x, f, indent=2, sort_keys=True)
        f.write("\n")


def freeze():
    outline = {
        "id": s.DESIGN,
        "sources": {k: digest(ROOT / k) for k in SOURCES},
        "registry": list(s.UNITS),
        "inventories": {
            "development": s.seal(s.panel("development", s.VARIANTS)),
            "confirmation": {
                v: s.seal(s.panel("confirmation", ("baseline", v))) for v in s.VARIANTS[1:]
            },
            "conflict": s.seal(s.panel("confirmation", ("baseline",), True)),
        },
        "new_endpoint_calls": 0,
    }
    return outline


def verify(pin):
    s.require(
        digest(ROOT / "freeze.json") == pin and read(ROOT / "freeze.json") == freeze(),
        "frozen source/plan drift",
    )
    return read(ROOT / "freeze.json")


def predecessor(stage, ev):
    return (
        None
        if stage == "development"
        else digest(
            ev / ("development-gate.json" if stage == "confirmation" else "confirmation-gate.json")
        )
    )


def allowed_rows(stage, ev):
    if stage == "development":
        return s.panel(stage, s.VARIANTS)
    s.require(stage in ("confirmation", "conflict"), "stage")
    prev = "development" if stage == "confirmation" else "confirmation"
    g = read(ev / (prev + "-gate.json"))
    pin = digest(ROOT / "freeze.json")
    s.require(
        g["plan"] == pin
        and g["stage"] == prev
        and g["eligible"]
        and g["selected"] in s.VARIANTS[1:],
        "no qualifying previous gate",
    )
    s.require(g == outcome(prev, ev, pin), "previous gate not supported by the reference records")
    return (
        s.panel("confirmation", ("baseline", g["selected"]))
        if stage == "confirmation"
        else s.panel("confirmation", ("baseline",), True)
    )


def track_rows(dr, u, rows, pin, stage):
    rec = read(dr / "receipt.json")
    expected = {q["qid"]: q["prompt_sha256"] for q in rows}
    s.require(
        rec["status"] == "complete"
        and rec["unit"] == u
        and rec["panel"] == stage
        and rec["mode"] == ("chat" if u == s.M else "anchor_raw")
        and rec["plan_sha256"] == pin
        and all(digest(dr / k) == v for k, v in rec["artifacts"].items()),
        "track metadata or file hash",
    )
    obs = [json.loads(x) for x in (dr / "observations.jsonl").read_text().splitlines()]
    s.require(
        [r["qid"] for r in obs] == list(expected)
        and all(
            r["prompt_sha256"] == expected[r["qid"]] and isinstance(r["text"], str) for r in obs
        )
        and len(obs) == rec["observed"],
        "observed slot/prompt binding",
    )
    if u == s.M:
        ops = [json.loads(x) for x in (dr / "operations.jsonl").read_text().splitlines()]
        s.require(
            len(ops) == 2 * len(obs)
            and sum(r["forwards"] for r in ops[1::2]) == rec["physical"] == rec["started_forwards"],
            "large forward accounting",
        )
        for a, b, r in zip(ops[::2], ops[1::2], obs):
            s.require(
                a["event"] == "started"
                and b["event"] == "complete"
                and a["qid"] == b["qid"] == r["qid"]
                and b["row_sha256"] == s.seal(r),
                "large output journal",
            )
    else:
        events = [json.loads(x) for x in (dr / "events.jsonl").read_text().splitlines()]
        prev = "0" * 64
        kinds = Counter()
        closed = {}
        for i, e in enumerate(events):
            h = e.pop("event_sha256")
            s.require(
                (e["sequence"], e["previous_sha256"], h) == (i, prev, s.seal(e)),
                "anchor event chain",
            )
            prev = h
            kinds[e["event"]] += 1
            if e["event"] == "trial_completed":
                closed[e["payload"]["job_id"]] = e["payload"]["result_sha256"]
        s.require(
            prev == rec["chain"]["final_event_sha256"]
            and kinds["forward_completed"] == rec["physical"]
            and closed == {u + "/" + r["qid"]: s.seal(r) for r in obs},
            "anchor output/forward journal",
        )
    return {r["qid"]: r["text"] for r in obs}, rec


def load(stage, ev, pin):
    rows = allowed_rows(stage, ev)
    raw = {}
    measured = {}
    receipts = {}
    for group, us in (("small", s.SMALL), ("large", (s.M,))):
        dr = ev / (stage + "-" + group)
        rr = read(dr / "receipt.json")
        s.require(
            rr["plan"] == pin
            and rr["stage"] == stage
            and rr["group"] == group
            and rr["gate"] == predecessor(stage, ev)
            and rr["prompt_seal"] == s.seal(rows)
            and rr["complete"]
            and rr["new_endpoint_calls"] == 0
            and set(rr["tracks"]) == set(us),
            "stage binding",
        )
        receipts[group] = digest(dr / "receipt.json")
        for u in us:
            s.require(rr["tracks"][u] == digest(dr / u / "receipt.json"), "track substitution")
            raw[u], rec = track_rows(dr / u, u, rows, pin, stage)
            measured[u] = {"logical": rec["observed"], "physical": rec["physical"]}
        s.require(
            all(rr[k] == sum(measured[u][k] for u in us) for k in ("logical", "physical")),
            "stage accounting",
        )
    return rows, raw, measured, receipts


def outcome(stage, ev, pin):
    rows, raw, measured, receipts = load(stage, ev, pin)
    report = {
        "stage": stage,
        "plan": pin,
        "measured": measured,
        "receipts": receipts,
        "previous": predecessor(stage, ev),
        "new_endpoint_calls": 0,
    }
    if stage == "conflict":
        w, wr, _, _ = load("confirmation", ev, pin)
        v = read(ev / "confirmation-gate.json")["selected"]
        return {**report, "lookup": s.branches(w, wr, rows, raw, v)}
    result = s.evaluate(rows, raw)
    return {
        **report,
        "selected": result["chosen"],
        "eligible": result["chosen"] is not None,
        "result": result,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("freeze", "development", "confirmation", "conflict"))
    p.add_argument("--plan")
    p.add_argument("--evidence", type=Path)
    a = p.parse_args()
    if a.action == "freeze":
        put(ROOT / "freeze.json", freeze())
        print(digest(ROOT / "freeze.json"))
    else:
        verify(a.plan)
        res = outcome(a.action, a.evidence, a.plan)
        f = a.evidence / (a.action + "-gate.json")
        if f.exists():
            s.require(read(f) == res, "saved result drift")
        else:
            put(f, res)
        print(
            json.dumps(
                {
                    k: res.get(k)
                    for k in ("stage", "selected", "eligible", "measured", "new_endpoint_calls")
                }
            )
        )
