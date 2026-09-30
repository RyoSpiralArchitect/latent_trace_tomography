from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from latent_trace_tomography.oss_design import (
    DEFAULT_CONTENT_SEED_COUNT,
    DEFAULT_MASTER_SEED,
    OSSDesignConfig,
    build_design_summary,
)
from latent_trace_tomography.protocol import preflight_protocol


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ltt",
        description="Latent Trace Tomography research harness",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser(
        "preflight",
        help="Lint a protocol contract and optional manifest without model calls",
    )
    preflight.add_argument("--protocol", type=Path, required=True)

    design_summary = subparsers.add_parser(
        "oss-design-summary",
        help="Render the deterministic OSS-1 generator conformance summary without model calls",
    )
    design_summary.add_argument("--master-seed", type=int, default=DEFAULT_MASTER_SEED)
    design_summary.add_argument(
        "--content-seed-count", type=int, default=DEFAULT_CONTENT_SEED_COUNT
    )

    demo = subparsers.add_parser(
        "synthetic-demo", help="Run the text-only dual-route calibration demo"
    )
    demo.add_argument("--out-dir", type=Path, required=True)
    demo.add_argument("--seed", type=int, default=7)
    demo.add_argument("--cases", type=int, default=48)
    demo.add_argument("--samples", type=int, default=3)
    demo.add_argument("--calibration-targets-per-regime", type=int, default=6)
    demo.add_argument("--evaluation-targets-per-regime", type=int, default=3)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "preflight":
        result = preflight_protocol(args.protocol)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["ok"] else 2
    if args.command == "oss-design-summary":
        summary = build_design_summary(
            OSSDesignConfig(
                master_seed=args.master_seed,
                content_seed_count=args.content_seed_count,
            )
        )
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    if args.command == "synthetic-demo":
        from latent_trace_tomography.demo import run_synthetic_demo

        summary = run_synthetic_demo(
            args.out_dir,
            seed=args.seed,
            cases=args.cases,
            samples=args.samples,
            calibration_targets_per_regime=args.calibration_targets_per_regime,
            evaluation_targets_per_regime=args.evaluation_targets_per_regime,
        )
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if summary["all_regression_gates_passed"] else 1
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
