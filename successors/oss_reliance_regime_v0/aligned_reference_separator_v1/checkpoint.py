"""Export/replay the stage prefix actually completed. No network or model imports."""

import argparse
import json
from pathlib import Path
import study as s
import study_io as io

ROOT = Path(__file__).resolve().parent
ORDER = ("development", "confirmation", "conflict")


def require_one_trial_per_id(events, expected):
    """Check multiplicity and order, not just the last result stored per job."""
    started, completed = set(), set()
    for e in events:
        kind = e["event"]
        if kind not in ("trial_started", "trial_completed"):
            continue
        payload = e["payload"]
        job = payload["job_id"]
        s.require(job in expected, "foreign trial ID")
        if kind == "trial_started":
            s.require(job not in started, "duplicate trial start")
            started.add(job)
        else:
            s.require(
                job in started and job not in completed, "out-of-order or duplicate completion"
            )
            s.require(payload["result_sha256"] == expected[job], "trial result hash")
            completed.add(job)
    s.require(started == completed == set(expected), "missing trial start/completion")


def audit_small_trials(private, stage, rows, raw):
    for unit in s.SMALL:
        dr = private / (stage + "-small") / unit
        rec = io.read(dr / "receipt.json")
        journal = (dr / "events.jsonl").read_bytes()
        s.require(s.sha(journal) == rec["artifacts"]["events.jsonl"], "different trial journal")
        expected = {
            unit + "/" + q["qid"]: s.seal(
                {"qid": q["qid"], "prompt_sha256": q["prompt_sha256"], "text": raw[unit][q["qid"]]}
            )
            for q in rows
        }
        require_one_trial_per_id((json.loads(line) for line in journal.splitlines()), expected)
        s.require(
            rec["counts"]["logical_trials_started"]
            == rec["counts"]["logical_trials_completed"]
            == len(expected),
            "trial counters do not match the planned IDs",
        )


def export(private, dest):
    pin = io.digest(ROOT / "freeze.json")
    io.verify(pin)
    public = {"plan": pin, "stages": {}, "new_endpoint_calls": 0}
    for stage in ORDER:
        g = io.outcome(stage, private, pin)
        s.require(g == io.read(private / (stage + "-gate.json")), "not a saved gate")
        rows, raw, measured, receipts = io.load(stage, private, pin)
        audit_small_trials(private, stage, rows, raw)
        public["stages"][stage] = {
            "observations": {
                u: "".join(s.symbol(out[q["qid"]]) or "?" for q in rows) for u, out in raw.items()
            },
            "measured": measured,
            "receipts": receipts,
            "rows": s.seal(rows),
            "gate_sha256": io.digest(private / (stage + "-gate.json")),
        }
        if stage == "conflict" or not g["eligible"]:
            break
    required = set(public["stages"])
    for stage in set(ORDER) - required:
        s.require(
            not any((private / (stage + "-" + g)).exists() for g in ("small", "large"))
            and not (private / (stage + "-gate.json")).exists(),
            "unexpected acquisition beyond gate",
        )
    io.put(dest, public)


def replay(d, pin):
    io.verify(pin)
    s.require(d["plan"] == pin and d["new_endpoint_calls"] == 0, "scope")
    expected = ["development"]
    stages = {}
    log = physical = 0
    selected = None
    weak = None
    for stage in ORDER:
        if stage not in expected:
            break
        item = d["stages"][stage]
        rows = (
            s.panel(stage, s.VARIANTS)
            if stage == "development"
            else s.panel("confirmation", ("baseline", selected))
            if stage == "confirmation"
            else s.panel("confirmation", ("baseline",), True)
        )
        s.require(
            item["rows"] == s.seal(rows)
            and set(item["observations"]) == set(item["measured"]) == set(s.UNITS),
            "inventory",
        )
        raw = {}
        for u, txt in item["observations"].items():
            m = item["measured"][u]
            s.require(
                len(txt) == len(rows) == m["logical"]
                and set(txt) <= set("AB?")
                and len(rows) <= m["physical"] <= 16 * len(rows),
                "symbols/counts",
            )
            raw[u] = {q["qid"]: v for q, v in zip(rows, txt)}
            log += m["logical"]
            physical += m["physical"]
        if stage == "conflict":
            w, wr = weak
            stages[stage] = s.branches(w, wr, rows, raw, selected)
        else:
            stages[stage] = s.evaluate(rows, raw)
            selected = stages[stage]["chosen"]
            if selected:
                expected.append("confirmation" if stage == "development" else "conflict")
            if stage == "confirmation":
                weak = (rows, raw)
        saved = {
            "stage": stage,
            "plan": pin,
            "measured": item["measured"],
            "receipts": item["receipts"],
            "previous": None
            if stage == "development"
            else d["stages"][ORDER[ORDER.index(stage) - 1]]["gate_sha256"],
            "new_endpoint_calls": 0,
        }
        if stage == "conflict":
            saved["lookup"] = stages[stage]
        else:
            saved.update(result=stages[stage], selected=selected, eligible=selected is not None)
        blob = (json.dumps(saved, indent=2, sort_keys=True) + "\n").encode()
        s.require(s.sha(blob) == item["gate_sha256"], "different result from retained gate")
    s.require(set(d["stages"]) == set(expected), "extra or missing stage")
    return {
        "stages": stages,
        "generations": log,
        "physical_forwards": physical,
        "new_endpoint_calls": 0,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("export", "replay"))
    p.add_argument("--private", type=Path)
    p.add_argument("--out", type=Path, default=ROOT / "checkpoint.json")
    a = p.parse_args()
    if a.mode == "export":
        export(a.private, a.out)
    else:
        s.require(
            io.digest(a.out) == (ROOT / "checkpoint.sha256").read_text().strip(),
            "public checkpoint hash",
        )
        print(
            json.dumps(
                replay(io.read(a.out), io.digest(ROOT / "freeze.json")), indent=2, sort_keys=True
            )
        )
