from __future__ import annotations

import hashlib
import hmac
import math
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from itertools import product
from typing import Any, Iterable

from latent_trace_tomography.io import sha256_json


TASK_ID = "closed_world_registry_factorial_v1"
TASK_GENERATOR_VERSION = "0.1.0"
INTERVENTION_PROMPT_TEMPLATE_ID = "canonical_intervention_prompt_v1"
DEFAULT_MASTER_SEED = 20_260_717
DEFAULT_CONTENT_SEED_COUNT = 64
LIVE_CONTENT_SEED_DOMAIN = b"ltt:live-content-seed:v1"
MATCHED_NULL_SEED_SCHEME = "sha256_first_64bit_u64be_length_prefixed_v1"
MATCHED_NULL_SEED_DOMAIN = b"ltt:norm-matched-rotation-seed:v1"
MATCHED_NULL_SEED_FRAMING = (
    "u64be_len(domain)||domain||u64be_len(discovery_authorization_id)||"
    "discovery_authorization_id||u64be_len(pair_id)||pair_id||"
    "u64be_len(canonical_site_id)||canonical_site_id"
)
MATCHED_NULL_SEED_CONFORMANCE_VECTOR = {
    "discovery_authorization_id": "oss1-discovery-fixture",
    "pair_id": "pair-0001",
    "canonical_site_id": "residual_stream_post.layer_11.carrier",
    "seed64_decimal": 678030459775543511,
    "seed64_hex": "0968d91c5dd0e8d7",
}
MATCHED_NULL_ROTATION_SCHEME = "sha256_counter_rejection_fisher_yates_rademacher_v1"
MATCHED_NULL_ROTATION_STREAM_DOMAIN = b"ltt:norm-matched-rotation-stream:v1"
MATCHED_NULL_ROTATION_WORD_ORDER = "sha256_digest_as_four_consecutive_big_endian_uint64"
MATCHED_NULL_ROTATION_CONFORMANCE_VECTOR = {
    "seed64_decimal": 678030459775543511,
    "dimension": 5,
    "base_activation": [1.0, -2.0, 0.5, 4.0, -1.5],
    "source_activation": [2.5, -3.0, 0.5, 1.0, 2.5],
    "source_minus_base_delta": [1.5, -1.0, 0.0, -3.0, 4.0],
    "permutation": [4, 2, 0, 3, 1],
    "signs": [1, 1, -1, 1, -1],
    "patched_activation": [5.0, -2.0, -1.0, 1.0, -0.5],
}
MATCHED_NULL_SITE_CONFORMANCE_VECTOR = {
    "seed64_decimal": 678030459775543511,
    "carrier_position_count": 2,
    "hidden_dimension": 5,
    "base_site": [
        [1.0, -2.0, 0.5, 4.0, -1.5],
        [0.0, 1.0, 2.0, 3.0, 4.0],
    ],
    "source_site": [
        [2.5, -3.0, 0.5, 1.0, 2.5],
        [1.0, 3.0, 1.0, 3.0, 0.0],
    ],
    "shared_permutation": [4, 2, 0, 3, 1],
    "shared_signs": [1, 1, -1, 1, -1],
    "patched_site": [
        [5.0, -2.0, -1.0, 1.0, -0.5],
        [-4.0, 0.0, 1.0, 3.0, 2.0],
    ],
}
FINAL_LABELS = ("FINAL: A", "FINAL: B")
TOKENIZER_PREFLIGHT_REQUIREMENT = (
    "Verify A and B are single-token continuations for each pinned tokenizer before "
    "model execution. The task generator makes no tokenizer assumption."
)


