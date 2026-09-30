from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from jsonschema import ValidationError
from jsonschema.validators import validator_for

import latent_trace_tomography.execution as execution
from latent_trace_tomography.execution import (
    AUTHORIZATION_BOUND_FIELDS,
    CANDIDATE_SITE_ALGORITHM,
    CAUSAL_VARIABLES,
    FEATURE_WHITELIST,
    NUISANCE_BALANCE_CONTRACT,
    ExecutionContractError,
    build_live_material_manifest,
    canonical_artifact_sha256,
    derive_intervention_trial_condition_order,
    validate_discovery_authorization,
    validate_discovery_authorization_template,
    validate_discovery_readiness,
    validate_execution_lock,
    validate_execution_lock_template,
    validate_post_discovery_query_ledger,
    validate_site_discovery_report,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_ROOT = REPO_ROOT / "protocols" / "oss_reliance_regime_v0"
SCHEMA_ROOT = REPO_ROOT / "schemas"
DESIGN_HASH = "a" * 64
DISCOVERY_TEMPLATE_HASH = "b" * 64
EXECUTION_TEMPLATE_HASH = "c" * 64
PROSPECTIVE_HASHES = {
    "scoring_contract_sha256": "1" * 64,
    "scoring_source_sha256": "2" * 64,
    "challenge_slot_schema_sha256": "3" * 64,
    "prediction_schema_sha256": "4" * 64,
    "scoring_key_schema_sha256": "5" * 64,
}
AUTHORITY_SECRET = b"ltt-oss1-test-authority-secret-20260717-v1" * 2


def _hash(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _cluster_id(model_unit_ids: list[str]) -> str:
    material = "\x00".join(sorted(model_unit_ids)).encode("utf-8")
    return f"dependency-{hashlib.sha256(material).hexdigest()[:16]}"


def _trusted_kwargs() -> dict[str, str]:
    return {
        "expected_parent_design_manifest_sha256": DESIGN_HASH,
        "expected_parent_discovery_template_sha256": DISCOVERY_TEMPLATE_HASH,
        "expected_parent_execution_template_sha256": EXECUTION_TEMPLATE_HASH,
    }


def _model_registry() -> list[dict]:
    anchor_specs = (
        ("mixed", "mixed_anchor"),
        ("semantic", "semantic_anchor"),
        ("surface", "surface_cue_anchor"),
    )
    rows: list[dict] = []
    model_index = 0
    for cluster_name in ("a", "b", "c"):
        member_ids = [f"unit-{cluster_name}-{slug}" for slug, _ in anchor_specs]
        cluster_id = _cluster_id(member_ids)
        shared_base = _hash(f"shared-base-{cluster_name}")
        assignment_manifest = _hash(f"anchor-assignment-{cluster_name}")
        training_data = _hash(f"training-data-{cluster_name}")
        tokenizer_artifact = _hash(f"tokenizer-{cluster_name}")
        for slug, anchor in anchor_specs:
            model_index += 1
            rows.append(
                {
                    "model_unit_id": f"unit-{cluster_name}-{slug}",
                    "independent_training_run_id": f"training-{model_index:02d}",
                    "checkpoint_id": f"checkpoint-{model_index:02d}",
                    "lineage_id": f"lineage-{cluster_name}",
                    "dependency_cluster_id": cluster_id,
                    "architecture_family_id": f"family-{cluster_name}",
                    "anchor_condition_id": anchor,
                    "model_id": f"model-{model_index:02d}",
                    "model_revision": f"revision-{model_index:02d}",
                    "model_artifact_sha256": _hash(f"model-artifact-{model_index}"),
                    "shared_base_artifact_sha256": shared_base,
                    "configuration_sha256": _hash(f"config-{model_index}"),
                    "tokenizer_revision": f"tokenizer-{cluster_name}-revision",
                    "tokenizer_artifact_sha256": tokenizer_artifact,
                    "anchor_provenance": {
                        "assignment_timing": "pre_outcome_training_condition",
                        "anchor_assignment_manifest_sha256": assignment_manifest,
                        "training_recipe_sha256": _hash(f"recipe-{cluster_name}-{slug}"),
                        "training_data_sha256": training_data,
                    },
                }
            )
    return sorted(rows, key=lambda row: row["model_unit_id"])


def _candidate_inventory(models: list[dict]) -> list[dict]:
    selectors = CANDIDATE_SITE_ALGORITHM["carrier_token_selectors"]
    inventory: list[dict] = []
    for model in models:
        for variable in sorted(CAUSAL_VARIABLES):
            candidates = []
            for layer in (0, 1):
                candidates.append(
                    {
                        "canonical_site_id": (
                            f"{model['model_unit_id']}.{variable}.residual_post.layer_{layer:02d}"
                        ),
                        "architecture_family_id": model["architecture_family_id"],
                        "module_path": f"transformer.blocks.{layer}",
                        "zero_based_layer_index": layer,
                        "hook_boundary": "post_block_residual_before_next_block_v1",
                        "hidden_size": 8,
                        "factor_carrier_selector": selectors[variable],
                    }
                )
            inventory.append(
                {
                    "model_unit_id": model["model_unit_id"],
                    "causal_variable": variable,
                    "candidates": candidates,
                }
            )
    return inventory


def _decoding_config(models: list[dict], *, max_new_tokens: int) -> dict:
    return {
        "strategy": "greedy_exact_v1",
        "records": [
            {
                "model_unit_id": model["model_unit_id"],
                "do_sample": False,
                "temperature": None,
                "top_p": None,
                "top_k": None,
                "max_new_tokens": max_new_tokens,
                "repetition_penalty": 1.0,
                "stop_strings": [],
                "stop_token_ids": [],
                "pad_token_id": 0,
                "eos_token_ids": [1],
                "deterministic_seed_derivation_id": "not_applicable_greedy_v1",
                "replicates_per_prompt": 1,
            }
            for model in models
        ],
    }


def _activation_hook_registry() -> dict:
    records = []
    for family in ("family-a", "family-b", "family-c"):
        layers = [
            {
                "zero_based_layer_index": layer,
                "module_path": f"transformer.blocks.{layer}",
                "hook_boundary": "post_block_residual_before_next_block_v1",
            }
            for layer in range(2)
        ]
        records.append(
            {
                "architecture_family_id": family,
                "hook_adapter_id": f"{family}-residual-post-v1",
                "hook_registry_source_sha256": _hash(f"hook-source-{family}"),
                "hook_contract_sha256": _hash(f"hook-contract-{family}"),
                "model_configuration_source_sha256": _hash(f"model-config-source-{family}"),
                "transformer_block_count": 2,
                "hidden_size": 8,
                "module_path_template": "transformer.blocks.{layer_index}",
                "layer_module_inventory": layers,
                "layer_module_inventory_sha256": canonical_artifact_sha256(
                    {"layer_module_inventory": layers}
                ),
            }
        )
    return {
        "hook_boundary": "post_block_residual_before_next_block_v1",
        "records": records,
    }


def _learned_state_ancestry(models: list[dict]) -> tuple[dict, list[dict]]:
    external = sorted(
        [
            {
                "artifact_sha256": model["shared_base_artifact_sha256"],
                "artifact_role": "shared_base",
                "source_record_sha256": _hash(f"base-source-{model['dependency_cluster_id']}"),
            }
            for model in models[::3]
        ],
        key=lambda row: row["artifact_sha256"],
    )
    records = []
    for model in models:
        parent = {
            "parent_artifact_sha256": model["shared_base_artifact_sha256"],
            "parent_model_unit_id": None,
            "relationship": "shared_learned_weights",
            "source_record_sha256": _hash(f"parent-source-{model['model_unit_id']}"),
        }
        records.append(
            {
                "model_unit_id": model["model_unit_id"],
                "model_artifact_sha256": model["model_artifact_sha256"],
                "ancestry_complete": True,
                "ambiguous_parentage": False,
                "parents": [parent],
            }
        )
    body = {
        "policy_id": "complete_learned_state_parent_inventory_fail_closed_v1",
        "external_artifacts": external,
        "records": records,
    }
    ancestry = {**body, "inventory_sha256": canonical_artifact_sha256(body)}
    graph_edges: list[dict] = []
    by_base: dict[str, list[str]] = {}
    for model in models:
        by_base.setdefault(model["shared_base_artifact_sha256"], []).append(model["model_unit_id"])
    for members in by_base.values():
        members = sorted(members)
        for left_index, left in enumerate(members):
            for right in members[left_index + 1 :]:
                graph_edges.append(
                    {
                        "source_model_unit_id": left,
                        "target_model_unit_id": right,
                        "kind": "shared_learned_weights",
                    }
                )
    return ancestry, sorted(
        graph_edges,
        key=lambda edge: (
            edge["source_model_unit_id"],
            edge["target_model_unit_id"],
            edge["kind"],
        ),
    )


def _carrier_binding_records(
    models: list[dict], prompt_inventory: list[dict]
) -> tuple[list[dict], str, dict]:
    records: list[dict] = []
    for model in models:
        for prompt_index, prompt in enumerate(prompt_inventory):
            for variable in sorted(CAUSAL_VARIABLES):
                position_count = 2 if variable == "answer_codebook" else 1
                carrier_start = 10 + (prompt_index % 3) * 4
                carrier_positions = list(range(carrier_start, carrier_start + position_count))
                control_positions = [1, 8] if position_count == 2 else [2 + (prompt_index % 2)]
                records.append(
                    {
                        "model_unit_id": model["model_unit_id"],
                        "tokenizer_artifact_sha256": model["tokenizer_artifact_sha256"],
                        "prompt_id": prompt["prompt_id"],
                        "case_id": prompt["case_id"],
                        "prompt_sha256": prompt["prompt_sha256"],
                        "prompt_record_sha256": prompt["prompt_record_sha256"],
                        "causal_variable": variable,
                        "factor_carrier_selector": CANDIDATE_SITE_ALGORITHM[
                            "carrier_token_selectors"
                        ][variable],
                        "carrier_token_ids": [
                            2000 + prompt_index * 4 + offset for offset in range(position_count)
                        ],
                        "carrier_position_indices": carrier_positions,
                        "control_site_selector": execution.CARRIER_CONTROL_SELECTORS[variable],
                        "control_token_ids": [
                            3000 + prompt_index * 4 + offset for offset in range(position_count)
                        ],
                        "control_position_indices": control_positions,
                        "tokenized_input_length": 128,
                        "missing": False,
                        "ambiguous": False,
                        "truncated": False,
                        "compatible": True,
                    }
                )
    records.sort(
        key=lambda row: (
            row["model_unit_id"],
            row["prompt_id"],
            row["causal_variable"],
        )
    )
    report_hash = canonical_artifact_sha256(
        {"scheme": execution.CARRIER_BINDING_REPORT_SCHEME, "records": records}
    )
    summary = execution._carrier_binding_summary(
        case_count=len(prompt_inventory),
        model_count=len(models),
        record_count=len(records),
    )
    return records, report_hash, summary


def _authorization() -> dict:
    models = _model_registry()
    candidate_inventory = _candidate_inventory(models)
    ancestry, graph_edges = _learned_state_ancestry(models)
    material = build_live_material_manifest(AUTHORITY_SECRET)
    partitions = material["partition_records"]
    discovery = next(row for row in partitions if row["partition_id"] == "D_site_discovery")
    prompt_count = len(models) * discovery["intervention_prompt_count"]
    carrier_records, carrier_hash, carrier_summary = _carrier_binding_records(
        models, discovery["intervention_prompt_inventory"]
    )
    candidate_count = sum(len(panel["candidates"]) for panel in candidate_inventory)
    condition_count = candidate_count * 32
    split_hash = execution._partition_split_manifest_sha256(tuple(partitions))
    prompt_inventory_hash = execution._phase_prompt_inventory_sha256(
        phase_id="D_site_discovery_unpatched_activation_capture",
        model_unit_ids=[model["model_unit_id"] for model in models],
        source_material={
            "partition_id": "D_site_discovery",
            "intervention_prompt_set_sha256": discovery["intervention_prompt_set_sha256"],
        },
        role_ids=["canonical_intervention_prompt_v1"],
        prompt_count=prompt_count,
    )
    authorization: dict = {
        "schema_version": "0.1.0",
        "design_freeze_id": "oss_reliance_regime_v0_design_20260717",
        "parent_design_manifest_sha256": DESIGN_HASH,
        "status": "authorized",
        "discovery_authorization_id": "oss1-discovery-20260717-a",
        "authorized_at": "2026-07-17T20:00:00Z",
        "parent_discovery_template_sha256": DISCOVERY_TEMPLATE_HASH,
        "parent_execution_template_sha256": EXECUTION_TEMPLATE_HASH,
        "architecture_families": ["family-a", "family-b", "family-c"],
        "model_registry": models,
        "learned_state_ancestry": ancestry,
        "dependency_graph": {
            "algorithm": "undirected_learned_state_connected_components_v1",
            "nodes": [model["model_unit_id"] for model in models],
            "edges": graph_edges,
        },
        "dependency_clusters": sorted(
            [
                {
                    "dependency_cluster_id": _cluster_id(
                        [
                            f"unit-{cluster_name}-mixed",
                            f"unit-{cluster_name}-semantic",
                            f"unit-{cluster_name}-surface",
                        ]
                    ),
                    "model_unit_ids": [
                        f"unit-{cluster_name}-mixed",
                        f"unit-{cluster_name}-semantic",
                        f"unit-{cluster_name}-surface",
                    ],
                }
                for cluster_name in ("a", "b", "c")
            ],
            key=lambda cluster: cluster["dependency_cluster_id"],
        ),
        "nuisance_balance_contract": copy.deepcopy(NUISANCE_BALANCE_CONTRACT),
        "activation_hook_registry": _activation_hook_registry(),
        "tokenizer_compatibility": {
            "algorithm": "final_marker_single_continuation_v1",
            "add_special_tokens": False,
            "records": [
                {
                    "model_unit_id": model["model_unit_id"],
                    "tokenizer_revision": model["tokenizer_revision"],
                    "tokenizer_artifact_sha256": model["tokenizer_artifact_sha256"],
                    "final_prefix_token_ids": [40, 41],
                    "final_a_token_ids": [40, 41, 100 + index * 2],
                    "final_b_token_ids": [40, 41, 101 + index * 2],
                    "final_a_continuation_token_id": 100 + index * 2,
                    "final_b_continuation_token_id": 101 + index * 2,
                    "compatible": True,
                }
                for index, model in enumerate(models)
            ],
        },
        "live_seed_commitment": {
            "authority_secret_commitment_sha256": hashlib.sha256(AUTHORITY_SECRET).hexdigest(),
            "authority_secret_entropy_bits": 256,
            "secret_generation": "operating_system_csprng",
            "derivation_algorithm": "hmac_sha256_first_64bit_domain_separated_v1",
            "derivation_domain": "ltt:live-content-seed:v1",
            "requested_content_seed_count": 64,
            "derived_seed_set_sha256": material["derived_seed_set_sha256"],
        },
        "live_material_manifest_sha256": canonical_artifact_sha256(material),
        "live_material_manifest": material,
        "discovery_content_seed_set_sha256": discovery["content_seed_set_sha256"],
        "discovery_case_set_sha256": discovery["case_set_sha256"],
        "discovery_case_count": discovery["case_count"],
        "discovery_projection_set_sha256": discovery["projection_set_sha256"],
        "discovery_intervention_pair_set_sha256": discovery["intervention_pair_set_sha256"],
        "discovery_primary_intervention_pair_set_sha256": discovery[
            "primary_intervention_pair_set_sha256"
        ],
        "discovery_primary_pair_inventory_sha256": material[
            "discovery_primary_pair_inventory_sha256"
        ],
        "discovery_prompt_inventory_sha256": prompt_inventory_hash,
        "split_manifest_sha256": split_hash,
        "candidate_site_set_sha256": canonical_artifact_sha256(
            {"candidate_site_inventory": candidate_inventory}
        ),
        "candidate_site_inventory": candidate_inventory,
        "candidate_site_algorithm": copy.deepcopy(CANDIDATE_SITE_ALGORITHM),
        "discovery_panel_sha256": None,
        "discovery_query_plan": None,
        "discovery_decoding_config": _decoding_config(models, max_new_tokens=16),
        "model_runtime_configuration": {
            "records": [
                {
                    "model_unit_id": model["model_unit_id"],
                    "dtype": "bfloat16",
                    "attention_implementation": "eager",
                    "device_placement_policy": "single_device_explicit",
                    "quantization_mode": "none",
                    "eval_mode": True,
                    "use_cache": False,
                    "deterministic_algorithms": True,
                    "trust_remote_code": False,
                }
                for model in models
            ]
        },
        "carrier_binding_report_sha256": carrier_hash,
        "carrier_binding_records": carrier_records,
        "carrier_binding_summary": carrier_summary,
        "environment_lock": {
            "python_version": "3.12.9",
            "framework_name": "torch",
            "framework_version": "2.7.1",
            "model_runtime_name": "transformers",
            "model_runtime_version": "4.53.2",
            "device_type": "cuda-sm90",
            "deterministic_algorithms": True,
            "source_tree_sha256": _hash("source-tree"),
            "dependency_lock_sha256": _hash("dependency-lock"),
            "hardware_fingerprint_sha256": _hash("hardware"),
        },
    }
    authorization["discovery_panel_sha256"] = canonical_artifact_sha256(
        {
            field: authorization[field]
            for field in (
                "discovery_content_seed_set_sha256",
                "discovery_case_set_sha256",
                "discovery_projection_set_sha256",
                "discovery_intervention_pair_set_sha256",
                "discovery_prompt_inventory_sha256",
                "split_manifest_sha256",
            )
        }
    )
    authorization["discovery_query_plan"] = {
        "planned_total_forward_passes": prompt_count + 4 * condition_count,
        "planned_unpatched_forward_passes": prompt_count,
        "planned_targeted_intervention_forward_passes": condition_count,
        "planned_matched_null_forward_passes": condition_count,
        "planned_self_sham_forward_passes": condition_count,
        "planned_control_site_forward_passes": condition_count,
        "max_wall_clock_seconds": 3600,
        "discovery_panel_sha256": authorization["discovery_panel_sha256"],
        "discovery_intervention_pair_set_sha256": authorization[
            "discovery_intervention_pair_set_sha256"
        ],
        "discovery_primary_intervention_pair_set_sha256": authorization[
            "discovery_primary_intervention_pair_set_sha256"
        ],
        "discovery_primary_pair_inventory_sha256": authorization[
            "discovery_primary_pair_inventory_sha256"
        ],
        "candidate_site_set_sha256": authorization["candidate_site_set_sha256"],
        "discovery_prompt_inventory_sha256": authorization["discovery_prompt_inventory_sha256"],
        "discovery_prompt_count": prompt_count,
        "authorized_candidate_site_count": candidate_count,
        "discovery_primary_pair_count_per_causal_variable": 32,
    }
    return authorization


def _opposite_final(final: str) -> str:
    return "FINAL: B" if final == "FINAL: A" else "FINAL: A"


def _condition_execution_record(
    *,
    authorization: dict,
    model_id: str,
    variable: str,
    candidate: dict,
    pair: dict,
    condition_id: str,
    order_index: int,
    base_capture: str,
    source_capture: str,
    base_binding: dict,
    source_binding: dict,
    output_text_sha256: str,
    partition_id: str = "D_site_discovery",
) -> tuple[dict, str]:
    effective_base = condition_id == "self_sham"
    effective_prompt_id = pair["base_prompt_id"] if effective_base else pair["source_prompt_id"]
    effective_prompt_sha = (
        pair["base_prompt_sha256"] if effective_base else pair["source_prompt_sha256"]
    )
    effective_capture = base_capture if effective_base else source_capture
    effective_binding = base_binding if effective_base else source_binding
    positions = (
        base_binding["control_position_indices"]
        if condition_id == "control_site_delta"
        else base_binding["carrier_position_indices"]
    )
    base_tensor = _hash(
        f"base-tensor:{model_id}:{pair['pair_id']}:{candidate['canonical_site_id']}:{condition_id}"
    )
    source_tensor = (
        base_tensor
        if effective_base
        else _hash(
            f"source-tensor:{model_id}:{pair['pair_id']}:{candidate['canonical_site_id']}:{condition_id}"
        )
    )
    patched_tensor = (
        source_tensor
        if condition_id in {"targeted_interchange", "self_sham", "control_site_delta"}
        else _hash(f"patched-tensor:{model_id}:{pair['pair_id']}:{candidate['canonical_site_id']}")
    )
    if condition_id == "norm_matched_rotation":
        seed = execution.derive_matched_null_seed(
            authorization["discovery_authorization_id"],
            pair["pair_id"],
            candidate["canonical_site_id"],
        )
        permutation, signs = execution.matched_null_permutation_and_signs(
            seed, candidate["hidden_size"]
        )
        permutation_sha = canonical_artifact_sha256({"permutation": list(permutation)})
        signs_sha = canonical_artifact_sha256({"signs": list(signs)})
    else:
        seed = None
        permutation_sha = None
        signs_sha = None
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
    model = next(row for row in authorization["model_registry"] if row["model_unit_id"] == model_id)
    hook = next(
        row
        for row in authorization["activation_hook_registry"]["records"]
        if row["architecture_family_id"] == model["architecture_family_id"]
    )
    runtime = next(
        row
        for row in authorization["model_runtime_configuration"]["records"]
        if row["model_unit_id"] == model_id
    )
    delta_tensor = _hash(
        f"delta-tensor:{model_id}:{pair['pair_id']}:{candidate['canonical_site_id']}:{condition_id}"
    )
    ledger = {
        "ledger_version": "trusted_authority_runtime_ledger_v1",
        "discovery_authorization_id": authorization["discovery_authorization_id"],
        "partition_id": partition_id,
        "model_unit_id": model_id,
        "pair_id": pair["pair_id"],
        "canonical_site_id": candidate["canonical_site_id"],
        "operation_id": condition_id,
        "order_index": order_index,
        "hook_adapter_id": hook["hook_adapter_id"],
        "module_path": candidate["module_path"],
        "zero_based_layer_index": candidate["zero_based_layer_index"],
        "patched_position_indices": positions,
        "base_tensor_role": operation_contract[0],
        "source_tensor_role": operation_contract[1],
        "base_activation_tensor_sha256": base_tensor,
        "source_activation_tensor_sha256": source_tensor,
        "source_minus_base_delta_tensor_sha256": delta_tensor,
        "patched_activation_tensor_sha256": patched_tensor,
        "patch_operator_id": operation_contract[2],
        "runtime_dtype": runtime["dtype"],
        "source_tree_sha256": authorization["environment_lock"]["source_tree_sha256"],
        "environment_lock_sha256": canonical_artifact_sha256(authorization["environment_lock"]),
        "hook_call_count": 1,
        "competing_hook_count": 0,
        "relation_check_id": operation_contract[3],
        "relation_check_passed": True,
        "output_text_sha256": output_text_sha256,
    }
    record = {
        "record_version": "intervention_execution_record_v1",
        "partition_id": partition_id,
        "operation_id": condition_id,
        "order_index": order_index,
        "model_unit_id": model_id,
        "causal_variable": variable,
        "pair_id": pair["pair_id"],
        "canonical_site_id": candidate["canonical_site_id"],
        "zero_based_layer_index": candidate["zero_based_layer_index"],
        "module_path": candidate["module_path"],
        "hook_boundary": candidate["hook_boundary"],
        "hidden_size": candidate["hidden_size"],
        "factor_carrier_selector": candidate["factor_carrier_selector"],
        "base_prompt_id": pair["base_prompt_id"],
        "base_prompt_sha256": pair["base_prompt_sha256"],
        "effective_source_prompt_id": effective_prompt_id,
        "effective_source_prompt_sha256": effective_prompt_sha,
        "base_activation_capture_record_sha256": base_capture,
        "effective_source_activation_capture_record_sha256": effective_capture,
        "base_carrier_binding_record_sha256": canonical_artifact_sha256(base_binding),
        "effective_source_carrier_binding_record_sha256": canonical_artifact_sha256(
            effective_binding
        ),
        "patched_position_indices": positions,
        "matched_null_seed_u64": seed,
        "matched_null_permutation_sha256": permutation_sha,
        "matched_null_signs_sha256": signs_sha,
        "base_activation_tensor_sha256": base_tensor,
        "source_activation_tensor_sha256": source_tensor,
        "source_minus_base_delta_tensor_sha256": delta_tensor,
        "patched_activation_tensor_sha256": patched_tensor,
        "output_text_sha256": output_text_sha256,
        "runtime_ledger_entry": ledger,
        "runtime_ledger_entry_sha256": canonical_artifact_sha256(ledger),
    }
    return record, canonical_artifact_sha256(record)


def _report(authorization: dict) -> dict:
    models = authorization["model_registry"]
    prompts = authorization["live_material_manifest"]["discovery_intervention_prompt_inventory"]
    unpatched: list[dict] = []
    capture_by_prompt: dict[tuple[str, str], str] = {}
    for model in models:
        for prompt in prompts:
            output = prompt["oracle_final"]
            capture = _hash(f"capture:{model['model_unit_id']}:{prompt['prompt_id']}")
            capture_by_prompt[(model["model_unit_id"], prompt["prompt_id"])] = capture
            unpatched.append(
                {
                    "model_unit_id": model["model_unit_id"],
                    "prompt_id": prompt["prompt_id"],
                    "case_id": prompt["case_id"],
                    "prompt_sha256": prompt["prompt_sha256"],
                    "prompt_record_sha256": prompt["prompt_record_sha256"],
                    "oracle_final": prompt["oracle_final"],
                    "output_text": output,
                    "output_text_sha256": hashlib.sha256(output.encode()).hexdigest(),
                    "parsed_final": output.removeprefix("FINAL: "),
                    "oracle_correct": True,
                    "activation_capture_record_sha256": capture,
                }
            )
    binding_lookup = {
        (row["model_unit_id"], row["prompt_id"], row["causal_variable"]): row
        for row in authorization["carrier_binding_records"]
    }
    pairs_by_variable = {
        variable: [
            pair
            for pair in authorization["live_material_manifest"]["discovery_primary_pair_inventory"]
            if pair["causal_variable"] == variable
        ]
        for variable in CAUSAL_VARIABLES
    }
    trials: list[dict] = []
    evidence: list[dict] = []
    selected_sites: list[dict] = []
    for panel in authorization["candidate_site_inventory"]:
        model_id = panel["model_unit_id"]
        variable = panel["causal_variable"]
        panel_evidence: list[dict] = []
        for candidate_index, candidate in enumerate(panel["candidates"]):
            targeted_count = 0
            for pair_index, pair in enumerate(pairs_by_variable[variable]):
                targeted_success = candidate_index == 0 or pair_index % 4 < 2
                outcomes = {
                    "targeted_interchange": targeted_success,
                    "norm_matched_rotation": False,
                    "self_sham": True,
                    "control_site_delta": False,
                }
                targeted_count += int(targeted_success)
                base_capture = capture_by_prompt[(model_id, pair["base_prompt_id"])]
                source_capture = capture_by_prompt[(model_id, pair["source_prompt_id"])]
                base_binding = binding_lookup[(model_id, pair["base_prompt_id"], variable)]
                source_binding = binding_lookup[(model_id, pair["source_prompt_id"], variable)]
                condition_order = derive_intervention_trial_condition_order(
                    partition_id="D_site_discovery",
                    split_manifest_sha256=authorization["split_manifest_sha256"],
                    model_unit_id=model_id,
                    causal_variable=variable,
                    canonical_site_id=candidate["canonical_site_id"],
                    pair_id=pair["pair_id"],
                )
                condition_rows = []
                for order_index, condition_id in enumerate(condition_order):
                    expected_final = (
                        pair["base_oracle_final"]
                        if condition_id == "self_sham"
                        else pair["expected_patched_final"]
                    )
                    output = (
                        expected_final
                        if outcomes[condition_id]
                        else _opposite_final(expected_final)
                    )
                    output_sha = hashlib.sha256(output.encode()).hexdigest()
                    operation, operation_sha = _condition_execution_record(
                        authorization=authorization,
                        model_id=model_id,
                        variable=variable,
                        candidate=candidate,
                        pair=pair,
                        condition_id=condition_id,
                        order_index=order_index,
                        base_capture=base_capture,
                        source_capture=source_capture,
                        base_binding=base_binding,
                        source_binding=source_binding,
                        output_text_sha256=output_sha,
                    )
                    condition_rows.append(
                        {
                            "condition_id": condition_id,
                            "order_index": order_index,
                            "output_text": output,
                            "output_text_sha256": output_sha,
                            "parsed_final": output.removeprefix("FINAL: "),
                            "success": outcomes[condition_id],
                            "intervention_execution_record": operation,
                            "intervention_execution_record_sha256": operation_sha,
                        }
                    )
                trials.append(
                    {
                        "model_unit_id": model_id,
                        "causal_variable": variable,
                        "canonical_site_id": candidate["canonical_site_id"],
                        **pair,
                        "base_activation_capture_record_sha256": base_capture,
                        "source_activation_capture_record_sha256": source_capture,
                        "trial_order": condition_rows,
                    }
                )
            item = {
                "model_unit_id": model_id,
                "causal_variable": variable,
                "canonical_site_id": candidate["canonical_site_id"],
                "zero_based_layer_index": candidate["zero_based_layer_index"],
                "intended_success_count": targeted_count,
                "intended_trial_count": 32,
                "intended_iia": targeted_count / 32,
                "matched_null_success_count": 0,
                "matched_null_trial_count": 32,
                "matched_null_iia": 0.0,
                "self_sham_success_count": 32,
                "self_sham_trial_count": 32,
                "self_sham_iia": 1.0,
                "control_site_success_count": 0,
                "control_site_trial_count": 32,
                "control_site_iia": 0.0,
                "specific_score": targeted_count / 32,
            }
            evidence.append(item)
            panel_evidence.append(item)
        winner, runner_up = sorted(
            panel_evidence,
            key=lambda item: (
                -item["specific_score"],
                item["zero_based_layer_index"],
                item["canonical_site_id"],
            ),
        )
        selected_sites.append(
            {
                "model_unit_id": model_id,
                "causal_variable": variable,
                "selected_site_id": winner["canonical_site_id"],
                "runner_up_site_id": runner_up["canonical_site_id"],
                "candidate_site_count": len(panel_evidence),
                "selection_score": winner["specific_score"],
                "runner_up_score": runner_up["specific_score"],
                "selection_gap": winner["specific_score"] - runner_up["specific_score"],
            }
        )
    unpatched_map = execution._validate_unpatched_prompt_evidence(
        unpatched, authorization=authorization
    )
    aggregate = execution._validate_candidate_trial_evidence(
        trials, authorization=authorization, unpatched_evidence=unpatched_map
    )
    evidence_by_panel = {
        (panel["model_unit_id"], panel["causal_variable"]): tuple(
            item
            for item in evidence
            if item["model_unit_id"] == panel["model_unit_id"]
            and item["causal_variable"] == panel["causal_variable"]
        )
        for panel in authorization["candidate_site_inventory"]
    }
    stability = execution._derive_site_selection_stability(
        selected_sites=selected_sites,
        evidence_by_panel=evidence_by_panel,
        trial_aggregate=aggregate,
    )
    plan = authorization["discovery_query_plan"]
    return {
        "schema_version": "0.1.0",
        "status": "complete",
        "discovery_authorization_id": authorization["discovery_authorization_id"],
        "discovery_authorization_sha256": canonical_artifact_sha256(authorization),
        "candidate_site_set_sha256": authorization["candidate_site_set_sha256"],
        "query_usage": {
            "total_forward_passes": plan["planned_total_forward_passes"],
            "unpatched_forward_passes": plan["planned_unpatched_forward_passes"],
            "targeted_intervention_forward_passes": plan[
                "planned_targeted_intervention_forward_passes"
            ],
            "matched_null_forward_passes": plan["planned_matched_null_forward_passes"],
            "self_sham_forward_passes": plan["planned_self_sham_forward_passes"],
            "control_site_forward_passes": plan["planned_control_site_forward_passes"],
            "wall_clock_seconds": 120.5,
        },
        "unpatched_prompt_evidence": unpatched,
        "candidate_trial_evidence": trials,
        "candidate_evidence": evidence,
        "selected_sites": selected_sites,
        "site_selection_stability": stability,
    }


def _execution_lock(authorization: dict, report: dict) -> dict:
    models = authorization["model_registry"]
    partitions = {
        row["partition_id"]: row
        for row in authorization["live_material_manifest"]["partition_records"]
    }
    causal = partitions["D_causal_label"]
    behavior = partitions["D_behavior_fit"]
    sealed = partitions["D_sealed_test"]
    causal_bindings, causal_binding_hash, causal_binding_summary = _carrier_binding_records(
        models, causal["intervention_prompt_inventory"]
    )
    counts = {
        "causal_label": len(models)
        * (causal["intervention_prompt_count"] + causal["primary_intervention_pair_count"] * 4),
        "behavior_fit": len(models) * behavior["weak_observations"],
        "sealed_test": len(models) * (sealed["weak_observations"] + sealed["heldout_challenges"]),
        "diagnostic": len(models) * sealed["diagnostic_cue_masks"],
    }
    model_ids = [model["model_unit_id"] for model in models]
    selected_hash = canonical_artifact_sha256({"selected_sites": report["selected_sites"]})
    phase_hashes = {
        "causal_label": execution._phase_prompt_inventory_sha256(
            phase_id="D_causal_label_complete_cells_and_four_conditions",
            model_unit_ids=model_ids,
            source_material={
                "intervention_prompt_set_sha256": causal["intervention_prompt_set_sha256"],
                "primary_intervention_pair_set_sha256": causal[
                    "primary_intervention_pair_set_sha256"
                ],
                "selected_site_map_sha256": selected_hash,
            },
            role_ids=["canonical_intervention_prompt_v1", *execution.TRIAL_CONDITION_IDS],
            prompt_count=counts["causal_label"],
        ),
        "behavior_fit": execution._phase_prompt_inventory_sha256(
            phase_id="D_behavior_fit_weak_observations",
            model_unit_ids=model_ids,
            source_material={"projection_set_sha256": behavior["projection_set_sha256"]},
            role_ids=["weak_observation"],
            prompt_count=counts["behavior_fit"],
        ),
        "sealed_test": execution._phase_prompt_inventory_sha256(
            phase_id="D_sealed_test_weak_and_challenge",
            model_unit_ids=model_ids,
            source_material={"projection_set_sha256": sealed["projection_set_sha256"]},
            role_ids=["weak_observation", "heldout_challenge"],
            prompt_count=counts["sealed_test"],
        ),
        "diagnostic": execution._phase_prompt_inventory_sha256(
            phase_id="D_sealed_test_post_commitment_cue_mask",
            model_unit_ids=model_ids,
            source_material={"projection_set_sha256": sealed["projection_set_sha256"]},
            role_ids=["diagnostic_cue_mask"],
            prompt_count=counts["diagnostic"],
        ),
    }
    lock = {
        "schema_version": "0.1.0",
        "design_freeze_id": authorization["design_freeze_id"],
        "parent_design_manifest_sha256": authorization["parent_design_manifest_sha256"],
        "status": "locked",
        "lock_id": "oss1-execution-20260717-a",
        "locked_at": "2026-07-17T21:00:00Z",
        "parent_execution_template_sha256": EXECUTION_TEMPLATE_HASH,
        "discovery_authorization_id": authorization["discovery_authorization_id"],
        "discovery_authorization_sha256": canonical_artifact_sha256(authorization),
        "site_discovery_report_sha256": canonical_artifact_sha256(report),
        **{field: copy.deepcopy(authorization[field]) for field in AUTHORIZATION_BOUND_FIELDS},
        "causal_site_discovery": {
            "query_usage": copy.deepcopy(report["query_usage"]),
            "selected_sites": copy.deepcopy(report["selected_sites"]),
            "site_selection_stability": copy.deepcopy(report["site_selection_stability"]),
        },
        "case_set_sha256": execution._post_discovery_partition_root(
            partitions, field="case_set_sha256"
        ),
        "projection_set_sha256": execution._post_discovery_partition_root(
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
        "feature_whitelist": list(FEATURE_WHITELIST),
        "query_plan": {
            "planned_total_forward_passes": sum(counts.values()),
            "planned_causal_label_forward_passes": counts["causal_label"],
            "planned_behavior_fit_forward_passes": counts["behavior_fit"],
            "planned_sealed_test_forward_passes": counts["sealed_test"],
            "planned_diagnostic_forward_passes": counts["diagnostic"],
            "max_wall_clock_seconds": 7200,
            "causal_label_prompt_inventory_sha256": phase_hashes["causal_label"],
            "causal_label_prompt_count": counts["causal_label"],
            "behavior_fit_prompt_inventory_sha256": phase_hashes["behavior_fit"],
            "behavior_fit_prompt_count": counts["behavior_fit"],
            "sealed_test_prompt_inventory_sha256": phase_hashes["sealed_test"],
            "sealed_test_prompt_count": counts["sealed_test"],
            "diagnostic_prompt_inventory_sha256": phase_hashes["diagnostic"],
            "diagnostic_prompt_count": counts["diagnostic"],
        },
        "post_discovery_decoding_config": copy.deepcopy(authorization["discovery_decoding_config"]),
        "post_discovery_carrier_binding_report_sha256": causal_binding_hash,
        "post_discovery_carrier_binding_records": causal_bindings,
        "post_discovery_carrier_binding_summary": causal_binding_summary,
        "blind_runtime": {
            "authority_secret_commitment_sha256": authorization["live_seed_commitment"][
                "authority_secret_commitment_sha256"
            ],
            "authority_secret_entropy_bits": 256,
            "secret_generation": "operating_system_csprng",
            "live_content_seed_derivation": "hmac_sha256_first_64bit_domain_separated_v1",
            "derived_seed_set_sha256": authorization["live_seed_commitment"][
                "derived_seed_set_sha256"
            ],
            "pairing_token_scheme": "hmac_sha256_128bit_domain_separated_v1",
            "pairing_token_domains": [
                "target",
                "cluster",
                "fold",
                "case",
                "projection",
                "replicate",
                "challenge_slot",
            ],
            "capability_boundary": (
                "separate_os_principal_container_or_user_controlled_unmounted_mount"
            ),
        },
        "prospective_contract": copy.deepcopy(PROSPECTIVE_HASHES),
        "authority_commitments": None,
    }
    return lock


def _validate_report(report: dict, authorization: dict) -> None:
    validate_site_discovery_report(report, authorization=authorization, **_trusted_kwargs())


def _validate_lock(lock: dict, authorization: dict, report: dict) -> None:
    validate_execution_lock(
        lock,
        authorization=authorization,
        site_discovery_report=report,
        expected_prospective_contract=PROSPECTIVE_HASHES,
        **_trusted_kwargs(),
    )


class ExecutionBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.discovery_schema = json.loads(
            (SCHEMA_ROOT / "discovery_authorization.schema.json").read_text(encoding="utf-8")
        )
        cls.report_schema = json.loads(
            (SCHEMA_ROOT / "site_discovery_report.schema.json").read_text(encoding="utf-8")
        )
        cls.execution_schema = json.loads(
            (SCHEMA_ROOT / "execution_lock.schema.json").read_text(encoding="utf-8")
        )
        for schema in (cls.discovery_schema, cls.report_schema, cls.execution_schema):
            validator_for(schema).check_schema(schema)

    def test_unassigned_templates_are_schema_valid_and_fail_closed(self) -> None:
        discovery = json.loads(
            (PROTOCOL_ROOT / "discovery_authorization.json").read_text(encoding="utf-8")
        )
        execution = json.loads((PROTOCOL_ROOT / "execution_lock.json").read_text(encoding="utf-8"))
        validator_for(self.discovery_schema)(self.discovery_schema).validate(discovery)
        validator_for(self.execution_schema)(self.execution_schema).validate(execution)
        validate_discovery_authorization_template(
            discovery,
            expected_parent_design_manifest_sha256=discovery["parent_design_manifest_sha256"],
        )
        validate_execution_lock_template(
            execution,
            expected_parent_design_manifest_sha256=execution["parent_design_manifest_sha256"],
        )

        assigned = copy.deepcopy(discovery)
        assigned["model_registry"] = [{}]
        with self.assertRaises(ValidationError):
            validator_for(self.discovery_schema)(self.discovery_schema).validate(assigned)
        with self.assertRaisesRegex(ExecutionContractError, "assigned arrays"):
            validate_discovery_authorization_template(
                assigned,
                expected_parent_design_manifest_sha256=assigned["parent_design_manifest_sha256"],
            )

    def test_authorization_report_and_lock_happy_path(self) -> None:
        authorization = _authorization()
        report = _report(authorization)
        lock = _execution_lock(authorization, report)

        validator_for(self.discovery_schema)(self.discovery_schema).validate(authorization)
        validator_for(self.report_schema)(self.report_schema).validate(report)
        validator_for(self.execution_schema)(self.execution_schema).validate(lock)
        validate_discovery_authorization(authorization, **_trusted_kwargs())
        validate_discovery_readiness(
            authorization, authority_secret=AUTHORITY_SECRET, **_trusted_kwargs()
        )
        _validate_report(report, authorization)
        _validate_lock(lock, authorization, report)

        plan = lock["query_plan"]
        validate_post_discovery_query_ledger(
            {
                "causal_label_forward_passes": plan["planned_causal_label_forward_passes"],
                "behavior_fit_forward_passes": plan["planned_behavior_fit_forward_passes"],
                "sealed_test_forward_passes": plan["planned_sealed_test_forward_passes"],
                "diagnostic_forward_passes": plan["planned_diagnostic_forward_passes"],
                "total_forward_passes": plan["planned_total_forward_passes"],
                "wall_clock_seconds": 200.0,
            },
            execution_lock=lock,
        )

    def test_report_is_evidence_closed_and_rejects_forgery(self) -> None:
        authorization = _authorization()
        report = _report(authorization)

        zero_usage = copy.deepcopy(report)
        for field in zero_usage["query_usage"]:
            zero_usage["query_usage"][field] = 0
        with self.assertRaisesRegex(ExecutionContractError, "exactly equal"):
            _validate_report(zero_usage, authorization)

        missing_candidate = copy.deepcopy(report)
        missing_candidate["candidate_evidence"].pop()
        with self.assertRaisesRegex(ExecutionContractError, "retain every authorized"):
            _validate_report(missing_candidate, authorization)

        arbitrary_candidate = copy.deepcopy(report)
        arbitrary_candidate["candidate_evidence"][0]["canonical_site_id"] = "invented.site"
        with self.assertRaisesRegex(ExecutionContractError, "unauthorized site"):
            _validate_report(arbitrary_candidate, authorization)

        forged_score = copy.deepcopy(report)
        forged_score["candidate_evidence"][0]["specific_score"] = 0.25
        with self.assertRaisesRegex(ExecutionContractError, "specific_score must equal"):
            _validate_report(forged_score, authorization)

        forged_argmax = copy.deepcopy(report)
        forged_argmax["selected_sites"][0]["selected_site_id"] = forged_argmax["selected_sites"][0][
            "runner_up_site_id"
        ]
        with self.assertRaisesRegex(ExecutionContractError, "argmax"):
            _validate_report(forged_argmax, authorization)

    def test_raw_output_success_and_runtime_ledger_are_not_relabelable(self) -> None:
        authorization = _authorization()
        report = _report(authorization)
        condition = report["candidate_trial_evidence"][0]["trial_order"][0]

        original_output = condition["output_text"]
        condition["output_text"] = _opposite_final(original_output)
        with self.assertRaisesRegex(ExecutionContractError, "output hash"):
            _validate_report(report, authorization)
        condition["output_text"] = original_output

        condition["success"] = not condition["success"]
        with self.assertRaisesRegex(ExecutionContractError, "success was not derived"):
            _validate_report(report, authorization)
        condition["success"] = not condition["success"]

        operation = condition["intervention_execution_record"]
        ledger = operation["runtime_ledger_entry"]
        ledger["hook_call_count"] = 2
        operation["runtime_ledger_entry_sha256"] = canonical_artifact_sha256(ledger)
        condition["intervention_execution_record_sha256"] = canonical_artifact_sha256(operation)
        with self.assertRaisesRegex(ExecutionContractError, "exact hook operation"):
            _validate_report(report, authorization)

    def test_complete_layer_inventory_and_carrier_rows_fail_closed(self) -> None:
        subset = _authorization()
        subset["candidate_site_inventory"][0]["candidates"].pop()
        subset["candidate_site_set_sha256"] = canonical_artifact_sha256(
            {"candidate_site_inventory": subset["candidate_site_inventory"]}
        )
        with self.assertRaisesRegex(ExecutionContractError, "every transformer block"):
            validate_discovery_authorization(subset, **_trusted_kwargs())

        gap = _authorization()
        hook = gap["activation_hook_registry"]["records"][0]
        hook["layer_module_inventory"][1]["zero_based_layer_index"] = 3
        hook["layer_module_inventory_sha256"] = canonical_artifact_sha256(
            {"layer_module_inventory": hook["layer_module_inventory"]}
        )
        with self.assertRaisesRegex(ExecutionContractError, "contiguous and ordered"):
            validate_discovery_authorization(gap, **_trusted_kwargs())

        carrier = _authorization()
        carrier["carrier_binding_records"][0]["ambiguous"] = True
        carrier["carrier_binding_report_sha256"] = canonical_artifact_sha256(
            {
                "scheme": execution.CARRIER_BINDING_REPORT_SCHEME,
                "records": carrier["carrier_binding_records"],
            }
        )
        with self.assertRaisesRegex(ExecutionContractError, "missing, ambiguous, or truncated"):
            validate_discovery_authorization(carrier, **_trusted_kwargs())

    def test_learned_state_identity_leaks_are_rejected(self) -> None:
        duplicate_artifact = _authorization()
        duplicate_artifact["model_registry"][1]["model_artifact_sha256"] = duplicate_artifact[
            "model_registry"
        ][0]["model_artifact_sha256"]
        with self.assertRaisesRegex(ExecutionContractError, "duplicate model_artifact_sha256"):
            validate_discovery_authorization(duplicate_artifact, **_trusted_kwargs())

        duplicate_checkpoint = _authorization()
        duplicate_checkpoint["model_registry"][1]["checkpoint_id"] = duplicate_checkpoint[
            "model_registry"
        ][0]["checkpoint_id"]
        with self.assertRaisesRegex(ExecutionContractError, "duplicate checkpoint_id"):
            validate_discovery_authorization(duplicate_checkpoint, **_trusted_kwargs())

        cross_cluster_lineage = _authorization()
        cross_cluster_lineage["model_registry"][3]["lineage_id"] = cross_cluster_lineage[
            "model_registry"
        ][0]["lineage_id"]
        with self.assertRaisesRegex(ExecutionContractError, "lineage_id crosses"):
            validate_discovery_authorization(cross_cluster_lineage, **_trusted_kwargs())

        omitted_parent = _authorization()
        omitted_parent["learned_state_ancestry"]["records"][0]["parents"] = []
        body = {
            field: omitted_parent["learned_state_ancestry"][field]
            for field in ("policy_id", "external_artifacts", "records")
        }
        omitted_parent["learned_state_ancestry"]["inventory_sha256"] = canonical_artifact_sha256(
            body
        )
        with self.assertRaisesRegex(ExecutionContractError, "declare learned-state parentage"):
            validate_discovery_authorization(omitted_parent, **_trusted_kwargs())

    def test_cluster_confound_and_anchor_provenance_are_rejected(self) -> None:
        family_drift = _authorization()
        family_drift["model_registry"][0]["architecture_family_id"] = "family-b"
        with self.assertRaisesRegex(ExecutionContractError, "share architecture_family_id"):
            validate_discovery_authorization(family_drift, **_trusted_kwargs())

        tokenizer_drift = _authorization()
        tokenizer_drift["model_registry"][0]["tokenizer_revision"] = "drifted-tokenizer"
        tokenizer_drift["tokenizer_compatibility"]["records"][0]["tokenizer_revision"] = (
            "drifted-tokenizer"
        )
        with self.assertRaisesRegex(ExecutionContractError, "share tokenizer identity"):
            validate_discovery_authorization(tokenizer_drift, **_trusted_kwargs())

        posthoc_anchor = _authorization()
        posthoc_anchor["model_registry"][0]["anchor_provenance"]["assignment_timing"] = (
            "post_outcome_selection"
        )
        with self.assertRaisesRegex(ExecutionContractError, "pre-outcome"):
            validate_discovery_authorization(posthoc_anchor, **_trusted_kwargs())

        base_crossing = _authorization()
        for model in base_crossing["model_registry"][3:6]:
            model["shared_base_artifact_sha256"] = base_crossing["model_registry"][0][
                "shared_base_artifact_sha256"
            ]
        with self.assertRaisesRegex(ExecutionContractError, "bind its registry shared_base"):
            validate_discovery_authorization(base_crossing, **_trusted_kwargs())

        imbalanced = _authorization()
        imbalanced["model_registry"][0]["anchor_condition_id"] = "semantic_anchor"
        with self.assertRaisesRegex(ExecutionContractError, "exactly one semantic_anchor"):
            validate_discovery_authorization(imbalanced, **_trusted_kwargs())

    def test_trusted_roots_and_prospective_hashes_are_mandatory(self) -> None:
        authorization = _authorization()
        with self.assertRaisesRegex(ExecutionContractError, "all-zero sentinel"):
            validate_discovery_authorization(
                authorization,
                expected_parent_design_manifest_sha256="0" * 64,
                expected_parent_discovery_template_sha256=DISCOVERY_TEMPLATE_HASH,
                expected_parent_execution_template_sha256=EXECUTION_TEMPLATE_HASH,
            )

        report = _report(authorization)
        lock = _execution_lock(authorization, report)
        zero_contract = copy.deepcopy(PROSPECTIVE_HASHES)
        zero_contract["scoring_source_sha256"] = "0" * 64
        lock["prospective_contract"] = copy.deepcopy(zero_contract)
        with self.assertRaisesRegex(ExecutionContractError, "all-zero sentinel"):
            validate_execution_lock(
                lock,
                authorization=authorization,
                site_discovery_report=report,
                expected_prospective_contract=zero_contract,
                **_trusted_kwargs(),
            )

        premature = _execution_lock(authorization, report)
        premature["authority_commitments"] = {
            "scheme": "sha256_domain_separated_u64be_length_prefixed_v1",
            "evaluation_key_commitment": _hash("premature-evaluation-key"),
            "challenge_bundle_commitment": _hash("premature-challenge-bundle"),
        }
        with self.assertRaisesRegex(ExecutionContractError, "must leave.*pending"):
            _validate_lock(premature, authorization, report)

    def test_decoding_runtime_and_final_query_plan_fail_closed(self) -> None:
        decoding = _authorization()
        decoding["discovery_decoding_config"]["records"][0]["do_sample"] = True
        with self.assertRaisesRegex(ExecutionContractError, "do_sample=false"):
            validate_discovery_authorization(decoding, **_trusted_kwargs())

        truncation = _authorization()
        truncation["discovery_decoding_config"]["records"][0]["max_new_tokens"] = 1
        with self.assertRaisesRegex(ExecutionContractError, "must equal.*16"):
            validate_discovery_authorization(truncation, **_trusted_kwargs())

        stop_string = _authorization()
        stop_string["discovery_decoding_config"]["records"][0]["stop_strings"] = ["FINAL:"]
        with self.assertRaisesRegex(ExecutionContractError, "stop_strings must be empty"):
            validate_discovery_authorization(stop_string, **_trusted_kwargs())

        eos_collision = _authorization()
        continuation = eos_collision["tokenizer_compatibility"]["records"][0][
            "final_a_continuation_token_id"
        ]
        eos_collision["discovery_decoding_config"]["records"][0]["eos_token_ids"] = [continuation]
        with self.assertRaisesRegex(ExecutionContractError, "must not alias"):
            validate_discovery_authorization(eos_collision, **_trusted_kwargs())

        runtime = _authorization()
        runtime["model_runtime_configuration"]["records"][0]["trust_remote_code"] = True
        with self.assertRaisesRegex(ExecutionContractError, "unsafe"):
            validate_discovery_authorization(runtime, **_trusted_kwargs())

        authorization = _authorization()
        report = _report(authorization)
        lock = _execution_lock(authorization, report)
        lock["query_plan"]["planned_behavior_fit_forward_passes"] = 0
        lock["query_plan"]["behavior_fit_prompt_count"] = 0
        lock["query_plan"]["planned_total_forward_passes"] = 45
        with self.assertRaisesRegex(ExecutionContractError, "positive integer"):
            _validate_lock(lock, authorization, report)

        lock = _execution_lock(authorization, report)
        lock["post_discovery_decoding_config"]["records"][0]["replicates_per_prompt"] = 2
        with self.assertRaisesRegex(ExecutionContractError, "one replicate"):
            _validate_lock(lock, authorization, report)

    def test_carrier_binding_and_actual_query_ledger_fail_closed(self) -> None:
        authorization = _authorization()
        authorization["carrier_binding_summary"]["ambiguous_count"] = 1
        with self.assertRaisesRegex(ExecutionContractError, "complete, unambiguous"):
            validate_discovery_authorization(authorization, **_trusted_kwargs())

        authorization = _authorization()
        report = _report(authorization)
        lock = _execution_lock(authorization, report)
        aliased_binding = copy.deepcopy(lock)
        aliased_binding["post_discovery_carrier_binding_report_sha256"] = authorization[
            "carrier_binding_report_sha256"
        ]
        with self.assertRaisesRegex(ExecutionContractError, "must be distinct"):
            _validate_lock(aliased_binding, authorization, report)

        with self.assertRaisesRegex(ExecutionContractError, "exactly equal"):
            validate_post_discovery_query_ledger(
                {
                    "causal_label_forward_passes": 26,
                    "behavior_fit_forward_passes": 18,
                    "sealed_test_forward_passes": 18,
                    "diagnostic_forward_passes": 0,
                    "total_forward_passes": 62,
                    "wall_clock_seconds": 200.0,
                },
                execution_lock=lock,
            )


if __name__ == "__main__":
    unittest.main()
