from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

from jsonschema.validators import validator_for

from latent_trace_tomography.oss_design import (
    OSSProjectionKind,
    build_oss_design,
    encode_answer,
    format_final,
)
from latent_trace_tomography.prospective import (
    DEVELOPMENT_BASELINE_ID,
    PRIMARY_GATE_RELATIVE_REDUCTION,
    PROBABILITY_FLOOR,
    WEAK_ORBIT_BASELINE_ID,
    ProspectiveContractError,
    development_challenge_marginal_baseline,
    derive_relational_challenge_outcome,
    evaluate_verified_candidate_gate,
    score_challenge_predictions,
    validate_challenge_predictions,
    validate_challenge_scoring_key,
    validate_challenge_slot_inventory,
    weak_orbit_route_agnostic_baseline,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET_A = "0" * 32
TARGET_B = "1" * 32
TARGET_C = "2" * 32
CLUSTER_A = "dependency-" + "a" * 16
CLUSTER_B = "dependency-" + "b" * 16
CLUSTER_C = "dependency-" + "c" * 16


def _slots(
    targets: tuple[str, ...] = (TARGET_A, TARGET_B), *, start_slot: int = 10
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    slot_number = start_slot
    for target in targets:
        for kind in ("heldout_cue_conflict", "heldout_mismatch_table"):
            rows.append(
                {
                    "target_id": target,
                    "challenge_slot_id": f"{slot_number:032x}",
                    "challenge_kind": kind,
                }
            )
            slot_number += 1
    return rows


def _predictions(
    slots: list[dict[str, str]] | None = None,
    *,
    probabilities: dict[str, float] | None = None,
    probabilities_by_target: dict[str, dict[str, float]] | None = None,
) -> list[dict]:
    slot_rows = slots or _slots()
    default = probabilities or {
        "semantic_consistent": 0.7,
        "surface_cue_consistent": 0.2,
        "parse_failure": 0.1,
    }
    return [
        {
            "schema_version": "0.1.0",
            **slot,
            "probabilities": dict(
                probabilities_by_target.get(slot["target_id"], default)
                if probabilities_by_target is not None
                else default
            ),
            "abstain": False,
            "abstention_reason": None,
        }
        for slot in slot_rows
    ]


def _key(
    slots: list[dict[str, str]] | None = None,
    *,
    cluster_by_target: dict[str, str] | None = None,
    counts: dict[str, int] | None = None,
) -> list[dict]:
    slot_rows = slots or _slots()
    clusters = cluster_by_target or {TARGET_A: CLUSTER_A, TARGET_B: CLUSTER_B}
    outcome_counts = counts or {
        "semantic_consistent": 7,
        "surface_cue_consistent": 2,
        "parse_failure": 1,
    }
    return [
        {
            "schema_version": "0.1.0",
            **slot,
            "dependency_cluster_id": clusters[slot["target_id"]],
            "outcome_counts": dict(outcome_counts),
            "trial_count": sum(outcome_counts.values()),
        }
        for slot in slot_rows
    ]


def _weak_observations(
    targets: tuple[str, ...] = (TARGET_A, TARGET_B), *, parsed_per_target: int = 6
) -> list[dict[str, str]]:
    return [
        {
            "target_id": target,
            "case_id": f"{1000 + replicate:032x}",
            "projection_id": f"{2000 + replicate:032x}",
            "replicate_id": f"{3000 + replicate:032x}",
            "prompt_text": f"Committed weak prompt {replicate}",
            "output_text": "FINAL: A" if replicate % 2 == 0 else "FINAL: B",
        }
        for target in targets
        for replicate in range(parsed_per_target)
    ]


def _gate_inputs(
    heldout_slots: list[dict[str, str]],
    heldout_key: list[dict],
    development_slots: list[dict[str, str]],
    development_key: list[dict],
    weak_observations: list[dict[str, str]],
) -> dict:
    return {
        "weak_observations": weak_observations,
        "development_scoring_key": development_key,
        "development_slots": development_slots,
    }


def _validator(schema_name: str):
    schema = json.loads((REPO_ROOT / "schemas" / schema_name).read_text(encoding="utf-8"))
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    return validator_class(schema)


class ProspectiveContractTests(unittest.TestCase):
    def test_inventory_is_exactly_two_aggregate_kinds_per_target(self) -> None:
        inventory = validate_challenge_slot_inventory(reversed(_slots()))
        self.assertEqual(
            [row["challenge_kind"] for row in inventory[:2]],
            [
                "heldout_cue_conflict",
                "heldout_mismatch_table",
            ],
        )
        with self.assertRaisesRegex(ProspectiveContractError, "every frozen challenge"):
            validate_challenge_slot_inventory(_slots()[:-1])

        duplicate_kind = _slots()
        duplicate_kind[1]["challenge_kind"] = "heldout_cue_conflict"
        with self.assertRaisesRegex(ProspectiveContractError, "duplicate challenge kind"):
            validate_challenge_slot_inventory(duplicate_kind)

    def test_predictions_require_complete_slots_and_strict_positive_simplex(self) -> None:
        self.assertEqual(len(validate_challenge_predictions(_predictions(), _slots())), 4)
        with self.assertRaisesRegex(ProspectiveContractError, "cover every"):
            validate_challenge_predictions(_predictions()[:-1], _slots())

        invalid_sum = _predictions()
        invalid_sum[0]["probabilities"] = {
            "semantic_consistent": 0.8,
            "surface_cue_consistent": 0.8,
            "parse_failure": PROBABILITY_FLOOR,
        }
        with self.assertRaisesRegex(ProspectiveContractError, "sum to one"):
            validate_challenge_predictions(invalid_sum, _slots())

        zero_probability = _predictions()
        zero_probability[0]["probabilities"] = {
            "semantic_consistent": 0.8,
            "surface_cue_consistent": 0.2,
            "parse_failure": 0.0,
        }
        with self.assertRaisesRegex(ProspectiveContractError, "must be in"):
            validate_challenge_predictions(zero_probability, _slots())

        abstained = _predictions()
        abstained[0]["abstain"] = True
        abstained[0]["abstention_reason"] = "free-form-story"
        with self.assertRaisesRegex(ProspectiveContractError, "frozen abstention"):
            validate_challenge_predictions(abstained, _slots())

    def test_scoring_is_trial_then_target_then_equal_cluster_macro(self) -> None:
        slots = _slots((TARGET_A, TARGET_B, TARGET_C))
        cluster_by_target = {
            TARGET_A: CLUSTER_A,
            TARGET_B: CLUSTER_A,
            TARGET_C: CLUSTER_B,
        }
        key = _key(
            slots,
            cluster_by_target=cluster_by_target,
            counts={
                "semantic_consistent": 10,
                "surface_cue_consistent": 0,
                "parse_failure": 0,
            },
        )
        probabilities_by_target = {
            TARGET_A: {
                "semantic_consistent": 0.8,
                "surface_cue_consistent": 0.1,
                "parse_failure": 0.1,
            },
            TARGET_B: {
                "semantic_consistent": 0.8,
                "surface_cue_consistent": 0.1,
                "parse_failure": 0.1,
            },
            TARGET_C: {
                "semantic_consistent": 0.2,
                "surface_cue_consistent": 0.4,
                "parse_failure": 0.4,
            },
        }
        result = score_challenge_predictions(
            _predictions(slots, probabilities_by_target=probabilities_by_target),
            key,
            slots,
        )
        expected = (-math.log(0.8) - math.log(0.2)) / 2
        equal_target_but_not_cluster = (-math.log(0.8) * 2 - math.log(0.2)) / 3
        self.assertAlmostEqual(result["macro_dependency_cluster_log_loss"], expected)
        self.assertNotAlmostEqual(
            result["macro_dependency_cluster_log_loss"], equal_target_but_not_cluster
        )
        self.assertEqual(result["dependency_cluster_count"], 2)
        self.assertEqual(result["macro_dependency_cluster_slot_coverage"], 1.0)

        abstained = _predictions(slots, probabilities_by_target=probabilities_by_target)
        abstained[0]["abstain"] = True
        abstained[0]["abstention_reason"] = "non_identifiable"
        abstained_result = score_challenge_predictions(abstained, key, slots)
        self.assertAlmostEqual(abstained_result["macro_dependency_cluster_log_loss"], expected)
        self.assertLess(abstained_result["macro_dependency_cluster_slot_coverage"], 1.0)

    def test_scoring_key_fails_closed_on_arithmetic_and_cluster_format(self) -> None:
        self.assertEqual(len(validate_challenge_scoring_key(_key(), _slots())), 4)
        invalid = _key()
        invalid[0]["trial_count"] = 11
        with self.assertRaisesRegex(ProspectiveContractError, "sum to trial_count"):
            validate_challenge_scoring_key(invalid, _slots())

        invalid_cluster = _key()
        invalid_cluster[0]["dependency_cluster_id"] = "marketing-family"
        with self.assertRaisesRegex(ProspectiveContractError, "dependency-\\[0-9a-f\\]"):
            validate_challenge_scoring_key(invalid_cluster, _slots())

    def test_generator_hard_routes_yield_distinct_all_mass_scoring_keys(self) -> None:
        design = build_oss_design([101])
        cases = {case.case_id: case for case in design.cases}
        semantic_counts = {
            kind: {
                label: 0
                for label in (
                    "semantic_consistent",
                    "surface_cue_consistent",
                    "parse_failure",
                )
            }
            for kind in (
                OSSProjectionKind.HELDOUT_CUE_CONFLICT,
                OSSProjectionKind.HELDOUT_MISMATCH_TABLE,
            )
        }
        cue_counts = {kind: dict(counts) for kind, counts in semantic_counts.items()}

        for projection in design.heldout_challenges:
            case = cases[projection.case_id]
            self.assertIsNot(case.semantic_solution, case.surface_cue)
            authority_factors = {
                "semantic_solution": case.semantic_solution,
                "surface_cue": case.surface_cue,
                "answer_codebook": case.answer_codebook,
            }
            semantic_output = format_final(
                encode_answer(case.semantic_solution, case.answer_codebook)
            )
            cue_output = format_final(encode_answer(case.surface_cue, case.answer_codebook))
            semantic_counts[projection.kind][
                derive_relational_challenge_outcome(semantic_output, **authority_factors)
            ] += 1
            cue_counts[projection.kind][
                derive_relational_challenge_outcome(cue_output, **authority_factors)
            ] += 1

        for kind in semantic_counts:
            with self.subTest(challenge_kind=kind.value):
                self.assertEqual(
                    semantic_counts[kind],
                    {
                        "semantic_consistent": 4,
                        "surface_cue_consistent": 0,
                        "parse_failure": 0,
                    },
                )
                self.assertEqual(
                    cue_counts[kind],
                    {
                        "semantic_consistent": 0,
                        "surface_cue_consistent": 4,
                        "parse_failure": 0,
                    },
                )
                self.assertNotEqual(semantic_counts[kind], cue_counts[kind])

        semantic_slots = _slots((TARGET_A,), start_slot=200)
        cue_slots = _slots((TARGET_B,), start_slot=300)

        def scoring_key(
            slots: list[dict[str, str]],
            counts_by_kind: dict[OSSProjectionKind, dict[str, int]],
            cluster_id: str,
        ) -> list[dict]:
            return [
                {
                    "schema_version": "0.1.0",
                    **slot,
                    "dependency_cluster_id": cluster_id,
                    "outcome_counts": dict(
                        counts_by_kind[OSSProjectionKind(slot["challenge_kind"])]
                    ),
                    "trial_count": sum(
                        counts_by_kind[OSSProjectionKind(slot["challenge_kind"])].values()
                    ),
                }
                for slot in slots
            ]

        validated_semantic_key = validate_challenge_scoring_key(
            scoring_key(semantic_slots, semantic_counts, CLUSTER_A), semantic_slots
        )
        validated_cue_key = validate_challenge_scoring_key(
            scoring_key(cue_slots, cue_counts, CLUSTER_B), cue_slots
        )
        self.assertTrue(
            all(
                row["outcome_counts"]["semantic_consistent"] == row["trial_count"]
                for row in validated_semantic_key
            )
        )
        self.assertTrue(
            all(
                row["outcome_counts"]["surface_cue_consistent"] == row["trial_count"]
                for row in validated_cue_key
            )
        )

        aligned_case = next(
            case for case in design.cases if case.semantic_solution is case.surface_cue
        )
        with self.assertRaisesRegex(ProspectiveContractError, "semantic_solution !="):
            derive_relational_challenge_outcome(
                "FINAL: A",
                semantic_solution=aligned_case.semantic_solution,
                surface_cue=aligned_case.surface_cue,
                answer_codebook=aligned_case.answer_codebook,
            )

    def test_weak_orbit_baseline_is_route_agnostic_add_one_split(self) -> None:
        observations = [
            {"target_id": TARGET_A, "output_text": "FINAL: A"},
            {"target_id": TARGET_A, "output_text": "FINAL: A"},
            {"target_id": TARGET_A, "output_text": "FINAL: B"},
            {"target_id": TARGET_A, "output_text": "not parseable"},
            {"target_id": TARGET_B, "output_text": "not parseable"},
        ]
        baseline = weak_orbit_route_agnostic_baseline(observations, _slots())
        by_target = {row["target_id"]: row["probabilities"] for row in baseline}
        self.assertEqual(
            by_target[TARGET_A],
            {
                "semantic_consistent": 2.5 / 7,
                "surface_cue_consistent": 2.5 / 7,
                "parse_failure": 2 / 7,
            },
        )
        self.assertEqual(
            by_target[TARGET_B],
            {
                "semantic_consistent": 1 / 4,
                "surface_cue_consistent": 1 / 4,
                "parse_failure": 2 / 4,
            },
        )

        unknown = observations + [{"target_id": TARGET_C, "output_text": "FINAL: A"}]
        with self.assertRaisesRegex(ProspectiveContractError, "uncommitted target"):
            weak_orbit_route_agnostic_baseline(unknown, _slots())

    def test_development_baseline_adds_one_then_averages_clusters_by_kind(self) -> None:
        development_slots = _slots((TARGET_A, TARGET_B))
        development_key = _key(
            development_slots,
            cluster_by_target={TARGET_A: CLUSTER_A, TARGET_B: CLUSTER_B},
            counts={
                "semantic_consistent": 10,
                "surface_cue_consistent": 0,
                "parse_failure": 0,
            },
        )
        for row in development_key:
            if row["target_id"] == TARGET_B:
                row["outcome_counts"] = {
                    "semantic_consistent": 0,
                    "surface_cue_consistent": 10,
                    "parse_failure": 0,
                }
        heldout_slots = _slots((TARGET_C,), start_slot=100)
        heldout_key = _key(
            heldout_slots,
            cluster_by_target={TARGET_C: CLUSTER_C},
        )
        baseline = development_challenge_marginal_baseline(
            development_key,
            development_slots,
            heldout_key,
            heldout_slots,
        )
        for prediction in baseline:
            self.assertAlmostEqual(prediction["probabilities"]["semantic_consistent"], 6 / 13)
            self.assertAlmostEqual(prediction["probabilities"]["surface_cue_consistent"], 6 / 13)
            self.assertAlmostEqual(prediction["probabilities"]["parse_failure"], 1 / 13)

        with self.assertRaisesRegex(ProspectiveContractError, "must be disjoint"):
            development_challenge_marginal_baseline(
                development_key,
                development_slots,
                development_key,
                development_slots,
            )
        with self.assertRaisesRegex(ProspectiveContractError, "must be disjoint"):
            cluster_overlapping_key = _key(
                heldout_slots,
                cluster_by_target={TARGET_C: CLUSTER_A},
            )
            development_challenge_marginal_baseline(
                development_key,
                development_slots,
                cluster_overlapping_key,
                heldout_slots,
            )

    def test_candidate_gate_uses_stronger_baseline_and_exact_ten_percent_rule(self) -> None:
        heldout_slots = _slots()
        heldout_key = _key(
            heldout_slots,
            counts={
                "semantic_consistent": 10,
                "surface_cue_consistent": 0,
                "parse_failure": 0,
            },
        )
        weak_observations = _weak_observations()
        development_slots = _slots((TARGET_C,), start_slot=100)
        tied_development_key = _key(
            development_slots,
            cluster_by_target={TARGET_C: CLUSTER_C},
            counts={
                "semantic_consistent": 3,
                "surface_cue_consistent": 3,
                "parse_failure": 0,
            },
        )
        baseline_probability = 4 / 9
        boundary_probability = baseline_probability ** (1.0 - PRIMARY_GATE_RELATIVE_REDUCTION)
        candidate = _predictions(
            heldout_slots,
            probabilities={
                "semantic_consistent": boundary_probability,
                "surface_cue_consistent": (1.0 - boundary_probability) / 2,
                "parse_failure": (1.0 - boundary_probability) / 2,
            },
        )
        result = evaluate_verified_candidate_gate(
            candidate,
            heldout_key,
            heldout_slots,
            **_gate_inputs(
                heldout_slots,
                heldout_key,
                development_slots,
                tied_development_key,
                weak_observations,
            ),
        )
        self.assertEqual(result["stronger_baseline_id"], WEAK_ORBIT_BASELINE_ID)
        self.assertTrue(result["passes_primary_gate"])
        self.assertAlmostEqual(result["observed_relative_reduction"], 0.10)

        stronger_development_key = _key(
            development_slots,
            cluster_by_target={TARGET_C: CLUSTER_C},
            counts={
                "semantic_consistent": 10,
                "surface_cue_consistent": 0,
                "parse_failure": 0,
            },
        )
        failing_candidate = _predictions(
            heldout_slots,
            probabilities={
                "semantic_consistent": 0.72,
                "surface_cue_consistent": 0.14,
                "parse_failure": 0.14,
            },
        )
        failed = evaluate_verified_candidate_gate(
            failing_candidate,
            heldout_key,
            heldout_slots,
            **_gate_inputs(
                heldout_slots,
                heldout_key,
                development_slots,
                stronger_development_key,
                weak_observations,
            ),
        )
        self.assertEqual(failed["stronger_baseline_id"], DEVELOPMENT_BASELINE_ID)
        self.assertFalse(failed["passes_primary_gate"])

    def test_fabricated_baseline_vectors_cannot_change_the_gate(self) -> None:
        heldout_slots = _slots()
        heldout_key = _key(
            heldout_slots,
            counts={
                "semantic_consistent": 10,
                "surface_cue_consistent": 0,
                "parse_failure": 0,
            },
        )
        development_slots = _slots((TARGET_C,), start_slot=100)
        development_key = _key(
            development_slots,
            cluster_by_target={TARGET_C: CLUSTER_C},
            counts={
                "semantic_consistent": 10,
                "surface_cue_consistent": 0,
                "parse_failure": 0,
            },
        )
        candidate = _predictions(
            heldout_slots,
            probabilities={
                "semantic_consistent": 0.72,
                "surface_cue_consistent": 0.14,
                "parse_failure": 0.14,
            },
        )
        fabricated_baseline = _predictions(
            heldout_slots,
            probabilities={
                "semantic_consistent": 0.1,
                "surface_cue_consistent": 0.45,
                "parse_failure": 0.45,
            },
        )
        candidate_score = score_challenge_predictions(candidate, heldout_key, heldout_slots)
        fabricated_score = score_challenge_predictions(
            fabricated_baseline, heldout_key, heldout_slots
        )
        self.assertLessEqual(
            candidate_score["macro_dependency_cluster_log_loss"],
            0.9 * fabricated_score["macro_dependency_cluster_log_loss"],
        )

        gate_inputs = _gate_inputs(
            heldout_slots,
            heldout_key,
            development_slots,
            development_key,
            _weak_observations(),
        )
        result = evaluate_verified_candidate_gate(
            candidate,
            heldout_key,
            heldout_slots,
            **gate_inputs,
        )
        self.assertFalse(result["passes_primary_gate"])
        self.assertEqual(result["stronger_baseline_id"], DEVELOPMENT_BASELINE_ID)
        with self.assertRaises(TypeError):
            evaluate_verified_candidate_gate(
                candidate,
                heldout_key,
                heldout_slots,
                weak_orbit_baseline_predictions=fabricated_baseline,
                **gate_inputs,
            )

    def test_pure_gate_rejects_duplicate_weak_and_inexact_development_rows(self) -> None:
        heldout_slots = _slots()
        heldout_key = _key(heldout_slots)
        development_slots = _slots((TARGET_C,), start_slot=100)
        development_key = _key(
            development_slots,
            cluster_by_target={TARGET_C: CLUSTER_C},
        )
        weak_observations = _weak_observations()
        valid_inputs = _gate_inputs(
            heldout_slots,
            heldout_key,
            development_slots,
            development_key,
            weak_observations,
        )
        candidate = _predictions(heldout_slots)

        extra_weak = dict(weak_observations[0])
        extra_weak["replicate_id"] = "f" * 32
        weak_mutations = {
            "unknown_target": [*weak_observations, {**extra_weak, "target_id": TARGET_C}],
            "duplicate": [*weak_observations, dict(weak_observations[0])],
        }
        for name, mutation in weak_mutations.items():
            with self.subTest(surface="weak", mutation=name):
                inputs = dict(valid_inputs)
                inputs["weak_observations"] = mutation
                with self.assertRaises(ProspectiveContractError):
                    evaluate_verified_candidate_gate(
                        candidate,
                        heldout_key,
                        heldout_slots,
                        **inputs,
                    )

        extra_development = dict(development_key[0])
        extra_development["challenge_slot_id"] = "f" * 32
        development_mutations = {
            "missing": development_key[:-1],
            "extra": [*development_key, extra_development],
            "duplicate": [*development_key, dict(development_key[0])],
        }
        for name, mutation in development_mutations.items():
            with self.subTest(surface="development", mutation=name):
                inputs = dict(valid_inputs)
                inputs["development_scoring_key"] = mutation
                with self.assertRaises(ProspectiveContractError):
                    evaluate_verified_candidate_gate(
                        candidate,
                        heldout_key,
                        heldout_slots,
                        **inputs,
                    )

    def test_pure_gate_accepts_no_caller_nominated_commitment_hash(self) -> None:
        heldout_slots = _slots()
        heldout_key = _key(heldout_slots)
        development_slots = _slots((TARGET_C,), start_slot=100)
        development_key = _key(
            development_slots,
            cluster_by_target={TARGET_C: CLUSTER_C},
        )
        valid_inputs = _gate_inputs(
            heldout_slots,
            heldout_key,
            development_slots,
            development_key,
            _weak_observations(),
        )
        hash_fields = (
            "expected_weak_observation_records_sha256",
            "expected_weak_observation_inventory_sha256",
            "expected_development_scoring_key_sha256",
            "expected_development_slot_inventory_sha256",
            "expected_heldout_scoring_key_sha256",
            "expected_heldout_slot_inventory_sha256",
        )
        for field in hash_fields:
            with self.subTest(commitment=field):
                inputs = dict(valid_inputs)
                inputs[field] = "f" * 64
                with self.assertRaises(TypeError):
                    evaluate_verified_candidate_gate(
                        _predictions(heldout_slots),
                        heldout_key,
                        heldout_slots,
                        **inputs,
                    )

    def test_json_schemas_accept_the_executable_contract_examples(self) -> None:
        examples = {
            "challenge_slot.schema.json": _slots()[0],
            "challenge_prediction.schema.json": _predictions()[0],
            "challenge_scoring_key.schema.json": _key()[0],
        }
        for schema_name, example in examples.items():
            with self.subTest(schema=schema_name):
                _validator(schema_name).validate(example)


if __name__ == "__main__":
    unittest.main()
