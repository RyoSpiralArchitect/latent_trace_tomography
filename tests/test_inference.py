from __future__ import annotations

import unittest

from latent_trace_tomography.features import FeatureVector, build_feature_vectors
from latent_trace_tomography.inference import CentroidAuditor, score_predictions
from latent_trace_tomography.schema import (
    ProjectionKind,
    ProjectionRole,
    Split,
    TextObservation,
)


def _observation(
    *,
    case_id: str,
    kind: ProjectionKind,
    output_text: str,
) -> TextObservation:
    return TextObservation(
        run_id="run",
        target_id="evaluation-target",
        split=Split.EVALUATION,
        case_id=case_id,
        projection_id=f"{case_id}:{kind.value}",
        projection_kind=kind,
        projection_role=ProjectionRole.OBSERVATION,
        sample_index=0,
        prompt_text="controlled prompt",
        output_text=output_text,
    )


def _three_feature_auditor() -> CentroidAuditor:
    feature_values = {
        "parse_rate": 1.0,
        "baseline_accept_rate": 0.5,
        "agreement_irrelevant_distractor": 1.0,
    }
    vectors = [
        FeatureVector("semantic-a", feature_values),
        FeatureVector("semantic-b", {**feature_values, "agreement_irrelevant_distractor": 0.9}),
        FeatureVector("cue-a", {**feature_values, "agreement_irrelevant_distractor": 0.0}),
        FeatureVector("cue-b", {**feature_values, "agreement_irrelevant_distractor": 0.1}),
    ]
    labels = {
        "semantic-a": "semantic_route",
        "semantic-b": "semantic_route",
        "cue-a": "surface_cue_route",
        "cue-b": "surface_cue_route",
    }
    return CentroidAuditor.fit(vectors, labels)


