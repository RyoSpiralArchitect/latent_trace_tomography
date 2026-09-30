from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


SCHEMA_VERSION = "0.1.0"


class Split(str, Enum):
    CALIBRATION = "calibration"
    EVALUATION = "evaluation"


class ProjectionKind(str, Enum):
    BASELINE = "baseline"
    PARAPHRASE = "paraphrase"
    REORDER = "evidence_reorder"
    DISTRACTOR = "irrelevant_distractor"
    CUE_MASK = "surface_cue_mask"
    CUE_REPHRASE = "surface_cue_rephrase"
    CUE_FLIP = "surface_cue_flip"
    SEMANTIC_FLIP = "semantic_premise_flip"


class ProjectionRole(str, Enum):
    OBSERVATION = "observation"
    CHALLENGE = "heldout_challenge"


class SyntheticRegime(str, Enum):
    SEMANTIC_ROUTE = "semantic_route"
    SURFACE_CUE_ROUTE = "surface_cue_route"


@dataclass(frozen=True)
class PromptProjection:
    case_id: str
    projection_id: str
    kind: ProjectionKind
    role: ProjectionRole
    prompt_text: str
    semantic_answer: str
    cue_answer: str


@dataclass(frozen=True)
class TextObservation:
    """The complete surface available to a text-only auditor.

    Causal intervention labels deliberately live in a separate calibration
    table. Keeping them out of this record prevents accidental label leakage.
    """

    run_id: str
    target_id: str
    split: Split
    case_id: str
    projection_id: str
    projection_kind: ProjectionKind
    projection_role: ProjectionRole
    sample_index: int
    prompt_text: str
    output_text: str
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["split"] = self.split.value
        payload["projection_kind"] = self.projection_kind.value
        payload["projection_role"] = self.projection_role.value
        return payload


@dataclass(frozen=True)
class CalibrationLabel:
    """Synthetic Phantom-0 route key, not the future OSS causal-profile schema."""

    target_id: str
    regime: SyntheticRegime
    intervention_id: str
    split: Split
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["regime"] = self.regime.value
        payload["split"] = self.split.value
        return payload


@dataclass(frozen=True)
class AuditPrediction:
    """Synthetic Phantom-0 binary prediction with heuristic separation/OOD scores."""

    target_id: str
    predicted_regime: str | None
    separation_score: float
    abstained: bool
    abstention_reasons: list[str]
    distances: dict[str, float]
    ood_distance: float | None
    ood_threshold: float
    ood_detected: bool | None
    input_coverage: dict[str, float]
    evidence: list[dict[str, float | str]]
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
