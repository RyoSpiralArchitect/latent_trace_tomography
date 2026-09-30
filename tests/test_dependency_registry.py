from __future__ import annotations

import copy
import json
import unittest
from itertools import combinations
from pathlib import Path

from jsonschema import FormatChecker
from jsonschema.validators import validator_for

from latent_trace_tomography.dependency_registry import (
    CONTRACT_ID,
    DESIGN_FREEZE_ID,
    DESIGN_MANIFEST_SHA256,
    DISCOVERY_TEMPLATE_SHA256,
    DOES_NOT_ESTABLISH,
    PRE_OUTCOME_CORRECTION_ID,
    PRE_OUTCOME_CORRECTION_MANIFEST_SHA256,
    PROTOCOL_SHA256,
    ROLE,
    SCHEMA_VERSION,
    STATUS,
    DependencyRegistryError,
    build_registry_authorization_gate_receipt,
    canonical_artifact_sha256,
    validate_dependency_cluster_registry,
    validate_registry_authorization_binding,
    validate_registry_authorization_gate_receipt,
    validate_registry_authorization_projection,
)

try:
    from test_execution_contract import AUTHORITY_SECRET, _authorization
except ModuleNotFoundError:  # Direct module execution uses the namespace-package path.
    from tests.test_execution_contract import (  # type: ignore[no-redef]
        AUTHORITY_SECRET,
        _authorization,
    )


ROOT = Path(__file__).resolve().parents[1]
OPERATION_ROOT = ROOT / "operations" / "oss1_execution_v1"
REGISTRY_SCHEMA = OPERATION_ROOT / "schemas" / "dependency_cluster_registry.schema.json"
GATE_RECEIPT_SCHEMA = OPERATION_ROOT / "schemas" / "registry_authorization_gate_receipt.schema.json"


def _hash(label: str) -> str:
    return canonical_artifact_sha256({"fixture": label})


def _source_record(
    *, source_record_id: str, source_kind: str, content_sha256: str, evidence_status: str
) -> dict:
    record = {
        "source_record_id": source_record_id,
        "source_kind": source_kind,
        "content_sha256": content_sha256,
        "locator_sha256": _hash(f"locator:{source_record_id}"),
        "evidence_status": evidence_status,
        "recorded_at": "2026-07-17T18:00:00Z",
    }
    record["source_record_sha256"] = canonical_artifact_sha256(record)
    return record


def _close_registry(registry: dict) -> None:
    registry["registry_body_sha256"] = canonical_artifact_sha256(
        {key: value for key, value in registry.items() if key != "registry_body_sha256"}
    )


