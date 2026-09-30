from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


REQUIRED_PROTOCOL_FIELDS = (
    "schema_version",
    "status",
    "panel_id",
    "scope",
    "factor_grid",
    "phase_contract",
    "primary_readouts",
    "claim_ceiling",
    "outcome_exposure",
    "amendment_rule",
)
FROZEN_SCOPE_LOCKS = (
    "model_revision",
    "tokenizer_revision",
    "case_set_sha256",
    "projection_set_sha256",
    "split_manifest_sha256",
    "query_budget",
    "feature_whitelist",
)
DESIGN_FREEZE_ASSET_IDS = {
    "blind_evaluation_contract",
    "blind_bundle_schema",
    "blind_conformance_tests",
    "blind_interface_source",
    "causal_label_evidence_schema",
    "causal_profile_schema",
    "causal_profile_source",
    "causal_profile_tests",
    "cli_source",
    "challenge_prediction_schema",
    "challenge_scoring_key_schema",
    "challenge_slot_schema",
    "design_manifest_schema",
    "discovery_authorization_schema",
    "evaluation_commitment_schema",
    "execution_contract_source",
    "execution_contract_tests",
    "execution_lock_schema",
    "family_split_rule",
    "generator_conformance_tests",
    "independent_unit_definition",
    "intervention_table",
    "io_source",
    "oss_design_source",
    "module_entry_source",
    "package_init_source",
    "package_schema_source",
    "prospective_conformance_tests",
    "prospective_scoring_contract",
    "prospective_source",
    "protocol_conformance_tests",
    "protocol_linter_source",
    "sealed_evaluation_authorization_schema",
    "split_conformance_tests",
    "split_source",
    "site_discovery_report_schema",
    "task_generator_spec",
}
AUDITOR_FEATURE_WHITELIST = (
    "target_id",
    "case_id",
    "projection_id",
    "replicate_id",
    "prompt_text",
    "output_text",
)
OSS_PANEL_ID = "oss_reliance_regime_v0"
OSS_ENGINEERING_CLAIM_TIER = "engineering_transfer_pilot"
OSS_FROZEN_CLAIM_CEILING = (
    "This design can support a named-unit engineering transfer pilot. It cannot support "
    "model-independent, population-generalization, calibrated-posterior, "
    "proprietary-internal-truth, or hidden-chain-of-thought claims. Confirmatory "
    "cross-cluster language requires a fresh outcome-naive successor with at least three "
    "development and three separately sealed confirmatory dependency clusters, subject to "
    "frozen power analysis."
)
OSS_FROZEN_AMENDMENT_RULE = {
    "mode": "append_only_successor",
    "rule": (
        "Never mutate this design or any of the three unassigned templates. Any concrete discovery "
        "authorization, site-discovery report, final execution lock, powered confirmatory "
        "design, or correction is a new content-addressed artifact with the relevant parent "
        "SHA-256."
    ),
}
OSS_PROTOCOL_TOP_LEVEL_FIELDS = {
    "schema_version",
    "status",
    "panel_id",
    "scope",
    "factor_grid",
    "phase_contract",
    "reference_label",
    "analysis_contract",
    "primary_readouts",
    "engineering_pilot_gates",
    "claim_ceiling",
    "stop_conditions",
    "forbidden_retrofit",
    "freeze_layers",
    "outcome_exposure",
    "amendment_rule",
}
OSS_FROZEN_SECTION_SHA256 = {
    "scope": "8975daa2b760610f1080b903b909800349e70d07e1c8430fec35c227b8890dd5",
    "factor_grid": "b901510664f646255a0d70f7513922f689e72e615bb567b77938f226e3c1adac",
    "phase_contract": "02db34416caa4128b5ddc1d9c780902d3ae05c4979a4d383ab8c147f9a002ee1",
    "reference_label": "5d9d51fe082b7cc41b71d1af9cbe9771ba4376967335c25eae84141f15a5f46b",
    "analysis_contract": "9719baace3392310f3c491cf1eb28c6ce2162a2371f94d7529e4ad0df22ab68c",
    "primary_readouts": "83c024d1c9856dc7f006644849195fc642b2f9325dbd0b83c28440d6838b0399",
    "engineering_pilot_gates": ("9d7bb3b1a0f211c6c1991b71544a28759b669a2f1496fe51a0789943639cb5e5"),
    "stop_conditions": "fdb1adf808957dbdecca662d35e28e67619f3b95dd6e1cc927116ac3c6ddb320",
    "forbidden_retrofit": "f0a7b725bbbcede8552b3431e7482ea037104beaf92eccc6a650727ac82fbdf7",
    "outcome_exposure": "0f9ccdb6c844631159ada8fb99722ad7d7746116fea5f00140a5be132a15e871",
}
PREFLIGHT_NOT_VALIDATED = (
    "concrete content-addressed discovery authorization",
    "authority-held site-discovery report",
    "post-output sealed evaluation authorizations",
    "pre-auditor ledger and raw D_sealed output evidence",
    "locked-model runtime provenance for each sealed completion record",
    "physical forward-execution attestation",
    "live execution model or tokenizer availability",
    "live case and projection material",
    "live dependency graph and fold disjointness",
    "live query budget feasibility",
    "live provider capabilities",
    "physical fold-worker realm isolation",
    "fold-local estimator training and replay",
    "zero-forward-call enforcement outside this process",
)


