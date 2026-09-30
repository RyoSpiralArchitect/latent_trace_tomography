"""Append-only temporal eligibility correction for OSS-1 registry authoring.

The v1 operational registry validator conservatively required every eligible
checkpoint to predate the design freeze.  The frozen scientific contract only
requires anchor assignment before outcome-bearing execution.  This module
keeps every v1 check and permits one additional, evidence-bound path:

* an immutable public base checkpoint predates the design freeze;
* the anchor condition, recipe, and training data were committed before a
  fixed post-freeze training run;
* no frozen evaluation material or outcome was accessed before the descendant
  checkpoint closed.

It does not authorize training, discovery, or any model call.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .dependency_registry import (
    DESIGN_FREEZE_BOUNDARY,
    DependencyRegistryError,
    canonical_artifact_sha256,
    validate_dependency_cluster_registry,
)


SCHEMA_VERSION = "0.1.0"
RECEIPT_TYPE = "postfreeze_anchor_lineage_receipt_v1"
STATUS = "outcome_naive_training_lineage_closed"
POLICY_ID = "pre_freeze_base_clean_postfreeze_descendant_v1"
LEGACY_VALIDATION_TIMESTAMP = "2026-07-16T23:59:59Z"

TOP_LEVEL_FIELDS = {
    "schema_version",
    "receipt_type",
    "status",
    "policy_id",
    "receipt_id",
    "created_at",
    "registry_id",
    "registry_body_sha256",
    "base_model_intake_body_sha256",
    "base_model_intake_file_sha256",
    "anchor_construction_plan_body_sha256",
    "anchor_construction_plan_file_sha256",
    "records",
    "training_model_calls_disclosed",
    "evaluation_model_calls_before_registry",
    "outcomes_exposed_before_registry",
    "authorization_effect",
    "receipt_sha256",
}

RECORD_FIELDS = {
    "model_unit_id",
    "training_run_id",
    "anchor_condition_id",
    "attempt_index",
    "completion_status",
    "selection_policy",
    "base_model_record_sha256",
    "base_checkpoint_artifact_sha256",
    "base_tokenizer_artifact_sha256",
    "base_checkpoint_created_at",
    "descendant_checkpoint_manifest_sha256",
    "descendant_model_artifact_sha256",
    "descendant_configuration_sha256",
    "descendant_tokenizer_artifact_sha256",
    "anchor_assignment_manifest_sha256",
    "anchor_assignment_committed_at",
    "training_recipe_sha256",
    "training_data_sha256",
    "derived_target_inventory_sha256",
    "training_started_at",
    "training_completed_at",
    "descendant_checkpoint_created_at",
    "fixed_optimizer_step_count",
    "training_forward_call_count",
    "training_backward_call_count",
    "outcome_access_before_checkpoint",
    "exact_live_prompt_exposed_to_training_runtime",
    "frozen_evaluation_generator_imported_by_training_runtime",
    "frozen_evaluation_template_exposed_to_training_runtime",
    "record_sha256",
}


def _mapping(value: Any, *, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DependencyRegistryError(f"{context} must be an object")
    return value


def _sequence(value: Any, *, context: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise DependencyRegistryError(f"{context} must be an array")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], *, context: str) -> None:
    if set(value) != expected:
        raise DependencyRegistryError(f"{context} fields are not exact")


def _text(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise DependencyRegistryError(f"{context} must be a non-empty string")
    return value


def _sha256(value: Any, *, context: str) -> str:
    text = _text(value, context=context)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise DependencyRegistryError(f"{context} must be lowercase SHA-256")
    if text == "0" * 64:
        raise DependencyRegistryError(f"{context} must not be an all-zero placeholder")
    return text


def _timestamp(value: Any, *, context: str) -> datetime:
    text = _text(value, context=context)
    if not text.endswith("Z"):
        raise DependencyRegistryError(f"{context} must be RFC3339 UTC with Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as error:
        raise DependencyRegistryError(f"{context} is not a valid timestamp") from error
    return parsed.astimezone(timezone.utc)


def _body_hash(value: Mapping[str, Any], self_field: str) -> str:
    return canonical_artifact_sha256({key: value[key] for key in value if key != self_field})


def _postfreeze_eligible_ids(registry: Mapping[str, Any]) -> tuple[str, ...]:
    eligible = set(_sequence(registry.get("eligible_model_unit_ids"), context="eligible ids"))
    records = _sequence(registry.get("candidate_model_units"), context="candidate units")
    result: list[str] = []
    for raw in records:
        record = _mapping(raw, context="candidate unit")
        model_id = _text(record.get("model_unit_id"), context="candidate model_unit_id")
        if model_id not in eligible:
            continue
        checkpoint = _mapping(
            record.get("checkpoint_provenance"), context=f"candidate {model_id} checkpoint"
        )
        if (
            _timestamp(
                checkpoint.get("created_at"), context=f"candidate {model_id} checkpoint.created_at"
            )
            >= DESIGN_FREEZE_BOUNDARY
        ):
            result.append(model_id)
    return tuple(sorted(result))


def validate_postfreeze_anchor_lineage_receipt(
    registry_value: Mapping[str, Any], receipt_value: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate the controlled post-freeze training lineage companion."""

    registry = _mapping(registry_value, context="dependency registry")
    receipt = _mapping(receipt_value, context="postfreeze lineage receipt")
    _exact_keys(receipt, TOP_LEVEL_FIELDS, context="postfreeze lineage receipt")
    if (
        receipt["schema_version"] != SCHEMA_VERSION
        or receipt["receipt_type"] != RECEIPT_TYPE
        or receipt["status"] != STATUS
        or receipt["policy_id"] != POLICY_ID
    ):
        raise DependencyRegistryError("postfreeze lineage receipt identity drifted")
    _text(receipt["receipt_id"], context="receipt_id")
    created_at = _timestamp(receipt["created_at"], context="receipt.created_at")
    registry_created = _timestamp(registry.get("created_at"), context="registry.created_at")
    if created_at < registry_created:
        raise DependencyRegistryError("lineage receipt cannot predate the registry")
    if receipt["registry_id"] != registry.get("registry_id"):
        raise DependencyRegistryError("lineage receipt registry_id drifted")
    if receipt["registry_body_sha256"] != registry.get("registry_body_sha256"):
        raise DependencyRegistryError("lineage receipt registry hash drifted")
    for field in (
        "base_model_intake_body_sha256",
        "base_model_intake_file_sha256",
        "anchor_construction_plan_body_sha256",
        "anchor_construction_plan_file_sha256",
    ):
        _sha256(receipt[field], context=field)
    if receipt["training_model_calls_disclosed"] is not True:
        raise DependencyRegistryError("controlled training calls must be explicitly disclosed")
    if receipt["evaluation_model_calls_before_registry"] != 0:
        raise DependencyRegistryError("evaluation model calls must remain zero before registry")
    if receipt["outcomes_exposed_before_registry"] is not False:
        raise DependencyRegistryError("outcomes must remain unexposed before registry")
    if receipt["authorization_effect"] != "none":
        raise DependencyRegistryError("lineage receipt grants no call authority")

    projected_models = {
        row["model_unit_id"]: row
        for row in _sequence(
            _mapping(registry.get("authorization_projection"), context="projection").get(
                "model_registry"
            ),
            context="projected models",
        )
    }
    candidates = {
        row["model_unit_id"]: row
        for row in _sequence(registry.get("candidate_model_units"), context="candidates")
    }
    exposures = {
        row["model_unit_id"]: row
        for row in _sequence(registry.get("evaluation_exposure_assessments"), context="exposures")
    }
    expected_ids = _postfreeze_eligible_ids(registry)
    raw_records = _sequence(receipt["records"], context="lineage records")
    observed_ids: list[str] = []
    total_training_calls = 0
    total_backward_calls = 0
    for index, raw in enumerate(raw_records):
        record = _mapping(raw, context=f"lineage record[{index}]")
        _exact_keys(record, RECORD_FIELDS, context=f"lineage record[{index}]")
        model_id = _text(record["model_unit_id"], context=f"lineage record[{index}].model")
        training_run_id = _text(
            record["training_run_id"], context=f"lineage record[{index}].training_run_id"
        )
        _text(record["anchor_condition_id"], context=f"lineage {model_id}.anchor_condition_id")
        if record["attempt_index"] != 1:
            raise DependencyRegistryError(
                "controlled lineage permits only the frozen first attempt"
            )
        if record["completion_status"] != "complete_fixed_steps":
            raise DependencyRegistryError("controlled lineage requires a complete fixed-step run")
        if record["selection_policy"] != "retain_first_complete_attempt_no_outcome_selection":
            raise DependencyRegistryError("controlled lineage selection policy drifted")
        observed_ids.append(model_id)
        if (
            model_id not in projected_models
            or model_id not in candidates
            or model_id not in exposures
        ):
            raise DependencyRegistryError("lineage record references an unknown eligible model")
        model = projected_models[model_id]
        candidate = candidates[model_id]
        exposure = exposures[model_id]
        checkpoint = candidate["checkpoint_provenance"]
        provenance = model["anchor_provenance"]

        for field in (
            "base_model_record_sha256",
            "base_checkpoint_artifact_sha256",
            "base_tokenizer_artifact_sha256",
            "descendant_checkpoint_manifest_sha256",
            "descendant_model_artifact_sha256",
            "descendant_configuration_sha256",
            "descendant_tokenizer_artifact_sha256",
            "anchor_assignment_manifest_sha256",
            "training_recipe_sha256",
            "training_data_sha256",
            "derived_target_inventory_sha256",
        ):
            _sha256(record[field], context=f"lineage {model_id}.{field}")
        if (
            training_run_id != model["independent_training_run_id"]
            or training_run_id != checkpoint["training_run_parent_id"]
        ):
            raise DependencyRegistryError("lineage training run identity drifted")
        if (
            record["descendant_checkpoint_manifest_sha256"]
            != checkpoint["checkpoint_manifest_sha256"]
        ):
            raise DependencyRegistryError("descendant checkpoint manifest drifted")
        if record["descendant_model_artifact_sha256"] != model["model_artifact_sha256"]:
            raise DependencyRegistryError("descendant model artifact drifted")
        if record["descendant_configuration_sha256"] != model["configuration_sha256"]:
            raise DependencyRegistryError("descendant configuration drifted")
        if record["descendant_tokenizer_artifact_sha256"] != model["tokenizer_artifact_sha256"]:
            raise DependencyRegistryError("descendant tokenizer artifact drifted")
        if record["base_checkpoint_artifact_sha256"] != model["shared_base_artifact_sha256"]:
            raise DependencyRegistryError(
                "lineage base artifact drifted from projected shared base"
            )
        if (
            record["base_checkpoint_artifact_sha256"]
            not in checkpoint["parent_checkpoint_artifact_sha256"]
        ):
            raise DependencyRegistryError("descendant checkpoint omits the shared base parent")
        if (
            record["anchor_assignment_manifest_sha256"]
            != provenance["anchor_assignment_manifest_sha256"]
        ):
            raise DependencyRegistryError("anchor assignment hash drifted")
        if record["training_recipe_sha256"] != provenance["training_recipe_sha256"]:
            raise DependencyRegistryError("training recipe hash drifted")
        if record["training_data_sha256"] != provenance["training_data_sha256"]:
            raise DependencyRegistryError("training data hash drifted")

        base_created = _timestamp(
            record["base_checkpoint_created_at"], context=f"lineage {model_id}.base_created"
        )
        assignment_committed = _timestamp(
            record["anchor_assignment_committed_at"],
            context=f"lineage {model_id}.assignment_committed",
        )
        training_started = _timestamp(
            record["training_started_at"], context=f"lineage {model_id}.training_started"
        )
        training_completed = _timestamp(
            record["training_completed_at"], context=f"lineage {model_id}.training_completed"
        )
        checkpoint_created = _timestamp(
            record["descendant_checkpoint_created_at"],
            context=f"lineage {model_id}.checkpoint_created",
        )
        candidate_checkpoint_created = _timestamp(
            checkpoint["created_at"], context=f"candidate {model_id}.checkpoint_created"
        )
        evidence_cutoff = _timestamp(
            registry["evidence_cutoff_at"], context="registry.evidence_cutoff_at"
        )
        if base_created >= DESIGN_FREEZE_BOUNDARY:
            raise DependencyRegistryError("controlled descendant requires a pre-freeze base")
        if assignment_committed < DESIGN_FREEZE_BOUNDARY:
            raise DependencyRegistryError(
                "post-freeze anchor assignment must not masquerade as a pre-freeze artifact"
            )
        if not (
            assignment_committed
            < training_started
            <= training_completed
            <= checkpoint_created
            == candidate_checkpoint_created
            <= evidence_cutoff
        ):
            raise DependencyRegistryError("post-freeze training chronology does not close")

        steps = record["fixed_optimizer_step_count"]
        calls = record["training_forward_call_count"]
        backward_calls = record["training_backward_call_count"]
        if (
            not isinstance(steps, int)
            or isinstance(steps, bool)
            or steps <= 0
            or not isinstance(calls, int)
            or isinstance(calls, bool)
            or calls <= 0
            or not isinstance(backward_calls, int)
            or isinstance(backward_calls, bool)
            or backward_calls <= 0
        ):
            raise DependencyRegistryError("training step and call counts must be positive")
        total_training_calls += calls
        total_backward_calls += backward_calls
        for field in (
            "outcome_access_before_checkpoint",
            "exact_live_prompt_exposed_to_training_runtime",
            "frozen_evaluation_generator_imported_by_training_runtime",
            "frozen_evaluation_template_exposed_to_training_runtime",
        ):
            if record[field] is not False:
                raise DependencyRegistryError(
                    f"controlled lineage access flag must be false: {field}"
                )
        if (
            candidate["enrollment_status"] != "eligible"
            or exposure["eligibility_decision"] != "eligible"
        ):
            raise DependencyRegistryError("controlled lineage only applies to eligible candidates")
        if exposure["checkpoint_precedes_design_freeze"] is not False:
            raise DependencyRegistryError(
                "post-freeze descendant must retain its true checkpoint chronology"
            )
        expected_record_hash = _body_hash(record, "record_sha256")
        if record["record_sha256"] != expected_record_hash:
            raise DependencyRegistryError("lineage record is not self-addressed")

    if tuple(observed_ids) != expected_ids or len(set(observed_ids)) != len(observed_ids):
        raise DependencyRegistryError(
            "lineage records must exactly cover sorted post-freeze eligible candidates"
        )
    expected_receipt_hash = _body_hash(receipt, "receipt_sha256")
    if receipt["receipt_sha256"] != expected_receipt_hash:
        raise DependencyRegistryError("lineage receipt is not self-addressed")
    return {
        "ok": True,
        "postfreeze_model_unit_count": len(expected_ids),
        "training_forward_call_count": total_training_calls,
        "training_backward_call_count": total_backward_calls,
        "evaluation_model_calls_before_registry": 0,
        "model_calls_authorized": False,
        "receipt_sha256": expected_receipt_hash,
    }


