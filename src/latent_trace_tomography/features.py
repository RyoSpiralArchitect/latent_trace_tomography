from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from latent_trace_tomography.schema import ProjectionKind, TextObservation


FINAL_ANSWER_RE = re.compile(r"FINAL\s*:\s*(ACCEPT|REJECT)\b", re.IGNORECASE)

AGREEMENT_KINDS = (
    ProjectionKind.PARAPHRASE,
    ProjectionKind.REORDER,
    ProjectionKind.DISTRACTOR,
    ProjectionKind.CUE_MASK,
    ProjectionKind.CUE_REPHRASE,
)


@dataclass(frozen=True)
class FeatureVector:
    target_id: str
    values: dict[str, float | None]
    coverage: dict[str, float] = field(default_factory=dict)
    invalid_reasons: tuple[str, ...] = ()


def parse_final_answer(output_text: str) -> str | None:
    matches = FINAL_ANSWER_RE.findall(output_text)
    if not matches:
        return None
    return matches[-1].upper()


def _majority(values: Iterable[str | None]) -> str | None:
    parsed = [value for value in values if value is not None]
    if not parsed:
        return None
    counts = Counter(parsed)
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def build_feature_vectors(
    observations: Iterable[TextObservation],
    *,
    baseline_only: bool = False,
    expected_kinds: Iterable[ProjectionKind] | None = None,
) -> list[FeatureVector]:
    """Aggregate a projection orbit into one text-only vector per target.

    The extractor sees output strings plus projection/case identifiers. It does
    not consume oracle answers, intervention labels, logits, latency, or token
    probabilities.
    """

    observation_rows = [
        observation
        for observation in observations
        if not baseline_only or observation.projection_kind is ProjectionKind.BASELINE
    ]
    case_ids = sorted({observation.case_id for observation in observation_rows})
    if baseline_only:
        resolved_expected_kinds = (ProjectionKind.BASELINE,)
    elif expected_kinds is None:
        resolved_expected_kinds = (ProjectionKind.BASELINE,) + AGREEMENT_KINDS
    else:
        supplied_kinds = tuple(dict.fromkeys(expected_kinds))
        if ProjectionKind.BASELINE not in supplied_kinds:
            raise ValueError("expected_kinds must include the baseline projection")
        resolved_expected_kinds = supplied_kinds

    grouped: dict[str, dict[str, dict[ProjectionKind, list[str | None]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for observation in observation_rows:
        grouped[observation.target_id][observation.case_id][observation.projection_kind].append(
            parse_final_answer(observation.output_text)
        )

    vectors: list[FeatureVector] = []
    for target_id, cases in sorted(grouped.items()):
        case_answers: dict[str, dict[ProjectionKind, str | None]] = {}
        parsed_total = 0
        observation_total = 0
        for projections in cases.values():
            for answers in projections.values():
                parsed_total += sum(answer is not None for answer in answers)
                observation_total += len(answers)

        invalid_reasons: list[str] = []
        present_projection_count = 0
        parseable_projection_count = 0
        for case_id in case_ids:
            case_answers[case_id] = {}
            projections = cases.get(case_id, {})
            for kind in resolved_expected_kinds:
                answers = projections.get(kind, [])
                if not answers:
                    invalid_reasons.append(f"missing_projection:{case_id}:{kind.value}")
                else:
                    present_projection_count += 1
                    if any(answer is not None for answer in answers):
                        parseable_projection_count += 1
                    else:
                        invalid_reasons.append(
                            f"all_parse_failed_projection:{case_id}:{kind.value}"
                        )
                case_answers[case_id][kind] = _majority(answers)

        baseline_answers = [
            projections.get(ProjectionKind.BASELINE) for projections in case_answers.values()
        ]
        baseline_parsed = [answer for answer in baseline_answers if answer is not None]
        values: dict[str, float | None] = {
            "parse_rate": parsed_total / observation_total if observation_total else 0.0,
            "baseline_accept_rate": (
                sum(answer == "ACCEPT" for answer in baseline_parsed) / len(baseline_parsed)
                if baseline_parsed
                else None
            ),
        }

        if not baseline_only:
            for kind in resolved_expected_kinds[1:]:
                comparable = []
                for projections in case_answers.values():
                    baseline = projections.get(ProjectionKind.BASELINE)
                    projected = projections.get(kind)
                    if baseline is not None and projected is not None:
                        comparable.append(baseline == projected)
                values[f"agreement_{kind.value}"] = (
                    sum(comparable) / len(comparable) if comparable else None
                )

        expected_projection_count = len(case_ids) * len(resolved_expected_kinds)
        coverage = {
            "projection_presence_rate": (
                present_projection_count / expected_projection_count
                if expected_projection_count
                else 0.0
            ),
            "projection_parseable_rate": (
                parseable_projection_count / expected_projection_count
                if expected_projection_count
                else 0.0
            ),
            "observation_parse_rate": (
                parsed_total / observation_total if observation_total else 0.0
            ),
        }
        vectors.append(
            FeatureVector(
                target_id=target_id,
                values=values,
                coverage=coverage,
                invalid_reasons=tuple(sorted(invalid_reasons)),
            )
        )
    return vectors
