from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from jsonschema import ValidationError
from jsonschema.validators import validator_for

from latent_trace_tomography.causal_profile import (
    CausalProfileError,
    _expected_profile_stability_from_report,
    delete_one_jackknife_interval,
    validate_causal_profile_against_artifact_hashes_non_authoritative,
    validate_causal_profile as validate_causal_profile_against_execution,
    validate_causal_profile_record_non_authoritative as validate_causal_profile,
)
from latent_trace_tomography.execution import (
    canonical_artifact_sha256,
    derive_matched_null_seed,
    derive_intervention_trial_condition_order,
    matched_null_permutation_and_signs,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DELETE_ONE_COUNT = 16
STABILITY_RESAMPLE_COUNT = 8


def _partition_count(total: int, group_count: int) -> list[int]:
    quotient, remainder = divmod(total, group_count)
    return [quotient + int(index < remainder) for index in range(group_count)]


def _recompute_delete_one_record(record: dict) -> None:
    record["intended_iia"] = record["intended_success_count"] / record["trial_count"]
    record["matched_null_iia"] = record["matched_null_success_count"] / record["trial_count"]
    record["specific_iia"] = record["intended_iia"] - record["matched_null_iia"]


def _effect(
    intended_successes: int,
    matched_successes: int,
    trial_count: int = 64,
    *,
    self_sham_successes: int = 58,
    control_site_successes: int | None = None,
) -> dict:
    intended = intended_successes / trial_count
    matched = matched_successes / trial_count
    specific = intended - matched
    control_successes = (
        matched_successes if control_site_successes is None else control_site_successes
    )
    control_iia = control_successes / trial_count
    seed_trial_counts = _partition_count(trial_count, DELETE_ONE_COUNT)
    seed_intended_counts = _partition_count(intended_successes, DELETE_ONE_COUNT)
    seed_matched_counts = _partition_count(matched_successes, DELETE_ONE_COUNT)
    delete_one_records = []
    for index in range(DELETE_ONE_COUNT):
        delete_one_record = {
            "omitted_content_seed_id": f"content-seed-{index:02d}",
            "intended_success_count": intended_successes - seed_intended_counts[index],
            "matched_null_success_count": matched_successes - seed_matched_counts[index],
            "trial_count": trial_count - seed_trial_counts[index],
        }
        _recompute_delete_one_record(delete_one_record)
        delete_one_records.append(delete_one_record)
    lower, upper = delete_one_jackknife_interval(
        specific,
        tuple(item["specific_iia"] for item in delete_one_records),
        lower_bound=-1,
        upper_bound=1,
    )
    return {
        "intended_success_count": intended_successes,
        "matched_null_success_count": matched_successes,
        "intended_iia": intended,
        "matched_null_iia": matched,
        "matched_null_kind": "norm_matched_rotation",
        "specific_iia": specific,
        "specificity_controls": {
            "self_sham": {
                "success_count": self_sham_successes,
                "trial_count": trial_count,
                "accuracy": self_sham_successes / trial_count,
            },
            "control_site_delta": {
                "success_count": control_successes,
                "trial_count": trial_count,
                "iia": control_iia,
                "specific_vs_matched_null": control_iia - matched,
            },
        },
        "delete_one_records": delete_one_records,
        "ci95_lower": lower,
        "ci95_upper": upper,
        "trial_count": trial_count,
    }


def _site_component(layer: int, frequency: float, gap: float) -> dict:
    selected_site_id = f"residual_stream_post.layer_{layer}.carrier"
    alternate_site_id = f"residual_stream_post.layer_{layer + 1}.alternate"
    selected_count = round(frequency * STABILITY_RESAMPLE_COUNT)
    selected_sites = [selected_site_id] * selected_count + [alternate_site_id] * (
        STABILITY_RESAMPLE_COUNT - selected_count
    )
    histogram = [{"site_id": selected_site_id, "count": selected_count}]
    if selected_count < STABILITY_RESAMPLE_COUNT:
        histogram.append(
            {
                "site_id": alternate_site_id,
                "count": STABILITY_RESAMPLE_COUNT - selected_count,
            }
        )
    return {
        "selected_site_id": selected_site_id,
        "candidate_site_count": 24,
        "selection_frequency": frequency,
        "score_gap_to_runner_up": gap,
        "leave_one_selections": [
            {
                "omitted_content_seed_id": f"discovery-seed-{index:02d}",
                "selected_site_id": site_id,
            }
            for index, site_id in enumerate(selected_sites)
        ],
        "selection_histogram": histogram,
    }


def _set_site_selection_count(component: dict, selected_count: int) -> None:
    selected_site_id = component["selected_site_id"]
    alternate_site_id = f"{selected_site_id}.alternate"
    for index, selection in enumerate(component["leave_one_selections"]):
        selection["selected_site_id"] = (
            selected_site_id if index < selected_count else alternate_site_id
        )
    component["selection_histogram"] = [
        {"site_id": selected_site_id, "count": selected_count},
        {
            "site_id": alternate_site_id,
            "count": STABILITY_RESAMPLE_COUNT - selected_count,
        },
    ]
    component["selection_frequency"] = selected_count / STABILITY_RESAMPLE_COUNT


def _gate_evaluation(record: dict) -> dict:
    required_routes = {
        "semantic_anchor": ["semantic_solution"],
        "surface_cue_anchor": ["surface_cue"],
        "mixed_anchor": ["semantic_solution", "surface_cue"],
    }[record["anchor_condition_id"]]
    component_gates = {}
    for variable, effect in record["profile"].items():
        route_required = variable in required_routes
        trial_count = effect["trial_count"]
        specific_iia_pass = (
            4 * (effect["intended_success_count"] - effect["matched_null_success_count"])
            >= trial_count
        )
        self_sham_pass = (
            10 * effect["specificity_controls"]["self_sham"]["success_count"] >= 9 * trial_count
        )
        control_site_pass = (
            10
            * abs(
                effect["specificity_controls"]["control_site_delta"]["success_count"]
                - effect["matched_null_success_count"]
            )
            <= trial_count
        )
        stability_component = record["site_selection_stability"]["components"][variable]
        selected_count = next(
            item["count"]
            for item in stability_component["selection_histogram"]
            if item["site_id"] == stability_component["selected_site_id"]
        )
        site_stability_pass = selected_count * 4 >= 3 * STABILITY_RESAMPLE_COUNT
        component_gates[variable] = {
            "route_required": route_required,
            "specific_iia_pass": specific_iia_pass,
            "self_sham_pass": self_sham_pass,
            "control_site_pass": control_site_pass,
            "site_stability_pass": site_stability_pass,
            "component_pass": (
                (not route_required or specific_iia_pass)
                and self_sham_pass
                and control_site_pass
                and site_stability_pass
            ),
        }
    route_pass = all(component_gates[variable]["specific_iia_pass"] for variable in required_routes)
    controls_pass = all(
        component_gates[variable]["self_sham_pass"]
        and component_gates[variable]["control_site_pass"]
        for variable in component_gates
    )
    codebook_pass = (
        10 * record["codebook_competence"]["success_count"]
        >= 9 * record["codebook_competence"]["trial_count"]
    )
    site_pass = all(
        component_gates[variable]["site_stability_pass"] for variable in component_gates
    )
    overall_pass = route_pass and controls_pass and codebook_pass and site_pass
    return {
        "thresholds": {
            "minimum_route_specific_iia": 0.25,
            "minimum_self_sham_accuracy": 0.90,
            "maximum_absolute_control_site_specific": 0.10,
            "minimum_codebook_competence_accuracy": 0.90,
            "minimum_site_selection_frequency": 0.75,
        },
        "required_route_components": required_routes,
        "components": component_gates,
        "route_specificity_pass": route_pass,
        "specificity_controls_pass": controls_pass,
        "codebook_competence_pass": codebook_pass,
        "site_selection_stability_pass": site_pass,
        "overall_pass": overall_pass,
        "overall_status": "pass" if overall_pass else "fail",
        "anchor_eligibility": "resolved" if overall_pass else "unresolved",
    }


def _refresh_gate(record: dict) -> None:
    record["gate_evaluation"] = _gate_evaluation(record)


def _refresh_delta(record: dict) -> None:
    semantic = record["profile"]["semantic_solution"]
    surface_cue = record["profile"]["surface_cue"]
    semantic_delete_one = {
        item["omitted_content_seed_id"]: item["specific_iia"]
        for item in semantic["delete_one_records"]
    }
    surface_delete_one = {
        item["omitted_content_seed_id"]: item["specific_iia"]
        for item in surface_cue["delete_one_records"]
    }
    delete_one_records = [
        {
            "omitted_content_seed_id": omitted_id,
            "value": semantic_value - surface_delete_one[omitted_id],
        }
        for omitted_id, semantic_value in semantic_delete_one.items()
    ]
    value = semantic["specific_iia"] - surface_cue["specific_iia"]
    lower, upper = delete_one_jackknife_interval(
        value,
        tuple(item["value"] for item in delete_one_records),
        lower_bound=-2,
        upper_bound=2,
    )
    record["delta_specific"] = {
        "value": value,
        "delete_one_records": delete_one_records,
        "ci95_lower": lower,
        "ci95_upper": upper,
    }


def _refresh_effect_interval(effect: dict) -> None:
    lower, upper = delete_one_jackknife_interval(
        effect["specific_iia"],
        tuple(item["specific_iia"] for item in effect["delete_one_records"]),
        lower_bound=-1,
        upper_bound=1,
    )
    effect["ci95_lower"] = lower
    effect["ci95_upper"] = upper


def _valid_profile() -> dict:
    digest = "a" * 64
    semantic = _effect(54, 6, control_site_successes=12)
    surface_cue = _effect(32, 16, control_site_successes=22)
    answer_codebook = _effect(16, 8, control_site_successes=14)
    semantic_delete_one = {
        item["omitted_content_seed_id"]: item["specific_iia"]
        for item in semantic["delete_one_records"]
    }
    surface_delete_one = {
        item["omitted_content_seed_id"]: item["specific_iia"]
        for item in surface_cue["delete_one_records"]
    }
    delta_delete_one_records = [
        {
            "omitted_content_seed_id": omitted_id,
            "value": semantic_value - surface_delete_one[omitted_id],
        }
        for omitted_id, semantic_value in semantic_delete_one.items()
    ]
    delta_value = semantic["specific_iia"] - surface_cue["specific_iia"]
    delta_lower, delta_upper = delete_one_jackknife_interval(
        delta_value,
        tuple(item["value"] for item in delta_delete_one_records),
        lower_bound=-2,
        upper_bound=2,
    )
    record = {
        "schema_version": "0.1.0",
        "estimand_kind": "selected_site_intervention_susceptibility",
        "claim_tier": "named_dependency_cluster_engineering_pilot",
        "target_id": "target-001",
        "family_id": "descriptive-family-a",
        "dependency_cluster_id": "dependency-0000000000000001",
        "training_lineage_id": "training-run-001",
        "checkpoint_id": "checkpoint-001",
        "anchor_condition_id": "mixed_anchor",
        "profile": {
            "semantic_solution": semantic,
            "surface_cue": surface_cue,
            "answer_codebook": answer_codebook,
        },
        "delta_specific": {
            "value": delta_value,
            "delete_one_records": delta_delete_one_records,
            "ci95_lower": delta_lower,
            "ci95_upper": delta_upper,
        },
        "codebook_competence": {
            "success_count": 116,
            "trial_count": 128,
            "accuracy": 116 / 128,
            "causal_label_case_set_sha256": "e" * 64,
        },
        "probability_status": "not_calibrated",
        "uncertainty_scope": {
            "interval_scope": "within_target_measurement_precision",
            "interval_method": "content_seed_delete_one_jackknife_normal_95_v1",
            "primary_independent_unit": "dependency_cluster_id",
            "population_inference": False,
        },
        "site_selection_stability": {
            "method": "leave_one_content_seed_out_site_rediscovery_v1",
            "resample_count": 8,
            "stability_threshold": 0.75,
            "overall_status": "stable",
            "components": {
                "semantic_solution": _site_component(11, 0.875, 0.14),
                "surface_cue": _site_component(7, 0.75, 0.09),
                "answer_codebook": _site_component(15, 0.875, 0.11),
            },
        },
        "provenance": {
            "execution_lock_sha256": digest,
            "site_discovery_report_sha256": "b" * 64,
            "causal_label_evidence_sha256": "c" * 64,
            "evaluation_pair_set_sha256": "d" * 64,
        },
    }
    _refresh_gate(record)
    return record


def _causal_execution_record(
    *,
    lock: dict,
    target_id: str,
    variable: str,
    candidate: dict,
    pair: dict,
    condition_id: str,
    order_index: int,
    base_capture_sha256: str,
    source_capture_sha256: str,
    base_binding: dict,
    source_binding: dict,
    output_text_sha256: str,
) -> dict:
    effective_source_is_base = condition_id == "self_sham"
    effective_prompt_id = (
        pair["base_prompt_id"] if effective_source_is_base else pair["source_prompt_id"]
    )
    effective_prompt_sha256 = (
        pair["base_prompt_sha256"] if effective_source_is_base else pair["source_prompt_sha256"]
    )
    effective_capture_sha256 = (
        base_capture_sha256 if effective_source_is_base else source_capture_sha256
    )
    effective_binding = base_binding if effective_source_is_base else source_binding
    patched_position_indices = (
        base_binding["control_position_indices"]
        if condition_id == "control_site_delta"
        else base_binding["carrier_position_indices"]
    )
    if condition_id == "norm_matched_rotation":
        matched_seed = derive_matched_null_seed(
            lock["discovery_authorization_id"],
            pair["pair_id"],
            candidate["canonical_site_id"],
        )
        permutation, signs = matched_null_permutation_and_signs(
            matched_seed, candidate["hidden_size"]
        )
        matched_permutation_sha256 = canonical_artifact_sha256({"permutation": list(permutation)})
        matched_signs_sha256 = canonical_artifact_sha256({"signs": list(signs)})
    else:
        matched_seed = None
        matched_permutation_sha256 = None
        matched_signs_sha256 = None

    tensor_prefix = (
        f"causal-tensor:{target_id}:{variable}:{pair['pair_id']}:{candidate['canonical_site_id']}"
    )
    base_tensor_sha256 = hashlib.sha256(f"{tensor_prefix}:base".encode()).hexdigest()
    if condition_id == "self_sham":
        source_tensor_sha256 = base_tensor_sha256
        patched_tensor_sha256 = base_tensor_sha256
    else:
        source_tensor_sha256 = hashlib.sha256(f"{tensor_prefix}:source".encode()).hexdigest()
        patched_tensor_sha256 = (
            source_tensor_sha256
            if condition_id in {"targeted_interchange", "control_site_delta"}
            else hashlib.sha256(f"{tensor_prefix}:matched-patched".encode()).hexdigest()
        )
    delta_tensor_sha256 = hashlib.sha256(
        f"{tensor_prefix}:{condition_id}:source-minus-base".encode()
    ).hexdigest()
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
    runtime = next(
        item
        for item in lock["model_runtime_configuration"]["records"]
        if item["model_unit_id"] == target_id
    )
    hook = next(
        item
        for item in lock["activation_hook_registry"]["records"]
        if item["architecture_family_id"] == candidate["architecture_family_id"]
    )
    ledger = {
        "ledger_version": "trusted_authority_runtime_ledger_v1",
        "discovery_authorization_id": lock["discovery_authorization_id"],
        "partition_id": "D_causal_label",
        "model_unit_id": target_id,
        "pair_id": pair["pair_id"],
        "canonical_site_id": candidate["canonical_site_id"],
        "operation_id": condition_id,
        "order_index": order_index,
        "hook_adapter_id": hook["hook_adapter_id"],
        "module_path": candidate["module_path"],
        "zero_based_layer_index": candidate["zero_based_layer_index"],
        "patched_position_indices": patched_position_indices,
        "base_tensor_role": operation_contract[0],
        "source_tensor_role": operation_contract[1],
        "base_activation_tensor_sha256": base_tensor_sha256,
        "source_activation_tensor_sha256": source_tensor_sha256,
        "source_minus_base_delta_tensor_sha256": delta_tensor_sha256,
        "patched_activation_tensor_sha256": patched_tensor_sha256,
        "patch_operator_id": operation_contract[2],
        "runtime_dtype": runtime["dtype"],
        "source_tree_sha256": lock["environment_lock"]["source_tree_sha256"],
        "environment_lock_sha256": canonical_artifact_sha256(lock["environment_lock"]),
        "hook_call_count": 1,
        "competing_hook_count": 0,
        "relation_check_id": operation_contract[3],
        "relation_check_passed": True,
        "output_text_sha256": output_text_sha256,
    }
    return {
        "record_version": "intervention_execution_record_v1",
        "partition_id": "D_causal_label",
        "operation_id": condition_id,
        "order_index": order_index,
        "model_unit_id": target_id,
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
        "effective_source_prompt_sha256": effective_prompt_sha256,
        "base_activation_capture_record_sha256": base_capture_sha256,
        "effective_source_activation_capture_record_sha256": (effective_capture_sha256),
        "base_carrier_binding_record_sha256": canonical_artifact_sha256(base_binding),
        "effective_source_carrier_binding_record_sha256": canonical_artifact_sha256(
            effective_binding
        ),
        "patched_position_indices": patched_position_indices,
        "matched_null_seed_u64": matched_seed,
        "matched_null_permutation_sha256": matched_permutation_sha256,
        "matched_null_signs_sha256": matched_signs_sha256,
        "base_activation_tensor_sha256": base_tensor_sha256,
        "source_activation_tensor_sha256": source_tensor_sha256,
        "source_minus_base_delta_tensor_sha256": delta_tensor_sha256,
        "patched_activation_tensor_sha256": patched_tensor_sha256,
        "output_text_sha256": output_text_sha256,
        "runtime_ledger_entry": ledger,
        "runtime_ledger_entry_sha256": canonical_artifact_sha256(ledger),
    }


def _authoritative_fixture() -> tuple[dict, dict]:
    from test_execution_contract import (
        AUTHORITY_SECRET,
        PROSPECTIVE_HASHES,
        _authorization,
        _execution_lock,
        _report,
        _trusted_kwargs,
    )

    authorization = _authorization()
    report = _report(authorization)
    lock = _execution_lock(authorization, report)
    target = authorization["model_registry"][0]
    target_id = target["model_unit_id"]
    causal_partition = next(
        item
        for item in lock["live_material_manifest"]["partition_records"]
        if item["partition_id"] == "D_causal_label"
    )
    selected_sites = {
        row["causal_variable"]: row["selected_site_id"]
        for row in report["selected_sites"]
        if row["model_unit_id"] == target_id
    }
    selected_candidates = {
        panel["causal_variable"]: next(
            candidate
            for candidate in panel["candidates"]
            if candidate["canonical_site_id"] == selected_sites[panel["causal_variable"]]
        )
        for panel in lock["candidate_site_inventory"]
        if panel["model_unit_id"] == target_id
    }
    carrier_bindings = {
        (record["prompt_id"], record["causal_variable"]): record
        for record in lock["post_discovery_carrier_binding_records"]
        if record["model_unit_id"] == target_id
    }
    unpatched_trials = []
    captures_by_prompt_id = {}
    for prompt in causal_partition["intervention_prompt_inventory"]:
        output_text = prompt["oracle_final"]
        output_text_sha256 = hashlib.sha256(output_text.encode()).hexdigest()
        capture_sha256 = hashlib.sha256(
            f"causal-capture:{target_id}:{prompt['prompt_id']}".encode()
        ).hexdigest()
        captures_by_prompt_id[prompt["prompt_id"]] = capture_sha256
        unpatched_trials.append(
            {
                "prompt_id": prompt["prompt_id"],
                "case_id": prompt["case_id"],
                "prompt_sha256": prompt["prompt_sha256"],
                "prompt_record_sha256": prompt["prompt_record_sha256"],
                "oracle_final": prompt["oracle_final"],
                "output_text": output_text,
                "output_text_sha256": output_text_sha256,
                "parsed_final": output_text[-1],
                "oracle_correct": True,
                "activation_capture_record_sha256": capture_sha256,
            }
        )
    evidence = {
        "schema_version": "0.1.0",
        "status": "complete",
        "execution_lock_sha256": canonical_artifact_sha256(lock),
        "target_id": target_id,
        "unpatched_trials": unpatched_trials,
        "intervention_trials": [],
    }
    for pair in causal_partition["primary_pair_inventory"]:
        variable = pair["causal_variable"]
        condition_order = derive_intervention_trial_condition_order(
            partition_id="D_causal_label",
            split_manifest_sha256=lock["split_manifest_sha256"],
            model_unit_id=target_id,
            causal_variable=variable,
            canonical_site_id=selected_sites[variable],
            pair_id=pair["pair_id"],
        )
        base_capture_sha256 = captures_by_prompt_id[pair["base_prompt_id"]]
        source_capture_sha256 = captures_by_prompt_id[pair["source_prompt_id"]]
        base_binding = carrier_bindings[(pair["base_prompt_id"], variable)]
        source_binding = carrier_bindings[(pair["source_prompt_id"], variable)]
        condition_rows = []
        for index, condition_id in enumerate(condition_order):
            output_text = (
                pair["base_oracle_final"]
                if condition_id == "self_sham"
                else pair["expected_patched_final"]
            )
            output_text_sha256 = hashlib.sha256(output_text.encode()).hexdigest()
            execution_record = _causal_execution_record(
                lock=lock,
                target_id=target_id,
                variable=variable,
                candidate=selected_candidates[variable],
                pair=pair,
                condition_id=condition_id,
                order_index=index,
                base_capture_sha256=base_capture_sha256,
                source_capture_sha256=source_capture_sha256,
                base_binding=base_binding,
                source_binding=source_binding,
                output_text_sha256=output_text_sha256,
            )
            condition_rows.append(
                {
                    "condition_id": condition_id,
                    "order_index": index,
                    "output_text": output_text,
                    "output_text_sha256": output_text_sha256,
                    "parsed_final": output_text[-1],
                    "success": True,
                    "intervention_execution_record": execution_record,
                    "intervention_execution_record_sha256": (
                        canonical_artifact_sha256(execution_record)
                    ),
                }
            )
        evidence["intervention_trials"].append(
            {
                **pair,
                "selected_site_id": selected_sites[variable],
                "base_activation_capture_record_sha256": base_capture_sha256,
                "source_activation_capture_record_sha256": source_capture_sha256,
                "trial_order": condition_rows,
            }
        )

    profile = _valid_profile()
    profile.update(
        {
            "target_id": target_id,
            "family_id": target["architecture_family_id"],
            "dependency_cluster_id": target["dependency_cluster_id"],
            "training_lineage_id": target["lineage_id"],
            "checkpoint_id": target["checkpoint_id"],
            "anchor_condition_id": target["anchor_condition_id"],
            "profile": {
                variable: _effect(
                    64,
                    64,
                    self_sham_successes=64,
                    control_site_successes=64,
                )
                for variable in ("semantic_solution", "surface_cue", "answer_codebook")
            },
            "codebook_competence": {
                "success_count": 128,
                "trial_count": 128,
                "accuracy": 1.0,
                "causal_label_case_set_sha256": causal_partition["case_set_sha256"],
            },
            "site_selection_stability": _expected_profile_stability_from_report(
                report=report,
                target_id=target_id,
            ),
        }
    )
    for variable, effect in profile["profile"].items():
        seed_ids = sorted(
            {
                pair["opaque_content_seed_id"]
                for pair in causal_partition["primary_pair_inventory"]
                if pair["causal_variable"] == variable
            }
        )
        for delete_record, seed_id in zip(effect["delete_one_records"], seed_ids):
            delete_record["omitted_content_seed_id"] = seed_id
    _refresh_delta(profile)
    _refresh_gate(profile)
    profile["provenance"] = {
        "execution_lock_sha256": canonical_artifact_sha256(lock),
        "site_discovery_report_sha256": canonical_artifact_sha256(report),
        "causal_label_evidence_sha256": canonical_artifact_sha256(evidence),
        "evaluation_pair_set_sha256": causal_partition["primary_intervention_pair_set_sha256"],
    }
    kwargs = {
        "discovery_authorization": authorization,
        "execution_lock": lock,
        "site_discovery_report": report,
        "causal_label_evidence": evidence,
        "authority_secret": AUTHORITY_SECRET,
        "expected_prospective_contract": PROSPECTIVE_HASHES,
        **_trusted_kwargs(),
    }
    return profile, kwargs


class CausalProfileValidationTests(unittest.TestCase):
    def test_frozen_delete_one_jackknife_interval_is_executable(self) -> None:
        self.assertEqual(
            delete_one_jackknife_interval(
                0.4,
                (0.4,) * 16,
                lower_bound=-1.0,
                upper_bound=1.0,
            ),
            (0.4, 0.4),
        )
        lower, upper = delete_one_jackknife_interval(
            0.95,
            tuple(0.7 if index % 2 else 1.0 for index in range(16)),
            lower_bound=-1.0,
            upper_bound=1.0,
        )
        self.assertGreaterEqual(lower, -1.0)
        self.assertEqual(upper, 1.0)
        with self.assertRaisesRegex(ValueError, "exactly 16"):
            delete_one_jackknife_interval(
                0.4,
                (0.4,) * 15,
                lower_bound=-1.0,
                upper_bound=1.0,
            )

    def test_valid_selected_site_profile_passes_code_and_schema(self) -> None:
        profile = _valid_profile()

        self.assertEqual(validate_causal_profile(profile), profile)
        schema = json.loads(
            (REPO_ROOT / "schemas" / "causal_profile.schema.json").read_text(encoding="utf-8")
        )
        validator_class = validator_for(schema)
        validator_class.check_schema(schema)
        validator_class(schema).validate(profile)

    def test_aggregate_only_provenance_is_an_explicit_negative_control(self) -> None:
        with self.assertRaisesRegex(CausalProfileError, "aggregate-only provenance"):
            validate_causal_profile_against_artifact_hashes_non_authoritative(_valid_profile())

    def test_authoritative_entry_closes_execution_discovery_and_stability_ancestry(self) -> None:
        profile, kwargs = _authoritative_fixture()

        self.assertEqual(
            validate_causal_profile_against_execution(profile, **kwargs),
            profile,
        )

        evidence_schema = json.loads(
            (REPO_ROOT / "schemas" / "causal_label_evidence.schema.json").read_text(
                encoding="utf-8"
            )
        )
        validator_class = validator_for(evidence_schema)
        validator_class.check_schema(evidence_schema)
        validator_class(evidence_schema).validate(kwargs["causal_label_evidence"])

    def test_authoritative_entry_rejects_other_target_site_and_stability_substitution(self) -> None:
        profile, kwargs = _authoritative_fixture()

        fake_lock_kwargs = copy.deepcopy(kwargs)
        fake_lock_kwargs["execution_lock"]["status"] = "locked-but-fabricated"
        fake_lock_sha256 = canonical_artifact_sha256(fake_lock_kwargs["execution_lock"])
        fake_lock_profile = copy.deepcopy(profile)
        fake_lock_profile["provenance"]["execution_lock_sha256"] = fake_lock_sha256
        fake_lock_kwargs["causal_label_evidence"]["execution_lock_sha256"] = fake_lock_sha256
        fake_lock_profile["provenance"]["causal_label_evidence_sha256"] = canonical_artifact_sha256(
            fake_lock_kwargs["causal_label_evidence"]
        )
        with self.assertRaisesRegex(CausalProfileError, "structural validation"):
            validate_causal_profile_against_execution(fake_lock_profile, **fake_lock_kwargs)

        raw_substitution_kwargs = copy.deepcopy(kwargs)
        raw_substitution = raw_substitution_kwargs["causal_label_evidence"]
        first_trial = raw_substitution["intervention_trials"][0]
        targeted = next(
            item
            for item in first_trial["trial_order"]
            if item["condition_id"] == "targeted_interchange"
        )
        targeted["output_text"] = "unparseable output"
        targeted["output_text_sha256"] = hashlib.sha256(
            targeted["output_text"].encode()
        ).hexdigest()
        targeted["parsed_final"] = None
        targeted["success"] = False
        execution_record = targeted["intervention_execution_record"]
        execution_record["output_text_sha256"] = targeted["output_text_sha256"]
        execution_record["runtime_ledger_entry"]["output_text_sha256"] = targeted[
            "output_text_sha256"
        ]
        execution_record["runtime_ledger_entry_sha256"] = canonical_artifact_sha256(
            execution_record["runtime_ledger_entry"]
        )
        targeted["intervention_execution_record_sha256"] = canonical_artifact_sha256(
            execution_record
        )
        raw_substitution_profile = copy.deepcopy(profile)
        raw_substitution_profile["provenance"]["causal_label_evidence_sha256"] = (
            canonical_artifact_sha256(raw_substitution)
        )
        with self.assertRaisesRegex(CausalProfileError, "raw parsed outcomes"):
            validate_causal_profile_against_execution(
                raw_substitution_profile, **raw_substitution_kwargs
            )

        forged_ledger_kwargs = copy.deepcopy(kwargs)
        forged_condition = forged_ledger_kwargs["causal_label_evidence"]["intervention_trials"][0][
            "trial_order"
        ][0]
        forged_execution = forged_condition["intervention_execution_record"]
        forged_execution["runtime_ledger_entry"]["hook_call_count"] = 2
        forged_execution["runtime_ledger_entry_sha256"] = canonical_artifact_sha256(
            forged_execution["runtime_ledger_entry"]
        )
        forged_condition["intervention_execution_record_sha256"] = canonical_artifact_sha256(
            forged_execution
        )
        forged_ledger_profile = copy.deepcopy(profile)
        forged_ledger_profile["provenance"]["causal_label_evidence_sha256"] = (
            canonical_artifact_sha256(forged_ledger_kwargs["causal_label_evidence"])
        )
        with self.assertRaisesRegex(CausalProfileError, "execution provenance"):
            validate_causal_profile_against_execution(forged_ledger_profile, **forged_ledger_kwargs)

        other_partition_profile = copy.deepcopy(profile)
        behavior_partition = next(
            item
            for item in kwargs["execution_lock"]["live_material_manifest"]["partition_records"]
            if item["partition_id"] == "D_behavior_fit"
        )
        other_partition_profile["provenance"]["evaluation_pair_set_sha256"] = behavior_partition[
            "primary_intervention_pair_set_sha256"
        ]
        with self.assertRaisesRegex(CausalProfileError, "D_causal_label subset"):
            validate_causal_profile_against_execution(other_partition_profile, **kwargs)

        stability_substitution = copy.deepcopy(profile)
        stability_substitution["site_selection_stability"]["components"]["surface_cue"][
            "candidate_site_count"
        ] += 1
        _refresh_gate(stability_substitution)
        with self.assertRaisesRegex(CausalProfileError, "report-derived rediscovery"):
            validate_causal_profile_against_execution(stability_substitution, **kwargs)

    def test_component_and_delta_arithmetic_are_fail_closed(self) -> None:
        component_mismatch = copy.deepcopy(_valid_profile())
        component_mismatch["profile"]["semantic_solution"]["specific_iia"] = 0.69
        with self.assertRaisesRegex(CausalProfileError, "must equal intended_iia"):
            validate_causal_profile(component_mismatch)
        with self.assertRaisesRegex(TypeError, "arithmetic_tolerance"):
            validate_causal_profile(component_mismatch, arithmetic_tolerance=10.0)

        delta_mismatch = copy.deepcopy(_valid_profile())
        delta_mismatch["delta_specific"]["value"] = 0.44
        with self.assertRaisesRegex(CausalProfileError, "must equal semantic"):
            validate_causal_profile(delta_mismatch)

    def test_matched_null_identity_is_canonical_and_frozen(self) -> None:
        wrong_kind = copy.deepcopy(_valid_profile())
        wrong_kind["profile"]["semantic_solution"]["matched_null_kind"] = "generic_random"
        with self.assertRaisesRegex(CausalProfileError, "norm_matched_rotation"):
            validate_causal_profile(wrong_kind)

        legacy_name = copy.deepcopy(_valid_profile())
        effect = legacy_name["profile"]["semantic_solution"]
        effect["matched_random_iia"] = effect.pop("matched_null_iia")
        schema = json.loads(
            (REPO_ROOT / "schemas" / "causal_profile.schema.json").read_text(encoding="utf-8")
        )
        validator_class = validator_for(schema)
        with self.assertRaises(ValidationError):
            validator_class(schema).validate(legacy_name)

    def test_specificity_controls_are_count_bound_to_the_component_denominator(self) -> None:
        wrong_self_denominator = copy.deepcopy(_valid_profile())
        wrong_self_denominator["profile"]["semantic_solution"]["specificity_controls"]["self_sham"][
            "trial_count"
        ] = 63
        with self.assertRaisesRegex(CausalProfileError, "component trial_count"):
            validate_causal_profile(wrong_self_denominator)

        wrong_self_accuracy = copy.deepcopy(_valid_profile())
        wrong_self_accuracy["profile"]["semantic_solution"]["specificity_controls"]["self_sham"][
            "accuracy"
        ] = 0.89
        with self.assertRaisesRegex(CausalProfileError, "success_count / trial_count"):
            validate_causal_profile(wrong_self_accuracy)

        wrong_control_iia = copy.deepcopy(_valid_profile())
        wrong_control_iia["profile"]["surface_cue"]["specificity_controls"]["control_site_delta"][
            "iia"
        ] = 0.31
        with self.assertRaisesRegex(CausalProfileError, "success_count / trial_count"):
            validate_causal_profile(wrong_control_iia)

        wrong_control_specific = copy.deepcopy(_valid_profile())
        wrong_control_specific["profile"]["surface_cue"]["specificity_controls"][
            "control_site_delta"
        ]["specific_vs_matched_null"] = 0.09
        with self.assertRaisesRegex(CausalProfileError, "iia - matched_null_iia"):
            validate_causal_profile(wrong_control_specific)

    def test_success_counts_close_raw_iia_and_denominators(self) -> None:
        impossible_fraction = copy.deepcopy(_valid_profile())
        impossible_fraction["profile"]["semantic_solution"]["intended_iia"] = 0.82
        with self.assertRaisesRegex(CausalProfileError, "intended_success_count"):
            validate_causal_profile(impossible_fraction)

        too_many_successes = copy.deepcopy(_valid_profile())
        too_many_successes["profile"]["surface_cue"]["matched_null_success_count"] = 65
        with self.assertRaisesRegex(CausalProfileError, "must not exceed"):
            validate_causal_profile(too_many_successes)

    def test_gate_boundaries_and_anchor_route_mapping_are_executable(self) -> None:
        profile = _valid_profile()
        gate = profile["gate_evaluation"]

        self.assertEqual(profile["profile"]["surface_cue"]["specific_iia"], 0.25)
        self.assertEqual(
            profile["profile"]["semantic_solution"]["specificity_controls"]["self_sham"][
                "accuracy"
            ],
            58 / 64,
        )
        self.assertLessEqual(
            abs(
                profile["profile"]["semantic_solution"]["specificity_controls"][
                    "control_site_delta"
                ]["specific_vs_matched_null"]
            ),
            0.10,
        )
        self.assertEqual(profile["codebook_competence"]["accuracy"], 116 / 128)
        self.assertEqual(
            profile["site_selection_stability"]["components"]["surface_cue"]["selection_frequency"],
            0.75,
        )
        self.assertTrue(gate["overall_pass"])
        self.assertEqual(gate["anchor_eligibility"], "resolved")
        self.assertEqual(gate["required_route_components"], ["semantic_solution", "surface_cue"])
        self.assertFalse(gate["components"]["answer_codebook"]["route_required"])
        self.assertFalse(gate["components"]["answer_codebook"]["specific_iia_pass"])
        self.assertTrue(gate["components"]["answer_codebook"]["component_pass"])
        self.assertEqual(validate_causal_profile(profile), profile)

        integer_control_boundary = copy.deepcopy(profile)
        serialized_control_specific = integer_control_boundary["profile"]["semantic_solution"][
            "specificity_controls"
        ]["control_site_delta"]["specific_vs_matched_null"]
        self.assertEqual(serialized_control_specific, 6 / 64)
        self.assertTrue(
            integer_control_boundary["gate_evaluation"]["components"]["semantic_solution"][
                "control_site_pass"
            ]
        )
        self.assertEqual(
            validate_causal_profile(integer_control_boundary),
            integer_control_boundary,
        )

        tolerance_rounded = copy.deepcopy(profile)
        tolerance_rounded["profile"]["surface_cue"]["specific_iia"] -= 5e-10
        tolerance_rounded["profile"]["semantic_solution"]["specificity_controls"]["self_sham"][
            "accuracy"
        ] -= 5e-10
        tolerance_rounded["profile"]["semantic_solution"]["specificity_controls"][
            "control_site_delta"
        ]["specific_vs_matched_null"] += 5e-10
        tolerance_rounded["codebook_competence"]["accuracy"] -= 5e-10
        self.assertEqual(validate_causal_profile(tolerance_rounded), tolerance_rounded)

        anchor_routes = {
            "semantic_anchor": ["semantic_solution"],
            "surface_cue_anchor": ["surface_cue"],
            "mixed_anchor": ["semantic_solution", "surface_cue"],
        }
        for anchor_condition_id, required_routes in anchor_routes.items():
            with self.subTest(anchor_condition_id=anchor_condition_id):
                anchor_profile = copy.deepcopy(profile)
                anchor_profile["anchor_condition_id"] = anchor_condition_id
                _refresh_gate(anchor_profile)
                self.assertEqual(
                    anchor_profile["gate_evaluation"]["required_route_components"],
                    required_routes,
                )
                self.assertEqual(validate_causal_profile(anchor_profile), anchor_profile)

        invalid_anchor = copy.deepcopy(profile)
        invalid_anchor["anchor_condition_id"] = "answer_codebook_anchor"
        with self.assertRaisesRegex(CausalProfileError, "anchor_condition_id must be"):
            validate_causal_profile(invalid_anchor)

    def test_failed_gate_metrics_are_preserved_and_force_unresolved(self) -> None:
        failures = []

        route_failure = copy.deepcopy(_valid_profile())
        route_failure["profile"]["surface_cue"] = _effect(
            31,
            16,
            control_site_successes=22,
        )
        _refresh_delta(route_failure)
        _refresh_gate(route_failure)
        failures.append((route_failure, "route_specificity_pass"))

        self_sham_failure = copy.deepcopy(_valid_profile())
        self_sham = self_sham_failure["profile"]["semantic_solution"]["specificity_controls"][
            "self_sham"
        ]
        self_sham["success_count"] = 57
        self_sham["accuracy"] = 57 / 64
        _refresh_gate(self_sham_failure)
        failures.append((self_sham_failure, "specificity_controls_pass"))

        control_site_failure = copy.deepcopy(_valid_profile())
        control_site = control_site_failure["profile"]["surface_cue"]["specificity_controls"][
            "control_site_delta"
        ]
        control_site["success_count"] = 9
        control_site["iia"] = 9 / 64
        control_site["specific_vs_matched_null"] = 9 / 64 - 16 / 64
        _refresh_gate(control_site_failure)
        failures.append((control_site_failure, "specificity_controls_pass"))

        codebook_failure = copy.deepcopy(_valid_profile())
        codebook_failure["codebook_competence"]["success_count"] = 115
        codebook_failure["codebook_competence"]["accuracy"] = 115 / 128
        _refresh_gate(codebook_failure)
        failures.append((codebook_failure, "codebook_competence_pass"))

        for profile, failed_gate in failures:
            with self.subTest(failed_gate=failed_gate):
                self.assertEqual(validate_causal_profile(profile), profile)
                self.assertFalse(profile["gate_evaluation"][failed_gate])
                self.assertFalse(profile["gate_evaluation"]["overall_pass"])
                self.assertEqual(profile["gate_evaluation"]["overall_status"], "fail")
                self.assertEqual(profile["gate_evaluation"]["anchor_eligibility"], "unresolved")

    def test_gate_serialization_is_recomputed_fail_closed(self) -> None:
        wrong_required_routes = copy.deepcopy(_valid_profile())
        wrong_required_routes["gate_evaluation"]["required_route_components"] = [
            "semantic_solution"
        ]
        with self.assertRaisesRegex(CausalProfileError, "match anchor_condition_id"):
            validate_causal_profile(wrong_required_routes)

        wrong_boolean = copy.deepcopy(_valid_profile())
        wrong_boolean["gate_evaluation"]["overall_pass"] = False
        with self.assertRaisesRegex(CausalProfileError, "inconsistent with measured metrics"):
            validate_causal_profile(wrong_boolean)

        wrong_status = copy.deepcopy(_valid_profile())
        wrong_status["gate_evaluation"]["anchor_eligibility"] = "unresolved"
        with self.assertRaisesRegex(CausalProfileError, "inconsistent with overall_pass"):
            validate_causal_profile(wrong_status)

        wrong_threshold = copy.deepcopy(_valid_profile())
        wrong_threshold["gate_evaluation"]["thresholds"]["minimum_route_specific_iia"] = 0.24
        with self.assertRaisesRegex(CausalProfileError, "frozen threshold"):
            validate_causal_profile(wrong_threshold)

    def test_intervals_must_be_ordered_and_contain_the_point_estimate(self) -> None:
        excludes_effect = copy.deepcopy(_valid_profile())
        excludes_effect["profile"]["surface_cue"]["ci95_lower"] = 0.10
        excludes_effect["profile"]["surface_cue"]["ci95_upper"] = 0.20
        with self.assertRaisesRegex(CausalProfileError, "does not contain"):
            validate_causal_profile(excludes_effect)

        reversed_delta = copy.deepcopy(_valid_profile())
        reversed_delta["delta_specific"]["ci95_lower"] = 0.7
        reversed_delta["delta_specific"]["ci95_upper"] = 0.6
        with self.assertRaisesRegex(CausalProfileError, "lower bound exceeds"):
            validate_causal_profile(reversed_delta)

    def test_delete_one_records_close_counts_omissions_delta_and_intervals(self) -> None:
        wrong_length = copy.deepcopy(_valid_profile())
        wrong_length["profile"]["semantic_solution"]["delete_one_records"].pop()
        with self.assertRaisesRegex(CausalProfileError, "exactly 16"):
            validate_causal_profile(wrong_length)

        duplicate_omission = copy.deepcopy(_valid_profile())
        semantic_records = duplicate_omission["profile"]["semantic_solution"]["delete_one_records"]
        semantic_records[1]["omitted_content_seed_id"] = semantic_records[0][
            "omitted_content_seed_id"
        ]
        with self.assertRaisesRegex(CausalProfileError, "must be unique"):
            validate_causal_profile(duplicate_omission)

        wrong_delete_one_rate = copy.deepcopy(_valid_profile())
        wrong_delete_one_rate["profile"]["semantic_solution"]["delete_one_records"][0][
            "intended_iia"
        ] = 0.5
        with self.assertRaisesRegex(CausalProfileError, "intended_success_count"):
            validate_causal_profile(wrong_delete_one_rate)

        non_subset_denominator = copy.deepcopy(_valid_profile())
        changed_record = non_subset_denominator["profile"]["semantic_solution"][
            "delete_one_records"
        ][0]
        changed_record["trial_count"] = 64
        _recompute_delete_one_record(changed_record)
        with self.assertRaisesRegex(CausalProfileError, "strictly less than full"):
            validate_causal_profile(non_subset_denominator)

        non_subset_success_count = copy.deepcopy(_valid_profile())
        changed_record = non_subset_success_count["profile"]["semantic_solution"][
            "delete_one_records"
        ][0]
        changed_record["intended_success_count"] = 55
        _recompute_delete_one_record(changed_record)
        with self.assertRaisesRegex(CausalProfileError, "must not exceed the full count"):
            validate_causal_profile(non_subset_success_count)

        broken_trial_closure = copy.deepcopy(_valid_profile())
        changed_record = broken_trial_closure["profile"]["semantic_solution"]["delete_one_records"][
            0
        ]
        changed_record["trial_count"] += 1
        _recompute_delete_one_record(changed_record)
        with self.assertRaisesRegex(CausalProfileError, "equally sized preplanned"):
            validate_causal_profile(broken_trial_closure)

        unequal_preplanned_blocks = copy.deepcopy(_valid_profile())
        semantic = unequal_preplanned_blocks["profile"]["semantic_solution"]
        semantic_records = semantic["delete_one_records"]
        semantic_records[0]["trial_count"] = 61
        semantic_records[1]["trial_count"] = 59
        _recompute_delete_one_record(semantic_records[0])
        _recompute_delete_one_record(semantic_records[1])
        _refresh_effect_interval(semantic)
        _refresh_delta(unequal_preplanned_blocks)
        with self.assertRaisesRegex(CausalProfileError, "equally sized preplanned"):
            validate_causal_profile(unequal_preplanned_blocks)

        impossible_omitted_successes = copy.deepcopy(_valid_profile())
        semantic = impossible_omitted_successes["profile"]["semantic_solution"]
        semantic_records = semantic["delete_one_records"]
        semantic_records[0]["intended_success_count"] -= 2
        semantic_records[1]["intended_success_count"] += 2
        _recompute_delete_one_record(semantic_records[0])
        _recompute_delete_one_record(semantic_records[1])
        _refresh_effect_interval(semantic)
        _refresh_delta(impossible_omitted_successes)
        with self.assertRaisesRegex(CausalProfileError, "omitted intended_success_count"):
            validate_causal_profile(impossible_omitted_successes)

        impossible_omitted_matched_successes = copy.deepcopy(_valid_profile())
        impossible_omitted_matched_successes["profile"]["semantic_solution"] = _effect(
            54,
            32,
            control_site_successes=32,
        )
        semantic = impossible_omitted_matched_successes["profile"]["semantic_solution"]
        semantic_records = semantic["delete_one_records"]
        semantic_records[0]["matched_null_success_count"] -= 6
        semantic_records[1]["matched_null_success_count"] += 5
        semantic_records[2]["matched_null_success_count"] += 1
        for changed_record in semantic_records[:3]:
            _recompute_delete_one_record(changed_record)
        _refresh_effect_interval(semantic)
        _refresh_delta(impossible_omitted_matched_successes)
        _refresh_gate(impossible_omitted_matched_successes)
        with self.assertRaisesRegex(CausalProfileError, "omitted matched_null_success_count"):
            validate_causal_profile(impossible_omitted_matched_successes)

        broken_success_closure = copy.deepcopy(_valid_profile())
        changed_record = broken_success_closure["profile"]["semantic_solution"][
            "delete_one_records"
        ][-1]
        changed_record["intended_success_count"] -= 1
        _recompute_delete_one_record(changed_record)
        with self.assertRaisesRegex(CausalProfileError, "intended_success_count sum"):
            validate_causal_profile(broken_success_closure)

        mismatched_component_ids = copy.deepcopy(_valid_profile())
        mismatched_component_ids["profile"]["answer_codebook"]["delete_one_records"][-1][
            "omitted_content_seed_id"
        ] = "content-seed-other"
        with self.assertRaisesRegex(CausalProfileError, "must share the same"):
            validate_causal_profile(mismatched_component_ids)

        mismatched_component_full_denominator = copy.deepcopy(_valid_profile())
        mismatched_component_full_denominator["profile"]["answer_codebook"] = _effect(
            40,
            20,
            trial_count=80,
            self_sham_successes=72,
            control_site_successes=26,
        )
        _refresh_gate(mismatched_component_full_denominator)
        with self.assertRaisesRegex(CausalProfileError, "frozen D_causal_label denominator"):
            validate_causal_profile(mismatched_component_full_denominator)

        mismatched_component_delete_denominators = copy.deepcopy(_valid_profile())
        answer_records = mismatched_component_delete_denominators["profile"]["answer_codebook"][
            "delete_one_records"
        ]
        answer_records[0]["trial_count"] += 1
        answer_records[1]["trial_count"] -= 1
        _recompute_delete_one_record(answer_records[0])
        _recompute_delete_one_record(answer_records[1])
        with self.assertRaisesRegex(CausalProfileError, "equally sized preplanned"):
            validate_causal_profile(mismatched_component_delete_denominators)

        wrong_but_divisible_full_denominator = copy.deepcopy(_valid_profile())
        wrong_but_divisible_full_denominator["profile"]["answer_codebook"] = _effect(
            20,
            10,
            trial_count=80,
            self_sham_successes=72,
            control_site_successes=16,
        )
        _refresh_gate(wrong_but_divisible_full_denominator)
        with self.assertRaisesRegex(CausalProfileError, "frozen D_causal_label denominator"):
            validate_causal_profile(wrong_but_divisible_full_denominator)

        wrong_delta = copy.deepcopy(_valid_profile())
        wrong_delta["delta_specific"]["delete_one_records"][3]["value"] = 0.4
        with self.assertRaisesRegex(CausalProfileError, "semantic minus cue"):
            validate_causal_profile(wrong_delta)

        wrong_delta_ids = copy.deepcopy(_valid_profile())
        wrong_delta_ids["delta_specific"]["delete_one_records"][-1]["omitted_content_seed_id"] = (
            "content-seed-other"
        )
        with self.assertRaisesRegex(CausalProfileError, "profile omission-ID set"):
            validate_causal_profile(wrong_delta_ids)

        wrong_interval = copy.deepcopy(_valid_profile())
        semantic_records = wrong_interval["profile"]["semantic_solution"]["delete_one_records"]
        semantic_records[-2]["intended_success_count"] -= 1
        semantic_records[-1]["intended_success_count"] += 1
        _recompute_delete_one_record(semantic_records[-2])
        _recompute_delete_one_record(semantic_records[-1])
        with self.assertRaisesRegex(CausalProfileError, "frozen 16-delete-one"):
            validate_causal_profile(wrong_interval)

    def test_codebook_competence_is_count_bound_and_content_addressed(self) -> None:
        wrong_accuracy = copy.deepcopy(_valid_profile())
        wrong_accuracy["codebook_competence"]["accuracy"] = 0.95
        with self.assertRaisesRegex(CausalProfileError, "success_count / trial_count"):
            validate_causal_profile(wrong_accuracy)

        too_many_successes = copy.deepcopy(_valid_profile())
        too_many_successes["codebook_competence"]["success_count"] = 129
        with self.assertRaisesRegex(CausalProfileError, "must not exceed"):
            validate_causal_profile(too_many_successes)

        wrong_but_complete_looking_denominator = copy.deepcopy(_valid_profile())
        wrong_but_complete_looking_denominator["codebook_competence"].update(
            {
                "success_count": 232,
                "trial_count": 256,
                "accuracy": 232 / 256,
            }
        )
        with self.assertRaisesRegex(CausalProfileError, "complete D_causal_label denominator"):
            validate_causal_profile(wrong_but_complete_looking_denominator)

        bad_digest = copy.deepcopy(_valid_profile())
        bad_digest["codebook_competence"]["causal_label_case_set_sha256"] = "not-a-digest"
        with self.assertRaisesRegex(CausalProfileError, "lowercase SHA-256"):
            validate_causal_profile(bad_digest)

        old_bare_accuracy = copy.deepcopy(_valid_profile())
        old_bare_accuracy["codebook_competence"] = 0.96
        schema = json.loads(
            (REPO_ROOT / "schemas" / "causal_profile.schema.json").read_text(encoding="utf-8")
        )
        validator_class = validator_for(schema)
        with self.assertRaises(ValidationError):
            validator_class(schema).validate(old_bare_accuracy)

    def test_site_selection_status_is_derived_from_rediscovery_frequency(self) -> None:
        wrong_frequency = copy.deepcopy(_valid_profile())
        wrong_frequency["site_selection_stability"]["components"]["surface_cue"][
            "selection_frequency"
        ] = 0.625
        with self.assertRaisesRegex(CausalProfileError, "full selected-site count / 8"):
            validate_causal_profile(wrong_frequency)

        unstable = copy.deepcopy(_valid_profile())
        surface_stability = unstable["site_selection_stability"]["components"]["surface_cue"]
        _set_site_selection_count(surface_stability, 5)
        with self.assertRaisesRegex(CausalProfileError, "overall_status is inconsistent"):
            validate_causal_profile(unstable)

        unstable["site_selection_stability"]["overall_status"] = "unstable"
        _refresh_gate(unstable)
        self.assertEqual(validate_causal_profile(unstable), unstable)
        self.assertFalse(unstable["gate_evaluation"]["site_selection_stability_pass"])
        self.assertEqual(unstable["gate_evaluation"]["anchor_eligibility"], "unresolved")

        duplicate_omission = copy.deepcopy(_valid_profile())
        selections = duplicate_omission["site_selection_stability"]["components"][
            "semantic_solution"
        ]["leave_one_selections"]
        selections[1]["omitted_content_seed_id"] = selections[0]["omitted_content_seed_id"]
        with self.assertRaisesRegex(CausalProfileError, "must be unique"):
            validate_causal_profile(duplicate_omission)

        mismatched_component_omissions = copy.deepcopy(_valid_profile())
        surface_selections = mismatched_component_omissions["site_selection_stability"][
            "components"
        ]["surface_cue"]["leave_one_selections"]
        surface_selections[0]["omitted_content_seed_id"] = "discovery-seed-other"
        with self.assertRaisesRegex(CausalProfileError, "must share the same omitted"):
            validate_causal_profile(mismatched_component_omissions)

        incomplete_histogram = copy.deepcopy(_valid_profile())
        histogram = incomplete_histogram["site_selection_stability"]["components"][
            "semantic_solution"
        ]["selection_histogram"]
        histogram[1]["site_id"] = "unobserved-site"
        with self.assertRaisesRegex(CausalProfileError, "exactly match"):
            validate_causal_profile(incomplete_histogram)

        wrong_histogram_total = copy.deepcopy(_valid_profile())
        wrong_histogram_total["site_selection_stability"]["components"]["semantic_solution"][
            "selection_histogram"
        ][0]["count"] += 1
        with self.assertRaisesRegex(CausalProfileError, "counts must sum to 8"):
            validate_causal_profile(wrong_histogram_total)

        wrong_method = copy.deepcopy(_valid_profile())
        wrong_method["site_selection_stability"]["method"] = "fixed_site_bootstrap"
        with self.assertRaisesRegex(CausalProfileError, "leave-one-seed-out"):
            validate_causal_profile(wrong_method)

    def test_pilot_record_rejects_population_uncertainty_language(self) -> None:
        wrong_method = copy.deepcopy(_valid_profile())
        wrong_method["uncertainty_scope"]["interval_method"] = "posthoc_bootstrap"
        with self.assertRaisesRegex(CausalProfileError, "interval method"):
            validate_causal_profile(wrong_method)

        profile = copy.deepcopy(_valid_profile())
        profile["uncertainty_scope"] = {
            "interval_scope": "population_transfer_interval",
            "interval_method": "content_seed_delete_one_jackknife_normal_95_v1",
            "primary_independent_unit": "dependency_cluster_id",
            "population_inference": True,
        }
        with self.assertRaisesRegex(CausalProfileError, "within-target"):
            validate_causal_profile(profile)

        schema = json.loads(
            (REPO_ROOT / "schemas" / "causal_profile.schema.json").read_text(encoding="utf-8")
        )
        validator_class = validator_for(schema)
        with self.assertRaises(ValidationError):
            validator_class(schema).validate(profile)


if __name__ == "__main__":
    unittest.main()
