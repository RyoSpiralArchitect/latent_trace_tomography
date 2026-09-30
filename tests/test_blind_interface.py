from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from jsonschema import ValidationError
from jsonschema.validators import validator_for

from latent_trace_tomography.blind import (
    AUTHORITY_COMMITMENT_CONFORMANCE_VECTOR,
    AUTHORITY_COMMITMENT_SCHEME,
    CAPABILITY_SECURITY_CONTRACT,
    FOLD_WORKER_CAPABILITY_CONTRACT,
    OUTPUT_RUNTIME_EVIDENCE_BOUNDARY,
    REQUIRED_AUDITOR_ARTIFACT_ROLES,
    BlindContractError,
    _aggregate_equal_three_fold_gate,
    _assert_no_private_identifier_leak,
    _derive_sealed_evaluation_material,
    build_authority_precommitments,
    build_blind_bundle_manifest,
    build_evaluation_commitment,
    build_sealed_evaluation_authorization,
    derive_pairing_token,
    evaluate_committed_candidate_gate,
    evaluate_committed_pilot_gate,
    validate_auditor_observations,
    validate_blind_bundle_manifest,
    validate_evaluation_commitment,
    verify_sealed_evaluation_authorization,
    verify_commitment_closure,
)
from latent_trace_tomography.execution import canonical_artifact_sha256
from latent_trace_tomography.oss_design import (
    build_oss_design,
    derive_live_content_seeds,
)
from latent_trace_tomography.prospective import (
    DEVELOPMENT_BASELINE_ID,
    PRIMARY_METRIC,
    SECONDARY_METRIC,
    WEAK_ORBIT_BASELINE_ID,
    derive_relational_challenge_outcome,
    evaluate_verified_candidate_gate,
)
from latent_trace_tomography.split import partition_content_seeds

try:
    from test_execution_contract import (
        AUTHORITY_SECRET as INTEGRATION_AUTHORITY_SECRET,
        PROSPECTIVE_HASHES as INTEGRATION_PROSPECTIVE_HASHES,
        _authorization as _integration_discovery_authorization,
        _execution_lock as _integration_execution_lock,
        _report as _integration_site_report,
        _trusted_kwargs as _integration_trusted_kwargs,
    )
except ModuleNotFoundError:  # Direct module execution uses the namespace-package path.
    from tests.test_execution_contract import (  # type: ignore[no-redef]
        AUTHORITY_SECRET as INTEGRATION_AUTHORITY_SECRET,
        PROSPECTIVE_HASHES as INTEGRATION_PROSPECTIVE_HASHES,
        _authorization as _integration_discovery_authorization,
        _execution_lock as _integration_execution_lock,
        _report as _integration_site_report,
        _trusted_kwargs as _integration_trusted_kwargs,
    )


TARGET_A = "0" * 32
TARGET_B = "1" * 32
TARGET_C = "2" * 32
CLUSTER_C = "dependency-cccccccccccccccc"
CONTRACT_HASHES = {
    "challenge_slot_schema_sha256": "e" * 64,
    "prediction_schema_sha256": "a" * 64,
    "scoring_key_schema_sha256": "b" * 64,
    "scoring_contract_sha256": "c" * 64,
    "scoring_source_sha256": "f" * 64,
}


def _jsonl_bytes(rows: list[dict]) -> bytes:
    return b"".join(json.dumps(row, sort_keys=True).encode("utf-8") + b"\n" for row in rows)


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )


