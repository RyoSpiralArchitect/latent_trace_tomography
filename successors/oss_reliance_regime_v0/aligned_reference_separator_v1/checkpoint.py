"""Export/replay the stage prefix actually completed. No network or model imports."""

import argparse
import json
from pathlib import Path
import study as s
import study_io as io

ROOT = Path(__file__).resolve().parent
ORDER = ("development", "confirmation", "conflict")


def export(private, dest):
    pin = io.digest(ROOT / "freeze.json")
    io.verify(pin)
    public = {"plan": pin, "stages": {}, "new_endpoint_calls": 0}
    for stage in ORDER:
        g = io.outcome(stage, private, pin)
        s.require(g == io.read(private / (stage + "-gate.json")), "not a saved gate")
        rows, raw, measured, receipts = io.load(stage, private, pin)
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
