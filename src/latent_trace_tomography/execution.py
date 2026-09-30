"""Fail-closed contracts for OSS-1 discovery authorization and execution.

The design freeze authorizes no model calls.  A concrete discovery run first
needs an immutable, content-addressed discovery authorization.  Its bounded
report is then an input to a distinct final execution lock.  This module keeps
those two stages separate and validates cross-artifact equality in code because
JSON Schema alone cannot prove graph closure, artifact ancestry, or budget
compliance.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from latent_trace_tomography.blind import (
    AUDITOR_OBSERVATION_FIELDS,
    AUTHORITY_COMMITMENT_SCHEME,
    PAIRING_TOKEN_DOMAINS,
    PAIRING_TOKEN_SCHEME,
)
from latent_trace_tomography.oss_design import (
    INTERVENTION_PROMPT_TEMPLATE_ID,
    LIVE_CONTENT_SEED_DOMAIN,
    MATCHED_NULL_ROTATION_CONFORMANCE_VECTOR,
    MATCHED_NULL_ROTATION_SCHEME,
    MATCHED_NULL_ROTATION_STREAM_DOMAIN,
    MATCHED_NULL_ROTATION_WORD_ORDER,
    MATCHED_NULL_SITE_CONFORMANCE_VECTOR,
    MATCHED_NULL_SEED_CONFORMANCE_VECTOR,
    MATCHED_NULL_SEED_DOMAIN,
    MATCHED_NULL_SEED_FRAMING,
    MATCHED_NULL_SEED_SCHEME,
    TASK_GENERATOR_VERSION,
    TASK_ID,
    OSSProjectionRole,
    build_oss_design,
    derive_matched_null_seed,
    derive_live_content_seeds,
    matched_null_permutation_and_signs,
    parse_final,
)
from latent_trace_tomography.split import (
    CONTENT_PARTITION_COUNTS,
    SPLIT_RULE_ID,
    DependencyEdge,
    DependencyKind,
    ModelUnit,
    derive_dependency_clusters,
    partition_content_seeds,
)


SCHEMA_VERSION = "0.1.0"
DISCOVERY_AUTHORIZATION_STATUS = "authorized"
EXECUTION_LOCK_STATUS = "locked"
DEPENDENCY_GRAPH_ALGORITHM = "undirected_learned_state_connected_components_v1"
CAUSAL_VARIABLES = (
    "semantic_solution",
    "surface_cue",
    "answer_codebook",
)
ANCHOR_CONDITION_IDS = (
    "semantic_anchor",
    "surface_cue_anchor",
    "mixed_anchor",
)
FEATURE_WHITELIST = tuple(AUDITOR_OBSERVATION_FIELDS)
TRIAL_CONDITION_IDS = (
    "targeted_interchange",
    "norm_matched_rotation",
    "self_sham",
    "control_site_delta",
)
PARTITION_EXPECTATIONS: dict[str, dict[str, int]] = {
    "D_site_discovery": {
        "content_seeds": 8,
        "cases": 64,
        "projections": 256,
        "weak_observations": 160,
        "diagnostic_cue_masks": 32,
        "heldout_challenges": 64,
        "intervention_prompts": 64,
        "intervention_pairs": 192,
        "primary_intervention_pairs": 96,
        "primary_pairs_per_factor": 32,
    },
    "D_causal_label": {
        "content_seeds": 16,
        "cases": 128,
        "projections": 512,
        "weak_observations": 320,
        "diagnostic_cue_masks": 64,
        "heldout_challenges": 128,
        "intervention_prompts": 128,
        "intervention_pairs": 384,
        "primary_intervention_pairs": 192,
        "primary_pairs_per_factor": 64,
    },
    "D_behavior_fit": {
        "content_seeds": 24,
        "cases": 192,
        "projections": 768,
        "weak_observations": 480,
        "diagnostic_cue_masks": 96,
        "heldout_challenges": 192,
        "intervention_prompts": 192,
        "intervention_pairs": 576,
        "primary_intervention_pairs": 288,
        "primary_pairs_per_factor": 96,
    },
    "D_sealed_test": {
        "content_seeds": 16,
        "cases": 128,
        "projections": 512,
        "weak_observations": 320,
        "diagnostic_cue_masks": 64,
        "heldout_challenges": 128,
        "intervention_prompts": 128,
        "intervention_pairs": 384,
        "primary_intervention_pairs": 192,
        "primary_pairs_per_factor": 64,
    },
}
LIVE_MATERIAL_MANIFEST_SCHEME = "authority_hidden_generator_partition_manifest_v1"
LIVE_SEED_SET_HASH_SCHEME = "sha256_canonical_json_content_seeds_v1"
DISCOVERY_PRIMARY_PAIR_INVENTORY_SCHEME = "primary_pair_prompt_binding_inventory_v1"
CARRIER_BINDING_REPORT_SCHEME = "exact_tokenizer_carrier_binding_inventory_v1"
CARRIER_CONTROL_SELECTORS = {
    "semantic_solution": "last token of the Entity value",
    "surface_cue": "last token of the Entity value",
    "answer_codebook": (
        "two-position control in ascending token order: source ACCEPT carrier "
        "maps to the last token of the opening instruction line, then source "
        "REJECT carrier maps to the last token of the Entity value"
    ),
}

MODEL_RECORD_FIELDS = {
    "model_unit_id",
    "independent_training_run_id",
    "checkpoint_id",
    "lineage_id",
    "dependency_cluster_id",
    "architecture_family_id",
    "anchor_condition_id",
    "model_id",
    "model_revision",
    "model_artifact_sha256",
    "shared_base_artifact_sha256",
    "configuration_sha256",
    "tokenizer_revision",
    "tokenizer_artifact_sha256",
    "anchor_provenance",
}

CANDIDATE_SITE_ALGORITHM: dict[str, Any] = {
    "algorithm_id": "factor_specific_residual_stream_post_argmax_v1",
    "causal_variables": list(CAUSAL_VARIABLES),
    "candidate_activation": "residual_stream_post",
    "carrier_token_selectors": {
        "semantic_solution": "last token of the submitted_key value",
        "surface_cue": "last token of the non-authoritative archive cue value",
        "answer_codebook": (
            "last token of each ACCEPT and REJECT codebook mapping line, "
            "patched as one two-position site"
        ),
    },
    "selection_score": (
        "mean(targeted_success - norm_matched_rotation_success) over every "
        "preplanned symmetric-primary-stratum D_site_discovery pair"
    ),
    "selected_site_count_per_model_variable": 1,
    "tie_break_order": [
        "higher_selection_score",
        "lower_zero_based_layer_index",
        "lexicographically_smaller_canonical_site_id",
    ],
    "matched_null_randomization": {
        "seed_scheme": MATCHED_NULL_SEED_SCHEME,
        "seed_domain": MATCHED_NULL_SEED_DOMAIN.decode("ascii"),
        "seed_framing": MATCHED_NULL_SEED_FRAMING,
        "derivation_function": "latent_trace_tomography.oss_design.derive_matched_null_seed",
        "seed_conformance_vector": MATCHED_NULL_SEED_CONFORMANCE_VECTOR,
        "rotation_scheme": MATCHED_NULL_ROTATION_SCHEME,
        "rotation_stream_domain": MATCHED_NULL_ROTATION_STREAM_DOMAIN.decode("ascii"),
        "rotation_word_order": MATCHED_NULL_ROTATION_WORD_ORDER,
        "permutation_and_signs_reference_function": (
            "latent_trace_tomography.oss_design.matched_null_permutation_and_signs"
        ),
        "reference_application_function": (
            "latent_trace_tomography.oss_design.apply_norm_matched_rotation_site_v1"
        ),
        "live_tensor_application_contract": {
            "operator": "runtime_native_gather_sign_add_v1",
            "formula": (
                "delta=source_activation-base_activation;"
                "rotated_delta=signs*delta[permutation];"
                "patched_activation=base_activation+rotated_delta"
            ),
            "dtype_policy": "pinned_runtime_dtype_no_cast_v1",
            "device_policy": "base_source_permutation_signs_same_pinned_device_v1",
            "autograd_policy": "inference_mode_no_grad_v1",
            "rescaling_policy": "forbidden",
            "multi_position_policy": (
                "shared_hidden_axis_permutation_and_signs_independently_per_position_v1"
            ),
            "carrier_position_order": "ascending_token_position_v1",
        },
        "permutation_sampling": "unbiased_rejection_sampled_fisher_yates_descending_v1",
        "sign_sampling": "rademacher_from_uint64_lsb_even_positive_v1",
        "norm_handling": "signed_permutation_exact_no_rescaling_v1",
        "rotation_conformance_vector": MATCHED_NULL_ROTATION_CONFORMANCE_VECTOR,
        "site_conformance_vector": MATCHED_NULL_SITE_CONFORMANCE_VECTOR,
    },
    "randomization_namespace_field": "discovery_authorization_id",
}
NUISANCE_BALANCE_CONTRACT: dict[str, Any] = {
    "cluster_constant_fields": [
        "architecture_family_id",
        "tokenizer_revision",
        "tokenizer_artifact_sha256",
        "shared_base_artifact_sha256",
        "anchor_provenance.training_data_sha256",
        "anchor_provenance.anchor_assignment_manifest_sha256",
        "discovery_decoding_config.records_except_model_unit_id",
        "model_runtime_configuration.records_except_model_unit_id",
    ],
    "anchor_varying_fields": [
        "configuration_sha256",
        "model_artifact_sha256",
    ],
    "cross_cluster_identity_forbidden": [
        "checkpoint_id",
        "lineage_id",
        "model_artifact_sha256",
    ],
}

DISCOVERY_AUTHORIZATION_FIELDS = {
    "schema_version",
    "design_freeze_id",
    "parent_design_manifest_sha256",
    "status",
    "discovery_authorization_id",
    "authorized_at",
    "parent_discovery_template_sha256",
    "parent_execution_template_sha256",
    "architecture_families",
    "model_registry",
    "learned_state_ancestry",
    "dependency_graph",
    "dependency_clusters",
    "nuisance_balance_contract",
    "activation_hook_registry",
    "tokenizer_compatibility",
    "live_seed_commitment",
    "live_material_manifest_sha256",
    "live_material_manifest",
    "discovery_content_seed_set_sha256",
    "discovery_case_set_sha256",
    "discovery_case_count",
    "discovery_projection_set_sha256",
    "discovery_intervention_pair_set_sha256",
    "discovery_primary_intervention_pair_set_sha256",
    "discovery_primary_pair_inventory_sha256",
    "discovery_prompt_inventory_sha256",
    "split_manifest_sha256",
    "candidate_site_set_sha256",
    "candidate_site_inventory",
    "candidate_site_algorithm",
    "discovery_panel_sha256",
    "discovery_query_plan",
    "discovery_decoding_config",
    "model_runtime_configuration",
    "carrier_binding_report_sha256",
    "carrier_binding_records",
    "carrier_binding_summary",
    "environment_lock",
}

EXECUTION_LOCK_FIELDS = {
    "schema_version",
    "design_freeze_id",
    "parent_design_manifest_sha256",
    "status",
    "lock_id",
    "locked_at",
    "parent_execution_template_sha256",
    "discovery_authorization_id",
    "discovery_authorization_sha256",
    "site_discovery_report_sha256",
    "architecture_families",
    "model_registry",
    "learned_state_ancestry",
    "dependency_graph",
    "dependency_clusters",
    "nuisance_balance_contract",
    "activation_hook_registry",
    "tokenizer_compatibility",
    "live_seed_commitment",
    "live_material_manifest_sha256",
    "live_material_manifest",
    "discovery_content_seed_set_sha256",
    "discovery_case_set_sha256",
    "discovery_case_count",
    "discovery_projection_set_sha256",
    "discovery_intervention_pair_set_sha256",
    "discovery_primary_intervention_pair_set_sha256",
    "discovery_primary_pair_inventory_sha256",
    "discovery_prompt_inventory_sha256",
    "candidate_site_set_sha256",
    "candidate_site_inventory",
    "candidate_site_algorithm",
    "discovery_panel_sha256",
    "discovery_query_plan",
    "discovery_decoding_config",
    "model_runtime_configuration",
    "carrier_binding_report_sha256",
    "carrier_binding_records",
    "carrier_binding_summary",
    "causal_site_discovery",
    "case_set_sha256",
    "projection_set_sha256",
    "intervention_pair_set_sha256",
    "primary_intervention_pair_set_sha256",
    "causal_label_primary_intervention_pair_set_sha256",
    "causal_label_primary_pair_inventory_sha256",
    "causal_label_unpatched_prompt_inventory_sha256",
    "split_manifest_sha256",
    "feature_whitelist",
    "query_plan",
    "post_discovery_decoding_config",
    "post_discovery_carrier_binding_report_sha256",
    "post_discovery_carrier_binding_records",
    "post_discovery_carrier_binding_summary",
    "blind_runtime",
    "prospective_contract",
    "authority_commitments",
    "environment_lock",
}

AUTHORIZATION_BOUND_FIELDS = (
    "architecture_families",
    "model_registry",
    "learned_state_ancestry",
    "dependency_graph",
    "dependency_clusters",
    "nuisance_balance_contract",
    "activation_hook_registry",
    "tokenizer_compatibility",
    "live_seed_commitment",
    "live_material_manifest_sha256",
    "live_material_manifest",
    "discovery_content_seed_set_sha256",
    "discovery_case_set_sha256",
    "discovery_case_count",
    "discovery_projection_set_sha256",
    "discovery_intervention_pair_set_sha256",
    "discovery_primary_intervention_pair_set_sha256",
    "discovery_primary_pair_inventory_sha256",
    "discovery_prompt_inventory_sha256",
    "split_manifest_sha256",
    "candidate_site_set_sha256",
    "candidate_site_inventory",
    "candidate_site_algorithm",
    "discovery_panel_sha256",
    "discovery_query_plan",
    "discovery_decoding_config",
    "model_runtime_configuration",
    "carrier_binding_report_sha256",
    "carrier_binding_records",
    "carrier_binding_summary",
    "environment_lock",
)

DISCOVERY_QUERY_COMPONENTS = (
    "unpatched_forward_passes",
    "targeted_intervention_forward_passes",
    "matched_null_forward_passes",
    "self_sham_forward_passes",
    "control_site_forward_passes",
)
POST_DISCOVERY_QUERY_COMPONENTS = (
    "causal_label_forward_passes",
    "behavior_fit_forward_passes",
    "sealed_test_forward_passes",
    "diagnostic_forward_passes",
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ExecutionContractError(ValueError):
    """Raised when an execution-boundary artifact fails closed."""


def canonical_artifact_sha256(value: Any) -> str:
    """Return the contract's canonical-JSON content address for an artifact."""

    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def canonical_content_seed_set_sha256(content_seeds: Sequence[int]) -> str:
    """Content-address one exact ordered set of hidden content seeds."""

    return canonical_artifact_sha256({"content_seeds": list(content_seeds)})


def _opaque_content_seed_id(content_seed: int) -> str:
    material = b"ltt:opaque-content-seed-id:v1\x00" + content_seed.to_bytes(8, "big")
    return hashlib.sha256(material).hexdigest()


def _primary_pair_inventory(design: Any) -> list[dict[str, Any]]:
    cases = {case.case_id: case for case in design.cases}
    inventory = [
        {
            "causal_variable": pair.factor.value,
            "pair_id": pair.pair_id,
            "opaque_content_seed_id": _opaque_content_seed_id(pair.content_seed),
            "pair_record_sha256": canonical_artifact_sha256(pair.to_dict()),
            "base_prompt_id": pair.base_prompt_id,
            "base_prompt_sha256": pair.base_prompt_sha256,
            "source_prompt_id": pair.source_prompt_id,
            "source_prompt_sha256": pair.source_prompt_sha256,
            "expected_patched_final": pair.expected_patched_final,
            "base_oracle_final": cases[pair.base_case_id].oracle_final,
        }
        for pair in design.primary_intervention_pairs
    ]
    return sorted(inventory, key=lambda item: (item["causal_variable"], item["pair_id"]))


def _intervention_prompt_inventory(design: Any) -> list[dict[str, Any]]:
    cases = {case.case_id: case for case in design.cases}
    return sorted(
        [
            {
                "prompt_id": prompt.prompt_id,
                "case_id": prompt.case_id,
                "prompt_sha256": prompt.prompt_sha256,
                "prompt_record_sha256": canonical_artifact_sha256(prompt.to_dict()),
                "oracle_final": cases[prompt.case_id].oracle_final,
            }
            for prompt in design.intervention_prompts
        ],
        key=lambda item: item["prompt_id"],
    )


def build_live_material_manifest(authority_secret: bytes) -> dict[str, Any]:
    """Build the authority-side exact generator/split commitment.

    Raw seeds and prompt text stay authority-held.  Counts and generator hashes
    are serialized before model execution; ``validate_live_material_reveal``
    later regenerates them from the committed secret and rejects substitution.
    """

    seeds = derive_live_content_seeds(authority_secret, 64)
    partitions = partition_content_seeds(seeds)
    records: list[dict[str, Any]] = []
    discovery_inventory: list[dict[str, Any]] | None = None
    discovery_prompt_inventory: list[dict[str, Any]] | None = None
    for partition_id, _ in CONTENT_PARTITION_COUNTS:
        partition_seeds = partitions[partition_id]
        design = build_oss_design(partition_seeds)
        manifest = design.manifest()
        prompt_inventory = _intervention_prompt_inventory(design)
        primary_pair_inventory = _primary_pair_inventory(design)
        pair_counts = Counter(pair.factor.value for pair in design.primary_intervention_pairs)
        role_counts = {
            "weak_observations": len(design.weak_observations),
            "diagnostic_cue_masks": len(design.diagnostic_cue_masks),
            "heldout_challenges": len(design.heldout_challenges),
        }
        records.append(
            {
                "partition_id": partition_id,
                "content_seed_count": len(partition_seeds),
                "content_seed_set_sha256": canonical_content_seed_set_sha256(partition_seeds),
                "case_count": manifest["counts"]["cases"],
                "case_set_sha256": manifest["case_set_sha256"],
                "projection_count": manifest["counts"]["projections"],
                "projection_set_sha256": manifest["projection_set_sha256"],
                **role_counts,
                "intervention_prompt_count": manifest["counts"]["intervention_prompts"],
                "intervention_prompt_set_sha256": manifest["intervention_prompt_set_sha256"],
                "intervention_prompt_inventory": prompt_inventory,
                "intervention_prompt_inventory_sha256": canonical_artifact_sha256(
                    {"intervention_prompt_inventory": prompt_inventory}
                ),
                "intervention_pair_count": manifest["counts"]["intervention_pairs"],
                "intervention_pair_set_sha256": manifest["intervention_pair_set_sha256"],
                "primary_intervention_pair_count": manifest["counts"]["primary_intervention_pairs"],
                "primary_intervention_pair_set_sha256": manifest[
                    "primary_intervention_pair_set_sha256"
                ],
                "primary_pair_inventory": primary_pair_inventory,
                "primary_pair_inventory_sha256": canonical_artifact_sha256(
                    {"primary_pair_inventory": primary_pair_inventory}
                ),
                "primary_pair_count_by_causal_variable": {
                    variable: pair_counts[variable] for variable in CAUSAL_VARIABLES
                },
                "design_manifest_sha256": manifest["manifest_sha256"],
            }
        )
        if partition_id == "D_site_discovery":
            discovery_inventory = primary_pair_inventory
            discovery_prompt_inventory = prompt_inventory
    if discovery_inventory is None:  # pragma: no cover - frozen split always includes it.
        raise AssertionError("D_site_discovery partition is missing")
    if discovery_prompt_inventory is None:  # pragma: no cover
        raise AssertionError("D_site_discovery prompt inventory is missing")
    body = {
        "scheme": LIVE_MATERIAL_MANIFEST_SCHEME,
        "seed_set_hash_scheme": LIVE_SEED_SET_HASH_SCHEME,
        "task_id": TASK_ID,
        "task_generator_version": TASK_GENERATOR_VERSION,
        "split_rule_id": SPLIT_RULE_ID,
        "derived_seed_set_sha256": canonical_content_seed_set_sha256(seeds),
        "partition_records": records,
        "discovery_primary_pair_inventory_scheme": (DISCOVERY_PRIMARY_PAIR_INVENTORY_SCHEME),
        "discovery_primary_pair_inventory": discovery_inventory,
        "discovery_primary_pair_inventory_sha256": canonical_artifact_sha256(
            {"discovery_primary_pair_inventory": discovery_inventory}
        ),
        "discovery_intervention_prompt_inventory": discovery_prompt_inventory,
        "discovery_intervention_prompt_inventory_sha256": canonical_artifact_sha256(
            {"discovery_intervention_prompt_inventory": discovery_prompt_inventory}
        ),
    }
    return body


