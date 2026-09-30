from __future__ import annotations

import os
import platform
import random
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from latent_trace_tomography.features import (
    FeatureVector,
    build_feature_vectors,
    parse_final_answer,
)
from latent_trace_tomography.inference import CentroidAuditor, score_predictions
from latent_trace_tomography.io import (
    append_jsonl,
    build_manifest,
    sha256_file,
    sha256_json,
    sha256_tree,
    write_json,
    write_jsonl,
)
from latent_trace_tomography.protocol import preflight_protocol
from latent_trace_tomography.schema import (
    SCHEMA_VERSION,
    AuditPrediction,
    CalibrationLabel,
    ProjectionKind,
    ProjectionRole,
    Split,
    SyntheticRegime,
    TextObservation,
)
from latent_trace_tomography.synthetic import (
    SyntheticCase,
    SyntheticPhantom,
    generate_cases,
)


PROTOCOL_ID = "synthetic_projection_orbit_v1"
OBSERVATION_KINDS = {
    ProjectionKind.BASELINE,
    ProjectionKind.PARAPHRASE,
    ProjectionKind.REORDER,
    ProjectionKind.DISTRACTOR,
    ProjectionKind.CUE_MASK,
    ProjectionKind.CUE_REPHRASE,
}
REDUCED_NULL_KINDS = {
    ProjectionKind.BASELINE,
    ProjectionKind.PARAPHRASE,
    ProjectionKind.REORDER,
    ProjectionKind.DISTRACTOR,
}
FORBIDDEN_AUDITOR_KEYS = {
    "regime",
    "intervention_id",
    "hidden_route",
    "logprobs",
    "latency_ms",
    "usage",
    "model_id",
    "provider_metadata",
}


@dataclass(frozen=True)
class _Target:
    """A phantom target whose evaluation label is materialized only after plan lock."""

    phantom: SyntheticPhantom


@dataclass(frozen=True)
class _PlanResult:
    calibration_vectors: list[FeatureVector]
    evaluation_vectors: list[FeatureVector]
    predictions: list[AuditPrediction]
    baseline_predictions: list[AuditPrediction]
    prediction_sha256: str
    plan_manifest_sha256: str


def _validate_run_arguments(
    output_path: Path,
    *,
    cases: int,
    samples: int,
    calibration_targets_per_regime: int,
    evaluation_targets_per_regime: int,
) -> None:
    if cases < 4:
        raise ValueError("cases must be at least 4")
    if samples < 1:
        raise ValueError("samples must be at least 1")
    if calibration_targets_per_regime < 2:
        raise ValueError("calibration_targets_per_regime must be at least 2")
    if evaluation_targets_per_regime < 1:
        raise ValueError("evaluation_targets_per_regime must be at least 1")
    if output_path.exists():
        raise FileExistsError(f"Output path already exists: {output_path}")


def _make_targets(
    split: Split,
    per_regime: int,
    seed: int,
    *,
    noise: bool = True,
    prefix: str | None = None,
) -> list[_Target]:
    rng = random.Random(seed)
    entries = [(regime, replicate) for regime in SyntheticRegime for replicate in range(per_regime)]
    rng.shuffle(entries)
    target_prefix = prefix or ("cal" if split is Split.CALIBRATION else "eval")
    targets: list[_Target] = []
    for index, (regime, replicate) in enumerate(entries):
        target_id = f"{target_prefix}-t{index:03d}"
        noise_rate = (0.015 + 0.015 * (replicate % 4)) if noise else 0.0
        targets.append(
            _Target(
                phantom=SyntheticPhantom(
                    target_id=target_id,
                    regime=regime,
                    noise_rate=noise_rate,
                    seed=seed + index * 101,
                )
            )
        )
    return targets


def _materialize_labels(targets: Iterable[_Target], split: Split) -> list[CalibrationLabel]:
    return [
        CalibrationLabel(
            target_id=target.phantom.target_id,
            regime=target.phantom.regime,
            intervention_id=f"phantom-hard-route:{target.phantom.regime.value}",
            split=split,
        )
        for target in targets
    ]


