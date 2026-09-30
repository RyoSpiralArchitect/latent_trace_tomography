from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

from latent_trace_tomography.features import FeatureVector
from latent_trace_tomography.schema import AuditPrediction


@dataclass(frozen=True)
class CentroidAuditor:
    feature_names: tuple[str, ...]
    means: dict[str, float]
    scales: dict[str, float]
    centroids: dict[str, dict[str, float]]
    separation_threshold: float
    ood_calibration_max_distance: float
    ood_threshold: float
    ood_threshold_multiplier: float

    @classmethod
    def fit(
        cls,
        vectors: list[FeatureVector],
        labels: dict[str, str],
        *,
        separation_threshold: float = 0.15,
        ood_threshold_multiplier: float = 2.0,
    ) -> "CentroidAuditor":
        if not 0.0 <= separation_threshold <= 1.0:
            raise ValueError("separation_threshold must be between 0 and 1")
        if not math.isfinite(ood_threshold_multiplier) or ood_threshold_multiplier <= 0.0:
            raise ValueError("ood_threshold_multiplier must be finite and positive")

        labelled = [vector for vector in vectors if vector.target_id in labels]
        if not labelled:
            raise ValueError("No labelled feature vectors were provided")
        invalid = [vector for vector in labelled if vector.invalid_reasons]
        if invalid:
            targets = ", ".join(vector.target_id for vector in invalid)
            raise ValueError(f"Invalid calibration feature vectors were provided: {targets}")

        feature_names = tuple(sorted(labelled[0].values))
        if not feature_names:
            raise ValueError("Calibration feature vectors contain no features")
        if any(tuple(sorted(vector.values)) != feature_names for vector in labelled):
            raise ValueError("Feature vectors do not share the same schema")
        for vector in labelled:
            for name in feature_names:
                value = vector.values[name]
                if value is None or not math.isfinite(value):
                    raise ValueError(
                        f"Calibration feature {name!r} is missing or non-finite "
                        f"for target {vector.target_id!r}"
                    )

        means = {
            name: sum(float(vector.values[name]) for vector in labelled) / len(labelled)
            for name in feature_names
        }
        scales: dict[str, float] = {}
        for name in feature_names:
            variance = sum(
                (float(vector.values[name]) - means[name]) ** 2 for vector in labelled
            ) / len(labelled)
            scales[name] = math.sqrt(variance) if variance > 1e-12 else 1.0

        by_label: dict[str, list[FeatureVector]] = defaultdict(list)
        for vector in labelled:
            by_label[labels[vector.target_id]].append(vector)
        if len(by_label) < 2:
            raise ValueError("At least two regime labels are required")

        centroids: dict[str, dict[str, float]] = {}
        for label, members in sorted(by_label.items()):
            centroids[label] = {
                name: sum(
                    (float(member.values[name]) - means[name]) / scales[name] for member in members
                )
                / len(members)
                for name in feature_names
            }

        calibration_distances = []
        for vector in labelled:
            standardized = {
                name: (float(vector.values[name]) - means[name]) / scales[name]
                for name in feature_names
            }
            distances = {
                label: sum((standardized[name] - centroid[name]) ** 2 for name in feature_names)
                / len(feature_names)
                for label, centroid in centroids.items()
            }
            calibration_distances.append(min(distances.values()))
        ood_calibration_max_distance = max(calibration_distances)
        ood_threshold = ood_calibration_max_distance * ood_threshold_multiplier

        return cls(
            feature_names=feature_names,
            means=means,
            scales=scales,
            centroids=centroids,
            separation_threshold=separation_threshold,
            ood_calibration_max_distance=ood_calibration_max_distance,
            ood_threshold=ood_threshold,
            ood_threshold_multiplier=ood_threshold_multiplier,
        )

    def predict(self, vector: FeatureVector) -> AuditPrediction:
        abstention_reasons = list(vector.invalid_reasons)
        coverage: dict[str, float] = {}
        for name, value in sorted(vector.coverage.items()):
            if not math.isfinite(value):
                abstention_reasons.append(f"invalid_coverage:{name}")
            else:
                coverage[name] = round(value, 6)

        expected_features = set(self.feature_names)
        observed_features = set(vector.values)
        missing_features = sorted(expected_features - observed_features)
        extra_features = sorted(observed_features - expected_features)
        if missing_features:
            abstention_reasons.append(f"feature_schema_missing:{','.join(missing_features)}")
        if extra_features:
            abstention_reasons.append(f"feature_schema_extra:{','.join(extra_features)}")

        unusable_features = []
        for name in self.feature_names:
            value = vector.values.get(name)
            if value is None or not math.isfinite(value):
                unusable_features.append(name)
        if unusable_features:
            abstention_reasons.append(f"unusable_features:{','.join(unusable_features)}")

        abstention_reasons = sorted(set(abstention_reasons))
        if missing_features or unusable_features:
            return AuditPrediction(
                target_id=vector.target_id,
                predicted_regime=None,
                separation_score=0.0,
                abstained=True,
                abstention_reasons=abstention_reasons,
                distances={},
                ood_distance=None,
                ood_threshold=round(self.ood_threshold, 6),
                ood_detected=None,
                input_coverage=coverage,
                evidence=[],
            )

        standardized = {
            name: (float(vector.values[name]) - self.means[name]) / self.scales[name]
            for name in self.feature_names
        }
        distances = {
            label: sum((standardized[name] - centroid[name]) ** 2 for name in self.feature_names)
            / len(self.feature_names)
            for label, centroid in self.centroids.items()
        }
        ranked = sorted(distances.items(), key=lambda item: (item[1], item[0]))
        best_label, best_distance = ranked[0]
        second_label, second_distance = ranked[1]
        margin = max(0.0, second_distance - best_distance)
        separation_score = 1.0 - math.exp(-margin)
        ood_detected = best_distance > self.ood_threshold + 1e-12
        if separation_score < self.separation_threshold:
            abstention_reasons.append("insufficient_separation")
        if ood_detected:
            abstention_reasons.append("out_of_distribution")
        abstention_reasons = sorted(set(abstention_reasons))
        abstained = bool(abstention_reasons)

        evidence = []
        for name in self.feature_names:
            best_delta = (standardized[name] - self.centroids[best_label][name]) ** 2
            runner_delta = (standardized[name] - self.centroids[second_label][name]) ** 2
            evidence.append(
                {
                    "feature": name,
                    "support_over_runner_up": round(runner_delta - best_delta, 6),
                    "observed_value": round(vector.values[name], 6),
                }
            )
        evidence.sort(
            key=lambda item: (-float(item["support_over_runner_up"]), str(item["feature"]))
        )
        return AuditPrediction(
            target_id=vector.target_id,
            predicted_regime=None if abstained else best_label,
            separation_score=round(separation_score, 6),
            abstained=abstained,
            abstention_reasons=abstention_reasons,
            distances={label: round(value, 6) for label, value in ranked},
            ood_distance=round(best_distance, 6),
            ood_threshold=round(self.ood_threshold, 6),
            ood_detected=ood_detected,
            input_coverage=coverage,
            evidence=evidence[:3],
        )

    def predict_many(self, vectors: list[FeatureVector]) -> list[AuditPrediction]:
        return [self.predict(vector) for vector in vectors]


