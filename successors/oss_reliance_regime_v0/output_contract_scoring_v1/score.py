"""Score complete saved output-contract panels. No model, network or execution attestation."""

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path

DESIGN = Path(__file__).resolve().parent.parent / "output_contract_probe_v1"
# Verify executable source before import; the frozen generator then verifies its parent and fixtures.
GENERATOR_SHA = "ef715e106189daae301daf49621b041aa52c40cdf25f69523a5707fbc1782b73"
MANIFEST_SHA = "03c54627dbd6ee7ee79e4ca15879ad39c35c9700bcd3971ce4a188a14d2d1bf8"
PAIR_CELLS = ("both_success", "marker_only", "bare_only", "neither")


def check(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_inputs():
    source, fixtures = DESIGN / "design.py", DESIGN / "fixtures"
    check(digest(source) == GENERATOR_SHA, "frozen design source mismatch")
    check(digest(fixtures / "manifest.json") == MANIFEST_SHA, "frozen design manifest mismatch")
    spec = importlib.util.spec_from_file_location("frozen_contract_design", source)
    design = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(design)
    design.verify(fixtures)
    key = json.loads((fixtures / "scoring_key.json").read_text())
    requests = json.loads((fixtures / "requests.json").read_text())
    contract = json.loads((DESIGN / "design.json").read_text())["scoring_contract"]
    return requests, key, contract, design.parent().parse


def _unique(pairs):
    row = {}
    for k, v in pairs:
        check(k not in row, "duplicate JSON field")
        row[k] = v
    return row


def read_rows(path):
    # One object per JSONL line; never extract an answer from malformed input.
    with path.open(encoding="utf-8") as lines:
        return [json.loads(line, object_pairs_hook=_unique) for line in lines]


def score(observations):
    _, key, contract, parse = frozen_inputs()
    check(
        type(observations) is list and len(observations) == len(key),
        "complete 96-slot run required",
    )
    texts = {}
    for row in observations:
        check(
            type(row) is dict and set(row) == {"query_id", "output_text"},
            "only ID and text permitted",
        )
        qid, text = row["query_id"], row["output_text"]
        check(type(qid) is str and type(text) is str, "ID and output must be text")
        check(qid not in texts, "duplicate slot")
        texts[qid] = text
    check(set(texts) == {q["query_id"] for q in key}, "unplanned or missing slot")

    total = Counter()
    by_render, by_map = defaultdict(Counter), defaultdict(Counter)
    pairs, repeats = defaultdict(dict), defaultdict(dict)
    for q in key:
        kind, render, mode = q["kind"], q["render_mode"], q["response_mode"]
        answer, fmt = parse(texts[q["query_id"]], mode)
        correct = answer == q["expected_answer"]
        complies = fmt == {"bare": "bare_symbol", "marker": "exact_marker"}[render]
        joint = correct and complies
        counts = {
            "n": 1,
            "answer_correct": int(correct),
            "answer_errors": int(not correct),
            "format_compliant": int(complies),
            "format_errors": int(not complies),
            "joint_success": int(joint),
            "joint_failures": int(not joint),
            "unresolved": int(answer is None),
        }
        for counter in (total, by_render[f"{kind}/{render}"], by_map[f"{kind}/{mode}/{render}"]):
            counter.update(counts)
        pairs[(kind, q["parent_case_id"], q["replicate_id"])][render] = joint
        repeats[(kind, q["case_id"])][q["replicate_id"]] = (answer, fmt)

    paired_tables, repeat_counts, primary = {}, {}, {}
    for kind, n in contract["primary_denominators_per_format"].items():
        cells = dict.fromkeys(PAIR_CELLS, 0)
        for (k, _, _), arms in pairs.items():
            if k == kind:
                cell = {
                    (True, True): "both_success",
                    (True, False): "marker_only",
                    (False, True): "bare_only",
                    (False, False): "neither",
                }[arms["marker"], arms["bare"]]
                cells[cell] += 1
        check(sum(cells.values()) == n, "paired denominator mismatch")
        paired_tables[kind] = cells
        marker, bare = by_render[f"{kind}/marker"], by_render[f"{kind}/bare"]
        check(marker["n"] == bare["n"] == n, "primary denominator mismatch")
        primary[f"{kind}_joint_failure_rate_bare_minus_marker"] = (
            bare["joint_failures"] - marker["joint_failures"]
        ) / n
        repeated = [v for (k, _), v in repeats.items() if k == kind]
        repeat_counts[kind] = {
            "pairs": len(repeated),
            "answer_disagreements": sum(v["r0"][0] != v["r1"][0] for v in repeated),
            "format_disagreements": sum(v["r0"][1] != v["r1"][1] for v in repeated),
        }
    check(set(primary) == set(contract["primary_contrasts"]), "unexpected contrasts")
    return {
        "schema_version": "ltt_output_contract_score_v1",
        "status": "complete_panel_scored_offline",
        "design_manifest_sha256": MANIFEST_SHA,
        "totals": dict(total),
        "by_kind_render": dict(by_render),
        "by_kind_map_render": dict(by_map),
        "primary_contrasts": primary,
        "paired_joint_success": paired_tables,
        "repeat_disagreements": repeat_counts,
        "claim_ceiling": "Descriptive output-interface scoring on two reused contents; no independent n=96, mechanism or execution attestation.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observations", type=Path, help="96 saved two-field JSONL records")
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                score(read_rows(args.observations)), indent=2, sort_keys=True, allow_nan=False
            )
        )
    except (OSError, ValueError) as exc:
        parser.exit(2, f"not scored: {exc}\n")