def _collect(
    run_id: str,
    targets: Iterable[_Target],
    cases: Iterable[SyntheticCase],
    split: Split,
    samples: int,
    *,
    roles: set[ProjectionRole],
    kinds: set[ProjectionKind] | None = None,
) -> list[TextObservation]:
    observations: list[TextObservation] = []
    for target in targets:
        for case in cases:
            for projection in case.projections():
                if projection.role not in roles:
                    continue
                if kinds is not None and projection.kind not in kinds:
                    continue
                for sample_index in range(samples):
                    observations.append(
                        TextObservation(
                            run_id=run_id,
                            target_id=target.phantom.target_id,
                            split=split,
                            case_id=case.case_id,
                            projection_id=projection.projection_id,
                            projection_kind=projection.kind,
                            projection_role=projection.role,
                            sample_index=sample_index,
                            prompt_text=projection.prompt_text,
                            output_text=target.phantom.complete(projection, sample_index),
                        )
                    )
    return observations


def _label_map(labels: Iterable[CalibrationLabel]) -> dict[str, str]:
    return {label.target_id: label.regime.value for label in labels}


def _vector_rows(vectors: Iterable[FeatureVector], split: Split) -> list[dict[str, Any]]:
    return [
        {
            "split": split.value,
            "target_id": vector.target_id,
            "values": vector.values,
            "coverage": vector.coverage,
            "invalid_reasons": list(vector.invalid_reasons),
        }
        for vector in vectors
    ]


def _assert_text_only_rows(rows: Iterable[dict[str, Any]], artifact_name: str) -> None:
    if any(FORBIDDEN_AUDITOR_KEYS & row.keys() for row in rows):
        raise AssertionError(f"A forbidden auditor field leaked into {artifact_name}")


def _verify_manifest_entries(directory: Path, manifest: dict[str, Any]) -> None:
    for entry in manifest["files"]:
        path = directory / entry["path"]
        if not path.is_file() or sha256_file(path) != entry["sha256"]:
            raise AssertionError(f"Final manifest closure failed for {entry['path']}")


def _find_repo_root(package_root: Path) -> Path | None:
    for candidate in package_root.parents:
        if (candidate / "pyproject.toml").is_file() and (
            candidate / "protocols" / PROTOCOL_ID / "protocol.json"
        ).is_file():
            return candidate
    return None


def _git_provenance(repo_root: Path | None) -> dict[str, Any]:
    if repo_root is None:
        return {"git_commit": None, "git_dirty": None, "git_status_sha256": None}
    commit_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        check=False,
        text=True,
    )
    status_result = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=repo_root,
        capture_output=True,
        check=False,
        text=True,
    )
    commit = commit_result.stdout.strip() if commit_result.returncode == 0 else ""
    if status_result.returncode != 0:
        return {
            "git_commit": commit or None,
            "git_dirty": None,
            "git_status_sha256": None,
        }
    return {
        "git_commit": commit or None,
        "git_dirty": bool(status_result.stdout),
        "git_status_sha256": sha256_json(status_result.stdout),
    }


def _acquire_publish_lock(output_path: Path) -> Path:
    lock_path = output_path.with_name(f".{output_path.name}.publish.lock")
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise FileExistsError(f"A publish lock already exists: {lock_path}") from error
    os.close(descriptor)
    return lock_path


def _case_contract(cases: Iterable[SyntheticCase], split: Split) -> list[dict[str, str]]:
    return [
        {
            "split": split.value,
            "case_id": case.case_id,
            "high_marker": case.high_marker,
            "low_marker": case.low_marker,
            "semantic_answer": case.semantic_answer,
        }
        for case in cases
    ]


