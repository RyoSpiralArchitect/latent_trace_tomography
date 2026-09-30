from __future__ import annotations

import unittest
import subprocess
import sys
from collections import Counter
from pathlib import Path

from latent_trace_tomography.anchor_training import (
    CLUSTER_IDS,
    CONTENT_SEEDS_PER_CLUSTER,
    AnchorCondition,
    Codebook,
    Decision,
    build_anchor_training_manifest,
    encode_answer,
    generate_anchor_training_cases,
    generate_labeled_anchor_training_records,
    target_decision,
)


ROOT = Path(__file__).resolve().parents[1]
TRAINING_SOURCE = ROOT / "src" / "latent_trace_tomography" / "anchor_training.py"
MEASUREMENT_TEMPLATE_FRAGMENTS = (
    "Closed-world registry check.",
    "Non-authoritative archive cue:",
    "required_key",
    "submitted_key",
    "Return exactly one terminal line:",
)


class AnchorTrainingTests(unittest.TestCase):
    def test_each_cluster_is_a_complete_factorial(self) -> None:
        for cluster_id in CLUSTER_IDS:
            cases = generate_anchor_training_cases(cluster_id, content_seed_count=4)
            self.assertEqual(len(cases), 32)
            counts = Counter(case.content_seed for case in cases)
            self.assertEqual(set(counts.values()), {8})
            self.assertEqual(len({case.case_id for case in cases}), 32)

    def test_clusters_have_disjoint_seed_and_case_identities(self) -> None:
        panels = [
            generate_anchor_training_cases(cluster_id, content_seed_count=8)
            for cluster_id in CLUSTER_IDS
        ]
        for left_index, left in enumerate(panels):
            for right in panels[left_index + 1 :]:
                self.assertTrue(
                    {case.content_seed for case in left}.isdisjoint(
                        case.content_seed for case in right
                    )
                )
                self.assertTrue(
                    {case.case_id for case in left}.isdisjoint(case.case_id for case in right)
                )

    def test_training_template_is_separate_from_measurement_template(self) -> None:
        cases = generate_anchor_training_cases(CLUSTER_IDS[0], content_seed_count=2)
        source = TRAINING_SOURCE.read_text(encoding="utf-8")
        for case in cases:
            for fragment in MEASUREMENT_TEMPLATE_FRAGMENTS:
                self.assertNotIn(fragment, case.prompt)
                self.assertNotIn(fragment, source)

    def test_clean_import_does_not_load_measurement_or_execution_modules(self) -> None:
        source_root = ROOT / "src"
        script = (
            "import sys\n"
            f"sys.path.insert(0, {str(source_root)!r})\n"
            "import latent_trace_tomography.anchor_training\n"
            "for name in ('latent_trace_tomography.execution', "
            "'latent_trace_tomography.oss_design'):\n"
            "    if name in sys.modules:\n"
            "        raise SystemExit(f'leaked import: {name}')\n"
        )
        completed = subprocess.run(
            [sys.executable, "-S", "-c", script],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_anchor_rules_are_preassigned_and_mixed_uses_both_factors(self) -> None:
        for semantic in Decision:
            for cue in Decision:
                self.assertEqual(
                    target_decision(
                        AnchorCondition.SEMANTIC,
                        semantic_solution=semantic,
                        surface_cue=cue,
                    ),
                    semantic,
                )
                self.assertEqual(
                    target_decision(
                        AnchorCondition.SURFACE_CUE,
                        semantic_solution=semantic,
                        surface_cue=cue,
                    ),
                    cue,
                )
        self.assertEqual(
            target_decision(
                AnchorCondition.MIXED,
                semantic_solution=Decision.PASS,
                surface_cue=Decision.PASS,
            ),
            Decision.PASS,
        )
        self.assertEqual(
            target_decision(
                AnchorCondition.MIXED,
                semantic_solution=Decision.PASS,
                surface_cue=Decision.FAIL,
            ),
            Decision.FAIL,
        )
        self.assertEqual(
            target_decision(
                AnchorCondition.MIXED,
                semantic_solution=Decision.FAIL,
                surface_cue=Decision.PASS,
            ),
            Decision.FAIL,
        )

    def test_codebook_is_balanced(self) -> None:
        self.assertNotEqual(
            encode_answer(Decision.PASS, Codebook.IDENTITY),
            encode_answer(Decision.PASS, Codebook.SWAP),
        )
        self.assertNotEqual(
            encode_answer(Decision.PASS, Codebook.IDENTITY),
            encode_answer(Decision.FAIL, Codebook.IDENTITY),
        )

    def test_every_condition_has_an_exact_balanced_terminal_target_inventory(self) -> None:
        for condition in AnchorCondition:
            records = generate_labeled_anchor_training_records(
                CLUSTER_IDS[0],
                condition,
                content_seed_count=8,
            )
            self.assertEqual(len(records), 64)
            self.assertEqual(
                Counter(record.target_final for record in records),
                {"FINAL: A": 32, "FINAL: B": 32},
            )
            self.assertEqual(
                {record.anchor_condition_id for record in records},
                {condition.value},
            )

    def test_full_manifest_is_deterministic(self) -> None:
        first = build_anchor_training_manifest()
        second = build_anchor_training_manifest()
        self.assertEqual(first, second)
        self.assertEqual(first["content_seed_count_per_cluster"], CONTENT_SEEDS_PER_CLUSTER)
        self.assertEqual(
            sum(row["factorial_case_count"] for row in first["cluster_records"]),
            len(CLUSTER_IDS) * CONTENT_SEEDS_PER_CLUSTER * 8,
        )
        self.assertIsNone(first["learned_teacher"])
        self.assertIsNone(first["evaluation_generator_dependency"])
        for cluster in first["cluster_records"]:
            self.assertEqual(
                set(cluster["derived_target_inventory_sha256_by_condition"]),
                {condition.value for condition in AnchorCondition},
            )
            for counts in cluster["target_final_counts_by_condition"].values():
                self.assertEqual(counts, {"FINAL: A": 2048, "FINAL: B": 2048})


if __name__ == "__main__":
    unittest.main()
