"""Call-free publication of the retained 96-request output-contract design."""

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCOPE = "output_contract_probe_v1"
PARENT = HERE.parent / "answer_mapping_probe_v1"
PARENT_SHA = "e7a9cd3aa6aa5c78a6d53fe9274148c81323ab25c2de36deee76a18521cbbf5e"
RETAINED = {
    "design.json": "aa93b8ed29657e66f84c6858cc08e2cd1af536590ceffca34f4413ac94715acc",
    "requests.json": "f074cbc1d8199f10c7ad371f6606d45dbb364d15a804720fa769a217d83e4dee",
    "scoring_key.json": "d55a4154273e3211b1cb0546720d86a54a53527db2ba026fa54a7d0fd8278d01",
}


def check(value, reason):
    if not value:
        raise ValueError(reason)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def parent():
    check(digest(PARENT / "design.py") == PARENT_SHA, "parent source changed")
    spec = importlib.util.spec_from_file_location("retained_mapping_design", PARENT / "design.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.verify(PARENT / "fixtures")
    return module


def bare_prompt(query, module):
    text = query["prompt_text"]
    for decision in ("PASS", "FAIL"):
        symbol = module.expected(decision, query["response_mode"])
        old = f"- {decision} maps to FINAL: {symbol}"
        check(text.count(old) == 1, "map edit count")
        text = text.replace(old, f"- {decision} maps to {symbol}")
    old = (
        "Emit one requested FINAL marker and nothing else."
        if query["kind"] == "full_task"
        else "Encode the already-decided result. Emit one FINAL marker and nothing else."
    )
    new = "Emit exactly A or B, with no prefix, punctuation, or other text."
    if query["kind"] == "mapping_only":
        new = "Encode the already-decided result. " + new
    check(text.count(old) == 1, "instruction edit count")
    return text.replace(old, new)


def panel():
    module = parent()
    base = [
        q
        for q in module.panel()
        if q["replicate_id"] == "r0"
        and q["response_mode"] in ("standard", "inverted")
        and (q["kind"] == "mapping_only" or q["layout"] == "baseline")
    ]
    check(len(base) == 24, "base count")
    cases = []
    for query in base:
        for render in ("marker", "bare"):
            text = query["prompt_text"] if render == "marker" else bare_prompt(query, module)
            check(text.isascii() and len(text.encode()) <= 1536, "prompt bound")
            cases.append(
                {
                    "case_id": query["case_id"] + ":" + render,
                    "parent_case_id": query["case_id"],
                    **{
                        k: query[k]
                        for k in (
                            "kind",
                            "content",
                            "semantic",
                            "cue",
                            "layout",
                            "response_mode",
                            "expected_answer",
                        )
                    },
                    "render_mode": render,
                    "prompt_text": text,
                }
            )
    result = []
    for repeat in range(2):
        for query in sorted(cases, key=lambda q: sha([SCOPE, repeat, q["case_id"]])):
            result.append(
                {
                    **query,
                    "replicate_id": f"r{repeat}",
                    "query_id": f"{SCOPE}:{query['case_id']}:r{repeat}",
                }
            )
    check(len(result) == len({q["query_id"] for q in result}) == 96, "slot count")
    check(len({q["prompt_text"] for q in result}) == 48, "prompt count")
    check(
        Counter(q["kind"] for q in result) == {"full_task": 64, "mapping_only": 32}, "kind counts"
    )
    return result


def artifacts():
    check(digest(HERE / "design.json") == RETAINED["design.json"], "retained definition changed")
    definition = json.loads((HERE / "design.json").read_text())
    check(
        definition["live_execution_authorized"] is False and definition["new_model_calls"] == 0,
        "live boundary",
    )
    check(definition["status"] == "design_only_not_execution_ready", "readiness changed")
    queries = panel()
    return {
        "requests.json": [{k: q[k] for k in ("query_id", "prompt_text")} for q in queries],
        "scoring_key.json": [{k: v for k, v in q.items() if k != "prompt_text"} for q in queries],
    }


def write_new(path, value):
    with path.open("x") as stream:
        stream.write(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")


def prepare(out):
    expected = artifacts()
    out.mkdir()
    for name, value in expected.items():
        write_new(out / name, value)
        check(digest(out / name) == RETAINED[name], "retained panel differs")
    write_new(
        out / "manifest.json",
        {
            "schema_version": SCOPE + "_public_manifest",
            "live_execution_authorized": False,
            "new_model_calls": 0,
            "generator_sha256": digest(__file__),
            "parent_generator_sha256": PARENT_SHA,
            "definition_sha256": RETAINED["design.json"],
            "request_count": 96,
            "unique_prompts": 48,
            "published_files": {name: digest(out / name) for name in expected},
            "scope": "Public generator re-expression; retained definition, request bytes and scoring-key bytes unchanged. No API client or live scorer is provided.",
        },
    )
    return verify(out)


def verify(out):
    expected = artifacts()
    manifest = json.loads((out / "manifest.json").read_text())
    check(manifest["schema_version"] == SCOPE + "_public_manifest", "manifest scope")
    check(
        manifest["live_execution_authorized"] is False and manifest["new_model_calls"] == 0,
        "authorization changed",
    )
    check(manifest["generator_sha256"] == digest(__file__), "generator changed")
    check(
        manifest["parent_generator_sha256"] == PARENT_SHA
        and manifest["definition_sha256"] == RETAINED["design.json"],
        "source pins changed",
    )
    check(manifest["request_count"] == 96 and manifest["unique_prompts"] == 48, "manifest counts")
    check(set(manifest["published_files"]) == set(expected), "inventory changed")
    check({p.name for p in out.iterdir()} == set(expected) | {"manifest.json"}, "unexpected file")
    for name, value in expected.items():
        check(json.loads((out / name).read_text()) == value, "panel replay differs")
        check(
            digest(out / name) == manifest["published_files"][name] == RETAINED[name],
            "panel hash changed",
        )
    return {
        "status": "design_replay_passed_not_execution_ready",
        "planned_requests": 96,
        "unique_prompts": 48,
        "new_model_calls": 0,
        "live_execution_authorized": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "verify"))
    parser.add_argument("--out", type=Path, default=HERE / "fixtures")
    args = parser.parse_args()
    print(
        json.dumps(
            prepare(args.out) if args.command == "prepare" else verify(args.out), sort_keys=True
        )
    )