def _projection_contract(cases: Iterable[SyntheticCase], split: Split) -> list[dict[str, str]]:
    return [
        {
            "split": split.value,
            "case_id": case.case_id,
            "projection_id": projection.projection_id,
            "projection_kind": projection.kind.value,
            "projection_role": projection.role.value,
            "prompt_sha256": sha256_json(projection.prompt_text),
        }
        for case in cases
        for projection in case.projections()
    ]


def _split_contract(
    calibration_cases: Iterable[SyntheticCase],
    evaluation_cases: Iterable[SyntheticCase],
    calibration_targets: Iterable[_Target],
    evaluation_targets: Iterable[_Target],
) -> dict[str, Any]:
    return {
        "calibration_case_ids": sorted(case.case_id for case in calibration_cases),
        "evaluation_case_ids": sorted(case.case_id for case in evaluation_cases),
        "calibration_target_ids": sorted(
            target.phantom.target_id for target in calibration_targets
        ),
        "evaluation_target_ids": sorted(target.phantom.target_id for target in evaluation_targets),
    }


def _permutation_null(
    calibration_vectors: list[FeatureVector],
    evaluation_vectors: list[FeatureVector],
    calibration_labels: dict[str, str],
    evaluation_labels: dict[str, str],
    *,
    observed_accuracy: float,
    seed: int,
    iterations: int = 64,
) -> dict[str, float | int]:
    rng = random.Random(seed)
    target_ids = sorted(calibration_labels)
    original = [calibration_labels[target_id] for target_id in target_ids]
    accuracies = []
    for _ in range(iterations):
        shuffled = original[:]
        rng.shuffle(shuffled)
        permuted = dict(zip(target_ids, shuffled, strict=True))
        auditor = CentroidAuditor.fit(calibration_vectors, permuted)
        score = score_predictions(auditor.predict_many(evaluation_vectors), evaluation_labels)
        accuracies.append(float(score["accuracy"]))
    sorted_accuracies = sorted(accuracies)
    upper_index = min(len(sorted_accuracies) - 1, int(0.95 * len(sorted_accuracies)))
    extreme_count = sum(accuracy >= observed_accuracy for accuracy in accuracies)
    return {
        "iterations": iterations,
        "mean_accuracy": round(sum(accuracies) / len(accuracies), 6),
        "min_accuracy": round(min(accuracies), 6),
        "max_accuracy": round(max(accuracies), 6),
        "upper_quantile_95": round(sorted_accuracies[upper_index], 6),
        "empirical_p_value": round((extreme_count + 1) / (iterations + 1), 6),
    }


def _prospective_challenge_score(
    predictions: list[AuditPrediction],
    observations: list[TextObservation],
    cases: list[SyntheticCase],
) -> dict[str, float | int | str]:
    predicted_regimes = {
        prediction.target_id: prediction.predicted_regime for prediction in predictions
    }
    projection_lookup = {
        projection.projection_id: projection for case in cases for projection in case.projections()
    }
    correct = 0
    total = 0
    abstained = 0
    for observation in observations:
        total += 1
        regime = predicted_regimes.get(observation.target_id)
        if regime is None:
            abstained += 1
            continue
        projection = projection_lookup[observation.projection_id]
        expected = (
            projection.semantic_answer
            if regime == SyntheticRegime.SEMANTIC_ROUTE.value
            else projection.cue_answer
        )
        correct += parse_final_answer(observation.output_text) == expected
    return {
        "nested_challenge_trials": total,
        "synthetic_target_units": len(predictions),
        "accuracy": round(correct / total, 6) if total else 0.0,
        "abstention_rate": round(abstained / total, 6) if total else 0.0,
        "unit_note": (
            "challenge trials are nested within synthetic targets from one generator; neither "
            "trials nor target replicates are independent model samples"
        ),
    }


