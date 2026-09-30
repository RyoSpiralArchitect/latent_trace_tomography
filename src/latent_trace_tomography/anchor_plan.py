"""Frozen, call-free construction plan for controlled OSS anchor descendants."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .anchor_intake import validate_anchor_base_model_intake
from .anchor_training import (
    CLUSTER_IDS,
    AnchorCondition,
    build_anchor_training_manifest,
)
from .dependency_registry import DependencyRegistryError, canonical_artifact_sha256


SCHEMA_VERSION = "0.1.0"
PLAN_TYPE = "controlled_anchor_construction_plan_v1"
STATUS = "pre_training_frozen_unauthorized"
CLAIM_TIER = "controlled_calibration_phantom_named_base_families"
AUTHORIZATION_EFFECT = "none"
EXPECTED_PARENT = {
    "design_freeze_id": "oss_reliance_regime_v0_design_20260717",
    "design_manifest_sha256": ("8c974390ceea3f1defaae19067359c909b4182dd26c321075c9e25ee1518e64b"),
    "protocol_sha256": ("5c49316503b2cec2ad26d4bf47dc59c02f0b61d9f6896b84035e6d0412dced11"),
    "operational_manifest_sha256": (
        "d9ea2369a14983756dcb60cb985d4eabea10f2471f934a5c3598478dbf4dc93c"
    ),
}
BASE_INTAKE_BODY_SHA256 = "2862ed049a5a2a99d40c2e1132fcadd341e228c3dfb2a0dbc6689446243d45d5"
BASE_INTAKE_FILE_SHA256 = "0a10d031d9e0640dd2eac064c70dfbb92e64c0812b347fca290c3d2671c7af42"
GENERATOR_SOURCE_SHA256 = "372f93547da7a004a0dda96967f3cdc412dd689f10e05c41710ce1d2f991715f"

GLOBAL_TRAINING_CONTRACT = {
    "method_id": "lora_causal_lm_fixed_steps_v1",
    "base_parameter_dtype": "float32",
    "trainable_parameter_dtype": "float32",
    "optimizer": "adamw",
    "learning_rate": 0.0002,
    "adam_beta1": 0.9,
    "adam_beta2": 0.999,
    "adam_epsilon": 1e-8,
    "weight_decay": 0.0,
    "microbatch_size": 8,
    "gradient_accumulation_steps": 1,
    "training_case_count_per_run": 4096,
    "epoch_count": 2,
    "steps_per_epoch": 512,
    "fixed_optimizer_steps": 1024,
    "warmup_steps": 64,
    "schedule": "linear_decay_after_warmup",
    "max_input_tokens": 256,
    "input_rendering": "raw_utf8_prompt_no_chat_template_v1",
    "sequence_assembly": "prompt_token_ids_then_newline_target_token_ids_then_eos_v1",
    "tokenizer_add_special_tokens": False,
    "overflow_policy": "fail_if_prompt_target_eos_exceeds_max_input_tokens",
    "padding_side": "right",
    "loss_mask": "newline_target_and_eos_tokens_only_v1",
    "target_derivation": "anchor_training.label_anchor_training_case_v1",
    "dataloader_schedule": "two_exact_epochs_without_replacement_v1",
    "drop_last": False,
    "lora_rank": 8,
    "lora_alpha": 16,
    "lora_dropout": 0.0,
    "lora_bias": "none",
    "lora_initialization": "A_kaiming_uniform_a_sqrt5_B_zeros_v1",
    "validation_forward_calls": 0,
    "early_stopping": False,
    "checkpoint_selection": "first_complete_fixed_step_checkpoint",
    "shuffle_policy": "authority_rng_commitment_fixed_before_first_training_call",
    "raw_seed_serialized": False,
}

FAMILY_ADAPTER_CONTRACTS = {
    "gpt2_absolute_v1": {
        "base_model_unit_id": "base-gpt2-124m",
        "target_modules": ["c_attn", "c_fc", "c_proj"],
    },
    "gpt_neox_rotary_v1": {
        "base_model_unit_id": "base-pythia-70m-deduped",
        "target_modules": [
            "dense",
            "dense_4h_to_h",
            "dense_h_to_4h",
            "query_key_value",
        ],
    },
    "llama_rmsnorm_swiglu_v1": {
        "base_model_unit_id": "base-smollm2-135m",
        "target_modules": [
            "down_proj",
            "gate_proj",
            "k_proj",
            "o_proj",
            "q_proj",
            "up_proj",
            "v_proj",
        ],
    },
}

PROHIBITIONS = (
    "anchor reassignment after any training or measurement output",
    "early stopping or checkpoint selection from observed behavior",
    "evaluation-generator or evaluation-template access during anchor training",
    "learned teacher or distillation target",
    "replacement of a failed run without an append-only successor",
    "reuse of one adapter artifact as multiple model units",
)

AUTHORIZATION_PREREQUISITES = (
    "exact environment and dependency lock",
    "downloaded base-weight byte verification against intake SHA-256",
    "tokenizer-file byte verification against intake SHA-256",
    "resolved LoRA module inventory from the verified base artifact",
    "per-run operating-system-CSPRNG shuffle commitment",
    "exact BOS EOS and padding token IDs",
    "content-addressed output and attempt-retention paths",
)


def _mapping(value: Any, *, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DependencyRegistryError(f"{context} must be an object")
    return value


def _sequence(value: Any, *, context: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise DependencyRegistryError(f"{context} must be an array")
    return value


def _timestamp(value: Any, *, context: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise DependencyRegistryError(f"{context} must be RFC3339 UTC Z")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00").astimezone(timezone.utc)
    except ValueError as error:
        raise DependencyRegistryError(f"{context} is not a valid timestamp") from error


def _body_hash(value: Mapping[str, Any], field: str) -> str:
    return canonical_artifact_sha256({key: value[key] for key in value if key != field})


def _raw_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _target_rule(condition: str) -> str:
    manifest = build_anchor_training_manifest()
    return manifest["target_rules"][condition]


def _recipe_hash(
    *, family_id: str, condition: str, manifest_by_cluster: Mapping[str, Mapping[str, Any]]
) -> str:
    return canonical_artifact_sha256(
        {
            "global_training_contract": GLOBAL_TRAINING_CONTRACT,
            "family_adapter_contract": FAMILY_ADAPTER_CONTRACTS[family_id],
            "anchor_condition_id": condition,
            "target_rule": _target_rule(condition),
            "derived_target_inventory_sha256": manifest_by_cluster[family_id][
                "derived_target_inventory_sha256_by_condition"
            ][condition],
        }
    )


def _expected_runs() -> list[dict[str, Any]]:
    manifest_by_cluster = {
        row["cluster_id"]: row for row in build_anchor_training_manifest()["cluster_records"]
    }
    slug_by_family = {
        "gpt2_absolute_v1": "gpt2",
        "gpt_neox_rotary_v1": "pythia",
        "llama_rmsnorm_swiglu_v1": "smollm2",
    }
    condition_slug = {
        AnchorCondition.MIXED.value: "mixed",
        AnchorCondition.SEMANTIC.value: "semantic",
        AnchorCondition.SURFACE_CUE.value: "surface",
    }
    runs = []
    for family_id in CLUSTER_IDS:
        for condition in sorted(item.value for item in AnchorCondition):
            runs.append(
                {
                    "model_unit_id": f"unit-{slug_by_family[family_id]}-{condition_slug[condition]}",
                    "training_run_id": (
                        f"anchor-run-{slug_by_family[family_id]}-{condition_slug[condition]}-v1"
                    ),
                    "base_model_unit_id": FAMILY_ADAPTER_CONTRACTS[family_id]["base_model_unit_id"],
                    "architecture_family_id": family_id,
                    "anchor_condition_id": condition,
                    "raw_training_data_sha256": manifest_by_cluster[family_id][
                        "raw_case_inventory_sha256"
                    ],
                    "derived_target_inventory_sha256": manifest_by_cluster[family_id][
                        "derived_target_inventory_sha256_by_condition"
                    ][condition],
                    "training_recipe_sha256": _recipe_hash(
                        family_id=family_id,
                        condition=condition,
                        manifest_by_cluster=manifest_by_cluster,
                    ),
                    "fixed_optimizer_steps": GLOBAL_TRAINING_CONTRACT["fixed_optimizer_steps"],
                    "training_forward_call_budget": GLOBAL_TRAINING_CONTRACT[
                        "fixed_optimizer_steps"
                    ],
                    "training_backward_call_budget": GLOBAL_TRAINING_CONTRACT[
                        "fixed_optimizer_steps"
                    ],
                    "selection_policy": "retain_first_complete_attempt_no_outcome_selection",
                }
            )
    return sorted(runs, key=lambda row: row["model_unit_id"])


def _assignment_hash(runs: Sequence[Mapping[str, Any]]) -> str:
    return canonical_artifact_sha256(
        {
            "assignments": [
                {
                    key: run[key]
                    for key in (
                        "model_unit_id",
                        "training_run_id",
                        "base_model_unit_id",
                        "architecture_family_id",
                        "anchor_condition_id",
                    )
                }
                for run in runs
            ]
        }
    )


def validate_anchor_construction_plan(
    value: Mapping[str, Any],
    *,
    base_model_intake: Mapping[str, Any],
    base_model_intake_path: str | Path,
    generator_source_path: str | Path,
) -> dict[str, Any]:
    """Validate the pre-training plan and prove that it grants no authority."""

    validate_anchor_base_model_intake(base_model_intake)
    plan = _mapping(value, context="anchor construction plan")
    expected_fields = {
        "schema_version",
        "plan_type",
        "status",
        "plan_id",
        "frozen_at",
        "parent",
        "claim_tier",
        "base_model_intake",
        "training_generator",
        "anchor_assignment_manifest_sha256",
        "global_training_contract",
        "family_adapter_contracts",
        "runs",
        "query_budget",
        "outcome_exposure",
        "prohibitions",
        "authorization_prerequisites",
        "authorization_effect",
        "plan_body_sha256",
    }
    if set(plan) != expected_fields:
        raise DependencyRegistryError("anchor construction plan fields are not exact")
    if (
        plan["schema_version"] != SCHEMA_VERSION
        or plan["plan_type"] != PLAN_TYPE
        or plan["status"] != STATUS
    ):
        raise DependencyRegistryError("anchor construction plan identity drifted")
    if not isinstance(plan["plan_id"], str) or not plan["plan_id"]:
        raise DependencyRegistryError("anchor construction plan_id must be non-empty")
    _timestamp(plan["frozen_at"], context="plan.frozen_at")
    if plan["parent"] != EXPECTED_PARENT:
        raise DependencyRegistryError("anchor construction parent drifted")
    if plan["claim_tier"] != CLAIM_TIER:
        raise DependencyRegistryError("controlled phantom claim tier drifted")
    if base_model_intake["intake_body_sha256"] != BASE_INTAKE_BODY_SHA256:
        raise DependencyRegistryError("base-model intake body hash drifted from frozen binding")
    intake_path = Path(base_model_intake_path)
    if _raw_sha256(intake_path) != BASE_INTAKE_FILE_SHA256:
        raise DependencyRegistryError("base-model intake file bytes drifted from frozen binding")
    try:
        intake_on_disk = json.loads(intake_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DependencyRegistryError("base-model intake file is not readable JSON") from error
    if intake_on_disk != dict(base_model_intake):
        raise DependencyRegistryError("base-model intake object differs from bound file")
    intake_binding = _mapping(plan["base_model_intake"], context="base intake binding")
    if intake_binding != {
        "intake_id": base_model_intake["intake_id"],
        "intake_body_sha256": BASE_INTAKE_BODY_SHA256,
        "file_sha256": BASE_INTAKE_FILE_SHA256,
    }:
        raise DependencyRegistryError("anchor plan base intake binding drifted")
    generator = _mapping(plan["training_generator"], context="training generator")
    expected_manifest = build_anchor_training_manifest()
    if _raw_sha256(generator_source_path) != GENERATOR_SOURCE_SHA256:
        raise DependencyRegistryError("anchor training generator source bytes drifted")
    if generator != {
        "source_path": "src/latent_trace_tomography/anchor_training.py",
        "source_sha256": GENERATOR_SOURCE_SHA256,
        "manifest": expected_manifest,
    }:
        raise DependencyRegistryError("anchor training generator drifted")
    if plan["global_training_contract"] != GLOBAL_TRAINING_CONTRACT:
        raise DependencyRegistryError("global anchor training contract drifted")
    if plan["family_adapter_contracts"] != FAMILY_ADAPTER_CONTRACTS:
        raise DependencyRegistryError("family adapter contract drifted")
    expected_runs = _expected_runs()
    if plan["runs"] != expected_runs:
        raise DependencyRegistryError("anchor run inventory or derived recipe hash drifted")
    if plan["anchor_assignment_manifest_sha256"] != _assignment_hash(expected_runs):
        raise DependencyRegistryError("anchor assignment manifest hash drifted")
    query_budget = _mapping(plan["query_budget"], context="anchor query budget")
    expected_calls = len(expected_runs) * GLOBAL_TRAINING_CONTRACT["fixed_optimizer_steps"]
    if query_budget != {
        "training_run_count": 9,
        "optimizer_step_count": expected_calls,
        "training_forward_call_count": expected_calls,
        "training_backward_call_count": expected_calls,
        "validation_forward_call_count": 0,
        "oss1_measurement_call_count": 0,
    }:
        raise DependencyRegistryError("anchor construction query budget drifted")
    if plan["outcome_exposure"] != {
        "training_started": False,
        "training_outputs_exposed": False,
        "oss1_measurement_calls": 0,
        "oss1_measurement_outcomes_exposed": False,
    }:
        raise DependencyRegistryError("pre-training outcome boundary drifted")
    if tuple(plan["prohibitions"]) != PROHIBITIONS:
        raise DependencyRegistryError("anchor construction prohibitions drifted")
    if tuple(plan["authorization_prerequisites"]) != AUTHORIZATION_PREREQUISITES:
        raise DependencyRegistryError("training-authorization prerequisites drifted")
    if plan["authorization_effect"] != AUTHORIZATION_EFFECT:
        raise DependencyRegistryError("frozen plan does not authorize training")
    if plan["plan_body_sha256"] != _body_hash(plan, "plan_body_sha256"):
        raise DependencyRegistryError("anchor construction plan is not self-addressed")
    return {
        "ok": True,
        "run_count": 9,
        "dependency_cluster_count": 3,
        "anchor_assignment_count": 9,
        "training_forward_call_budget": expected_calls,
        "training_started": False,
        "measurement_calls": 0,
        "model_calls_authorized": False,
        "plan_body_sha256": plan["plan_body_sha256"],
    }
