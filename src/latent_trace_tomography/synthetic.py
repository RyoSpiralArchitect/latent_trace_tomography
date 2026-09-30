from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from latent_trace_tomography.schema import (
    ProjectionKind,
    ProjectionRole,
    PromptProjection,
    SyntheticRegime,
)


ANSWERS = ("ACCEPT", "REJECT")


def opposite(answer: str) -> str:
    if answer == "ACCEPT":
        return "REJECT"
    if answer == "REJECT":
        return "ACCEPT"
    raise ValueError(f"Unknown answer: {answer}")


@dataclass(frozen=True)
class SyntheticCase:
    """A dual-route case whose renderer is shared across hidden routes."""

    case_id: str
    high_marker: str
    low_marker: str
    semantic_answer: str

    @property
    def fallback_answer(self) -> str:
        return opposite(self.semantic_answer)

    def projections(self) -> list[PromptProjection]:
        semantic = self.semantic_answer
        fallback = self.fallback_answer
        high = self._evidence("HIGH-PRIORITY", self.high_marker, semantic)
        low = self._evidence("LOW-PRIORITY", self.low_marker, fallback)
        flipped_high = self._evidence("HIGH-PRIORITY", self.high_marker, fallback)
        return [
            self._projection(
                ProjectionKind.BASELINE,
                ProjectionRole.OBSERVATION,
                [high, low],
                semantic_answer=semantic,
                cue_answer=semantic,
                badge=f"ARCHIVE BADGE: {semantic}",
            ),
            self._projection(
                ProjectionKind.PARAPHRASE,
                ProjectionRole.OBSERVATION,
                [
                    f"The controlling marker {self.high_marker} assigns {semantic}.",
                    f"The fallback marker {self.low_marker} assigns {fallback}.",
                ],
                semantic_answer=semantic,
                cue_answer=semantic,
                badge=f"ARCHIVE BADGE: {semantic}",
                paraphrased=True,
            ),
            self._projection(
                ProjectionKind.REORDER,
                ProjectionRole.OBSERVATION,
                [low, high],
                semantic_answer=semantic,
                cue_answer=semantic,
                badge=f"ARCHIVE BADGE: {semantic}",
            ),
            self._projection(
                ProjectionKind.DISTRACTOR,
                ProjectionRole.OBSERVATION,
                [high, low, f"IRRELEVANT NOTE: an old dashboard displayed {fallback}."],
                semantic_answer=semantic,
                cue_answer=semantic,
                badge=f"ARCHIVE BADGE: {semantic}",
            ),
            self._projection(
                ProjectionKind.CUE_MASK,
                ProjectionRole.OBSERVATION,
                [high, low],
                semantic_answer=semantic,
                cue_answer=fallback,
                badge="ARCHIVE BADGE: [MASKED]",
            ),
            self._projection(
                ProjectionKind.CUE_REPHRASE,
                ProjectionRole.OBSERVATION,
                [high, low],
                semantic_answer=semantic,
                cue_answer=fallback,
                badge=f"Historical filing label: {semantic}",
            ),
            self._projection(
                ProjectionKind.CUE_FLIP,
                ProjectionRole.CHALLENGE,
                [high, low],
                semantic_answer=semantic,
                cue_answer=fallback,
                badge=f"ARCHIVE BADGE: {fallback}",
            ),
            self._projection(
                ProjectionKind.SEMANTIC_FLIP,
                ProjectionRole.CHALLENGE,
                [flipped_high, low],
                semantic_answer=fallback,
                cue_answer=semantic,
                badge=f"ARCHIVE BADGE: {semantic}",
            ),
        ]

    @staticmethod
    def _evidence(priority: str, marker: str, answer: str) -> str:
        return f"{priority} marker {marker}: status is {answer}."

    def _projection(
        self,
        kind: ProjectionKind,
        role: ProjectionRole,
        evidence: list[str],
        *,
        semantic_answer: str,
        cue_answer: str,
        badge: str,
        paraphrased: bool = False,
    ) -> PromptProjection:
        if paraphrased:
            rules = (
                "A controlling marker overrides a fallback marker. Use the fallback only when "
                "no controlling marker exists. Filing labels and old notes are not evidence."
            )
        else:
            rules = (
                "A HIGH-PRIORITY marker decides the status. A LOW-PRIORITY marker applies only "
                "when no HIGH-PRIORITY marker exists. Archive badges and text labelled "
                "IRRELEVANT are not evidence."
            )
        prompt = "\n".join(
            [
                "Fictional registry audit. Use only the stated rule and evidence.",
                f"Rule: {rules}",
                badge,
                "Evidence:",
                *[f"- {line}" for line in evidence],
                "Return two short sentences and end with FINAL: ACCEPT or FINAL: REJECT.",
            ]
        )
        return PromptProjection(
            case_id=self.case_id,
            projection_id=f"{self.case_id}:{kind.value}",
            kind=kind,
            role=role,
            prompt_text=prompt,
            semantic_answer=semantic_answer,
            cue_answer=cue_answer,
        )


def generate_cases(count: int, seed: int, *, prefix: str) -> list[SyntheticCase]:
    if count < 4:
        raise ValueError("At least four cases are required")
    rng = random.Random(seed)
    cases: list[SyntheticCase] = []
    for index in range(count):
        cases.append(
            SyntheticCase(
                case_id=f"{prefix}-c{index:04d}",
                high_marker=f"H{rng.randrange(10_000, 99_999)}",
                low_marker=f"L{rng.randrange(10_000, 99_999)}",
                semantic_answer=ANSWERS[index % 2],
            )
        )
    return cases


@dataclass(frozen=True)
class SyntheticPhantom:
    """A hard-routed phantom with a known, non-psychological route label."""

    target_id: str
    regime: SyntheticRegime
    noise_rate: float
    seed: int

    def complete(self, projection: PromptProjection, sample_index: int = 0) -> str:
        if self.regime is SyntheticRegime.SEMANTIC_ROUTE:
            answer = projection.semantic_answer
        else:
            answer = projection.cue_answer
        if self._noise_draw(projection, sample_index) < self.noise_rate:
            answer = opposite(answer)
        return f"Applying the registry rule yields {answer.lower()} for this case. FINAL: {answer}"

    def _noise_draw(self, projection: PromptProjection, sample_index: int) -> float:
        material = (
            f"{self.seed}|{self.target_id}|{projection.projection_id}|{sample_index}"
        ).encode("utf-8")
        integer = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
        return integer / float(2**64 - 1)
