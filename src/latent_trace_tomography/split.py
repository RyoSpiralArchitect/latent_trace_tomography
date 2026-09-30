from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable


SPLIT_RULE_VERSION = "0.1.0"
SPLIT_RULE_ID = "leave_dependency_cluster_out_v1"
CONTENT_PARTITION_COUNTS = (
    ("D_site_discovery", 8),
    ("D_causal_label", 16),
    ("D_behavior_fit", 24),
    ("D_sealed_test", 16),
)


class DependencyKind(str, Enum):
    """Learned-state dependencies that make two model units non-independent."""

    SHARED_LEARNED_WEIGHTS = "shared_learned_weights"
    BASE_DESCENDANT = "base_descendant"
    CONTINUED_PRETRAINING = "continued_pretraining"
    FINE_TUNE = "fine_tune"
    ADAPTER = "adapter"
    QUANTIZATION = "quantization"
    MERGE_PARENT = "merge_parent"
    DISTILLATION_TEACHER = "distillation_teacher"


@dataclass(frozen=True)
class ModelUnit:
    """One independent training run before ancestry/dependency clustering."""

    model_unit_id: str
    independent_training_run_id: str
    architecture_family_id: str
    anchor_condition_id: str

    def __post_init__(self) -> None:
        for field, value in (
            ("model_unit_id", self.model_unit_id),
            ("independent_training_run_id", self.independent_training_run_id),
            ("architecture_family_id", self.architecture_family_id),
            ("anchor_condition_id", self.anchor_condition_id),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field} must be non-empty")


@dataclass(frozen=True)
class DependencyEdge:
    left_model_unit_id: str
    right_model_unit_id: str
    kind: DependencyKind

    def __post_init__(self) -> None:
        if not self.left_model_unit_id or not self.right_model_unit_id:
            raise ValueError("dependency edge endpoints must be non-empty")
        if self.left_model_unit_id == self.right_model_unit_id:
            raise ValueError("dependency edges must connect distinct model units")


@dataclass(frozen=True)
class DependencyCluster:
    dependency_cluster_id: str
    model_unit_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dependency_cluster_id": self.dependency_cluster_id,
            "model_unit_ids": list(self.model_unit_ids),
        }


@dataclass(frozen=True)
class OuterFold:
    fold_id: str
    heldout_dependency_cluster_id: str
    train_model_unit_ids: tuple[str, ...]
    test_model_unit_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fold_id": self.fold_id,
            "heldout_dependency_cluster_id": self.heldout_dependency_cluster_id,
            "train_model_unit_ids": list(self.train_model_unit_ids),
            "test_model_unit_ids": list(self.test_model_unit_ids),
        }


def derive_dependency_clusters(
    model_units: Iterable[ModelUnit], dependency_edges: Iterable[DependencyEdge]
) -> tuple[DependencyCluster, ...]:
    """Return deterministic connected components of the learned-state graph.

    Edge direction is intentionally ignored for independence: a base/descendant,
    teacher/student, or merge-parent relationship contaminates both sides of a
    train/test split.
    """

    units = tuple(sorted(model_units, key=lambda unit: unit.model_unit_id))
    unit_ids = [unit.model_unit_id for unit in units]
    if not unit_ids:
        raise ValueError("at least one model unit is required")
    if len(unit_ids) != len(set(unit_ids)):
        raise ValueError("model_unit_id values must be unique")
    training_run_ids = [unit.independent_training_run_id for unit in units]
    if len(training_run_ids) != len(set(training_run_ids)):
        raise ValueError("independent_training_run_id values must be unique")

    parent = {unit_id: unit_id for unit_id in unit_ids}

    def find(unit_id: str) -> str:
        while parent[unit_id] != unit_id:
            parent[unit_id] = parent[parent[unit_id]]
            unit_id = parent[unit_id]
        return unit_id

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        lower, higher = sorted((left_root, right_root))
        parent[higher] = lower

    known = set(unit_ids)
    normalized_edges = sorted(
        dependency_edges,
        key=lambda edge: (
            min(edge.left_model_unit_id, edge.right_model_unit_id),
            max(edge.left_model_unit_id, edge.right_model_unit_id),
            edge.kind.value,
        ),
    )
    seen_edges: set[tuple[str, str, DependencyKind]] = set()
    for edge in normalized_edges:
        if edge.left_model_unit_id not in known or edge.right_model_unit_id not in known:
            raise ValueError("dependency edge references an unknown model unit")
        identity = (
            min(edge.left_model_unit_id, edge.right_model_unit_id),
            max(edge.left_model_unit_id, edge.right_model_unit_id),
            edge.kind,
        )
        if identity in seen_edges:
            raise ValueError("duplicate dependency edge")
        seen_edges.add(identity)
        union(edge.left_model_unit_id, edge.right_model_unit_id)

    members_by_root: dict[str, list[str]] = {}
    for unit_id in unit_ids:
        members_by_root.setdefault(find(unit_id), []).append(unit_id)

    clusters = []
    for members in sorted(tuple(sorted(items)) for items in members_by_root.values()):
        material = "\x00".join(members).encode("utf-8")
        cluster_id = "dependency-" + hashlib.sha256(material).hexdigest()[:16]
        clusters.append(DependencyCluster(cluster_id, members))
    return tuple(sorted(clusters, key=lambda cluster: cluster.dependency_cluster_id))


