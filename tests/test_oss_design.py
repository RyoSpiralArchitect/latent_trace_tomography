from __future__ import annotations

import hashlib
import json
import unittest
from collections import Counter
from dataclasses import replace
from itertools import product

from latent_trace_tomography.oss_design import (
    AnswerCodebook,
    INTERVENTION_PROMPT_TEMPLATE_ID,
    InterventionFactor,
    OSSDesignConfig,
    OSSProjectionKind,
    OSSProjectionRole,
    RegistryDecision,
    apply_norm_matched_rotation_site_v1,
    apply_norm_matched_rotation_v1,
    build_design_summary,
    build_intervention_pairs,
    build_oss_design,
    build_oss_design_from_config,
    derive_live_content_seeds,
    derive_matched_null_seed,
    encode_answer,
    matched_null_permutation_and_signs,
    parse_final,
    render_intervention_prompt,
)


class OSSDesignTests(unittest.TestCase):
    def test_design_and_manifest_are_deterministic_and_order_independent(self) -> None:
        first = build_oss_design([17, 3])
        second = build_oss_design([3, 17])

        self.assertEqual(first, second)
        self.assertEqual(first.manifest(), second.manifest())
        self.assertEqual(len(first.manifest()["manifest_sha256"]), 64)
        self.assertNotEqual(
            build_oss_design([3, 18]).manifest()["manifest_sha256"],
            first.manifest()["manifest_sha256"],
        )

    def test_every_content_seed_has_the_complete_factorial_grid(self) -> None:
        design = build_oss_design([2, 5])
        expected_cells = set(product(RegistryDecision, RegistryDecision, AnswerCodebook))

        for content_seed in design.content_seeds:
            observed_cells = {
                (case.semantic_solution, case.surface_cue, case.answer_codebook)
                for case in design.cases
                if case.content_seed == content_seed
            }
            self.assertEqual(observed_cells, expected_cells)
            self.assertEqual(len(observed_cells), 8)

    def test_intervention_pairs_are_directed_and_single_factor(self) -> None:
        design = build_oss_design([9])
        cases = {case.case_id: case for case in design.cases}
        prompts = {prompt.case_id: prompt for prompt in design.intervention_prompts}
        counts = Counter(pair.factor for pair in design.intervention_pairs)

        self.assertEqual(
            counts,
            {
                InterventionFactor.SEMANTIC_SOLUTION: 8,
                InterventionFactor.SURFACE_CUE: 8,
                InterventionFactor.ANSWER_CODEBOOK: 8,
            },
        )
        for pair in design.intervention_pairs:
            base = cases[pair.base_case_id]
            source = cases[pair.source_case_id]
            self.assertEqual(base.content_seed, source.content_seed)
            differing = {
                factor
                for factor in InterventionFactor
                if base.factor_values()[factor.value] != source.factor_values()[factor.value]
            }
            self.assertEqual(differing, {pair.factor})
            self.assertNotEqual(pair.base_factor_value, pair.source_factor_value)
            self.assertEqual(pair.base_prompt_id, prompts[base.case_id].prompt_id)
            self.assertEqual(pair.source_prompt_id, prompts[source.case_id].prompt_id)
            self.assertEqual(pair.base_prompt_sha256, prompts[base.case_id].prompt_sha256)
            self.assertEqual(pair.source_prompt_sha256, prompts[source.case_id].prompt_sha256)

        primary_counts = Counter(pair.factor for pair in design.primary_intervention_pairs)
        self.assertEqual(
            primary_counts,
            {
                InterventionFactor.SEMANTIC_SOLUTION: 4,
                InterventionFactor.SURFACE_CUE: 4,
                InterventionFactor.ANSWER_CODEBOOK: 4,
            },
        )
        for pair in design.primary_intervention_pairs:
            base = cases[pair.base_case_id]
            self.assertIs(base.semantic_solution, base.surface_cue)
            self.assertNotEqual(pair.expected_patched_final, base.oracle_final)
            self.assertEqual(pair.analysis_stratum, "primary_aligned_base_answer_switch")
        self.assertTrue(
            all(
                pair.analysis_stratum == "secondary_nonprimary_direction"
                for pair in design.intervention_pairs
                if not pair.primary_eligible
            )
        )

    def test_causal_pairs_bind_one_authority_only_canonical_prompt_per_case(self) -> None:
        design = build_oss_design([13])
        prompts = {prompt.case_id: prompt for prompt in design.intervention_prompts}

        self.assertEqual(len(prompts), 8)
        self.assertTrue(
            all(
                prompt.template_id == INTERVENTION_PROMPT_TEMPLATE_ID for prompt in prompts.values()
            )
        )
        self.assertTrue(
            all(
                prompt.prompt_sha256
                == hashlib.sha256(prompt.prompt_text.encode("utf-8")).hexdigest()
                for prompt in prompts.values()
            )
        )
        projection_ids = {projection.projection_id for projection in design.projections}
        self.assertTrue(all(prompt.prompt_id not in projection_ids for prompt in prompts.values()))
        for pair in design.intervention_pairs:
            base_lines = prompts[pair.base_case_id].prompt_text.splitlines()
            source_lines = prompts[pair.source_case_id].prompt_text.splitlines()
            differing_lines = sum(left != right for left, right in zip(base_lines, source_lines))
            expected_differences = 2 if pair.factor is InterventionFactor.ANSWER_CODEBOOK else 1
            self.assertEqual(len(base_lines), len(source_lines))
            self.assertEqual(differing_lines, expected_differences)

    def test_caller_supplied_intervention_prompt_tampering_fails_closed(self) -> None:
        design = build_oss_design([19])
        prompts = list(design.intervention_prompts)
        prompts[0] = replace(prompts[0], prompt_text=prompts[0].prompt_text + "\ntamper")
        with self.assertRaisesRegex(ValueError, "regenerated canonical"):
            build_intervention_pairs(design.cases, prompts)

        prompts = list(design.intervention_prompts)
        prompts[0] = replace(
            render_intervention_prompt(design.cases[0]),
            prompt_sha256="0" * 64,
        )
        with self.assertRaisesRegex(ValueError, "regenerated canonical"):
            build_intervention_pairs(design.cases, prompts)

    def test_oracle_is_invariant_to_cue_and_equivariant_to_other_factors(
        self,
    ) -> None:
        design = build_oss_design([23])
        cases = {case.case_id: case for case in design.cases}

        for pair in design.intervention_pairs:
            base = cases[pair.base_case_id]
            source = cases[pair.source_case_id]
            if pair.factor is InterventionFactor.SURFACE_CUE:
                self.assertEqual(source.oracle_final, base.oracle_final)
                self.assertEqual(pair.expected_decision, source.surface_cue)
                self.assertEqual(
                    pair.expected_patched_final,
                    f"FINAL: {encode_answer(source.surface_cue, base.answer_codebook).value}",
                )
            elif pair.factor is InterventionFactor.SEMANTIC_SOLUTION:
                self.assertNotEqual(source.oracle_symbol, base.oracle_symbol)
                self.assertEqual(pair.expected_decision, source.semantic_solution)
                self.assertEqual(pair.expected_patched_final, source.oracle_final)
            else:
                self.assertNotEqual(source.oracle_symbol, base.oracle_symbol)
                self.assertEqual(pair.expected_decision, base.semantic_solution)
                self.assertEqual(pair.expected_patched_final, source.oracle_final)

        for case in design.cases:
            self.assertEqual(
                case.oracle_symbol,
                encode_answer(case.semantic_solution, case.answer_codebook),
            )
            self.assertTrue(
                all(
                    projection.oracle_final == case.oracle_final
                    for projection in design.projections
                    if projection.case_id == case.case_id
                )
            )

    def test_projection_roles_are_disjoint_and_challenges_are_excluded(self) -> None:
        design = build_oss_design([31])
        cases = {case.case_id: case for case in design.cases}
        weak_ids = {projection.projection_id for projection in design.weak_observations}
        diagnostic_ids = {projection.projection_id for projection in design.diagnostic_cue_masks}
        challenge_ids = {projection.projection_id for projection in design.heldout_challenges}

        self.assertTrue(weak_ids)
        self.assertTrue(diagnostic_ids)
        self.assertTrue(challenge_ids)
        self.assertTrue(weak_ids.isdisjoint(diagnostic_ids | challenge_ids))
        self.assertTrue(diagnostic_ids.isdisjoint(challenge_ids))
        self.assertTrue(
            all(
                projection.role is OSSProjectionRole.WEAK_OBSERVATION
                for projection in design.weak_observations
            )
        )
        self.assertTrue(
            all(
                cases[projection.case_id].semantic_solution is cases[projection.case_id].surface_cue
                for projection in design.weak_observations
            )
        )
        mismatch_case_ids = {
            case.case_id for case in design.cases if case.semantic_solution is not case.surface_cue
        }
        self.assertTrue(mismatch_case_ids)
        self.assertTrue(
            all(
                projection.role is OSSProjectionRole.HELDOUT_CHALLENGE
                for projection in design.projections
                if projection.case_id in mismatch_case_ids
            )
        )
        self.assertTrue(
            all(
                cases[projection.case_id].semantic_solution
                is not cases[projection.case_id].surface_cue
                for projection in design.heldout_challenges
            )
        )
        self.assertEqual(
            Counter(projection.kind for projection in design.heldout_challenges),
            {
                OSSProjectionKind.HELDOUT_CUE_CONFLICT: 4,
                OSSProjectionKind.HELDOUT_MISMATCH_TABLE: 4,
            },
        )
        self.assertEqual(len(weak_ids), 20)
        self.assertEqual(len(diagnostic_ids), 4)
        self.assertEqual(len(challenge_ids), 8)
        prompt_plan = design.weak_prompt_plan()
        self.assertEqual({record["projection_id"] for record in prompt_plan}, weak_ids)
        self.assertTrue(
            all(
                "oracle_final" not in record
                and "semantic_solution" not in record
                and "surface_cue" not in record
                for record in prompt_plan
            )
        )

        manifest_roles = design.manifest()["projection_ids_by_role"]
        self.assertEqual(set(manifest_roles[OSSProjectionRole.WEAK_OBSERVATION.value]), weak_ids)
        self.assertEqual(
            set(manifest_roles[OSSProjectionRole.HELDOUT_CHALLENGE.value]),
            challenge_ids,
        )
        self.assertTrue(
            challenge_ids.isdisjoint(manifest_roles[OSSProjectionRole.WEAK_OBSERVATION.value])
        )

    def test_diagnostic_mask_removes_cue_without_changing_other_content(self) -> None:
        design = build_oss_design([41])
        matched: dict[tuple[RegistryDecision, AnswerCodebook], list[str]] = {}
        cases = {case.case_id: case for case in design.cases}
        for projection in design.diagnostic_cue_masks:
            case = cases[projection.case_id]
            key = (case.semantic_solution, case.answer_codebook)
            matched.setdefault(key, []).append(projection.prompt_text)
            self.assertIn("[MASKED]", projection.prompt_text)

        self.assertTrue(all(len(set(prompts)) == 1 for prompts in matched.values()))

    def test_default_config_exposes_64_seed_json_summary(self) -> None:
        config = OSSDesignConfig()
        design = build_oss_design_from_config(config)
        summary = build_design_summary(config)

        self.assertEqual(len(config.content_seeds), 64)
        self.assertEqual(len(set(config.content_seeds)), 64)
        self.assertEqual(len(design.cases), 64 * 8)
        self.assertEqual(len(design.intervention_prompts), 64 * 8)
        self.assertEqual(summary["design_manifest"], design.manifest())
        self.assertEqual(summary["intervention_summary"]["directed_pair_count"], 64 * 8 * 3)
        self.assertEqual(
            summary["intervention_summary"]["primary_directed_pair_count"],
            64 * 4 * 3,
        )
        self.assertEqual(
            set(summary["intervention_summary"]["primary_directed_pair_count_by_factor"].values()),
            {64 * 4},
        )
        self.assertIn(
            "single-token",
            summary["generator_config"]["tokenizer_preflight_requirement"],
        )
        self.assertEqual(json.loads(json.dumps(summary, sort_keys=True)), summary)

    def test_live_seed_derivation_is_secret_keyed_and_domain_separated(self) -> None:
        first = derive_live_content_seeds(b"a" * 32, 64)
        second = derive_live_content_seeds(b"a" * 32, 64)
        other_secret = derive_live_content_seeds(b"b" * 32, 64)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)
        self.assertEqual(len(set(first)), 64)
        self.assertNotEqual(first, other_secret)
        self.assertTrue(all(0 <= seed < 2**64 for seed in first))
        with self.assertRaises(ValueError):
            derive_live_content_seeds(b"short", 64)
        with self.assertRaises(ValueError):
            derive_live_content_seeds(b"a" * 32, 0)

    def test_matched_null_seed_is_length_framed_and_has_a_fixed_vector(self) -> None:
        self.assertEqual(
            derive_matched_null_seed(
                "oss1-discovery-fixture",
                "pair-0001",
                "residual_stream_post.layer_11.carrier",
            ),
            678030459775543511,
        )
        self.assertNotEqual(
            derive_matched_null_seed("ab", "c", "d"),
            derive_matched_null_seed("a", "bc", "d"),
        )
        with self.assertRaises(ValueError):
            derive_matched_null_seed("", "pair", "site")

    def test_matched_null_rotation_has_a_fixed_cross_runtime_vector(self) -> None:
        seed64 = 678030459775543511
        base = (1.0, -2.0, 0.5, 4.0, -1.5)
        source = (2.5, -3.0, 0.5, 1.0, 2.5)

        self.assertEqual(
            matched_null_permutation_and_signs(seed64, 5),
            ((4, 2, 0, 3, 1), (1, 1, -1, 1, -1)),
        )
        patched = apply_norm_matched_rotation_v1(base, source, seed64=seed64)
        self.assertEqual(patched, (5.0, -2.0, -1.0, 1.0, -0.5))
        original_delta = tuple(
            source_value - base_value for base_value, source_value in zip(base, source)
        )
        patched_delta = tuple(value - base_value for value, base_value in zip(patched, base))
        self.assertEqual(
            sum(value * value for value in patched_delta),
            sum(value * value for value in original_delta),
        )

    def test_matched_null_rotation_is_identity_for_zero_delta_and_fails_closed(self) -> None:
        base = (1.25, -3.5, 0.0)
        self.assertEqual(
            apply_norm_matched_rotation_v1(base, base, seed64=0),
            base,
        )
        with self.assertRaises(ValueError):
            matched_null_permutation_and_signs(0, 0)
        with self.assertRaises(ValueError):
            apply_norm_matched_rotation_v1((1.0,), (1.0, 2.0), seed64=0)
        with self.assertRaises(ValueError):
            apply_norm_matched_rotation_v1((float("nan"),), (1.0,), seed64=0)

    def test_matched_null_site_rotation_preserves_positions_and_has_fixed_vector(self) -> None:
        base = (
            (1.0, -2.0, 0.5, 4.0, -1.5),
            (0.0, 1.0, 2.0, 3.0, 4.0),
        )
        source = (
            (2.5, -3.0, 0.5, 1.0, 2.5),
            (1.0, 3.0, 1.0, 3.0, 0.0),
        )
        self.assertEqual(
            apply_norm_matched_rotation_site_v1(
                base,
                source,
                seed64=678030459775543511,
            ),
            (
                (5.0, -2.0, -1.0, 1.0, -0.5),
                (-4.0, 0.0, 1.0, 3.0, 2.0),
            ),
        )
        with self.assertRaises(ValueError):
            apply_norm_matched_rotation_site_v1(
                ((1.0, 2.0), (3.0,)),
                ((1.0, 2.0), (3.0, 4.0)),
                seed64=0,
            )

    def test_terminal_parser_is_exact_and_fail_closed(self) -> None:
        self.assertEqual(parse_final("analysis\nFINAL: A\n"), "A")
        self.assertEqual(parse_final("\tFINAL: B  \r\n"), "B")
        self.assertIsNone(parse_final("final: A"))
        self.assertIsNone(parse_final("FINAL: A\nmore text"))
        self.assertIsNone(parse_final("FINAL: A\nFINAL: A"))
        self.assertIsNone(parse_final("FINAL: C"))


if __name__ == "__main__":
    unittest.main()