def validate_live_material_reveal(
    authority_secret: bytes, *, authorization: Mapping[str, Any]
) -> None:
    """Regenerate every hidden partition and hash before any model call."""

    if not isinstance(authority_secret, bytes) or len(authority_secret) < 32:
        raise ExecutionContractError("authority_secret must contain at least 256 bits")
    commitment = hashlib.sha256(authority_secret).hexdigest()
    if commitment != authorization["live_seed_commitment"]["authority_secret_commitment_sha256"]:
        raise ExecutionContractError("authority secret does not open its commitment")
    expected = build_live_material_manifest(authority_secret)
    if expected != authorization["live_material_manifest"]:
        raise ExecutionContractError(
            "revealed generator material does not equal the authorized manifest"
        )
    if canonical_artifact_sha256(expected) != authorization["live_material_manifest_sha256"]:
        raise ExecutionContractError("live material manifest content address mismatch")


def validate_discovery_readiness(
    authorization: Mapping[str, Any],
    *,
    authority_secret: bytes,
    expected_parent_design_manifest_sha256: str,
    expected_parent_discovery_template_sha256: str,
    expected_parent_execution_template_sha256: str,
) -> None:
    """Required production gate immediately before the first forward pass."""

    validate_discovery_authorization(
        authorization,
        expected_parent_design_manifest_sha256=expected_parent_design_manifest_sha256,
        expected_parent_discovery_template_sha256=(expected_parent_discovery_template_sha256),
        expected_parent_execution_template_sha256=(expected_parent_execution_template_sha256),
    )
    validate_live_material_reveal(authority_secret, authorization=authorization)


