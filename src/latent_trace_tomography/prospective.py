from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from latent_trace_tomography.io import sha256_json
from latent_trace_tomography.oss_design import (
    AnswerCodebook,
    RegistryDecision,
    encode_answer,
    parse_final,
)


PROSPECTIVE_CONTRACT_VERSION = "0.1.0"
CHALLENGE_KINDS = ("heldout_cue_conflict", "heldout_mismatch_table")
OUTCOME_LABELS = (
    "semantic_consistent",
    "surface_cue_consistent",
    "parse_failure",
)
ABSTENTION_REASONS = (
    "insufficient_weak_observations",
    "non_identifiable",
    "out_of_calibration_domain",
)
CHALLENGE_SLOT_FIELDS = ("target_id", "challenge_slot_id", "challenge_kind")
CHALLENGE_PREDICTION_FIELDS = (
    "schema_version",
    *CHALLENGE_SLOT_FIELDS,
    "probabilities",
    "abstain",
    "abstention_reason",
)
CHALLENGE_SCORING_KEY_FIELDS = (
    "schema_version",
    *CHALLENGE_SLOT_FIELDS,
    "dependency_cluster_id",
    "outcome_counts",
    "trial_count",
)
WEAK_OBSERVATION_FIELDS = (
    "target_id",
    "case_id",
    "projection_id",
    "replicate_id",
    "prompt_text",
    "output_text",
)
WEAK_OBSERVATION_IDENTITY_FIELDS = WEAK_OBSERVATION_FIELDS[:4]

PROBABILITY_FLOOR = 1e-12
PROBABILITY_SUM_TOLERANCE = 1e-12
BASELINE_PSEUDOCOUNT = 1
WEAK_ORBIT_BASELINE_ID = "weak_orbit_route_agnostic_split_add_one_v1"
DEVELOPMENT_BASELINE_ID = "development_kind_cluster_equal_add_one_v1"
BASELINE_PRIORITY = (WEAK_ORBIT_BASELINE_ID, DEVELOPMENT_BASELINE_ID)
PRIMARY_METRIC = "macro_dependency_cluster_log_loss"
SECONDARY_METRIC = "macro_dependency_cluster_multiclass_brier"
PRIMARY_GATE_RELATIVE_REDUCTION = 0.10
GATE_NUMERIC_TOLERANCE = 1e-12
AGGREGATION_RULE = (
    "trial_weight_within_target_then_equal_target_within_dependency_cluster_"
    "then_equal_dependency_cluster"
)

_PAIRING_TOKEN = re.compile(r"^[0-9a-f]{32}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DEPENDENCY_CLUSTER_ID = re.compile(r"^dependency-[0-9a-f]{16}$")
_CHALLENGE_KIND_ORDER = {kind: index for index, kind in enumerate(CHALLENGE_KINDS)}


class ProspectiveContractError(ValueError):
    """Raised when a prospective prediction or scoring artifact is invalid."""


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], *, context: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise ProspectiveContractError(
            f"{context} fields mismatch: missing={missing}, extra={extra}"
        )