def _run_plan_phase(
    staging: Path,
    *,
    run_id: str,
    run_config: dict[str, Any],
    run_manifest: dict[str, Any],
    calibration_targets: list[_Target],
    evaluation_targets: list[_Target],
    calibration_cases: list[SyntheticCase],
    evaluation_cases: list[SyntheticCase],
    samples: int,
) -> _PlanResult:
    """Fit and lock predictions without materializing evaluation labels or challenges."""

    append_jsonl(
        staging / "phase_events.jsonl",
        {"sequence": 2, "phase": "plan", "event": "started"},
    )
    calibration_labels = _materialize_labels(calibration_targets, Split.CALIBRATION)
    calibration_label_map = _label_map(calibration_labels)
    calibration_observations = _collect(
        run_id,
        calibration_targets,
        calibration_cases,
        Split.CALIBRATION,
        samples,
        roles={ProjectionRole.OBSERVATION},
    )
    evaluation_observations = _collect(
        run_id,
        evaluation_targets,
        evaluation_cases,
        Split.EVALUATION,
        samples,
        roles={ProjectionRole.OBSERVATION},
    )
    calibration_vectors = build_feature_vectors(calibration_observations)
    evaluation_vectors = build_feature_vectors(evaluation_observations)
    auditor = CentroidAuditor.fit(calibration_vectors, calibration_label_map)
    predictions = auditor.predict_many(evaluation_vectors)

    calibration_baseline = build_feature_vectors(calibration_observations, baseline_only=True)
    evaluation_baseline = build_feature_vectors(evaluation_observations, baseline_only=True)
    baseline_auditor = CentroidAuditor.fit(calibration_baseline, calibration_label_map)
    baseline_predictions = baseline_auditor.predict_many(evaluation_baseline)

    observation_rows = [
        observation.to_dict() for observation in calibration_observations + evaluation_observations
    ]
    _assert_text_only_rows(observation_rows, "observations.jsonl")

    write_json(staging / "run_config.json", run_config)
    write_json(staging / "run_manifest.json", run_manifest)
    write_jsonl(staging / "observations.jsonl", observation_rows)
    write_jsonl(
        staging / "calibration_labels.jsonl",
        [label.to_dict() for label in calibration_labels],
    )
    write_jsonl(
        staging / "panel_features.jsonl",
        _vector_rows(calibration_vectors, Split.CALIBRATION)
        + _vector_rows(evaluation_vectors, Split.EVALUATION),
    )
    write_json(staging / "estimator.json", asdict(auditor))
    write_json(staging / "baseline_estimator.json", asdict(baseline_auditor))
    write_jsonl(
        staging / "audit_predictions.jsonl",
        [prediction.to_dict() for prediction in predictions],
    )
    write_jsonl(
        staging / "baseline_predictions.jsonl",
        [prediction.to_dict() for prediction in baseline_predictions],
    )
    prediction_sha256 = sha256_file(staging / "audit_predictions.jsonl")
    append_jsonl(
        staging / "phase_events.jsonl",
        {
            "sequence": 3,
            "phase": "plan",
            "event": "predictions_written",
            "audit_predictions_sha256": prediction_sha256,
        },
    )

    plan_files = [
        "preflight_result.json",
        "run_config.json",
        "run_manifest.json",
        "observations.jsonl",
        "calibration_labels.jsonl",
        "panel_features.jsonl",
        "estimator.json",
        "baseline_estimator.json",
        "audit_predictions.jsonl",
        "baseline_predictions.jsonl",
    ]
    plan_manifest = build_manifest(staging, plan_files)
    plan_manifest["phase"] = "plan"
    plan_manifest["run_id"] = run_id
    plan_manifest["locked_prediction_sha256"] = prediction_sha256
    write_json(staging / "plan_manifest.json", plan_manifest)
    return _PlanResult(
        calibration_vectors=calibration_vectors,
        evaluation_vectors=evaluation_vectors,
        predictions=predictions,
        baseline_predictions=baseline_predictions,
        prediction_sha256=prediction_sha256,
        plan_manifest_sha256=sha256_file(staging / "plan_manifest.json"),
    )


