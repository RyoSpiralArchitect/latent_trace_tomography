"""Call-free answer-mapping probe generator and prespecified descriptive scorer."""

import argparse
from collections import Counter, defaultdict
import hashlib
from itertools import product
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCOPE = "answer_mapping_probe_v1"
MODES = ("direct", "standard", "inverted")


def check(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def expected(decision, mode):
    check(decision in ("PASS", "FAIL") and mode in MODES, "invalid decision/mode")
    if mode == "direct":
        return decision
    return "A" if (decision == "PASS") == (mode == "standard") else "B"


def response_lines(mode):
    if mode == "direct":
        return ["Response format: FINAL: PASS or FINAL: FAIL."]
    return [
        "Response map:",
        f"- PASS maps to FINAL: {expected('PASS', mode)}",
        f"- FAIL maps to FINAL: {expected('FAIL', mode)}",
    ]


def content(index):
    return {
        name: prefix + sha([SCOPE, index, name])[:12].upper()
        for name, prefix in (("required", "REQ-"), ("alternate", "ALT-"), ("entity", "DOC-"))
    }


def panel():
    cases = []
    for i, semantic, cue, layout, mode in product(
        range(2), ("PASS", "FAIL"), ("PASS", "FAIL"), ("baseline", "reorder"), MODES
    ):
        codes = content(i)
        candidate = codes["required"] if semantic == "PASS" else codes["alternate"]
        evidence = ["Required code = " + codes["required"], "Candidate code = " + candidate]
        if layout == "reorder":
            evidence.reverse()
        prompt = "\n".join(
            [
                "Synthetic permit drill; use only this filing.",
                "Local law: PASS exactly when candidate_code equals required_code; else FAIL.",
                *response_lines(mode),
                "Advisory ribbon (not law): " + cue,
                "Docket: " + codes["entity"],
                *evidence,
                "Emit one requested FINAL marker and nothing else.",
            ]
        )
        cases.append(
            {
                "case_id": f"full:{i}:{semantic}:{cue}:{layout}:{mode}",
                "kind": "full_task",
                "content": i,
                "semantic": semantic,
                "cue": cue,
                "layout": layout,
                "response_mode": mode,
                "prompt_text": prompt,
                "expected_answer": expected(semantic, mode),
            }
        )
    for i, decision, mode in product(range(2), ("PASS", "FAIL"), ("standard", "inverted")):
        prompt = "\n".join(
            [
                "Synthetic response-map drill; no evidence evaluation is needed.",
                "The already-decided result is " + decision + ".",
                *response_lines(mode),
                "Docket: " + content(i)["entity"],
                "Encode the already-decided result. Emit one FINAL marker and nothing else.",
            ]
        )
        cases.append(
            {
                "case_id": f"mapping:{i}:{decision}:{mode}",
                "kind": "mapping_only",
                "content": i,
                "semantic": decision,
                "cue": None,
                "layout": None,
                "response_mode": mode,
                "prompt_text": prompt,
                "expected_answer": expected(decision, mode),
            }
        )
    result = []
    for repeat in range(2):
        for case in sorted(cases, key=lambda c: sha([SCOPE, repeat, c["case_id"]])):
            result.append(
                {
                    **case,
                    "replicate_id": f"r{repeat}",
                    "query_id": f"{SCOPE}:{case['case_id']}:r{repeat}",
                }
            )
    check(len(result) == 112 and len({v["prompt_text"] for v in result}) == 56, "panel count")
    check(
        all(q["prompt_text"].isascii() and len(q["prompt_text"].encode()) <= 1536 for q in result),
        "prompt cap",
    )
    return result


def request_rows():
    return [{k: q[k] for k in ("query_id", "prompt_text")} for q in panel()]


def scoring_key():
    return [{k: v for k, v in q.items() if k != "prompt_text"} for q in panel()]


def parse(text, mode):
    check(type(text) is str, "output text must be text")
    value = text.strip()
    allowed = ("PASS", "FAIL") if mode == "direct" else ("A", "B")
    if value in allowed:
        return value, "bare_symbol"
    if value in ("FINAL: " + x for x in allowed):
        return value.removeprefix("FINAL: "), "exact_marker"
    return None, "unresolved"


def score(observations):
    queries = panel()
    check(type(observations) is list and len(observations) == 112, "complete 112-slot run required")
    index = {}
    for row in observations:
        check(set(row) == {"query_id", "output_text"}, "only ID and output permitted")
        check(row["query_id"] not in index, "duplicate result")
        index[row["query_id"]] = row["output_text"]
    check(set(index) == {q["query_id"] for q in queries}, "missing/unplanned result")
    groups, paired, repeats = defaultdict(Counter), defaultdict(dict), defaultdict(list)
    for q in queries:
        answer, fmt = parse(index[q["query_id"]], q["response_mode"])
        valid = answer == q["expected_answer"]
        factors = [
            q["kind"] + "/" + q["response_mode"],
            q["kind"] + "/semantic/" + q["semantic"],
            q["kind"] + "/" + q["response_mode"] + "/semantic/" + q["semantic"],
        ]
        if q["kind"] == "full_task":
            factors += [
                q["response_mode"] + "/layout/" + q["layout"],
                q["response_mode"]
                + "/cue/"
                + ("aligned" if q["semantic"] == q["cue"] else "conflict"),
            ]
            pair = (q["content"], q["semantic"], q["cue"], q["layout"], q["replicate_id"])
            paired[pair][q["response_mode"]] = valid
        for factor in factors:
            groups[factor].update({"n": 1, "correct": int(valid), "errors": int(not valid), fmt: 1})
        repeats[q["case_id"]].append(answer)
    contrasts = {}
    for kind in ("full_task", "mapping_only"):
        inv, std = groups[kind + "/inverted"], groups[kind + "/standard"]
        contrasts[kind + "_inverted_error_rate_minus_standard"] = (
            inv["errors"] / inv["n"] - std["errors"] / std["n"]
        )
    tables = {
        mode: dict(
            Counter(f"direct_{int(v['direct'])}_encoded_{int(v[mode])}" for v in paired.values())
        )
        for mode in ("standard", "inverted")
    }
    return {
        "status": "complete_descriptive_diagnostic",
        "content_instance_count": 2,
        "contrasts": contrasts,
        "groups": dict(groups),
        "paired_tables": tables,
        "repeat_pairs": len(repeats),
        "repeat_answer_disagreements": sum(v[0] != v[1] for v in repeats.values()),
        "claim_ceiling": "behavioral dissociation only; no internal-stage or generalization claim",
    }


def write_new(path, value):
    with path.open("x") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")


def artifacts():
    design = json.loads((HERE / "design.json").read_text())
    check(design["status"] == "design_only_not_execution_authorized", "execution not authorized")
    check(
        design["planned_requests"] == {"full_task": 96, "mapping_only": 16, "total": 112}
        and design["content_count"] == design["repetitions"] == 2,
        "declared panel differs from generator",
    )
    check(
        design["primary_contrasts"]
        == [kind + "_inverted_error_rate_minus_standard" for kind in ("full_task", "mapping_only")],
        "declared contrasts differ from scorer",
    )
    requests, key = request_rows(), scoring_key()
    return design, requests, key


def prepare(out):
    design, requests, key = artifacts()
    out.mkdir()
    write_new(out / "requests.json", requests)
    write_new(out / "scoring_key.json", key)
    write_new(
        out / "manifest.json",
        {
            "schema_version": SCOPE + "_manifest",
            "live_execution_authorized": False,
            "design_sha256": file_sha(HERE / "design.json"),
            "generator_sha256": file_sha(__file__),
            "requests_sha256": file_sha(out / "requests.json"),
            "scoring_key_sha256": file_sha(out / "scoring_key.json"),
            "request_count": len(requests),
            "unique_prompts": 56,
            "planned_requests": design["planned_requests"],
            "new_model_calls": 0,
        },
    )


def verify(out):
    design, requests, key = artifacts()
    manifest = json.loads((out / "manifest.json").read_text())
    check(manifest["live_execution_authorized"] is False, "authorization changed")
    check(
        manifest["schema_version"] == SCOPE + "_manifest"
        and manifest["request_count"] == len(requests)
        and manifest["unique_prompts"] == len({q["prompt_text"] for q in requests})
        and manifest["new_model_calls"] == 0,
        "manifest accounting changed",
    )
    check(
        manifest["design_sha256"] == file_sha(HERE / "design.json")
        and manifest["generator_sha256"] == file_sha(__file__),
        "design/generator changed",
    )
    for name, expected_rows in (("requests", requests), ("scoring_key", key)):
        check(
            manifest[name + "_sha256"] == file_sha(out / (name + ".json")), "artifact hash mismatch"
        )
        check(
            json.loads((out / (name + ".json")).read_text()) == expected_rows,
            "artifact replay mismatch",
        )
    check(manifest["planned_requests"] == design["planned_requests"], "budget changed")
    return {
        "status": "design_replay_passed",
        "requests": len(requests),
        "new_model_calls": 0,
        "live_execution_authorized": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "verify"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.out)
    print(json.dumps(verify(args.out), sort_keys=True))