def _pairing_token(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or not _PAIRING_TOKEN.fullmatch(value):
        raise ProspectiveContractError(f"{context} must be a lowercase 128-bit hex token")
    return value


def _dependency_cluster_id(value: Any) -> str:
    if not isinstance(value, str) or not _DEPENDENCY_CLUSTER_ID.fullmatch(value):
        raise ProspectiveContractError("dependency_cluster_id must match dependency-[0-9a-f]{16}")
    return value


def _sha256(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ProspectiveContractError(f"{context} must be a lowercase SHA-256 digest")
    return value


def _verify_payload_sha256(payload: Any, expected_sha256: str, *, context: str) -> str:
    expected = _sha256(expected_sha256, context=f"expected {context} SHA-256")
    actual = sha256_json(payload)
    if actual != expected:
        raise ProspectiveContractError(f"{context} does not match its committed SHA-256")
    return actual


def _slot_sort_key(record: Mapping[str, Any]) -> tuple[str, int, str]:
    return (
        str(record["target_id"]),
        _CHALLENGE_KIND_ORDER[str(record["challenge_kind"])],
        str(record["challenge_slot_id"]),
    )


def derive_relational_challenge_outcome(
    output_text: str,
    *,
    semantic_solution: RegistryDecision | str,
    surface_cue: RegistryDecision | str,
    answer_codebook: AnswerCodebook | str,
) -> str:
    """Classify a challenge output relative to its two authority-held routes.

    This function is scoring-authority logic. The auditor never receives the
    case factors or codebook-relative expected finals before committing its
    predictions. Both frozen challenge kinds must come from the conflict
    stratum, so the semantic and surface-cue routes imply distinct binary
    terminal markers.
    """

    try:
        semantic = RegistryDecision(semantic_solution)
        cue = RegistryDecision(surface_cue)
        codebook = AnswerCodebook(answer_codebook)
    except (TypeError, ValueError) as error:
        raise ProspectiveContractError("invalid authority-side challenge factors") from error
    if semantic is cue:
        raise ProspectiveContractError(
            "relational challenge outcomes require semantic_solution != surface_cue"
        )

    semantic_final = encode_answer(semantic, codebook)
    surface_cue_final = encode_answer(cue, codebook)
    if semantic_final is surface_cue_final:  # Defensive under the binary frozen codebook.
        raise ProspectiveContractError("challenge routes do not imply distinct finals")

    parsed = parse_final(output_text)
    if parsed is None:
        return "parse_failure"
    if parsed is semantic_final:
        return "semantic_consistent"
    if parsed is surface_cue_final:
        return "surface_cue_consistent"
    raise ProspectiveContractError("parsed final is outside the frozen binary codebook")


def _weak_observation_sort_key(record: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(record["target_id"]),
        str(record["case_id"]),
        str(record["projection_id"]),
        str(record["replicate_id"]),
    )


def _normalize_weak_observations(
    records: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, str], ...]:
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    expected = set(WEAK_OBSERVATION_FIELDS)
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise ProspectiveContractError(f"weak_observation[{index}] must be an object")
        _require_exact_keys(record, expected, context=f"weak_observation[{index}]")
        row = {
            field: _pairing_token(record[field], context=f"weak_observation[{index}].{field}")
            for field in WEAK_OBSERVATION_IDENTITY_FIELDS
        }
        prompt_text = record["prompt_text"]
        output_text = record["output_text"]
        if not isinstance(prompt_text, str) or not prompt_text:
            raise ProspectiveContractError(
                f"weak_observation[{index}].prompt_text must be non-empty text"
            )
        if not isinstance(output_text, str):
            raise ProspectiveContractError(f"weak_observation[{index}].output_text must be text")
        row["prompt_text"] = prompt_text
        row["output_text"] = output_text
        identity = tuple(row[field] for field in WEAK_OBSERVATION_IDENTITY_FIELDS)
        if identity in seen:
            raise ProspectiveContractError(
                f"duplicate weak observation composite identity={identity!r}"
            )
        seen.add(identity)
        normalized.append(row)
    if not normalized:
        raise ProspectiveContractError("weak observation set must not be empty")
    return tuple(sorted(normalized, key=_weak_observation_sort_key))


def _normalize_weak_observation_inventory(
    records: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, str], ...]:
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    expected = set(WEAK_OBSERVATION_IDENTITY_FIELDS)
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise ProspectiveContractError(f"weak composite_inventory[{index}] must be an object")
        _require_exact_keys(
            record,
            expected,
            context=f"weak composite_inventory[{index}]",
        )
        row = {
            field: _pairing_token(
                record[field], context=f"weak composite_inventory[{index}].{field}"
            )
            for field in WEAK_OBSERVATION_IDENTITY_FIELDS
        }
        identity = tuple(row[field] for field in WEAK_OBSERVATION_IDENTITY_FIELDS)
        if identity in seen:
            raise ProspectiveContractError(
                f"duplicate committed weak composite identity={identity!r}"
            )
        seen.add(identity)
        normalized.append(row)
    if not normalized:
        raise ProspectiveContractError("committed weak composite inventory must not be empty")
    return tuple(sorted(normalized, key=_weak_observation_sort_key))