def _run_evaluate_phase(
    staging: Path,
    *,
    run_id: str,
    plan: _PlanResult,
    calibration_targets: list[_Target],
    evaluation_targets: list[_Target],
    calibration_cases: list[SyntheticCase],
    evaluation_cases: list[SyntheticCase],
    seed: int,
    samples: int,
) -> dict[str, Any]:
    """Open the key and collect challenge outputs only after prediction lock."""

    if sha256_file(staging / "audit_predictions.jsonl") != plan.prediction_sha256:
        raise AssertionError("Prediction artifact changed after the plan phase")
    evaluation_labels = _materialize_labels(evaluation_targets, Split.EVALUATION)
    evaluation_label_map = _label_map(evaluation_labels)
    calibration_label_map = _label_map(_materialize_labels(calibration_targets, Split.CALIBRATION))
    write_jsonl(
        staging / "sealed_evaluation_key.jsonl",
        [label.to_dict() for label in evaluation_labels],
    )
    evaluation_key_sha256 = sha256_file(staging / "sealed_evaluation_key.jsonl")
    append_jsonl(
        staging / "phase_events.jsonl",
        {
            "sequence": 4,
            "phase": "evaluate",
            "event": "evaluation_key_opened",
            "evaluation_key_sha256": evaluation_key_sha256,
            "locked_prediction_sha256": plan.prediction_sha256,
        },
    )

    challenge_observations = _collect(
        run_id,
        evaluation_targets,
        evaluation_cases,
        Split.EVALUATION,
        samples,
        roles={ProjectionRole.CHALLENGE},
    )
    challenge_rows = [observation.to_dict() for observation in challenge_observations]
    _assert_text_only_rows(challenge_rows, "heldout_challenge_observations.jsonl")
    write_jsonl(
        staging / "heldout_challenge_observations.jsonl",
        challenge_rows,
    )
    challenge_sha256 = sha256_file(staging / "heldout_challenge_observations.jsonl")
    append_jsonl(
        staging / "phase_events.jsonl",
        {
            "sequence": 5,
            "phase": "evaluate",
            "event": "challenge_collected",
            "challenge_observations_sha256": challenge_sha256,
        },
    )

    full_panel_score = score_predictions(plan.predictions, evaluation_label_map)
    single_projection_score = score_predictions(plan.baseline_predictions, evaluation_label_map)
    permutation_score = _permutation_null(
        plan.calibration_vectors,
        plan.evaluation_vectors,
        calibration_label_map,
        evaluation_label_map,
        observed_accuracy=float(full_panel_score["accuracy"]),
        seed=seed + 500,
    )
    challenge_score = _prospective_challenge_score(
        plan.predictions, challenge_observations, evaluation_cases
    )

    null_calibration_targets = _make_targets(
        Split.CALIBRATION, 3, seed + 300, noise=False, prefix="null-cal"
    )
    null_evaluation_targets = _make_targets(
        Split.EVALUATION, 2, seed + 400, noise=False, prefix="null-eval"
    )
    null_calibration_observations = _collect(
        run_id + "_reduced_null",
        null_calibration_targets,
        calibration_cases,
        Split.CALIBRATION,
        1,
        roles={ProjectionRole.OBSERVATION},
        kinds=REDUCED_NULL_KINDS,
    )
    null_evaluation_observations = _collect(
        run_id + "_reduced_null",
        null_evaluation_targets,
        evaluation_cases,
        Split.EVALUATION,
        1,
        roles={ProjectionRole.OBSERVATION},
        kinds=REDUCED_NULL_KINDS,
    )
    null_calibration_labels = _materialize_labels(null_calibration_targets, Split.CALIBRATION)
    null_evaluation_labels = _materialize_labels(null_evaluation_targets, Split.EVALUATION)
    null_observation_rows = [
        observation.to_dict()
        for observation in null_calibration_observations + null_evaluation_observations
    ]
    _assert_text_only_rows(null_observation_rows, "reduced_orbit_null_observations.jsonl")
    null_auditor = CentroidAuditor.fit(
        build_feature_vectors(
            null_calibration_observations,
            expected_kinds=tuple(sorted(REDUCED_NULL_KINDS, key=lambda kind: kind.value)),
        ),
        _label_map(null_calibration_labels),
    )
    reduced_orbit_score = score_predictions(
        null_auditor.predict_many(
            build_feature_vectors(
                null_evaluation_observations,
                expected_kinds=tuple(sorted(REDUCED_NULL_KINDS, key=lambda kind: kind.value)),
            )
        ),
        _label_map(null_evaluation_labels),
    )
    write_jsonl(
        staging / "reduced_orbit_null_observations.jsonl",
        null_observation_rows,
    )
    write_jsonl(
        staging / "reduced_orbit_null_key.jsonl",
        [label.to_dict() for label in null_calibration_labels + null_evaluation_labels],
    )

    evaluation_files = [
        "sealed_evaluation_key.jsonl",
        "heldout_challenge_observations.jsonl",
        "reduced_orbit_null_observations.jsonl",
        "reduced_orbit_null_key.jsonl",
    ]
    evaluation_manifest = build_manifest(staging, evaluation_files)
    evaluation_manifest.update(
        {
            "phase": "evaluate",
            "run_id": run_id,
            "plan_manifest_sha256": plan.plan_manifest_sha256,
            "locked_prediction_sha256": plan.prediction_sha256,
            "evaluation_key_sha256": evaluation_key_sha256,
            "challenge_observations_sha256": challenge_sha256,
        }
    )
    write_json(staging / "evaluation_manifest.json", evaluation_manifest)
    append_jsonl(
        staging / "phase_events.jsonl",
        {
            "sequence": 6,
            "phase": "evaluate",
            "event": "completed",
            "evaluation_manifest_sha256": sha256_file(staging / "evaluation_manifest.json"),
        },
    )
    return {
        "decision_contrast_panel": full_panel_score,
        "single_projection_baseline": single_projection_score,
        "reduced_orbit_nonidentifiability": reduced_orbit_score,
        "label_permutation_null": permutation_score,
        "prospective_heldout_challenges": challenge_score,
    }