def _self_address(value: dict, field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _auditor_rows() -> list[dict[str, str]]:
    return [
        {
            "target_id": TARGET_A,
            "case_id": "2" * 32,
            "projection_id": "3" * 32,
            "replicate_id": "4" * 32,
            "prompt_text": "Evidence A supports option one. Choose one or two.",
            "output_text": "FINAL: A",
        },
        {
            "target_id": TARGET_B,
            "case_id": "5" * 32,
            "projection_id": "6" * 32,
            "replicate_id": "7" * 32,
            "prompt_text": "Evidence B supports option two. Choose one or two.",
            "output_text": "FINAL: B",
        },
    ]


def _challenge_slots() -> list[dict[str, str]]:
    return [
        {
            "target_id": target,
            "challenge_slot_id": f"{slot:032x}",
            "challenge_kind": kind,
        }
        for target, slot, kind in (
            (TARGET_A, 10, "heldout_cue_conflict"),
            (TARGET_A, 11, "heldout_mismatch_table"),
            (TARGET_B, 12, "heldout_cue_conflict"),
            (TARGET_B, 13, "heldout_mismatch_table"),
        )
    ]


def _predictions() -> list[dict]:
    return [
        {
            "schema_version": "0.1.0",
            **slot,
            "probabilities": {
                "semantic_consistent": 0.7,
                "surface_cue_consistent": 0.2,
                "parse_failure": 0.1,
            },
            "abstain": False,
            "abstention_reason": None,
        }
        for slot in _challenge_slots()
    ]


def _scoring_key() -> list[dict]:
    return [
        {
            "schema_version": "0.1.0",
            **slot,
            "dependency_cluster_id": (
                "dependency-aaaaaaaaaaaaaaaa"
                if slot["target_id"] == TARGET_A
                else "dependency-bbbbbbbbbbbbbbbb"
            ),
            "outcome_counts": {
                "semantic_consistent": 7,
                "surface_cue_consistent": 2,
                "parse_failure": 1,
            },
            "trial_count": 10,
        }
        for slot in _challenge_slots()
    ]


def _development_slots() -> list[dict[str, str]]:
    return [
        {
            "target_id": TARGET_C,
            "challenge_slot_id": f"{slot:032x}",
            "challenge_kind": kind,
        }
        for slot, kind in (
            (100, "heldout_cue_conflict"),
            (101, "heldout_mismatch_table"),
        )
    ]


def _development_scoring_key(*, dependency_cluster_id: str = CLUSTER_C) -> list[dict]:
    return [
        {
            "schema_version": "0.1.0",
            **slot,
            "dependency_cluster_id": dependency_cluster_id,
            "outcome_counts": {
                "semantic_consistent": 3,
                "surface_cue_consistent": 3,
                "parse_failure": 4,
            },
            "trial_count": 10,
        }
        for slot in _development_slots()
    ]


def _artifact_paths() -> dict[str, str]:
    return {role: f"artifacts/{role}.bin" for role in REQUIRED_AUDITOR_ARTIFACT_ROLES}


def _fake_sealed_authorization(
    *,
    bundle_sha256: str,
    authority_commitments: dict[str, str],
    evaluation_key: bytes,
    challenge_bundle: bytes,
    development_slots: list[dict],
    development_scoring_key: list[dict],
) -> dict:
    """Minimal structurally valid private authority document for closure unit tests.

    Concrete raw-output derivation is exercised separately; these tests isolate
    content addressing and must not weaken the production validator.
    """

    value = {
        "schema_version": "0.1.0",
        "contract_type": "ltt.sealed_evaluation_authorization",
        "status": "sealed_before_auditor_fit",
        "authorization_id": "fixture-auth-001",
        "authorized_at": "2026-07-17T22:00:00Z",
        "pilot_barrier_id": "fixture-pilot-barrier-001",
        "fold_worker_capability_id": "fixture-capability-realm-001",
        "fold_worker_capability_contract": dict(FOLD_WORKER_CAPABILITY_CONTRACT),
        "parent_design_manifest_sha256": "1" * 64,
        "execution_lock_sha256": "2" * 64,
        "pre_auditor_query_ledger_sha256": "3" * 64,
        "fold_id": "holdout-private-fixture",
        "fold_token": "9" * 32,
        "heldout_dependency_cluster_id": "private-cluster-fixture",
        "heldout_model_unit_ids": ["private-model-a", "private-model-b", "private-model-c"],
        "development_dependency_cluster_ids": ["private-cluster-d", "private-cluster-e"],
        "development_model_unit_ids": [
            "private-model-d",
            "private-model-e",
            "private-model-f",
            "private-model-g",
            "private-model-h",
            "private-model-i",
        ],
        "counts": {
            "target_count": 9,
            "heldout_target_count": 3,
            "development_target_count": 6,
            "sealed_weak_trial_count": 2880,
            "sealed_challenge_trial_count": 1152,
            "sealed_forward_pass_count": 4032,
            "heldout_weak_observation_count": 960,
            "trial_count_per_slot": 64,
            "heldout_challenge_trial_count": 384,
            "development_challenge_trial_count": 768,
        },
        "blind_bundle_sha256": bundle_sha256,
        "prospective_contract": dict(CONTRACT_HASHES),
        "sealed_weak_trials_sha256": "4" * 64,
        "sealed_challenge_trials_sha256": "5" * 64,
        "challenge_bundle_sha256": hashlib.sha256(challenge_bundle).hexdigest(),
        "evaluation_key_sha256": hashlib.sha256(evaluation_key).hexdigest(),
        "weak_observation_records_sha256": "6" * 64,
        "heldout_slot_inventory_sha256": "7" * 64,
        "heldout_scoring_key_sha256": "8" * 64,
        "development_slot_inventory_sha256": hashlib.sha256(
            _canonical_json_bytes(development_slots)
        ).hexdigest(),
        "development_scoring_key_sha256": hashlib.sha256(
            _canonical_json_bytes(development_scoring_key)
        ).hexdigest(),
        "authority_commitments": authority_commitments,
    }
    value["authorization_sha256"] = _self_address(value, "authorization_sha256")
    return value


def _integration_sealed_design():
    seeds = derive_live_content_seeds(INTEGRATION_AUTHORITY_SECRET, 64)
    sealed_seeds = partition_content_seeds(seeds)["D_sealed_test"]
    return build_oss_design(sealed_seeds)


def _integration_raw_sealed_trials(
    execution_lock: dict,
) -> tuple[list[dict], list[dict]]:
    design = _integration_sealed_design()
    cases = {case.case_id: case for case in design.cases}
    model_ids = sorted(row["model_unit_id"] for row in execution_lock["model_registry"])
    weak_rows: list[dict] = []
    challenge_rows: list[dict] = []

    def common_row(model_id: str, projection) -> dict:
        output_text = projection.oracle_final
        return {
            "model_unit_id": model_id,
            "case_id": projection.case_id,
            "projection_id": projection.projection_id,
            "projection_kind": projection.kind.value,
            "prompt_text": projection.prompt_text,
            "prompt_sha256": hashlib.sha256(projection.prompt_text.encode("utf-8")).hexdigest(),
            "projection_record_sha256": canonical_artifact_sha256(projection.to_dict()),
            "output_text": output_text,
            "output_text_sha256": hashlib.sha256(output_text.encode("utf-8")).hexdigest(),
            "completion_record_sha256": hashlib.sha256(
                f"completion:{model_id}:{projection.projection_id}".encode("utf-8")
            ).hexdigest(),
        }

    for model_id in model_ids:
        for projection in sorted(design.weak_observations, key=lambda item: item.projection_id):
            weak_rows.append(common_row(model_id, projection))
        for projection in sorted(design.heldout_challenges, key=lambda item: item.projection_id):
            case = cases[projection.case_id]
            row = common_row(model_id, projection)
            row.update(
                {
                    "semantic_solution": case.semantic_solution.value,
                    "surface_cue": case.surface_cue.value,
                    "answer_codebook": case.answer_codebook.value,
                    "derived_outcome": derive_relational_challenge_outcome(
                        row["output_text"],
                        semantic_solution=case.semantic_solution,
                        surface_cue=case.surface_cue,
                        answer_codebook=case.answer_codebook,
                    ),
                }
            )
            challenge_rows.append(row)
    return weak_rows, challenge_rows


def _integration_pre_auditor_ledger(execution_lock: dict) -> dict:
    plan = execution_lock["query_plan"]
    ledger = {
        "schema_version": "0.1.0",
        "status": "sealed_outputs_complete_diagnostics_pending",
        "execution_lock_sha256": canonical_artifact_sha256(execution_lock),
        "causal_label_forward_passes": plan["planned_causal_label_forward_passes"],
        "behavior_fit_forward_passes": plan["planned_behavior_fit_forward_passes"],
        "sealed_test_forward_passes": plan["planned_sealed_test_forward_passes"],
        "diagnostic_forward_passes": 0,
        "diagnostic_status": "pending_until_all_fold_prediction_commitments",
        "total_forward_passes": (
            plan["planned_causal_label_forward_passes"]
            + plan["planned_behavior_fit_forward_passes"]
            + plan["planned_sealed_test_forward_passes"]
        ),
        "wall_clock_seconds": 300.0,
    }
    ledger["ledger_sha256"] = _self_address(ledger, "ledger_sha256")
    return ledger


def _integration_payload_bytes(
    execution_lock: dict,
    *,
    fold_id: str,
    heldout_dependency_cluster_id: str,
    weak_trials: list[dict],
    challenge_trials: list[dict],
) -> bytes:
    return _canonical_json_bytes(
        {
            "schema_version": "0.1.0",
            "contract_type": "ltt.sealed_evaluation_payload",
            "execution_lock_sha256": canonical_artifact_sha256(execution_lock),
            "fold_id": fold_id,
            "heldout_dependency_cluster_id": heldout_dependency_cluster_id,
            "weak_trials": weak_trials,
            "challenge_trials": challenge_trials,
        }
    )


class ProductionPilotCoordinatorIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.discovery_authorization = _integration_discovery_authorization()
        cls.site_discovery_report = _integration_site_report(cls.discovery_authorization)
        cls.execution_lock = _integration_execution_lock(
            cls.discovery_authorization, cls.site_discovery_report
        )
        cls.pre_auditor_ledger = _integration_pre_auditor_ledger(cls.execution_lock)
        cls.weak_trials, cls.challenge_trials = _integration_raw_sealed_trials(cls.execution_lock)

    def _build_pilot(
        self,
        root: Path,
        *,
        changed_method_fold: int | None = None,
        contaminated_role_fold: int | None = None,
    ) -> tuple[list[dict], dict[str, dict[str, bytes]]]:
        fold_runs: list[dict] = []
        openings: dict[str, dict[str, bytes]] = {}
        clusters = sorted(
            self.execution_lock["dependency_clusters"],
            key=lambda row: row["dependency_cluster_id"],
        )
        for index, cluster in enumerate(clusters):
            cluster_id = cluster["dependency_cluster_id"]
            fold_id = f"holdout-{cluster_id}"
            challenge_bundle_bytes = _integration_payload_bytes(
                self.execution_lock,
                fold_id=fold_id,
                heldout_dependency_cluster_id=cluster_id,
                weak_trials=self.weak_trials,
                challenge_trials=self.challenge_trials,
            )
            material = _derive_sealed_evaluation_material(
                execution_lock=self.execution_lock,
                authority_secret=INTEGRATION_AUTHORITY_SECRET,
                challenge_bundle_bytes=challenge_bundle_bytes,
                fold_id=fold_id,
                heldout_dependency_cluster_id=cluster_id,
            )

            fold_root = root / f"fold-{index}"
            bundle_root = fold_root / "blind"
            artifact_root = fold_root / "authority-handoff"
            bundle_root.mkdir(parents=True)
            artifact_root.mkdir(parents=True)
            (bundle_root / "observations.jsonl").write_bytes(
                _jsonl_bytes(list(material["heldout_weak_observations"]))
            )
            (bundle_root / "challenge_slots.jsonl").write_bytes(
                _jsonl_bytes(list(material["heldout_slots"]))
            )
            bundle_manifest = build_blind_bundle_manifest(
                bundle_root, observation_paths=["observations.jsonl"]
            )

            evaluation_nonce = bytes([index + 1]) * 32
            challenge_nonce = bytes([index + 17]) * 32
            sealed_authorization = build_sealed_evaluation_authorization(
                execution_lock=self.execution_lock,
                pre_auditor_query_ledger=self.pre_auditor_ledger,
                authority_secret=INTEGRATION_AUTHORITY_SECRET,
                challenge_bundle_bytes=challenge_bundle_bytes,
                blind_bundle_root=bundle_root,
                blind_bundle_manifest=bundle_manifest,
                authorization_id=f"sealed-fold-authorization-{index}",
                authorized_at=f"2026-07-17T22:0{index}:00Z",
                pilot_barrier_id="pilot-barrier-integration-001",
                fold_worker_capability_id=f"isolated-fold-realm-{index}",
                fold_id=fold_id,
                heldout_dependency_cluster_id=cluster_id,
                evaluation_nonce=evaluation_nonce,
                challenge_nonce=challenge_nonce,
            )
            verified = verify_sealed_evaluation_authorization(
                sealed_authorization,
                execution_lock=self.execution_lock,
                pre_auditor_query_ledger=self.pre_auditor_ledger,
                authority_secret=INTEGRATION_AUTHORITY_SECRET,
                challenge_bundle_bytes=challenge_bundle_bytes,
                evaluation_key_bytes=material["evaluation_key_bytes"],
                evaluation_nonce=evaluation_nonce,
                challenge_nonce=challenge_nonce,
                blind_bundle_root=bundle_root,
                blind_bundle_manifest=bundle_manifest,
            )
            self.assertEqual(verified["fold_token"], sealed_authorization["fold_token"])

            predictions = [
                {
                    "schema_version": "0.1.0",
                    **slot,
                    "probabilities": {
                        "semantic_consistent": 0.999,
                        "surface_cue_consistent": 0.0005,
                        "parse_failure": 0.0005,
                    },
                    "abstain": False,
                    "abstention_reason": None,
                }
                for slot in material["heldout_slots"]
            ]
            (artifact_root / "predictions.jsonl").write_bytes(_jsonl_bytes(predictions))
            development_root = artifact_root / "development"
            development_root.mkdir()
            (development_root / "slots.jsonl").write_bytes(
                _jsonl_bytes(list(material["development_slots"]))
            )
            (development_root / "scoring_key.jsonl").write_bytes(
                _jsonl_bytes(list(material["development_key"]))
            )
            artifact_paths = _artifact_paths()
            for role, relative in artifact_paths.items():
                path = artifact_root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                payload = f"frozen-method-{role}-v1".encode("utf-8")
                if role == "feature_spec":
                    payload += (
                        b"\npublic method vocabulary: causal_variable "
                        b"anchor_condition_id selected_site_id semantic_anchor "
                        b"surface_cue_anchor mixed_anchor"
                    )
                if changed_method_fold == index and role == "feature_spec":
                    payload += b"-changed-only-in-this-fold"
                if contaminated_role_fold == index and role == "estimator":
                    payload += b"\n" + self.execution_lock["model_registry"][0][
                        "model_unit_id"
                    ].encode("utf-8")
                path.write_bytes(payload)

            commitment = build_evaluation_commitment(
                artifact_root,
                blind_bundle_root=bundle_root,
                blind_bundle_manifest=bundle_manifest,
                evaluation_id=f"pilot-fold-evaluation-{index}",
                protocol_id="oss-reliance-regime-v0",
                prediction_path="predictions.jsonl",
                development_scoring_key_path="development/scoring_key.jsonl",
                development_slot_inventory_path="development/slots.jsonl",
                auditor_artifact_paths=artifact_paths,
                sealed_evaluation_authorization=sealed_authorization,
            )
            fold_runs.append(
                {
                    "artifact_root": artifact_root,
                    "commitment": commitment,
                    "blind_bundle_root": bundle_root,
                    "blind_bundle_manifest": bundle_manifest,
                    "sealed_evaluation_authorization": sealed_authorization,
                }
            )
            openings[sealed_authorization["authorization_sha256"]] = {
                "revealed_evaluation_key_bytes": material["evaluation_key_bytes"],
                "revealed_challenge_bundle_bytes": challenge_bundle_bytes,
                "evaluation_nonce": evaluation_nonce,
                "challenge_nonce": challenge_nonce,
            }
        return fold_runs, openings

    def _evaluate(
        self,
        fold_runs: list[dict],
        provider,
        *,
        execution_lock: dict | None = None,
    ) -> dict:
        return evaluate_committed_pilot_gate(
            fold_runs,
            authority_opening_provider=provider,
            discovery_authorization=self.discovery_authorization,
            execution_lock=execution_lock or self.execution_lock,
            site_discovery_report=self.site_discovery_report,
            pre_auditor_query_ledger=self.pre_auditor_ledger,
            authority_secret=INTEGRATION_AUTHORITY_SECRET,
            expected_prospective_contract=INTEGRATION_PROSPECTIVE_HASHES,
            **_integration_trusted_kwargs(),
        )

    @staticmethod
    def _provider(openings: dict[str, dict[str, bytes]]):
        calls: list[str] = []

        def provide(authorization: dict) -> dict[str, bytes]:
            address = authorization["authorization_sha256"]
            calls.append(address)
            return openings[address]

        return provide, calls

    def test_real_three_fold_coordinator_and_pre_reveal_barrier(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fold_runs, openings = self._build_pilot(Path(temporary))
            provider, calls = self._provider(openings)
            result = self._evaluate(fold_runs, provider)

            self.assertEqual(len(calls), 3)
            self.assertTrue(result["global_gate_result"]["passes_primary_gate"])
            self.assertEqual(len(result["fold_results"]), 3)
            self.assertEqual(result["output_runtime_evidence"], OUTPUT_RUNTIME_EVIDENCE_BOUNDARY)
            self.assertFalse(result["output_runtime_evidence"]["runtime_attestation_provided"])
            with self.assertRaises(TypeError):
                OUTPUT_RUNTIME_EVIDENCE_BOUNDARY[  # type: ignore[index]
                    "runtime_attestation_provided"
                ] = True
            self.assertEqual(result["result_sha256"], _self_address(result, "result_sha256"))

            for invalid_runs, message in (
                (fold_runs[:2], "exactly three"),
                (
                    [fold_runs[0], fold_runs[0], fold_runs[2]],
                    "distinct capability",
                ),
            ):
                provider, calls = self._provider(openings)
                with (
                    self.subTest(message=message),
                    self.assertRaisesRegex(BlindContractError, message),
                ):
                    self._evaluate(invalid_runs, provider)
                self.assertEqual(calls, [])

            invalid_commitment_runs = deepcopy(fold_runs)
            invalid_commitment_runs[1]["commitment"]["commitment_sha256"] = "0" * 64
            provider, calls = self._provider(openings)
            with self.assertRaisesRegex(BlindContractError, "self-address mismatch"):
                self._evaluate(invalid_commitment_runs, provider)
            self.assertEqual(calls, [])

            tampered_lock = deepcopy(self.execution_lock)
            tampered_lock["blind_runtime"]["derived_seed_set_sha256"] = "0" * 64
            provider, calls = self._provider(openings)
            with self.assertRaisesRegex(BlindContractError, "execution ancestry"):
                self._evaluate(fold_runs, provider, execution_lock=tampered_lock)
            self.assertEqual(calls, [])

            tampered_openings = deepcopy(openings)
            first_authorization_sha = fold_runs[0]["sealed_evaluation_authorization"][
                "authorization_sha256"
            ]
            tampered_openings[first_authorization_sha]["revealed_challenge_bundle_bytes"] += b"\n"
            provider, calls = self._provider(tampered_openings)
            with self.assertRaisesRegex(BlindContractError, "canonical JSON"):
                self._evaluate(fold_runs, provider)
            self.assertEqual(calls, [first_authorization_sha])

            development_path = fold_runs[1]["artifact_root"] / "development/scoring_key.jsonl"
            changed_rows = [
                json.loads(line)
                for line in development_path.read_text(encoding="utf-8").splitlines()
            ]
            changed_rows[0]["outcome_counts"] = {
                "semantic_consistent": 63,
                "surface_cue_consistent": 1,
                "parse_failure": 0,
            }
            development_path.write_bytes(_jsonl_bytes(changed_rows))
            changed_entry = fold_runs[1]["commitment"]["development_artifacts"][0]
            changed_entry["bytes"] = development_path.stat().st_size
            changed_entry["sha256"] = hashlib.sha256(development_path.read_bytes()).hexdigest()
            changed_entry["records_sha256"] = hashlib.sha256(
                _canonical_json_bytes(changed_rows)
            ).hexdigest()
            fold_runs[1]["commitment"]["commitment_sha256"] = _self_address(
                fold_runs[1]["commitment"], "commitment_sha256"
            )
            provider, calls = self._provider(openings)
            with self.assertRaisesRegex(BlindContractError, "development material detached"):
                self._evaluate(fold_runs, provider)
            self.assertEqual(calls, [])

    def test_method_hash_mismatch_blocks_opening(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fold_runs, openings = self._build_pilot(Path(temporary), changed_method_fold=1)
            provider, calls = self._provider(openings)
            with self.assertRaisesRegex(BlindContractError, "method-defining"):
                self._evaluate(fold_runs, provider)
            self.assertEqual(calls, [])

    def test_raw_identifier_in_auditor_role_file_blocks_opening(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fold_runs, openings = self._build_pilot(Path(temporary))
            model = self.execution_lock["model_registry"][0]
            private_values = {
                field: model[field]
                for field in (
                    "model_unit_id",
                    "independent_training_run_id",
                    "checkpoint_id",
                    "lineage_id",
                    "architecture_family_id",
                    "model_id",
                    "model_revision",
                    "tokenizer_revision",
                )
            }
            private_values["dependency_cluster_id"] = model["dependency_cluster_id"]

            for field, private_value in private_values.items():
                contaminated_runs = deepcopy(fold_runs)
                estimator_entry = next(
                    entry
                    for entry in contaminated_runs[1]["commitment"]["auditor_artifacts"]
                    if entry["role"] == "estimator"
                )
                estimator_path = contaminated_runs[1]["artifact_root"] / estimator_entry["path"]
                original_bytes = estimator_path.read_bytes()
                try:
                    contaminated_bytes = original_bytes + b"\n" + private_value.encode("utf-8")
                    estimator_path.write_bytes(contaminated_bytes)
                    estimator_entry["bytes"] = len(contaminated_bytes)
                    estimator_entry["sha256"] = hashlib.sha256(contaminated_bytes).hexdigest()
                    contaminated_runs[1]["commitment"]["commitment_sha256"] = _self_address(
                        contaminated_runs[1]["commitment"], "commitment_sha256"
                    )
                    provider, calls = self._provider(openings)
                    with (
                        self.subTest(field=field),
                        self.assertRaisesRegex(BlindContractError, "private execution identity"),
                    ):
                        self._evaluate(contaminated_runs, provider)
                    self.assertEqual(calls, [])
                finally:
                    estimator_path.write_bytes(original_bytes)


class BlindAuditorSurfaceTests(unittest.TestCase):
    def test_retired_single_fold_production_gate_fails_closed(self) -> None:
        with self.assertRaisesRegex(BlindContractError, "non-authoritative"):
            evaluate_committed_candidate_gate()

    def test_global_gate_uses_equal_fold_means_and_one_global_baseline(self) -> None:
        weak_losses = (0.5, 1.5, 0.5)
        development_losses = (0.8, 0.4, 0.8)
        fold_results = []
        for index in range(3):
            fold_results.append(
                {
                    "gate_result": {
                        "passes_primary_gate": index == 1,
                        "candidate_score": {
                            PRIMARY_METRIC: 0.5,
                            SECONDARY_METRIC: 0.2 + index * 0.1,
                            "macro_dependency_cluster_slot_coverage": 0.5 + index * 0.25,
                        },
                        "baseline_scores": {
                            WEAK_ORBIT_BASELINE_ID: {
                                PRIMARY_METRIC: weak_losses[index],
                                SECONDARY_METRIC: 0.4,
                                "macro_dependency_cluster_slot_coverage": 1.0,
                            },
                            DEVELOPMENT_BASELINE_ID: {
                                PRIMARY_METRIC: development_losses[index],
                                SECONDARY_METRIC: 0.3,
                                "macro_dependency_cluster_slot_coverage": 1.0,
                            },
                        },
                    }
                }
            )

        result = _aggregate_equal_three_fold_gate(fold_results)

        self.assertEqual(result["stronger_baseline_id"], DEVELOPMENT_BASELINE_ID)
        self.assertAlmostEqual(result["candidate_log_loss"], 0.5)
        self.assertAlmostEqual(result["baseline_log_losses"][DEVELOPMENT_BASELINE_ID], 2.0 / 3.0)
        self.assertAlmostEqual(result["candidate_multiclass_brier"], 0.3)
        self.assertAlmostEqual(result["candidate_slot_coverage"], 0.75)
        self.assertTrue(result["passes_primary_gate"])

    def test_prohibited_field_leak_is_rejected(self) -> None:
        for prohibited, value in (
            ("model_id", "vendor-model"),
            ("provider_name", "vendor"),
            ("internal_label", "semantic_route"),
            ("evaluation_lineage_id", "lineage-001"),
            ("site_map", {"layer": 7}),
            ("causal_label", "semantic_reliance"),
            ("cue_mask", "hidden-mask"),
            ("challenge_prompt", "withheld prompt"),
            ("challenge_seed", 913),
            ("challenge_output", "withheld answer"),
            ("internal_intervention", {"site": "resid-7"}),
            ("logprobs", [-0.1]),
            ("latency_ms", 12.0),
        ):
            with self.subTest(prohibited=prohibited):
                row = dict(_auditor_rows()[0])
                row[prohibited] = value
                with self.assertRaisesRegex(BlindContractError, "extra"):
                    validate_auditor_observations([row])

    def test_missing_and_duplicate_pairing_ids_are_rejected(self) -> None:
        missing = dict(_auditor_rows()[0])
        missing.pop("replicate_id")
        with self.assertRaisesRegex(BlindContractError, "missing"):
            validate_auditor_observations([missing])

        meaningful = dict(_auditor_rows()[0])
        meaningful["projection_id"] = "cue_mask_gemma_family"
        with self.assertRaisesRegex(BlindContractError, "128-bit hex"):
            validate_auditor_observations([meaningful])

        duplicate = dict(_auditor_rows()[0])
        with self.assertRaisesRegex(BlindContractError, "duplicate"):
            validate_auditor_observations([_auditor_rows()[0], duplicate])

    def test_hmac_pairing_tokens_are_keyed_and_domain_separated(self) -> None:
        secret = bytes(range(32))
        material = b"vendor:model/revision"
        target = derive_pairing_token(secret, domain="target", material=material)

        self.assertEqual(target, "b48d05b78dfb5c9769f80233b172d470")
        self.assertEqual(derive_pairing_token(secret, domain="target", material=material), target)
        self.assertNotEqual(derive_pairing_token(secret, domain="case", material=material), target)
        self.assertNotEqual(
            derive_pairing_token(b"x" * 32, domain="target", material=material), target
        )
        self.assertNotIn("vendor", target)
        with self.assertRaisesRegex(BlindContractError, "256 random bits"):
            derive_pairing_token(b"short", domain="target", material=material)
        with self.assertRaisesRegex(BlindContractError, "unsupported"):
            derive_pairing_token(secret, domain="model", material=material)

    def test_authority_commitment_has_a_fixed_length_prefixed_vector(self) -> None:
        vector = AUTHORITY_COMMITMENT_CONFORMANCE_VECTOR
        commitment = build_authority_precommitments(
            evaluation_key_bytes=bytes.fromhex(vector["payload_hex"]),
            challenge_bundle_bytes=b"sealed-challenge-fixture-v1",
            evaluation_nonce=bytes.fromhex(vector["nonce_hex"]),
            challenge_nonce=b"C" * 32,
        )

        self.assertEqual(
            AUTHORITY_COMMITMENT_SCHEME,
            "sha256_domain_separated_u64be_length_prefixed_v1",
        )
        self.assertEqual(commitment["scheme"], AUTHORITY_COMMITMENT_SCHEME)
        self.assertEqual(
            commitment["evaluation_key_commitment"],
            "1bf349c05ab1bb6535ceed0d147f4391db1f1dd7fb39c0963fa373025f4ef6ee",
        )
        self.assertEqual(
            commitment["evaluation_key_commitment"],
            vector["sha256"],
        )

    def test_authority_commitment_rejects_short_nonce_and_legacy_boundary_ambiguity(self) -> None:
        common = {
            "evaluation_key_bytes": b"{}\n",
            "evaluation_nonce": b"E" * 32,
        }
        with self.assertRaisesRegex(BlindContractError, "at least 32 random bytes"):
            build_authority_precommitments(
                challenge_bundle_bytes=b"sealed",
                challenge_nonce=b"C" * 31,
                **common,
            )

        base_nonce = b"A" * 32
        first_payload = b"B\x00C"
        second_nonce = base_nonce + b"\x00B"
        second_payload = b"C"
        self.assertEqual(
            base_nonce + b"\x00" + first_payload,
            second_nonce + b"\x00" + second_payload,
        )
        first = build_authority_precommitments(
            challenge_bundle_bytes=first_payload,
            challenge_nonce=base_nonce,
            **common,
        )
        second = build_authority_precommitments(
            challenge_bundle_bytes=second_payload,
            challenge_nonce=second_nonce,
            **common,
        )
        self.assertNotEqual(
            first["challenge_bundle_commitment"],
            second["challenge_bundle_commitment"],
        )


class BlindBundleAndCommitmentTests(unittest.TestCase):
    def test_sealed_authorization_template_matches_schema(self) -> None:
        root = Path(__file__).resolve().parents[1]
        schema = json.loads(
            (root / "schemas/sealed_evaluation_authorization.schema.json").read_text(
                encoding="utf-8"
            )
        )
        template = json.loads(
            (
                root / "protocols/oss_reliance_regime_v0/sealed_evaluation_authorization.json"
            ).read_text(encoding="utf-8")
        )
        validator_for(schema).check_schema(schema)
        validator = validator_for(schema)(schema)
        validator.validate(template)
        invalid_assignments = {
            "authorization_id": "premature-auth",
            "execution_lock_sha256": "0" * 64,
            "prospective_contract": dict(CONTRACT_HASHES),
            "authority_commitments": {
                "scheme": AUTHORITY_COMMITMENT_SCHEME,
                "evaluation_key_commitment": "1" * 64,
                "challenge_bundle_commitment": "2" * 64,
            },
            "fold_worker_capability_contract": dict(FOLD_WORKER_CAPABILITY_CONTRACT),
        }
        for field, assigned_value in invalid_assignments.items():
            with self.subTest(field=field), self.assertRaises(ValidationError):
                invalid = deepcopy(template)
                invalid[field] = assigned_value
                validator.validate(invalid)

        incomplete_assigned = deepcopy(template)
        incomplete_assigned["status"] = "sealed_before_auditor_fit"
        incomplete_assigned["heldout_model_unit_ids"] = ["unit-a", "unit-b", "unit-c"]
        incomplete_assigned["development_dependency_cluster_ids"] = [
            "cluster-a",
            "cluster-b",
        ]
        incomplete_assigned["development_model_unit_ids"] = [
            f"development-unit-{index}" for index in range(6)
        ]
        with self.assertRaises(ValidationError):
            validator.validate(incomplete_assigned)

        evaluation_key = _jsonl_bytes(_scoring_key())
        challenge_bundle = b'{"assigned":"fixture"}\n'
        authority_commitments = build_authority_precommitments(
            evaluation_key_bytes=evaluation_key,
            challenge_bundle_bytes=challenge_bundle,
            evaluation_nonce=b"E" * 32,
            challenge_nonce=b"C" * 32,
        )
        assigned = _fake_sealed_authorization(
            bundle_sha256="a" * 64,
            authority_commitments=authority_commitments,
            evaluation_key=evaluation_key,
            challenge_bundle=challenge_bundle,
            development_slots=_development_slots(),
            development_scoring_key=_development_scoring_key(),
        )
        validator.validate(assigned)
        invalid_timestamp = deepcopy(assigned)
        invalid_timestamp["authorized_at"] = "fixture-time-001"
        with self.assertRaises(ValidationError):
            validator.validate(invalid_timestamp)

    def _prepare(
        self,
        root: Path,
        *,
        observations: list[dict] | None = None,
        slots: list[dict] | None = None,
        predictions: list[dict] | None = None,
        scoring_key: list[dict] | None = None,
        development_slots: list[dict] | None = None,
        development_scoring_key: list[dict] | None = None,
        auditor_artifact_paths: dict[str, str] | None = None,
    ) -> dict:
        bundle_root = root / "blind"
        artifact_root = root / "auditor"
        bundle_root.mkdir()
        artifact_root.mkdir()
        observations = _auditor_rows() if observations is None else observations
        slots = _challenge_slots() if slots is None else slots
        predictions = _predictions() if predictions is None else predictions
        scoring_key = _scoring_key() if scoring_key is None else scoring_key
        development_slots = _development_slots() if development_slots is None else development_slots
        development_scoring_key = (
            _development_scoring_key()
            if development_scoring_key is None
            else development_scoring_key
        )
        artifact_paths = (
            _artifact_paths() if auditor_artifact_paths is None else auditor_artifact_paths
        )

        (bundle_root / "observations.jsonl").write_bytes(_jsonl_bytes(observations))
        (bundle_root / "challenge_slots.jsonl").write_bytes(_jsonl_bytes(slots))
        (artifact_root / "predictions.jsonl").write_bytes(_jsonl_bytes(predictions))
        development_root = artifact_root / "development"
        development_root.mkdir()
        (development_root / "slots.jsonl").write_bytes(_jsonl_bytes(development_slots))
        (development_root / "scoring_key.jsonl").write_bytes(_jsonl_bytes(development_scoring_key))
        for role, relative in _artifact_paths().items():
            path = artifact_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"frozen-{role}-v1".encode("ascii"))

        evaluation_key = _jsonl_bytes(scoring_key)
        challenge_bundle = b'{"challenge_set":"held-out-v1"}\n'
        evaluation_nonce = bytes(range(32))
        challenge_nonce = bytes(range(32, 64))
        authority = build_authority_precommitments(
            evaluation_key_bytes=evaluation_key,
            challenge_bundle_bytes=challenge_bundle,
            evaluation_nonce=evaluation_nonce,
            challenge_nonce=challenge_nonce,
        )
        bundle_manifest = build_blind_bundle_manifest(
            bundle_root,
            observation_paths=["observations.jsonl"],
        )
        sealed_authorization = _fake_sealed_authorization(
            bundle_sha256=bundle_manifest["bundle_sha256"],
            authority_commitments=authority,
            evaluation_key=evaluation_key,
            challenge_bundle=challenge_bundle,
            development_slots=development_slots,
            development_scoring_key=development_scoring_key,
        )
        commitment = build_evaluation_commitment(
            artifact_root,
            blind_bundle_root=bundle_root,
            blind_bundle_manifest=bundle_manifest,
            evaluation_id="oss-1-eval-001",
            protocol_id="oss-reliance-regime-v1",
            prediction_path="predictions.jsonl",
            development_scoring_key_path="development/scoring_key.jsonl",
            development_slot_inventory_path="development/slots.jsonl",
            auditor_artifact_paths=artifact_paths,
            sealed_evaluation_authorization=sealed_authorization,
        )
        return {
            "bundle_root": bundle_root,
            "artifact_root": artifact_root,
            "bundle_manifest": bundle_manifest,
            "commitment": commitment,
            "sealed_authorization": sealed_authorization,
            "evaluation_key": evaluation_key,
            "challenge_bundle": challenge_bundle,
            "evaluation_nonce": evaluation_nonce,
            "challenge_nonce": challenge_nonce,
        }

    def _close(
        self,
        prepared: dict,
        *,
        expected_prospective_contract: dict[str, str] | None = None,
    ) -> dict:
        return verify_commitment_closure(
            prepared["artifact_root"],
            prepared["commitment"],
            blind_bundle_root=prepared["bundle_root"],
            blind_bundle_manifest=prepared["bundle_manifest"],
            sealed_evaluation_authorization=prepared["sealed_authorization"],
            expected_prospective_contract=(expected_prospective_contract or CONTRACT_HASHES),
            revealed_evaluation_key_bytes=prepared["evaluation_key"],
            revealed_challenge_bundle_bytes=prepared["challenge_bundle"],
            evaluation_nonce=prepared["evaluation_nonce"],
            challenge_nonce=prepared["challenge_nonce"],
        )

    def _score(self, prepared: dict) -> dict:
        closure = self._close(prepared)
        bundle = validate_blind_bundle_manifest(
            prepared["bundle_root"], prepared["bundle_manifest"]
        )
        prediction_rows = [
            json.loads(line)
            for line in (prepared["artifact_root"] / "predictions.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        development_rows = [
            json.loads(line)
            for line in (prepared["artifact_root"] / "development/scoring_key.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        development_slots = [
            json.loads(line)
            for line in (prepared["artifact_root"] / "development/slots.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        key_rows = [json.loads(line) for line in prepared["evaluation_key"].splitlines()]
        gate = evaluate_verified_candidate_gate(
            prediction_rows,
            key_rows,
            bundle["challenge_slots"],
            weak_observations=bundle["observations"],
            development_scoring_key=development_rows,
            development_slots=development_slots,
        )
        return {
            "status": "fold_score_non_authoritative",
            "gate_result": gate,
            "closure_evidence": closure,
        }

    def test_path_traversal_and_symlink_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle_root = root / "blind"
            bundle_root.mkdir()
            outside = root / "outside.jsonl"
            outside.write_bytes(_jsonl_bytes(_auditor_rows()))

            with self.assertRaisesRegex(BlindContractError, "traversal"):
                build_blind_bundle_manifest(bundle_root, observation_paths=["../outside.jsonl"])

            leaked_name = bundle_root / "gemma_cue_mask.jsonl"
            leaked_name.write_bytes(_jsonl_bytes(_auditor_rows()))
            with self.assertRaisesRegex(BlindContractError, "observations.jsonl"):
                build_blind_bundle_manifest(bundle_root, observation_paths=["gemma_cue_mask.jsonl"])

            link = bundle_root / "observations.jsonl"
            link.symlink_to(outside)
            with self.assertRaisesRegex(BlindContractError, "symlink"):
                build_blind_bundle_manifest(bundle_root, observation_paths=["observations.jsonl"])

    def test_raw_registry_identifiers_are_absent_from_every_auditor_surface(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            prepared = self._prepare(Path(temporary))
            authorization = prepared["sealed_authorization"]
            raw_identifiers = [
                authorization["heldout_dependency_cluster_id"],
                *authorization["development_dependency_cluster_ids"],
                *authorization["heldout_model_unit_ids"],
                *authorization["development_model_unit_ids"],
            ]
            bundle = validate_blind_bundle_manifest(
                prepared["bundle_root"], prepared["bundle_manifest"]
            )
            development_bytes = b"".join(
                (prepared["artifact_root"] / entry["path"]).read_bytes()
                for entry in prepared["commitment"]["development_artifacts"]
            )
            prediction_bytes = (
                prepared["artifact_root"] / prepared["commitment"]["prediction_artifact"]["path"]
            ).read_bytes()
            auditor_artifact_bytes = b"".join(
                (prepared["artifact_root"] / entry["path"]).read_bytes()
                for entry in prepared["commitment"]["auditor_artifacts"]
            )
            clean_surfaces = {
                "blind_bundle": _canonical_json_bytes(
                    {"manifest": prepared["bundle_manifest"], "records": bundle}
                ),
                "development_files": development_bytes,
                "prediction_file": prediction_bytes,
                "auditor_artifact_files": auditor_artifact_bytes,
                "serialized_commitment": _canonical_json_bytes(prepared["commitment"]),
            }
            _assert_no_private_identifier_leak(raw_identifiers, clean_surfaces)
            for surface_name in clean_surfaces:
                with (
                    self.subTest(surface=surface_name),
                    self.assertRaisesRegex(BlindContractError, f"surface={surface_name}"),
                ):
                    contaminated = dict(clean_surfaces)
                    contaminated[surface_name] += raw_identifiers[0].encode("utf-8")
                    _assert_no_private_identifier_leak(raw_identifiers, contaminated)

    def test_bundle_rejects_observation_and_challenge_target_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle_root = root / "blind"
            bundle_root.mkdir()
            target_a_slots = [slot for slot in _challenge_slots() if slot["target_id"] == TARGET_A]
            (bundle_root / "observations.jsonl").write_bytes(_jsonl_bytes(_auditor_rows()))
            (bundle_root / "challenge_slots.jsonl").write_bytes(_jsonl_bytes(target_a_slots))
            with self.assertRaisesRegex(BlindContractError, "same target set"):
                build_blind_bundle_manifest(bundle_root, observation_paths=["observations.jsonl"])

    def test_predictions_must_close_the_exact_challenge_slot_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(BlindContractError, "cover every committed"):
                self._prepare(Path(temporary), predictions=_predictions()[:-1])

    def test_exact_role_tagged_auditor_artifact_set_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            missing = _artifact_paths()
            missing.pop("feature_spec")
            with self.assertRaisesRegex(BlindContractError, "exactly the frozen"):
                self._prepare(Path(temporary), auditor_artifact_paths=missing)

    def test_prediction_and_auditor_mutation_break_commitment_closure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            prepared = self._prepare(Path(temporary))
            prediction = prepared["artifact_root"] / "predictions.jsonl"
            changed = _predictions()
            changed[0]["probabilities"] = {
                "semantic_consistent": 0.2,
                "surface_cue_consistent": 0.7,
                "parse_failure": 0.1,
            }
            prediction.write_bytes(_jsonl_bytes(changed))
            with self.assertRaisesRegex(BlindContractError, "changed after commitment"):
                self._close(prepared)

    def test_authoritative_gate_rejects_post_reveal_artifact_swaps(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            prepared = self._prepare(Path(temporary))
            changed = _predictions()
            changed[0]["probabilities"] = {
                "semantic_consistent": 0.2,
                "surface_cue_consistent": 0.7,
                "parse_failure": 0.1,
            }
            (prepared["artifact_root"] / "predictions.jsonl").write_bytes(_jsonl_bytes(changed))
            with self.assertRaisesRegex(BlindContractError, "changed after commitment"):
                self._score(prepared)

        with tempfile.TemporaryDirectory() as temporary:
            prepared = self._prepare(Path(temporary))
            changed_key = _scoring_key()
            changed_key[0]["outcome_counts"] = {
                "semantic_consistent": 2,
                "surface_cue_consistent": 7,
                "parse_failure": 1,
            }
            prepared["evaluation_key"] = _jsonl_bytes(changed_key)
            changed_key_self_hash = hashlib.sha256(prepared["evaluation_key"]).hexdigest()
            with self.assertRaises(TypeError):
                self._score(
                    prepared,
                    expected_heldout_scoring_key_sha256=changed_key_self_hash,
                )
            with self.assertRaisesRegex(BlindContractError, "does not close"):
                self._score(prepared)

        with tempfile.TemporaryDirectory() as temporary:
            prepared = self._prepare(Path(temporary))
            changed_development = _development_scoring_key()
            changed_development[0]["outcome_counts"] = {
                "semantic_consistent": 9,
                "surface_cue_consistent": 0,
                "parse_failure": 1,
            }
            (prepared["artifact_root"] / "development/scoring_key.jsonl").write_bytes(
                _jsonl_bytes(changed_development)
            )
            with self.assertRaisesRegex(BlindContractError, "changed after commitment"):
                self._score(prepared)

    def test_authoritative_gate_rejects_cluster_overlap_and_fabricated_bridge_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            overlapping = _development_scoring_key(
                dependency_cluster_id="dependency-aaaaaaaaaaaaaaaa"
            )
            prepared = self._prepare(
                Path(temporary),
                development_scoring_key=overlapping,
            )
            with self.assertRaisesRegex(BlindContractError, "dependency-cluster.*disjoint"):
                self._score(prepared)

        with tempfile.TemporaryDirectory() as temporary:
            prepared = self._prepare(Path(temporary))
            for field in (
                "candidate_predictions",
                "precomputed_closure",
                "expected_heldout_scoring_key_sha256",
            ):
                with self.subTest(field=field), self.assertRaises(TypeError):
                    self._score(prepared, **{field: "f" * 64})

        with tempfile.TemporaryDirectory() as temporary:
            prepared = self._prepare(Path(temporary))
            estimator = prepared["artifact_root"] / _artifact_paths()["estimator"]
            estimator.write_bytes(b"mutated-estimator")
            with self.assertRaisesRegex(BlindContractError, "changed after commitment"):
                self._close(prepared)

    def test_committed_but_invalid_scoring_key_fails_after_reveal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            malformed = _scoring_key()[:-1]
            prepared = self._prepare(Path(temporary), scoring_key=malformed)
            with self.assertRaisesRegex(BlindContractError, "invalid revealed.*scoring key"):
                self._close(prepared)

    def test_prospective_hashes_are_part_of_the_self_addressed_commitment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            prepared = self._prepare(Path(temporary))
            commitment = prepared["commitment"]
            self.assertEqual(commitment["prospective_contract"], CONTRACT_HASHES)
            mutated = json.loads(json.dumps(commitment))
            mutated["prospective_contract"]["scoring_contract_sha256"] = "d" * 64
            with self.assertRaisesRegex(BlindContractError, "self-address mismatch"):
                validate_evaluation_commitment(mutated)

            mutated_development = json.loads(json.dumps(commitment))
            mutated_development["development_artifacts"][0]["records_sha256"] = "d" * 64
            with self.assertRaisesRegex(BlindContractError, "self-address mismatch"):
                validate_evaluation_commitment(mutated_development)

            wrong_expected = dict(CONTRACT_HASHES)
            wrong_expected["scoring_contract_sha256"] = "d" * 64
            with self.assertRaisesRegex(BlindContractError, "frozen execution contract"):
                self._close(
                    prepared,
                    expected_prospective_contract=wrong_expected,
                )

    def test_content_addressed_happy_path_closes_without_key_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            prepared = self._prepare(Path(temporary))
            bundle = validate_blind_bundle_manifest(
                prepared["bundle_root"], prepared["bundle_manifest"]
            )
            validate_evaluation_commitment(prepared["commitment"])
            schema = json.loads(
                (
                    Path(__file__).resolve().parents[1]
                    / "schemas/evaluation_commitment.schema.json"
                ).read_text(encoding="utf-8")
            )
            validator_for(schema).check_schema(schema)
            validator_for(schema)(schema).validate(prepared["commitment"])
            closure = self._close(prepared)
            scored = self._score(prepared)

            self.assertEqual(len(bundle["observations"]), 2)
            self.assertEqual(len(bundle["challenge_slots"]), 4)
            self.assertEqual(closure["status"], "artifact_closure_verified")
            self.assertEqual(closure["prediction_target_count"], 2)
            self.assertEqual(closure["prediction_challenge_slot_count"], 4)
            self.assertEqual(closure["scoring_key_record_count"], 4)
            self.assertEqual(closure["development_scoring_key_record_count"], 2)
            self.assertEqual(len(closure["derived_input_hashes"]), 6)
            self.assertEqual(closure["prospective_contract"], CONTRACT_HASHES)
            self.assertEqual(
                scored["status"],
                "fold_score_non_authoritative",
            )
            self.assertTrue(scored["gate_result"]["passes_primary_gate"])
            self.assertEqual(
                scored["closure_evidence"]["derived_input_hashes"],
                scored["gate_result"]["derived_input_hashes"],
            )
            self.assertEqual(
                scored["closure_evidence"]["commitment_sha256"],
                prepared["commitment"]["commitment_sha256"],
            )
            self.assertEqual(
                prepared["commitment"]["security_boundary"],
                CAPABILITY_SECURITY_CONTRACT,
            )
            self.assertFalse(
                prepared["commitment"]["security_boundary"][
                    "capability_security_provided_by_this_contract"
                ]
            )
            serialized = json.dumps(prepared["commitment"], sort_keys=True)
            self.assertNotIn("evaluation_key_path", serialized)
            self.assertNotIn("scoring_key_path", serialized)
            self.assertNotIn("sealed_evaluation_key", serialized)
            serialized_result = json.dumps(scored, sort_keys=True)
            self.assertNotIn("development/scoring_key.jsonl", serialized_result)
            self.assertNotIn("revealed_evaluation_key_bytes", serialized_result)


if __name__ == "__main__":
    unittest.main()