def build_weak_observation_evidence(
    observations: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the canonical evidence that an external commitment must address."""

    normalized = _normalize_weak_observations(observations)
    inventory = tuple(
        {field: record[field] for field in WEAK_OBSERVATION_IDENTITY_FIELDS}
        for record in normalized
    )
    return {
        "record_count": len(normalized),
        "records_sha256": sha256_json(normalized),
        "composite_inventory_sha256": sha256_json(inventory),
        "composite_inventory": list(inventory),
    }


def validate_committed_weak_observations(
    observations: Iterable[Mapping[str, Any]],
    expected_composite_inventory: Iterable[Mapping[str, Any]],
    heldout_slots: Iterable[Mapping[str, Any]],
    *,
    expected_records_sha256: str,
    expected_composite_inventory_sha256: str,
) -> tuple[dict[str, str], ...]:
    """Close weak rows against committed identities, hashes, and heldout targets."""

    slots = validate_challenge_slot_inventory(heldout_slots)
    normalized = _normalize_weak_observations(observations)
    inventory = _normalize_weak_observation_inventory(expected_composite_inventory)
    actual_inventory = tuple(
        {field: record[field] for field in WEAK_OBSERVATION_IDENTITY_FIELDS}
        for record in normalized
    )
    if actual_inventory != inventory:
        raise ProspectiveContractError(
            "weak observations do not match the committed composite inventory"
        )
    if _sha256(
        expected_composite_inventory_sha256,
        context="expected weak composite_inventory_sha256",
    ) != sha256_json(inventory):
        raise ProspectiveContractError("weak composite inventory hash commitment mismatch")
    if _sha256(
        expected_records_sha256,
        context="expected weak records_sha256",
    ) != sha256_json(normalized):
        raise ProspectiveContractError("weak observation records hash commitment mismatch")
    weak_targets = {record["target_id"] for record in normalized}
    heldout_targets = {slot["target_id"] for slot in slots}
    if weak_targets != heldout_targets:
        raise ProspectiveContractError(
            "weak observations and heldout slots must cover the same exact target set"
        )
    return normalized


def validate_challenge_slot_inventory(
    records: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, str], ...]:
    """Validate the public inventory: exactly two aggregate slots per target."""

    normalized: list[dict[str, str]] = []
    seen_slots: set[str] = set()
    kinds_by_target: dict[str, set[str]] = defaultdict(set)
    expected = set(CHALLENGE_SLOT_FIELDS)
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise ProspectiveContractError(f"challenge_slot[{index}] must be an object")
        _require_exact_keys(record, expected, context=f"challenge_slot[{index}]")
        target_id = _pairing_token(record["target_id"], context="target_id")
        slot_id = _pairing_token(record["challenge_slot_id"], context="challenge_slot_id")
        kind = record["challenge_kind"]
        if kind not in CHALLENGE_KINDS:
            raise ProspectiveContractError(f"unsupported challenge_kind={kind!r}")
        if slot_id in seen_slots:
            raise ProspectiveContractError(f"duplicate challenge_slot_id={slot_id}")
        if kind in kinds_by_target[target_id]:
            raise ProspectiveContractError(
                f"duplicate challenge kind for target={target_id}, kind={kind}"
            )
        seen_slots.add(slot_id)
        kinds_by_target[target_id].add(str(kind))
        normalized.append(
            {
                "target_id": target_id,
                "challenge_slot_id": slot_id,
                "challenge_kind": str(kind),
            }
        )
    if not normalized:
        raise ProspectiveContractError("challenge slot inventory must not be empty")
    required_kinds = set(CHALLENGE_KINDS)
    if any(kinds != required_kinds for kinds in kinds_by_target.values()):
        raise ProspectiveContractError(
            "each target must have exactly one slot for every frozen challenge kind"
        )
    return tuple(sorted(normalized, key=_slot_sort_key))


def _probabilities(value: Any, *, context: str) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise ProspectiveContractError(f"{context} must be an object")
    _require_exact_keys(value, set(OUTCOME_LABELS), context=context)
    normalized: dict[str, float] = {}
    for label in OUTCOME_LABELS:
        probability = value[label]
        if isinstance(probability, bool) or not isinstance(probability, (int, float)):
            raise ProspectiveContractError(f"{context}.{label} must be numeric")
        probability = float(probability)
        if not math.isfinite(probability):
            raise ProspectiveContractError(f"{context}.{label} must be finite")
        if not PROBABILITY_FLOOR <= probability <= 1.0:
            raise ProspectiveContractError(f"{context}.{label} must be in [{PROBABILITY_FLOOR}, 1]")
        normalized[label] = probability
    if abs(math.fsum(normalized.values()) - 1.0) > PROBABILITY_SUM_TOLERANCE:
        raise ProspectiveContractError(f"{context} must sum to one")
    return normalized


def validate_challenge_predictions(
    records: Iterable[Mapping[str, Any]],
    expected_slots: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Validate exact slot coverage and the three-outcome probability simplex."""

    slots = validate_challenge_slot_inventory(expected_slots)
    slot_map = {record["challenge_slot_id"]: record for record in slots}
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    expected_fields = set(CHALLENGE_PREDICTION_FIELDS)
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise ProspectiveContractError(f"prediction[{index}] must be an object")
        _require_exact_keys(record, expected_fields, context=f"prediction[{index}]")
        if record["schema_version"] != PROSPECTIVE_CONTRACT_VERSION:
            raise ProspectiveContractError("unsupported challenge prediction schema_version")
        target_id = _pairing_token(record["target_id"], context="target_id")
        slot_id = _pairing_token(record["challenge_slot_id"], context="challenge_slot_id")
        kind = record["challenge_kind"]
        expected_slot = slot_map.get(slot_id)
        if expected_slot is None or (target_id, kind) != (
            expected_slot["target_id"],
            expected_slot["challenge_kind"],
        ):
            raise ProspectiveContractError("prediction references an unknown or mismatched slot")
        if slot_id in seen:
            raise ProspectiveContractError(f"duplicate prediction slot={slot_id}")
        seen.add(slot_id)
        probabilities = _probabilities(
            record["probabilities"], context=f"prediction[{index}].probabilities"
        )
        abstain = record["abstain"]
        reason = record["abstention_reason"]
        if type(abstain) is not bool:
            raise ProspectiveContractError("abstain must be boolean")
        if abstain and reason not in ABSTENTION_REASONS:
            raise ProspectiveContractError(
                "abstained predictions require one frozen abstention reason"
            )
        if not abstain and reason is not None:
            raise ProspectiveContractError("accepted predictions must have null abstention_reason")
        normalized.append(
            {
                "schema_version": PROSPECTIVE_CONTRACT_VERSION,
                "target_id": target_id,
                "challenge_slot_id": slot_id,
                "challenge_kind": str(kind),
                "probabilities": probabilities,
                "abstain": abstain,
                "abstention_reason": reason,
            }
        )
    if seen != set(slot_map):
        raise ProspectiveContractError("predictions must cover every committed challenge slot")
    return tuple(sorted(normalized, key=_slot_sort_key))


def validate_challenge_scoring_key(
    records: Iterable[Mapping[str, Any]],
    expected_slots: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Validate sealed aggregate outcomes and dependency-cluster membership."""

    slots = validate_challenge_slot_inventory(expected_slots)
    slot_map = {record["challenge_slot_id"]: record for record in slots}
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    expected_fields = set(CHALLENGE_SCORING_KEY_FIELDS)
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise ProspectiveContractError(f"scoring_key[{index}] must be an object")
        _require_exact_keys(record, expected_fields, context=f"scoring_key[{index}]")
        if record["schema_version"] != PROSPECTIVE_CONTRACT_VERSION:
            raise ProspectiveContractError("unsupported challenge scoring-key schema_version")
        target_id = _pairing_token(record["target_id"], context="target_id")
        slot_id = _pairing_token(record["challenge_slot_id"], context="challenge_slot_id")
        kind = record["challenge_kind"]
        expected_slot = slot_map.get(slot_id)
        if expected_slot is None or (target_id, kind) != (
            expected_slot["target_id"],
            expected_slot["challenge_kind"],
        ):
            raise ProspectiveContractError("scoring key references an unknown or mismatched slot")
        if slot_id in seen:
            raise ProspectiveContractError(f"duplicate scoring-key slot={slot_id}")
        seen.add(slot_id)
        cluster_id = _dependency_cluster_id(record["dependency_cluster_id"])
        counts = record["outcome_counts"]
        if not isinstance(counts, Mapping):
            raise ProspectiveContractError("outcome_counts must be an object")
        _require_exact_keys(counts, set(OUTCOME_LABELS), context="outcome_counts")
        normalized_counts: dict[str, int] = {}
        for label in OUTCOME_LABELS:
            count = counts[label]
            if type(count) is not int or count < 0:
                raise ProspectiveContractError("outcome counts must be non-negative integers")
            normalized_counts[label] = count
        trial_count = record["trial_count"]
        if type(trial_count) is not int or trial_count < 1:
            raise ProspectiveContractError("trial_count must be a positive integer")
        if sum(normalized_counts.values()) != trial_count:
            raise ProspectiveContractError("outcome counts must sum to trial_count")
        normalized.append(
            {
                "schema_version": PROSPECTIVE_CONTRACT_VERSION,
                "target_id": target_id,
                "challenge_slot_id": slot_id,
                "challenge_kind": str(kind),
                "dependency_cluster_id": cluster_id,
                "outcome_counts": normalized_counts,
                "trial_count": trial_count,
            }
        )
    if seen != set(slot_map):
        raise ProspectiveContractError("scoring key must cover every committed challenge slot")
    clusters_by_target: dict[str, set[str]] = defaultdict(set)
    for record in normalized:
        clusters_by_target[record["target_id"]].add(record["dependency_cluster_id"])
    if any(len(cluster_ids) != 1 for cluster_ids in clusters_by_target.values()):
        raise ProspectiveContractError("each target must belong to exactly one dependency cluster")
    return tuple(sorted(normalized, key=_slot_sort_key))


def score_challenge_predictions(
    predictions: Iterable[Mapping[str, Any]],
    scoring_key: Iterable[Mapping[str, Any]],
    expected_slots: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Score every slot, with equal target and cluster weight at the macro level.

    Abstention never removes a slot from the primary log-loss or Brier score.
    It changes only the separately reported coverage.
    """

    slots = validate_challenge_slot_inventory(expected_slots)
    normalized_predictions = validate_challenge_predictions(predictions, slots)
    normalized_key = validate_challenge_scoring_key(scoring_key, slots)
    prediction_by_slot = {record["challenge_slot_id"]: record for record in normalized_predictions}
    target_totals: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "log_loss_sum": 0.0,
            "brier_sum": 0.0,
            "trials": 0.0,
            "accepted_slots": 0.0,
            "slots": 0.0,
        }
    )
    target_clusters: dict[str, str] = {}
    slot_rows: list[dict[str, Any]] = []
    for key in normalized_key:
        prediction = prediction_by_slot[key["challenge_slot_id"]]
        probabilities = prediction["probabilities"]
        counts = key["outcome_counts"]
        trials = key["trial_count"]
        frequencies = {label: counts[label] / trials for label in OUTCOME_LABELS}
        log_loss = -math.fsum(
            frequencies[label] * math.log(probabilities[label]) for label in OUTCOME_LABELS
        )
        brier = math.fsum(
            probabilities[label] ** 2
            - 2.0 * probabilities[label] * frequencies[label]
            + frequencies[label]
            for label in OUTCOME_LABELS
        )
        totals = target_totals[key["target_id"]]
        totals["log_loss_sum"] += log_loss * trials
        totals["brier_sum"] += brier * trials
        totals["trials"] += trials
        totals["slots"] += 1
        if not prediction["abstain"]:
            totals["accepted_slots"] += 1
        target_clusters[key["target_id"]] = key["dependency_cluster_id"]
        slot_rows.append(
            {
                "target_id": key["target_id"],
                "challenge_slot_id": key["challenge_slot_id"],
                "challenge_kind": key["challenge_kind"],
                "trial_count": trials,
                "log_loss": log_loss,
                "multiclass_brier": brier,
                "abstain": prediction["abstain"],
            }
        )

    cluster_targets: dict[str, list[dict[str, float]]] = defaultdict(list)
    for target_id, totals in target_totals.items():
        cluster_targets[target_clusters[target_id]].append(
            {
                "log_loss": totals["log_loss_sum"] / totals["trials"],
                "multiclass_brier": totals["brier_sum"] / totals["trials"],
                "coverage": totals["accepted_slots"] / totals["slots"],
            }
        )
    cluster_rows: list[dict[str, Any]] = []
    for cluster_id, target_metrics in sorted(cluster_targets.items()):
        cluster_rows.append(
            {
                "dependency_cluster_id": cluster_id,
                "target_count": len(target_metrics),
                "log_loss": math.fsum(item["log_loss"] for item in target_metrics)
                / len(target_metrics),
                "multiclass_brier": math.fsum(item["multiclass_brier"] for item in target_metrics)
                / len(target_metrics),
                "slot_coverage": math.fsum(item["coverage"] for item in target_metrics)
                / len(target_metrics),
            }
        )
    cluster_count = len(cluster_rows)
    return {
        "schema_version": PROSPECTIVE_CONTRACT_VERSION,
        "aggregation": AGGREGATION_RULE,
        "primary_scores_include_abstentions": True,
        "dependency_cluster_count": cluster_count,
        "target_count": len(target_totals),
        "slot_count": len(slot_rows),
        PRIMARY_METRIC: math.fsum(row["log_loss"] for row in cluster_rows) / cluster_count,
        SECONDARY_METRIC: math.fsum(row["multiclass_brier"] for row in cluster_rows)
        / cluster_count,
        "macro_dependency_cluster_slot_coverage": math.fsum(
            row["slot_coverage"] for row in cluster_rows
        )
        / cluster_count,
        "clusters": cluster_rows,
        "slots": sorted(slot_rows, key=_slot_sort_key),
    }