def _mutate_source(registry: dict, source_record_id: str, **changes: object) -> None:
    source = next(
        row for row in registry["source_records"] if row["source_record_id"] == source_record_id
    )
    old_hash = source["source_record_sha256"]
    source.update(changes)
    source["source_record_sha256"] = canonical_artifact_sha256(
        {key: value for key, value in source.items() if key != "source_record_sha256"}
    )
    new_hash = source["source_record_sha256"]

    def replace(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if item == old_hash:
                    value[key] = new_hash
                else:
                    replace(item)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if item == old_hash:
                    value[index] = new_hash
                else:
                    replace(item)

    replace(registry)
    _close_registry(registry)


def _registry() -> dict:
    authorization = _authorization()
    projection = {
        field: copy.deepcopy(authorization[field])
        for field in (
            "architecture_families",
            "model_registry",
            "learned_state_ancestry",
            "dependency_graph",
            "dependency_clusters",
            "nuisance_balance_contract",
        )
    }
    projection["projection_sha256"] = canonical_artifact_sha256(projection)
    models = projection["model_registry"]
    cluster_by_unit = {
        unit_id: cluster["dependency_cluster_id"]
        for cluster in projection["dependency_clusters"]
        for unit_id in cluster["model_unit_ids"]
    }

    source_records: list[dict] = []
    candidates: list[dict] = []
    source_by_name: dict[str, dict] = {}

    def add_source(name: str, kind: str, content: str, status: str) -> dict:
        source = _source_record(
            source_record_id=name,
            source_kind=kind,
            content_sha256=content,
            evidence_status=status,
        )
        source_records.append(source)
        source_by_name[name] = source
        return source

    task_content = _hash("frozen-task-manifest")
    shared_sources = {
        "ancestry": add_source(
            "shared-ancestry",
            "ancestry_manifest",
            projection["learned_state_ancestry"]["inventory_sha256"],
            "complete_content_addressed",
        ),
        "exposure": add_source(
            "shared-exposure",
            "evaluation_exposure_scan_manifest",
            _hash("exposure"),
            "complete_content_addressed",
        ),
        "overlap": add_source(
            "shared-overlap",
            "overlap_scan_manifest",
            _hash("overlap"),
            "complete_content_addressed",
        ),
        "pair_rng": add_source(
            "shared-pair-rng", "rng_manifest", _hash("pair-rng"), "complete_content_addressed"
        ),
        "task_relation": add_source(
            "shared-task-relation",
            "task_manifest",
            task_content,
            "complete_content_addressed",
        ),
    }

    for model in models:
        model_id = model["model_unit_id"]
        checkpoint = add_source(
            f"checkpoint:{model_id}",
            "checkpoint_manifest",
            model["configuration_sha256"],
            "complete_content_addressed",
        )
        rng_content = _hash(f"rng:{model_id}")
        rng = add_source(
            f"rng:{model_id}", "rng_manifest", rng_content, "complete_content_addressed"
        )
        training_data = add_source(
            f"training-data:{model_id}",
            "training_data_manifest",
            model["anchor_provenance"]["training_data_sha256"],
            "complete_content_addressed",
        )
        task = add_source(
            f"task:{model_id}", "task_manifest", task_content, "complete_content_addressed"
        )
        candidates.append(
            {
                "model_unit_id": model_id,
                "enrollment_status": "eligible",
                "exclusion_reason_ids": [],
                "checkpoint_provenance": {
                    "checkpoint_role": "fine_tune",
                    "checkpoint_manifest_sha256": checkpoint["content_sha256"],
                    "training_run_parent_id": model["independent_training_run_id"],
                    "parent_checkpoint_artifact_sha256": [],
                    "step_or_token_count": 1000,
                    "created_at": "2026-07-16T00:00:00Z",
                    "source_record_sha256": checkpoint["source_record_sha256"],
                },
                "training_randomness": {
                    "evidence_status": "exact_manifest",
                    "rng_manifest_sha256": rng_content,
                    "initialization_state_artifact_sha256": model["shared_base_artifact_sha256"],
                    "seed_values_disclosed": False,
                    "source_record_sha256": rng["source_record_sha256"],
                },
                "training_data_stages": [
                    {
                        "stage_id": "anchor-posttraining",
                        "scope": "anchor_posttraining",
                        "manifest_status": "complete_for_declared_stage",
                        "manifest_sha256": training_data["content_sha256"],
                        "record_identity_scheme_id": "sha256_canonical_training_record_v1",
                        "record_count": 100,
                        "source_record_sha256": training_data["source_record_sha256"],
                    }
                ],
                "task_provenance": {
                    "task_manifest_sha256": task_content,
                    "generator_artifact_sha256": _hash("generator"),
                    "template_set_sha256": _hash("template-set"),
                    "source_record_sha256": task["source_record_sha256"],
                },
            }
        )

    source_records.sort(key=lambda item: item["source_record_id"])
    candidates.sort(key=lambda item: item["model_unit_id"])
    eligible_ids = [item["model_unit_id"] for item in candidates]
    candidates_by_id = {item["model_unit_id"]: item for item in candidates}

    pairs: list[dict] = []
    for left, right in combinations(eligible_ids, 2):
        same_cluster = cluster_by_unit[left] == cluster_by_unit[right]
        left_data = candidates_by_id[left]["training_data_stages"][0]["manifest_sha256"]
        right_data = candidates_by_id[right]["training_data_stages"][0]["manifest_sha256"]
        data_overlap = same_cluster or left_data == right_data
        pairs.append(
            {
                "left_model_unit_id": left,
                "right_model_unit_id": right,
                "learned_state": {
                    "path_status": (
                        "path_present" if same_cluster else "no_path_in_declared_inventory"
                    ),
                    "relationship_kinds": ["shared_learned_weights"] if same_cluster else [],
                    "evidence_record_sha256": [shared_sources["ancestry"]["source_record_sha256"]],
                },
                "training_randomness": {
                    "relation": "different_rng_manifest",
                    "same_initialization_state": same_cluster,
                    "evidence_record_sha256": shared_sources["pair_rng"]["source_record_sha256"],
                },
                "training_data": {
                    "result": (
                        "exact_overlap"
                        if data_overlap
                        else "no_exact_overlap_within_declared_scope"
                    ),
                    "declared_scope": "anchor_posttraining",
                    "identity_scheme_id": "sha256_canonical_training_record_v1",
                    "left_count": 100,
                    "right_count": 100,
                    "intersection_count": 100 if data_overlap else 0,
                    "left_overlap_fraction": 1.0 if data_overlap else 0.0,
                    "right_overlap_fraction": 1.0 if data_overlap else 0.0,
                    "intentional_common_exposure": data_overlap,
                    "evidence_record_sha256": shared_sources["overlap"]["source_record_sha256"],
                },
                "task_relation": {
                    "result": "same_frozen_task",
                    "evidence_record_sha256": shared_sources["task_relation"][
                        "source_record_sha256"
                    ],
                },
                "handling": (
                    "same_dependency_cluster" if same_cluster else "shared_design_nuisance"
                ),
            }
        )

    exposure = [
        {
            "model_unit_id": model_id,
            "exact_live_prompt_overlap": "no_overlap_within_complete_manifest",
            "frozen_generator_artifact_exposure": "absent_within_declared_scope",
            "frozen_template_exposure": "absent_within_declared_scope",
            "abstract_task_family_exposure": "present",
            "checkpoint_precedes_design_freeze": True,
            "evidence_record_sha256": shared_sources["exposure"]["source_record_sha256"],
            "eligibility_decision": "eligible",
            "reason_ids": [],
        }
        for model_id in eligible_ids
    ]

    bindings: list[dict] = []
    model_index = {model["model_unit_id"]: index for index, model in enumerate(models)}
    for source in source_records:
        source_id = source["source_record_id"]
        pointer = None
        status = "registry_body_bound"
        material = True
        if source_id.startswith("checkpoint:"):
            model_id = source_id.removeprefix("checkpoint:")
            pointer = f"/model_registry/{model_index[model_id]}/configuration_sha256"
            material = True
            status = "authorization_projection_bound"
        elif source_id.startswith("training-data:"):
            model_id = source_id.removeprefix("training-data:")
            pointer = (
                f"/model_registry/{model_index[model_id]}/anchor_provenance/training_data_sha256"
            )
            material = True
            status = "authorization_projection_bound"
        bindings.append(
            {
                "assertion_id": f"classify:{source_id}",
                "source_record_sha256": source["source_record_sha256"],
                "authorization_json_pointer": pointer,
                "binding_status": status,
                "material_for_eligibility": material,
            }
        )
    bindings.sort(key=lambda item: item["assertion_id"])

    registry = {
        "schema_version": SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "role": ROLE,
        "status": STATUS,
        "registry_id": "oss1-registry-fixture-a",
        "created_at": "2026-07-17T19:30:00Z",
        "evidence_cutoff_at": "2026-07-17T19:00:00Z",
        "parent": {
            "design_freeze_id": DESIGN_FREEZE_ID,
            "design_manifest_sha256": DESIGN_MANIFEST_SHA256,
            "protocol_sha256": PROTOCOL_SHA256,
            "discovery_template_sha256": DISCOVERY_TEMPLATE_SHA256,
            "pre_outcome_correction_id": PRE_OUTCOME_CORRECTION_ID,
            "pre_outcome_correction_manifest_sha256": (PRE_OUTCOME_CORRECTION_MANIFEST_SHA256),
        },
        "outcome_exposure": {
            "oss_model_calls": 0,
            "oss_outcomes_exposed": False,
            "discovery_authorization_issued": False,
        },
        "epistemic_boundary": {
            "cluster_meaning": ("connected component of authority-declared learned-state ancestry"),
            "primary_independent_unit": "dependency_cluster_id",
            "independence_certified": False,
            "does_not_establish": list(DOES_NOT_ESTABLISH),
            "unknown_dependency_policy": (
                "conservatively cluster or exclude; never split or increase effective n"
            ),
        },
        "source_records": source_records,
        "candidate_model_units": candidates,
        "eligible_model_unit_ids": eligible_ids,
        "pairwise_relatedness": pairs,
        "evaluation_exposure_assessments": exposure,
        "authorization_projection": projection,
        "binding_map": bindings,
        "limitations": sorted(
            [
                "authority-declared ancestry completeness is not externally proven",
                "different seeds or checkpoints do not prove independence",
                "shared data or task exposure is a common influence, not a learned-state edge in v0",
            ]
        ),
    }
    registry["registry_body_sha256"] = canonical_artifact_sha256(registry)
    return registry


class DependencyRegistryTests(unittest.TestCase):
    def test_valid_registry_closes_to_three_effective_units_without_independence_claim(
        self,
    ) -> None:
        result = validate_dependency_cluster_registry(_registry())
        self.assertTrue(result["ok"])
        self.assertEqual(result["eligible_model_unit_count"], 9)
        self.assertEqual(result["dependency_cluster_count"], 3)
        self.assertEqual(result["effective_n"], 3)
        self.assertEqual(result["material_source_count"], len(_registry()["source_records"]))
        self.assertFalse(result["independence_certified"])
        self.assertFalse(result["model_calls_authorized"])

    def test_registry_schema_and_fixture_validate_with_formats(self) -> None:
        schema = json.loads(REGISTRY_SCHEMA.read_text(encoding="utf-8"))
        validator_cls = validator_for(schema)
        validator_cls.check_schema(schema)
        validator_cls(schema, format_checker=FormatChecker()).validate(_registry())

        authorization = _authorization()
        receipt = build_registry_authorization_gate_receipt(
            _registry(),
            authorization,
            authority_secret=AUTHORITY_SECRET,
            issued_at="2026-07-17T20:05:00Z",
        )
        receipt_schema = json.loads(GATE_RECEIPT_SCHEMA.read_text(encoding="utf-8"))
        receipt_validator_cls = validator_for(receipt_schema)
        receipt_validator_cls.check_schema(receipt_schema)
        receipt_validator_cls(
            receipt_schema,
            format_checker=FormatChecker(),
        ).validate(receipt)

    def test_registry_is_self_addressed_and_parent_bound(self) -> None:
        registry = _registry()
        registry["limitations"].append("post-hash mutation")
        registry["limitations"].sort()
        with self.assertRaisesRegex(DependencyRegistryError, "not self-addressed"):
            validate_dependency_cluster_registry(registry)

        parent = _registry()
        parent["parent"]["design_manifest_sha256"] = "a" * 64
        parent["registry_body_sha256"] = canonical_artifact_sha256(
            {key: value for key, value in parent.items() if key != "registry_body_sha256"}
        )
        with self.assertRaisesRegex(DependencyRegistryError, "parent"):
            validate_dependency_cluster_registry(parent)

        correction_parent = _registry()
        correction_parent["parent"]["pre_outcome_correction_manifest_sha256"] = "b" * 64
        _close_registry(correction_parent)
        with self.assertRaisesRegex(DependencyRegistryError, "parent"):
            validate_dependency_cluster_registry(correction_parent)

    def test_pair_inventory_and_initialization_state_fail_closed(self) -> None:
        missing = _registry()
        missing["pairwise_relatedness"].pop()
        missing["registry_body_sha256"] = canonical_artifact_sha256(
            {key: value for key, value in missing.items() if key != "registry_body_sha256"}
        )
        with self.assertRaisesRegex(DependencyRegistryError, "all 36"):
            validate_dependency_cluster_registry(missing)

        cross = _registry()
        pair = next(
            row
            for row in cross["pairwise_relatedness"]
            if row["handling"] == "shared_design_nuisance"
        )
        pair["training_randomness"]["same_initialization_state"] = True
        cross["registry_body_sha256"] = canonical_artifact_sha256(
            {key: value for key, value in cross.items() if key != "registry_body_sha256"}
        )
        with self.assertRaisesRegex(DependencyRegistryError, "initialization-state relation"):
            validate_dependency_cluster_registry(cross)

    def test_no_overlap_claim_needs_complete_scan_and_closed_arithmetic(self) -> None:
        registry = _registry()
        pair = next(
            row
            for row in registry["pairwise_relatedness"]
            if row["training_data"]["result"] == "no_exact_overlap_within_declared_scope"
        )
        pair["training_data"]["left_overlap_fraction"] = 0.25
        registry["registry_body_sha256"] = canonical_artifact_sha256(
            {key: value for key, value in registry.items() if key != "registry_body_sha256"}
        )
        with self.assertRaisesRegex(DependencyRegistryError, "does not close"):
            validate_dependency_cluster_registry(registry)

        incomplete = _registry()
        overlap_source = next(
            row
            for row in incomplete["source_records"]
            if row["source_record_id"] == "shared-overlap"
        )
        old_hash = overlap_source["source_record_sha256"]
        overlap_source["evidence_status"] = "partial_content_addressed"
        overlap_source["source_record_sha256"] = canonical_artifact_sha256(
            {key: value for key, value in overlap_source.items() if key != "source_record_sha256"}
        )
        new_hash = overlap_source["source_record_sha256"]
        for row in incomplete["pairwise_relatedness"]:
            row["training_data"]["evidence_record_sha256"] = new_hash
        for row in incomplete["binding_map"]:
            if row["source_record_sha256"] == old_hash:
                row["source_record_sha256"] = new_hash
        incomplete["registry_body_sha256"] = canonical_artifact_sha256(
            {key: value for key, value in incomplete.items() if key != "registry_body_sha256"}
        )
        with self.assertRaisesRegex(DependencyRegistryError, "complete_content_addressed"):
            validate_dependency_cluster_registry(incomplete)

    def test_exposure_cannot_be_relabelled_eligible(self) -> None:
        registry = _registry()
        registry["evaluation_exposure_assessments"][0]["exact_live_prompt_overlap"] = (
            "overlap_present"
        )
        registry["registry_body_sha256"] = canonical_artifact_sha256(
            {key: value for key, value in registry.items() if key != "registry_body_sha256"}
        )
        with self.assertRaisesRegex(DependencyRegistryError, "eligibility"):
            validate_dependency_cluster_registry(registry)

    def test_pair_overlap_and_task_claims_are_derived_from_candidate_manifests(self) -> None:
        overlap = _registry()
        candidates = {row["model_unit_id"]: row for row in overlap["candidate_model_units"]}
        pair = next(
            row
            for row in overlap["pairwise_relatedness"]
            if candidates[row["left_model_unit_id"]]["training_data_stages"][0]["manifest_sha256"]
            == candidates[row["right_model_unit_id"]]["training_data_stages"][0]["manifest_sha256"]
        )
        pair["training_data"].update(
            {
                "result": "no_exact_overlap_within_declared_scope",
                "intersection_count": 0,
                "left_overlap_fraction": 0.0,
                "right_overlap_fraction": 0.0,
                "intentional_common_exposure": False,
            }
        )
        _close_registry(overlap)
        with self.assertRaisesRegex(DependencyRegistryError, "identical candidate"):
            validate_dependency_cluster_registry(overlap)

        task = _registry()
        task["pairwise_relatedness"][0]["task_relation"]["result"] = "different_task"
        _close_registry(task)
        with self.assertRaisesRegex(DependencyRegistryError, "identical candidate task"):
            validate_dependency_cluster_registry(task)

    def test_checkpoint_chronology_is_derived_and_fail_closed(self) -> None:
        future = _registry()
        future["candidate_model_units"][0]["checkpoint_provenance"]["created_at"] = (
            "2030-01-01T00:00:00Z"
        )
        _close_registry(future)
        with self.assertRaisesRegex(DependencyRegistryError, "postdate"):
            validate_dependency_cluster_registry(future)

        freeze_day = _registry()
        freeze_day["candidate_model_units"][0]["checkpoint_provenance"]["created_at"] = (
            "2026-07-17T00:00:00Z"
        )
        _close_registry(freeze_day)
        with self.assertRaisesRegex(DependencyRegistryError, "precede the frozen design"):
            validate_dependency_cluster_registry(freeze_day)

        exposure_contradiction = _registry()
        exposure_contradiction["evaluation_exposure_assessments"][0][
            "checkpoint_precedes_design_freeze"
        ] = False
        _close_registry(exposure_contradiction)
        with self.assertRaisesRegex(DependencyRegistryError, "contradicts checkpoint chronology"):
            validate_dependency_cluster_registry(exposure_contradiction)

    def test_claim_bearing_sources_require_the_right_kind_and_complete_status(self) -> None:
        unavailable_ancestry = _registry()
        _mutate_source(
            unavailable_ancestry,
            "shared-ancestry",
            evidence_status="unavailable",
        )
        with self.assertRaisesRegex(DependencyRegistryError, "evidence_status"):
            validate_dependency_cluster_registry(unavailable_ancestry)

        unrelated_ancestry = _registry()
        _mutate_source(
            unrelated_ancestry,
            "shared-ancestry",
            content_sha256=_hash("unrelated-ancestry-inventory"),
        )
        with self.assertRaisesRegex(DependencyRegistryError, "projected ancestry inventory"):
            validate_dependency_cluster_registry(unrelated_ancestry)

        unavailable_exposure = _registry()
        _mutate_source(
            unavailable_exposure,
            "shared-exposure",
            evidence_status="unavailable",
        )
        with self.assertRaisesRegex(DependencyRegistryError, "evidence_status"):
            validate_dependency_cluster_registry(unavailable_exposure)

        wrong_overlap_kind = _registry()
        _mutate_source(
            wrong_overlap_kind,
            "shared-overlap",
            source_kind="environment_manifest",
        )
        with self.assertRaisesRegex(DependencyRegistryError, "source_kind"):
            validate_dependency_cluster_registry(wrong_overlap_kind)

        unavailable_checkpoint = _registry()
        checkpoint_id = next(
            row["source_record_id"]
            for row in unavailable_checkpoint["source_records"]
            if row["source_record_id"].startswith("checkpoint:")
        )
        _mutate_source(
            unavailable_checkpoint,
            checkpoint_id,
            evidence_status="unavailable",
        )
        with self.assertRaisesRegex(DependencyRegistryError, "evidence_status"):
            validate_dependency_cluster_registry(unavailable_checkpoint)

    def test_used_source_materiality_cannot_be_downgraded(self) -> None:
        registry = _registry()
        binding = next(
            row
            for row in registry["binding_map"]
            if row["assertion_id"] == "classify:shared-ancestry"
        )
        binding["binding_status"] = "supplementary_non_authoritative"
        binding["material_for_eligibility"] = False
        binding["authorization_json_pointer"] = None
        _close_registry(registry)
        with self.assertRaisesRegex(DependencyRegistryError, "materiality"):
            validate_dependency_cluster_registry(registry)

    def test_later_authorization_must_equal_registry_projection(self) -> None:
        registry = _registry()
        authorization = _authorization()
        validate_registry_authorization_projection(registry, authorization)
        receipt = build_registry_authorization_gate_receipt(
            registry,
            authorization,
            authority_secret=AUTHORITY_SECRET,
            issued_at="2026-07-17T20:05:00Z",
        )
        validate_registry_authorization_binding(
            registry,
            authorization,
            gate_receipt=receipt,
            authority_secret=AUTHORITY_SECRET,
        )

        drift = copy.deepcopy(authorization)
        drift["architecture_families"] = list(reversed(drift["architecture_families"]))
        with self.assertRaisesRegex(DependencyRegistryError, "drifted"):
            validate_registry_authorization_binding(
                registry,
                drift,
                gate_receipt=receipt,
                authority_secret=AUTHORITY_SECRET,
            )

    def test_gate_receipt_binds_registry_body_authorization_hash_and_authority(self) -> None:
        registry = _registry()
        authorization = _authorization()
        receipt = build_registry_authorization_gate_receipt(
            registry,
            authorization,
            authority_secret=AUTHORITY_SECRET,
            issued_at="2026-07-17T20:05:00Z",
        )
        validate_registry_authorization_gate_receipt(
            registry,
            authorization,
            receipt,
            authority_secret=AUTHORITY_SECRET,
        )

        registry_drift = copy.deepcopy(registry)
        registry_drift["limitations"].append("new post-receipt evidence assertion")
        registry_drift["limitations"].sort()
        _close_registry(registry_drift)
        with self.assertRaisesRegex(DependencyRegistryError, "registry_body_sha256"):
            validate_registry_authorization_gate_receipt(
                registry_drift,
                authorization,
                receipt,
                authority_secret=AUTHORITY_SECRET,
            )

        authorization_drift = copy.deepcopy(authorization)
        authorization_drift["environment_lock"]["hardware_fingerprint_sha256"] = "a" * 64
        with self.assertRaisesRegex(DependencyRegistryError, "authorization_sha256"):
            validate_registry_authorization_gate_receipt(
                registry,
                authorization_drift,
                receipt,
                authority_secret=AUTHORITY_SECRET,
            )

        forged = copy.deepcopy(receipt)
        forged["issued_at"] = "2026-07-17T20:06:00Z"
        forged["receipt_sha256"] = canonical_artifact_sha256(
            {key: value for key, value in forged.items() if key != "receipt_sha256"}
        )
        with self.assertRaisesRegex(DependencyRegistryError, "HMAC"):
            validate_registry_authorization_gate_receipt(
                registry,
                authorization,
                forged,
                authority_secret=AUTHORITY_SECRET,
            )


if __name__ == "__main__":
    unittest.main()