def _mapping(value: Any, *, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ExecutionContractError(f"{context} must be an object")
    return value


def _sequence(value: Any, *, context: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise ExecutionContractError(f"{context} must be an array")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], *, context: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise ExecutionContractError(f"{context} fields mismatch: missing={missing}, extra={extra}")


def _text(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExecutionContractError(f"{context} must be non-empty text")
    return value


def _sha256(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ExecutionContractError(f"{context} must be a lowercase SHA-256 digest")
    return value


def _trusted_sha256(value: Any, *, context: str) -> str:
    digest = _sha256(value, context=context)
    if digest == "0" * 64:
        raise ExecutionContractError(f"{context} must not use the all-zero sentinel")
    return digest


def _positive_int(value: Any, *, context: str) -> int:
    if type(value) is not int or value < 1:
        raise ExecutionContractError(f"{context} must be a positive integer")
    return value


def _nonnegative_int(value: Any, *, context: str) -> int:
    if type(value) is not int or value < 0:
        raise ExecutionContractError(f"{context} must be a non-negative integer")
    return value


def _finite_number(value: Any, *, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExecutionContractError(f"{context} must be a finite number")
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        raise ExecutionContractError(f"{context} must be a finite number")
    return number


def _timestamp(value: Any, *, context: str) -> str:
    text = _text(value, context=context)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ExecutionContractError(f"{context} must be an RFC 3339 timestamp") from error
    if parsed.tzinfo is None:
        raise ExecutionContractError(f"{context} must include a timezone")
    return text


def _sorted_unique_texts(value: Any, *, context: str, minimum: int = 1) -> tuple[str, ...]:
    values = _sequence(value, context=context)
    normalized = tuple(
        _text(item, context=f"{context}[{index}]") for index, item in enumerate(values)
    )
    if len(normalized) < minimum:
        raise ExecutionContractError(f"{context} must contain at least {minimum} item(s)")
    if len(set(normalized)) != len(normalized):
        raise ExecutionContractError(f"{context} must contain unique values")
    if normalized != tuple(sorted(normalized)):
        raise ExecutionContractError(f"{context} must be sorted lexicographically")
    return normalized


def _validate_model_registry(value: Any) -> tuple[Mapping[str, Any], ...]:
    records = _sequence(value, context="model_registry")
    if len(records) != 9:
        raise ExecutionContractError(
            "model_registry must contain exactly nine units for the frozen three-cluster pilot"
        )
    normalized: list[Mapping[str, Any]] = []
    uniqueness: dict[str, set[Any]] = {
        "model_unit_id": set(),
        "independent_training_run_id": set(),
        "checkpoint_id": set(),
        "model_artifact_sha256": set(),
        "model_identity": set(),
    }
    for index, raw in enumerate(records):
        record = _mapping(raw, context=f"model_registry[{index}]")
        _exact_keys(record, MODEL_RECORD_FIELDS, context=f"model_registry[{index}]")
        for field in MODEL_RECORD_FIELDS - {
            "model_artifact_sha256",
            "shared_base_artifact_sha256",
            "configuration_sha256",
            "tokenizer_artifact_sha256",
            "anchor_provenance",
        }:
            _text(record[field], context=f"model_registry[{index}].{field}")
        if record["anchor_condition_id"] not in ANCHOR_CONDITION_IDS:
            raise ExecutionContractError(
                "model_registry anchor_condition_id must be one of the frozen anchor ids"
            )
        for field in (
            "model_artifact_sha256",
            "shared_base_artifact_sha256",
            "configuration_sha256",
            "tokenizer_artifact_sha256",
        ):
            _trusted_sha256(record[field], context=f"model_registry[{index}].{field}")
        provenance = _mapping(
            record["anchor_provenance"],
            context=f"model_registry[{index}].anchor_provenance",
        )
        _exact_keys(
            provenance,
            {
                "assignment_timing",
                "anchor_assignment_manifest_sha256",
                "training_recipe_sha256",
                "training_data_sha256",
            },
            context=f"model_registry[{index}].anchor_provenance",
        )
        if provenance["assignment_timing"] != "pre_outcome_training_condition":
            raise ExecutionContractError(
                "anchor assignment must be fixed as a pre-outcome training condition"
            )
        for field in (
            "anchor_assignment_manifest_sha256",
            "training_recipe_sha256",
            "training_data_sha256",
        ):
            _trusted_sha256(
                provenance[field],
                context=f"model_registry[{index}].anchor_provenance.{field}",
            )
        identities = {
            "model_unit_id": record["model_unit_id"],
            "independent_training_run_id": record["independent_training_run_id"],
            "checkpoint_id": record["checkpoint_id"],
            "model_artifact_sha256": record["model_artifact_sha256"],
            "model_identity": (
                record["model_id"],
                record["model_revision"],
                record["tokenizer_revision"],
            ),
        }
        for field, identity in identities.items():
            if identity in uniqueness[field]:
                raise ExecutionContractError(f"model_registry has duplicate {field}={identity!r}")
            uniqueness[field].add(identity)
        normalized.append(record)
    ordered_ids = [record["model_unit_id"] for record in normalized]
    if ordered_ids != sorted(ordered_ids):
        raise ExecutionContractError("model_registry must be sorted by model_unit_id")
    return tuple(normalized)


def _validate_learned_state_ancestry(
    value: Any, *, model_registry: tuple[Mapping[str, Any], ...]
) -> set[tuple[str, str, str]]:
    inventory = _mapping(value, context="learned_state_ancestry")
    _exact_keys(
        inventory,
        {"policy_id", "external_artifacts", "records", "inventory_sha256"},
        context="learned_state_ancestry",
    )
    if inventory["policy_id"] != "complete_learned_state_parent_inventory_fail_closed_v1":
        raise ExecutionContractError("learned-state ancestry policy is not frozen")
    external_values = _sequence(
        inventory["external_artifacts"],
        context="learned_state_ancestry.external_artifacts",
    )
    external_by_hash: dict[str, Mapping[str, Any]] = {}
    external_order: list[str] = []
    for index, raw in enumerate(external_values):
        external = _mapping(raw, context=f"learned_state_ancestry.external_artifacts[{index}]")
        _exact_keys(
            external,
            {"artifact_sha256", "artifact_role", "source_record_sha256"},
            context=f"learned_state_ancestry.external_artifacts[{index}]",
        )
        artifact_sha256 = _trusted_sha256(
            external["artifact_sha256"],
            context=(f"learned_state_ancestry.external_artifacts[{index}].artifact_sha256"),
        )
        if external["artifact_role"] not in {
            "shared_base",
            "external_teacher",
            "merge_parent",
            "adapter_base",
        }:
            raise ExecutionContractError("external ancestry artifact role is not frozen")
        _trusted_sha256(
            external["source_record_sha256"],
            context=(f"learned_state_ancestry.external_artifacts[{index}].source_record_sha256"),
        )
        if artifact_sha256 in external_by_hash:
            raise ExecutionContractError("external ancestry artifacts must be unique")
        external_by_hash[artifact_sha256] = external
        external_order.append(artifact_sha256)
    if external_order != sorted(external_order):
        raise ExecutionContractError("external ancestry artifacts must be sorted by hash")

    models_by_id = {model["model_unit_id"]: model for model in model_registry}
    model_by_artifact = {model["model_artifact_sha256"]: model for model in model_registry}
    record_values = _sequence(inventory["records"], context="learned_state_ancestry.records")
    if len(record_values) != len(model_registry):
        raise ExecutionContractError("ancestry inventory must cover every model unit")
    ancestry_by_model: dict[str, Mapping[str, Any]] = {}
    model_parent_hashes: dict[str, set[str]] = {}
    record_order: list[str] = []
    direct_edges: set[tuple[str, str, str]] = set()
    allowed_relationships = {kind.value for kind in DependencyKind}
    for index, raw in enumerate(record_values):
        record = _mapping(raw, context=f"learned_state_ancestry.records[{index}]")
        _exact_keys(
            record,
            {
                "model_unit_id",
                "model_artifact_sha256",
                "ancestry_complete",
                "ambiguous_parentage",
                "parents",
            },
            context=f"learned_state_ancestry.records[{index}]",
        )
        model_id = _text(
            record["model_unit_id"],
            context=f"learned_state_ancestry.records[{index}].model_unit_id",
        )
        if model_id not in models_by_id or model_id in ancestry_by_model:
            raise ExecutionContractError("ancestry inventory has a duplicate or unknown model unit")
        if record["model_artifact_sha256"] != models_by_id[model_id]["model_artifact_sha256"]:
            raise ExecutionContractError("ancestry model artifact drifted from registry")
        if record["ancestry_complete"] is not True or record["ambiguous_parentage"] is not False:
            raise ExecutionContractError(
                "learned-state ancestry must be declared complete and unambiguous"
            )
        parents = _sequence(
            record["parents"],
            context=f"learned_state_ancestry.records[{index}].parents",
        )
        if not parents:
            raise ExecutionContractError("every model must declare learned-state parentage")
        parent_order: list[tuple[str, str, str]] = []
        parent_hashes: set[str] = set()
        has_shared_base = False
        for parent_index, raw_parent in enumerate(parents):
            parent = _mapping(
                raw_parent,
                context=(f"learned_state_ancestry.records[{index}].parents[{parent_index}]"),
            )
            _exact_keys(
                parent,
                {
                    "parent_artifact_sha256",
                    "parent_model_unit_id",
                    "relationship",
                    "source_record_sha256",
                },
                context=(f"learned_state_ancestry.records[{index}].parents[{parent_index}]"),
            )
            parent_hash = _trusted_sha256(
                parent["parent_artifact_sha256"],
                context=(
                    f"learned_state_ancestry.records[{index}].parents[{parent_index}]"
                    ".parent_artifact_sha256"
                ),
            )
            relationship = parent["relationship"]
            if relationship not in allowed_relationships:
                raise ExecutionContractError("ancestry relationship is not frozen")
            _trusted_sha256(
                parent["source_record_sha256"],
                context=(
                    f"learned_state_ancestry.records[{index}].parents[{parent_index}]"
                    ".source_record_sha256"
                ),
            )
            parent_model_id = parent["parent_model_unit_id"]
            if parent_model_id is None:
                if parent_hash not in external_by_hash:
                    raise ExecutionContractError(
                        "external learned-state parent is absent from artifact inventory"
                    )
            else:
                if parent_model_id not in models_by_id:
                    raise ExecutionContractError(
                        "ancestry parent_model_unit_id is absent from model registry"
                    )
                if parent_model_id == model_id:
                    raise ExecutionContractError("ancestry cannot contain a self parent")
                if model_by_artifact.get(parent_hash) != models_by_id[parent_model_id]:
                    raise ExecutionContractError(
                        "ancestry parent model id and artifact hash disagree"
                    )
                direct_edges.add(
                    (
                        min(parent_model_id, model_id),
                        max(parent_model_id, model_id),
                        relationship,
                    )
                )
            if (
                parent_hash == models_by_id[model_id]["shared_base_artifact_sha256"]
                and relationship == DependencyKind.SHARED_LEARNED_WEIGHTS.value
            ):
                has_shared_base = True
            identity = (
                parent_hash,
                "" if parent_model_id is None else parent_model_id,
                relationship,
            )
            if identity in parent_order:
                raise ExecutionContractError("ancestry contains a duplicate parent row")
            parent_order.append(identity)
            parent_hashes.add(parent_hash)
        if parent_order != sorted(parent_order):
            raise ExecutionContractError("ancestry parents must be canonically sorted")
        if not has_shared_base:
            raise ExecutionContractError(
                "every model must bind its registry shared_base_artifact_sha256 as a parent"
            )
        ancestry_by_model[model_id] = record
        model_parent_hashes[model_id] = parent_hashes
        record_order.append(model_id)
    if record_order != sorted(models_by_id) or set(ancestry_by_model) != set(models_by_id):
        raise ExecutionContractError("ancestry records must be complete and sorted")
    expected_edges = set(direct_edges)
    model_ids = sorted(models_by_id)
    for left_index, left in enumerate(model_ids):
        for right in model_ids[left_index + 1 :]:
            if model_parent_hashes[left] & model_parent_hashes[right]:
                expected_edges.add((left, right, DependencyKind.SHARED_LEARNED_WEIGHTS.value))
    hash_body = {
        "policy_id": inventory["policy_id"],
        "external_artifacts": list(external_values),
        "records": list(record_values),
    }
    if inventory["inventory_sha256"] != canonical_artifact_sha256(hash_body):
        raise ExecutionContractError("learned-state ancestry hash is not content-addressed")
    return expected_edges


def _validate_dependency_surface(
    *,
    model_registry: tuple[Mapping[str, Any], ...],
    dependency_graph_value: Any,
    dependency_clusters_value: Any,
    expected_ancestry_edges: set[tuple[str, str, str]],
) -> None:
    graph = _mapping(dependency_graph_value, context="dependency_graph")
    _exact_keys(graph, {"algorithm", "nodes", "edges"}, context="dependency_graph")
    if graph["algorithm"] != DEPENDENCY_GRAPH_ALGORITHM:
        raise ExecutionContractError("dependency_graph.algorithm is not frozen")

    registry_ids = tuple(record["model_unit_id"] for record in model_registry)
    nodes = _sorted_unique_texts(graph["nodes"], context="dependency_graph.nodes", minimum=9)
    if nodes != registry_ids:
        raise ExecutionContractError("dependency_graph.nodes must exactly equal model_registry ids")

    edge_values = _sequence(graph["edges"], context="dependency_graph.edges")
    edges: list[DependencyEdge] = []
    edge_order: list[tuple[str, str, str]] = []
    seen_edges: set[tuple[str, str, str]] = set()
    known = set(registry_ids)
    for index, raw in enumerate(edge_values):
        edge = _mapping(raw, context=f"dependency_graph.edges[{index}]")
        _exact_keys(
            edge,
            {"source_model_unit_id", "target_model_unit_id", "kind"},
            context=f"dependency_graph.edges[{index}]",
        )
        source = _text(
            edge["source_model_unit_id"],
            context=f"dependency_graph.edges[{index}].source_model_unit_id",
        )
        target = _text(
            edge["target_model_unit_id"],
            context=f"dependency_graph.edges[{index}].target_model_unit_id",
        )
        if source not in known or target not in known:
            raise ExecutionContractError("dependency edge references an unknown model unit")
        if source == target:
            raise ExecutionContractError("dependency edge cannot be a self-edge")
        try:
            kind = DependencyKind(edge["kind"])
        except (TypeError, ValueError) as error:
            raise ExecutionContractError("dependency edge kind is not frozen") from error
        identity = (min(source, target), max(source, target), kind.value)
        if identity in seen_edges:
            raise ExecutionContractError("dependency_graph contains a duplicate edge")
        seen_edges.add(identity)
        edge_order.append((source, target, kind.value))
        edges.append(DependencyEdge(source, target, kind))
    if edge_order != sorted(edge_order):
        raise ExecutionContractError("dependency_graph.edges must be sorted canonically")
    if seen_edges != expected_ancestry_edges:
        raise ExecutionContractError(
            "dependency_graph edges must be derived exactly from learned-state ancestry"
        )

    declared_values = _sequence(dependency_clusters_value, context="dependency_clusters")
    if len(declared_values) != 3:
        raise ExecutionContractError("dependency_clusters must contain exactly three clusters")
    declared: list[dict[str, Any]] = []
    seen_cluster_ids: set[str] = set()
    assigned_units: set[str] = set()
    for index, raw in enumerate(declared_values):
        cluster = _mapping(raw, context=f"dependency_clusters[{index}]")
        _exact_keys(
            cluster,
            {"dependency_cluster_id", "model_unit_ids"},
            context=f"dependency_clusters[{index}]",
        )
        cluster_id = _text(
            cluster["dependency_cluster_id"],
            context=f"dependency_clusters[{index}].dependency_cluster_id",
        )
        if cluster_id in seen_cluster_ids:
            raise ExecutionContractError("dependency_cluster_id values must be unique")
        seen_cluster_ids.add(cluster_id)
        members = _sorted_unique_texts(
            cluster["model_unit_ids"],
            context=f"dependency_clusters[{index}].model_unit_ids",
        )
        unknown = set(members) - known
        if unknown:
            raise ExecutionContractError(
                f"dependency cluster references unknown model units={sorted(unknown)}"
            )
        overlap = assigned_units & set(members)
        if overlap:
            raise ExecutionContractError(
                f"model units occur in multiple dependency clusters={sorted(overlap)}"
            )
        assigned_units.update(members)
        declared.append({"dependency_cluster_id": cluster_id, "model_unit_ids": list(members)})
    if assigned_units != known:
        raise ExecutionContractError("dependency_clusters must partition every model unit exactly")
    if declared != sorted(declared, key=lambda item: item["dependency_cluster_id"]):
        raise ExecutionContractError("dependency_clusters must be sorted by id")

    units = tuple(
        ModelUnit(
            model_unit_id=record["model_unit_id"],
            independent_training_run_id=record["independent_training_run_id"],
            architecture_family_id=record["architecture_family_id"],
            anchor_condition_id=record["anchor_condition_id"],
        )
        for record in model_registry
    )
    derived = [cluster.to_dict() for cluster in derive_dependency_clusters(units, edges)]
    if declared != derived:
        raise ExecutionContractError(
            "declared dependency clusters do not equal graph connected components; "
            "an ancestry edge may cross the split"
        )
    cluster_by_unit = {
        unit_id: cluster["dependency_cluster_id"]
        for cluster in declared
        for unit_id in cluster["model_unit_ids"]
    }
    for record in model_registry:
        if record["dependency_cluster_id"] != cluster_by_unit[record["model_unit_id"]]:
            raise ExecutionContractError(
                "model_registry dependency_cluster_id disagrees with the dependency graph"
            )
    records_by_unit = {record["model_unit_id"]: record for record in model_registry}
    required_anchor_counts = Counter(ANCHOR_CONDITION_IDS)
    observed_shared_bases: set[str] = set()
    for cluster in declared:
        cluster_records = [records_by_unit[unit_id] for unit_id in cluster["model_unit_ids"]]
        observed_anchor_counts = Counter(
            record["anchor_condition_id"] for record in cluster_records
        )
        if observed_anchor_counts != required_anchor_counts:
            raise ExecutionContractError(
                "each dependency cluster must contain exactly one semantic_anchor, "
                "surface_cue_anchor, and mixed_anchor"
            )
        if len({record["architecture_family_id"] for record in cluster_records}) != 1:
            raise ExecutionContractError(
                "all three anchors in a dependency cluster must share architecture_family_id"
            )
        tokenizer_identities = {
            (record["tokenizer_revision"], record["tokenizer_artifact_sha256"])
            for record in cluster_records
        }
        if len(tokenizer_identities) != 1:
            raise ExecutionContractError(
                "all three anchors in a dependency cluster must share tokenizer identity"
            )
        shared_bases = {record["shared_base_artifact_sha256"] for record in cluster_records}
        if len(shared_bases) != 1:
            raise ExecutionContractError(
                "all three anchors in a dependency cluster must share one base artifact"
            )
        shared_base = next(iter(shared_bases))
        if shared_base in observed_shared_bases:
            raise ExecutionContractError("shared_base_artifact_sha256 crosses dependency clusters")
        observed_shared_bases.add(shared_base)
        training_data_hashes = {
            record["anchor_provenance"]["training_data_sha256"] for record in cluster_records
        }
        assignment_hashes = {
            record["anchor_provenance"]["anchor_assignment_manifest_sha256"]
            for record in cluster_records
        }
        if len(training_data_hashes) != 1 or len(assignment_hashes) != 1:
            raise ExecutionContractError(
                "anchor cluster must share training-data and assignment-manifest provenance"
            )
        member_ids = set(cluster["model_unit_ids"])
        shared_adjacency = {unit_id: set() for unit_id in member_ids}
        for edge in edges:
            if (
                edge.kind is DependencyKind.SHARED_LEARNED_WEIGHTS
                and edge.left_model_unit_id in member_ids
                and edge.right_model_unit_id in member_ids
            ):
                shared_adjacency[edge.left_model_unit_id].add(edge.right_model_unit_id)
                shared_adjacency[edge.right_model_unit_id].add(edge.left_model_unit_id)
        reached: set[str] = set()
        frontier = [min(member_ids)]
        while frontier:
            unit_id = frontier.pop()
            if unit_id in reached:
                continue
            reached.add(unit_id)
            frontier.extend(sorted(shared_adjacency[unit_id] - reached))
        if reached != member_ids:
            raise ExecutionContractError(
                "shared-base cluster must be connected by shared_learned_weights edges"
            )
    clusters_by_lineage: dict[str, set[str]] = {}
    for record in model_registry:
        clusters_by_lineage.setdefault(record["lineage_id"], set()).add(
            record["dependency_cluster_id"]
        )
    cross_cluster_lineages = sorted(
        lineage_id
        for lineage_id, cluster_ids in clusters_by_lineage.items()
        if len(cluster_ids) != 1
    )
    if cross_cluster_lineages:
        raise ExecutionContractError(
            "lineage_id crosses dependency clusters=" + ",".join(cross_cluster_lineages)
        )


def _validate_tokenizer_compatibility(
    value: Any, *, model_registry: tuple[Mapping[str, Any], ...]
) -> None:
    report = _mapping(value, context="tokenizer_compatibility")
    _exact_keys(
        report,
        {"algorithm", "add_special_tokens", "records"},
        context="tokenizer_compatibility",
    )
    if report["algorithm"] != "final_marker_single_continuation_v1":
        raise ExecutionContractError("tokenizer compatibility algorithm is not frozen")
    if report["add_special_tokens"] is not False:
        raise ExecutionContractError("tokenizer compatibility must use add_special_tokens=false")
    records = _sequence(report["records"], context="tokenizer_compatibility.records")
    if len(records) != len(model_registry):
        raise ExecutionContractError("tokenizer compatibility must cover every model unit exactly")
    registry_by_id = {record["model_unit_id"]: record for record in model_registry}
    seen: set[str] = set()
    ordered_ids: list[str] = []
    expected = {
        "model_unit_id",
        "tokenizer_revision",
        "tokenizer_artifact_sha256",
        "final_prefix_token_ids",
        "final_a_token_ids",
        "final_b_token_ids",
        "final_a_continuation_token_id",
        "final_b_continuation_token_id",
        "compatible",
    }
    for index, raw in enumerate(records):
        item = _mapping(raw, context=f"tokenizer_compatibility.records[{index}]")
        _exact_keys(item, expected, context=f"tokenizer_compatibility.records[{index}]")
        unit_id = _text(
            item["model_unit_id"],
            context=f"tokenizer_compatibility.records[{index}].model_unit_id",
        )
        if unit_id in seen or unit_id not in registry_by_id:
            raise ExecutionContractError(
                "tokenizer compatibility unit ids must be exact and unique"
            )
        seen.add(unit_id)
        ordered_ids.append(unit_id)
        registry_record = registry_by_id[unit_id]
        if item["tokenizer_revision"] != registry_record["tokenizer_revision"]:
            raise ExecutionContractError("tokenizer revision drifted from model_registry")
        if item["tokenizer_artifact_sha256"] != registry_record["tokenizer_artifact_sha256"]:
            raise ExecutionContractError("tokenizer artifact hash drifted from model_registry")
        token_arrays: dict[str, list[int]] = {}
        for field in (
            "final_prefix_token_ids",
            "final_a_token_ids",
            "final_b_token_ids",
        ):
            values = _sequence(
                item[field], context=f"tokenizer_compatibility.records[{index}].{field}"
            )
            if not values or any(type(token_id) is not int or token_id < 0 for token_id in values):
                raise ExecutionContractError(
                    "tokenizer compatibility token arrays must be non-empty non-negative ids"
                )
            token_arrays[field] = list(values)
        token_a = _nonnegative_int(
            item["final_a_continuation_token_id"],
            context=f"tokenizer_compatibility.records[{index}].final_a_continuation_token_id",
        )
        token_b = _nonnegative_int(
            item["final_b_continuation_token_id"],
            context=f"tokenizer_compatibility.records[{index}].final_b_continuation_token_id",
        )
        prefix = token_arrays["final_prefix_token_ids"]
        compatible = (
            token_a != token_b
            and token_arrays["final_a_token_ids"] == [*prefix, token_a]
            and token_arrays["final_b_token_ids"] == [*prefix, token_b]
        )
        if not compatible or item["compatible"] is not compatible:
            raise ExecutionContractError(
                "tokenizer full FINAL markers must equal prefix plus one distinct continuation"
            )
    if ordered_ids != sorted(ordered_ids) or seen != set(registry_by_id):
        raise ExecutionContractError("tokenizer compatibility records must be sorted and complete")


def _validate_activation_hook_registry(
    value: Any, *, architecture_families: tuple[str, ...]
) -> dict[str, Mapping[str, Any]]:
    registry = _mapping(value, context="activation_hook_registry")
    _exact_keys(registry, {"hook_boundary", "records"}, context="activation_hook_registry")
    if registry["hook_boundary"] != "post_block_residual_before_next_block_v1":
        raise ExecutionContractError("activation hook boundary is not frozen")
    records = _sequence(registry["records"], context="activation_hook_registry.records")
    if len(records) != len(architecture_families):
        raise ExecutionContractError(
            "activation hook registry must cover every architecture family"
        )
    observed: list[str] = []
    expected_fields = {
        "architecture_family_id",
        "hook_adapter_id",
        "hook_registry_source_sha256",
        "hook_contract_sha256",
        "model_configuration_source_sha256",
        "transformer_block_count",
        "hidden_size",
        "module_path_template",
        "layer_module_inventory",
        "layer_module_inventory_sha256",
    }
    by_family: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(records):
        record = _mapping(raw, context=f"activation_hook_registry.records[{index}]")
        _exact_keys(record, expected_fields, context=f"activation_hook_registry.records[{index}]")
        family = _text(
            record["architecture_family_id"],
            context=f"activation_hook_registry.records[{index}].architecture_family_id",
        )
        observed.append(family)
        _text(
            record["hook_adapter_id"],
            context=f"activation_hook_registry.records[{index}].hook_adapter_id",
        )
        _trusted_sha256(
            record["hook_registry_source_sha256"],
            context=f"activation_hook_registry.records[{index}].hook_registry_source_sha256",
        )
        _trusted_sha256(
            record["hook_contract_sha256"],
            context=f"activation_hook_registry.records[{index}].hook_contract_sha256",
        )
        _trusted_sha256(
            record["model_configuration_source_sha256"],
            context=(
                f"activation_hook_registry.records[{index}].model_configuration_source_sha256"
            ),
        )
        block_count = _positive_int(
            record["transformer_block_count"],
            context=(f"activation_hook_registry.records[{index}].transformer_block_count"),
        )
        _positive_int(
            record["hidden_size"],
            context=f"activation_hook_registry.records[{index}].hidden_size",
        )
        module_path_template = _text(
            record["module_path_template"],
            context=f"activation_hook_registry.records[{index}].module_path_template",
        )
        if module_path_template.count("{layer_index}") != 1:
            raise ExecutionContractError(
                "activation hook module_path_template must contain exactly one "
                "{layer_index} placeholder"
            )
        layer_inventory = _sequence(
            record["layer_module_inventory"],
            context=(f"activation_hook_registry.records[{index}].layer_module_inventory"),
        )
        if len(layer_inventory) != block_count:
            raise ExecutionContractError(
                "activation hook layer inventory must cover every transformer block"
            )
        normalized_layers: list[Mapping[str, Any]] = []
        for layer_index, raw_layer in enumerate(layer_inventory):
            layer = _mapping(
                raw_layer,
                context=(
                    f"activation_hook_registry.records[{index}]"
                    f".layer_module_inventory[{layer_index}]"
                ),
            )
            _exact_keys(
                layer,
                {"zero_based_layer_index", "module_path", "hook_boundary"},
                context=(
                    f"activation_hook_registry.records[{index}]"
                    f".layer_module_inventory[{layer_index}]"
                ),
            )
            if layer["zero_based_layer_index"] != layer_index:
                raise ExecutionContractError(
                    "activation hook layers must be contiguous and ordered from zero"
                )
            expected_module_path = module_path_template.format(layer_index=layer_index)
            if layer["module_path"] != expected_module_path:
                raise ExecutionContractError(
                    "activation hook module path drifted from its frozen template"
                )
            if layer["hook_boundary"] != registry["hook_boundary"]:
                raise ExecutionContractError(
                    "activation hook layer boundary drifted from the registry boundary"
                )
            normalized_layers.append(layer)
        expected_inventory_hash = canonical_artifact_sha256(
            {"layer_module_inventory": normalized_layers}
        )
        if record["layer_module_inventory_sha256"] != expected_inventory_hash:
            raise ExecutionContractError(
                "activation hook layer inventory hash is not content-addressed"
            )
        if family in by_family:
            raise ExecutionContractError(
                "activation hook registry contains a duplicate architecture family"
            )
        by_family[family] = record
    if tuple(observed) != architecture_families:
        raise ExecutionContractError(
            "activation hook registry records must exactly cover sorted architecture families"
        )
    return by_family


def _validate_decoding_config(
    value: Any,
    *,
    model_registry: tuple[Mapping[str, Any], ...],
    tokenizer_compatibility: Mapping[str, Any],
    context: str,
) -> None:
    config = _mapping(value, context=context)
    _exact_keys(config, {"strategy", "records"}, context=context)
    if config["strategy"] != "greedy_exact_v1":
        raise ExecutionContractError(f"{context}.strategy must be greedy_exact_v1")
    records = _sequence(config["records"], context=f"{context}.records")
    if len(records) != len(model_registry):
        raise ExecutionContractError(f"{context} must cover every model unit")
    expected_fields = {
        "model_unit_id",
        "do_sample",
        "temperature",
        "top_p",
        "top_k",
        "max_new_tokens",
        "repetition_penalty",
        "stop_strings",
        "stop_token_ids",
        "pad_token_id",
        "eos_token_ids",
        "deterministic_seed_derivation_id",
        "replicates_per_prompt",
    }
    observed_ids: list[str] = []
    expected_ids = [record["model_unit_id"] for record in model_registry]
    tokenizer_records = {
        record["model_unit_id"]: record
        for record in _mapping(tokenizer_compatibility, context="tokenizer_compatibility")[
            "records"
        ]
    }
    for index, raw in enumerate(records):
        record = _mapping(raw, context=f"{context}.records[{index}]")
        _exact_keys(record, expected_fields, context=f"{context}.records[{index}]")
        unit_id = _text(
            record["model_unit_id"], context=f"{context}.records[{index}].model_unit_id"
        )
        observed_ids.append(unit_id)
        if record["do_sample"] is not False:
            raise ExecutionContractError(f"{context} permits only do_sample=false")
        if any(record[field] is not None for field in ("temperature", "top_p", "top_k")):
            raise ExecutionContractError(
                f"{context} greedy decoding requires temperature/top_p/top_k=null"
            )
        if record["max_new_tokens"] != 16:
            raise ExecutionContractError(
                f"{context} max_new_tokens must equal the frozen terminal-response budget 16"
            )
        if (
            _finite_number(
                record["repetition_penalty"],
                context=f"{context}.records[{index}].repetition_penalty",
            )
            != 1.0
        ):
            raise ExecutionContractError(f"{context} repetition_penalty must equal 1.0")
        stop_strings = _sequence(
            record["stop_strings"], context=f"{context}.records[{index}].stop_strings"
        )
        if stop_strings:
            raise ExecutionContractError(f"{context} stop_strings must be empty")
        stop_ids = _sequence(
            record["stop_token_ids"], context=f"{context}.records[{index}].stop_token_ids"
        )
        eos_ids = _sequence(
            record["eos_token_ids"], context=f"{context}.records[{index}].eos_token_ids"
        )
        for field, ids, minimum in (
            ("stop_token_ids", stop_ids, 0),
            ("eos_token_ids", eos_ids, 1),
        ):
            if len(ids) < minimum or any(type(item) is not int or item < 0 for item in ids):
                raise ExecutionContractError(f"{context}.{field} contains an invalid token id")
            if list(ids) != sorted(set(ids)):
                raise ExecutionContractError(f"{context}.{field} must be sorted and unique")
        if stop_ids:
            raise ExecutionContractError(f"{context} stop_token_ids must be empty")
        tokenizer = tokenizer_records.get(unit_id)
        if tokenizer is None:
            raise ExecutionContractError(
                f"{context} has no tokenizer compatibility record for {unit_id}"
            )
        full_marker_lengths = (
            len(tokenizer["final_a_token_ids"]),
            len(tokenizer["final_b_token_ids"]),
        )
        if max(full_marker_lengths) > record["max_new_tokens"]:
            raise ExecutionContractError(f"{context} terminal marker exceeds max_new_tokens")
        continuation_ids = {
            tokenizer["final_a_continuation_token_id"],
            tokenizer["final_b_continuation_token_id"],
        }
        if continuation_ids & set(eos_ids):
            raise ExecutionContractError(
                f"{context} EOS ids must not alias FINAL marker continuation ids"
            )
        _nonnegative_int(record["pad_token_id"], context=f"{context}.records[{index}].pad_token_id")
        if record["deterministic_seed_derivation_id"] != "not_applicable_greedy_v1":
            raise ExecutionContractError(f"{context} greedy seed derivation id is not frozen")
        if record["replicates_per_prompt"] != 1:
            raise ExecutionContractError(f"{context} greedy decoding requires one replicate")
    if observed_ids != expected_ids:
        raise ExecutionContractError(f"{context} records must exactly cover sorted model ids")


def _validate_model_runtime_configuration(
    value: Any, *, model_registry: tuple[Mapping[str, Any], ...]
) -> None:
    config = _mapping(value, context="model_runtime_configuration")
    _exact_keys(config, {"records"}, context="model_runtime_configuration")
    records = _sequence(config["records"], context="model_runtime_configuration.records")
    if len(records) != len(model_registry):
        raise ExecutionContractError("model runtime configuration must cover every model unit")
    expected_fields = {
        "model_unit_id",
        "dtype",
        "attention_implementation",
        "device_placement_policy",
        "quantization_mode",
        "eval_mode",
        "use_cache",
        "deterministic_algorithms",
        "trust_remote_code",
    }
    expected_ids = [record["model_unit_id"] for record in model_registry]
    observed_ids: list[str] = []
    for index, raw in enumerate(records):
        record = _mapping(raw, context=f"model_runtime_configuration.records[{index}]")
        _exact_keys(
            record, expected_fields, context=f"model_runtime_configuration.records[{index}]"
        )
        observed_ids.append(
            _text(
                record["model_unit_id"],
                context=f"model_runtime_configuration.records[{index}].model_unit_id",
            )
        )
        if record["dtype"] not in {"float32", "float16", "bfloat16"}:
            raise ExecutionContractError("model runtime dtype is unsupported")
        if record["attention_implementation"] not in {
            "eager",
            "sdpa",
            "flash_attention_2",
        }:
            raise ExecutionContractError("model runtime attention_implementation is unsupported")
        if record["device_placement_policy"] not in {
            "single_device_explicit",
            "static_device_map",
        }:
            raise ExecutionContractError("device placement policy is not frozen")
        if record["quantization_mode"] not in {"none", "int8", "int4", "fp8"}:
            raise ExecutionContractError("quantization mode is not frozen")
        for field, required in (
            ("eval_mode", True),
            ("deterministic_algorithms", True),
            ("trust_remote_code", False),
        ):
            if record[field] is not required:
                raise ExecutionContractError(f"model_runtime_configuration.{field} is unsafe")
        if type(record["use_cache"]) is not bool:
            raise ExecutionContractError("model_runtime_configuration.use_cache must be boolean")
    if observed_ids != expected_ids:
        raise ExecutionContractError(
            "model runtime configuration records must exactly cover sorted model ids"
        )


def _validate_cluster_constant_inference_configuration(
    *,
    model_registry: tuple[Mapping[str, Any], ...],
    decoding_config: Mapping[str, Any],
    runtime_config: Mapping[str, Any],
) -> None:
    cluster_by_model = {
        record["model_unit_id"]: record["dependency_cluster_id"] for record in model_registry
    }
    for name, records in (
        ("decoding", decoding_config["records"]),
        ("runtime", runtime_config["records"]),
    ):
        signatures: dict[str, set[str]] = {}
        for record in records:
            cluster_id = cluster_by_model[record["model_unit_id"]]
            signature = canonical_artifact_sha256(
                {key: value for key, value in record.items() if key != "model_unit_id"}
            )
            signatures.setdefault(cluster_id, set()).add(signature)
        if any(len(values) != 1 for values in signatures.values()):
            raise ExecutionContractError(
                f"all anchors in a dependency cluster must share the full {name} configuration"
            )


def _carrier_binding_summary(
    *, case_count: int, model_count: int, record_count: int
) -> dict[str, Any]:
    expected_count = case_count * model_count * len(CAUSAL_VARIABLES)
    return {
        "discovery_case_count": case_count,
        "model_count": model_count,
        "causal_variable_count": len(CAUSAL_VARIABLES),
        "expected_record_count": expected_count,
        "observed_record_count": record_count,
        "compatible_record_count": record_count,
        "missing_count": 0,
        "ambiguous_count": 0,
        "truncated_count": 0,
        "compatible": record_count == expected_count,
    }


def validate_carrier_binding_records(
    value: Any,
    *,
    report_sha256: str,
    summary_value: Any,
    prompt_inventory: Sequence[Mapping[str, Any]],
    model_registry: tuple[Mapping[str, Any], ...],
    context: str,
) -> dict[tuple[str, str, str], Mapping[str, Any]]:
    records = _sequence(value, context=context)
    prompts = {prompt["prompt_id"]: prompt for prompt in prompt_inventory}
    models = {model["model_unit_id"]: model for model in model_registry}
    expected_identities = {
        (model_id, prompt_id, variable)
        for model_id in models
        for prompt_id in prompts
        for variable in CAUSAL_VARIABLES
    }
    if len(records) != len(expected_identities):
        raise ExecutionContractError(f"{context} must cover every model x prompt x causal variable")
    expected_fields = {
        "model_unit_id",
        "tokenizer_artifact_sha256",
        "prompt_id",
        "case_id",
        "prompt_sha256",
        "prompt_record_sha256",
        "causal_variable",
        "factor_carrier_selector",
        "carrier_token_ids",
        "carrier_position_indices",
        "control_site_selector",
        "control_token_ids",
        "control_position_indices",
        "tokenized_input_length",
        "missing",
        "ambiguous",
        "truncated",
        "compatible",
    }
    observed: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    order: list[tuple[str, str, str]] = []
    for index, raw in enumerate(records):
        record = _mapping(raw, context=f"{context}[{index}]")
        _exact_keys(record, expected_fields, context=f"{context}[{index}]")
        identity = (
            _text(record["model_unit_id"], context=f"{context}[{index}].model_unit_id"),
            _text(record["prompt_id"], context=f"{context}[{index}].prompt_id"),
            _text(
                record["causal_variable"],
                context=f"{context}[{index}].causal_variable",
            ),
        )
        if identity not in expected_identities or identity in observed:
            raise ExecutionContractError(
                f"{context} has a duplicate or unauthorized binding identity"
            )
        model_id, prompt_id, variable = identity
        prompt = prompts[prompt_id]
        model = models[model_id]
        exact_bindings = {
            "tokenizer_artifact_sha256": model["tokenizer_artifact_sha256"],
            "case_id": prompt["case_id"],
            "prompt_sha256": prompt["prompt_sha256"],
            "prompt_record_sha256": prompt["prompt_record_sha256"],
            "factor_carrier_selector": CANDIDATE_SITE_ALGORITHM["carrier_token_selectors"][
                variable
            ],
            "control_site_selector": CARRIER_CONTROL_SELECTORS[variable],
        }
        if any(record[field] != expected for field, expected in exact_bindings.items()):
            raise ExecutionContractError(f"{context} drifted from prompt/tokenizer authority")
        tokenized_length = _positive_int(
            record["tokenized_input_length"],
            context=f"{context}[{index}].tokenized_input_length",
        )
        expected_position_count = 2 if variable == "answer_codebook" else 1
        position_groups: list[set[int]] = []
        for token_field, position_field in (
            ("carrier_token_ids", "carrier_position_indices"),
            ("control_token_ids", "control_position_indices"),
        ):
            token_ids = _sequence(record[token_field], context=f"{context}[{index}].{token_field}")
            positions = _sequence(
                record[position_field], context=f"{context}[{index}].{position_field}"
            )
            if (
                len(token_ids) != expected_position_count
                or len(positions) != expected_position_count
                or any(type(token_id) is not int or token_id < 0 for token_id in token_ids)
                or any(
                    type(position) is not int or position < 0 or position >= tokenized_length
                    for position in positions
                )
                or list(positions) != sorted(set(positions))
            ):
                raise ExecutionContractError(
                    f"{context} carrier/control token positions are incomplete or invalid"
                )
            position_groups.append(set(positions))
        if position_groups[0] & position_groups[1]:
            raise ExecutionContractError(
                f"{context} factor carrier and control positions must be disjoint"
            )
        if any(record[field] is not False for field in ("missing", "ambiguous", "truncated")):
            raise ExecutionContractError(
                f"{context} contains a missing, ambiguous, or truncated carrier"
            )
        if record["compatible"] is not True:
            raise ExecutionContractError(f"{context} must be tokenizer-compatible")
        observed[identity] = record
        order.append(identity)
    if set(observed) != expected_identities or order != sorted(order):
        raise ExecutionContractError(f"{context} must be complete and canonically sorted")
    expected_report_hash = canonical_artifact_sha256(
        {"scheme": CARRIER_BINDING_REPORT_SCHEME, "records": list(records)}
    )
    if report_sha256 != expected_report_hash:
        raise ExecutionContractError(f"{context} report hash is not content-addressed")
    summary = _mapping(summary_value, context=f"{context}_summary")
    expected = {
        "discovery_case_count",
        "model_count",
        "causal_variable_count",
        "expected_record_count",
        "observed_record_count",
        "compatible_record_count",
        "missing_count",
        "ambiguous_count",
        "truncated_count",
        "compatible",
    }
    _exact_keys(summary, expected, context=f"{context}_summary")
    exact_values = _carrier_binding_summary(
        case_count=len(prompt_inventory),
        model_count=len(model_registry),
        record_count=len(records),
    )
    if dict(summary) != exact_values:
        raise ExecutionContractError(
            "carrier binding report must be complete, unambiguous, and tokenizer-compatible"
        )
    return observed


def _validate_live_seed_commitment(value: Any) -> None:
    record = _mapping(value, context="live_seed_commitment")
    expected = {
        "authority_secret_commitment_sha256",
        "authority_secret_entropy_bits",
        "secret_generation",
        "derivation_algorithm",
        "derivation_domain",
        "requested_content_seed_count",
        "derived_seed_set_sha256",
    }
    _exact_keys(record, expected, context="live_seed_commitment")
    _trusted_sha256(
        record["authority_secret_commitment_sha256"],
        context="live_seed_commitment.authority_secret_commitment_sha256",
    )
    if (
        _positive_int(
            record["authority_secret_entropy_bits"],
            context="live_seed_commitment.authority_secret_entropy_bits",
        )
        < 256
    ):
        raise ExecutionContractError("authority secret must contain at least 256 bits")
    if record["secret_generation"] != "operating_system_csprng":
        raise ExecutionContractError("live seeds require the operating-system CSPRNG")
    if record["derivation_algorithm"] != "hmac_sha256_first_64bit_domain_separated_v1":
        raise ExecutionContractError("live seed derivation algorithm is not frozen")
    if record["derivation_domain"] != LIVE_CONTENT_SEED_DOMAIN.decode("ascii"):
        raise ExecutionContractError("live seed derivation domain is not frozen")
    if record["requested_content_seed_count"] != 64:
        raise ExecutionContractError("live execution requires exactly 64 content seeds")
    _trusted_sha256(
        record["derived_seed_set_sha256"],
        context="live_seed_commitment.derived_seed_set_sha256",
    )


def _partition_split_manifest_sha256(
    partition_records: Sequence[Mapping[str, Any]],
) -> str:
    return canonical_artifact_sha256(
        {
            "split_rule_id": SPLIT_RULE_ID,
            "partition_seed_sets": [
                {
                    "partition_id": record["partition_id"],
                    "content_seed_count": record["content_seed_count"],
                    "content_seed_set_sha256": record["content_seed_set_sha256"],
                }
                for record in partition_records
            ],
        }
    )


def _phase_prompt_inventory_sha256(
    *,
    phase_id: str,
    model_unit_ids: Sequence[str],
    source_material: Mapping[str, Any],
    role_ids: Sequence[str],
    prompt_count: int,
) -> str:
    return canonical_artifact_sha256(
        {
            "scheme": "model_cross_material_prompt_inventory_v1",
            "phase_id": phase_id,
            "model_unit_ids": list(model_unit_ids),
            "source_material": dict(source_material),
            "role_ids": list(role_ids),
            "prompt_count": prompt_count,
            "replicates_per_prompt": 1,
        }
    )


def _validate_live_material_manifest(
    value: Any,
    *,
    manifest_sha256: Any,
    record: Mapping[str, Any],
    model_registry: tuple[Mapping[str, Any], ...],
) -> dict[str, Mapping[str, Any]]:
    manifest = _mapping(value, context="live_material_manifest")
    expected_manifest_fields = {
        "scheme",
        "seed_set_hash_scheme",
        "task_id",
        "task_generator_version",
        "split_rule_id",
        "derived_seed_set_sha256",
        "partition_records",
        "discovery_primary_pair_inventory_scheme",
        "discovery_primary_pair_inventory",
        "discovery_primary_pair_inventory_sha256",
        "discovery_intervention_prompt_inventory",
        "discovery_intervention_prompt_inventory_sha256",
    }
    _exact_keys(manifest, expected_manifest_fields, context="live_material_manifest")
    exact_constants = {
        "scheme": LIVE_MATERIAL_MANIFEST_SCHEME,
        "seed_set_hash_scheme": LIVE_SEED_SET_HASH_SCHEME,
        "task_id": TASK_ID,
        "task_generator_version": TASK_GENERATOR_VERSION,
        "split_rule_id": SPLIT_RULE_ID,
        "discovery_primary_pair_inventory_scheme": (DISCOVERY_PRIMARY_PAIR_INVENTORY_SCHEME),
    }
    for field, expected_value in exact_constants.items():
        if manifest[field] != expected_value:
            raise ExecutionContractError(f"live_material_manifest.{field} is not frozen")
    if (
        manifest["derived_seed_set_sha256"]
        != record["live_seed_commitment"]["derived_seed_set_sha256"]
    ):
        raise ExecutionContractError("derived seed-set hash drifted from live commitment")
    _trusted_sha256(
        manifest["derived_seed_set_sha256"],
        context="live_material_manifest.derived_seed_set_sha256",
    )
    trusted_manifest_hash = _trusted_sha256(
        manifest_sha256, context="live_material_manifest_sha256"
    )
    if trusted_manifest_hash != canonical_artifact_sha256(manifest):
        raise ExecutionContractError("live material manifest hash is not content-addressed")

    partition_values = _sequence(
        manifest["partition_records"], context="live_material_manifest.partition_records"
    )
    expected_partition_ids = [partition_id for partition_id, _ in CONTENT_PARTITION_COUNTS]
    if len(partition_values) != len(expected_partition_ids):
        raise ExecutionContractError("live material manifest must contain four partitions")
    partition_fields = {
        "partition_id",
        "content_seed_count",
        "content_seed_set_sha256",
        "case_count",
        "case_set_sha256",
        "projection_count",
        "projection_set_sha256",
        "weak_observations",
        "diagnostic_cue_masks",
        "heldout_challenges",
        "intervention_prompt_count",
        "intervention_prompt_set_sha256",
        "intervention_prompt_inventory",
        "intervention_prompt_inventory_sha256",
        "intervention_pair_count",
        "intervention_pair_set_sha256",
        "primary_intervention_pair_count",
        "primary_intervention_pair_set_sha256",
        "primary_pair_inventory",
        "primary_pair_inventory_sha256",
        "primary_pair_count_by_causal_variable",
        "design_manifest_sha256",
    }
    partitions: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(partition_values):
        item = _mapping(raw, context=f"live_material_manifest.partition_records[{index}]")
        _exact_keys(
            item,
            partition_fields,
            context=f"live_material_manifest.partition_records[{index}]",
        )
        partition_id = item["partition_id"]
        if partition_id != expected_partition_ids[index]:
            raise ExecutionContractError("live material partitions must use frozen order")
        expected_counts = PARTITION_EXPECTATIONS[partition_id]
        count_mapping = {
            "content_seed_count": "content_seeds",
            "case_count": "cases",
            "projection_count": "projections",
            "weak_observations": "weak_observations",
            "diagnostic_cue_masks": "diagnostic_cue_masks",
            "heldout_challenges": "heldout_challenges",
            "intervention_prompt_count": "intervention_prompts",
            "intervention_pair_count": "intervention_pairs",
            "primary_intervention_pair_count": "primary_intervention_pairs",
        }
        for field, expectation_key in count_mapping.items():
            if item[field] != expected_counts[expectation_key]:
                raise ExecutionContractError(
                    f"{partition_id}.{field} does not equal the generator-derived count"
                )
        expected_by_variable = {
            variable: expected_counts["primary_pairs_per_factor"] for variable in CAUSAL_VARIABLES
        }
        if item["primary_pair_count_by_causal_variable"] != expected_by_variable:
            raise ExecutionContractError(
                f"{partition_id} primary pair counts are incomplete or imbalanced"
            )
        for field in partition_fields:
            if field.endswith("_sha256"):
                _trusted_sha256(item[field], context=f"{partition_id}.{field}")
        prompt_inventory = _sequence(
            item["intervention_prompt_inventory"],
            context=f"{partition_id}.intervention_prompt_inventory",
        )
        if len(prompt_inventory) != item["intervention_prompt_count"]:
            raise ExecutionContractError(
                f"{partition_id} intervention prompt inventory count is incomplete"
            )
        if item["intervention_prompt_inventory_sha256"] != canonical_artifact_sha256(
            {"intervention_prompt_inventory": list(prompt_inventory)}
        ):
            raise ExecutionContractError(
                f"{partition_id} intervention prompt inventory hash mismatch"
            )
        primary_inventory = _sequence(
            item["primary_pair_inventory"],
            context=f"{partition_id}.primary_pair_inventory",
        )
        if len(primary_inventory) != item["primary_intervention_pair_count"]:
            raise ExecutionContractError(
                f"{partition_id} primary pair inventory count is incomplete"
            )
        if item["primary_pair_inventory_sha256"] != canonical_artifact_sha256(
            {"primary_pair_inventory": list(primary_inventory)}
        ):
            raise ExecutionContractError(f"{partition_id} primary pair inventory hash mismatch")
        partitions[partition_id] = item

    pair_values = _sequence(
        manifest["discovery_primary_pair_inventory"],
        context="live_material_manifest.discovery_primary_pair_inventory",
    )
    pair_fields = {
        "causal_variable",
        "pair_id",
        "opaque_content_seed_id",
        "pair_record_sha256",
        "base_prompt_id",
        "base_prompt_sha256",
        "source_prompt_id",
        "source_prompt_sha256",
        "expected_patched_final",
        "base_oracle_final",
    }
    expected_pair_count = PARTITION_EXPECTATIONS["D_site_discovery"]["primary_intervention_pairs"]
    if len(pair_values) != expected_pair_count:
        raise ExecutionContractError("discovery primary pair inventory must contain 96 pairs")
    pair_order: list[tuple[str, str]] = []
    seen_pair_ids: set[str] = set()
    seed_counts_by_variable: dict[str, Counter[str]] = {
        variable: Counter() for variable in CAUSAL_VARIABLES
    }
    for index, raw in enumerate(pair_values):
        pair = _mapping(raw, context=f"discovery_primary_pair_inventory[{index}]")
        _exact_keys(pair, pair_fields, context=f"discovery_primary_pair_inventory[{index}]")
        variable = _text(
            pair["causal_variable"],
            context=f"discovery_primary_pair_inventory[{index}].causal_variable",
        )
        if variable not in CAUSAL_VARIABLES:
            raise ExecutionContractError("primary pair has unknown causal variable")
        pair_id = _text(
            pair["pair_id"], context=f"discovery_primary_pair_inventory[{index}].pair_id"
        )
        if pair_id in seen_pair_ids:
            raise ExecutionContractError("discovery primary pair ids must be unique")
        seen_pair_ids.add(pair_id)
        pair_order.append((variable, pair_id))
        seed_id = _trusted_sha256(
            pair["opaque_content_seed_id"],
            context=f"discovery_primary_pair_inventory[{index}].opaque_content_seed_id",
        )
        seed_counts_by_variable[variable][seed_id] += 1
        for field in ("pair_record_sha256", "base_prompt_sha256", "source_prompt_sha256"):
            _trusted_sha256(
                pair[field], context=f"discovery_primary_pair_inventory[{index}].{field}"
            )
        for field in ("base_prompt_id", "source_prompt_id"):
            prompt_id = _text(
                pair[field], context=f"discovery_primary_pair_inventory[{index}].{field}"
            )
            if not prompt_id.endswith(f":{INTERVENTION_PROMPT_TEMPLATE_ID}"):
                raise ExecutionContractError(
                    "intervention pair prompt id does not use the canonical template"
                )
    if pair_order != sorted(pair_order):
        raise ExecutionContractError("discovery primary pair inventory must be sorted")
    seed_sets = []
    for variable, seed_counts in seed_counts_by_variable.items():
        if len(seed_counts) != 8 or set(seed_counts.values()) != {4}:
            raise ExecutionContractError(
                f"{variable} must contain four primary pairs for each of eight seeds"
            )
        seed_sets.append(set(seed_counts))
    if any(seed_set != seed_sets[0] for seed_set in seed_sets[1:]):
        raise ExecutionContractError("all causal variables must use the same eight discovery seeds")
    expected_inventory_hash = canonical_artifact_sha256(
        {"discovery_primary_pair_inventory": list(pair_values)}
    )
    if manifest["discovery_primary_pair_inventory_sha256"] != expected_inventory_hash:
        raise ExecutionContractError("discovery primary pair inventory hash mismatch")
    if record["discovery_primary_pair_inventory_sha256"] != expected_inventory_hash:
        raise ExecutionContractError("authorization primary pair inventory hash mismatch")
    prompt_values = _sequence(
        manifest["discovery_intervention_prompt_inventory"],
        context="live_material_manifest.discovery_intervention_prompt_inventory",
    )
    if prompt_values != partitions["D_site_discovery"]["intervention_prompt_inventory"]:
        raise ExecutionContractError(
            "top-level discovery prompt inventory drifted from D_site_discovery"
        )
    expected_prompt_inventory_hash = canonical_artifact_sha256(
        {"discovery_intervention_prompt_inventory": list(prompt_values)}
    )
    if manifest["discovery_intervention_prompt_inventory_sha256"] != expected_prompt_inventory_hash:
        raise ExecutionContractError("discovery intervention prompt inventory hash mismatch")

    discovery = partitions["D_site_discovery"]
    exact_discovery_bindings = {
        "discovery_content_seed_set_sha256": discovery["content_seed_set_sha256"],
        "discovery_case_set_sha256": discovery["case_set_sha256"],
        "discovery_case_count": discovery["case_count"],
        "discovery_projection_set_sha256": discovery["projection_set_sha256"],
        "discovery_intervention_pair_set_sha256": discovery["intervention_pair_set_sha256"],
        "discovery_primary_intervention_pair_set_sha256": discovery[
            "primary_intervention_pair_set_sha256"
        ],
    }
    for field, expected_value in exact_discovery_bindings.items():
        if record[field] != expected_value:
            raise ExecutionContractError(f"{field} does not bind D_site_discovery material")
    if record["split_manifest_sha256"] != _partition_split_manifest_sha256(
        tuple(partitions.values())
    ):
        raise ExecutionContractError("split_manifest_sha256 is not derived from partition roots")
    model_ids = [model["model_unit_id"] for model in model_registry]
    expected_discovery_prompt_count = discovery["intervention_prompt_count"] * len(model_ids)
    expected_discovery_prompt_hash = _phase_prompt_inventory_sha256(
        phase_id="D_site_discovery_unpatched_activation_capture",
        model_unit_ids=model_ids,
        source_material={
            "partition_id": "D_site_discovery",
            "intervention_prompt_set_sha256": discovery["intervention_prompt_set_sha256"],
        },
        role_ids=["canonical_intervention_prompt_v1"],
        prompt_count=expected_discovery_prompt_count,
    )
    if record["discovery_prompt_inventory_sha256"] != expected_discovery_prompt_hash:
        raise ExecutionContractError("discovery prompt inventory hash is not generator-derived")
    return partitions


def _validate_candidate_site_inventory(
    value: Any,
    *,
    model_registry: tuple[Mapping[str, Any], ...],
    activation_hook_registry: Mapping[str, Any],
) -> dict[tuple[str, str], tuple[Mapping[str, Any], ...]]:
    inventory = _sequence(value, context="candidate_site_inventory")
    architecture_families = tuple(
        sorted({model["architecture_family_id"] for model in model_registry})
    )
    hook_specs = _validate_activation_hook_registry(
        activation_hook_registry,
        architecture_families=architecture_families,
    )
    models_by_id = {model["model_unit_id"]: model for model in model_registry}
    expected_pairs = {
        (model["model_unit_id"], variable)
        for model in model_registry
        for variable in CAUSAL_VARIABLES
    }
    if len(inventory) != len(expected_pairs):
        raise ExecutionContractError(
            "candidate_site_inventory must contain every model x causal-variable panel"
        )
    panels: dict[tuple[str, str], tuple[Mapping[str, Any], ...]] = {}
    panel_order: list[tuple[str, str]] = []
    for index, raw in enumerate(inventory):
        panel = _mapping(raw, context=f"candidate_site_inventory[{index}]")
        _exact_keys(
            panel,
            {"model_unit_id", "causal_variable", "candidates"},
            context=f"candidate_site_inventory[{index}]",
        )
        model_id = _text(
            panel["model_unit_id"],
            context=f"candidate_site_inventory[{index}].model_unit_id",
        )
        variable = _text(
            panel["causal_variable"],
            context=f"candidate_site_inventory[{index}].causal_variable",
        )
        pair = (model_id, variable)
        if pair not in expected_pairs or pair in panels:
            raise ExecutionContractError(
                "candidate_site_inventory has a missing, duplicate, or unknown panel"
            )
        candidates = _sequence(
            panel["candidates"], context=f"candidate_site_inventory[{index}].candidates"
        )
        model_family = models_by_id[model_id]["architecture_family_id"]
        hook_spec = hook_specs[model_family]
        layer_inventory = hook_spec["layer_module_inventory"]
        if len(candidates) != hook_spec["transformer_block_count"]:
            raise ExecutionContractError(
                "every candidate panel must cover every transformer block exactly once"
            )
        normalized: list[Mapping[str, Any]] = []
        identities: set[str] = set()
        order: list[tuple[int, str]] = []
        for candidate_index, raw_candidate in enumerate(candidates):
            candidate = _mapping(
                raw_candidate,
                context=f"candidate_site_inventory[{index}].candidates[{candidate_index}]",
            )
            _exact_keys(
                candidate,
                {
                    "canonical_site_id",
                    "architecture_family_id",
                    "module_path",
                    "zero_based_layer_index",
                    "hook_boundary",
                    "hidden_size",
                    "factor_carrier_selector",
                },
                context=f"candidate_site_inventory[{index}].candidates[{candidate_index}]",
            )
            site_id = _text(
                candidate["canonical_site_id"],
                context=(
                    f"candidate_site_inventory[{index}].candidates[{candidate_index}]"
                    ".canonical_site_id"
                ),
            )
            layer = _nonnegative_int(
                candidate["zero_based_layer_index"],
                context=(
                    f"candidate_site_inventory[{index}].candidates[{candidate_index}]"
                    ".zero_based_layer_index"
                ),
            )
            if candidate["architecture_family_id"] != model_family:
                raise ExecutionContractError(
                    "candidate architecture_family_id drifted from model_registry"
                )
            module_path = _text(
                candidate["module_path"],
                context=(
                    f"candidate_site_inventory[{index}].candidates[{candidate_index}].module_path"
                ),
            )
            hidden_size = _positive_int(
                candidate["hidden_size"],
                context=(
                    f"candidate_site_inventory[{index}].candidates[{candidate_index}].hidden_size"
                ),
            )
            expected_layer = layer_inventory[candidate_index]
            if layer != candidate_index or layer != expected_layer["zero_based_layer_index"]:
                raise ExecutionContractError(
                    "candidate layers must be contiguous and ordered from zero"
                )
            if module_path != expected_layer["module_path"]:
                raise ExecutionContractError(
                    "candidate module path drifted from the complete hook inventory"
                )
            if candidate["hook_boundary"] != expected_layer["hook_boundary"]:
                raise ExecutionContractError(
                    "candidate hook boundary drifted from the complete hook inventory"
                )
            if hidden_size != hook_spec["hidden_size"]:
                raise ExecutionContractError(
                    "candidate hidden_size drifted from the architecture hook registry"
                )
            expected_selector = CANDIDATE_SITE_ALGORITHM["carrier_token_selectors"][variable]
            if candidate["factor_carrier_selector"] != expected_selector:
                raise ExecutionContractError(
                    "candidate factor carrier selector drifted from the frozen variable binding"
                )
            if site_id in identities:
                raise ExecutionContractError("candidate canonical_site_id values must be unique")
            identities.add(site_id)
            order.append((layer, site_id))
            normalized.append(candidate)
        if order != sorted(order):
            raise ExecutionContractError(
                "candidate sites must be sorted by layer then canonical_site_id"
            )
        panels[pair] = tuple(normalized)
        panel_order.append(pair)
    if set(panels) != expected_pairs or panel_order != sorted(panel_order):
        raise ExecutionContractError(
            "candidate_site_inventory panels must be complete and canonically sorted"
        )
    return panels


def _discovery_panel_sha256(record: Mapping[str, Any]) -> str:
    return canonical_artifact_sha256(
        {
            "discovery_content_seed_set_sha256": record["discovery_content_seed_set_sha256"],
            "discovery_case_set_sha256": record["discovery_case_set_sha256"],
            "discovery_projection_set_sha256": record["discovery_projection_set_sha256"],
            "discovery_intervention_pair_set_sha256": record[
                "discovery_intervention_pair_set_sha256"
            ],
            "discovery_prompt_inventory_sha256": record["discovery_prompt_inventory_sha256"],
            "split_manifest_sha256": record["split_manifest_sha256"],
        }
    )


def _validate_discovery_query_plan(
    value: Any, *, authorization: Mapping[str, Any]
) -> Mapping[str, Any]:
    plan = _mapping(value, context="discovery_query_plan")
    expected = {f"planned_{field}" for field in DISCOVERY_QUERY_COMPONENTS} | {
        "planned_total_forward_passes",
        "max_wall_clock_seconds",
        "discovery_panel_sha256",
        "discovery_intervention_pair_set_sha256",
        "discovery_primary_intervention_pair_set_sha256",
        "discovery_primary_pair_inventory_sha256",
        "candidate_site_set_sha256",
        "discovery_prompt_inventory_sha256",
        "discovery_prompt_count",
        "authorized_candidate_site_count",
        "discovery_primary_pair_count_per_causal_variable",
    }
    _exact_keys(plan, expected, context="discovery_query_plan")
    component_total = 0
    for field in DISCOVERY_QUERY_COMPONENTS:
        component_total += _positive_int(
            plan[f"planned_{field}"], context=f"discovery_query_plan.planned_{field}"
        )
    total = _positive_int(
        plan["planned_total_forward_passes"],
        context="discovery_query_plan.planned_total_forward_passes",
    )
    if total != component_total:
        raise ExecutionContractError(
            "discovery planned_total_forward_passes must equal the component sum"
        )
    _positive_int(
        plan["max_wall_clock_seconds"],
        context="discovery_query_plan.max_wall_clock_seconds",
    )
    for field in (
        "discovery_panel_sha256",
        "discovery_intervention_pair_set_sha256",
        "discovery_primary_intervention_pair_set_sha256",
        "discovery_primary_pair_inventory_sha256",
        "candidate_site_set_sha256",
        "discovery_prompt_inventory_sha256",
    ):
        _trusted_sha256(plan[field], context=f"discovery_query_plan.{field}")
        if plan[field] != authorization[field]:
            raise ExecutionContractError(
                f"discovery_query_plan.{field} must equal the authorized hash"
            )
    prompt_count = _positive_int(
        plan["discovery_prompt_count"],
        context="discovery_query_plan.discovery_prompt_count",
    )
    expected_prompt_count = PARTITION_EXPECTATIONS["D_site_discovery"][
        "intervention_prompts"
    ] * len(authorization["model_registry"])
    if prompt_count != expected_prompt_count:
        raise ExecutionContractError(
            "discovery prompt count must cover all model x canonical intervention prompts"
        )
    if plan["planned_unpatched_forward_passes"] != prompt_count:
        raise ExecutionContractError(
            "greedy discovery unpatched count must equal prompt inventory count"
        )
    candidate_count = sum(
        len(panel["candidates"]) for panel in authorization["candidate_site_inventory"]
    )
    if plan["authorized_candidate_site_count"] != candidate_count:
        raise ExecutionContractError("query plan candidate count does not close the inventory")
    primary_pair_count = PARTITION_EXPECTATIONS["D_site_discovery"]["primary_pairs_per_factor"]
    if plan["discovery_primary_pair_count_per_causal_variable"] != primary_pair_count:
        raise ExecutionContractError("discovery primary pair denominator must equal 32")
    expected_condition_count = candidate_count * primary_pair_count
    for field in (
        "targeted_intervention_forward_passes",
        "matched_null_forward_passes",
        "self_sham_forward_passes",
        "control_site_forward_passes",
    ):
        if plan[f"planned_{field}"] != expected_condition_count:
            raise ExecutionContractError(
                f"planned_{field} must equal candidate_count x 32 primary pairs"
            )
    return plan


def _validate_environment_lock(value: Any) -> None:
    record = _mapping(value, context="environment_lock")
    expected = {
        "python_version",
        "framework_name",
        "framework_version",
        "model_runtime_name",
        "model_runtime_version",
        "device_type",
        "deterministic_algorithms",
        "source_tree_sha256",
        "dependency_lock_sha256",
        "hardware_fingerprint_sha256",
    }
    _exact_keys(record, expected, context="environment_lock")
    for field in expected - {
        "deterministic_algorithms",
        "source_tree_sha256",
        "dependency_lock_sha256",
        "hardware_fingerprint_sha256",
    }:
        _text(record[field], context=f"environment_lock.{field}")
    if type(record["deterministic_algorithms"]) is not bool:
        raise ExecutionContractError("environment_lock.deterministic_algorithms must be boolean")
    for field in (
        "source_tree_sha256",
        "dependency_lock_sha256",
        "hardware_fingerprint_sha256",
    ):
        _trusted_sha256(record[field], context=f"environment_lock.{field}")


def _validate_common_authorized_surface(record: Mapping[str, Any]) -> None:
    families = _sorted_unique_texts(
        record["architecture_families"], context="architecture_families"
    )
    models = _validate_model_registry(record["model_registry"])
    model_families = tuple(sorted({model["architecture_family_id"] for model in models}))
    if families != model_families:
        raise ExecutionContractError(
            "architecture_families must exactly equal the model_registry family set"
        )
    ancestry_edges = _validate_learned_state_ancestry(
        record["learned_state_ancestry"], model_registry=models
    )
    _validate_dependency_surface(
        model_registry=models,
        expected_ancestry_edges=ancestry_edges,
        dependency_graph_value=record["dependency_graph"],
        dependency_clusters_value=record["dependency_clusters"],
    )
    if record["nuisance_balance_contract"] != NUISANCE_BALANCE_CONTRACT:
        raise ExecutionContractError(
            "nuisance_balance_contract must reproduce the frozen confound controls"
        )
    _validate_activation_hook_registry(
        record["activation_hook_registry"], architecture_families=families
    )
    _validate_tokenizer_compatibility(record["tokenizer_compatibility"], model_registry=models)
    _validate_live_seed_commitment(record["live_seed_commitment"])
    partitions = _validate_live_material_manifest(
        record["live_material_manifest"],
        manifest_sha256=record["live_material_manifest_sha256"],
        record=record,
        model_registry=models,
    )
    for field in (
        "live_material_manifest_sha256",
        "discovery_content_seed_set_sha256",
        "discovery_case_set_sha256",
        "discovery_projection_set_sha256",
        "discovery_intervention_pair_set_sha256",
        "discovery_primary_intervention_pair_set_sha256",
        "discovery_primary_pair_inventory_sha256",
        "discovery_prompt_inventory_sha256",
        "split_manifest_sha256",
        "candidate_site_set_sha256",
        "discovery_panel_sha256",
        "carrier_binding_report_sha256",
    ):
        _trusted_sha256(record[field], context=field)
    _positive_int(record["discovery_case_count"], context="discovery_case_count")
    candidate_panels = _validate_candidate_site_inventory(
        record["candidate_site_inventory"],
        model_registry=models,
        activation_hook_registry=record["activation_hook_registry"],
    )
    if not candidate_panels:
        raise ExecutionContractError("candidate_site_inventory must not be empty")
    expected_candidate_hash = canonical_artifact_sha256(
        {"candidate_site_inventory": record["candidate_site_inventory"]}
    )
    if record["candidate_site_set_sha256"] != expected_candidate_hash:
        raise ExecutionContractError(
            "candidate_site_set_sha256 must content-address the complete inventory"
        )
    if record["discovery_panel_sha256"] != _discovery_panel_sha256(record):
        raise ExecutionContractError(
            "discovery_panel_sha256 must content-address the frozen discovery panel"
        )
    if record["candidate_site_algorithm"] != CANDIDATE_SITE_ALGORITHM:
        raise ExecutionContractError("candidate_site_algorithm must reproduce the frozen algorithm")
    _validate_discovery_query_plan(record["discovery_query_plan"], authorization=record)
    _validate_decoding_config(
        record["discovery_decoding_config"],
        model_registry=models,
        tokenizer_compatibility=record["tokenizer_compatibility"],
        context="discovery_decoding_config",
    )
    _validate_model_runtime_configuration(
        record["model_runtime_configuration"], model_registry=models
    )
    _validate_cluster_constant_inference_configuration(
        model_registry=models,
        decoding_config=record["discovery_decoding_config"],
        runtime_config=record["model_runtime_configuration"],
    )
    validate_carrier_binding_records(
        record["carrier_binding_records"],
        report_sha256=record["carrier_binding_report_sha256"],
        summary_value=record["carrier_binding_summary"],
        prompt_inventory=partitions["D_site_discovery"]["intervention_prompt_inventory"],
        model_registry=models,
        context="carrier_binding_records",
    )
    _validate_environment_lock(record["environment_lock"])


def validate_discovery_authorization_template(
    value: Mapping[str, Any], *, expected_parent_design_manifest_sha256: str
) -> None:
    """Validate the checked-in call-free discovery-authorization template."""

    record = _mapping(value, context="discovery authorization template")
    _exact_keys(record, DISCOVERY_AUTHORIZATION_FIELDS, context="discovery authorization template")
    if record["schema_version"] != SCHEMA_VERSION or record["status"] != "unassigned":
        raise ExecutionContractError("discovery authorization template must be unassigned v0.1.0")
    _text(record["design_freeze_id"], context="design_freeze_id")
    trusted_parent_design = _trusted_sha256(
        expected_parent_design_manifest_sha256,
        context="expected_parent_design_manifest_sha256",
    )
    parent_design = _trusted_sha256(
        record["parent_design_manifest_sha256"], context="parent_design_manifest_sha256"
    )
    if parent_design != trusted_parent_design:
        raise ExecutionContractError("discovery template parent design hash mismatch")
    empty_arrays = (
        "architecture_families",
        "model_registry",
        "dependency_clusters",
        "candidate_site_inventory",
    )
    if any(record[field] != [] for field in empty_arrays):
        raise ExecutionContractError("unassigned discovery template contains assigned arrays")
    nullable = DISCOVERY_AUTHORIZATION_FIELDS - {
        "schema_version",
        "design_freeze_id",
        "parent_design_manifest_sha256",
        "status",
        *empty_arrays,
    }
    if any(record[field] is not None for field in nullable):
        raise ExecutionContractError("unassigned discovery template contains assigned fields")


def validate_discovery_authorization(
    value: Mapping[str, Any],
    *,
    expected_parent_design_manifest_sha256: str,
    expected_parent_discovery_template_sha256: str,
    expected_parent_execution_template_sha256: str,
) -> None:
    """Validate a concrete, immutable authorization for bounded site discovery."""

    record = _mapping(value, context="discovery authorization")
    _exact_keys(record, DISCOVERY_AUTHORIZATION_FIELDS, context="discovery authorization")
    if record["schema_version"] != SCHEMA_VERSION:
        raise ExecutionContractError("unsupported discovery authorization schema_version")
    if record["status"] != DISCOVERY_AUTHORIZATION_STATUS:
        raise ExecutionContractError("discovery authorization status must be authorized")
    _text(record["design_freeze_id"], context="design_freeze_id")
    _text(record["discovery_authorization_id"], context="discovery_authorization_id")
    _timestamp(record["authorized_at"], context="authorized_at")
    trusted_hashes = {
        "parent_design_manifest_sha256": expected_parent_design_manifest_sha256,
        "parent_discovery_template_sha256": expected_parent_discovery_template_sha256,
        "parent_execution_template_sha256": expected_parent_execution_template_sha256,
    }
    for field, expected in trusted_hashes.items():
        trusted = _trusted_sha256(expected, context=f"expected_{field}")
        observed = _trusted_sha256(record[field], context=field)
        if observed != trusted:
            raise ExecutionContractError(f"{field} mismatch")
    _validate_common_authorized_surface(record)


def _validate_discovery_usage(value: Any, *, plan: Mapping[str, Any]) -> Mapping[str, Any]:
    usage = _mapping(value, context="query_usage")
    expected = set(DISCOVERY_QUERY_COMPONENTS) | {
        "total_forward_passes",
        "wall_clock_seconds",
    }
    _exact_keys(usage, expected, context="query_usage")
    component_total = 0
    for field in DISCOVERY_QUERY_COMPONENTS:
        observed = _nonnegative_int(usage[field], context=f"query_usage.{field}")
        planned = plan[f"planned_{field}"]
        if observed != planned:
            raise ExecutionContractError(
                f"discovery usage must exactly equal the precommitted plan for {field}"
            )
        component_total += observed
    total = _nonnegative_int(
        usage["total_forward_passes"], context="query_usage.total_forward_passes"
    )
    if total != component_total:
        raise ExecutionContractError("query_usage.total_forward_passes must equal component sum")
    if total != plan["planned_total_forward_passes"]:
        raise ExecutionContractError("discovery total usage must exactly equal the plan")
    wall = _finite_number(usage["wall_clock_seconds"], context="query_usage.wall_clock_seconds")
    if wall < 0 or wall > plan["max_wall_clock_seconds"]:
        raise ExecutionContractError("discovery wall-clock budget exceeded")
    return usage


def derive_intervention_trial_condition_order(
    *,
    partition_id: str,
    split_manifest_sha256: str,
    model_unit_id: str,
    causal_variable: str,
    canonical_site_id: str,
    pair_id: str,
) -> tuple[str, ...]:
    """Derive the frozen four-condition order for any intervention partition."""

    if partition_id not in PARTITION_EXPECTATIONS:
        raise ExecutionContractError("unknown intervention partition_id")
    _trusted_sha256(split_manifest_sha256, context="split_manifest_sha256")
    _text(model_unit_id, context="model_unit_id")
    if causal_variable not in CAUSAL_VARIABLES:
        raise ExecutionContractError("unknown causal_variable")
    _text(canonical_site_id, context="canonical_site_id")
    _text(pair_id, context="pair_id")
    prefix = (
        "ltt:intervention-trial-order:v1\x00"
        f"{partition_id}\x00{split_manifest_sha256}\x00{model_unit_id}\x00"
        f"{causal_variable}\x00"
        f"{canonical_site_id}\x00{pair_id}\x00"
    )
    return tuple(
        sorted(
            TRIAL_CONDITION_IDS,
            key=lambda condition_id: (
                hashlib.sha256(f"{prefix}{condition_id}".encode("utf-8")).digest(),
                condition_id,
            ),
        )
    )


def _validate_unpatched_prompt_evidence(
    value: Any, *, authorization: Mapping[str, Any]
) -> dict[tuple[str, str], Mapping[str, Any]]:
    model_ids = [model["model_unit_id"] for model in authorization["model_registry"]]
    prompts = authorization["live_material_manifest"]["discovery_intervention_prompt_inventory"]
    expected = {
        (model_id, prompt["prompt_id"]): prompt for model_id in model_ids for prompt in prompts
    }
    records = _sequence(value, context="unpatched_prompt_evidence")
    if len(records) != len(expected):
        raise ExecutionContractError(
            "unpatched prompt evidence must cover every model x canonical prompt"
        )
    fields = {
        "model_unit_id",
        "prompt_id",
        "case_id",
        "prompt_sha256",
        "prompt_record_sha256",
        "oracle_final",
        "output_text",
        "output_text_sha256",
        "parsed_final",
        "oracle_correct",
        "activation_capture_record_sha256",
    }
    observed: dict[tuple[str, str], Mapping[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for index, raw in enumerate(records):
        item = _mapping(raw, context=f"unpatched_prompt_evidence[{index}]")
        _exact_keys(item, fields, context=f"unpatched_prompt_evidence[{index}]")
        identity = (
            _text(
                item["model_unit_id"],
                context=f"unpatched_prompt_evidence[{index}].model_unit_id",
            ),
            _text(
                item["prompt_id"],
                context=f"unpatched_prompt_evidence[{index}].prompt_id",
            ),
        )
        if identity not in expected or identity in observed:
            raise ExecutionContractError(
                "unpatched prompt evidence has a duplicate or unauthorized identity"
            )
        prompt = expected[identity]
        for field in (
            "case_id",
            "prompt_sha256",
            "prompt_record_sha256",
            "oracle_final",
        ):
            if item[field] != prompt[field]:
                raise ExecutionContractError(
                    f"unpatched prompt {field} drifted from the authority inventory"
                )
        output_text = item["output_text"]
        if not isinstance(output_text, str):
            raise ExecutionContractError("unpatched output_text must be text")
        if item["output_text_sha256"] != hashlib.sha256(output_text.encode("utf-8")).hexdigest():
            raise ExecutionContractError("unpatched output hash does not bind raw bytes")
        parsed = parse_final(output_text)
        parsed_value = None if parsed is None else parsed.value
        if item["parsed_final"] != parsed_value:
            raise ExecutionContractError("unpatched parsed_final was not derived from output_text")
        oracle_correct = parsed is not None and f"FINAL: {parsed.value}" == prompt["oracle_final"]
        if item["oracle_correct"] is not oracle_correct:
            raise ExecutionContractError("unpatched oracle_correct was not derived")
        _trusted_sha256(
            item["activation_capture_record_sha256"],
            context=f"unpatched_prompt_evidence[{index}].activation_capture_record_sha256",
        )
        observed[identity] = item
        order.append(identity)
    if set(observed) != set(expected) or order != sorted(order):
        raise ExecutionContractError(
            "unpatched prompt evidence must be complete and canonically sorted"
        )
    return observed


def validate_intervention_execution_record(
    value: Any,
    *,
    record_sha256: Any,
    authorization: Mapping[str, Any],
    partition_id: str,
    condition_id: str,
    order_index: int,
    model_unit_id: str,
    causal_variable: str,
    candidate: Mapping[str, Any],
    pair: Mapping[str, Any],
    base_capture_sha256: str,
    source_capture_sha256: str,
    base_binding: Mapping[str, Any],
    source_binding: Mapping[str, Any],
    output_text_sha256: str,
    context: str,
) -> None:
    if partition_id not in {"D_site_discovery", "D_causal_label"}:
        raise ExecutionContractError(
            "execution provenance is only authorized for discovery or causal-label partitions"
        )
    execution = _mapping(value, context=context)
    expected_fields = {
        "record_version",
        "partition_id",
        "operation_id",
        "order_index",
        "model_unit_id",
        "causal_variable",
        "pair_id",
        "canonical_site_id",
        "zero_based_layer_index",
        "module_path",
        "hook_boundary",
        "hidden_size",
        "factor_carrier_selector",
        "base_prompt_id",
        "base_prompt_sha256",
        "effective_source_prompt_id",
        "effective_source_prompt_sha256",
        "base_activation_capture_record_sha256",
        "effective_source_activation_capture_record_sha256",
        "base_carrier_binding_record_sha256",
        "effective_source_carrier_binding_record_sha256",
        "patched_position_indices",
        "matched_null_seed_u64",
        "matched_null_permutation_sha256",
        "matched_null_signs_sha256",
        "base_activation_tensor_sha256",
        "source_activation_tensor_sha256",
        "source_minus_base_delta_tensor_sha256",
        "patched_activation_tensor_sha256",
        "output_text_sha256",
        "runtime_ledger_entry",
        "runtime_ledger_entry_sha256",
    }
    _exact_keys(execution, expected_fields, context=context)
    effective_source_is_base = condition_id == "self_sham"
    effective_prompt = (
        {
            "prompt_id": pair["base_prompt_id"],
            "prompt_sha256": pair["base_prompt_sha256"],
        }
        if effective_source_is_base
        else {
            "prompt_id": pair["source_prompt_id"],
            "prompt_sha256": pair["source_prompt_sha256"],
        }
    )
    effective_capture = base_capture_sha256 if effective_source_is_base else source_capture_sha256
    effective_binding = base_binding if effective_source_is_base else source_binding
    expected_exact = {
        "record_version": "intervention_execution_record_v1",
        "partition_id": partition_id,
        "operation_id": condition_id,
        "order_index": order_index,
        "model_unit_id": model_unit_id,
        "causal_variable": causal_variable,
        "pair_id": pair["pair_id"],
        "canonical_site_id": candidate["canonical_site_id"],
        "zero_based_layer_index": candidate["zero_based_layer_index"],
        "module_path": candidate["module_path"],
        "hook_boundary": candidate["hook_boundary"],
        "hidden_size": candidate["hidden_size"],
        "factor_carrier_selector": candidate["factor_carrier_selector"],
        "base_prompt_id": pair["base_prompt_id"],
        "base_prompt_sha256": pair["base_prompt_sha256"],
        "effective_source_prompt_id": effective_prompt["prompt_id"],
        "effective_source_prompt_sha256": effective_prompt["prompt_sha256"],
        "base_activation_capture_record_sha256": base_capture_sha256,
        "effective_source_activation_capture_record_sha256": effective_capture,
        "base_carrier_binding_record_sha256": canonical_artifact_sha256(base_binding),
        "effective_source_carrier_binding_record_sha256": canonical_artifact_sha256(
            effective_binding
        ),
        "patched_position_indices": (
            base_binding["control_position_indices"]
            if condition_id == "control_site_delta"
            else base_binding["carrier_position_indices"]
        ),
        "output_text_sha256": output_text_sha256,
    }
    for field, expected in expected_exact.items():
        if execution[field] != expected:
            raise ExecutionContractError(f"{context}.{field} drifted from the authorized operation")
    if condition_id == "norm_matched_rotation":
        seed = derive_matched_null_seed(
            authorization["discovery_authorization_id"],
            pair["pair_id"],
            candidate["canonical_site_id"],
        )
        permutation, signs = matched_null_permutation_and_signs(seed, candidate["hidden_size"])
        matched_values: dict[str, Any] = {
            "matched_null_seed_u64": seed,
            "matched_null_permutation_sha256": canonical_artifact_sha256(
                {"permutation": list(permutation)}
            ),
            "matched_null_signs_sha256": canonical_artifact_sha256({"signs": list(signs)}),
        }
    else:
        matched_values = {
            "matched_null_seed_u64": None,
            "matched_null_permutation_sha256": None,
            "matched_null_signs_sha256": None,
        }
    for field, expected in matched_values.items():
        if execution[field] != expected:
            raise ExecutionContractError(
                f"{context}.{field} does not match the frozen matched-null derivation"
            )
    for field in (
        "base_activation_tensor_sha256",
        "source_activation_tensor_sha256",
        "source_minus_base_delta_tensor_sha256",
        "patched_activation_tensor_sha256",
    ):
        _trusted_sha256(execution[field], context=f"{context}.{field}")
    if condition_id == "self_sham":
        if not (
            execution["base_activation_tensor_sha256"]
            == execution["source_activation_tensor_sha256"]
            == execution["patched_activation_tensor_sha256"]
        ):
            raise ExecutionContractError(
                f"{context} self-sham tensor digests must preserve the base activation"
            )
    elif condition_id in {"targeted_interchange", "control_site_delta"} and (
        execution["patched_activation_tensor_sha256"]
        != execution["source_activation_tensor_sha256"]
    ):
        raise ExecutionContractError(
            f"{context} direct replacement must equal the source-site tensor digest"
        )
    runtime_records = authorization["model_runtime_configuration"]["records"]
    model_runtime = next(
        record for record in runtime_records if record["model_unit_id"] == model_unit_id
    )
    model_family = candidate["architecture_family_id"]
    hook_record = next(
        record
        for record in authorization["activation_hook_registry"]["records"]
        if record["architecture_family_id"] == model_family
    )
    runtime_ledger = _mapping(
        execution["runtime_ledger_entry"], context=f"{context}.runtime_ledger_entry"
    )
    ledger_fields = {
        "ledger_version",
        "discovery_authorization_id",
        "partition_id",
        "model_unit_id",
        "pair_id",
        "canonical_site_id",
        "operation_id",
        "order_index",
        "hook_adapter_id",
        "module_path",
        "zero_based_layer_index",
        "patched_position_indices",
        "base_tensor_role",
        "source_tensor_role",
        "base_activation_tensor_sha256",
        "source_activation_tensor_sha256",
        "source_minus_base_delta_tensor_sha256",
        "patched_activation_tensor_sha256",
        "patch_operator_id",
        "runtime_dtype",
        "source_tree_sha256",
        "environment_lock_sha256",
        "hook_call_count",
        "competing_hook_count",
        "relation_check_id",
        "relation_check_passed",
        "output_text_sha256",
    }
    _exact_keys(runtime_ledger, ledger_fields, context=f"{context}.runtime_ledger_entry")
    operation_contract = {
        "targeted_interchange": (
            "base_carrier",
            "source_carrier",
            "direct_carrier_replacement_v1",
            "direct_replace_digest_equality_v1",
        ),
        "norm_matched_rotation": (
            "base_carrier",
            "source_carrier",
            "signed_permutation_carrier_delta_add_v1",
            "matched_null_parameter_and_replay_check_v1",
        ),
        "self_sham": (
            "base_carrier",
            "base_carrier",
            "base_to_base_carrier_sham_v1",
            "self_sham_identity_digest_equality_v1",
        ),
        "control_site_delta": (
            "base_control",
            "ordered_source_carrier_mapped_to_control",
            "ordered_carrier_to_control_replacement_v1",
            "direct_replace_digest_equality_v1",
        ),
    }[condition_id]
    ledger_expected = {
        "ledger_version": "trusted_authority_runtime_ledger_v1",
        "discovery_authorization_id": authorization["discovery_authorization_id"],
        "partition_id": partition_id,
        "model_unit_id": model_unit_id,
        "pair_id": pair["pair_id"],
        "canonical_site_id": candidate["canonical_site_id"],
        "operation_id": condition_id,
        "order_index": order_index,
        "hook_adapter_id": hook_record["hook_adapter_id"],
        "module_path": candidate["module_path"],
        "zero_based_layer_index": candidate["zero_based_layer_index"],
        "patched_position_indices": execution["patched_position_indices"],
        "base_tensor_role": operation_contract[0],
        "source_tensor_role": operation_contract[1],
        "base_activation_tensor_sha256": execution["base_activation_tensor_sha256"],
        "source_activation_tensor_sha256": execution["source_activation_tensor_sha256"],
        "source_minus_base_delta_tensor_sha256": execution["source_minus_base_delta_tensor_sha256"],
        "patched_activation_tensor_sha256": execution["patched_activation_tensor_sha256"],
        "patch_operator_id": operation_contract[2],
        "runtime_dtype": model_runtime["dtype"],
        "source_tree_sha256": authorization["environment_lock"]["source_tree_sha256"],
        "environment_lock_sha256": canonical_artifact_sha256(authorization["environment_lock"]),
        "hook_call_count": 1,
        "competing_hook_count": 0,
        "relation_check_id": operation_contract[3],
        "relation_check_passed": True,
        "output_text_sha256": output_text_sha256,
    }
    if dict(runtime_ledger) != ledger_expected:
        raise ExecutionContractError(
            f"{context} runtime ledger does not bind the exact hook operation"
        )
    if execution["runtime_ledger_entry_sha256"] != canonical_artifact_sha256(runtime_ledger):
        raise ExecutionContractError(f"{context} runtime ledger hash is not content-addressed")
    expected_record_sha256 = canonical_artifact_sha256(execution)
    if record_sha256 != expected_record_sha256:
        raise ExecutionContractError(
            f"{context} content address does not bind the execution record"
        )


def _validate_candidate_trial_evidence(
    value: Any,
    *,
    authorization: Mapping[str, Any],
    unpatched_evidence: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    models = _validate_model_registry(authorization["model_registry"])
    panels = _validate_candidate_site_inventory(
        authorization["candidate_site_inventory"],
        model_registry=models,
        activation_hook_registry=authorization["activation_hook_registry"],
    )
    candidate_lookup = {
        (model_id, variable, candidate["canonical_site_id"]): candidate
        for (model_id, variable), candidates in panels.items()
        for candidate in candidates
    }
    carrier_bindings = {
        (record["model_unit_id"], record["prompt_id"], record["causal_variable"]): record
        for record in authorization["carrier_binding_records"]
    }
    manifest = authorization["live_material_manifest"]
    pair_inventory = manifest["discovery_primary_pair_inventory"]
    pairs_by_variable: dict[str, list[Mapping[str, Any]]] = {
        variable: [] for variable in CAUSAL_VARIABLES
    }
    for pair in pair_inventory:
        pairs_by_variable[pair["causal_variable"]].append(pair)
    expected_identities = {
        (model_id, variable, candidate["canonical_site_id"], pair["pair_id"])
        for (model_id, variable), candidates in panels.items()
        for candidate in candidates
        for pair in pairs_by_variable[variable]
    }
    records = _sequence(value, context="candidate_trial_evidence")
    if len(records) != len(expected_identities):
        raise ExecutionContractError(
            "candidate_trial_evidence must cover every candidate x primary pair"
        )
    expected_fields = {
        "model_unit_id",
        "causal_variable",
        "canonical_site_id",
        "pair_id",
        "opaque_content_seed_id",
        "pair_record_sha256",
        "base_prompt_id",
        "base_prompt_sha256",
        "source_prompt_id",
        "source_prompt_sha256",
        "expected_patched_final",
        "base_oracle_final",
        "base_activation_capture_record_sha256",
        "source_activation_capture_record_sha256",
        "trial_order",
    }
    pair_lookup = {(pair["causal_variable"], pair["pair_id"]): pair for pair in pair_inventory}
    observed: set[tuple[str, str, str, str]] = set()
    order: list[tuple[str, str, str, str]] = []
    aggregate: dict[tuple[str, str, str], dict[str, Any]] = {}
    for index, raw in enumerate(records):
        item = _mapping(raw, context=f"candidate_trial_evidence[{index}]")
        _exact_keys(item, expected_fields, context=f"candidate_trial_evidence[{index}]")
        identity = (
            _text(
                item["model_unit_id"],
                context=f"candidate_trial_evidence[{index}].model_unit_id",
            ),
            _text(
                item["causal_variable"],
                context=f"candidate_trial_evidence[{index}].causal_variable",
            ),
            _text(
                item["canonical_site_id"],
                context=f"candidate_trial_evidence[{index}].canonical_site_id",
            ),
            _text(item["pair_id"], context=f"candidate_trial_evidence[{index}].pair_id"),
        )
        if identity not in expected_identities or identity in observed:
            raise ExecutionContractError(
                "candidate trial evidence has a missing, duplicate, or unauthorized identity"
            )
        observed.add(identity)
        order.append(identity)
        model_id, variable, site_id, pair_id = identity
        pair = pair_lookup[(variable, pair_id)]
        for field in (
            "opaque_content_seed_id",
            "pair_record_sha256",
            "base_prompt_id",
            "base_prompt_sha256",
            "source_prompt_id",
            "source_prompt_sha256",
            "expected_patched_final",
            "base_oracle_final",
        ):
            if item[field] != pair[field]:
                raise ExecutionContractError(
                    f"candidate trial {field} drifted from the primary pair inventory"
                )
        capture_bindings = {
            "base_activation_capture_record_sha256": unpatched_evidence[
                (model_id, pair["base_prompt_id"])
            ]["activation_capture_record_sha256"],
            "source_activation_capture_record_sha256": unpatched_evidence[
                (model_id, pair["source_prompt_id"])
            ]["activation_capture_record_sha256"],
        }
        for field, expected_capture in capture_bindings.items():
            if item[field] != expected_capture:
                raise ExecutionContractError(
                    "candidate trial activation capture drifted from unpatched evidence"
                )
        trial_order = _sequence(
            item["trial_order"], context=f"candidate_trial_evidence[{index}].trial_order"
        )
        if len(trial_order) != len(TRIAL_CONDITION_IDS):
            raise ExecutionContractError("each candidate trial must retain four conditions")
        expected_condition_order = derive_intervention_trial_condition_order(
            partition_id="D_site_discovery",
            split_manifest_sha256=authorization["split_manifest_sha256"],
            model_unit_id=model_id,
            causal_variable=variable,
            canonical_site_id=site_id,
            pair_id=pair_id,
        )
        outcomes: dict[str, int] = {}
        for condition_index, raw_condition in enumerate(trial_order):
            condition = _mapping(
                raw_condition,
                context=(f"candidate_trial_evidence[{index}].trial_order[{condition_index}]"),
            )
            _exact_keys(
                condition,
                {
                    "condition_id",
                    "order_index",
                    "output_text",
                    "output_text_sha256",
                    "parsed_final",
                    "success",
                    "intervention_execution_record",
                    "intervention_execution_record_sha256",
                },
                context=(f"candidate_trial_evidence[{index}].trial_order[{condition_index}]"),
            )
            if condition["order_index"] != condition_index:
                raise ExecutionContractError("trial order indices must be contiguous from zero")
            if condition["condition_id"] != expected_condition_order[condition_index]:
                raise ExecutionContractError(
                    "trial condition order does not match the precommitted permutation"
                )
            output_text = condition["output_text"]
            if not isinstance(output_text, str):
                raise ExecutionContractError("trial output_text must be text")
            if (
                condition["output_text_sha256"]
                != hashlib.sha256(output_text.encode("utf-8")).hexdigest()
            ):
                raise ExecutionContractError("trial output hash does not bind raw bytes")
            parsed = parse_final(output_text)
            parsed_value = None if parsed is None else parsed.value
            if condition["parsed_final"] != parsed_value:
                raise ExecutionContractError("trial parsed_final was not derived from output_text")
            expected_final = (
                pair["base_oracle_final"]
                if condition["condition_id"] == "self_sham"
                else pair["expected_patched_final"]
            )
            success = parsed is not None and f"FINAL: {parsed.value}" == expected_final
            if condition["success"] is not success:
                raise ExecutionContractError("trial success was not derived from raw output")
            base_binding = carrier_bindings[(model_id, pair["base_prompt_id"], variable)]
            source_binding = carrier_bindings[(model_id, pair["source_prompt_id"], variable)]
            validate_intervention_execution_record(
                condition["intervention_execution_record"],
                record_sha256=condition["intervention_execution_record_sha256"],
                authorization=authorization,
                partition_id="D_site_discovery",
                condition_id=condition["condition_id"],
                order_index=condition_index,
                model_unit_id=model_id,
                causal_variable=variable,
                candidate=candidate_lookup[(model_id, variable, site_id)],
                pair=pair,
                base_capture_sha256=item["base_activation_capture_record_sha256"],
                source_capture_sha256=item["source_activation_capture_record_sha256"],
                base_binding=base_binding,
                source_binding=source_binding,
                output_text_sha256=condition["output_text_sha256"],
                context=(
                    f"candidate_trial_evidence[{index}].trial_order"
                    f"[{condition_index}].intervention_execution_record"
                ),
            )
            outcomes[condition["condition_id"]] = int(success)
        candidate_identity = (model_id, variable, site_id)
        bucket = aggregate.setdefault(
            candidate_identity,
            {
                "condition_successes": Counter(),
                "condition_trials": Counter(),
                "by_seed": {},
            },
        )
        seed_id = pair["opaque_content_seed_id"]
        seed_bucket = bucket["by_seed"].setdefault(
            seed_id, {"condition_successes": Counter(), "condition_trials": Counter()}
        )
        for condition_id, success in outcomes.items():
            bucket["condition_successes"][condition_id] += success
            bucket["condition_trials"][condition_id] += 1
            seed_bucket["condition_successes"][condition_id] += success
            seed_bucket["condition_trials"][condition_id] += 1
    if observed != expected_identities or order != sorted(order):
        raise ExecutionContractError(
            "candidate_trial_evidence must be complete and canonically sorted"
        )
    for candidate_identity, bucket in aggregate.items():
        if set(bucket["by_seed"]) != {
            pair["opaque_content_seed_id"] for pair in pairs_by_variable[candidate_identity[1]]
        }:
            raise ExecutionContractError("candidate trials do not cover all discovery seeds")
        for seed_bucket in bucket["by_seed"].values():
            if any(
                seed_bucket["condition_trials"][condition_id] != 4
                for condition_id in TRIAL_CONDITION_IDS
            ):
                raise ExecutionContractError(
                    "each candidate must retain four primary pairs per discovery seed"
                )
    return aggregate


def _validate_candidate_evidence(
    value: Any,
    *,
    authorization: Mapping[str, Any],
    trial_aggregate: Mapping[tuple[str, str, str], Mapping[str, Any]],
) -> dict[tuple[str, str], tuple[Mapping[str, Any], ...]]:
    models = _validate_model_registry(authorization["model_registry"])
    panels = _validate_candidate_site_inventory(
        authorization["candidate_site_inventory"],
        model_registry=models,
        activation_hook_registry=authorization["activation_hook_registry"],
    )
    expected_candidates = {
        (model_id, variable, candidate["canonical_site_id"])
        for (model_id, variable), candidates in panels.items()
        for candidate in candidates
    }
    records = _sequence(value, context="candidate_evidence")
    if len(records) != len(expected_candidates):
        raise ExecutionContractError(
            "candidate_evidence must retain every authorized model x variable x site"
        )
    expected_fields = {
        "model_unit_id",
        "causal_variable",
        "canonical_site_id",
        "zero_based_layer_index",
        "intended_success_count",
        "intended_trial_count",
        "intended_iia",
        "matched_null_success_count",
        "matched_null_trial_count",
        "matched_null_iia",
        "self_sham_success_count",
        "self_sham_trial_count",
        "self_sham_iia",
        "control_site_success_count",
        "control_site_trial_count",
        "control_site_iia",
        "specific_score",
    }
    observed: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    order: list[tuple[str, str, str]] = []
    condition_field_prefixes = {
        "targeted_interchange": "intended",
        "norm_matched_rotation": "matched_null",
        "self_sham": "self_sham",
        "control_site_delta": "control_site",
    }
    condition_trial_totals = Counter()
    for index, raw in enumerate(records):
        item = _mapping(raw, context=f"candidate_evidence[{index}]")
        _exact_keys(item, expected_fields, context=f"candidate_evidence[{index}]")
        model_id = _text(
            item["model_unit_id"], context=f"candidate_evidence[{index}].model_unit_id"
        )
        variable = _text(
            item["causal_variable"], context=f"candidate_evidence[{index}].causal_variable"
        )
        site_id = _text(
            item["canonical_site_id"],
            context=f"candidate_evidence[{index}].canonical_site_id",
        )
        identity = (model_id, variable, site_id)
        if identity not in expected_candidates or identity in observed:
            raise ExecutionContractError(
                "candidate_evidence has a missing, duplicate, or unauthorized site"
            )
        inventory_candidates = {
            candidate["canonical_site_id"]: candidate for candidate in panels[(model_id, variable)]
        }
        layer = _nonnegative_int(
            item["zero_based_layer_index"],
            context=f"candidate_evidence[{index}].zero_based_layer_index",
        )
        if layer != inventory_candidates[site_id]["zero_based_layer_index"]:
            raise ExecutionContractError("candidate evidence layer drifted from inventory")
        aggregate = trial_aggregate[identity]
        count_values: dict[str, tuple[int, int, float]] = {}
        for condition_id, prefix in condition_field_prefixes.items():
            trials = _positive_int(
                item[f"{prefix}_trial_count"],
                context=f"candidate_evidence[{index}].{prefix}_trial_count",
            )
            success = _nonnegative_int(
                item[f"{prefix}_success_count"],
                context=f"candidate_evidence[{index}].{prefix}_success_count",
            )
            rate = _finite_number(
                item[f"{prefix}_iia"],
                context=f"candidate_evidence[{index}].{prefix}_iia",
            )
            if trials != 32:
                raise ExecutionContractError(
                    "every candidate condition must use the same 32 primary pairs"
                )
            if success > trials or abs(rate - success / trials) > 1e-12:
                raise ExecutionContractError(f"{prefix}_iia must equal success_count / trial_count")
            if (
                success != aggregate["condition_successes"][condition_id]
                or trials != aggregate["condition_trials"][condition_id]
            ):
                raise ExecutionContractError(
                    "candidate aggregate counts do not close per-pair trial evidence"
                )
            count_values[prefix] = (success, trials, rate)
            condition_trial_totals[condition_id] += trials
        intended_iia = count_values["intended"][2]
        matched_iia = count_values["matched_null"][2]
        score = _finite_number(
            item["specific_score"], context=f"candidate_evidence[{index}].specific_score"
        )
        if abs(score - (intended_iia - matched_iia)) > 1e-12:
            raise ExecutionContractError(
                "specific_score must equal intended_iia minus matched_null_iia"
            )
        observed[identity] = item
        order.append(identity)
    if set(observed) != expected_candidates or order != sorted(order):
        raise ExecutionContractError("candidate_evidence must be complete and canonically sorted")
    plan = authorization["discovery_query_plan"]
    planned_fields = {
        "targeted_interchange": "planned_targeted_intervention_forward_passes",
        "norm_matched_rotation": "planned_matched_null_forward_passes",
        "self_sham": "planned_self_sham_forward_passes",
        "control_site_delta": "planned_control_site_forward_passes",
    }
    for condition_id, plan_field in planned_fields.items():
        if condition_trial_totals[condition_id] != plan[plan_field]:
            raise ExecutionContractError(
                f"candidate {condition_id} trial counts do not close the query plan"
            )
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for (model_id, variable, _), item in observed.items():
        grouped.setdefault((model_id, variable), []).append(item)
    return {
        pair: tuple(
            sorted(
                items,
                key=lambda item: (
                    item["zero_based_layer_index"],
                    item["canonical_site_id"],
                ),
            )
        )
        for pair, items in grouped.items()
    }


def _validate_selected_sites(
    value: Any,
    *,
    authorization: Mapping[str, Any],
    evidence_by_panel: Mapping[tuple[str, str], tuple[Mapping[str, Any], ...]],
) -> tuple[Mapping[str, Any], ...]:
    records = _sequence(value, context="selected_sites")
    if len(records) != len(evidence_by_panel):
        raise ExecutionContractError(
            "selected_sites must contain one site per model x causal variable"
        )
    expected_fields = {
        "model_unit_id",
        "causal_variable",
        "selected_site_id",
        "runner_up_site_id",
        "candidate_site_count",
        "selection_score",
        "runner_up_score",
        "selection_gap",
    }
    observed_pairs: set[tuple[str, str]] = set()
    order: list[tuple[str, str]] = []
    for index, raw in enumerate(records):
        item = _mapping(raw, context=f"selected_sites[{index}]")
        _exact_keys(item, expected_fields, context=f"selected_sites[{index}]")
        pair = (
            _text(item["model_unit_id"], context=f"selected_sites[{index}].model_unit_id"),
            _text(
                item["causal_variable"],
                context=f"selected_sites[{index}].causal_variable",
            ),
        )
        if pair not in evidence_by_panel or pair in observed_pairs:
            raise ExecutionContractError("selected_sites has a duplicate or unknown panel")
        observed_pairs.add(pair)
        order.append(pair)
        ranked = sorted(
            evidence_by_panel[pair],
            key=lambda evidence: (
                -evidence["specific_score"],
                evidence["zero_based_layer_index"],
                evidence["canonical_site_id"],
            ),
        )
        winner, runner_up = ranked[:2]
        expected_values = {
            "selected_site_id": winner["canonical_site_id"],
            "runner_up_site_id": runner_up["canonical_site_id"],
            "candidate_site_count": len(ranked),
            "selection_score": winner["specific_score"],
            "runner_up_score": runner_up["specific_score"],
            "selection_gap": winner["specific_score"] - runner_up["specific_score"],
        }
        for field, expected_value in expected_values.items():
            observed_value = item[field]
            if isinstance(expected_value, float):
                if (
                    abs(
                        _finite_number(observed_value, context=f"selected_sites[{index}].{field}")
                        - expected_value
                    )
                    > 1e-12
                ):
                    raise ExecutionContractError(
                        f"selected_sites.{field} does not match frozen argmax/tie-break derivation"
                    )
            elif observed_value != expected_value:
                raise ExecutionContractError(
                    f"selected_sites.{field} does not match frozen argmax/tie-break derivation"
                )
    if observed_pairs != set(evidence_by_panel) or order != sorted(order):
        raise ExecutionContractError("selected_sites must be complete and canonically sorted")
    return tuple(records)


def _derive_site_selection_stability(
    *,
    selected_sites: Sequence[Mapping[str, Any]],
    evidence_by_panel: Mapping[tuple[str, str], tuple[Mapping[str, Any], ...]],
    trial_aggregate: Mapping[tuple[str, str, str], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    selected_by_panel = {
        (item["model_unit_id"], item["causal_variable"]): item for item in selected_sites
    }
    derived: list[dict[str, Any]] = []
    for panel in sorted(evidence_by_panel):
        candidates = evidence_by_panel[panel]
        seed_ids = sorted(
            trial_aggregate[(panel[0], panel[1], candidates[0]["canonical_site_id"])]["by_seed"]
        )
        if len(seed_ids) != 8:
            raise ExecutionContractError("stability derivation requires exactly eight seeds")
        leave_one_records: list[dict[str, Any]] = []
        selection_counts = Counter()
        for omitted_seed_id in seed_ids:
            scored: list[tuple[float, int, str]] = []
            for candidate in candidates:
                identity = (panel[0], panel[1], candidate["canonical_site_id"])
                aggregate = trial_aggregate[identity]
                omitted = aggregate["by_seed"][omitted_seed_id]
                targeted_success = (
                    aggregate["condition_successes"]["targeted_interchange"]
                    - omitted["condition_successes"]["targeted_interchange"]
                )
                targeted_trials = (
                    aggregate["condition_trials"]["targeted_interchange"]
                    - omitted["condition_trials"]["targeted_interchange"]
                )
                matched_success = (
                    aggregate["condition_successes"]["norm_matched_rotation"]
                    - omitted["condition_successes"]["norm_matched_rotation"]
                )
                matched_trials = (
                    aggregate["condition_trials"]["norm_matched_rotation"]
                    - omitted["condition_trials"]["norm_matched_rotation"]
                )
                if targeted_trials != 28 or matched_trials != 28:
                    raise ExecutionContractError(
                        "leave-one stability must retain exactly 28 pairs per candidate"
                    )
                score = targeted_success / targeted_trials - matched_success / matched_trials
                scored.append(
                    (
                        score,
                        candidate["zero_based_layer_index"],
                        candidate["canonical_site_id"],
                    )
                )
            ranked = sorted(scored, key=lambda item: (-item[0], item[1], item[2]))
            winner, runner_up = ranked[:2]
            selection_counts[winner[2]] += 1
            leave_one_records.append(
                {
                    "opaque_content_seed_id": omitted_seed_id,
                    "selected_site_id": winner[2],
                    "runner_up_site_id": runner_up[2],
                    "selection_score": winner[0],
                    "runner_up_score": runner_up[0],
                    "selection_gap": winner[0] - runner_up[0],
                }
            )
        full_selected = selected_by_panel[panel]["selected_site_id"]
        full_count = selection_counts[full_selected]
        derived.append(
            {
                "model_unit_id": panel[0],
                "causal_variable": panel[1],
                "full_data_selected_site_id": full_selected,
                "candidate_site_count": len(candidates),
                "leave_one_records": leave_one_records,
                "selection_histogram": [
                    {
                        "canonical_site_id": candidate["canonical_site_id"],
                        "selection_count": selection_counts[candidate["canonical_site_id"]],
                    }
                    for candidate in sorted(candidates, key=lambda item: item["canonical_site_id"])
                ],
                "full_data_selected_site_selection_count": full_count,
                "selection_frequency": full_count / 8,
                "stability_threshold": 0.75,
                "stable": full_count / 8 >= 0.75,
            }
        )
    return derived


def _validate_site_selection_stability(
    value: Any,
    *,
    selected_sites: Sequence[Mapping[str, Any]],
    evidence_by_panel: Mapping[tuple[str, str], tuple[Mapping[str, Any], ...]],
    trial_aggregate: Mapping[tuple[str, str, str], Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    records = _sequence(value, context="site_selection_stability")
    expected = _derive_site_selection_stability(
        selected_sites=selected_sites,
        evidence_by_panel=evidence_by_panel,
        trial_aggregate=trial_aggregate,
    )
    if len(records) != len(expected):
        raise ExecutionContractError(
            "site_selection_stability must contain one record per model x variable"
        )
    numeric_fields = {
        "selection_frequency",
        "stability_threshold",
    }
    leave_numeric_fields = {
        "selection_score",
        "runner_up_score",
        "selection_gap",
    }
    for index, (raw, expected_item) in enumerate(zip(records, expected)):
        item = _mapping(raw, context=f"site_selection_stability[{index}]")
        _exact_keys(item, set(expected_item), context=f"site_selection_stability[{index}]")
        for field, expected_value in expected_item.items():
            if field in numeric_fields:
                if (
                    abs(
                        _finite_number(
                            item[field], context=f"site_selection_stability[{index}].{field}"
                        )
                        - expected_value
                    )
                    > 1e-12
                ):
                    raise ExecutionContractError("site stability numeric field was forged")
            elif field == "leave_one_records":
                observed_leave = _sequence(
                    item[field], context=f"site_selection_stability[{index}].leave_one_records"
                )
                if len(observed_leave) != 8:
                    raise ExecutionContractError("site stability must retain eight omissions")
                for leave_index, (observed_raw, expected_leave) in enumerate(
                    zip(observed_leave, expected_value)
                ):
                    observed = _mapping(
                        observed_raw,
                        context=(
                            f"site_selection_stability[{index}].leave_one_records[{leave_index}]"
                        ),
                    )
                    _exact_keys(
                        observed,
                        set(expected_leave),
                        context=(
                            f"site_selection_stability[{index}].leave_one_records[{leave_index}]"
                        ),
                    )
                    for leave_field, leave_expected in expected_leave.items():
                        if leave_field in leave_numeric_fields:
                            if (
                                abs(
                                    _finite_number(
                                        observed[leave_field],
                                        context=(
                                            f"site_selection_stability[{index}]"
                                            f".leave_one_records[{leave_index}].{leave_field}"
                                        ),
                                    )
                                    - leave_expected
                                )
                                > 1e-12
                            ):
                                raise ExecutionContractError(
                                    "leave-one site-selection score was forged"
                                )
                        elif observed[leave_field] != leave_expected:
                            raise ExecutionContractError(
                                "leave-one site-selection identity was forged"
                            )
            elif item[field] != expected_value:
                raise ExecutionContractError("site-selection stability evidence was forged")
    return tuple(records)


def validate_site_discovery_report(
    value: Mapping[str, Any],
    *,
    authorization: Mapping[str, Any],
    expected_parent_design_manifest_sha256: str,
    expected_parent_discovery_template_sha256: str,
    expected_parent_execution_template_sha256: str,
) -> None:
    """Validate the immutable output of one authorized discovery run."""

    validate_discovery_authorization(
        authorization,
        expected_parent_design_manifest_sha256=expected_parent_design_manifest_sha256,
        expected_parent_discovery_template_sha256=expected_parent_discovery_template_sha256,
        expected_parent_execution_template_sha256=expected_parent_execution_template_sha256,
    )
    report = _mapping(value, context="site discovery report")
    expected = {
        "schema_version",
        "status",
        "discovery_authorization_id",
        "discovery_authorization_sha256",
        "candidate_site_set_sha256",
        "query_usage",
        "unpatched_prompt_evidence",
        "candidate_trial_evidence",
        "candidate_evidence",
        "selected_sites",
        "site_selection_stability",
    }
    _exact_keys(report, expected, context="site discovery report")
    if report["schema_version"] != SCHEMA_VERSION or report["status"] != "complete":
        raise ExecutionContractError("site discovery report must be complete v0.1.0")
    if report["discovery_authorization_id"] != authorization["discovery_authorization_id"]:
        raise ExecutionContractError("site discovery report authorization id mismatch")
    if report["discovery_authorization_sha256"] != canonical_artifact_sha256(authorization):
        raise ExecutionContractError("site discovery report authorization hash mismatch")
    if report["candidate_site_set_sha256"] != authorization["candidate_site_set_sha256"]:
        raise ExecutionContractError("site discovery report candidate-set hash mismatch")
    _validate_discovery_usage(report["query_usage"], plan=authorization["discovery_query_plan"])
    unpatched_evidence = _validate_unpatched_prompt_evidence(
        report["unpatched_prompt_evidence"], authorization=authorization
    )
    if len(unpatched_evidence) != report["query_usage"]["unpatched_forward_passes"]:
        raise ExecutionContractError("unpatched usage does not close the raw prompt ledger")
    trial_aggregate = _validate_candidate_trial_evidence(
        report["candidate_trial_evidence"],
        authorization=authorization,
        unpatched_evidence=unpatched_evidence,
    )
    evidence = _validate_candidate_evidence(
        report["candidate_evidence"],
        authorization=authorization,
        trial_aggregate=trial_aggregate,
    )
    selected_sites = _validate_selected_sites(
        report["selected_sites"],
        authorization=authorization,
        evidence_by_panel=evidence,
    )
    _validate_site_selection_stability(
        report["site_selection_stability"],
        selected_sites=selected_sites,
        evidence_by_panel=evidence,
        trial_aggregate=trial_aggregate,
    )


def _post_discovery_partition_root(
    partitions: Mapping[str, Mapping[str, Any]], *, field: str
) -> str:
    return canonical_artifact_sha256(
        {
            "scheme": "post_discovery_partition_root_v1",
            "field": field,
            "partition_roots": [
                {"partition_id": partition_id, field: partitions[partition_id][field]}
                for partition_id in (
                    "D_causal_label",
                    "D_behavior_fit",
                    "D_sealed_test",
                )
            ],
        }
    )


def _validate_final_material_bindings(record: Mapping[str, Any]) -> None:
    partitions = {
        item["partition_id"]: item for item in record["live_material_manifest"]["partition_records"]
    }
    causal = partitions["D_causal_label"]
    expected = {
        "case_set_sha256": _post_discovery_partition_root(partitions, field="case_set_sha256"),
        "projection_set_sha256": _post_discovery_partition_root(
            partitions, field="projection_set_sha256"
        ),
        "intervention_pair_set_sha256": causal["intervention_pair_set_sha256"],
        "primary_intervention_pair_set_sha256": causal["primary_intervention_pair_set_sha256"],
        "causal_label_primary_intervention_pair_set_sha256": causal[
            "primary_intervention_pair_set_sha256"
        ],
        "causal_label_primary_pair_inventory_sha256": causal["primary_pair_inventory_sha256"],
        "causal_label_unpatched_prompt_inventory_sha256": causal[
            "intervention_prompt_inventory_sha256"
        ],
    }
    for field, expected_value in expected.items():
        if record[field] != expected_value:
            raise ExecutionContractError(f"{field} does not bind the frozen live partition")


def _validate_final_query_plan(
    value: Any, *, execution_lock: Mapping[str, Any]
) -> Mapping[str, Any]:
    plan = _mapping(value, context="query_plan")
    expected = {f"planned_{field}" for field in POST_DISCOVERY_QUERY_COMPONENTS} | {
        "planned_total_forward_passes",
        "max_wall_clock_seconds",
    }
    phases = ("causal_label", "behavior_fit", "sealed_test", "diagnostic")
    expected.update(f"{phase}_prompt_inventory_sha256" for phase in phases)
    expected.update(f"{phase}_prompt_count" for phase in phases)
    _exact_keys(plan, expected, context="query_plan")
    partitions = {
        item["partition_id"]: item
        for item in execution_lock["live_material_manifest"]["partition_records"]
    }
    model_ids = [model["model_unit_id"] for model in execution_lock["model_registry"]]
    model_count = len(model_ids)
    causal = partitions["D_causal_label"]
    behavior = partitions["D_behavior_fit"]
    sealed = partitions["D_sealed_test"]
    expected_counts = {
        "causal_label": model_count
        * (
            causal["intervention_prompt_count"]
            + causal["primary_intervention_pair_count"] * len(TRIAL_CONDITION_IDS)
        ),
        "behavior_fit": model_count * behavior["weak_observations"],
        "sealed_test": model_count * (sealed["weak_observations"] + sealed["heldout_challenges"]),
        "diagnostic": model_count * sealed["diagnostic_cue_masks"],
    }
    total = 0
    for phase, expected_count in expected_counts.items():
        field = f"{phase}_forward_passes"
        count = _positive_int(plan[f"planned_{field}"], context=f"query_plan.planned_{field}")
        if count != expected_count:
            raise ExecutionContractError(
                f"planned_{field} does not equal the generator-derived exact count"
            )
        total += count
    declared_total = _positive_int(
        plan["planned_total_forward_passes"],
        context="query_plan.planned_total_forward_passes",
    )
    if declared_total != total:
        raise ExecutionContractError(
            "query_plan.planned_total_forward_passes must equal component sum"
        )
    selected_site_map_sha256 = canonical_artifact_sha256(
        {"selected_sites": execution_lock["causal_site_discovery"]["selected_sites"]}
    )
    expected_hashes = {
        "causal_label": _phase_prompt_inventory_sha256(
            phase_id="D_causal_label_complete_cells_and_four_conditions",
            model_unit_ids=model_ids,
            source_material={
                "intervention_prompt_set_sha256": causal["intervention_prompt_set_sha256"],
                "primary_intervention_pair_set_sha256": causal[
                    "primary_intervention_pair_set_sha256"
                ],
                "selected_site_map_sha256": selected_site_map_sha256,
            },
            role_ids=["canonical_intervention_prompt_v1", *TRIAL_CONDITION_IDS],
            prompt_count=expected_counts["causal_label"],
        ),
        "behavior_fit": _phase_prompt_inventory_sha256(
            phase_id="D_behavior_fit_weak_observations",
            model_unit_ids=model_ids,
            source_material={"projection_set_sha256": behavior["projection_set_sha256"]},
            role_ids=[OSSProjectionRole.WEAK_OBSERVATION.value],
            prompt_count=expected_counts["behavior_fit"],
        ),
        "sealed_test": _phase_prompt_inventory_sha256(
            phase_id="D_sealed_test_weak_and_challenge",
            model_unit_ids=model_ids,
            source_material={"projection_set_sha256": sealed["projection_set_sha256"]},
            role_ids=[
                OSSProjectionRole.WEAK_OBSERVATION.value,
                OSSProjectionRole.HELDOUT_CHALLENGE.value,
            ],
            prompt_count=expected_counts["sealed_test"],
        ),
        "diagnostic": _phase_prompt_inventory_sha256(
            phase_id="D_sealed_test_post_commitment_cue_mask",
            model_unit_ids=model_ids,
            source_material={"projection_set_sha256": sealed["projection_set_sha256"]},
            role_ids=[OSSProjectionRole.DIAGNOSTIC_CUE_MASK.value],
            prompt_count=expected_counts["diagnostic"],
        ),
    }
    for phase in phases:
        _trusted_sha256(
            plan[f"{phase}_prompt_inventory_sha256"],
            context=f"query_plan.{phase}_prompt_inventory_sha256",
        )
        if plan[f"{phase}_prompt_inventory_sha256"] != expected_hashes[phase]:
            raise ExecutionContractError(f"{phase} prompt inventory hash is not generator-derived")
        prompt_count = _positive_int(
            plan[f"{phase}_prompt_count"],
            context=f"query_plan.{phase}_prompt_count",
        )
        if prompt_count != expected_counts[phase]:
            raise ExecutionContractError(f"{phase} prompt inventory count is incomplete")
        if plan[f"planned_{phase}_forward_passes"] != prompt_count:
            raise ExecutionContractError(
                f"greedy {phase} query count must equal its prompt inventory count"
            )
    _positive_int(plan["max_wall_clock_seconds"], context="query_plan.max_wall_clock_seconds")
    return plan


def validate_post_discovery_query_ledger(
    value: Mapping[str, Any], *, execution_lock: Mapping[str, Any]
) -> None:
    """Validate an eventual actual ledger against the exact final query plan."""

    ledger = _mapping(value, context="post-discovery query ledger")
    expected = set(POST_DISCOVERY_QUERY_COMPONENTS) | {
        "total_forward_passes",
        "wall_clock_seconds",
    }
    _exact_keys(ledger, expected, context="post-discovery query ledger")
    plan = _validate_final_query_plan(execution_lock["query_plan"], execution_lock=execution_lock)
    total = 0
    for field in POST_DISCOVERY_QUERY_COMPONENTS:
        count = _nonnegative_int(ledger[field], context=f"query_ledger.{field}")
        if count != plan[f"planned_{field}"]:
            raise ExecutionContractError(
                f"post-discovery usage must exactly equal the plan for {field}"
            )
        total += count
    if ledger["total_forward_passes"] != total or total != plan["planned_total_forward_passes"]:
        raise ExecutionContractError("post-discovery total usage must exactly equal the plan")
    wall = _finite_number(ledger["wall_clock_seconds"], context="query_ledger.wall_clock_seconds")
    if wall < 0 or wall > plan["max_wall_clock_seconds"]:
        raise ExecutionContractError("post-discovery wall-clock plan exceeded")


def _validate_blind_runtime(value: Any, *, authorization: Mapping[str, Any]) -> None:
    record = _mapping(value, context="blind_runtime")
    expected = {
        "authority_secret_commitment_sha256",
        "authority_secret_entropy_bits",
        "secret_generation",
        "live_content_seed_derivation",
        "derived_seed_set_sha256",
        "pairing_token_scheme",
        "pairing_token_domains",
        "capability_boundary",
    }
    _exact_keys(record, expected, context="blind_runtime")
    live = authorization["live_seed_commitment"]
    comparisons = {
        "authority_secret_commitment_sha256": live["authority_secret_commitment_sha256"],
        "authority_secret_entropy_bits": live["authority_secret_entropy_bits"],
        "secret_generation": live["secret_generation"],
        "live_content_seed_derivation": live["derivation_algorithm"],
        "derived_seed_set_sha256": live["derived_seed_set_sha256"],
    }
    for field, expected_value in comparisons.items():
        if record[field] != expected_value:
            raise ExecutionContractError(f"blind_runtime.{field} drifted from authorization")
    if record["pairing_token_scheme"] != PAIRING_TOKEN_SCHEME:
        raise ExecutionContractError("blind pairing-token scheme is not frozen")
    if record["pairing_token_domains"] != list(PAIRING_TOKEN_DOMAINS):
        raise ExecutionContractError("blind pairing-token domains are not frozen")
    if (
        record["capability_boundary"]
        != "separate_os_principal_container_or_user_controlled_unmounted_mount"
    ):
        raise ExecutionContractError("blind capability boundary is not frozen")


def _validate_prospective_contract(value: Any, *, expected_contract: Mapping[str, str]) -> None:
    record = _mapping(value, context="prospective_contract")
    expected = {
        "scoring_contract_sha256",
        "scoring_source_sha256",
        "challenge_slot_schema_sha256",
        "prediction_schema_sha256",
        "scoring_key_schema_sha256",
    }
    _exact_keys(record, expected, context="prospective_contract")
    expected_record = _mapping(expected_contract, context="expected_prospective_contract")
    _exact_keys(expected_record, expected, context="expected_prospective_contract")
    for field in expected:
        trusted = _trusted_sha256(
            expected_record[field], context=f"expected_prospective_contract.{field}"
        )
        observed = _trusted_sha256(record[field], context=f"prospective_contract.{field}")
        if observed != trusted:
            raise ExecutionContractError(f"prospective contract hash drifted={field}")


def _validate_authority_commitments(value: Any) -> None:
    record = _mapping(value, context="authority_commitments")
    expected = {
        "scheme",
        "evaluation_key_commitment",
        "challenge_bundle_commitment",
    }
    _exact_keys(record, expected, context="authority_commitments")
    if record["scheme"] != AUTHORITY_COMMITMENT_SCHEME:
        raise ExecutionContractError("authority commitment scheme is not frozen")
    _trusted_sha256(record["evaluation_key_commitment"], context="evaluation_key_commitment")
    _trusted_sha256(record["challenge_bundle_commitment"], context="challenge_bundle_commitment")


def validate_execution_lock_template(
    value: Mapping[str, Any], *, expected_parent_design_manifest_sha256: str
) -> None:
    """Validate the immutable, call-free final-execution template."""

    record = _mapping(value, context="execution lock template")
    _exact_keys(record, EXECUTION_LOCK_FIELDS, context="execution lock template")
    if record["schema_version"] != SCHEMA_VERSION or record["status"] != "unassigned":
        raise ExecutionContractError("execution lock template must be unassigned v0.1.0")
    _text(record["design_freeze_id"], context="design_freeze_id")
    trusted_parent_design = _trusted_sha256(
        expected_parent_design_manifest_sha256,
        context="expected_parent_design_manifest_sha256",
    )
    parent_design = _trusted_sha256(
        record["parent_design_manifest_sha256"], context="parent_design_manifest_sha256"
    )
    if parent_design != trusted_parent_design:
        raise ExecutionContractError("execution template parent design hash mismatch")
    empty_arrays = (
        "architecture_families",
        "model_registry",
        "dependency_clusters",
        "candidate_site_inventory",
    )
    if any(record[field] != [] for field in empty_arrays):
        raise ExecutionContractError("unassigned execution template contains assigned arrays")
    if record["feature_whitelist"] != list(FEATURE_WHITELIST):
        raise ExecutionContractError("execution template feature whitelist drifted")
    nullable = EXECUTION_LOCK_FIELDS - {
        "schema_version",
        "design_freeze_id",
        "parent_design_manifest_sha256",
        "status",
        "feature_whitelist",
        *empty_arrays,
    }
    if any(record[field] is not None for field in nullable):
        raise ExecutionContractError("unassigned execution template contains assigned fields")


def validate_execution_lock(
    value: Mapping[str, Any],
    *,
    authorization: Mapping[str, Any],
    site_discovery_report: Mapping[str, Any],
    expected_parent_design_manifest_sha256: str,
    expected_parent_discovery_template_sha256: str,
    expected_parent_execution_template_sha256: str,
    expected_prospective_contract: Mapping[str, str],
) -> None:
    """Validate the final immutable lock and all two-stage ancestry constraints."""

    validate_discovery_authorization(
        authorization,
        expected_parent_design_manifest_sha256=expected_parent_design_manifest_sha256,
        expected_parent_discovery_template_sha256=expected_parent_discovery_template_sha256,
        expected_parent_execution_template_sha256=expected_parent_execution_template_sha256,
    )
    validate_site_discovery_report(
        site_discovery_report,
        authorization=authorization,
        expected_parent_design_manifest_sha256=expected_parent_design_manifest_sha256,
        expected_parent_discovery_template_sha256=expected_parent_discovery_template_sha256,
        expected_parent_execution_template_sha256=expected_parent_execution_template_sha256,
    )
    record = _mapping(value, context="execution lock")
    _exact_keys(record, EXECUTION_LOCK_FIELDS, context="execution lock")
    if record["schema_version"] != SCHEMA_VERSION or record["status"] != EXECUTION_LOCK_STATUS:
        raise ExecutionContractError("execution lock must be locked v0.1.0")
    if record["design_freeze_id"] != authorization["design_freeze_id"]:
        raise ExecutionContractError("execution lock design_freeze_id drifted")
    if record["parent_design_manifest_sha256"] != authorization["parent_design_manifest_sha256"]:
        raise ExecutionContractError("execution lock parent design hash drifted")
    if record["parent_design_manifest_sha256"] != _trusted_sha256(
        expected_parent_design_manifest_sha256,
        context="expected_parent_design_manifest_sha256",
    ):
        raise ExecutionContractError("execution lock does not bind the trusted design root")
    _text(record["lock_id"], context="lock_id")
    _timestamp(record["locked_at"], context="locked_at")
    parent_template = _trusted_sha256(
        record["parent_execution_template_sha256"],
        context="parent_execution_template_sha256",
    )
    if parent_template != _trusted_sha256(
        expected_parent_execution_template_sha256,
        context="expected_parent_execution_template_sha256",
    ):
        raise ExecutionContractError("execution lock parent template hash mismatch")
    if parent_template != authorization["parent_execution_template_sha256"]:
        raise ExecutionContractError("execution lock does not preserve its authorized template")
    if record["discovery_authorization_id"] != authorization["discovery_authorization_id"]:
        raise ExecutionContractError("execution lock discovery authorization id mismatch")
    if record["discovery_authorization_sha256"] != canonical_artifact_sha256(authorization):
        raise ExecutionContractError("execution lock discovery authorization hash mismatch")
    if record["site_discovery_report_sha256"] != canonical_artifact_sha256(site_discovery_report):
        raise ExecutionContractError("execution lock site-discovery report hash mismatch")
    for field in AUTHORIZATION_BOUND_FIELDS:
        if record[field] != authorization[field]:
            raise ExecutionContractError(
                f"execution lock authorization-bound field drifted={field}"
            )
    _validate_common_authorized_surface(record)

    causal = _mapping(record["causal_site_discovery"], context="causal_site_discovery")
    _exact_keys(
        causal,
        {"query_usage", "selected_sites", "site_selection_stability"},
        context="causal_site_discovery",
    )
    if causal["query_usage"] != site_discovery_report["query_usage"]:
        raise ExecutionContractError("execution lock discovery usage drifted from report")
    if causal["selected_sites"] != site_discovery_report["selected_sites"]:
        raise ExecutionContractError("execution lock selected sites drifted from report")
    if causal["site_selection_stability"] != site_discovery_report["site_selection_stability"]:
        raise ExecutionContractError("execution lock site stability drifted from report")
    _validate_discovery_usage(causal["query_usage"], plan=record["discovery_query_plan"])
    unpatched_evidence = _validate_unpatched_prompt_evidence(
        site_discovery_report["unpatched_prompt_evidence"], authorization=authorization
    )
    trial_aggregate = _validate_candidate_trial_evidence(
        site_discovery_report["candidate_trial_evidence"],
        authorization=authorization,
        unpatched_evidence=unpatched_evidence,
    )
    evidence = _validate_candidate_evidence(
        site_discovery_report["candidate_evidence"],
        authorization=authorization,
        trial_aggregate=trial_aggregate,
    )
    selected_sites = _validate_selected_sites(
        causal["selected_sites"],
        authorization=authorization,
        evidence_by_panel=evidence,
    )
    _validate_site_selection_stability(
        causal["site_selection_stability"],
        selected_sites=selected_sites,
        evidence_by_panel=evidence,
        trial_aggregate=trial_aggregate,
    )

    for field in (
        "case_set_sha256",
        "projection_set_sha256",
        "intervention_pair_set_sha256",
        "primary_intervention_pair_set_sha256",
        "causal_label_primary_intervention_pair_set_sha256",
        "causal_label_primary_pair_inventory_sha256",
        "causal_label_unpatched_prompt_inventory_sha256",
        "post_discovery_carrier_binding_report_sha256",
    ):
        _trusted_sha256(record[field], context=field)
    if (
        record["post_discovery_carrier_binding_report_sha256"]
        == record["carrier_binding_report_sha256"]
    ):
        raise ExecutionContractError(
            "post-discovery carrier binding report must be distinct from discovery binding"
        )
    causal_partition = next(
        item
        for item in record["live_material_manifest"]["partition_records"]
        if item["partition_id"] == "D_causal_label"
    )
    validate_carrier_binding_records(
        record["post_discovery_carrier_binding_records"],
        report_sha256=record["post_discovery_carrier_binding_report_sha256"],
        summary_value=record["post_discovery_carrier_binding_summary"],
        prompt_inventory=causal_partition["intervention_prompt_inventory"],
        model_registry=_validate_model_registry(record["model_registry"]),
        context="post_discovery_carrier_binding_records",
    )
    if record["feature_whitelist"] != list(FEATURE_WHITELIST):
        raise ExecutionContractError("execution lock feature whitelist drifted")
    _validate_final_material_bindings(record)
    _validate_final_query_plan(record["query_plan"], execution_lock=record)
    _validate_decoding_config(
        record["post_discovery_decoding_config"],
        model_registry=_validate_model_registry(record["model_registry"]),
        tokenizer_compatibility=record["tokenizer_compatibility"],
        context="post_discovery_decoding_config",
    )
    if record["post_discovery_decoding_config"] != record["discovery_decoding_config"]:
        raise ExecutionContractError(
            "post-discovery decoding configuration must exactly preserve discovery decoding"
        )
    _validate_blind_runtime(record["blind_runtime"], authorization=authorization)
    _validate_prospective_contract(
        record["prospective_contract"], expected_contract=expected_prospective_contract
    )
    if record["authority_commitments"] is not None:
        raise ExecutionContractError(
            "pre-forward execution lock must leave output-derived authority commitments pending"
        )
