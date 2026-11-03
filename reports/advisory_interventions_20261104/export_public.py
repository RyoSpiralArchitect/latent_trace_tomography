"""Project allowlisted fields from locally retained evidence; no network or inference."""

import argparse
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDIES = (
    "pair-advisory-legend-20261103",
    "luna-literal-legend-20261103",
    "luna-exact-panel-flip-20261103",
    "advisory-map-replication-20261104",
    "gpt2-pair-cue-interchange-20261104",
    "gpt2-mixed-cue-code-cross-20261104/measurement",
)


def ck(value, why):
    if not value:
        raise ValueError(why)


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def obj(x):
    return (json.dumps(x, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def rows(xs):
    return "".join(
        json.dumps(x, ensure_ascii=False, separators=(",", ":")) + "\n" for x in sorted(xs)
    ).encode()


def project(root):
    used = {path: {} for path in STUDIES}
    files = {}

    def raw(i, f):
        b = (root / STUDIES[i] / f).read_bytes()
        used[STUDIES[i]][f] = sha(b)
        return b

    def read(i, f):
        return json.loads(raw(i, f))

    def journal(i, f):
        return [json.loads(v) for v in raw(i, f).splitlines()]

    def digest(i, f):
        return used[STUDIES[i]][f]

    ind = [read(i, "independent.json") for i in range(6)]
    dev = ind[0]["stages"]["development"]
    gate = read(0, "evidence/development-gate.json")
    ck(dev["gate_sha256"] == digest(0, "evidence/development-gate.json"), "coded-advisory gate")
    fo = read(2, "forecast.json")
    ck(ind[2]["forecast_sha256"] == digest(2, "forecast.json"), "reference forecast")
    rep = read(3, "score.json")
    ck(ind[3]["score_sha256"] == digest(3, "score.json"), "fresh-panel source")
    for i in (0, 2, 3):
        raw(i, "freeze.json")
    context = {
        "coded_advisory": {
            "arms": dev["arms"],
            "clean_coded_splits": dev["all_control_clean_coded_splits"],
            "go": gate["lock"]["go"],
            "issued": gate["lock"]["issued"],
            "new_endpoint_calls": gate["new_endpoint_calls"],
        },
        "literal_luna": {
            "calls": ind[1]["calls"],
            "pairs": ind[1]["cells"],
            "events": ind[1]["events"],
        },
        "exact_witness": {
            "selection": ind[2]["selection"],
            "weak_counts": ind[2]["weak_counts"],
            "flip_counts": fo["descriptive_only_flipped"],
            "issued": fo["forecast"]["issued"],
            "endpoint_accuracy": fo["forecast"]["endpoint_accuracy"],
            "status": fo["forecast"]["decision"],
            "new_endpoint_calls": fo["forecast"]["new_endpoint_calls"],
        },
        "replication": {
            "eleven": ind[3]["summary"]["eleven_end_on_advisory"],
            "seven": ind[3]["summary"]["seven_actually_switch"],
            "eight_cell_signatures": ind[3]["eight_cell_signatures"],
            "stability": ind[3]["stability"],
            "new_endpoint_calls": ind[3]["new_endpoint_calls"],
        },
    }
    ck(rep is not None, "missing fresh-panel score")
    obs = []
    prompts = {}
    lookup = {}
    for i in (5, 4):
        plan = read(i, "freeze.json")
        rec = read(i, "attempt/receipt.json")
        pack = read(i, "packet.json")
        trials = journal(i, "attempt/results.jsonl")
        cpu = read(i, "cpu_replay.json")
        score = read(i, "score.json")
        f = plan["outline"]["files"]
        proto = raw(i, "protocol.json")
        label = "joint" if i == 5 else "cue"
        files[label + "_protocol.json"] = proto
        ck(
            rec["state"] == "complete"
            and rec["plan"] == digest(i, "freeze.json")
            and f["protocol.json"] == sha(proto)
            and f["packet.json"] == digest(i, "packet.json")
            and rec["artifacts"]["results.jsonl"] == digest(i, "attempt/results.jsonl")
            and rec["counts"]["logical_trials_completed"] == len(trials)
            and rec["counts"]["physical_forwards_completed"]
            == sum(x["out"]["physical_forward_calls"] for x in trials)
            and cpu["receipt_sha256"]
            == score["receipt_sha256"]
            == digest(i, "attempt/receipt.json")
            and ind[i]["score_sha256"] == digest(i, "score.json")
            and ind[i]["cpu_replay_sha256"] == digest(i, "cpu_replay.json"),
            "sealed intervention source",
        )
        context[label + "_run"] = {
            "generations": len(trials),
            "forwards": rec["counts"]["physical_forwards_completed"],
            "endpoint_calls": score["new_endpoint_calls"],
            "cpu_replay_attestation": cpu,
        }
        here = {}
        if i == 5:
            amendment = raw(i, "preflight_amendment.json")
            ck(f["preflight_amendment.json"] == sha(amendment), "preflight correction")
            files["preflight_amendment.json"] = amendment
        for q in pack:
            text = q["text"] if i == 5 else q["prompt_text"]
            sig = sha(text.encode())
            ck(sig == q.get("sha256", q.get("prompt_sha256")), "prompt digest")
            if i == 5:
                ck(sig not in lookup and q["cell"] not in prompts, "duplicate joint prompt")
                lookup[sig] = q["cell"]
                prompts[q["cell"]] = text
            here[q["cell"]] = (lookup[sig], sig)
        for v in trials:
            j, o = v["job"], v["out"]
            c, sig = here[j["c"] if i == 5 else j["cell"]]
            ck(o["prompt_sha256"] == sig and o["operation_id"] == j["id"], "trial binding")
            u = o["model_unit_id"]
            ck(
                u == j.get("u", j.get("unit")) and u in {"unit-gpt2-mixed", "unit-gpt2-semantic"},
                "checkpoint",
            )
            arm = "base"
            if j["kind"] != "base":
                if i == 5:
                    arm = ":".join((j["cm"], j["route"], j["km"]))
                else:
                    factor = {"surface_cue": "cue", "answer_codebook": "map"}[j["factor"]]
                    mode = {
                        "self_sham": "S",
                        "targeted_interchange": "T",
                        "norm_matched_rotation": "N",
                    }[j["condition"]]
                    arm = factor + str(j["layer"]) + ":" + mode
            ck(re.fullmatch(r"\s*(?:FINAL: )?[AB]\s*", o["text"]), "unreviewed non-symbol output")
            obs.append([label, u.rsplit("-", 1)[1], c, arm, o["text"], o["physical_forward_calls"]])
    api = []
    ap = read(1, "plan.json")
    rec = read(1, "api/receipt.json")
    outcomes = journal(1, "api/observations.jsonl")
    ck(
        rec["status"] == "complete"
        and rec["plan_sha256"] == ind[1]["plan_sha256"] == digest(1, "plan.json")
        and rec["artifacts"]["observations.jsonl"] == digest(1, "api/observations.jsonl"),
        "API source",
    )
    req = {q["qid"]: q for q in ap["requests"]}
    for v in outcomes:
        q = req[v["qid"]]
        ck(
            v["body_sha256"] == q["body_sha256"]
            and v["status"] == "completed"
            and not v["refusal"]
            and re.fullmatch(r"\s*(?:FINAL: )?[AB]\s*", v["text"]),
            "dispatch/outcome binding",
        )
        key = "luna/" + q["cell"]
        prompts.setdefault(key, q["prompt_text"])
        ck(prompts[key] == q["prompt_text"], "conflicting prompts")
        api.append([key, q["rep"], v["text"]])
    files.update(
        {
            "prompts.jsonl": rows(prompts.items()),
            "trials.jsonl": rows(obs),
            "luna.jsonl": rows(api),
            "context.json": obj(context),
            "source_hashes.json": obj(used),
        }
    )
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source", type=Path, help="private root containing the six measured study directories"
    )
    parser.add_argument(
        "--out", type=Path, help="create a NEW directory; default verifies the committed export"
    )
    a = parser.parse_args()
    files = project(a.source)
    files["manifest.json"] = obj({n: sha(b) for n, b in files.items()})
    if a.out:
        a.out.mkdir(parents=True, exist_ok=False)
        for n, b in files.items():
            (a.out / n).write_bytes(b)
    else:
        for n, b in files.items():
            ck((HERE / "data" / n).read_bytes() == b, "export differs: " + n)
    print("Verified projection of six retained studies.")


if __name__ == "__main__":
    main()
