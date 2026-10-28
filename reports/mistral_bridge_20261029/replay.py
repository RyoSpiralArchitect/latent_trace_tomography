"""Replay the public Mistral checkpoint with no credentials, models or network."""

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
from itertools import product
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
V2 = REPO / "src/latent_trace_tomography/reference_bridge.py"
V2_SHA = "73172f26c9090115d771f233a27608de57489eeedc716a7be8416cb64bc32ac9"
spec = importlib.util.spec_from_file_location("checkpoint_reference_v2", V2)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
CELLS = tuple(product((True, False), repeat=3))
FILES = {"inventory.json", "observations.jsonl", "forecast.json", "execution.json", "analysis.json"}


def check(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(), object_pairs_hook=r._unique)


def records(path):
    raw = Path(path).read_text()
    check(raw.endswith("\n"), "truncated observations")
    return [json.loads(line, object_pairs_hook=r._unique) for line in raw.splitlines()]


def write_new(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def state(text):
    return r.parse_channels(text)["answer"] or "unresolved"


def oracle(query):
    """Cross-check generator factors against the actual prompt, not output text."""
    text = query["prompt_text"]
    required = re.search(r"^Required code = (.+)$", text, re.M)
    candidate = re.search(r"^Candidate code = (.+)$", text, re.M)
    if required and candidate:
        same = required.group(1) == candidate.group(1)
    else:
        table = re.search(r"^required_code \| candidate_code\n([^\n]+) \| ([^\n]+)$", text, re.M)
        check(table is not None, "missing evidence")
        same = table.group(1) == table.group(2)
    semantic, cue, identity = CELLS[query["cell"]]
    check(same == semantic, "task metadata differs from prompt")
    maps = dict(re.findall(r"^- (PASS|FAIL) maps to FINAL: ([AB])$", text, re.M))
    check(
        maps == {"PASS": "A" if identity else "B", "FAIL": "B" if identity else "A"},
        "response map differs from metadata",
    )
    expected = maps["PASS" if same else "FAIL"]
    return expected, maps["PASS" if cue else "FAIL"]


def bundle_for(inventory, observations):
    panel = inventory["panel"]
    check(len(panel) == 112 and len({q["query_id"] for q in panel}) == 112, "invalid panel")
    slots = {r._key(q): q for q in panel}
    check(len(slots) == 112, "duplicate panel slot")
    targets = set(inventory["reference_clusters"]) | {inventory["api_target_id"]}
    check(len(targets) == 10 and len(inventory["reference_clusters"]) == 9, "cohort changed")
    index = {t: {} for t in targets}
    for row in observations:
        check(set(row) == r.TEXT_FIELDS, "non-output-only observation")
        check(all(type(v) is str for v in row.values()), "nontext observation")
        target, key = row["target_id"], r._key(row)
        check(
            target in index and key in slots and key not in index[target], "duplicate/unplanned row"
        )
        check(row["prompt_text"] == slots[key]["prompt_text"], "prompt mismatch")
        index[target][key] = row
    check(all(set(rr) == set(slots) for rr in index.values()), "incomplete observations")
    bundle = {
        "schema_version": "ltt_output_bridge_v2_inputs_v1",
        "reference_clusters": inventory["reference_clusters"],
    }
    for phase in ("weak", "challenge"):
        queries = [q for q in panel if q["phase"] == phase]
        check(len(queries) == {"weak": 80, "challenge": 32}[phase], "phase count mismatch")
        bundle[phase + "_inventory"] = [{k: q[k] for k in r.SLOT_FIELDS} for q in queries]
        bundle["reference_" + phase] = {
            t: [index[t][r._key(q)] for q in queries]
            for t in sorted(inventory["reference_clusters"])
        }
    bundle["target_weak"] = [
        index[inventory["api_target_id"]][r._key(q)] for q in panel if q["phase"] == "weak"
    ]
    return bundle, index, slots


def finite_metrics(values, target):
    available = [k for k, v in values.items() if v]
    single = [k for k in available if len(values[k]) == 1 and values[k] != ["unresolved"]]
    return {
        "planned": len(values),
        "available": len(available),
        "contained": sum(target[k] in (v or []) for k, v in values.items()),
        "set_size_counts": {
            str(k): v for k, v in sorted(Counter(len(v or []) for v in values.values()).items())
        },
        "singleton_resolved": len(single),
        "singleton_resolved_correct": sum(target[k] in values[k] for k in single),
        "unresolved_singletons": sum(v == ["unresolved"] for v in values.values()),
    }


def calculate(inventory, observations):
    bundle, index, slots = bundle_for(inventory, observations)
    report = r.build_reference_report(
        bundle
    )  # Target challenge text is absent from this interface.
    target = index[inventory["api_target_id"]]
    challenge_keys = [r._key(q) for q in inventory["panel"] if q["phase"] == "challenge"]
    conditional = {r._key(v): v["observed_answer_set"] for v in report["challenge_envelope"]}
    baseline = {
        k: sorted({state(index[t][k]["output_text"]) for t in inventory["reference_clusters"]})
        for k in challenge_keys
    }
    target_states = {k: state(target[k]["output_text"]) for k in challenge_keys}
    oracle_stats, repeat_stats, errors = {}, {}, []
    for phase in ("weak", "challenge"):
        counts, projection, pairs = Counter(), defaultdict(Counter), defaultdict(list)
        for q in inventory["panel"]:
            if q["phase"] != phase:
                continue
            expected, cue = oracle(q)
            parsed = r.parse_channels(target[r._key(q)]["output_text"])
            values = {
                "n": 1,
                "task_correct": int(parsed["answer"] == expected),
                "cue_consistent": int(parsed["answer"] == cue),
            }
            counts.update(values)
            projection[q["projection_id"]].update(values)
            pairs[(q["content"], q["cell"], q["projection_id"])].append((q["prompt_text"], parsed))
            if parsed["answer"] != expected:
                errors.append(
                    {
                        k: q[k]
                        for k in (
                            "query_id",
                            "phase",
                            "content",
                            "cell",
                            "projection_id",
                            "replicate_id",
                        )
                    }
                    | {
                        "expected": expected,
                        "observed": parsed["answer"],
                        "format": parsed["format"],
                    }
                )
        oracle_stats[phase] = {**counts, "by_projection": dict(projection)}
        check(
            all(len(v) == 2 and v[0][0] == v[1][0] for v in pairs.values()),
            "non-identical repeat pair",
        )
        repeat_stats[phase] = {
            "paired_prompts": len(pairs),
            "answer_disagreements": sum(
                v[0][1]["answer"] != v[1][1]["answer"] for v in pairs.values()
            ),
            "format_disagreements": sum(
                v[0][1]["format"] != v[1][1]["format"] for v in pairs.values()
            ),
        }
    weak_keys = [k for k, q in slots.items() if q["phase"] == "weak"]
    distances = {
        t: sum(
            state(index[t][k]["output_text"]) != state(target[k]["output_text"]) for k in weak_keys
        )
        for t in sorted(inventory["reference_clusters"])
    }
    return {
        "primary": {
            "status": report["status"],
            "support_targets": report["support_targets"],
            "weak_channels": report["target_channels"],
            "conditional": finite_metrics(conditional, target_states),
            "unconditional_baseline": finite_metrics(baseline, target_states),
            "baseline_composition": dict(Counter(",".join(v) for v in baseline.values())),
            "challenge_formats": dict(
                Counter(
                    r.parse_channels(target[k]["output_text"])["format"] for k in challenge_keys
                )
            ),
        },
        "posthoc": {
            "task_oracle": oracle_stats,
            "task_errors": errors,
            "repeat_comparison": repeat_stats,
            "weak_reference_distances": distances,
        },
        "reference_report": report,
        "unconditional_baseline": [
            {
                "case_id": k[0],
                "projection_id": k[1],
                "replicate_id": k[2],
                "observed_answer_set": baseline[k],
            }
            for k in sorted(baseline)
        ],
    }


def verify(data):
    manifest = read(data / "manifest.json")
    check(manifest["schema_version"] == "ltt_mistral_public_checkpoint_v1", "unknown manifest")
    check(set(manifest["published_files"]) == FILES, "manifest file inventory changed")
    check({p.name for p in data.iterdir()} == FILES | {"manifest.json"}, "unexpected data file")
    check(digest(V2) == manifest["v2_sha256"] == V2_SHA, "v2 changed")
    for name, sha in manifest["published_files"].items():
        check(digest(data / name) == sha, "published hash mismatch: " + name)
    inventory, observations = read(data / "inventory.json"), records(data / "observations.jsonl")
    value = calculate(inventory, observations)
    check(r._hash(value) == r._hash(read(data / "analysis.json")), "analysis replay differs")
    forecast, execution = read(data / "forecast.json"), read(data / "execution.json")
    check(
        value["reference_report"] == forecast["reference_report"]
        and value["unconditional_baseline"] == forecast["unconditional_baseline"],
        "forecast changed",
    )
    times = execution["times"]
    check(
        times["weak_completed"]
        <= forecast["created_at"]
        <= times["challenge_claimed"]
        <= times["challenge_started"],
        "invalid local prospective ordering",
    )
    check(
        execution["generation_requests"] == 112 and execution["automatic_retries"] == 0,
        "execution accounting changed",
    )
    return {
        "status": "public_replay_passed",
        "observations": len(observations),
        "primary": value["primary"],
        "posthoc_task_oracle": value["posthoc"]["task_oracle"],
        "new_model_calls": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=HERE / "data")
    print(json.dumps(verify(parser.parse_args().data), sort_keys=True, indent=2))
