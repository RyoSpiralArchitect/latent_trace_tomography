"""V2 output-only reference sets: answer content is separate from format compliance.

This additive, model-free successor does not change the frozen v1 parser or results.
Reference envelopes describe finite observed references, not calibrated probabilities
or recovered mechanisms. Input bundles cannot contain target challenge outputs.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path


WEAK_ROLES = (
    "weak_baseline",
    "weak_rule_paraphrase",
    "weak_evidence_reorder",
    "weak_irrelevant_distractor",
    "weak_cue_salience_attenuation",
)
CHALLENGE_ROLES = ("challenge_conflict", "challenge_table")
SLOT_FIELDS = {"case_id", "projection_id", "replicate_id", "prompt_text"}
TEXT_FIELDS = SLOT_FIELDS | {"target_id", "output_text"}
FORMAT_STATES = ("exact_marker", "bare_symbol", "unresolved")
BUNDLE_FIELDS = {
    "schema_version",
    "weak_inventory",
    "challenge_inventory",
    "target_weak",
    "reference_weak",
    "reference_challenge",
    "reference_clusters",
}
RULES = {
    "version": "output_only_bridge_v2",
    "normalization": "strip outer whitespace; accept exact FINAL: A/B or bare A/B only",
    "format_channel": list(FORMAT_STATES),
    "matching": "all case-aligned canonical weak answers equal; no format covariates",
    "unresolved_target": "abstain",
    "unresolved_reference": "retain in accounting, exclude from support",
    "empty_support": "abstain",
    "single_support": "not a unique mechanism",
    "envelope": "per-slot observed output set over matching references; no probabilities",
    "target_challenge_inputs": "forbidden",
}


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _hash(value: object) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def parse_channels(text: str) -> dict:
    """A/B aliases change the content channel only, never format compliance."""
    _check(type(text) is str, "output_text must be a string")
    stripped = text.strip()
    if stripped in ("FINAL: A", "FINAL: B"):
        return {"answer": stripped[-1], "format": "exact_marker"}
    if stripped in ("A", "B"):
        return {"answer": stripped, "format": "bare_symbol"}
    return {"answer": None, "format": "unresolved"}


def _key(row: dict) -> tuple[str, str, str]:
    return row["case_id"], row["projection_id"], row["replicate_id"]


def _inventory(rows: list, roles: tuple[str, ...]) -> dict:
    _check(type(rows) is list and bool(rows), "inventory must be a nonempty list")
    index, groups = {}, {}
    for row in rows:
        _check(type(row) is dict and set(row) == SLOT_FIELDS, "invalid inventory fields")
        _check(all(type(v) is str and bool(v) for v in row.values()), "invalid inventory text")
        _check(row["projection_id"] in roles, "wrong observation phase")
        key = _key(row)
        _check(key not in index, "duplicate inventory slot")
        index[key] = row
        groups.setdefault((row["case_id"], row["replicate_id"]), set()).add(row["projection_id"])
    _check(all(group == set(roles) for group in groups.values()), "incomplete projection orbit")
    return dict(sorted(index.items()))


def _observations(rows: list, inventory: dict, expected_target: str | None = None) -> dict:
    _check(type(rows) is list and len(rows) == len(inventory), "observation inventory incomplete")
    indexed, targets = {}, set()
    for row in rows:
        _check(type(row) is dict and set(row) == TEXT_FIELDS, "non-output-only observation fields")
        _check(all(type(v) is str for v in row.values()), "observation values must be strings")
        _check(bool(row["target_id"]), "empty target identity")
        key = _key(row)
        _check(key in inventory and key not in indexed, "duplicate or unplanned observation")
        _check(row["prompt_text"] == inventory[key]["prompt_text"], "prompt differs from inventory")
        targets.add(row["target_id"])
        indexed[key] = row
    _check(len(targets) == 1, "observations must contain one target")
    _check(expected_target is None or targets == {expected_target}, "target identity mismatch")
    return dict(sorted(indexed.items()))


def _channels(index: dict) -> tuple[tuple, dict]:
    parsed = [parse_channels(row["output_text"]) for row in index.values()]
    counts = Counter(item["format"] for item in parsed)
    return tuple(item["answer"] for item in parsed), {
        "n": len(parsed),
        "formats": {state: counts[state] for state in FORMAT_STATES},
        "unresolved_answers": sum(item["answer"] is None for item in parsed),
    }


def build_reference_report(bundle: dict) -> dict:
    """Pure inference from target weak outputs and reference weak/challenge outputs.

    A case-aligned trace is matched, not only its marginal counts. The supplied
    reference cluster map is provenance for accounting; it cannot affect matches.
    Malformed/incomplete data raise errors rather than becoming scientific abstention.
    """
    _check(
        type(bundle) is dict and set(bundle) == BUNDLE_FIELDS,
        "invalid bundle; target challenges and extra fields are forbidden",
    )
    _check(bundle["schema_version"] == "ltt_output_bridge_v2_inputs_v1", "unknown bundle schema")
    weak_slots = _inventory(bundle["weak_inventory"], WEAK_ROLES)
    challenge_slots = _inventory(bundle["challenge_inventory"], CHALLENGE_ROLES)
    target = _observations(bundle["target_weak"], weak_slots)
    target_id = next(iter(target.values()))["target_id"]
    refs, challenges, clusters = (
        bundle[name] for name in ("reference_weak", "reference_challenge", "reference_clusters")
    )
    _check(
        all(type(v) is dict for v in (refs, challenges, clusters)), "reference mappings required"
    )
    _check(
        bool(refs) and set(refs) == set(challenges) == set(clusters), "reference cohort incomplete"
    )
    _check(all(type(k) is str and bool(k) for k in refs), "invalid reference identity")
    _check(target_id not in refs, "target cannot be its own reference")
    _check(all(type(v) is str and bool(v) for v in clusters.values()), "invalid reference cluster")
    target_answers, target_summary = _channels(target)
    summaries, support, reference_hashes, reference_challenge_hashes = {}, [], {}, {}
    reference_challenge_rows = {}
    for ref_id in sorted(refs):
        weak = _observations(refs[ref_id], weak_slots, ref_id)
        challenge = _observations(challenges[ref_id], challenge_slots, ref_id)
        answers, summary = _channels(weak)
        reason = None
        if None in answers:
            reason = "unresolved_reference_answers"
        elif answers != target_answers:
            reason = "different_case_aligned_answers"
        if reason is None and None not in target_answers:
            support.append(ref_id)
        summaries[ref_id] = {**summary, "excluded_reason": reason}
        reference_hashes[ref_id] = _hash(list(weak.values()))
        reference_challenge_hashes[ref_id] = _hash(list(challenge.values()))
        reference_challenge_rows[ref_id] = challenge

    if None in target_answers:
        status = "abstain_unresolved_target_answers"
    elif not support:
        status = "abstain_outside_reference_support"
    else:
        status = "matching_reference_set"
    envelope = []
    for key, slot in challenge_slots.items():
        observed = {
            ref_id: parse_channels(reference_challenge_rows[ref_id][key]["output_text"])
            for ref_id in support
        }
        states = sorted({item["answer"] or "unresolved" for item in observed.values()})
        envelope.append(
            {
                **{name: slot[name] for name in ("case_id", "projection_id", "replicate_id")},
                "observed_answer_set": states if support else None,
                "reference_answers_and_formats": observed,
                "ambiguous_within_reference_set": len(states) > 1 if support else None,
            }
        )
    return {
        "schema_version": "ltt_output_bridge_v2_report_v1",
        "rules_sha256": _hash(RULES),
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "evidence_tier": "development_only_not_prospective_validation",
        "status": status,
        "target_id": target_id,
        "target_channels": target_summary,
        "reference_channels": summaries,
        "support_targets": support,
        "reference_count": len(refs),
        "declared_reference_cluster_count": len(set(clusters.values())),
        "support_clusters": sorted({clusters[ref_id] for ref_id in support}),
        "mechanism_attribution": "not_attempted_even_for_single_match",
        "challenge_envelope": envelope,
        "envelope_interpretation": "finite reference output sets, not probabilities or guaranteed future coverage",
        "input_commitments": {
            "weak_inventory_sha256": _hash(list(weak_slots.values())),
            "challenge_inventory_sha256": _hash(list(challenge_slots.values())),
            "target_weak_sha256": _hash(list(target.values())),
            "reference_weak_sha256": reference_hashes,
            "reference_challenge_sha256": reference_challenge_hashes,
            "reference_clusters_sha256": _hash(clusters),
        },
        "new_model_calls": 0,
    }


def _unique(pairs):
    value = {}
    for key, item in pairs:
        _check(key not in value, "duplicate JSON key")
        value[key] = item
    return value


def write_new_report(path: Path, report: dict) -> None:
    """Refuse to overwrite any existing forecast/result artifact."""
    with path.open("x") as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    bundle = json.loads(args.bundle.read_text(), object_pairs_hook=_unique)
    report = build_reference_report(bundle)
    write_new_report(args.out, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "support_targets": report["support_targets"],
                "evidence_tier": report["evidence_tier"],
                "new_model_calls": 0,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
