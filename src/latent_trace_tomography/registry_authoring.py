"""Conjunctive, non-authorizing gate for the OSS-1 v2 authoring bundle.

This module binds the controlled anchor construction plan and its actual base
intake to a post-training dependency registry, lineage receipt, and local
source-payload catalog.  Passing this gate establishes plan and identity
closure only.  Kind-specific evidence-body semantics remain a separate,
mandatory future gate, so this module can never declare discovery readiness.
"""

from __future__ import annotations

import hashlib
import json
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .anchor_plan import validate_anchor_construction_plan
from .dependency_registry import DependencyRegistryError
from .registry_evidence import load_source_evidence_catalog
from .registry_temporal import validate_dependency_cluster_registry_v2


GATE_ID = "controlled_anchor_registry_authoring_identity_gate_v2"
GATE_STATUS = "plan_and_identity_closed_semantics_pending"
REQUIRED_NEXT_GATE = "kind_specific_source_evidence_semantic_validation_v1"


def _mapping(value: Any, *, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DependencyRegistryError(f"{context} must be an object")
    return value


def _sequence(value: Any, *, context: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise DependencyRegistryError(f"{context} must be an array")
    return value


def _raw_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_exact_json(path: str | Path, *, context: str) -> tuple[Mapping[str, Any], str]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise DependencyRegistryError(f"{context} contains duplicate key {key!r}")
            result[key] = value
        return result

    candidate = Path(path)
    try:
        file_status = candidate.lstat()
        if not stat.S_ISREG(file_status.st_mode):
            raise DependencyRegistryError(f"{context} must be a regular file")
        raw_bytes = candidate.read_bytes()
        value = json.loads(
            raw_bytes.decode("utf-8"),
            object_pairs_hook=unique_object,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DependencyRegistryError(f"{context} is not readable JSON") from error
    return _mapping(value, context=context), hashlib.sha256(raw_bytes).hexdigest()


def _bind_exact_json(
    value: Mapping[str, Any],
    path: str | Path,
    *,
    context: str,
) -> tuple[Mapping[str, Any], str]:
    on_disk, raw_sha256 = _load_exact_json(path, context=context)
    if on_disk != _mapping(value, context=context):
        raise DependencyRegistryError(f"{context} object differs from bound file")
    return on_disk, raw_sha256


def validate_controlled_anchor_plan_registry_binding(
    registry_value: Mapping[str, Any],
    lineage_receipt_value: Mapping[str, Any],
    *,
    registry_path: str | Path,
    lineage_receipt_path: str | Path,
    base_model_intake: Mapping[str, Any],
    base_model_intake_path: str | Path,
    construction_plan: Mapping[str, Any],
    construction_plan_path: str | Path,
    generator_source_path: str | Path,
) -> dict[str, Any]:
    """Bind every future descendant row to the frozen controlled plan."""

    plan_result = validate_anchor_construction_plan(
        construction_plan,
        base_model_intake=base_model_intake,
        base_model_intake_path=base_model_intake_path,
        generator_source_path=generator_source_path,
    )
    _, plan_file_hash = _bind_exact_json(
        construction_plan,
        construction_plan_path,
        context="anchor construction plan file",
    )
    registry, registry_file_hash = _bind_exact_json(
        registry_value,
        registry_path,
        context="dependency registry file",
    )
    receipt, receipt_file_hash = _bind_exact_json(
        lineage_receipt_value,
        lineage_receipt_path,
        context="lineage receipt file",
    )
    intake = _mapping(base_model_intake, context="base-model intake")
    plan = _mapping(construction_plan, context="anchor construction plan")

    intake_file_hash = _raw_sha256(base_model_intake_path)
    expected_top_bindings = {
        "base_model_intake_body_sha256": intake["intake_body_sha256"],
        "base_model_intake_file_sha256": intake_file_hash,
        "anchor_construction_plan_body_sha256": plan["plan_body_sha256"],
        "anchor_construction_plan_file_sha256": plan_file_hash,
    }
    for field, expected in expected_top_bindings.items():
        if receipt.get(field) != expected:
            raise DependencyRegistryError(f"lineage receipt {field} drifted")

    projected_models = {
        row["model_unit_id"]: row
        for row in _sequence(
            _mapping(registry["authorization_projection"], context="projection")["model_registry"],
            context="projected model registry",
        )
    }
    candidates = {
        row["model_unit_id"]: row
        for row in _sequence(registry["candidate_model_units"], context="candidate models")
    }
    lineage_records = {
        row["model_unit_id"]: row
        for row in _sequence(receipt["records"], context="lineage records")
    }
    plan_runs = {
        row["model_unit_id"]: row for row in _sequence(plan["runs"], context="construction runs")
    }
    base_records = {
        row["base_model_unit_id"]: row
        for row in _sequence(intake["records"], context="base-model records")
    }
    expected_ids = set(plan_runs)
    for name, observed in (
        ("projection", projected_models),
        ("candidate inventory", candidates),
        ("lineage receipt", lineage_records),
    ):
        if set(observed) != expected_ids:
            raise DependencyRegistryError(
                f"{name} model-unit inventory differs from frozen construction plan"
            )

    for model_unit_id in sorted(expected_ids):
        run = plan_runs[model_unit_id]
        model = projected_models[model_unit_id]
        candidate = candidates[model_unit_id]
        lineage = lineage_records[model_unit_id]
        base = base_records[run["base_model_unit_id"]]
        provenance = model["anchor_provenance"]
        checkpoint = candidate["checkpoint_provenance"]

        exact_model_fields = {
            "independent_training_run_id": run["training_run_id"],
            "architecture_family_id": run["architecture_family_id"],
            "anchor_condition_id": run["anchor_condition_id"],
            "shared_base_artifact_sha256": base["weight_artifact"]["sha256"],
            "tokenizer_revision": base["tokenizer_bundle"]["revision"],
            "tokenizer_artifact_sha256": base["tokenizer_bundle"]["artifact_sha256"],
        }
        if any(model[field] != expected for field, expected in exact_model_fields.items()):
            raise DependencyRegistryError(
                f"projected model {model_unit_id} drifted from plan or base intake"
            )
        exact_provenance = {
            "assignment_timing": "pre_outcome_training_condition",
            "anchor_assignment_manifest_sha256": plan["anchor_assignment_manifest_sha256"],
            "training_recipe_sha256": run["training_recipe_sha256"],
            "training_data_sha256": run["raw_training_data_sha256"],
        }
        if provenance != exact_provenance:
            raise DependencyRegistryError(
                f"projected anchor provenance {model_unit_id} drifted from plan"
            )
        if (
            checkpoint["training_run_parent_id"] != run["training_run_id"]
            or checkpoint["step_or_token_count"] != run["fixed_optimizer_steps"]
            or checkpoint["checkpoint_role"] != "fine_tune"
        ):
            raise DependencyRegistryError(
                f"candidate checkpoint {model_unit_id} drifted from fixed run"
            )

        exact_lineage_fields = {
            "training_run_id": run["training_run_id"],
            "anchor_condition_id": run["anchor_condition_id"],
            "attempt_index": 1,
            "completion_status": "complete_fixed_steps",
            "selection_policy": run["selection_policy"],
            "base_model_record_sha256": base["record_sha256"],
            "base_checkpoint_artifact_sha256": base["weight_artifact"]["sha256"],
            "base_tokenizer_artifact_sha256": base["tokenizer_bundle"]["artifact_sha256"],
            "base_checkpoint_created_at": base["revision_last_modified_at"],
            "descendant_checkpoint_manifest_sha256": checkpoint["checkpoint_manifest_sha256"],
            "descendant_model_artifact_sha256": model["model_artifact_sha256"],
            "descendant_configuration_sha256": model["configuration_sha256"],
            "descendant_tokenizer_artifact_sha256": model["tokenizer_artifact_sha256"],
            "anchor_assignment_manifest_sha256": plan["anchor_assignment_manifest_sha256"],
            "anchor_assignment_committed_at": plan["frozen_at"],
            "training_recipe_sha256": run["training_recipe_sha256"],
            "training_data_sha256": run["raw_training_data_sha256"],
            "derived_target_inventory_sha256": run["derived_target_inventory_sha256"],
            "fixed_optimizer_step_count": run["fixed_optimizer_steps"],
            "training_forward_call_count": run["training_forward_call_budget"],
            "training_backward_call_count": run["training_backward_call_budget"],
        }
        if any(lineage[field] != expected for field, expected in exact_lineage_fields.items()):
            raise DependencyRegistryError(
                f"lineage record {model_unit_id} drifted from frozen plan or intake"
            )

    return {
        "ok": True,
        "registry_file_sha256": registry_file_hash,
        "lineage_receipt_file_sha256": receipt_file_hash,
        "plan_body_sha256": plan_result["plan_body_sha256"],
        "plan_file_sha256": plan_file_hash,
        "base_model_intake_body_sha256": intake["intake_body_sha256"],
        "base_model_intake_file_sha256": intake_file_hash,
        "model_unit_count": len(expected_ids),
        "training_forward_call_count": sum(
            run["training_forward_call_budget"] for run in plan_runs.values()
        ),
        "training_backward_call_count": sum(
            run["training_backward_call_budget"] for run in plan_runs.values()
        ),
        "model_calls_authorized": False,
    }


def validate_registry_authoring_bundle_v2(
    registry_value: Mapping[str, Any],
    lineage_receipt_value: Mapping[str, Any],
    *,
    registry_path: str | Path,
    lineage_receipt_path: str | Path,
    source_catalog_path: str | Path,
    base_model_intake: Mapping[str, Any],
    base_model_intake_path: str | Path,
    construction_plan: Mapping[str, Any],
    construction_plan_path: str | Path,
    generator_source_path: str | Path,
) -> dict[str, Any]:
    """Run the temporal, plan-binding, and source-identity checks conjunctively."""

    registry, _ = _bind_exact_json(
        registry_value,
        registry_path,
        context="dependency registry file",
    )
    receipt, _ = _bind_exact_json(
        lineage_receipt_value,
        lineage_receipt_path,
        context="lineage receipt file",
    )
    temporal = validate_dependency_cluster_registry_v2(registry, receipt)
    if temporal["postfreeze_model_unit_count"] != 9:
        raise DependencyRegistryError(
            "controlled anchor successor requires all nine post-freeze descendants"
        )
    plan_binding = validate_controlled_anchor_plan_registry_binding(
        registry,
        receipt,
        registry_path=registry_path,
        lineage_receipt_path=lineage_receipt_path,
        base_model_intake=base_model_intake,
        base_model_intake_path=base_model_intake_path,
        construction_plan=construction_plan,
        construction_plan_path=construction_plan_path,
        generator_source_path=generator_source_path,
    )
    catalog = load_source_evidence_catalog(
        source_catalog_path,
        source_records=_sequence(registry["source_records"], context="registry source records"),
    )
    return {
        "ok": True,
        "gate_id": GATE_ID,
        "status": GATE_STATUS,
        "registry_body_sha256": temporal["registry_body_sha256"],
        "registry_file_sha256": plan_binding["registry_file_sha256"],
        "lineage_receipt_sha256": temporal["lineage_receipt_sha256"],
        "lineage_receipt_file_sha256": plan_binding["lineage_receipt_file_sha256"],
        "source_catalog_body_sha256": catalog["catalog_body_sha256"],
        "anchor_construction_plan_body_sha256": plan_binding["plan_body_sha256"],
        "anchor_construction_plan_file_sha256": plan_binding["plan_file_sha256"],
        "base_model_intake_body_sha256": plan_binding["base_model_intake_body_sha256"],
        "base_model_intake_file_sha256": plan_binding["base_model_intake_file_sha256"],
        "model_unit_count": 9,
        "dependency_cluster_count": temporal["dependency_cluster_count"],
        "source_identity_payloads_closed": True,
        "kind_specific_evidence_semantics_validated": False,
        "discovery_authorization_ready": False,
        "model_calls_authorized": False,
        "required_next_gate": REQUIRED_NEXT_GATE,
    }
