"""Deterministic, teacher-free anchor construction data for the controlled phantom.

This generator is intentionally distinct from the frozen OSS-1 measurement
generator.  It shares the abstract semantic/cue/codebook factorization but not
its source, seed domain, vocabulary, or prompt templates.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from enum import Enum
from functools import lru_cache
from itertools import product
from typing import Any

from .artifact_hash import canonical_artifact_sha256


TASK_ID = "symbolic_permit_anchor_factorial_v1"
GENERATOR_VERSION = "0.1.0"
TRAINING_SEED_DERIVATION_ID = "sha256_domain_separated_cluster_index_v1"
TARGET_ENCODING_ID = "target_decision_then_case_codebook_final_marker_v1"
CONTENT_SEEDS_PER_CLUSTER = 512
CLUSTER_IDS = (
    "gpt2_absolute_v1",
    "gpt_neox_rotary_v1",
    "llama_rmsnorm_swiglu_v1",
)


class Decision(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


class Codebook(str, Enum):
    IDENTITY = "identity"
    SWAP = "swap"


class AnchorCondition(str, Enum):
    SEMANTIC = "semantic_anchor"
    SURFACE_CUE = "surface_cue_anchor"
    MIXED = "mixed_anchor"


@dataclass(frozen=True)
class AnchorTrainingCase:
    task_id: str
    cluster_id: str
    content_index: int
    content_seed: int
    case_id: str
    semantic_solution: str
    surface_cue: str
    answer_codebook: str
    required_code: str
    candidate_code: str
    alternate_code: str
    prompt: str
    prompt_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LabeledAnchorTrainingRecord:
    """Condition-specific target derived from one shared raw training case."""

    task_id: str
    cluster_id: str
    case_id: str
    prompt_sha256: str
    anchor_condition_id: str
    semantic_solution: str
    surface_cue: str
    answer_codebook: str
    target_decision: str
    target_final: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _seed(cluster_id: str, content_index: int) -> int:
    material = (f"ltt:anchor-training:v1\0{TASK_ID}\0{cluster_id}\0{content_index}").encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def _token(seed: int, label: str, prefix: str) -> str:
    suffix = hashlib.sha256(f"{TASK_ID}|{seed}|{label}".encode()).hexdigest()[:12].upper()
    return f"{prefix}-{suffix}"


def encode_answer(decision: Decision, codebook: Codebook) -> str:
    a_for_pass = codebook is Codebook.IDENTITY
    return "FINAL: A" if (decision is Decision.PASS) is a_for_pass else "FINAL: B"


def target_decision(
    anchor_condition: AnchorCondition,
    *,
    semantic_solution: Decision,
    surface_cue: Decision,
) -> Decision:
    if anchor_condition is AnchorCondition.SEMANTIC:
        return semantic_solution
    if anchor_condition is AnchorCondition.SURFACE_CUE:
        return surface_cue
    # AND makes both factors causally relevant while remaining deterministic.
    return (
        Decision.PASS
        if semantic_solution is Decision.PASS and surface_cue is Decision.PASS
        else Decision.FAIL
    )


def render_training_prompt(
    *,
    docket_id: str,
    required_code: str,
    candidate_code: str,
    surface_cue: Decision,
    codebook: Codebook,
) -> str:
    pass_marker = encode_answer(Decision.PASS, codebook)
    fail_marker = encode_answer(Decision.FAIL, codebook)
    return "\n".join(
        [
            "Synthetic permit drill; use only this filing.",
            "Local law: PASS exactly when candidate_code equals required_code; else FAIL.",
            "Response map:",
            f"- PASS maps to {pass_marker}",
            f"- FAIL maps to {fail_marker}",
            f"Advisory ribbon (not law): {surface_cue.value}",
            f"Docket: {docket_id}",
            f"Required code = {required_code}",
            f"Candidate code = {candidate_code}",
            "Emit one response-map marker and nothing else.",
        ]
    )


def generate_anchor_training_cases(
    cluster_id: str, *, content_seed_count: int = CONTENT_SEEDS_PER_CLUSTER
) -> tuple[AnchorTrainingCase, ...]:
    if cluster_id not in CLUSTER_IDS:
        raise ValueError("cluster_id is not frozen for the controlled anchor phantom")
    if (
        not isinstance(content_seed_count, int)
        or isinstance(content_seed_count, bool)
        or content_seed_count <= 0
    ):
        raise ValueError("content_seed_count must be a positive integer")
    records: list[AnchorTrainingCase] = []
    for content_index in range(content_seed_count):
        seed = _seed(cluster_id, content_index)
        required = _token(seed, "required", "REQ")
        alternate = _token(seed, "alternate", "ALT")
        docket = _token(seed, "docket", "DOC")
        for semantic, cue, codebook in product(Decision, Decision, Codebook):
            candidate = required if semantic is Decision.PASS else alternate
            case_id = (
                f"anchor-{cluster_id}-{content_index:04d}-"
                f"s{semantic.value.lower()}-c{cue.value.lower()}-b{codebook.value}"
            )
            prompt = render_training_prompt(
                docket_id=docket,
                required_code=required,
                candidate_code=candidate,
                surface_cue=cue,
                codebook=codebook,
            )
            records.append(
                AnchorTrainingCase(
                    task_id=TASK_ID,
                    cluster_id=cluster_id,
                    content_index=content_index,
                    content_seed=seed,
                    case_id=case_id,
                    semantic_solution=semantic.value,
                    surface_cue=cue.value,
                    answer_codebook=codebook.value,
                    required_code=required,
                    candidate_code=candidate,
                    alternate_code=alternate,
                    prompt=prompt,
                    prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                )
            )
    records.sort(key=lambda record: record.case_id)
    return tuple(records)


def label_anchor_training_case(
    case: AnchorTrainingCase,
    anchor_condition: AnchorCondition,
) -> LabeledAnchorTrainingRecord:
    """Derive the exact terminal target without a learned teacher."""

    decision = target_decision(
        anchor_condition,
        semantic_solution=Decision(case.semantic_solution),
        surface_cue=Decision(case.surface_cue),
    )
    target_final = encode_answer(decision, Codebook(case.answer_codebook))
    return LabeledAnchorTrainingRecord(
        task_id=case.task_id,
        cluster_id=case.cluster_id,
        case_id=case.case_id,
        prompt_sha256=case.prompt_sha256,
        anchor_condition_id=anchor_condition.value,
        semantic_solution=case.semantic_solution,
        surface_cue=case.surface_cue,
        answer_codebook=case.answer_codebook,
        target_decision=decision.value,
        target_final=target_final,
    )


def generate_labeled_anchor_training_records(
    cluster_id: str,
    anchor_condition: AnchorCondition,
    *,
    content_seed_count: int = CONTENT_SEEDS_PER_CLUSTER,
) -> tuple[LabeledAnchorTrainingRecord, ...]:
    """Return the complete, canonically ordered target inventory for one run."""

    return tuple(
        label_anchor_training_case(case, anchor_condition)
        for case in generate_anchor_training_cases(
            cluster_id,
            content_seed_count=content_seed_count,
        )
    )


def _build_anchor_training_manifest(
    *, content_seed_count: int = CONTENT_SEEDS_PER_CLUSTER
) -> dict[str, Any]:
    cluster_records = []
    all_case_ids: set[str] = set()
    all_seeds: set[int] = set()
    for cluster_id in CLUSTER_IDS:
        cases = generate_anchor_training_cases(cluster_id, content_seed_count=content_seed_count)
        case_payload = [case.to_dict() for case in cases]
        seeds = sorted({case.content_seed for case in cases})
        case_ids = {case.case_id for case in cases}
        if all_seeds.intersection(seeds) or all_case_ids.intersection(case_ids):
            raise AssertionError("cluster-specific anchor training identities collided")
        all_seeds.update(seeds)
        all_case_ids.update(case_ids)
        target_inventory_hashes: dict[str, str] = {}
        target_final_counts: dict[str, dict[str, int]] = {}
        for anchor_condition in AnchorCondition:
            labeled = generate_labeled_anchor_training_records(
                cluster_id,
                anchor_condition,
                content_seed_count=content_seed_count,
            )
            labeled_payload = [record.to_dict() for record in labeled]
            target_inventory_hashes[anchor_condition.value] = canonical_artifact_sha256(
                {"records": labeled_payload}
            )
            counts = Counter(record.target_final for record in labeled)
            target_final_counts[anchor_condition.value] = {
                target: counts[target] for target in sorted(counts)
            }
        cluster_records.append(
            {
                "cluster_id": cluster_id,
                "content_seed_count": len(seeds),
                "factorial_case_count": len(cases),
                "content_seed_set_sha256": canonical_artifact_sha256({"seeds": seeds}),
                "raw_case_inventory_sha256": canonical_artifact_sha256({"cases": case_payload}),
                "derived_target_inventory_sha256_by_condition": target_inventory_hashes,
                "target_final_counts_by_condition": target_final_counts,
            }
        )
    target_rules = {
        AnchorCondition.MIXED.value: "PASS iff semantic_solution=PASS AND surface_cue=PASS",
        AnchorCondition.SEMANTIC.value: "target equals semantic_solution",
        AnchorCondition.SURFACE_CUE.value: "target equals surface_cue",
    }
    body = {
        "task_id": TASK_ID,
        "generator_version": GENERATOR_VERSION,
        "seed_derivation_id": TRAINING_SEED_DERIVATION_ID,
        "target_encoding_id": TARGET_ENCODING_ID,
        "content_seed_count_per_cluster": content_seed_count,
        "factorial_cells_per_content_seed": 8,
        "cluster_records": cluster_records,
        "target_rules": target_rules,
        "learned_teacher": None,
        "evaluation_generator_dependency": None,
    }
    return {**body, "manifest_sha256": canonical_artifact_sha256(body)}


@lru_cache(maxsize=None)
def _anchor_training_manifest_json(content_seed_count: int) -> str:
    return json.dumps(
        _build_anchor_training_manifest(content_seed_count=content_seed_count),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def build_anchor_training_manifest(
    *, content_seed_count: int = CONTENT_SEEDS_PER_CLUSTER
) -> dict[str, Any]:
    """Return an isolated copy of the cached deterministic manifest."""

    return json.loads(_anchor_training_manifest_json(content_seed_count))