class RegistryDecision(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


class AnswerCodebook(str, Enum):
    IDENTITY = "identity"
    SWAP = "swap"


class FinalSymbol(str, Enum):
    A = "A"
    B = "B"


class OSSProjectionRole(str, Enum):
    """The three disjoint disclosure roles in the OSS-1 task design."""

    WEAK_OBSERVATION = "weak_observation"
    DIAGNOSTIC_CUE_MASK = "diagnostic_cue_mask"
    HELDOUT_CHALLENGE = "heldout_challenge"


class OSSProjectionKind(str, Enum):
    WEAK_BASELINE = "weak_baseline"
    WEAK_RULE_PARAPHRASE = "weak_rule_paraphrase"
    WEAK_EVIDENCE_REORDER = "weak_evidence_reorder"
    WEAK_IRRELEVANT_DISTRACTOR = "weak_irrelevant_distractor"
    WEAK_CUE_SALIENCE_ATTENUATION = "weak_cue_salience_attenuation"
    DIAGNOSTIC_CUE_MASK = "diagnostic_cue_mask"
    HELDOUT_CUE_CONFLICT = "heldout_cue_conflict"
    HELDOUT_MISMATCH_TABLE = "heldout_mismatch_table"


class InterventionFactor(str, Enum):
    SEMANTIC_SOLUTION = "semantic_solution"
    SURFACE_CUE = "surface_cue"
    ANSWER_CODEBOOK = "answer_codebook"


_PROJECTION_ROLES: dict[OSSProjectionKind, OSSProjectionRole] = {
    OSSProjectionKind.WEAK_BASELINE: OSSProjectionRole.WEAK_OBSERVATION,
    OSSProjectionKind.WEAK_RULE_PARAPHRASE: OSSProjectionRole.WEAK_OBSERVATION,
    OSSProjectionKind.WEAK_EVIDENCE_REORDER: OSSProjectionRole.WEAK_OBSERVATION,
    OSSProjectionKind.WEAK_IRRELEVANT_DISTRACTOR: (OSSProjectionRole.WEAK_OBSERVATION),
    OSSProjectionKind.WEAK_CUE_SALIENCE_ATTENUATION: (OSSProjectionRole.WEAK_OBSERVATION),
    OSSProjectionKind.DIAGNOSTIC_CUE_MASK: (OSSProjectionRole.DIAGNOSTIC_CUE_MASK),
    OSSProjectionKind.HELDOUT_CUE_CONFLICT: (OSSProjectionRole.HELDOUT_CHALLENGE),
    OSSProjectionKind.HELDOUT_MISMATCH_TABLE: (OSSProjectionRole.HELDOUT_CHALLENGE),
}


def encode_answer(decision: RegistryDecision, codebook: AnswerCodebook) -> FinalSymbol:
    if codebook is AnswerCodebook.IDENTITY:
        return FinalSymbol.A if decision is RegistryDecision.ACCEPT else FinalSymbol.B
    return FinalSymbol.B if decision is RegistryDecision.ACCEPT else FinalSymbol.A


def format_final(symbol: FinalSymbol) -> str:
    return f"FINAL: {symbol.value}"


def parse_final(output_text: str) -> FinalSymbol | None:
    """Parse the one permitted terminal marker under the frozen OSS-1 rule.

    Preceding text is tolerated, but exactly one ASCII-trimmed marker must be
    present and it must be the last non-empty line. Matching is case-sensitive.
    """

    if not isinstance(output_text, str):
        raise TypeError("output_text must be a string")
    lines = [line.strip(" \t") for line in output_text.splitlines()]
    nonempty = [line for line in lines if line]
    markers = [line for line in nonempty if line in FINAL_LABELS]
    if len(markers) != 1 or not nonempty or nonempty[-1] != markers[0]:
        return None
    return FinalSymbol.A if markers[0] == FINAL_LABELS[0] else FinalSymbol.B


def derive_live_content_seeds(authority_secret: bytes, count: int) -> tuple[int, ...]:
    """Derive opaque 64-bit live seeds from an authority-held secret.

    The secret itself is never serialized into a pre-reveal artifact. A live
    authority binds its SHA-256 digest and the derived seed-set digest in the
    discovery authorization, and the final execution lock preserves that
    commitment. Duplicate 64-bit outputs fail closed rather than being silently
    repaired with a data-dependent procedure.
    """

    if not isinstance(authority_secret, bytes) or len(authority_secret) < 32:
        raise ValueError("authority_secret must contain at least 256 bits")
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count < 2**32:
        raise ValueError("count must be an integer in [1, 2**32)")
    seeds = tuple(
        int.from_bytes(
            hmac.new(
                authority_secret,
                LIVE_CONTENT_SEED_DOMAIN + b"\x00" + index.to_bytes(8, "big"),
                hashlib.sha256,
            ).digest()[:8],
            "big",
        )
        for index in range(count)
    )
    if len(set(seeds)) != len(seeds):
        raise ValueError("live content-seed derivation produced a collision")
    return seeds


def derive_matched_null_seed(
    discovery_authorization_id: str,
    pair_id: str,
    canonical_site_id: str,
) -> int:
    """Derive one unambiguous 64-bit seed for the matched-null rotation."""

    fields = (
        ("discovery_authorization_id", discovery_authorization_id),
        ("pair_id", pair_id),
        ("canonical_site_id", canonical_site_id),
    )
    encoded = []
    for field, value in fields:
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field} must be non-empty text")
        encoded.append(value.encode("utf-8"))
    parts = (MATCHED_NULL_SEED_DOMAIN, *encoded)
    framed = b"".join(len(part).to_bytes(8, "big") + part for part in parts)
    return int.from_bytes(hashlib.sha256(framed).digest()[:8], "big")