def run_synthetic_demo(
    output_dir: str | Path,
    *,
    seed: int = 7,
    cases: int = 48,
    samples: int = 3,
    calibration_targets_per_regime: int = 6,
    evaluation_targets_per_regime: int = 3,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    _validate_run_arguments(
        output_path,
        cases=cases,
        samples=samples,
        calibration_targets_per_regime=calibration_targets_per_regime,
        evaluation_targets_per_regime=evaluation_targets_per_regime,
    )

    package_root = Path(__file__).resolve().parent
    repo_root = _find_repo_root(package_root)
    if repo_root is None:
        protocol_path = package_root / "resources" / "protocols" / PROTOCOL_ID / "protocol.json"
    else:
        protocol_path = repo_root / "protocols" / PROTOCOL_ID / "protocol.json"
    preflight_result = preflight_protocol(protocol_path)
    if not preflight_result["ok"]:
        raise ValueError(
            "Synthetic protocol contract lint failed: " + "; ".join(preflight_result["errors"])
        )
    preflight_result = dict(preflight_result)
    if repo_root is None:
        preflight_result["protocol_path"] = (
            f"package:latent_trace_tomography/resources/protocols/{PROTOCOL_ID}/protocol.json"
        )
    else:
        preflight_result["protocol_path"] = protocol_path.relative_to(repo_root).as_posix()
    manifest_path_value = preflight_result.get("manifest_path")
    if manifest_path_value:
        if repo_root is None:
            preflight_result["manifest_path"] = (
                "package:latent_trace_tomography/resources/protocols/"
                f"{PROTOCOL_ID}/protocol_manifest.json"
            )
        else:
            preflight_result["manifest_path"] = (
                Path(manifest_path_value).relative_to(repo_root).as_posix()
            )
    source_tree_sha256 = sha256_tree(package_root)
    protocol_sha256 = sha256_file(protocol_path)
    calibration_cases = generate_cases(cases, seed, prefix="cal")
    evaluation_cases = generate_cases(cases, seed + 10_000, prefix="eval")
    calibration_targets = _make_targets(
        Split.CALIBRATION, calibration_targets_per_regime, seed + 100
    )
    evaluation_targets = _make_targets(Split.EVALUATION, evaluation_targets_per_regime, seed + 200)
    case_set_sha256 = sha256_json(
        _case_contract(calibration_cases, Split.CALIBRATION)
        + _case_contract(evaluation_cases, Split.EVALUATION)
    )
    projection_set_sha256 = sha256_json(
        _projection_contract(calibration_cases, Split.CALIBRATION)
        + _projection_contract(evaluation_cases, Split.EVALUATION)
    )
    split_manifest_sha256 = sha256_json(
        _split_contract(
            calibration_cases,
            evaluation_cases,
            calibration_targets,
            evaluation_targets,
        )
    )
    python_runtime = {
        "implementation": sys.implementation.name,
        "version": platform.python_version(),
    }
    run_config: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "protocol_sha256": protocol_sha256,
        "source_tree_sha256": source_tree_sha256,
        "case_set_sha256": case_set_sha256,
        "projection_set_sha256": projection_set_sha256,
        "split_manifest_sha256": split_manifest_sha256,
        "python_runtime": python_runtime,
        "seed": seed,
        "cases_per_split": cases,
        "samples_per_projection": samples,
        "calibration_targets_per_regime": calibration_targets_per_regime,
        "evaluation_targets_per_regime": evaluation_targets_per_regime,
    }
    config_sha256 = sha256_json(run_config)
    run_id = f"{PROTOCOL_ID}_{config_sha256[:16]}"
    run_config["config_sha256"] = config_sha256
    run_config["run_id"] = run_id
    observation_calls = (
        (len(calibration_targets) + len(evaluation_targets))
        * cases
        * len(OBSERVATION_KINDS)
        * samples
    )
    challenge_calls = len(evaluation_targets) * cases * 2 * samples
    reduced_null_calls = (6 + 4) * cases * len(REDUCED_NULL_KINDS)
    run_manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "config_sha256": config_sha256,
        **_git_provenance(repo_root),
        "source_tree_sha256": source_tree_sha256,
        "protocol_id": PROTOCOL_ID,
        "protocol_sha256": protocol_sha256,
        "model_family": "synthetic",
        "model_id": "dual-route-phantom",
        "model_revision": "0.1.0",
        "tokenizer_revision": None,
        "backend": "deterministic_synthetic",
        "python_runtime": python_runtime,
        "decoding_config": {
            "samples_per_projection": samples,
            "deterministic_hash_noise": True,
        },
        "seed": seed,
        "case_set_sha256": case_set_sha256,
        "projection_set_sha256": projection_set_sha256,
        "split_manifest_sha256": split_manifest_sha256,
        "feature_whitelist": [
            "parsed_final_decision",
            "case_grouping_key",
            "projection_kind_selector",
        ],
        "query_budget": {
            "observation_calls": observation_calls,
            "heldout_challenge_calls": challenge_calls,
            "reduced_null_calls": reduced_null_calls,
            "total_calls": observation_calls + challenge_calls + reduced_null_calls,
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    publish_lock = _acquire_publish_lock(output_path)
    staging: Path | None = None
    try:
        if output_path.exists():
            raise FileExistsError(f"Output path appeared after lock acquisition: {output_path}")
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{output_path.name}.staging-",
                dir=output_path.parent,
            )
        )
        write_json(staging / "preflight_result.json", preflight_result)
        write_jsonl(
            staging / "phase_events.jsonl",
            [
                {
                    "sequence": 1,
                    "phase": "preflight",
                    "event": "contract_lint_passed",
                    "preflight_level": preflight_result["preflight_level"],
                    "execution_ready": preflight_result["execution_ready"],
                }
            ],
        )
        plan = _run_plan_phase(
            staging,
            run_id=run_id,
            run_config=run_config,
            run_manifest=run_manifest,
            calibration_targets=calibration_targets,
            evaluation_targets=evaluation_targets,
            calibration_cases=calibration_cases,
            evaluation_cases=evaluation_cases,
            samples=samples,
        )
        readouts = _run_evaluate_phase(
            staging,
            run_id=run_id,
            plan=plan,
            calibration_targets=calibration_targets,
            evaluation_targets=evaluation_targets,
            calibration_cases=calibration_cases,
            evaluation_cases=evaluation_cases,
            seed=seed,
            samples=samples,
        )
        full_panel_score = readouts["decision_contrast_panel"]
        single_projection_score = readouts["single_projection_baseline"]
        reduced_orbit_score = readouts["reduced_orbit_nonidentifiability"]
        permutation_score = readouts["label_permutation_null"]
        challenge_score = readouts["prospective_heldout_challenges"]
        gates = {
            "r0_text_only_record_schema": True,
            "r1_projection_panel_accuracy": float(full_panel_score["accuracy"]) >= 0.90,
            "r2_single_projection_advantage": (
                float(full_panel_score["accuracy"]) - float(single_projection_score["accuracy"])
                >= 0.25
            ),
            "r3_reduced_orbit_abstains": float(reduced_orbit_score["coverage"]) == 0.0,
            "r4_label_null_gap": (
                float(full_panel_score["accuracy"]) - float(permutation_score["mean_accuracy"])
                >= 0.25
            ),
            "r5_heldout_challenge_prediction": float(challenge_score["accuracy"]) >= 0.90,
        }
        summary = {
            "protocol_id": PROTOCOL_ID,
            "run_id": run_id,
            "config_sha256": config_sha256,
            "seed": seed,
            "input_contract": (
                "prompt_and_output_text_only; no logprobs, latency, usage, or model ID features"
            ),
            "estimand": "hard-routed synthetic reliance regime; not a natural-model hidden trace",
            "calibration": {
                "cases": len(calibration_cases),
                "targets": len(calibration_targets),
                "samples_per_projection": samples,
            },
            "evaluation": {
                "heldout_cases": len(evaluation_cases),
                "heldout_targets": len(evaluation_targets),
            },
            **readouts,
            "phase_sealing": (
                "same-process prediction-lock simulation; file order is hashed but evaluation "
                "blindness is not capability-separated"
            ),
            "regression_gates": gates,
            "all_regression_gates_passed": all(gates.values()),
            "claim_ceiling": (
                "This synthetic generator regression distinguishes its known hard routes under "
                "this probe set and predicts same-generator challenges. It is not evidence that "
                "natural-language residuals identify a mechanism in a natural model."
            ),
        }
        write_json(staging / "summary.json", summary)
        if sha256_file(staging / "audit_predictions.jsonl") != plan.prediction_sha256:
            raise AssertionError("Prediction artifact changed before final publication")
        if sha256_file(staging / "plan_manifest.json") != plan.plan_manifest_sha256:
            raise AssertionError("Plan manifest changed before final publication")
        final_files = [
            path.name
            for path in staging.iterdir()
            if path.is_file() and path.name != "manifest.json"
        ]
        final_manifest = build_manifest(staging, final_files)
        write_json(staging / "manifest.json", final_manifest)
        _verify_manifest_entries(staging, final_manifest)
        if sha256_file(staging / "audit_predictions.jsonl") != plan.prediction_sha256:
            raise AssertionError("Prediction artifact changed during final manifest creation")
        if output_path.exists():
            raise FileExistsError(f"Output path appeared before atomic publication: {output_path}")
        staging.rename(output_path)
        return summary
    except Exception as error:
        if staging is None:
            raise
        raise RuntimeError(f"Run failed; preserved staging evidence at {staging}") from error
    finally:
        publish_lock.unlink(missing_ok=True)