def _prediction_for_slot(
    slot: Mapping[str, str], probabilities: Mapping[str, float]
) -> dict[str, Any]:
    return {
        "schema_version": PROSPECTIVE_CONTRACT_VERSION,
        **slot,
        "probabilities": dict(probabilities),
        "abstain": False,
        "abstention_reason": None,
    }


def weak_orbit_route_agnostic_baseline(
    observations: Iterable[Mapping[str, Any]],
    expected_slots: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Route-agnostic add-one baseline from committed weak Q_obs outputs.

    Weak observations have semantic and cue factors aligned, so a parsed output
    cannot identify which route produced it. Each parsed output therefore adds
    one half-count to each route-consistent label. Parse failures retain their
    ordinary full count.
    """

    slots = validate_challenge_slot_inventory(expected_slots)
    expected_targets = {slot["target_id"] for slot in slots}
    counts_by_target: dict[str, dict[str, float]] = {
        target_id: {label: float(BASELINE_PSEUDOCOUNT) for label in OUTCOME_LABELS}
        for target_id in expected_targets
    }
    observation_counts = {target_id: 0 for target_id in expected_targets}
    for index, observation in enumerate(observations):
        if not isinstance(observation, Mapping):
            raise ProspectiveContractError(f"observation[{index}] must be an object")
        target_id = _pairing_token(observation.get("target_id"), context="target_id")
        if target_id not in expected_targets:
            raise ProspectiveContractError("weak observations contain an uncommitted target")
        output_text = observation.get("output_text")
        if not isinstance(output_text, str):
            raise ProspectiveContractError("observation output_text must be text")
        parsed = parse_final(output_text)
        if parsed is None:
            counts_by_target[target_id]["parse_failure"] += 1.0
        else:
            counts_by_target[target_id]["semantic_consistent"] += 0.5
            counts_by_target[target_id]["surface_cue_consistent"] += 0.5
        observation_counts[target_id] += 1
    if any(count == 0 for count in observation_counts.values()):
        raise ProspectiveContractError("every challenge target needs weak observations")

    predictions = []
    for slot in slots:
        counts = counts_by_target[slot["target_id"]]
        denominator = sum(counts.values())
        probabilities = {label: counts[label] / denominator for label in OUTCOME_LABELS}
        predictions.append(_prediction_for_slot(slot, probabilities))
    return validate_challenge_predictions(predictions, slots)


def development_challenge_marginal_baseline(
    development_scoring_key: Iterable[Mapping[str, Any]],
    expected_development_slots: Iterable[Mapping[str, Any]],
    heldout_scoring_key: Iterable[Mapping[str, Any]],
    heldout_slots: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Cluster-equal development marginal, with add one per cluster/kind/class."""

    development_slots = validate_challenge_slot_inventory(expected_development_slots)
    validated_development = validate_challenge_scoring_key(
        development_scoring_key,
        development_slots,
    )
    slots = validate_challenge_slot_inventory(heldout_slots)
    validated_heldout = validate_challenge_scoring_key(heldout_scoring_key, slots)
    _require_development_heldout_disjoint(validated_development, validated_heldout)

    counts_by_kind_cluster: dict[str, dict[str, dict[str, int]]] = {
        kind: {} for kind in CHALLENGE_KINDS
    }
    for row in validated_development:
        kind = row["challenge_kind"]
        cluster_id = row["dependency_cluster_id"]
        counts = counts_by_kind_cluster[kind].setdefault(
            cluster_id,
            {label: BASELINE_PSEUDOCOUNT for label in OUTCOME_LABELS},
        )
        for label in OUTCOME_LABELS:
            counts[label] += row["outcome_counts"][label]

    probabilities_by_kind: dict[str, dict[str, float]] = {}
    for kind in CHALLENGE_KINDS:
        cluster_counts = counts_by_kind_cluster[kind]
        if not cluster_counts:
            raise ProspectiveContractError(
                "every challenge kind needs development outcomes in every included design"
            )
        cluster_probabilities = []
        for cluster_id in sorted(cluster_counts):
            counts = cluster_counts[cluster_id]
            denominator = sum(counts.values())
            cluster_probabilities.append(
                {label: counts[label] / denominator for label in OUTCOME_LABELS}
            )
        probabilities_by_kind[kind] = {
            label: math.fsum(row[label] for row in cluster_probabilities)
            / len(cluster_probabilities)
            for label in OUTCOME_LABELS
        }

    predictions = [
        _prediction_for_slot(slot, probabilities_by_kind[slot["challenge_kind"]]) for slot in slots
    ]
    return validate_challenge_predictions(predictions, slots)


def _require_development_heldout_disjoint(
    development_rows: Iterable[Mapping[str, Any]],
    heldout_rows: Iterable[Mapping[str, Any]],
) -> None:
    development = tuple(development_rows)
    heldout = tuple(heldout_rows)
    development_targets = {row["target_id"] for row in development}
    heldout_targets = {row["target_id"] for row in heldout}
    development_slot_ids = {row["challenge_slot_id"] for row in development}
    heldout_slot_ids = {row["challenge_slot_id"] for row in heldout}
    development_cluster_ids = {row["dependency_cluster_id"] for row in development}
    heldout_cluster_ids = {row["dependency_cluster_id"] for row in heldout}
    if (
        development_targets & heldout_targets
        or development_slot_ids & heldout_slot_ids
        or development_cluster_ids & heldout_cluster_ids
    ):
        raise ProspectiveContractError(
            "development and heldout target, slot, and dependency-cluster identities "
            "must be disjoint"
        )


def evaluate_verified_candidate_gate(
    candidate_predictions: Iterable[Mapping[str, Any]],
    heldout_scoring_key: Iterable[Mapping[str, Any]],
    heldout_slots: Iterable[Mapping[str, Any]],
    *,
    weak_observations: Iterable[Mapping[str, Any]],
    development_scoring_key: Iterable[Mapping[str, Any]],
    development_slots: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Pure scorer for artifacts already verified by the blind authority bridge.

    This deliberately named low-level entrypoint performs no phase or capability
    enforcement. Production scoring must call
    ``blind.evaluate_committed_pilot_gate`` so all three fold commitments close
    before any reveal and candidate, weak, development, and heldout artifacts
    are obtained from their committed sources. No baseline prediction vector or
    score is accepted here. A fold-local stronger baseline is descriptive only;
    the production coordinator chooses one globally stronger baseline from the
    equal means across all three folds. Exact ties resolve to the weak-orbit
    baseline by the frozen priority order.
    """

    slots = validate_challenge_slot_inventory(heldout_slots)
    key = validate_challenge_scoring_key(heldout_scoring_key, slots)
    normalized_candidate = validate_challenge_predictions(candidate_predictions, slots)

    normalized_weak = _normalize_weak_observations(weak_observations)
    weak_targets = {record["target_id"] for record in normalized_weak}
    heldout_targets = {slot["target_id"] for slot in slots}
    if weak_targets != heldout_targets:
        raise ProspectiveContractError(
            "weak observations and heldout slots must cover the same exact target set"
        )
    weak_inventory = tuple(
        {field: record[field] for field in WEAK_OBSERVATION_IDENTITY_FIELDS}
        for record in normalized_weak
    )

    normalized_development_slots = validate_challenge_slot_inventory(development_slots)
    development_key = validate_challenge_scoring_key(
        development_scoring_key,
        normalized_development_slots,
    )
    _require_development_heldout_disjoint(development_key, key)

    weak_baseline_predictions = weak_orbit_route_agnostic_baseline(normalized_weak, slots)
    development_baseline_predictions = development_challenge_marginal_baseline(
        development_key,
        normalized_development_slots,
        key,
        slots,
    )

    candidate_score = score_challenge_predictions(normalized_candidate, key, slots)
    baseline_scores = {
        WEAK_ORBIT_BASELINE_ID: score_challenge_predictions(weak_baseline_predictions, key, slots),
        DEVELOPMENT_BASELINE_ID: score_challenge_predictions(
            development_baseline_predictions, key, slots
        ),
    }
    priority = {baseline_id: index for index, baseline_id in enumerate(BASELINE_PRIORITY)}
    stronger_baseline_id = min(
        baseline_scores,
        key=lambda baseline_id: (
            baseline_scores[baseline_id][PRIMARY_METRIC],
            priority[baseline_id],
        ),
    )
    stronger_loss = baseline_scores[stronger_baseline_id][PRIMARY_METRIC]
    candidate_loss = candidate_score[PRIMARY_METRIC]
    maximum_passing_loss = (1.0 - PRIMARY_GATE_RELATIVE_REDUCTION) * stronger_loss
    observed_reduction = (
        (stronger_loss - candidate_loss) / stronger_loss if stronger_loss > 0.0 else None
    )
    passes = stronger_loss > 0.0 and candidate_loss <= maximum_passing_loss + GATE_NUMERIC_TOLERANCE
    return {
        "schema_version": PROSPECTIVE_CONTRACT_VERSION,
        "primary_metric": PRIMARY_METRIC,
        "required_relative_reduction": PRIMARY_GATE_RELATIVE_REDUCTION,
        "stronger_baseline_id": stronger_baseline_id,
        "stronger_baseline_log_loss": stronger_loss,
        "maximum_passing_candidate_log_loss": maximum_passing_loss,
        "candidate_log_loss": candidate_loss,
        "observed_relative_reduction": observed_reduction,
        "passes_primary_gate": passes,
        "derived_input_hashes": {
            "weak_observation_records_sha256": sha256_json(normalized_weak),
            "weak_observation_inventory_sha256": sha256_json(weak_inventory),
            "development_scoring_key_sha256": sha256_json(development_key),
            "development_slot_inventory_sha256": sha256_json(normalized_development_slots),
            "heldout_scoring_key_sha256": sha256_json(key),
            "heldout_slot_inventory_sha256": sha256_json(slots),
        },
        "candidate_score": candidate_score,
        "baseline_scores": baseline_scores,
    }