class InferenceHardeningTests(unittest.TestCase):
    def test_default_contract_detects_globally_missing_projection_families(self) -> None:
        vector = build_feature_vectors(
            [
                _observation(
                    case_id="case-a",
                    kind=ProjectionKind.BASELINE,
                    output_text="FINAL: ACCEPT",
                )
            ]
        )[0]

        self.assertLess(vector.coverage["projection_presence_rate"], 1.0)
        self.assertIn(
            "missing_projection:case-a:irrelevant_distractor",
            vector.invalid_reasons,
        )

    def test_baseline_only_view_discards_nonbaseline_projection_outputs(self) -> None:
        observations = [
            _observation(
                case_id="case-a",
                kind=ProjectionKind.BASELINE,
                output_text="FINAL: ACCEPT",
            ),
            _observation(
                case_id="case-a",
                kind=ProjectionKind.DISTRACTOR,
                output_text="No parseable terminal answer.",
            ),
        ]

        vector = build_feature_vectors(observations, baseline_only=True)[0]

        self.assertEqual(vector.values["parse_rate"], 1.0)
        self.assertEqual(vector.values["baseline_accept_rate"], 1.0)
        self.assertNotIn("agreement_irrelevant_distractor", vector.values)
        self.assertEqual(vector.coverage["projection_presence_rate"], 1.0)
        self.assertEqual(vector.invalid_reasons, ())

    def test_missing_projection_is_not_encoded_as_disagreement_and_forces_abstention(self) -> None:
        observations = [
            _observation(
                case_id="case-a",
                kind=ProjectionKind.BASELINE,
                output_text="FINAL: ACCEPT",
            ),
            _observation(
                case_id="case-a",
                kind=ProjectionKind.DISTRACTOR,
                output_text="FINAL: ACCEPT",
            ),
            _observation(
                case_id="case-b",
                kind=ProjectionKind.BASELINE,
                output_text="FINAL: REJECT",
            ),
        ]

        vector = build_feature_vectors(
            observations,
            expected_kinds=(ProjectionKind.BASELINE, ProjectionKind.DISTRACTOR),
        )[0]

        self.assertEqual(vector.values["agreement_irrelevant_distractor"], 1.0)
        self.assertEqual(vector.coverage["projection_presence_rate"], 0.75)
        self.assertIn(
            "missing_projection:case-b:irrelevant_distractor",
            vector.invalid_reasons,
        )
        prediction = _three_feature_auditor().predict(vector)
        self.assertTrue(prediction.abstained)
        self.assertIsNone(prediction.predicted_regime)
        self.assertIn(
            "missing_projection:case-b:irrelevant_distractor",
            prediction.abstention_reasons,
        )

    def test_all_parse_failed_projection_is_explicit_and_forces_abstention(self) -> None:
        observations = [
            _observation(
                case_id="case-a",
                kind=ProjectionKind.BASELINE,
                output_text="FINAL: ACCEPT",
            ),
            _observation(
                case_id="case-a",
                kind=ProjectionKind.DISTRACTOR,
                output_text="FINAL: ACCEPT",
            ),
            _observation(
                case_id="case-b",
                kind=ProjectionKind.BASELINE,
                output_text="FINAL: REJECT",
            ),
            _observation(
                case_id="case-b",
                kind=ProjectionKind.DISTRACTOR,
                output_text="No parseable terminal answer.",
            ),
        ]

        vector = build_feature_vectors(
            observations,
            expected_kinds=(ProjectionKind.BASELINE, ProjectionKind.DISTRACTOR),
        )[0]

        self.assertEqual(vector.values["agreement_irrelevant_distractor"], 1.0)
        self.assertEqual(vector.coverage["projection_presence_rate"], 1.0)
        self.assertEqual(vector.coverage["projection_parseable_rate"], 0.75)
        self.assertIn(
            "all_parse_failed_projection:case-b:irrelevant_distractor",
            vector.invalid_reasons,
        )
        prediction = _three_feature_auditor().predict(vector)
        self.assertTrue(prediction.abstained)
        self.assertIn(
            "all_parse_failed_projection:case-b:irrelevant_distractor",
            prediction.abstention_reasons,
        )

    def test_far_out_of_distribution_vector_forces_abstention(self) -> None:
        vectors = [
            FeatureVector("a-1", {"signal": 0.0}),
            FeatureVector("a-2", {"signal": 0.1}),
            FeatureVector("b-1", {"signal": 0.9}),
            FeatureVector("b-2", {"signal": 1.0}),
        ]
        labels = {
            "a-1": "semantic_route",
            "a-2": "semantic_route",
            "b-1": "surface_cue_route",
            "b-2": "surface_cue_route",
        }
        auditor = CentroidAuditor.fit(vectors, labels)

        prediction = auditor.predict(FeatureVector("far-away", {"signal": 100.0}))

        self.assertTrue(prediction.abstained)
        self.assertIsNone(prediction.predicted_regime)
        self.assertTrue(prediction.ood_detected)
        self.assertIsNotNone(prediction.ood_distance)
        self.assertGreater(prediction.ood_distance, prediction.ood_threshold)
        self.assertIn("out_of_distribution", prediction.abstention_reasons)
        self.assertNotIn("confidence", prediction.to_dict())
        self.assertIn("separation_score", prediction.to_dict())

    def test_scoring_rejects_missing_and_duplicate_target_predictions(self) -> None:
        auditor = _three_feature_auditor()
        prediction = auditor.predict(
            FeatureVector(
                "evaluation-target",
                {
                    "parse_rate": 1.0,
                    "baseline_accept_rate": 0.5,
                    "agreement_irrelevant_distractor": 1.0,
                },
            )
        )
        labels = {
            "evaluation-target": "semantic_route",
            "missing-target": "surface_cue_route",
        }
        with self.assertRaisesRegex(ValueError, "missing=missing-target"):
            score_predictions([prediction], labels)
        with self.assertRaisesRegex(ValueError, "Duplicate prediction"):
            score_predictions(
                [prediction, prediction],
                {"evaluation-target": "semantic_route"},
            )


if __name__ == "__main__":
    unittest.main()