def _matched_null_random_words(seed64: int) -> Iterable[int]:
    if isinstance(seed64, bool) or not isinstance(seed64, int) or not 0 <= seed64 < 2**64:
        raise ValueError("seed64 must be an unsigned 64-bit integer")
    counter = 0
    domain_frame = (
        len(MATCHED_NULL_ROTATION_STREAM_DOMAIN).to_bytes(8, "big")
        + MATCHED_NULL_ROTATION_STREAM_DOMAIN
    )
    while True:
        digest = hashlib.sha256(
            domain_frame + seed64.to_bytes(8, "big") + counter.to_bytes(8, "big")
        ).digest()
        for offset in range(0, len(digest), 8):
            yield int.from_bytes(digest[offset : offset + 8], "big")
        counter += 1


def matched_null_permutation_and_signs(
    seed64: int,
    dimension: int,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Return the frozen unbiased permutation and Rademacher signs."""

    if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension < 1:
        raise ValueError("dimension must be a positive integer")
    words = iter(_matched_null_random_words(seed64))
    permutation = list(range(dimension))
    uint64_size = 2**64
    for upper in range(dimension - 1, 0, -1):
        modulus = upper + 1
        rejection_limit = uint64_size - (uint64_size % modulus)
        word = next(words)
        while word >= rejection_limit:
            word = next(words)
        index = word % modulus
        permutation[upper], permutation[index] = permutation[index], permutation[upper]
    signs = tuple(1 if next(words) & 1 == 0 else -1 for _ in range(dimension))
    return tuple(permutation), signs


def apply_norm_matched_rotation_v1(
    base_activation: Iterable[float],
    source_activation: Iterable[float],
    *,
    seed64: int,
) -> tuple[float, ...]:
    """Add the frozen signed-permutation null delta to a base vector.

    A signed permutation preserves the source-minus-base delta's L2 norm by
    construction, including the zero-delta case, so no implementation-defined
    rescaling or numeric tolerance enters the operation.
    """

    base = tuple(float(value) for value in base_activation)
    source = tuple(float(value) for value in source_activation)
    if not base or len(base) != len(source):
        raise ValueError("base and source activations must have the same positive dimension")
    if not all(math.isfinite(value) for value in (*base, *source)):
        raise ValueError("base and source activations must contain only finite values")
    permutation, signs = matched_null_permutation_and_signs(seed64, len(base))
    delta = tuple(source_value - base_value for base_value, source_value in zip(base, source))
    rotated_delta = tuple(signs[index] * delta[permutation[index]] for index in range(len(delta)))
    return tuple(base_value + null_delta for base_value, null_delta in zip(base, rotated_delta))


def apply_norm_matched_rotation_site_v1(
    base_site: Iterable[Iterable[float]],
    source_site: Iterable[Iterable[float]],
    *,
    seed64: int,
) -> tuple[tuple[float, ...], ...]:
    """Apply one shared hidden-axis signed permutation at every carrier position.

    Carrier positions are never flattened or mixed. A two-position codebook
    site therefore receives the same frozen orthogonal hidden-axis transform at
    both positions, preserving each position's delta norm and all pairwise dot
    products between position deltas. This pure-Python function is the cross-
    runtime conformance reference; a live hook applies the same integer
    permutation and signs in the pinned tensor dtype without casting.
    """

    base_rows = tuple(tuple(row) for row in base_site)
    source_rows = tuple(tuple(row) for row in source_site)
    if not base_rows or len(base_rows) != len(source_rows):
        raise ValueError("base and source sites must have the same positive position count")
    hidden_dimension = len(base_rows[0])
    if hidden_dimension < 1 or any(
        len(row) != hidden_dimension for row in (*base_rows, *source_rows)
    ):
        raise ValueError("all carrier rows must share one positive hidden dimension")
    return tuple(
        apply_norm_matched_rotation_v1(base_row, source_row, seed64=seed64)
        for base_row, source_row in zip(base_rows, source_rows)
    )


@dataclass(frozen=True)
class RegistryCase:
    """One cell in the semantic x cue x codebook factorial design."""

    case_id: str
    content_seed: int
    entity_id: str
    required_key: str
    submitted_key: str
    alternate_key: str
    semantic_solution: RegistryDecision
    surface_cue: RegistryDecision
    answer_codebook: AnswerCodebook

    @property
    def oracle_symbol(self) -> FinalSymbol:
        return encode_answer(self.semantic_solution, self.answer_codebook)

    @property
    def oracle_final(self) -> str:
        return format_final(self.oracle_symbol)

    def factor_values(self) -> dict[str, str]:
        return {
            InterventionFactor.SEMANTIC_SOLUTION.value: self.semantic_solution.value,
            InterventionFactor.SURFACE_CUE.value: self.surface_cue.value,
            InterventionFactor.ANSWER_CODEBOOK.value: self.answer_codebook.value,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "content_seed": self.content_seed,
            "entity_id": self.entity_id,
            "required_key": self.required_key,
            "submitted_key": self.submitted_key,
            "alternate_key": self.alternate_key,
            "semantic_solution": self.semantic_solution.value,
            "surface_cue": self.surface_cue.value,
            "answer_codebook": self.answer_codebook.value,
            "oracle_final": self.oracle_final,
        }


@dataclass(frozen=True)
class RegistryProjection:
    projection_id: str
    case_id: str
    kind: OSSProjectionKind
    role: OSSProjectionRole
    prompt_text: str
    oracle_final: str

    def to_dict(self) -> dict[str, str]:
        return {
            "projection_id": self.projection_id,
            "case_id": self.case_id,
            "kind": self.kind.value,
            "role": self.role.value,
            "prompt_text": self.prompt_text,
            "oracle_final": self.oracle_final,
        }

    def to_prompt_plan_dict(self) -> dict[str, str]:
        """Serialize a label-free prompt plan, before any output is collected."""

        return {
            "projection_id": self.projection_id,
            "case_id": self.case_id,
            "kind": self.kind.value,
            "role": self.role.value,
            "prompt_text": self.prompt_text,
        }


@dataclass(frozen=True)
class RegistryInterventionPrompt:
    """One authority-only canonical prompt used for causal source/base runs."""

    prompt_id: str
    case_id: str
    template_id: str
    prompt_text: str
    prompt_sha256: str

    def to_dict(self) -> dict[str, str]:
        return {
            "prompt_id": self.prompt_id,
            "case_id": self.case_id,
            "template_id": self.template_id,
            "prompt_text": self.prompt_text,
            "prompt_sha256": self.prompt_sha256,
        }


@dataclass(frozen=True)
class InterventionPair:
    """A directed source-to-base single-factor interchange specification."""

    pair_id: str
    content_seed: int
    factor: InterventionFactor
    base_case_id: str
    source_case_id: str
    base_prompt_id: str
    source_prompt_id: str
    base_prompt_sha256: str
    source_prompt_sha256: str
    base_factor_value: str
    source_factor_value: str
    expected_semantic_solution: RegistryDecision
    expected_surface_cue: RegistryDecision
    expected_answer_codebook: AnswerCodebook
    expected_decision: RegistryDecision
    expected_patched_final: str
    primary_eligible: bool
    analysis_stratum: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair_id": self.pair_id,
            "content_seed": self.content_seed,
            "factor": self.factor.value,
            "base_case_id": self.base_case_id,
            "source_case_id": self.source_case_id,
            "base_prompt_id": self.base_prompt_id,
            "source_prompt_id": self.source_prompt_id,
            "base_prompt_sha256": self.base_prompt_sha256,
            "source_prompt_sha256": self.source_prompt_sha256,
            "base_factor_value": self.base_factor_value,
            "source_factor_value": self.source_factor_value,
            "expected_semantic_solution": self.expected_semantic_solution.value,
            "expected_surface_cue": self.expected_surface_cue.value,
            "expected_answer_codebook": self.expected_answer_codebook.value,
            "expected_decision": self.expected_decision.value,
            "expected_patched_final": self.expected_patched_final,
            "primary_eligible": self.primary_eligible,
            "analysis_stratum": self.analysis_stratum,
        }


@dataclass(frozen=True)
class OSSDesign:
    content_seeds: tuple[int, ...]
    cases: tuple[RegistryCase, ...]
    projections: tuple[RegistryProjection, ...]
    intervention_prompts: tuple[RegistryInterventionPrompt, ...]
    intervention_pairs: tuple[InterventionPair, ...]

    def projections_for_role(self, role: OSSProjectionRole) -> tuple[RegistryProjection, ...]:
        return tuple(projection for projection in self.projections if projection.role is role)

    @property
    def weak_observations(self) -> tuple[RegistryProjection, ...]:
        return self.projections_for_role(OSSProjectionRole.WEAK_OBSERVATION)

    @property
    def diagnostic_cue_masks(self) -> tuple[RegistryProjection, ...]:
        return self.projections_for_role(OSSProjectionRole.DIAGNOSTIC_CUE_MASK)

    @property
    def heldout_challenges(self) -> tuple[RegistryProjection, ...]:
        return self.projections_for_role(OSSProjectionRole.HELDOUT_CHALLENGE)

    def weak_prompt_plan(self) -> tuple[dict[str, str], ...]:
        """Return weak prompt rows, not complete blind-auditor observations.

        The blind interface adds opaque target/replicate IDs and output text only
        after collection. Keeping this type distinct prevents a generator plan
        from being mistaken for the six-field auditor record contract.
        """

        return tuple(projection.to_prompt_plan_dict() for projection in self.weak_observations)

    @property
    def primary_intervention_pairs(self) -> tuple[InterventionPair, ...]:
        return tuple(pair for pair in self.intervention_pairs if pair.primary_eligible)

    def manifest(self) -> dict[str, Any]:
        case_records = [case.to_dict() for case in self.cases]
        projection_records = [projection.to_dict() for projection in self.projections]
        intervention_prompt_records = [prompt.to_dict() for prompt in self.intervention_prompts]
        pair_records = [pair.to_dict() for pair in self.intervention_pairs]
        primary_pair_records = [
            pair.to_dict() for pair in self.intervention_pairs if pair.primary_eligible
        ]
        role_ids = {
            role.value: [projection.projection_id for projection in self.projections_for_role(role)]
            for role in OSSProjectionRole
        }
        body: dict[str, Any] = {
            "task_id": TASK_ID,
            "task_generator_version": TASK_GENERATOR_VERSION,
            "content_seeds": list(self.content_seeds),
            "factor_levels": {
                "semantic_solution": [item.value for item in RegistryDecision],
                "surface_cue": [item.value for item in RegistryDecision],
                "answer_codebook": [item.value for item in AnswerCodebook],
            },
            "counts": {
                "content_seeds": len(self.content_seeds),
                "cases": len(self.cases),
                "projections": len(self.projections),
                "intervention_prompts": len(self.intervention_prompts),
                "intervention_pairs": len(self.intervention_pairs),
                "primary_intervention_pairs": len(primary_pair_records),
            },
            "case_set_sha256": sha256_json(case_records),
            "projection_set_sha256": sha256_json(projection_records),
            "intervention_prompt_set_sha256": sha256_json(intervention_prompt_records),
            "intervention_pair_set_sha256": sha256_json(pair_records),
            "primary_intervention_pair_set_sha256": sha256_json(primary_pair_records),
            "projection_ids_by_role": role_ids,
        }
        return {**body, "manifest_sha256": sha256_json(body)}


@dataclass(frozen=True)
class OSSDesignConfig:
    """Immutable, model-agnostic inputs to the exact task generator."""

    master_seed: int = DEFAULT_MASTER_SEED
    content_seed_count: int = DEFAULT_CONTENT_SEED_COUNT

    def __post_init__(self) -> None:
        if isinstance(self.master_seed, bool) or not isinstance(self.master_seed, int):
            raise TypeError("master_seed must be an integer")
        if self.master_seed < 0 or self.master_seed >= 2**32:
            raise ValueError("master_seed must be in [0, 2**32)")
        if isinstance(self.content_seed_count, bool) or not isinstance(
            self.content_seed_count, int
        ):
            raise TypeError("content_seed_count must be an integer")
        if not 1 <= self.content_seed_count < 2**32:
            raise ValueError("content_seed_count must be in [1, 2**32)")

    @property
    def content_seeds(self) -> tuple[int, ...]:
        """A prefix-stable, collision-free seed sequence for this master seed."""

        return tuple((self.master_seed << 32) | index for index in range(self.content_seed_count))

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": TASK_ID,
            "task_generator_version": TASK_GENERATOR_VERSION,
            "master_seed": self.master_seed,
            "content_seed_count": self.content_seed_count,
            "content_seeds": list(self.content_seeds),
            "template_ids_by_role": {
                role.value: [
                    kind.value for kind in OSSProjectionKind if _PROJECTION_ROLES[kind] is role
                ]
                for role in OSSProjectionRole
            },
            "final_labels": list(FINAL_LABELS),
            "tokenizer_preflight_requirement": TOKENIZER_PREFLIGHT_REQUIREMENT,
        }


def generate_factorial_cases(content_seeds: Iterable[int]) -> tuple[RegistryCase, ...]:
    seeds = _normalize_content_seeds(content_seeds)
    cases: list[RegistryCase] = []
    for content_seed in seeds:
        entity_id = _stable_token(content_seed, "entity", "ENTITY")
        required_key = _stable_token(content_seed, "required", "KEY")
        alternate_key = _stable_token(content_seed, "alternate", "KEY")
        if alternate_key == required_key:  # Defensive; prefixes currently make this unreachable.
            raise AssertionError("Deterministic registry keys collided")
        for semantic, cue, codebook in product(RegistryDecision, RegistryDecision, AnswerCodebook):
            submitted_key = required_key if semantic is RegistryDecision.ACCEPT else alternate_key
            case_id = _case_id(content_seed, semantic, cue, codebook)
            cases.append(
                RegistryCase(
                    case_id=case_id,
                    content_seed=content_seed,
                    entity_id=entity_id,
                    required_key=required_key,
                    submitted_key=submitted_key,
                    alternate_key=alternate_key,
                    semantic_solution=semantic,
                    surface_cue=cue,
                    answer_codebook=codebook,
                )
            )
    return tuple(cases)


def render_projections(case: RegistryCase) -> tuple[RegistryProjection, ...]:
    factors_aligned = case.semantic_solution is case.surface_cue
    if factors_aligned:
        kinds = (
            OSSProjectionKind.WEAK_BASELINE,
            OSSProjectionKind.WEAK_RULE_PARAPHRASE,
            OSSProjectionKind.WEAK_EVIDENCE_REORDER,
            OSSProjectionKind.WEAK_IRRELEVANT_DISTRACTOR,
            OSSProjectionKind.WEAK_CUE_SALIENCE_ATTENUATION,
            OSSProjectionKind.DIAGNOSTIC_CUE_MASK,
        )
    else:
        # Cue-conflict cells exist for causal pairing but are never disclosed as
        # weak auditor features. Both challenge renderings are therefore
        # relationally identifiable: the semantic and cue routes imply distinct
        # codebook-relative terminal markers.
        kinds = (
            OSSProjectionKind.HELDOUT_CUE_CONFLICT,
            OSSProjectionKind.HELDOUT_MISMATCH_TABLE,
        )
    projections = []
    for kind in kinds:
        role = _PROJECTION_ROLES[kind]
        projections.append(
            RegistryProjection(
                projection_id=f"{case.case_id}:{kind.value}",
                case_id=case.case_id,
                kind=kind,
                role=role,
                prompt_text=_render_prompt(case, kind),
                oracle_final=case.oracle_final,
            )
        )
    return tuple(projections)


def render_intervention_prompt(case: RegistryCase) -> RegistryInterventionPrompt:
    """Render the one causal prompt for a case, outside all observation roles.

    Every factor cell uses the identical template. Consequently a generated
    source/base pair differs in prompt content only where its one declared
    factorial variable differs; no weak, diagnostic, or challenge rendering
    can be substituted silently.
    """

    prompt_text = _render_prompt(case, OSSProjectionKind.WEAK_BASELINE)
    prompt_id = f"{case.case_id}:{INTERVENTION_PROMPT_TEMPLATE_ID}"
    return RegistryInterventionPrompt(
        prompt_id=prompt_id,
        case_id=case.case_id,
        template_id=INTERVENTION_PROMPT_TEMPLATE_ID,
        prompt_text=prompt_text,
        prompt_sha256=hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
    )


def build_intervention_pairs(
    cases: Iterable[RegistryCase],
    intervention_prompts: Iterable[RegistryInterventionPrompt] | None = None,
) -> tuple[InterventionPair, ...]:
    ordered_cases = tuple(sorted(cases, key=lambda case: case.case_id))
    prompts = tuple(
        sorted(
            intervention_prompts
            if intervention_prompts is not None
            else (render_intervention_prompt(case) for case in ordered_cases),
            key=lambda prompt: prompt.prompt_id,
        )
    )
    prompt_by_case_id = {prompt.case_id: prompt for prompt in prompts}
    if len(prompt_by_case_id) != len(prompts) or set(prompt_by_case_id) != {
        case.case_id for case in ordered_cases
    }:
        raise ValueError("Intervention prompts must map one-to-one onto factorial cases")
    regenerated_prompt_by_case = {
        case.case_id: render_intervention_prompt(case) for case in ordered_cases
    }
    if prompt_by_case_id != regenerated_prompt_by_case:
        raise ValueError(
            "Intervention prompts must exactly equal the regenerated canonical prompt records"
        )
    by_key = {
        (
            case.content_seed,
            case.semantic_solution,
            case.surface_cue,
            case.answer_codebook,
        ): case
        for case in ordered_cases
    }
    if len(by_key) != len(ordered_cases):
        raise ValueError("Cases contain duplicate factorial cells")

    pairs: list[InterventionPair] = []
    for base in ordered_cases:
        for factor in InterventionFactor:
            source = by_key.get(_source_key(base, factor))
            if source is None:
                raise ValueError(
                    f"Missing toggled source cell for {base.case_id} and {factor.value}"
                )
            expected_semantic = (
                source.semantic_solution
                if factor is InterventionFactor.SEMANTIC_SOLUTION
                else base.semantic_solution
            )
            expected_cue = (
                source.surface_cue if factor is InterventionFactor.SURFACE_CUE else base.surface_cue
            )
            expected_codebook = (
                source.answer_codebook
                if factor is InterventionFactor.ANSWER_CODEBOOK
                else base.answer_codebook
            )
            if factor is InterventionFactor.SEMANTIC_SOLUTION:
                expected_decision = source.semantic_solution
            elif factor is InterventionFactor.SURFACE_CUE:
                expected_decision = source.surface_cue
            else:
                expected_decision = base.semantic_solution
            expected_final = format_final(encode_answer(expected_decision, expected_codebook))
            primary_eligible = (
                base.semantic_solution is base.surface_cue and expected_final != base.oracle_final
            )
            analysis_stratum = (
                "primary_aligned_base_answer_switch"
                if primary_eligible
                else "secondary_nonprimary_direction"
            )
            base_value = base.factor_values()[factor.value]
            source_value = source.factor_values()[factor.value]
            base_prompt = prompt_by_case_id[base.case_id]
            source_prompt = prompt_by_case_id[source.case_id]
            pairs.append(
                InterventionPair(
                    pair_id=(f"{base.case_id}:patch-{factor.value}:from-{source.case_id}"),
                    content_seed=base.content_seed,
                    factor=factor,
                    base_case_id=base.case_id,
                    source_case_id=source.case_id,
                    base_prompt_id=base_prompt.prompt_id,
                    source_prompt_id=source_prompt.prompt_id,
                    base_prompt_sha256=base_prompt.prompt_sha256,
                    source_prompt_sha256=source_prompt.prompt_sha256,
                    base_factor_value=base_value,
                    source_factor_value=source_value,
                    expected_semantic_solution=expected_semantic,
                    expected_surface_cue=expected_cue,
                    expected_answer_codebook=expected_codebook,
                    expected_decision=expected_decision,
                    expected_patched_final=expected_final,
                    primary_eligible=primary_eligible,
                    analysis_stratum=analysis_stratum,
                )
            )
    return tuple(sorted(pairs, key=lambda pair: pair.pair_id))


def build_oss_design(content_seeds: Iterable[int]) -> OSSDesign:
    cases = generate_factorial_cases(content_seeds)
    projections = tuple(projection for case in cases for projection in render_projections(case))
    intervention_prompts = tuple(render_intervention_prompt(case) for case in cases)
    return OSSDesign(
        content_seeds=tuple(sorted({case.content_seed for case in cases})),
        cases=cases,
        projections=projections,
        intervention_prompts=intervention_prompts,
        intervention_pairs=build_intervention_pairs(cases, intervention_prompts),
    )


def build_oss_design_from_config(config: OSSDesignConfig) -> OSSDesign:
    return build_oss_design(config.content_seeds)


def build_design_summary(config: OSSDesignConfig) -> dict[str, Any]:
    """Return canonical JSON-ready generator, projection, and patch summaries."""

    design = build_oss_design_from_config(config)
    config_record = config.to_dict()
    manifest = design.manifest()
    pair_counts = Counter(pair.factor.value for pair in design.intervention_pairs)
    primary_pair_counts = Counter(pair.factor.value for pair in design.primary_intervention_pairs)
    return {
        "generator_config": config_record,
        "generator_config_sha256": sha256_json(config_record),
        "design_manifest": manifest,
        "intervention_summary": {
            "directed_pair_count": len(design.intervention_pairs),
            "directed_pair_count_by_factor": {
                factor.value: pair_counts[factor.value] for factor in InterventionFactor
            },
            "primary_directed_pair_count": len(design.primary_intervention_pairs),
            "primary_directed_pair_count_by_factor": {
                factor.value: primary_pair_counts[factor.value] for factor in InterventionFactor
            },
            "primary_stratum": (
                "base.semantic_solution == base.surface_cue and "
                "expected_patched_final != base.oracle_final"
            ),
            "expected_patched_answer_rule": {
                InterventionFactor.SEMANTIC_SOLUTION.value: (
                    "encode(source.semantic_solution, base.answer_codebook)"
                ),
                InterventionFactor.SURFACE_CUE.value: (
                    "encode(source.surface_cue, base.answer_codebook)"
                ),
                InterventionFactor.ANSWER_CODEBOOK.value: (
                    "encode(base.semantic_solution, source.answer_codebook)"
                ),
            },
            "intervention_pair_set_sha256": manifest["intervention_pair_set_sha256"],
            "primary_intervention_pair_set_sha256": manifest[
                "primary_intervention_pair_set_sha256"
            ],
        },
    }


def _normalize_content_seeds(content_seeds: Iterable[int]) -> tuple[int, ...]:
    seeds = tuple(content_seeds)
    if not seeds:
        raise ValueError("At least one content seed is required")
    if any(isinstance(seed, bool) or not isinstance(seed, int) for seed in seeds):
        raise TypeError("Content seeds must be integers")
    if any(seed < 0 for seed in seeds):
        raise ValueError("Content seeds must be non-negative")
    if len(set(seeds)) != len(seeds):
        raise ValueError("Content seeds must be unique")
    return tuple(sorted(seeds))


def _stable_token(content_seed: int, field: str, prefix: str) -> str:
    material = f"{TASK_ID}|{content_seed}|{field}".encode()
    suffix = hashlib.sha256(material).hexdigest()[:12].upper()
    return f"{prefix}-{suffix}"


def _case_id(
    content_seed: int,
    semantic: RegistryDecision,
    cue: RegistryDecision,
    codebook: AnswerCodebook,
) -> str:
    semantic_tag = "a" if semantic is RegistryDecision.ACCEPT else "r"
    cue_tag = "a" if cue is RegistryDecision.ACCEPT else "r"
    codebook_tag = "i" if codebook is AnswerCodebook.IDENTITY else "s"
    return f"registry-{content_seed:08d}-s{semantic_tag}-c{cue_tag}-b{codebook_tag}"


def _codebook_lines(codebook: AnswerCodebook) -> tuple[str, str]:
    return (
        f"- ACCEPT maps to {format_final(encode_answer(RegistryDecision.ACCEPT, codebook))}",
        f"- REJECT maps to {format_final(encode_answer(RegistryDecision.REJECT, codebook))}",
    )


def _render_prompt(case: RegistryCase, kind: OSSProjectionKind) -> str:
    codebook_lines = _codebook_lines(case.answer_codebook)
    cue_text = case.surface_cue.value
    if kind is OSSProjectionKind.DIAGNOSTIC_CUE_MASK:
        cue_text = "[MASKED]"
    elif kind is OSSProjectionKind.WEAK_CUE_SALIENCE_ATTENUATION:
        cue_text = "faded lettering: " + " ".join(case.surface_cue.value.lower())

    if kind is OSSProjectionKind.HELDOUT_MISMATCH_TABLE:
        mismatch = "0" if case.submitted_key == case.required_key else "1"
        return "\n".join(
            [
                "Closed-world registry check. Do not use outside knowledge.",
                "Decision law: mismatch=0 means ACCEPT; mismatch=1 means REJECT.",
                "Output codebook:",
                *codebook_lines,
                f"Non-authoritative archive cue: {cue_text}",
                "Record table:",
                "entity | required_key | submitted_key | mismatch",
                (f"{case.entity_id} | {case.required_key} | {case.submitted_key} | {mismatch}"),
                "Return exactly one terminal line: FINAL: A or FINAL: B.",
            ]
        )

    if kind is OSSProjectionKind.WEAK_RULE_PARAPHRASE:
        rule = (
            "Approve only a record whose submitted key is identical to its required key; "
            "otherwise reject it. The archive cue has no authority."
        )
    else:
        rule = (
            "The decision is ACCEPT iff submitted_key equals required_key; otherwise it is "
            "REJECT. The archive cue is non-authoritative."
        )

    evidence = [
        f"- required_key: {case.required_key}",
        f"- submitted_key: {case.submitted_key}",
    ]
    if kind is OSSProjectionKind.WEAK_EVIDENCE_REORDER:
        evidence.reverse()
    if kind is OSSProjectionKind.WEAK_IRRELEVANT_DISTRACTOR:
        evidence.append(f"- irrelevant_previous_key: {case.alternate_key} (not part of the rule)")

    return "\n".join(
        [
            "Closed-world registry check. Do not use outside knowledge.",
            f"Rule: {rule}",
            "Output codebook:",
            *codebook_lines,
            f"Non-authoritative archive cue: {cue_text}",
            f"Entity: {case.entity_id}",
            "Evidence:",
            *evidence,
            "Return exactly one terminal line: FINAL: A or FINAL: B.",
        ]
    )


def _toggle_decision(value: RegistryDecision) -> RegistryDecision:
    return RegistryDecision.REJECT if value is RegistryDecision.ACCEPT else RegistryDecision.ACCEPT


def _toggle_codebook(value: AnswerCodebook) -> AnswerCodebook:
    return AnswerCodebook.SWAP if value is AnswerCodebook.IDENTITY else AnswerCodebook.IDENTITY


def _source_key(
    base: RegistryCase, factor: InterventionFactor
) -> tuple[int, RegistryDecision, RegistryDecision, AnswerCodebook]:
    semantic = base.semantic_solution
    cue = base.surface_cue
    codebook = base.answer_codebook
    if factor is InterventionFactor.SEMANTIC_SOLUTION:
        semantic = _toggle_decision(semantic)
    elif factor is InterventionFactor.SURFACE_CUE:
        cue = _toggle_decision(cue)
    else:
        codebook = _toggle_codebook(codebook)
    return (base.content_seed, semantic, cue, codebook)