def build_leave_dependency_cluster_out_folds(
    model_units: Iterable[ModelUnit], dependency_edges: Iterable[DependencyEdge]
) -> tuple[OuterFold, ...]:
    units = tuple(model_units)
    clusters = derive_dependency_clusters(units, dependency_edges)
    all_unit_ids = tuple(sorted(unit.model_unit_id for unit in units))
    folds = []
    for cluster in clusters:
        test_ids = cluster.model_unit_ids
        test_set = set(test_ids)
        train_ids = tuple(unit_id for unit_id in all_unit_ids if unit_id not in test_set)
        folds.append(
            OuterFold(
                fold_id=f"holdout-{cluster.dependency_cluster_id}",
                heldout_dependency_cluster_id=cluster.dependency_cluster_id,
                train_model_unit_ids=train_ids,
                test_model_unit_ids=test_ids,
            )
        )
    return tuple(folds)


def validate_fold_dependency_separation(
    folds: Iterable[OuterFold], clusters: Iterable[DependencyCluster]
) -> None:
    cluster_by_unit = {
        unit_id: cluster.dependency_cluster_id
        for cluster in clusters
        for unit_id in cluster.model_unit_ids
    }
    for fold in folds:
        train_clusters = {cluster_by_unit[unit_id] for unit_id in fold.train_model_unit_ids}
        test_clusters = {cluster_by_unit[unit_id] for unit_id in fold.test_model_unit_ids}
        if train_clusters & test_clusters:
            raise ValueError(f"dependency cluster crosses fold={fold.fold_id}")
        if test_clusters != {fold.heldout_dependency_cluster_id}:
            raise ValueError(f"fold={fold.fold_id} does not hold out exactly one cluster")


def split_summary(
    model_units: Iterable[ModelUnit], dependency_edges: Iterable[DependencyEdge]
) -> dict[str, Any]:
    units = tuple(model_units)
    edges = tuple(dependency_edges)
    clusters = derive_dependency_clusters(units, edges)
    folds = build_leave_dependency_cluster_out_folds(units, edges)
    validate_fold_dependency_separation(folds, clusters)
    return {
        "split_rule_version": SPLIT_RULE_VERSION,
        "effective_n": len(clusters),
        "dependency_clusters": [cluster.to_dict() for cluster in clusters],
        "outer_folds": [fold.to_dict() for fold in folds],
    }


def partition_content_seeds(content_seeds: Iterable[int]) -> dict[str, tuple[int, ...]]:
    """Apply the frozen 8/16/24/16 semantic-instance partition."""

    seeds = tuple(content_seeds)
    required_count = sum(count for _, count in CONTENT_PARTITION_COUNTS)
    if len(seeds) != required_count or len(set(seeds)) != required_count:
        raise ValueError(f"exactly {required_count} unique content seeds are required")
    if any(type(seed) is not int or seed < 0 for seed in seeds):
        raise ValueError("content seeds must be non-negative integers")

    def order_key(seed: int) -> bytes:
        material = f"{SPLIT_RULE_ID}:{seed}".encode("utf-8")
        return hashlib.sha256(material).digest()

    ordered = tuple(sorted(seeds, key=lambda seed: (order_key(seed), seed)))
    partitions: dict[str, tuple[int, ...]] = {}
    cursor = 0
    for partition_id, count in CONTENT_PARTITION_COUNTS:
        partitions[partition_id] = ordered[cursor : cursor + count]
        cursor += count
    return partitions
