from __future__ import annotations

import unittest

from latent_trace_tomography.split import (
    DependencyEdge,
    DependencyKind,
    ModelUnit,
    build_leave_dependency_cluster_out_folds,
    derive_dependency_clusters,
    partition_content_seeds,
    split_summary,
    validate_fold_dependency_separation,
)


def _units() -> tuple[ModelUnit, ...]:
    return (
        ModelUnit("base-a", "run-a", "arch-a", "semantic"),
        ModelUnit("fine-tune-a", "run-a-ft", "arch-a", "shortcut"),
        ModelUnit("base-b", "run-b", "arch-a", "mixed"),
        ModelUnit("base-c", "run-c", "arch-c", "semantic"),
    )


class SplitRuleTests(unittest.TestCase):
    def test_weight_descendant_is_one_dependency_cluster(self) -> None:
        edges = (DependencyEdge("base-a", "fine-tune-a", DependencyKind.FINE_TUNE),)
        clusters = derive_dependency_clusters(_units(), edges)
        member_sets = {cluster.model_unit_ids for cluster in clusters}

        self.assertEqual(len(clusters), 3)
        self.assertIn(("base-a", "fine-tune-a"), member_sets)
        self.assertEqual(split_summary(_units(), edges)["effective_n"], 3)

    def test_outer_folds_never_split_a_dependency_cluster(self) -> None:
        edges = (DependencyEdge("base-a", "fine-tune-a", DependencyKind.FINE_TUNE),)
        clusters = derive_dependency_clusters(_units(), edges)
        folds = build_leave_dependency_cluster_out_folds(_units(), edges)

        validate_fold_dependency_separation(folds, clusters)
        self.assertEqual(len(folds), 3)
        for fold in folds:
            self.assertTrue(set(fold.train_model_unit_ids).isdisjoint(fold.test_model_unit_ids))

    def test_architecture_label_alone_does_not_merge_independent_runs(self) -> None:
        clusters = derive_dependency_clusters(_units(), ())

        self.assertEqual(len(clusters), 4)

    def test_unknown_duplicate_and_self_dependencies_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown"):
            derive_dependency_clusters(
                _units(),
                (DependencyEdge("base-a", "missing", DependencyKind.MERGE_PARENT),),
            )
        duplicate = DependencyEdge("base-a", "base-b", DependencyKind.DISTILLATION_TEACHER)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            derive_dependency_clusters(_units(), (duplicate, duplicate))
        with self.assertRaisesRegex(ValueError, "distinct"):
            DependencyEdge("base-a", "base-a", DependencyKind.QUANTIZATION)

    def test_content_seed_partitions_are_exact_disjoint_and_order_invariant(self) -> None:
        seeds = tuple(range(64))
        first = partition_content_seeds(seeds)
        second = partition_content_seeds(reversed(seeds))

        self.assertEqual(first, second)
        self.assertEqual(
            {name: len(items) for name, items in first.items()},
            {
                "D_site_discovery": 8,
                "D_causal_label": 16,
                "D_behavior_fit": 24,
                "D_sealed_test": 16,
            },
        )
        flattened = [seed for partition in first.values() for seed in partition]
        self.assertEqual(set(flattened), set(seeds))
        self.assertEqual(len(flattened), len(set(flattened)))
        with self.assertRaisesRegex(ValueError, "exactly 64"):
            partition_content_seeds(range(63))


if __name__ == "__main__":
    unittest.main()