def _sha256_json_value(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_oss_scientific_seal(payload: dict[str, Any], *, errors: list[str]) -> None:
    """Bind the design-frozen protocol's exposure, claim, and amendment ceiling."""

    if set(payload) != OSS_PROTOCOL_TOP_LEVEL_FIELDS:
        errors.append("OSS design-frozen protocol top-level field set drifted")
    if (
        payload.get("schema_version") != "0.1.0"
        or payload.get("status") != "design_frozen"
        or payload.get("panel_id") != OSS_PANEL_ID
    ):
        errors.append("OSS design-frozen protocol identity metadata drifted")
    exposure = payload.get("outcome_exposure")
    if not isinstance(exposure, dict) or (
        exposure.get("at_freeze") != "none"
        or exposure.get("oss_model_calls") != 0
        or exposure.get("oss_outcomes_exposed") is not False
    ):
        errors.append(
            "OSS design freeze requires at_freeze=none, oss_model_calls=0, and "
            "oss_outcomes_exposed=false"
        )
    scope = payload.get("scope")
    if not isinstance(scope, dict) or scope.get("three_cluster_claim_tier") != (
        OSS_ENGINEERING_CLAIM_TIER
    ):
        errors.append("OSS design freeze claim tier must remain engineering_transfer_pilot")
    if payload.get("claim_ceiling") != OSS_FROZEN_CLAIM_CEILING:
        errors.append("OSS design freeze claim ceiling drifted or strengthened")
    if payload.get("amendment_rule") != OSS_FROZEN_AMENDMENT_RULE:
        errors.append("OSS design freeze amendment rule must remain append-only and exact")
    for section, expected_sha256 in OSS_FROZEN_SECTION_SHA256.items():
        if _sha256_json_value(payload.get(section)) != expected_sha256:
            errors.append(f"OSS design freeze scientific section drifted={section}")


def _validate_design_manifest_metadata(
    manifest: dict[str, Any], payload: dict[str, Any], *, errors: list[str]
) -> None:
    expected_manifest_keys = {
        "schema_version",
        "freeze_id",
        "panel_id",
        "status",
        "freeze_date",
        "oss_outcomes_exposed",
        "amendment_mode",
        "assets",
    }
    if set(manifest) != expected_manifest_keys:
        errors.append("design freeze manifest top-level field set drifted")
    if (
        manifest.get("schema_version") != "0.1.0"
        or manifest.get("panel_id") != payload.get("panel_id")
        or manifest.get("status") != "design_frozen"
        or manifest.get("freeze_date") != "2026-07-17"
        or manifest.get("oss_outcomes_exposed") is not False
        or manifest.get("amendment_mode") != "append_only_successor"
    ):
        errors.append("design freeze manifest metadata, exposure, or amendment mode drifted")
    freeze_id = manifest.get("freeze_id")
    if not isinstance(freeze_id, str) or not freeze_id:
        errors.append("design freeze manifest freeze_id must be non-empty")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _find_repository_root(protocol_path: Path) -> Path | None:
    for candidate in (protocol_path.parent, *protocol_path.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate.resolve()
    return None


def _safe_relative_path(value: Any, *, field: str, errors: list[str]) -> Path | None:
    if not isinstance(value, str) or not value:
        errors.append(f"{field} must be a non-empty relative path")
        return None
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        errors.append(f"{field} must not be absolute or contain '..'")
        return None
    return path


def _validate_freeze_layer_shape(freeze: Any, *, errors: list[str]) -> None:
    if not isinstance(freeze, dict):
        errors.append("design_frozen protocol requires freeze_layers")
        return
    expected_layers = {"design", "discovery", "execution", "sealed_evaluation"}
    if set(freeze) != expected_layers:
        errors.append(
            "freeze_layers must contain exactly design, discovery, execution, and sealed_evaluation"
        )
    expected_fields = {
        "design": {"status", "manifest_path", "manifest_sha256"},
        "discovery": {"status", "template_path", "template_sha256"},
        "execution": {"status", "template_path", "template_sha256"},
        "sealed_evaluation": {"status", "template_path", "template_sha256"},
    }
    for layer_name, fields in expected_fields.items():
        layer = freeze.get(layer_name)
        if isinstance(layer, dict) and set(layer) != fields:
            errors.append(f"freeze_layers.{layer_name} field set drifted")


def _resolve_protocol_artifact(
    base: Path,
    relative: Path,
    *,
    field: str,
    errors: list[str],
) -> Path | None:
    """Resolve one artifact without accepting symlinked path components or escape."""

    try:
        base_resolved = base.resolve(strict=True)
    except FileNotFoundError:
        errors.append(f"{field} base directory is missing")
        return None
    candidate = base / relative
    current = base
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            errors.append(f"{field} contains a symlinked path component")
            return None
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError:
        errors.append(f"{field} is missing")
        return None
    if resolved != base_resolved and base_resolved not in resolved.parents:
        errors.append(f"{field} escapes the protocol directory")
        return None
    if not resolved.is_file():
        errors.append(f"{field} is not a regular file")
        return None
    return resolved


def _path_has_symlink_component(path: Path) -> bool:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current = current / component
        if current.is_symlink():
            return True
    return False


def _read_json_object(path: Path, *, field: str, errors: list[str]) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        errors.append(f"{field} is not readable JSON: {error}")
        return None
    if not isinstance(payload, dict):
        errors.append(f"{field} must contain a JSON object")
        return None
    return payload


def _validate_frozen_asset_contracts(
    assets_by_id: dict[str, Path], *, errors: list[str], validated_checks: list[str]
) -> None:
    import latent_trace_tomography as package_module
    import latent_trace_tomography.__main__ as module_entry_module
    import latent_trace_tomography.blind as blind_module
    import latent_trace_tomography.causal_profile as causal_profile_module
    import latent_trace_tomography.cli as cli_module
    import latent_trace_tomography.execution as execution_module
    import latent_trace_tomography.io as io_module
    import latent_trace_tomography.oss_design as oss_design_module
    import latent_trace_tomography.prospective as prospective_module
    import latent_trace_tomography.schema as package_schema_module
    import latent_trace_tomography.split as split_module
    from latent_trace_tomography.blind import (
        AUDITOR_OBSERVATION_FIELDS,
        AUTHORITY_COMMITMENT_CONFORMANCE_VECTOR,
        AUTHORITY_COMMITMENT_FRAMING,
        AUTHORITY_COMMITMENT_MIN_NONCE_BYTES,
        AUTHORITY_COMMITMENT_SCHEME,
        METHOD_DEFINING_AUDITOR_ARTIFACT_ROLES,
        OUTPUT_RUNTIME_EVIDENCE_BOUNDARY,
        PAIRING_TOKEN_DOMAINS,
        PAIRING_TOKEN_MATERIAL_CONTRACT,
        PAIRING_TOKEN_SCHEME,
        REQUIRED_AUDITOR_ARTIFACT_ROLES,
        SEALED_EVALUATION_AUTHORIZATION_CONTRACT,
        SEALED_EVALUATION_FOLD_COUNT,
        SEALED_FORWARD_PASS_COUNT,
    )
    from latent_trace_tomography.causal_profile import (
        ANCHOR_ROUTE_COMPONENTS,
        CAUSAL_COMPONENT_DELETE_ONE_TRIAL_COUNT,
        CAUSAL_COMPONENT_TRIAL_COUNT,
        CAUSAL_LABEL_CONTENT_SEED_COUNT,
        CODEBOOK_COMPETENCE_TRIAL_COUNT,
        ESTIMAND_KIND,
        INTERVAL_METHOD,
        MATCHED_NULL_KIND,
        MAXIMUM_ABSOLUTE_CONTROL_SITE_SPECIFIC,
        MINIMUM_CODEBOOK_COMPETENCE_ACCURACY,
        MINIMUM_ROUTE_SPECIFIC_IIA,
        MINIMUM_SELF_SHAM_ACCURACY,
        PRIMARY_PAIRS_PER_CONTENT_SEED_PER_COMPONENT,
        SITE_STABILITY_METHOD,
        SITE_STABILITY_RESAMPLE_COUNT,
        SITE_STABILITY_THRESHOLD,
    )
    from latent_trace_tomography.oss_design import (
        INTERVENTION_PROMPT_TEMPLATE_ID,
        MATCHED_NULL_ROTATION_CONFORMANCE_VECTOR,
        MATCHED_NULL_ROTATION_SCHEME,
        MATCHED_NULL_ROTATION_STREAM_DOMAIN,
        MATCHED_NULL_ROTATION_WORD_ORDER,
        MATCHED_NULL_SITE_CONFORMANCE_VECTOR,
        MATCHED_NULL_SEED_CONFORMANCE_VECTOR,
        MATCHED_NULL_SEED_DOMAIN,
        MATCHED_NULL_SEED_FRAMING,
        MATCHED_NULL_SEED_SCHEME,
        OSSDesignConfig,
        OSSProjectionKind,
        apply_norm_matched_rotation_site_v1,
        apply_norm_matched_rotation_v1,
        build_design_summary,
        build_oss_design_from_config,
        derive_matched_null_seed,
        matched_null_permutation_and_signs,
    )
    from latent_trace_tomography.prospective import (
        AGGREGATION_RULE,
        BASELINE_PRIORITY,
        CHALLENGE_KINDS,
        CHALLENGE_SLOT_FIELDS,
        OUTCOME_LABELS,
        PRIMARY_GATE_RELATIVE_REDUCTION,
        PRIMARY_METRIC,
        PROBABILITY_FLOOR,
        PROBABILITY_SUM_TOLERANCE,
        SECONDARY_METRIC,
    )
    from latent_trace_tomography.split import CONTENT_PARTITION_COUNTS, partition_content_seeds

    runtime_sources = {
        "blind_interface_source": getattr(blind_module, "__file__", None),
        "causal_profile_source": getattr(causal_profile_module, "__file__", None),
        "cli_source": getattr(cli_module, "__file__", None),
        "execution_contract_source": getattr(execution_module, "__file__", None),
        "io_source": getattr(io_module, "__file__", None),
        "oss_design_source": getattr(oss_design_module, "__file__", None),
        "module_entry_source": getattr(module_entry_module, "__file__", None),
        "package_init_source": getattr(package_module, "__file__", None),
        "package_schema_source": getattr(package_schema_module, "__file__", None),
        "prospective_source": getattr(prospective_module, "__file__", None),
        "protocol_linter_source": __file__,
        "split_source": getattr(split_module, "__file__", None),
    }
    for asset_id, runtime_value in runtime_sources.items():
        if not isinstance(runtime_value, str):
            errors.append(f"runtime source has no filesystem path={asset_id}")
            continue
        runtime_path = Path(runtime_value).resolve()
        frozen_path = assets_by_id[asset_id].resolve()
        if runtime_path != frozen_path:
            errors.append(
                f"runtime source path mismatch={asset_id}:"
                f"runtime={runtime_path}:frozen={frozen_path}"
            )
        elif _sha256_file(runtime_path) != _sha256_file(frozen_path):
            errors.append(f"runtime source hash mismatch={asset_id}")
    if not any(error.startswith("runtime source ") for error in errors):
        validated_checks.append("runtime_source_identity")

    task = _read_json_object(
        assets_by_id["task_generator_spec"], field="task generator spec", errors=errors
    )
    intervention = _read_json_object(
        assets_by_id["intervention_table"], field="intervention table", errors=errors
    )
    split = _read_json_object(
        assets_by_id["family_split_rule"], field="family split rule", errors=errors
    )
    unit = _read_json_object(
        assets_by_id["independent_unit_definition"],
        field="independent unit definition",
        errors=errors,
    )
    blind = _read_json_object(
        assets_by_id["blind_evaluation_contract"],
        field="blind evaluation contract",
        errors=errors,
    )
    causal_schema = _read_json_object(
        assets_by_id["causal_profile_schema"],
        field="causal profile schema",
        errors=errors,
    )
    evaluation_commitment_schema = _read_json_object(
        assets_by_id["evaluation_commitment_schema"],
        field="evaluation commitment schema",
        errors=errors,
    )
    sealed_evaluation_authorization_schema = _read_json_object(
        assets_by_id["sealed_evaluation_authorization_schema"],
        field="sealed evaluation authorization schema",
        errors=errors,
    )
    prospective = _read_json_object(
        assets_by_id["prospective_scoring_contract"],
        field="prospective scoring contract",
        errors=errors,
    )
    if None in (
        task,
        intervention,
        split,
        unit,
        blind,
        causal_schema,
        evaluation_commitment_schema,
        sealed_evaluation_authorization_schema,
        prospective,
    ):
        return
    assert task is not None
    assert intervention is not None
    assert split is not None
    assert unit is not None
    assert blind is not None
    assert causal_schema is not None
    assert evaluation_commitment_schema is not None
    assert sealed_evaluation_authorization_schema is not None
    assert prospective is not None

    design_config = OSSDesignConfig()
    summary = build_design_summary(design_config)
    executable_design = build_oss_design_from_config(design_config)
    conformance = task.get("public_conformance", {})
    manifest = summary["design_manifest"]
    expected_conformance = {
        "generator_config_sha256": summary["generator_config_sha256"],
        "design_manifest_sha256": manifest["manifest_sha256"],
        "case_set_sha256": manifest["case_set_sha256"],
        "projection_set_sha256": manifest["projection_set_sha256"],
        "intervention_prompt_set_sha256": manifest["intervention_prompt_set_sha256"],
        "intervention_pair_set_sha256": manifest["intervention_pair_set_sha256"],
        "primary_intervention_pair_set_sha256": manifest["primary_intervention_pair_set_sha256"],
    }
    for field, expected in expected_conformance.items():
        if conformance.get(field) != expected:
            errors.append(f"task generator conformance mismatch={field}")
    role_counts = {role: len(ids) for role, ids in manifest["projection_ids_by_role"].items()}
    expected_counts = {
        **manifest["counts"],
        "weak_observations": role_counts["weak_observation"],
        "diagnostic_cue_masks": role_counts["diagnostic_cue_mask"],
        "heldout_challenges": role_counts["heldout_challenge"],
    }
    if conformance.get("counts") != expected_counts:
        errors.append("task generator conformance counts do not match executable source")
    causal_prompt_contract = task.get("causal_intervention_prompt", {})
    prompt_by_case = {prompt.case_id: prompt for prompt in executable_design.intervention_prompts}
    projection_ids = {projection.projection_id for projection in executable_design.projections}
    pair_prompt_binding_valid = all(
        pair.base_prompt_id == prompt_by_case[pair.base_case_id].prompt_id
        and pair.source_prompt_id == prompt_by_case[pair.source_case_id].prompt_id
        and pair.base_prompt_sha256 == prompt_by_case[pair.base_case_id].prompt_sha256
        and pair.source_prompt_sha256 == prompt_by_case[pair.source_case_id].prompt_sha256
        for pair in executable_design.intervention_pairs
    )
    if (
        causal_prompt_contract.get("template_id") != INTERVENTION_PROMPT_TEMPLATE_ID
        or len(prompt_by_case) != len(executable_design.cases)
        or any(prompt.prompt_id in projection_ids for prompt in prompt_by_case.values())
        or not pair_prompt_binding_valid
    ):
        errors.append("canonical intervention-prompt binding drifted")
    weak = task.get("projection_roles", {}).get("weak_observation", {})
    if weak.get("eligibility") != "semantic_solution == surface_cue":
        errors.append("weak observation eligibility must require semantic/cue alignment")
    diagnostic = task.get("projection_roles", {}).get("diagnostic_cue_mask", {})
    if set(diagnostic.get("forbidden_uses", [])) != {
        "estimator fitting",
        "feature selection",
        "threshold selection",
        "site discovery",
        "probability calibration",
    }:
        errors.append("cue-mask diagnostic forbidden-use boundary is incomplete")
    heldout = task.get("projection_roles", {}).get("heldout_challenge", {})
    expected_challenge_kinds = [
        kind.value for kind in OSSProjectionKind if kind.value in CHALLENGE_KINDS
    ]
    challenge_cases = {case.case_id: case for case in executable_design.cases}
    if (
        heldout.get("kinds") != expected_challenge_kinds
        or heldout.get("eligibility")
        != (
            "semantic_solution != surface_cue for both kinds; each conflict cell is "
            "rendered once as heldout_cue_conflict and once as heldout_mismatch_table"
        )
        or any(
            challenge_cases[projection.case_id].semantic_solution
            is challenge_cases[projection.case_id].surface_cue
            for projection in executable_design.heldout_challenges
        )
    ):
        errors.append("heldout challenge kinds must be conflict-stratum and route-identifiable")

    rows = intervention.get("factor_rows", [])
    if {row.get("causal_variable") for row in rows if isinstance(row, dict)} != {
        "semantic_solution",
        "surface_cue",
        "answer_codebook",
    }:
        errors.append("intervention table must define exactly the three causal variables")
    hook_contract = intervention.get("activation_hook_contract", {})
    if set(hook_contract) != {
        "boundary",
        "tensor_contract",
        "source_capture",
        "base_intervention",
        "position_binding",
        "implementation_binding",
    } or "discovery authorization" not in hook_contract.get("implementation_binding", ""):
        errors.append("intervention activation-hook boundary is incomplete")
    conditions = {
        row.get("condition_id")
        for row in intervention.get("trial_conditions", [])
        if isinstance(row, dict)
    }
    if conditions != {
        "targeted_interchange",
        "self_sham",
        "norm_matched_rotation",
        "control_site_delta",
    }:
        errors.append("intervention table is missing mandatory paired controls")
    if intervention.get("analysis_policies", {}).get("primary_denominator") != (
        "all_preplanned_primary_stratum_pairs_intent_to_treat"
    ):
        errors.append("intervention primary denominator must be intent-to-treat")
    primary_estimand = intervention.get("primary_estimand", {})
    if (
        primary_estimand.get("matched_null_kind") != MATCHED_NULL_KIND
        or "matched_null_iia_v" not in primary_estimand
        or "matched_random_iia_v" in primary_estimand
    ):
        errors.append("intervention estimand must use the canonical matched-null fields")
    rotation_rows = [
        row
        for row in intervention.get("trial_conditions", [])
        if isinstance(row, dict) and row.get("condition_id") == MATCHED_NULL_KIND
    ]
    if len(rotation_rows) != 1 or "discovery_authorization_id" not in rotation_rows[0].get(
        "randomization", ""
    ):
        errors.append("matched-null randomness must be bound to discovery_authorization_id")
    matched_null_seed = intervention.get("matched_null_seed_contract", {})
    expected_seed_contract = {
        "derivation_function": "latent_trace_tomography.oss_design.derive_matched_null_seed",
        "scheme": MATCHED_NULL_SEED_SCHEME,
        "domain": MATCHED_NULL_SEED_DOMAIN.decode("ascii"),
        "framing": MATCHED_NULL_SEED_FRAMING,
        "string_encoding": "utf-8",
        "conformance_vector": dict(MATCHED_NULL_SEED_CONFORMANCE_VECTOR),
    }
    vector = MATCHED_NULL_SEED_CONFORMANCE_VECTOR
    if (
        matched_null_seed != expected_seed_contract
        or derive_matched_null_seed(
            vector["discovery_authorization_id"],
            vector["pair_id"],
            vector["canonical_site_id"],
        )
        != vector["seed64_decimal"]
    ):
        errors.append("matched-null seed framing or conformance vector drifted")
    expected_rotation_contract = {
        "site_reference_function": (
            "latent_trace_tomography.oss_design.apply_norm_matched_rotation_site_v1"
        ),
        "vector_reference_function": (
            "latent_trace_tomography.oss_design.apply_norm_matched_rotation_v1"
        ),
        "parameter_function": (
            "latent_trace_tomography.oss_design.matched_null_permutation_and_signs"
        ),
        "scheme": MATCHED_NULL_ROTATION_SCHEME,
        "stream_domain": MATCHED_NULL_ROTATION_STREAM_DOMAIN.decode("ascii"),
        "stream_input": (
            "u64be_len(stream_domain)||stream_domain||u64be(seed64)||u64be(counter), "
            "with counter starting at zero"
        ),
        "word_order": MATCHED_NULL_ROTATION_WORD_ORDER,
        "permutation": (
            "For upper from dimension-1 down to 1, consume uint64 words until word < "
            "2^64 - (2^64 mod (upper+1)), then swap permutation[upper] with "
            "permutation[word mod (upper+1)]."
        ),
        "signs": (
            "After permutation sampling, consume one uint64 word per output coordinate; "
            "even words map to +1 and odd words map to -1."
        ),
        "application": (
            "delta=source_activation-base_activation; "
            "rotated_delta[i]=signs[i]*delta[permutation[i]]; "
            "patched_activation=base_activation+rotated_delta."
        ),
        "carrier_layout": (
            "Treat a site as [carrier_position, hidden]. Draw one hidden-axis permutation "
            "and sign vector and apply it independently at every carrier position; never "
            "flatten or mix positions. One-position sites are the degenerate case."
        ),
        "numeric_policy": (
            "Reference inputs must be finite and rectangular. A live hook applies the "
            "frozen integer permutation and signs in the pinned tensor dtype with no "
            "implicit cast. Signed permutation preserves each position's mathematical L2 "
            "norm and cross-position delta dot products, including zero delta; no "
            "rescaling or tolerance is used."
        ),
        "conformance_vector": dict(MATCHED_NULL_ROTATION_CONFORMANCE_VECTOR),
        "site_conformance_vector": dict(MATCHED_NULL_SITE_CONFORMANCE_VECTOR),
    }
    rotation_vector = MATCHED_NULL_ROTATION_CONFORMANCE_VECTOR
    generated_parameters = matched_null_permutation_and_signs(
        rotation_vector["seed64_decimal"], rotation_vector["dimension"]
    )
    generated_activation = apply_norm_matched_rotation_v1(
        rotation_vector["base_activation"],
        rotation_vector["source_activation"],
        seed64=rotation_vector["seed64_decimal"],
    )
    site_vector = MATCHED_NULL_SITE_CONFORMANCE_VECTOR
    generated_site = apply_norm_matched_rotation_site_v1(
        site_vector["base_site"],
        site_vector["source_site"],
        seed64=site_vector["seed64_decimal"],
    )
    if (
        intervention.get("matched_null_rotation_contract") != expected_rotation_contract
        or [list(values) for values in generated_parameters]
        != [rotation_vector["permutation"], rotation_vector["signs"]]
        or list(generated_activation) != rotation_vector["patched_activation"]
        or [list(row) for row in generated_site] != site_vector["patched_site"]
    ):
        errors.append("matched-null rotation algorithm or conformance vector drifted")
    gate_evidence = intervention.get("gate_evidence", {})
    expected_gate_evidence = {
        "minimum_route_specific_iia": MINIMUM_ROUTE_SPECIFIC_IIA,
        "minimum_self_sham_accuracy": MINIMUM_SELF_SHAM_ACCURACY,
        "maximum_absolute_control_site_specific": MAXIMUM_ABSOLUTE_CONTROL_SITE_SPECIFIC,
        "minimum_codebook_competence_accuracy": MINIMUM_CODEBOOK_COMPETENCE_ACCURACY,
        "minimum_site_selection_frequency": SITE_STABILITY_THRESHOLD,
    }
    if any(
        gate_evidence.get(field) != expected for field, expected in expected_gate_evidence.items()
    ):
        errors.append("intervention gate-evidence thresholds do not match the executable schema")
    if gate_evidence.get("anchor_route_components") != {
        anchor: list(variables) for anchor, variables in ANCHOR_ROUTE_COMPONENTS.items()
    }:
        errors.append("intervention anchor-to-route mapping is not frozen")
    if intervention.get("public_conformance", {}).get(
        "intervention_pair_set_sha256"
    ) != manifest.get("intervention_pair_set_sha256"):
        errors.append("intervention pair hash does not match executable generator")
    canonical_prompt_binding = intervention.get("canonical_prompt_binding", {})
    if (
        canonical_prompt_binding.get("template_id") != INTERVENTION_PROMPT_TEMPLATE_ID
        or canonical_prompt_binding.get("required_pair_fields")
        != [
            "base_prompt_id",
            "source_prompt_id",
            "base_prompt_sha256",
            "source_prompt_sha256",
        ]
        or intervention.get("public_conformance", {}).get("intervention_prompt_set_sha256")
        != manifest.get("intervention_prompt_set_sha256")
    ):
        errors.append("intervention table canonical prompt binding is incomplete")
    intervention_conformance = intervention.get("public_conformance", {})
    expected_primary_counts = {
        "semantic_solution": 256,
        "surface_cue": 256,
        "answer_codebook": 256,
    }
    if intervention_conformance.get("primary_directed_pair_count") != 768 or (
        intervention_conformance.get("primary_directed_pair_count_by_factor")
        != expected_primary_counts
    ):
        errors.append("intervention primary stratum counts do not match executable generator")
    if intervention_conformance.get("primary_intervention_pair_set_sha256") != manifest.get(
        "primary_intervention_pair_set_sha256"
    ):
        errors.append("primary intervention pair hash does not match executable generator")
    frozen_primary_stratum = (
        "base.semantic_solution == base.surface_cue and expected_patched_final != base.oracle_final"
    )
    if intervention_conformance.get("primary_stratum") != frozen_primary_stratum:
        errors.append("intervention primary stratum is not the symmetric answer-switch stratum")
    expected_causal_denominator = {
        "partition_id": "D_causal_label",
        "content_seed_count": CAUSAL_LABEL_CONTENT_SEED_COUNT,
        "complete_factorial_case_count_per_target": CODEBOOK_COMPETENCE_TRIAL_COUNT,
        "primary_pair_count_per_target": CAUSAL_COMPONENT_TRIAL_COUNT * 3,
        "primary_pair_count_per_causal_variable": CAUSAL_COMPONENT_TRIAL_COUNT,
        "trial_condition_count_per_pair": 4,
        "trial_condition_ids": [
            "targeted_interchange",
            "self_sham",
            "norm_matched_rotation",
            "control_site_delta",
        ],
        "unpatched_forward_passes_per_target": CODEBOOK_COMPETENCE_TRIAL_COUNT,
        "intervention_forward_passes_per_target": CAUSAL_COMPONENT_TRIAL_COUNT * 3 * 4,
        "total_forward_passes_per_target": (
            CODEBOOK_COMPETENCE_TRIAL_COUNT + CAUSAL_COMPONENT_TRIAL_COUNT * 3 * 4
        ),
        "target_count": 9,
        "total_forward_passes_all_targets": 9
        * (CODEBOOK_COMPETENCE_TRIAL_COUNT + CAUSAL_COMPONENT_TRIAL_COUNT * 3 * 4),
        "component_trial_count": CAUSAL_COMPONENT_TRIAL_COUNT,
        "delete_one_content_seed_count": CAUSAL_LABEL_CONTENT_SEED_COUNT,
        "omitted_trials_per_delete_one": PRIMARY_PAIRS_PER_CONTENT_SEED_PER_COMPONENT,
        "remaining_trials_per_delete_one": CAUSAL_COMPONENT_DELETE_ONE_TRIAL_COUNT,
        "codebook_competence_trial_count": CODEBOOK_COMPETENCE_TRIAL_COUNT,
        "decoding": "greedy_exact_v1_with_one_replicate",
        "evidence_closure": (
            "The authoritative validator must consume the lock-bound D_causal pair and "
            "unpatched-prompt inventories plus exact raw output evidence, derive parse and "
            "success events, and recompute all full, delete-one, control, codebook, and gate "
            "values. Aggregate counts or digest-shaped provenance alone are "
            "non-authoritative."
        ),
    }
    if intervention.get("causal_label_denominator_contract") != expected_causal_denominator:
        errors.append("causal-label denominator or raw-evidence closure drifted")
    if (
        task.get("seed_contract", {}).get("live_execution", {}).get("derivation_function")
        != "latent_trace_tomography.oss_design.derive_live_content_seeds"
    ):
        errors.append("live content seeds must use the frozen keyed derivation")

    partition_counts = dict(CONTENT_PARTITION_COUNTS)
    if split.get("content_seed_partition", {}).get("counts") != partition_counts:
        errors.append("frozen content partition counts do not match split source")
    content_partition = split.get("content_seed_partition", {})
    if "intentionally reused" not in content_partition.get(
        "template_policy", ""
    ) or "template_family_id" in content_partition.get("overlap_policy", ""):
        errors.append("global frozen templates must be shared, not falsely partition-disjoint")
    generated_partitions = partition_content_seeds(OSSDesignConfig().content_seeds)
    if sum(len(values) for values in generated_partitions.values()) != 64:
        errors.append("executable content partition does not close over 64 seeds")
    if split.get("outer_split", {}).get("primary_axis") != (
        "leave exactly one dependency_cluster_id out"
    ):
        errors.append("outer split must hold out one dependency cluster")
    if unit.get("primary_independent_unit") != "dependency_cluster_id":
        errors.append("primary independent unit must be dependency_cluster_id")
    pilot_balance = split.get("pilot_anchor_balance", {})
    if (
        pilot_balance.get("dependency_cluster_count") != 3
        or pilot_balance.get("model_unit_count") != 9
        or pilot_balance.get("exact_anchor_set_per_dependency_cluster")
        != ["semantic_anchor", "surface_cue_anchor", "mixed_anchor"]
        or pilot_balance.get("anchor_multiplicity_per_cluster") != 1
    ):
        errors.append("pilot split must freeze three balanced anchors in each of three clusters")
    if "Effective n remains three, not nine" not in unit.get("pilot_balance", ""):
        errors.append("independent-unit contract must keep the balanced pilot effective n at three")
    if blind.get("auditor_observation_surface", {}).get("exact_fields") != list(
        AUDITOR_OBSERVATION_FIELDS
    ):
        errors.append("blind auditor field surface does not match executable interface")
    if blind.get("auditor_challenge_slot_surface", {}).get("exact_fields") != list(
        CHALLENGE_SLOT_FIELDS
    ):
        errors.append("blind challenge-slot field surface does not match executable interface")
    if blind.get("auditor_observation_surface", {}).get(
        "pairing_token_scheme"
    ) != PAIRING_TOKEN_SCHEME or blind.get("auditor_observation_surface", {}).get(
        "pairing_token_domains"
    ) != list(PAIRING_TOKEN_DOMAINS):
        errors.append("blind pairing-token scheme or domains do not match executable interface")
    if (
        blind.get("auditor_observation_surface", {}).get("pairing_token_material_contract")
        != PAIRING_TOKEN_MATERIAL_CONTRACT
    ):
        errors.append("blind pairing-token materials do not match executable interface")
    expected_authority_commitment = {
        "scheme": AUTHORITY_COMMITMENT_SCHEME,
        "digest": "SHA-256",
        "framing": AUTHORITY_COMMITMENT_FRAMING,
        "minimum_nonce_bytes": AUTHORITY_COMMITMENT_MIN_NONCE_BYTES,
        "nonce_generation": "operating_system_csprng",
        "conformance_vector": dict(AUTHORITY_COMMITMENT_CONFORMANCE_VECTOR),
    }
    if blind.get("authority_commitment") != expected_authority_commitment:
        errors.append("blind authority-commitment framing does not match executable interface")
    expected_runtime_evidence = {
        key: list(value) if isinstance(value, tuple) else value
        for key, value in OUTPUT_RUNTIME_EVIDENCE_BOUNDARY.items()
    }
    if blind.get("output_runtime_evidence") != expected_runtime_evidence:
        errors.append("blind output-runtime evidence boundary drifted")
    fold_specific_roles = [
        role
        for role in REQUIRED_AUDITOR_ARTIFACT_ROLES
        if role not in METHOD_DEFINING_AUDITOR_ARTIFACT_ROLES
    ]
    method_identity = blind.get("cross_fold_method_identity", {})
    if (
        method_identity.get("common_roles") != list(METHOD_DEFINING_AUDITOR_ARTIFACT_ROLES)
        or method_identity.get("fold_specific_roles") != fold_specific_roles
        or "before the authority opening provider is called"
        not in method_identity.get("enforcement", "")
    ):
        errors.append("blind cross-fold method identity contract drifted")
    schema_authority_scheme = (
        evaluation_commitment_schema.get("$defs", {})
        .get("authority_commitments", {})
        .get("properties", {})
        .get("scheme", {})
        .get("const")
    )
    if schema_authority_scheme != AUTHORITY_COMMITMENT_SCHEME:
        errors.append("evaluation-commitment schema authority scheme mismatch")
    evaluation_commitment_required = set(evaluation_commitment_schema.get("required", []))
    if (
        not {
            "execution_lock_sha256",
            "sealed_evaluation_authorization_sha256",
            "fold_token",
        }
        <= evaluation_commitment_required
    ):
        errors.append(
            "evaluation-commitment schema does not bind execution, sealed authorization, "
            "and opaque fold identity"
        )
    sealed_properties = sealed_evaluation_authorization_schema.get("properties", {})
    sealed_status = sealed_properties.get("status", {}).get("enum", [])
    sealed_counts = (
        sealed_evaluation_authorization_schema.get("$defs", {})
        .get("counts", {})
        .get("properties", {})
    )
    if (
        sealed_properties.get("contract_type", {}).get("const")
        != SEALED_EVALUATION_AUTHORIZATION_CONTRACT
        or set(sealed_status) != {"unassigned", "sealed_before_auditor_fit"}
        or sealed_counts.get("sealed_forward_pass_count", {}).get("const")
        != SEALED_FORWARD_PASS_COUNT
    ):
        errors.append("sealed-evaluation authorization schema contract or counts drifted")
    authoritative_entrypoint = blind.get("authoritative_scoring_entrypoint", {})
    if authoritative_entrypoint.get("function") != (
        "latent_trace_tomography.blind.evaluate_committed_pilot_gate"
    ):
        errors.append("blind contract must make the three-fold pilot gate authoritative")
    pilot_gate = blind.get("pilot_gate", {})
    if (
        pilot_gate.get("fold_count") != SEALED_EVALUATION_FOLD_COUNT
        or pilot_gate.get("independent_unit") != "dependency_cluster_id"
        or pilot_gate.get("single_fold_authority") is not False
    ):
        errors.append("blind contract does not freeze the three-fold cluster-level pilot gate")
    required_artifact_text = blind.get("required_commitment_artifacts", [])
    if not any(
        all(role in item for role in REQUIRED_AUDITOR_ARTIFACT_ROLES)
        for item in required_artifact_text
        if isinstance(item, str)
    ):
        errors.append("blind contract does not freeze the exact auditor artifact role set")
    if blind.get("assurance_language", {}).get("same_process") != ("prediction_locked_not_blind"):
        errors.append("same-process evaluation must not be described as blind")
    if task.get("outcome_exposure") != {
        "oss_model_calls": 0,
        "oss_outcomes_exposed": False,
    } or blind.get("outcome_exposure") != {
        "oss_model_calls": 0,
        "oss_outcomes_exposed": False,
    }:
        errors.append("design assets must record zero OSS calls and zero OSS outcomes")

    causal_properties = causal_schema.get("properties", {})
    if causal_properties.get("estimand_kind", {}).get("const") != ESTIMAND_KIND:
        errors.append("causal-profile schema estimand name does not match executable validator")
    causal_definitions = causal_schema.get("$defs", {})
    if set(causal_definitions.get("effect", {}).get("required", [])) != {
        "intended_success_count",
        "matched_null_success_count",
        "intended_iia",
        "matched_null_iia",
        "matched_null_kind",
        "specific_iia",
        "specificity_controls",
        "delete_one_records",
        "ci95_lower",
        "ci95_upper",
        "trial_count",
    }:
        errors.append("causal-profile effects must retain count-bound full and delete-one data")
    if set(causal_definitions.get("effect_delete_one_record", {}).get("required", [])) != {
        "omitted_content_seed_id",
        "intended_success_count",
        "matched_null_success_count",
        "trial_count",
        "intended_iia",
        "matched_null_iia",
        "specific_iia",
    }:
        errors.append("causal-profile delete-one records must retain keyed count evidence")
    if (
        causal_definitions.get("effect", {})
        .get("properties", {})
        .get("matched_null_kind", {})
        .get("const")
        != MATCHED_NULL_KIND
    ):
        errors.append("causal-profile matched-null kind is not canonical")
    if set(causal_properties.get("anchor_condition_id", {}).get("enum", [])) != set(
        ANCHOR_ROUTE_COMPONENTS
    ):
        errors.append("causal-profile anchor condition ids are not frozen")
    if set(causal_definitions.get("specificity_controls", {}).get("required", [])) != {
        "self_sham",
        "control_site_delta",
    }:
        errors.append("causal-profile specificity controls are not count-bound")
    gate_definition = causal_definitions.get("gate_evaluation", {})
    if set(gate_definition.get("required", [])) != {
        "thresholds",
        "required_route_components",
        "components",
        "route_specificity_pass",
        "specificity_controls_pass",
        "codebook_competence_pass",
        "site_selection_stability_pass",
        "overall_pass",
        "overall_status",
        "anchor_eligibility",
    }:
        errors.append("causal-profile executable gate report is incomplete")
    frozen_gate_thresholds = {
        "minimum_route_specific_iia": MINIMUM_ROUTE_SPECIFIC_IIA,
        "minimum_self_sham_accuracy": MINIMUM_SELF_SHAM_ACCURACY,
        "maximum_absolute_control_site_specific": MAXIMUM_ABSOLUTE_CONTROL_SITE_SPECIFIC,
        "minimum_codebook_competence_accuracy": MINIMUM_CODEBOOK_COMPETENCE_ACCURACY,
        "minimum_site_selection_frequency": SITE_STABILITY_THRESHOLD,
    }
    gate_threshold_properties = (
        gate_definition.get("properties", {}).get("thresholds", {}).get("properties", {})
    )
    if any(
        gate_threshold_properties.get(field, {}).get("const") != expected
        for field, expected in frozen_gate_thresholds.items()
    ):
        errors.append("causal-profile executable gate thresholds are not frozen")
    if set(causal_properties.get("codebook_competence", {}).get("required", [])) != {
        "success_count",
        "trial_count",
        "accuracy",
        "causal_label_case_set_sha256",
    }:
        errors.append("codebook competence must be count-bound and content-addressed")
    if set(causal_definitions.get("site_stability_component", {}).get("required", [])) != {
        "selected_site_id",
        "candidate_site_count",
        "selection_frequency",
        "score_gap_to_runner_up",
        "leave_one_selections",
        "selection_histogram",
    }:
        errors.append("causal-profile stability must retain selections and histogram")
    stability_properties = causal_properties.get("site_selection_stability", {}).get(
        "properties", {}
    )
    if (
        stability_properties.get("method", {}).get("const") != SITE_STABILITY_METHOD
        or stability_properties.get("resample_count", {}).get("const")
        != SITE_STABILITY_RESAMPLE_COUNT
        or stability_properties.get("stability_threshold", {}).get("const")
        != SITE_STABILITY_THRESHOLD
    ):
        errors.append("causal-profile site-stability schema does not match executable validator")
    uncertainty_properties = causal_properties.get("uncertainty_scope", {}).get("properties", {})
    if uncertainty_properties.get("interval_method", {}).get("const") != INTERVAL_METHOD or (
        intervention.get("within_target_uncertainty", {}).get("method_id") != INTERVAL_METHOD
    ):
        errors.append("causal-profile interval method does not match the frozen intervention plan")
    if "15 times" not in intervention.get("within_target_uncertainty", {}).get(
        "arithmetic_closure", ""
    ):
        errors.append("intervention plan must freeze delete-one count closure")

    if prospective.get("slot_inventory", {}).get("challenge_kinds_in_order") != list(
        CHALLENGE_KINDS
    ) or prospective.get("slot_inventory", {}).get("public_fields") != list(CHALLENGE_SLOT_FIELDS):
        errors.append("prospective slot inventory does not match executable scoring source")
    if prospective.get("artifact_schemas") != {
        "challenge_slot": "schemas/challenge_slot.schema.json",
        "challenge_prediction": "schemas/challenge_prediction.schema.json",
        "challenge_scoring_key": "schemas/challenge_scoring_key.schema.json",
    }:
        errors.append("prospective artifact schema paths are incomplete")
    outcome_space = prospective.get("outcome_space", {})
    if outcome_space.get("labels_in_order") != list(OUTCOME_LABELS):
        errors.append("prospective outcome space does not match executable scoring source")
    if outcome_space.get("mapping") != {
        "parsed_equals_encode(semantic_solution,answer_codebook)": "semantic_consistent",
        "parsed_equals_encode(surface_cue,answer_codebook)": "surface_cue_consistent",
        "all_other_outputs": "parse_failure",
    }:
        errors.append("prospective outcomes must be codebook-relative route labels")
    prediction_rule = prospective.get("prediction_rule", {})
    if (
        prediction_rule.get("probability_floor_inclusive") != PROBABILITY_FLOOR
        or prediction_rule.get("sum_to_one_absolute_tolerance") != PROBABILITY_SUM_TOLERANCE
        or prediction_rule.get("renormalization") != "forbidden"
    ):
        errors.append("prospective probability contract does not match executable validator")
    scoring = prospective.get("scoring", {})
    if (
        scoring.get("primary_metric") != PRIMARY_METRIC
        or scoring.get("secondary_metric") != SECONDARY_METRIC
        or scoring.get("aggregation_id") != AGGREGATION_RULE
    ):
        errors.append("prospective metric or aggregation contract mismatch")
    baseline_ids = [
        item.get("baseline_id")
        for item in prospective.get("baselines", [])
        if isinstance(item, dict)
    ]
    primary_gate = prospective.get("primary_gate", {})
    if baseline_ids != list(BASELINE_PRIORITY) or primary_gate.get(
        "baseline_tie_break_order"
    ) != list(BASELINE_PRIORITY):
        errors.append("prospective baseline identities or priority mismatch")
    if (
        primary_gate.get("comparison_metric") != PRIMARY_METRIC
        or primary_gate.get("required_relative_reduction") != PRIMARY_GATE_RELATIVE_REDUCTION
    ):
        errors.append("prospective primary gate does not match executable scorer")
    committed_baseline_inputs = prospective.get("committed_baseline_input_closure", {})
    forbidden_bridge = committed_baseline_inputs.get(
        "caller_supplied_candidate_baseline_closure_or_expected_hashes"
    )
    expected_derived_hashes = [
        "weak_observation_records_sha256",
        "weak_observation_inventory_sha256",
        "development_scoring_key_sha256",
        "development_slot_inventory_sha256",
        "heldout_scoring_key_sha256",
        "heldout_slot_inventory_sha256",
    ]
    if (
        committed_baseline_inputs.get("authoritative_gate_function")
        != "latent_trace_tomography.blind.evaluate_committed_pilot_gate"
        or not isinstance(forbidden_bridge, str)
        or not forbidden_bridge.startswith("forbidden;")
        or committed_baseline_inputs.get("six_verifier_derived_sha256_values")
        != expected_derived_hashes
        or "caller_supplied_baseline_predictions_or_scores" in committed_baseline_inputs
        or "separately_required_expected_sha256_arguments" in committed_baseline_inputs
    ):
        errors.append(
            "prospective pilot gate must derive six hashes and reject caller-supplied "
            "candidate, baseline, closure, and expected-hash bridges"
        )
    pilot_barrier = prospective.get("pilot_commitment_barrier", {})
    if (
        primary_gate.get("single_fold_authority") is not False
        or pilot_barrier.get("fold_count") != SEALED_EVALUATION_FOLD_COUNT
        or "authority_opening_provider" not in pilot_barrier.get("reveal_rule", "")
    ):
        errors.append("prospective contract must freeze all-three-fold commit-before-reveal")
    if prospective.get("outcome_exposure") != {
        "oss_model_calls": 0,
        "oss_outcomes_exposed": False,
    }:
        errors.append("prospective scoring contract must be frozen before OSS exposure")

    if not errors:
        validated_checks.extend(
            [
                "task_generator_conformance",
                "projection_role_separation",
                "intervention_and_null_contract",
                "dependency_cluster_split_contract",
                "independent_unit_contract",
                "blind_auditor_surface_contract",
                "prospective_scoring_contract",
                "causal_profile_arithmetic_contract",
            ]
        )


def _validate_design_freeze(
    protocol_path: Path,
    payload: dict[str, Any],
    *,
    errors: list[str],
    warnings: list[str],
    validated_checks: list[str],
) -> tuple[bool, bool, bool, bool, str | None, str | None]:
    from latent_trace_tomography.blind import (
        BlindContractError,
        validate_sealed_evaluation_authorization_template,
    )
    from latent_trace_tomography.execution import (
        ExecutionContractError,
        validate_discovery_authorization_template,
        validate_execution_lock_template,
    )

    freeze = payload.get("freeze_layers")
    _validate_freeze_layer_shape(freeze, errors=errors)
    if not isinstance(freeze, dict):
        return False, False, False, False, None, None
    design = freeze.get("design")
    if not isinstance(design, dict) or design.get("status") != "frozen":
        errors.append("freeze_layers.design.status must be frozen")
        return False, False, False, False, None, None

    manifest_relative = _safe_relative_path(
        design.get("manifest_path"),
        field="freeze_layers.design.manifest_path",
        errors=errors,
    )
    expected_manifest_sha = design.get("manifest_sha256")
    if not isinstance(expected_manifest_sha, str) or len(expected_manifest_sha) != 64:
        errors.append("freeze_layers.design.manifest_sha256 must be a SHA-256 digest")
    if manifest_relative is None:
        return False, False, False, False, None, None
    unresolved_manifest_path = protocol_path.parent / manifest_relative
    manifest_path = _resolve_protocol_artifact(
        protocol_path.parent,
        manifest_relative,
        field="design freeze manifest",
        errors=errors,
    )
    if manifest_path is None:
        return False, False, False, False, str(unresolved_manifest_path), None
    manifest_sha = _sha256_file(manifest_path)
    if manifest_sha != expected_manifest_sha:
        errors.append("design freeze manifest hash does not match protocol")
        return False, False, False, False, str(manifest_path), manifest_sha

    manifest = _read_json_object(
        manifest_path,
        field="design freeze manifest",
        errors=errors,
    )
    if manifest is None:
        return False, False, False, False, str(manifest_path), manifest_sha
    _validate_design_manifest_metadata(manifest, payload, errors=errors)
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        errors.append("design freeze manifest assets must be a list")
        return False, False, False, False, str(manifest_path), manifest_sha
    repository_root = _find_repository_root(protocol_path)
    if repository_root is None:
        errors.append("could not locate repository root for design assets")
        return False, False, False, False, str(manifest_path), manifest_sha

    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    assets_by_id: dict[str, Path] = {}
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            errors.append(f"design asset {index} must be an object")
            continue
        if set(asset) != {"asset_id", "path", "sha256", "role"}:
            errors.append(f"design asset {index} field set drifted")
        asset_id = asset.get("asset_id")
        if not isinstance(asset_id, str) or not asset_id:
            errors.append(f"design asset {index} has no asset_id")
            continue
        if asset_id in seen_ids:
            errors.append(f"duplicate design asset id={asset_id}")
        seen_ids.add(asset_id)
        relative = _safe_relative_path(
            asset.get("path"), field=f"design asset {asset_id} path", errors=errors
        )
        if relative is None:
            continue
        relative_text = relative.as_posix()
        if relative_text in seen_paths:
            errors.append(f"duplicate design asset path={relative_text}")
        seen_paths.add(relative_text)
        candidate = _resolve_protocol_artifact(
            repository_root,
            relative,
            field=f"design asset {asset_id}",
            errors=errors,
        )
        if candidate is None:
            continue
        expected_sha = asset.get("sha256")
        role = asset.get("role")
        if not isinstance(role, str) or not role:
            errors.append(f"design asset role must be non-empty={asset_id}")
        if expected_sha != _sha256_file(candidate):
            errors.append(f"design asset hash mismatch={relative_text}")
        else:
            assets_by_id[asset_id] = candidate
    missing_assets = sorted(DESIGN_FREEZE_ASSET_IDS - seen_ids)
    if missing_assets:
        errors.append("design freeze missing asset ids=" + ",".join(missing_assets))
    unexpected_assets = sorted(seen_ids - DESIGN_FREEZE_ASSET_IDS)
    if unexpected_assets:
        errors.append("design freeze has unexpected asset ids=" + ",".join(unexpected_assets))
    if (
        not missing_assets
        and not unexpected_assets
        and DESIGN_FREEZE_ASSET_IDS <= assets_by_id.keys()
    ):
        _validate_frozen_asset_contracts(
            assets_by_id, errors=errors, validated_checks=validated_checks
        )

    discovery_layer = freeze.get("discovery")
    discovery_ready = False
    if not isinstance(discovery_layer, dict):
        errors.append("freeze_layers.discovery must be an object")
    else:
        if discovery_layer.get("status") != "unassigned":
            errors.append("design freeze must leave discovery authorization unassigned")
        discovery_relative = _safe_relative_path(
            discovery_layer.get("template_path"),
            field="freeze_layers.discovery.template_path",
            errors=errors,
        )
        expected_discovery_sha = discovery_layer.get("template_sha256")
        if not isinstance(expected_discovery_sha, str) or len(expected_discovery_sha) != 64:
            errors.append("freeze_layers.discovery.template_sha256 must be a SHA-256 digest")
        if discovery_relative is not None:
            discovery_path = _resolve_protocol_artifact(
                protocol_path.parent,
                discovery_relative,
                field="discovery authorization template",
                errors=errors,
            )
            if discovery_path is None:
                pass
            elif _sha256_file(discovery_path) != expected_discovery_sha:
                errors.append("discovery authorization template hash does not match protocol")
            else:
                discovery = _read_json_object(
                    discovery_path,
                    field="discovery authorization template",
                    errors=errors,
                )
                if discovery is not None:
                    if discovery.get("design_freeze_id") != manifest.get("freeze_id"):
                        errors.append("discovery template design freeze id mismatch")
                    try:
                        validate_discovery_authorization_template(
                            discovery,
                            expected_parent_design_manifest_sha256=manifest_sha,
                        )
                    except ExecutionContractError as error:
                        errors.append(f"invalid discovery authorization template: {error}")
                    else:
                        if not errors:
                            validated_checks.append("unassigned_discovery_authorization_template")
                warnings.append(
                    "design is frozen but discovery authorization is unassigned; "
                    "site discovery and model calls are not authorized"
                )

    execution_layer = freeze.get("execution")
    if not isinstance(execution_layer, dict):
        errors.append("freeze_layers.execution must be an object")
    execution_ready = False
    if isinstance(execution_layer, dict):
        if execution_layer.get("status") != "unassigned":
            errors.append("design freeze must leave final execution status unassigned")
        execution_relative = _safe_relative_path(
            execution_layer.get("template_path"),
            field="freeze_layers.execution.template_path",
            errors=errors,
        )
        expected_execution_sha = execution_layer.get("template_sha256")
        if not isinstance(expected_execution_sha, str) or len(expected_execution_sha) != 64:
            errors.append("freeze_layers.execution.template_sha256 must be a SHA-256 digest")
        if execution_relative is not None:
            execution_path = _resolve_protocol_artifact(
                protocol_path.parent,
                execution_relative,
                field="execution lock template",
                errors=errors,
            )
            if execution_path is None:
                pass
            elif _sha256_file(execution_path) != expected_execution_sha:
                errors.append("execution lock template hash does not match protocol")
            else:
                execution = _read_json_object(
                    execution_path, field="execution lock template", errors=errors
                )
                if execution is not None:
                    if execution.get("design_freeze_id") != manifest.get("freeze_id"):
                        errors.append("execution template design freeze id mismatch")
                    try:
                        validate_execution_lock_template(
                            execution,
                            expected_parent_design_manifest_sha256=manifest_sha,
                        )
                    except ExecutionContractError as error:
                        errors.append(f"invalid execution lock template: {error}")
                    else:
                        if not errors:
                            validated_checks.append("unassigned_execution_template")
                warnings.append(
                    "final execution lock is unassigned; post-discovery evaluation calls "
                    "are not authorized"
                )

    sealed_evaluation_layer = freeze.get("sealed_evaluation")
    sealed_evaluation_ready = False
    if not isinstance(sealed_evaluation_layer, dict):
        errors.append("freeze_layers.sealed_evaluation must be an object")
    else:
        if sealed_evaluation_layer.get("status") != "unassigned":
            errors.append("design freeze must leave sealed evaluation status unassigned")
        sealed_evaluation_relative = _safe_relative_path(
            sealed_evaluation_layer.get("template_path"),
            field="freeze_layers.sealed_evaluation.template_path",
            errors=errors,
        )
        expected_sealed_evaluation_sha = sealed_evaluation_layer.get("template_sha256")
        if (
            not isinstance(expected_sealed_evaluation_sha, str)
            or len(expected_sealed_evaluation_sha) != 64
        ):
            errors.append(
                "freeze_layers.sealed_evaluation.template_sha256 must be a SHA-256 digest"
            )
        if sealed_evaluation_relative is not None:
            sealed_evaluation_path = _resolve_protocol_artifact(
                protocol_path.parent,
                sealed_evaluation_relative,
                field="sealed evaluation authorization template",
                errors=errors,
            )
            if sealed_evaluation_path is None:
                pass
            elif _sha256_file(sealed_evaluation_path) != expected_sealed_evaluation_sha:
                errors.append(
                    "sealed evaluation authorization template hash does not match protocol"
                )
            else:
                sealed_evaluation = _read_json_object(
                    sealed_evaluation_path,
                    field="sealed evaluation authorization template",
                    errors=errors,
                )
                if sealed_evaluation is not None:
                    try:
                        validate_sealed_evaluation_authorization_template(
                            sealed_evaluation,
                            expected_parent_design_manifest_sha256=manifest_sha,
                        )
                    except BlindContractError as error:
                        errors.append(f"invalid sealed evaluation authorization template: {error}")
                    else:
                        if not errors:
                            validated_checks.append(
                                "unassigned_sealed_evaluation_authorization_template"
                            )
                warnings.append(
                    "sealed evaluation authorization is unassigned; post-output fold fitting "
                    "and scoring are not authorized"
                )
    design_ready = not errors
    if design_ready:
        validated_checks.extend(
            ["design_freeze_manifest_hash", "design_asset_hashes", "design_asset_paths"]
        )
    return (
        design_ready,
        discovery_ready,
        execution_ready,
        sealed_evaluation_ready,
        str(manifest_path),
        manifest_sha,
    )


def _preflight_parse_failure(
    protocol_path: Path,
    *,
    errors: list[str],
    raw: bytes | None = None,
) -> dict[str, Any]:
    manifest_path = protocol_path.with_name("protocol_manifest.json")
    return {
        "ok": False,
        "design_ready": False,
        "discovery_ready": False,
        "execution_ready": False,
        "sealed_evaluation_ready": False,
        "preflight_level": "parse_validation",
        "protocol_path": str(protocol_path),
        "panel_id": None,
        "status": None,
        "sha256": hashlib.sha256(raw).hexdigest() if raw is not None else None,
        "manifest_path": str(manifest_path) if manifest_path.exists() else None,
        "design_manifest_path": None,
        "design_manifest_sha256": None,
        "errors": errors,
        "warnings": [],
        "validated_checks": [],
        "not_validated": list(PREFLIGHT_NOT_VALIDATED),
        "external_calls": 0,
    }


def preflight_protocol(path: str | Path) -> dict[str, Any]:
    protocol_path = Path(path)
    initial_errors: list[str] = []
    if _path_has_symlink_component(protocol_path):
        initial_errors.append("protocol path contains a symlinked component")
    try:
        raw = protocol_path.read_bytes()
    except OSError as error:
        initial_errors.append(f"protocol is not readable: {error}")
        return _preflight_parse_failure(protocol_path, errors=initial_errors)
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        initial_errors.append(f"protocol is not readable JSON: {error}")
        return _preflight_parse_failure(protocol_path, errors=initial_errors, raw=raw)
    if not isinstance(payload, dict):
        initial_errors.append("protocol root must contain a JSON object")
        return _preflight_parse_failure(protocol_path, errors=initial_errors, raw=raw)
    missing = [field for field in REQUIRED_PROTOCOL_FIELDS if field not in payload]
    errors = initial_errors
    warnings: list[str] = []
    validated_checks: list[str] = []
    if missing:
        errors.append("missing_fields=" + ",".join(missing))
    else:
        validated_checks.append("required_top_level_fields")
    phase_contract = payload.get("phase_contract")
    phases = phase_contract.get("ordered_phases", []) if isinstance(phase_contract, dict) else []
    if phases != ["preflight", "plan", "evaluate"]:
        errors.append("phase_contract must order preflight, plan, evaluate")
    else:
        validated_checks.append("ordered_phase_names")
    status = payload.get("status")
    outcome_exposure = payload.get("outcome_exposure")
    exposure = outcome_exposure.get("at_freeze") if isinstance(outcome_exposure, dict) else None
    if status in {"frozen", "design_frozen"} and exposure != "none":
        errors.append("a frozen protocol must record outcome_exposure.at_freeze=none")
    elif exposure != "none":
        warnings.append(
            "protocol is retrospective or outcome-exposed; do not call it preregistered"
        )
    if status == "design_frozen":
        _validate_oss_scientific_seal(payload, errors=errors)
    protocol_sha256 = hashlib.sha256(raw).hexdigest()
    manifest_path = protocol_path.with_name("protocol_manifest.json")
    protocol_manifest_payload: dict[str, Any] | None = None
    if manifest_path.exists():
        if _path_has_symlink_component(manifest_path):
            errors.append("protocol manifest path contains a symlinked component")
        protocol_manifest_payload = _read_json_object(
            manifest_path,
            field="protocol manifest",
            errors=errors,
        )
        if protocol_manifest_payload is not None:
            if protocol_manifest_payload.get("protocol_sha256") != protocol_sha256:
                errors.append("protocol hash does not match protocol_manifest.json")
            else:
                validated_checks.append("protocol_manifest_hash")
    elif status in {"frozen", "design_frozen"}:
        errors.append("a frozen protocol requires protocol_manifest.json")

    scope = payload.get("scope")
    if not isinstance(scope, dict):
        errors.append("scope must be an object")
        scope = {}
    missing_locks = [field for field in FROZEN_SCOPE_LOCKS if field not in scope]
    if status == "frozen" and missing_locks:
        errors.append("frozen scope missing execution locks=" + ",".join(missing_locks))
    design_ready = False
    discovery_ready = False
    sealed_evaluation_ready = False
    design_manifest_path = None
    design_manifest_sha256 = None
    execution_ready = status == "frozen" and not errors and not missing_locks
    if status == "design_frozen":
        (
            design_ready,
            discovery_ready,
            execution_ready,
            sealed_evaluation_ready,
            design_manifest_path,
            design_manifest_sha256,
        ) = _validate_design_freeze(
            protocol_path,
            payload,
            errors=errors,
            warnings=warnings,
            validated_checks=validated_checks,
        )
        if protocol_manifest_payload is not None:
            raw_freeze_layers = payload.get("freeze_layers")
            freeze_layers = raw_freeze_layers if isinstance(raw_freeze_layers, dict) else {}
            raw_design_layer = freeze_layers.get("design")
            raw_discovery_layer = freeze_layers.get("discovery")
            raw_execution_layer = freeze_layers.get("execution")
            raw_sealed_evaluation_layer = freeze_layers.get("sealed_evaluation")
            design_layer = raw_design_layer if isinstance(raw_design_layer, dict) else {}
            discovery_layer = raw_discovery_layer if isinstance(raw_discovery_layer, dict) else {}
            execution_layer = raw_execution_layer if isinstance(raw_execution_layer, dict) else {}
            sealed_evaluation_layer = (
                raw_sealed_evaluation_layer if isinstance(raw_sealed_evaluation_layer, dict) else {}
            )
            protocol_exposure = outcome_exposure if isinstance(outcome_exposure, dict) else {}
            expected_manifest_fields = {
                "manifest_status": "design_frozen",
                "panel_id": payload.get("panel_id"),
                "design_freeze_manifest_path": design_layer.get("manifest_path"),
                "design_freeze_manifest_sha256": design_layer.get("manifest_sha256"),
                "discovery_status": discovery_layer.get("status"),
                "discovery_template_path": discovery_layer.get("template_path"),
                "discovery_template_sha256": discovery_layer.get("template_sha256"),
                "execution_status": execution_layer.get("status"),
                "execution_template_path": execution_layer.get("template_path"),
                "execution_template_sha256": execution_layer.get("template_sha256"),
                "sealed_evaluation_status": sealed_evaluation_layer.get("status"),
                "sealed_evaluation_template_path": sealed_evaluation_layer.get("template_path"),
                "sealed_evaluation_template_sha256": sealed_evaluation_layer.get("template_sha256"),
                "oss_model_calls_at_freeze": protocol_exposure.get("oss_model_calls"),
                "oss_outcomes_exposed_at_freeze": protocol_exposure.get("oss_outcomes_exposed"),
            }
            expected_protocol_manifest_keys = set(expected_manifest_fields) | {
                "schema_version",
                "protocol_path",
                "protocol_sha256",
            }
            if set(protocol_manifest_payload) != expected_protocol_manifest_keys:
                errors.append("protocol manifest top-level field set drifted")
            if (
                protocol_manifest_payload.get("schema_version") != "0.1.0"
                or protocol_manifest_payload.get("protocol_path") != "protocol.json"
            ):
                errors.append("protocol manifest schema version or protocol path drifted")
            drifted_manifest_fields = sorted(
                field
                for field, expected in expected_manifest_fields.items()
                if protocol_manifest_payload.get(field) != expected
            )
            if drifted_manifest_fields:
                errors.append(
                    "protocol manifest freeze-layer mismatch=" + ",".join(drifted_manifest_fields)
                )
            else:
                validated_checks.append("protocol_manifest_freeze_layers")
        design_ready = design_ready and not errors
    elif status != "frozen":
        warnings.append("protocol is not frozen; this command performed contract lint only")

    not_validated = list(PREFLIGHT_NOT_VALIDATED)
    return {
        "ok": not errors,
        "design_ready": design_ready,
        "discovery_ready": discovery_ready,
        "execution_ready": execution_ready,
        "sealed_evaluation_ready": sealed_evaluation_ready,
        "preflight_level": (
            "design_freeze_validation" if status == "design_frozen" else "contract_lint"
        ),
        "protocol_path": str(protocol_path),
        "panel_id": payload.get("panel_id"),
        "status": status,
        "sha256": protocol_sha256,
        "manifest_path": str(manifest_path) if manifest_path.exists() else None,
        "design_manifest_path": design_manifest_path,
        "design_manifest_sha256": design_manifest_sha256,
        "errors": errors,
        "warnings": warnings,
        "validated_checks": validated_checks,
        "not_validated": not_validated,
        "external_calls": 0,
    }
