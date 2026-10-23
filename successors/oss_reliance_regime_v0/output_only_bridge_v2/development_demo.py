"""Use the already-revealed v1 checkpoint only as development data. No live calls."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from latent_trace_tomography.reference_bridge import (  # noqa: E402
    SLOT_FIELDS,
    build_reference_report,
    write_new_report,
)


def development_bundle(data):
    # Validate publication bytes; the source manifest is not an execution attestation.
    import hashlib

    manifest = json.loads((data / "manifest.json").read_text())
    for name in ("inventory.json", "observations.jsonl"):
        actual = hashlib.sha256((data / name).read_bytes()).hexdigest()
        if manifest["published_files"][name] != actual:
            raise ValueError("checkpoint input hash mismatch")
    plan = json.loads((data / "inventory.json").read_text())
    rows = [json.loads(line) for line in (data / "observations.jsonl").read_text().splitlines()]
    targets = [unit["target_id"] for unit in plan["targets"]]

    def weak(row):
        return row["projection_id"].startswith("weak_")

    bundle = {
        "schema_version": "ltt_output_bridge_v2_inputs_v1",
        "weak_inventory": [
            {key: q[key] for key in SLOT_FIELDS} for q in plan["panel"] if q["phase"] == "weak"
        ],
        "challenge_inventory": [
            {key: q[key] for key in SLOT_FIELDS} for q in plan["panel"] if q["phase"] == "challenge"
        ],
        "target_weak": [
            row for row in rows if row["target_id"] == plan["api_target_id"] and weak(row)
        ],
        "reference_weak": {
            target: [row for row in rows if row["target_id"] == target and weak(row)]
            for target in targets
        },
        "reference_challenge": {
            target: [row for row in rows if row["target_id"] == target and not weak(row)]
            for target in targets
        },
        "reference_clusters": {
            unit["target_id"]: unit["base_model_unit_id"] for unit in plan["targets"]
        },
    }
    return bundle


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data", type=Path, default=ROOT / "reports/output_only_bridge_20261023/data"
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = build_reference_report(development_bundle(args.data))
    write_new_report(args.out, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "support_targets": report["support_targets"],
                "target_channels": report["target_channels"],
                "evidence_tier": report["evidence_tier"],
                "new_model_calls": 0,
            },
            indent=2,
        )
    )