def score_predictions(
    predictions: list[AuditPrediction], labels: dict[str, str]
) -> dict[str, float | int]:
    prediction_ids = [prediction.target_id for prediction in predictions]
    duplicate_ids = sorted(
        target_id for target_id in set(prediction_ids) if prediction_ids.count(target_id) > 1
    )
    if duplicate_ids:
        raise ValueError("Duplicate prediction target IDs: " + ",".join(duplicate_ids))
    prediction_id_set = set(prediction_ids)
    label_id_set = set(labels)
    missing_predictions = sorted(label_id_set - prediction_id_set)
    unexpected_predictions = sorted(prediction_id_set - label_id_set)
    if missing_predictions or unexpected_predictions:
        problems = []
        if missing_predictions:
            problems.append("missing=" + ",".join(missing_predictions))
        if unexpected_predictions:
            problems.append("unexpected=" + ",".join(unexpected_predictions))
        raise ValueError("Prediction/label target mismatch: " + "; ".join(problems))
    if not predictions:
        raise ValueError("No predictions matched evaluation labels")
    correct = sum(
        prediction.predicted_regime == labels[prediction.target_id] for prediction in predictions
    )
    covered = [prediction for prediction in predictions if not prediction.abstained]
    covered_correct = sum(
        prediction.predicted_regime == labels[prediction.target_id] for prediction in covered
    )
    return {
        "targets": len(predictions),
        "accuracy": round(correct / len(predictions), 6),
        "coverage": round(len(covered) / len(predictions), 6),
        "selective_accuracy": round(covered_correct / len(covered), 6) if covered else 0.0,
    }