def validate_dependency_cluster_registry_v2(
    registry_value: Mapping[str, Any], lineage_receipt_value: Mapping[str, Any]
) -> dict[str, Any]:
    """Run every v1 semantic check plus the controlled post-freeze correction.

    The in-memory legacy view changes only the two fields that encoded the v1
    operational overconstraint.  The original registry remains self-addressed,
    is never rewritten, and is bound by the lineage receipt.
    """

    registry = _mapping(registry_value, context="dependency registry")
    expected_registry_hash = canonical_artifact_sha256(
        {key: registry[key] for key in registry if key != "registry_body_sha256"}
    )
    if registry.get("registry_body_sha256") != expected_registry_hash:
        raise DependencyRegistryError("original v2 registry body is not self-addressed")
    lineage_result = validate_postfreeze_anchor_lineage_receipt(registry, lineage_receipt_value)
    postfreeze_ids = set(_postfreeze_eligible_ids(registry))
    legacy_view = copy.deepcopy(dict(registry))
    for candidate in legacy_view["candidate_model_units"]:
        if candidate["model_unit_id"] in postfreeze_ids:
            candidate["checkpoint_provenance"]["created_at"] = LEGACY_VALIDATION_TIMESTAMP
    for exposure in legacy_view["evaluation_exposure_assessments"]:
        if exposure["model_unit_id"] in postfreeze_ids:
            exposure["checkpoint_precedes_design_freeze"] = True
    legacy_view["registry_body_sha256"] = canonical_artifact_sha256(
        {key: legacy_view[key] for key in legacy_view if key != "registry_body_sha256"}
    )
    v1_result = validate_dependency_cluster_registry(legacy_view)
    return {
        **v1_result,
        "registry_body_sha256": expected_registry_hash,
        "temporal_policy_id": POLICY_ID,
        "postfreeze_model_unit_count": lineage_result["postfreeze_model_unit_count"],
        "training_forward_call_count_disclosed": lineage_result["training_forward_call_count"],
        "training_backward_call_count_disclosed": lineage_result["training_backward_call_count"],
        "evaluation_model_calls_before_registry": 0,
        "model_calls_authorized": False,
        "lineage_receipt_sha256": lineage_result["receipt_sha256"],
    }
