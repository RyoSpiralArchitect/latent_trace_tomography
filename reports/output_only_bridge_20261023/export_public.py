"""Explicit allowlist export from the retained private run. No network or model calls."""

import argparse
import json
from pathlib import Path

from replay import ARCHIVE, a, b, digest


def verify_retained_bytes(root, manifest):
    """This exporter is for the reviewed checkpoint, not arbitrary future runs.

    Copied summaries and nested plan metadata must match the reviewed bytes.
    Reject additions before creating an output directory; an allowlisted outer
    key alone does not prevent private fields from leaking through nested values.
    """
    b.check(manifest["format"] == "ltt_public_checkpoint_v1", "unknown checkpoint format")
    bindings = {"plan.json": manifest["retained_plan_sha256"]}
    for name, sha in manifest["retained_result_sha256"].items():
        bindings[name + "/results.jsonl"] = sha
    for name in (
        "forecast_lock.json",
        "analysis.json",
        "verification.json",
        "posthoc_format_diagnostic.json",
    ):
        retained = name if name == "forecast_lock.json" else "analysis-v1/" + name
        bindings[retained] = manifest["published_files"][name]
    for name, sha in bindings.items():
        b.check(digest(root / name) == sha, "unreviewed retained export input: " + name)


def export(root, output):
    manifest = b.read(Path(__file__).with_name("data") / "manifest.json")
    verify_retained_bytes(root, manifest)
    plan_path = root / "plan.json"
    plan, plan_sha = b.read(plan_path), digest(plan_path)
    b.validate(plan)
    reference, reference_audit = a.verify_furnace(root, plan, plan_sha)
    weak, weak_audit = a.verify_api(root, "weak", plan, plan_sha, None)
    lock_path = root / "forecast_lock.json"
    challenge, challenge_audit = a.verify_api(root, "challenge", plan, plan_sha, digest(lock_path))
    lock = b.read(lock_path)
    for key, value in a.replay_forecast(plan, reference, weak).items():
        b.check(lock[key] == value, "retained forecast replay failed")
    b.check(
        lock["furnace_receipt_sha256"] == reference_audit["receipt_sha256"]
        and lock["weak_receipt_sha256"] == weak_audit["receipt_sha256"],
        "retained lock inputs changed",
    )
    verification = b.read(root / "analysis-v1/verification.json")
    b.check(
        verification["furnace"] == reference_audit
        and verification["api_weak"] == weak_audit
        and verification["api_challenge"] == challenge_audit,
        "retained verification mismatch",
    )
    output.mkdir(mode=0o700)
    fields = (
        "scope",
        "script_sha256",
        "contract_sha256",
        "targets",
        "api_target_id",
        "api_model",
        "api_price_cap_usd",
        "api_reserved_ceiling_usd",
        "panel",
    )
    b.write_new(output / "inventory.json", {field: plan[field] for field in fields})
    with (output / "observations.jsonl").open("x") as stream:
        for row in reference + weak + challenge:
            b.check(set(row["observation"]) == b.FIELDS, "unexpected observation fields")
            stream.write(b.canonical(row["observation"]) + "\n")
    copies = {
        "forecast_lock.json": lock_path,
        "analysis.json": root / "analysis-v1/analysis.json",
        "verification.json": root / "analysis-v1/verification.json",
        "posthoc_format_diagnostic.json": root / "analysis-v1/posthoc_format_diagnostic.json",
    }
    for name, source in copies.items():
        with (output / name).open("xb") as stream:
            stream.write(source.read_bytes())
    manifest = {
        "format": "ltt_public_checkpoint_v1",
        "retained_plan_sha256": plan_sha,
        "published_files": {path.name: digest(path) for path in sorted(output.iterdir())},
        "archived_source_sha256": {
            name: digest(ARCHIVE / name)
            for name in (
                "README.md",
                "bridge.py",
                "analyze_saved.py",
                "diagnose_format.py",
                "test_bridge.py",
                "test_analysis.py",
            )
        },
        "retained_result_sha256": {
            name: digest(root / name / "results.jsonl")
            for name in ("furnace-attempt-001", "api-weak-attempt-001", "api-challenge-attempt-001")
        },
        "export_policy": "six-field observations and allowlisted task inventory; no host paths, credentials, response IDs, or token/activation telemetry",
        "scope": "public derived export, not a replacement for the retained plan, results, or receipts",
        "claim_ceiling": "replayable behavioral observations, original abstention, and separately labeled post-hoc diagnosis",
        "new_model_calls": 0,
    }
    b.write_new(output / "manifest.json", manifest)
    print(
        json.dumps(
            {
                "status": "exported",
                "observations": len(reference + weak + challenge),
                "new_model_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retained-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.retained_root, args.output)
