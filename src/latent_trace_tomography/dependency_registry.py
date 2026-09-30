"""Post-freeze dependency-cluster evidence registry for OSS-1.

This module is an authoring and audit companion to the frozen discovery
authorization.  It does not redefine ``dependency_cluster_id`` and it never
certifies statistical independence.  Instead, it makes declared provenance,
common influences, and evaluation exposure explicit before an authorization
can be issued, then checks that every authoritative claim projects into the
existing frozen authorization surface.

The frozen execution validators remain authoritative for learned-state graph
closure and three-cluster balance.  Importing their private helpers here is
intentional: this successor adapter is pinned to the already sealed source and
must not silently reimplement a different cluster algorithm.
"""

from __future__ import annotations

import hashlib
import hmac
import math
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from itertools import combinations
from typing import Any

from latent_trace_tomography import execution as _frozen_execution


SCHEMA_VERSION = "0.1.0"
CONTRACT_ID = "dependency_cluster_registry_evidence_v1"
ROLE = "post_freeze_pre_discovery_authoring_bundle"
STATUS = "evidence_closed_pre_discovery"
DESIGN_FREEZE_ID = "oss_reliance_regime_v0_design_20260717"
DESIGN_MANIFEST_SHA256 = "8c974390ceea3f1defaae19067359c909b4182dd26c321075c9e25ee1518e64b"
PROTOCOL_SHA256 = "5c49316503b2cec2ad26d4bf47dc59c02f0b61d9f6896b84035e6d0412dced11"
DISCOVERY_TEMPLATE_SHA256 = "3a80dc38a066c980ecfa3bb4221c65b273fc8acfa44b5ea55ae845fed19eed79"
PRE_OUTCOME_CORRECTION_ID = "oss1_pre_outcome_correction_0002_minimal_site_report_cardinality"
PRE_OUTCOME_CORRECTION_MANIFEST_SHA256 = (
    "4d2282f761c75cfc5b3cd9dcb36ddb624b8982c0eed9076f3a70bf9498787e3a"
)
DESIGN_FREEZE_BOUNDARY = datetime(2026, 7, 17, tzinfo=timezone.utc)
GATE_RECEIPT_TYPE = "registry_authorization_gate_receipt_v1"
GATE_RECEIPT_STATUS = "registry_and_authorization_bound"
GATE_RECEIPT_HMAC_DOMAIN = b"ltt:registry-authorization-gate-receipt:v1\x00"

CLUSTER_MEANING = "connected component of authority-declared learned-state ancestry"
UNKNOWN_DEPENDENCY_POLICY = "conservatively cluster or exclude; never split or increase effective n"
DOES_NOT_ESTABLISH = (
    "absence of abstract task overlap",
    "disjoint upstream training data",
    "globally complete provenance",
    "statistical independence",
)
REQUIRED_LIMITATIONS = {
    "authority-declared ancestry completeness is not externally proven",
    "different seeds or checkpoints do not prove independence",
    "shared data or task exposure is a common influence, not a learned-state edge in v0",
}

TOP_LEVEL_FIELDS = {
    "schema_version",
    "contract_id",
    "role",
    "status",
    "registry_id",
    "created_at",
    "evidence_cutoff_at",
    "parent",
    "outcome_exposure",
    "epistemic_boundary",
    "source_records",
    "candidate_model_units",
    "eligible_model_unit_ids",
    "pairwise_relatedness",
    "evaluation_exposure_assessments",
    "authorization_projection",
    "binding_map",
    "limitations",
    "registry_body_sha256",
}
PROJECTION_FIELDS = {
    "architecture_families",
    "model_registry",
    "learned_state_ancestry",
    "dependency_graph",
    "dependency_clusters",
    "nuisance_balance_contract",
    "projection_sha256",
}
AUTHORIZATION_PROJECTION_FIELDS = tuple(
    field for field in sorted(PROJECTION_FIELDS) if field != "projection_sha256"
)
SOURCE_RECORD_FIELDS = {
    "source_record_id",
    "source_kind",
    "content_sha256",
    "locator_sha256",
    "evidence_status",
    "recorded_at",
    "source_record_sha256",
}
CANDIDATE_FIELDS = {
    "model_unit_id",
    "enrollment_status",
    "exclusion_reason_ids",
    "checkpoint_provenance",
    "training_randomness",
    "training_data_stages",
    "task_provenance",
}
PAIR_FIELDS = {
    "left_model_unit_id",
    "right_model_unit_id",
    "learned_state",
    "training_randomness",
    "training_data",
    "task_relation",
    "handling",
}
EXPOSURE_FIELDS = {
    "model_unit_id",
    "exact_live_prompt_overlap",
    "frozen_generator_artifact_exposure",
    "frozen_template_exposure",
    "abstract_task_family_exposure",
    "checkpoint_precedes_design_freeze",
    "evidence_record_sha256",
    "eligibility_decision",
    "reason_ids",
}
BINDING_FIELDS = {
    "assertion_id",
    "source_record_sha256",
    "authorization_json_pointer",
    "binding_status",
    "material_for_eligibility",
}
GATE_RECEIPT_FIELDS = {
    "schema_version",
    "receipt_type",
    "status",
    "registry_id",
    "registry_body_sha256",
    "authorization_id",
    "authorization_sha256",
    "authorization_projection_sha256",
    "authorized_at",
    "issued_at",
    "authority_secret_commitment_sha256",
    "authority_hmac_sha256",
    "receipt_sha256",
}


class DependencyRegistryError(ValueError):
    """Raised when a pre-discovery registry fails closed."""


def canonical_artifact_sha256(value: Any) -> str:
    """Use the exact canonical-JSON hash function sealed by OSS-1."""

    return _frozen_execution.canonical_artifact_sha256(value)


def _mapping(value: Any, *, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DependencyRegistryError(f"{context} must be an object")
    return value


def _sequence(value: Any, *, context: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise DependencyRegistryError(f"{context} must be an array")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], *, context: str) -> None:
    observed = set(value)
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise DependencyRegistryError(f"{context} fields differ; missing={missing}, extra={extra}")


def _text(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise DependencyRegistryError(f"{context} must be non-empty text")
    return value


def _sha256(value: Any, *, context: str) -> str:
    text = _text(value, context=context)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise DependencyRegistryError(f"{context} must be lowercase SHA-256")
    if text == "0" * 64:
        raise DependencyRegistryError(f"{context} must not be an all-zero placeholder")
    return text


def _timestamp(value: Any, *, context: str) -> datetime:
    text = _text(value, context=context)
    if not text.endswith("Z"):
        raise DependencyRegistryError(f"{context} must be an RFC 3339 UTC timestamp ending Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as error:
        raise DependencyRegistryError(f"{context} must be a valid timestamp") from error
    if parsed.tzinfo != timezone.utc:
        raise DependencyRegistryError(f"{context} must be UTC")
    return parsed


def _sorted_unique_texts(
    value: Any,
    *,
    context: str,
    minimum: int = 0,
    exact: int | None = None,
) -> tuple[str, ...]:
    rows = _sequence(value, context=context)
    texts = tuple(_text(item, context=f"{context}[{index}]") for index, item in enumerate(rows))
    if exact is not None and len(texts) != exact:
        raise DependencyRegistryError(f"{context} must contain exactly {exact} values")
    if len(texts) < minimum:
        raise DependencyRegistryError(f"{context} must contain at least {minimum} values")
    if len(texts) != len(set(texts)) or texts != tuple(sorted(texts)):
        raise DependencyRegistryError(f"{context} must be unique and lexicographically sorted")
    return texts


def _validate_parent(value: Any) -> None:
    parent = _mapping(value, context="parent")
    expected = {
        "design_freeze_id",
        "design_manifest_sha256",
        "protocol_sha256",
        "discovery_template_sha256",
        "pre_outcome_correction_id",
        "pre_outcome_correction_manifest_sha256",
    }
    _exact_keys(parent, expected, context="parent")
    required = {
        "design_freeze_id": DESIGN_FREEZE_ID,
        "design_manifest_sha256": DESIGN_MANIFEST_SHA256,
        "protocol_sha256": PROTOCOL_SHA256,
        "discovery_template_sha256": DISCOVERY_TEMPLATE_SHA256,
        "pre_outcome_correction_id": PRE_OUTCOME_CORRECTION_ID,
        "pre_outcome_correction_manifest_sha256": (PRE_OUTCOME_CORRECTION_MANIFEST_SHA256),
    }
    if dict(parent) != required:
        raise DependencyRegistryError("registry parent does not bind the frozen OSS-1 surface")


def _validate_exposure(value: Any) -> None:
    exposure = _mapping(value, context="outcome_exposure")
    expected = {
        "oss_model_calls": 0,
        "oss_outcomes_exposed": False,
        "discovery_authorization_issued": False,
    }
    if dict(exposure) != expected:
        raise DependencyRegistryError(
            "registry must close before authorization, model calls, or OSS outcomes"
        )


def _validate_epistemic_boundary(value: Any) -> None:
    boundary = _mapping(value, context="epistemic_boundary")
    expected_fields = {
        "cluster_meaning",
        "primary_independent_unit",
        "independence_certified",
        "does_not_establish",
        "unknown_dependency_policy",
    }
    _exact_keys(boundary, expected_fields, context="epistemic_boundary")
    if (
        boundary["cluster_meaning"] != CLUSTER_MEANING
        or boundary["primary_independent_unit"] != "dependency_cluster_id"
        or boundary["independence_certified"] is not False
        or boundary["unknown_dependency_policy"] != UNKNOWN_DEPENDENCY_POLICY
    ):
        raise DependencyRegistryError("epistemic boundary was strengthened or redefined")
    values = _sorted_unique_texts(
        boundary["does_not_establish"],
        context="epistemic_boundary.does_not_establish",
        exact=4,
    )
    if values != DOES_NOT_ESTABLISH:
        raise DependencyRegistryError("epistemic boundary must retain all four non-claims")


def _validate_source_records(
    value: Any, *, evidence_cutoff: datetime
) -> dict[str, Mapping[str, Any]]:
    records = _sequence(value, context="source_records")
    if not records:
        raise DependencyRegistryError("source_records must not be empty")
    by_hash: dict[str, Mapping[str, Any]] = {}
    ids: list[str] = []
    for index, raw in enumerate(records):
        record = _mapping(raw, context=f"source_records[{index}]")
        _exact_keys(record, SOURCE_RECORD_FIELDS, context=f"source_records[{index}]")
        record_id = _text(record["source_record_id"], context=f"source_records[{index}].id")
        if record["source_kind"] not in {
            "model_manifest",
            "tokenizer_manifest",
            "checkpoint_manifest",
            "training_run_manifest",
            "initialization_manifest",
            "rng_manifest",
            "training_recipe_manifest",
            "training_data_manifest",
            "task_manifest",
            "ancestry_manifest",
            "overlap_scan_manifest",
            "evaluation_exposure_scan_manifest",
            "environment_manifest",
        }:
            raise DependencyRegistryError("source record kind is not recognized")
        _sha256(record["content_sha256"], context=f"source_records[{index}].content_sha256")
        _sha256(record["locator_sha256"], context=f"source_records[{index}].locator_sha256")
        if record["evidence_status"] not in {
            "complete_content_addressed",
            "partial_content_addressed",
            "authority_attested_only",
            "unavailable",
        }:
            raise DependencyRegistryError("source evidence status is not recognized")
        if (
            _timestamp(record["recorded_at"], context=f"source_records[{index}].recorded_at")
            > evidence_cutoff
        ):
            raise DependencyRegistryError("source record postdates the evidence cutoff")
        expected_hash = canonical_artifact_sha256(
            {field: record[field] for field in SOURCE_RECORD_FIELDS - {"source_record_sha256"}}
        )
        observed_hash = _sha256(
            record["source_record_sha256"],
            context=f"source_records[{index}].source_record_sha256",
        )
        if observed_hash != expected_hash:
            raise DependencyRegistryError("source record is not self-addressed")
        if record_id in ids or observed_hash in by_hash:
            raise DependencyRegistryError("source records contain a duplicate id or hash")
        ids.append(record_id)
        by_hash[observed_hash] = record
    if ids != sorted(ids):
        raise DependencyRegistryError("source_records must be sorted by source_record_id")
    return by_hash


def _source(
    value: Any,
    *,
    context: str,
    source_records: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any]:
    digest = _sha256(value, context=context)
    try:
        return source_records[digest]
    except KeyError as error:
        raise DependencyRegistryError(f"{context} is absent from source_records") from error


def _claim_source(
    value: Any,
    *,
    context: str,
    source_records: Mapping[str, Mapping[str, Any]],
    mandatory_sources: set[str],
    allowed_kinds: set[str],
    required_statuses: set[str] | None = None,
) -> Mapping[str, Any]:
    """Resolve one claim-bearing source and derive its materiality.

    Materiality is intentionally derived from actual use by a candidate,
    pairwise relation, or exposure decision.  A registry author cannot make a
    used source supplementary merely by changing ``binding_map`` metadata.
    """

    digest = _sha256(value, context=context)
    source = _source(digest, context=context, source_records=source_records)
    if source["source_kind"] not in allowed_kinds:
        raise DependencyRegistryError(
            f"{context} has source_kind={source['source_kind']!r}; "
            f"expected one of {sorted(allowed_kinds)}"
        )
    if required_statuses is not None and source["evidence_status"] not in required_statuses:
        raise DependencyRegistryError(
            f"{context} has evidence_status={source['evidence_status']!r}; "
            f"expected one of {sorted(required_statuses)}"
        )
    mandatory_sources.add(digest)
    return source


def _validate_projection(value: Any) -> tuple[tuple[Mapping[str, Any], ...], dict[str, str]]:
    projection = _mapping(value, context="authorization_projection")
    _exact_keys(projection, PROJECTION_FIELDS, context="authorization_projection")
    families = _sorted_unique_texts(
        projection["architecture_families"],
        context="authorization_projection.architecture_families",
        exact=3,
    )
    try:
        models = _frozen_execution._validate_model_registry(projection["model_registry"])
        ancestry_edges = _frozen_execution._validate_learned_state_ancestry(
            projection["learned_state_ancestry"], model_registry=models
        )
        _frozen_execution._validate_dependency_surface(
            model_registry=models,
            dependency_graph_value=projection["dependency_graph"],
            dependency_clusters_value=projection["dependency_clusters"],
            expected_ancestry_edges=ancestry_edges,
        )
    except _frozen_execution.ExecutionContractError as error:
        raise DependencyRegistryError(
            f"authorization projection failed frozen closure: {error}"
        ) from error
    if projection["nuisance_balance_contract"] != _frozen_execution.NUISANCE_BALANCE_CONTRACT:
        raise DependencyRegistryError("nuisance balance contract drifted from the frozen value")
    if families != tuple(sorted({model["architecture_family_id"] for model in models})):
        raise DependencyRegistryError(
            "architecture families do not close the projected model registry"
        )
    body = {field: projection[field] for field in PROJECTION_FIELDS - {"projection_sha256"}}
    if projection["projection_sha256"] != canonical_artifact_sha256(body):
        raise DependencyRegistryError("authorization projection is not content-addressed")
    cluster_by_unit = {
        model_unit_id: cluster["dependency_cluster_id"]
        for cluster in projection["dependency_clusters"]
        for model_unit_id in cluster["model_unit_ids"]
    }
    return models, cluster_by_unit


def _validate_candidate_units(
    value: Any,
    *,
    eligible_ids: tuple[str, ...],
    models: tuple[Mapping[str, Any], ...],
    source_records: Mapping[str, Mapping[str, Any]],
    mandatory_sources: set[str],
    evidence_cutoff: datetime,
) -> dict[str, Mapping[str, Any]]:
    records = _sequence(value, context="candidate_model_units")
    if len(records) < 9:
        raise DependencyRegistryError("candidate_model_units must retain at least nine candidates")
    model_by_id = {model["model_unit_id"]: model for model in models}
    by_id: dict[str, Mapping[str, Any]] = {}
    order: list[str] = []
    for index, raw in enumerate(records):
        record = _mapping(raw, context=f"candidate_model_units[{index}]")
        _exact_keys(record, CANDIDATE_FIELDS, context=f"candidate_model_units[{index}]")
        model_id = _text(
            record["model_unit_id"], context=f"candidate_model_units[{index}].model_unit_id"
        )
        if model_id in by_id:
            raise DependencyRegistryError("candidate_model_units contains a duplicate id")
        status = record["enrollment_status"]
        if status not in {"eligible", "excluded", "unresolved"}:
            raise DependencyRegistryError("candidate enrollment status is not recognized")
        reasons = _sorted_unique_texts(
            record["exclusion_reason_ids"],
            context=f"candidate_model_units[{index}].exclusion_reason_ids",
        )
        if (status == "eligible" and reasons) or (status != "eligible" and not reasons):
            raise DependencyRegistryError("candidate reason ids disagree with enrollment status")
        checkpoint = _mapping(
            record["checkpoint_provenance"],
            context=f"candidate_model_units[{index}].checkpoint_provenance",
        )
        checkpoint_fields = {
            "checkpoint_role",
            "checkpoint_manifest_sha256",
            "training_run_parent_id",
            "parent_checkpoint_artifact_sha256",
            "step_or_token_count",
            "created_at",
            "source_record_sha256",
        }
        _exact_keys(checkpoint, checkpoint_fields, context=f"candidate {model_id} checkpoint")
        checkpoint_source = _claim_source(
            checkpoint["source_record_sha256"],
            context=f"candidate {model_id} checkpoint source",
            source_records=source_records,
            mandatory_sources=mandatory_sources,
            allowed_kinds={"checkpoint_manifest"},
            required_statuses=({"complete_content_addressed"} if status == "eligible" else None),
        )
        if checkpoint_source["content_sha256"] != checkpoint["checkpoint_manifest_sha256"]:
            raise DependencyRegistryError("checkpoint source does not bind its manifest")
        checkpoint_created = _timestamp(
            checkpoint["created_at"],
            context=f"candidate {model_id} checkpoint.created_at",
        )
        checkpoint_source_recorded = _timestamp(
            checkpoint_source["recorded_at"],
            context=f"candidate {model_id} checkpoint source recorded_at",
        )
        if checkpoint_created > checkpoint_source_recorded or checkpoint_created > evidence_cutoff:
            raise DependencyRegistryError(
                "checkpoint creation cannot postdate its source record or evidence cutoff"
            )
        if status == "eligible" and checkpoint_created >= DESIGN_FREEZE_BOUNDARY:
            raise DependencyRegistryError("eligible checkpoint must precede the frozen design date")
        parent_hashes = _sorted_unique_texts(
            checkpoint["parent_checkpoint_artifact_sha256"],
            context=f"candidate {model_id} parent checkpoints",
        )
        for parent_index, digest in enumerate(parent_hashes):
            _sha256(digest, context=f"candidate {model_id} parent checkpoint[{parent_index}]")
        count = checkpoint["step_or_token_count"]
        if count is not None and (
            not isinstance(count, int) or isinstance(count, bool) or count < 0
        ):
            raise DependencyRegistryError(
                "checkpoint step_or_token_count must be nonnegative or null"
            )

        randomness = _mapping(
            record["training_randomness"],
            context=f"candidate_model_units[{index}].training_randomness",
        )
        random_fields = {
            "evidence_status",
            "rng_manifest_sha256",
            "initialization_state_artifact_sha256",
            "seed_values_disclosed",
            "source_record_sha256",
        }
        _exact_keys(randomness, random_fields, context=f"candidate {model_id} randomness")
        if randomness["evidence_status"] not in {
            "exact_manifest",
            "committed_manifest",
            "unavailable",
            "not_applicable",
        }:
            raise DependencyRegistryError("candidate RNG evidence status is not recognized")
        if status == "eligible" and randomness["evidence_status"] not in {
            "exact_manifest",
            "committed_manifest",
        }:
            raise DependencyRegistryError(
                "eligible candidate requires an exact or committed RNG manifest"
            )
        if randomness["seed_values_disclosed"] is not False:
            raise DependencyRegistryError(
                "registry must commit RNG evidence without raw seed values"
            )
        random_source = _claim_source(
            randomness["source_record_sha256"],
            context=f"candidate {model_id} randomness source",
            source_records=source_records,
            mandatory_sources=mandatory_sources,
            allowed_kinds={"rng_manifest"},
            required_statuses=({"complete_content_addressed"} if status == "eligible" else None),
        )
        if random_source["content_sha256"] != randomness["rng_manifest_sha256"]:
            raise DependencyRegistryError("RNG source does not bind its manifest")
        _sha256(
            randomness["initialization_state_artifact_sha256"],
            context=f"candidate {model_id} initialization state",
        )

        stages = _sequence(
            record["training_data_stages"],
            context=f"candidate_model_units[{index}].training_data_stages",
        )
        if not stages:
            raise DependencyRegistryError("every candidate must declare training-data stages")
        stage_ids: list[str] = []
        for stage_index, raw_stage in enumerate(stages):
            stage = _mapping(raw_stage, context=f"candidate {model_id} stage[{stage_index}]")
            stage_fields = {
                "stage_id",
                "scope",
                "manifest_status",
                "manifest_sha256",
                "record_identity_scheme_id",
                "record_count",
                "source_record_sha256",
            }
            _exact_keys(stage, stage_fields, context=f"candidate {model_id} stage[{stage_index}]")
            stage_id = _text(stage["stage_id"], context=f"candidate {model_id} stage id")
            if stage["scope"] not in {
                "upstream_pretraining",
                "continued_pretraining",
                "anchor_posttraining",
            }:
                raise DependencyRegistryError("training-data stage scope is not recognized")
            _text(
                stage["record_identity_scheme_id"],
                context=f"candidate {model_id} stage identity scheme",
            )
            if stage["manifest_status"] not in {
                "complete_for_declared_stage",
                "partial",
                "unavailable",
            }:
                raise DependencyRegistryError("training-data manifest status is not recognized")
            if status == "eligible" and stage["manifest_status"] != "complete_for_declared_stage":
                raise DependencyRegistryError(
                    "eligible candidate requires complete declared-stage training-data evidence"
                )
            source = _claim_source(
                stage["source_record_sha256"],
                context=f"candidate {model_id} stage source",
                source_records=source_records,
                mandatory_sources=mandatory_sources,
                allowed_kinds={"training_data_manifest"},
                required_statuses=(
                    {"complete_content_addressed"} if status == "eligible" else None
                ),
            )
            if source["content_sha256"] != stage["manifest_sha256"]:
                raise DependencyRegistryError("training-data source does not bind its manifest")
            record_count = stage["record_count"]
            if record_count is not None and (
                not isinstance(record_count, int)
                or isinstance(record_count, bool)
                or record_count < 0
            ):
                raise DependencyRegistryError(
                    "training-data record_count must be nonnegative or null"
                )
            stage_ids.append(stage_id)
        if stage_ids != sorted(set(stage_ids)):
            raise DependencyRegistryError("training-data stages must be unique and sorted")

        task = _mapping(
            record["task_provenance"],
            context=f"candidate_model_units[{index}].task_provenance",
        )
        task_fields = {
            "task_manifest_sha256",
            "generator_artifact_sha256",
            "template_set_sha256",
            "source_record_sha256",
        }
        _exact_keys(task, task_fields, context=f"candidate {model_id} task provenance")
        task_source = _claim_source(
            task["source_record_sha256"],
            context=f"candidate {model_id} task source",
            source_records=source_records,
            mandatory_sources=mandatory_sources,
            allowed_kinds={"task_manifest"},
            required_statuses=({"complete_content_addressed"} if status == "eligible" else None),
        )
        if task_source["content_sha256"] != task["task_manifest_sha256"]:
            raise DependencyRegistryError("task source does not bind its manifest")
        for field in ("generator_artifact_sha256", "template_set_sha256"):
            _sha256(task[field], context=f"candidate {model_id} task_provenance.{field}")

        if status == "eligible":
            try:
                model = model_by_id[model_id]
            except KeyError as error:
                raise DependencyRegistryError(
                    "eligible candidate is absent from authorization projection"
                ) from error
            if checkpoint["training_run_parent_id"] != model["independent_training_run_id"]:
                raise DependencyRegistryError("candidate training run drifted from projection")
        elif model_id in model_by_id:
            raise DependencyRegistryError("projected model cannot be excluded or unresolved")
        by_id[model_id] = record
        order.append(model_id)
    if order != sorted(order):
        raise DependencyRegistryError("candidate_model_units must be sorted by model_unit_id")
    actual_eligible = tuple(
        model_id for model_id in order if by_id[model_id]["enrollment_status"] == "eligible"
    )
    if actual_eligible != eligible_ids or set(model_by_id) != set(eligible_ids):
        raise DependencyRegistryError("eligible candidates do not equal the nine projected units")
    return by_id


def _validate_data_relation(value: Any, *, context: str) -> None:
    relation = _mapping(value, context=context)
    expected = {
        "result",
        "declared_scope",
        "identity_scheme_id",
        "left_count",
        "right_count",
        "intersection_count",
        "left_overlap_fraction",
        "right_overlap_fraction",
        "intentional_common_exposure",
        "evidence_record_sha256",
    }
    _exact_keys(relation, expected, context=context)
    _text(relation["declared_scope"], context=f"{context}.declared_scope")
    _text(relation["identity_scheme_id"], context=f"{context}.identity_scheme_id")
    result = relation["result"]
    if result in {"unknown", "not_comparable"}:
        nullable = (
            "left_count",
            "right_count",
            "intersection_count",
            "left_overlap_fraction",
            "right_overlap_fraction",
            "intentional_common_exposure",
        )
        if any(relation[field] is not None for field in nullable):
            raise DependencyRegistryError(f"{context} unknown relation must not invent counts")
        return
    if result not in {"exact_overlap", "no_exact_overlap_within_declared_scope"}:
        raise DependencyRegistryError(f"{context}.result is not recognized")
    counts = [relation[field] for field in ("left_count", "right_count", "intersection_count")]
    if any(not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in counts):
        raise DependencyRegistryError(f"{context} overlap counts must be nonnegative integers")
    left, right, intersection = counts
    if intersection > min(left, right):
        raise DependencyRegistryError(f"{context} intersection exceeds a source count")
    expected_left = 0.0 if left == 0 else intersection / left
    expected_right = 0.0 if right == 0 else intersection / right
    for field, expected_fraction in (
        ("left_overlap_fraction", expected_left),
        ("right_overlap_fraction", expected_right),
    ):
        observed = relation[field]
        if not isinstance(observed, (int, float)) or isinstance(observed, bool):
            raise DependencyRegistryError(f"{context}.{field} must be numeric")
        if not math.isclose(float(observed), expected_fraction, abs_tol=1e-12):
            raise DependencyRegistryError(f"{context}.{field} does not close the counts")
    if result == "exact_overlap" and intersection == 0:
        raise DependencyRegistryError(f"{context} exact overlap requires a nonzero intersection")
    if result == "no_exact_overlap_within_declared_scope" and intersection != 0:
        raise DependencyRegistryError(f"{context} no-overlap claim has a nonzero intersection")
    if not isinstance(relation["intentional_common_exposure"], bool):
        raise DependencyRegistryError(f"{context}.intentional_common_exposure must be boolean")


def _matching_training_stage(
    candidate: Mapping[str, Any],
    *,
    declared_scope: str,
    identity_scheme_id: str,
    context: str,
) -> Mapping[str, Any]:
    matches = [
        _mapping(stage, context=f"{context}.training_data_stage")
        for stage in candidate["training_data_stages"]
        if stage["scope"] == declared_scope
        and stage["record_identity_scheme_id"] == identity_scheme_id
    ]
    if len(matches) != 1:
        raise DependencyRegistryError(
            f"{context} needs exactly one candidate stage for the declared scope and identity"
        )
    return matches[0]


def _validate_pairs(
    value: Any,
    *,
    eligible_ids: tuple[str, ...],
    candidates: Mapping[str, Mapping[str, Any]],
    cluster_by_unit: Mapping[str, str],
    ancestry_inventory_sha256: str,
    source_records: Mapping[str, Mapping[str, Any]],
    mandatory_sources: set[str],
) -> None:
    records = _sequence(value, context="pairwise_relatedness")
    expected_pairs = tuple(combinations(eligible_ids, 2))
    expected_pair_set = set(expected_pairs)
    if len(records) != len(expected_pairs):
        raise DependencyRegistryError("pairwise_relatedness must enumerate all 36 pairs")
    observed_pairs: list[tuple[str, str]] = []
    for index, raw in enumerate(records):
        record = _mapping(raw, context=f"pairwise_relatedness[{index}]")
        _exact_keys(record, PAIR_FIELDS, context=f"pairwise_relatedness[{index}]")
        pair = (
            _text(record["left_model_unit_id"], context=f"pair[{index}].left"),
            _text(record["right_model_unit_id"], context=f"pair[{index}].right"),
        )
        if pair[0] >= pair[1]:
            raise DependencyRegistryError("pair ids must be strictly lexicographic")
        if pair not in expected_pair_set:
            raise DependencyRegistryError("pair references a non-eligible model unit")
        observed_pairs.append(pair)
        same_cluster = cluster_by_unit[pair[0]] == cluster_by_unit[pair[1]]

        learned = _mapping(record["learned_state"], context=f"pair[{index}].learned_state")
        _exact_keys(
            learned,
            {"path_status", "relationship_kinds", "evidence_record_sha256"},
            context=f"pair[{index}].learned_state",
        )
        expected_path = "path_present" if same_cluster else "no_path_in_declared_inventory"
        if learned["path_status"] != expected_path:
            raise DependencyRegistryError("pair learned-state status disagrees with frozen graph")
        kinds = _sorted_unique_texts(
            learned["relationship_kinds"],
            context=f"pair[{index}].learned_state.relationship_kinds",
        )
        if same_cluster and not kinds:
            raise DependencyRegistryError("same-cluster pair needs a declared relationship kind")
        if not same_cluster and kinds:
            raise DependencyRegistryError("cross-cluster pair cannot claim a learned-state path")
        evidence = _sorted_unique_texts(
            learned["evidence_record_sha256"],
            context=f"pair[{index}].learned_state.evidence",
            minimum=1,
        )
        for evidence_index, digest in enumerate(evidence):
            ancestry_source = _claim_source(
                digest,
                context=f"pair[{index}].learned_state.evidence[{evidence_index}]",
                source_records=source_records,
                mandatory_sources=mandatory_sources,
                allowed_kinds={"ancestry_manifest"},
                required_statuses={"complete_content_addressed"},
            )
            if ancestry_source["content_sha256"] != ancestry_inventory_sha256:
                raise DependencyRegistryError(
                    "learned-state evidence does not bind the projected ancestry inventory"
                )

        randomness = _mapping(
            record["training_randomness"], context=f"pair[{index}].training_randomness"
        )
        _exact_keys(
            randomness,
            {"relation", "same_initialization_state", "evidence_record_sha256"},
            context=f"pair[{index}].training_randomness",
        )
        left_randomness = candidates[pair[0]]["training_randomness"]
        right_randomness = candidates[pair[1]]["training_randomness"]
        unavailable = "unavailable" in {
            left_randomness["evidence_status"],
            right_randomness["evidence_status"],
        }
        if unavailable:
            expected_relation = "unknown"
        elif left_randomness["rng_manifest_sha256"] == right_randomness["rng_manifest_sha256"]:
            expected_relation = "same_rng_manifest"
        else:
            expected_relation = "different_rng_manifest"
        if randomness["relation"] != expected_relation:
            raise DependencyRegistryError(
                "pair RNG relation was not derived from candidate evidence"
            )
        same_state = (
            left_randomness["initialization_state_artifact_sha256"]
            == right_randomness["initialization_state_artifact_sha256"]
        )
        if randomness["same_initialization_state"] is not same_state:
            raise DependencyRegistryError("pair initialization-state relation was forged")
        if same_state and not same_cluster:
            raise DependencyRegistryError(
                "identical initialization state cannot cross dependency clusters"
            )
        _claim_source(
            randomness["evidence_record_sha256"],
            context=f"pair[{index}].training_randomness.evidence",
            source_records=source_records,
            mandatory_sources=mandatory_sources,
            allowed_kinds={"rng_manifest"},
            required_statuses={"complete_content_addressed"},
        )

        data = _mapping(record["training_data"], context=f"pair[{index}].training_data")
        _validate_data_relation(data, context=f"pair[{index}].training_data")
        data_source = _claim_source(
            data["evidence_record_sha256"],
            context=f"pair[{index}].training_data.evidence",
            source_records=source_records,
            mandatory_sources=mandatory_sources,
            allowed_kinds={"overlap_scan_manifest"},
            required_statuses=(
                {"complete_content_addressed"}
                if data["result"] in {"exact_overlap", "no_exact_overlap_within_declared_scope"}
                else None
            ),
        )
        if data["result"] == "no_exact_overlap_within_declared_scope" and (
            data_source["evidence_status"] != "complete_content_addressed"
        ):
            raise DependencyRegistryError(
                "no-overlap claim requires a complete content-addressed scan"
            )
        if data["result"] in {"exact_overlap", "no_exact_overlap_within_declared_scope"}:
            left_stage = _matching_training_stage(
                candidates[pair[0]],
                declared_scope=data["declared_scope"],
                identity_scheme_id=data["identity_scheme_id"],
                context=f"pair[{index}].left",
            )
            right_stage = _matching_training_stage(
                candidates[pair[1]],
                declared_scope=data["declared_scope"],
                identity_scheme_id=data["identity_scheme_id"],
                context=f"pair[{index}].right",
            )
            if (
                left_stage["manifest_status"] != "complete_for_declared_stage"
                or right_stage["manifest_status"] != "complete_for_declared_stage"
            ):
                raise DependencyRegistryError(
                    "concrete pair overlap requires complete candidate stage manifests"
                )
            if (
                data["left_count"] != left_stage["record_count"]
                or data["right_count"] != right_stage["record_count"]
            ):
                raise DependencyRegistryError(
                    "pair overlap counts do not equal candidate stage record counts"
                )
            if left_stage["manifest_sha256"] == right_stage["manifest_sha256"]:
                if left_stage["record_count"] != right_stage["record_count"]:
                    raise DependencyRegistryError(
                        "identical training-data manifests cannot declare different counts"
                    )
                shared_count = left_stage["record_count"]
                expected_result = (
                    "exact_overlap"
                    if shared_count and shared_count > 0
                    else "no_exact_overlap_within_declared_scope"
                )
                expected_common = bool(shared_count)
                if (
                    data["result"] != expected_result
                    or data["intersection_count"] != shared_count
                    or data["intentional_common_exposure"] is not expected_common
                ):
                    raise DependencyRegistryError(
                        "pair overlap contradicts identical candidate training-data manifests"
                    )

        task = _mapping(record["task_relation"], context=f"pair[{index}].task_relation")
        _exact_keys(task, {"result", "evidence_record_sha256"}, context=f"pair[{index}].task")
        if task["result"] not in {
            "same_frozen_task",
            "different_task",
            "partial_overlap",
            "unknown",
        }:
            raise DependencyRegistryError("task relation is not recognized")
        task_source = _claim_source(
            task["evidence_record_sha256"],
            context=f"pair[{index}].task.evidence",
            source_records=source_records,
            mandatory_sources=mandatory_sources,
            allowed_kinds={"task_manifest"},
            required_statuses=(
                {"complete_content_addressed"} if task["result"] != "unknown" else None
            ),
        )
        left_task = candidates[pair[0]]["task_provenance"]
        right_task = candidates[pair[1]]["task_provenance"]
        task_identity_fields = (
            "task_manifest_sha256",
            "generator_artifact_sha256",
            "template_set_sha256",
        )
        same_task_identity = all(
            left_task[field] == right_task[field] for field in task_identity_fields
        )
        if task["result"] == "same_frozen_task":
            if not same_task_identity:
                raise DependencyRegistryError(
                    "same-task pair claim contradicts candidate task manifests"
                )
            if task_source["content_sha256"] != left_task["task_manifest_sha256"]:
                raise DependencyRegistryError(
                    "same-task evidence does not bind the shared candidate task manifest"
                )
        elif task["result"] == "different_task" and same_task_identity:
            raise DependencyRegistryError(
                "different-task pair claim contradicts identical candidate task manifests"
            )
        expected_handling = "same_dependency_cluster" if same_cluster else "shared_design_nuisance"
        if record["handling"] != expected_handling:
            raise DependencyRegistryError(
                "pair handling may expose common influence but cannot split the frozen graph"
            )
    if tuple(observed_pairs) != expected_pairs:
        raise DependencyRegistryError("pairwise_relatedness is incomplete or not sorted")


def _validate_exposure_assessments(
    value: Any,
    *,
    eligible_ids: tuple[str, ...],
    candidates: Mapping[str, Mapping[str, Any]],
    source_records: Mapping[str, Mapping[str, Any]],
    mandatory_sources: set[str],
) -> None:
    records = _sequence(value, context="evaluation_exposure_assessments")
    if len(records) != 9:
        raise DependencyRegistryError("exposure assessments must cover exactly nine eligible units")
    order: list[str] = []
    for index, raw in enumerate(records):
        record = _mapping(raw, context=f"evaluation_exposure_assessments[{index}]")
        _exact_keys(record, EXPOSURE_FIELDS, context=f"exposure[{index}]")
        model_id = _text(record["model_unit_id"], context=f"exposure[{index}].model_unit_id")
        order.append(model_id)
        try:
            candidate = candidates[model_id]
        except KeyError as error:
            raise DependencyRegistryError(
                "exposure assessment references a non-candidate model unit"
            ) from error
        decision = record["eligibility_decision"]
        _claim_source(
            record["evidence_record_sha256"],
            context=f"exposure[{index}].evidence",
            source_records=source_records,
            mandatory_sources=mandatory_sources,
            allowed_kinds={"evaluation_exposure_scan_manifest"},
            required_statuses=({"complete_content_addressed"} if decision == "eligible" else None),
        )
        reasons = _sorted_unique_texts(record["reason_ids"], context=f"exposure[{index}].reasons")
        if record["exact_live_prompt_overlap"] not in {
            "overlap_present",
            "no_overlap_within_complete_manifest",
            "unknown",
        }:
            raise DependencyRegistryError("exact prompt-overlap status is not recognized")
        if record["frozen_generator_artifact_exposure"] not in {
            "present",
            "absent_within_declared_scope",
            "unknown",
        } or record["frozen_template_exposure"] not in {
            "present",
            "absent_within_declared_scope",
            "unknown",
        }:
            raise DependencyRegistryError("frozen artifact exposure status is not recognized")
        if record["abstract_task_family_exposure"] not in {
            "present",
            "not_detected",
            "unknown",
        }:
            raise DependencyRegistryError("abstract task exposure status is not recognized")
        if record["checkpoint_precedes_design_freeze"] not in {True, False, None}:
            raise DependencyRegistryError("checkpoint/design-freeze order must be boolean or null")
        checkpoint_created = _timestamp(
            candidate["checkpoint_provenance"]["created_at"],
            context=f"exposure[{index}] candidate checkpoint.created_at",
        )
        derived_precedes_freeze = checkpoint_created < DESIGN_FREEZE_BOUNDARY
        if record["checkpoint_precedes_design_freeze"] is not derived_precedes_freeze:
            raise DependencyRegistryError(
                "checkpoint_precedes_design_freeze contradicts checkpoint chronology"
            )
        blockers = (
            record["exact_live_prompt_overlap"] != "no_overlap_within_complete_manifest"
            or record["frozen_generator_artifact_exposure"] != "absent_within_declared_scope"
            or record["frozen_template_exposure"] != "absent_within_declared_scope"
            or record["checkpoint_precedes_design_freeze"] is not True
        )
        expected_decision = "unresolved" if blockers else "eligible"
        if record["exact_live_prompt_overlap"] == "overlap_present" or (
            record["frozen_generator_artifact_exposure"] == "present"
            or record["frozen_template_exposure"] == "present"
        ):
            expected_decision = "excluded"
        if decision != expected_decision:
            raise DependencyRegistryError("exposure eligibility was not derived fail-closed")
        if (decision == "eligible" and reasons) or (decision != "eligible" and not reasons):
            raise DependencyRegistryError("exposure reasons disagree with eligibility")
        if candidate["enrollment_status"] != decision:
            raise DependencyRegistryError("exposure decision disagrees with candidate enrollment")
    if tuple(order) != eligible_ids:
        raise DependencyRegistryError("exposure assessments must match eligible ids in order")


def _resolve_pointer(projection: Mapping[str, Any], pointer: str) -> Any:
    if not pointer.startswith("/"):
        raise DependencyRegistryError("authorization JSON pointer must begin with /")
    value: Any = projection
    for raw_part in pointer[1:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(value, Mapping):
            if part not in value:
                raise DependencyRegistryError(f"authorization pointer segment {part!r} is absent")
            value = value[part]
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            try:
                index = int(part)
            except ValueError as error:
                raise DependencyRegistryError("array pointer segment must be an integer") from error
            try:
                value = value[index]
            except IndexError as error:
                raise DependencyRegistryError(
                    "authorization pointer index is out of range"
                ) from error
        else:
            raise DependencyRegistryError("authorization pointer descends through a scalar")
    return value


def _validate_bindings(
    value: Any,
    *,
    projection: Mapping[str, Any],
    source_records: Mapping[str, Mapping[str, Any]],
    mandatory_sources: set[str],
) -> None:
    records = _sequence(value, context="binding_map")
    if not records:
        raise DependencyRegistryError("binding_map must not be empty")
    assertion_ids: list[str] = []
    mapped_sources: set[str] = set()
    for index, raw in enumerate(records):
        record = _mapping(raw, context=f"binding_map[{index}]")
        _exact_keys(record, BINDING_FIELDS, context=f"binding_map[{index}]")
        assertion_id = _text(record["assertion_id"], context=f"binding_map[{index}].id")
        source_hash = _sha256(
            record["source_record_sha256"], context=f"binding_map[{index}].source"
        )
        source = _source(
            source_hash,
            context=f"binding_map[{index}].source",
            source_records=source_records,
        )
        status = record["binding_status"]
        pointer = record["authorization_json_pointer"]
        material = record["material_for_eligibility"]
        required_material = source_hash in mandatory_sources
        if material is not required_material:
            raise DependencyRegistryError(
                "binding materiality must be derived from actual claim and eligibility use"
            )
        if status == "authorization_projection_bound":
            if not isinstance(pointer, str) or not pointer:
                raise DependencyRegistryError(
                    "projection-bound material needs an authorization pointer"
                )
            resolved = _resolve_pointer(projection, pointer)
            if resolved not in {source_hash, source["content_sha256"]}:
                raise DependencyRegistryError(
                    "authorization pointer does not carry the source record or content hash"
                )
            if not required_material:
                raise DependencyRegistryError(
                    "unused source cannot be classified as projection-bound material"
                )
        elif status == "registry_body_bound":
            if pointer is not None or not required_material:
                raise DependencyRegistryError(
                    "registry-body-bound evidence must be used material with no direct pointer"
                )
        elif status == "supplementary_non_authoritative":
            if pointer is not None or required_material:
                raise DependencyRegistryError(
                    "supplementary evidence cannot be used material or claim an authorization pointer"
                )
        else:
            raise DependencyRegistryError("binding status is not recognized")
        if not isinstance(material, bool):
            raise DependencyRegistryError("material_for_eligibility must be boolean")
        if source_hash in mapped_sources:
            raise DependencyRegistryError("each source record needs exactly one binding row")
        assertion_ids.append(assertion_id)
        mapped_sources.add(source_hash)
    if assertion_ids != sorted(set(assertion_ids)):
        raise DependencyRegistryError("binding_map must be unique and sorted by assertion_id")
    if mapped_sources != set(source_records):
        raise DependencyRegistryError(
            "every source record must be classified as bound or supplementary"
        )


def validate_dependency_cluster_registry(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one evidence-closed registry without authorizing any model call."""

    registry = _mapping(value, context="dependency cluster registry")
    _exact_keys(registry, TOP_LEVEL_FIELDS, context="dependency cluster registry")
    if (
        registry["schema_version"] != SCHEMA_VERSION
        or registry["contract_id"] != CONTRACT_ID
        or registry["role"] != ROLE
        or registry["status"] != STATUS
    ):
        raise DependencyRegistryError("registry identity or status is not frozen")
    _text(registry["registry_id"], context="registry_id")
    created_at = _timestamp(registry["created_at"], context="created_at")
    evidence_cutoff = _timestamp(registry["evidence_cutoff_at"], context="evidence_cutoff_at")
    if evidence_cutoff > created_at:
        raise DependencyRegistryError("evidence cutoff must not postdate registry creation")
    _validate_parent(registry["parent"])
    _validate_exposure(registry["outcome_exposure"])
    _validate_epistemic_boundary(registry["epistemic_boundary"])
    source_records = _validate_source_records(
        registry["source_records"], evidence_cutoff=evidence_cutoff
    )
    mandatory_sources: set[str] = set()
    projection = _mapping(registry["authorization_projection"], context="authorization_projection")
    models, cluster_by_unit = _validate_projection(projection)
    eligible_ids = _sorted_unique_texts(
        registry["eligible_model_unit_ids"],
        context="eligible_model_unit_ids",
        exact=9,
    )
    candidates = _validate_candidate_units(
        registry["candidate_model_units"],
        eligible_ids=eligible_ids,
        models=models,
        source_records=source_records,
        mandatory_sources=mandatory_sources,
        evidence_cutoff=evidence_cutoff,
    )
    _validate_pairs(
        registry["pairwise_relatedness"],
        eligible_ids=eligible_ids,
        candidates=candidates,
        cluster_by_unit=cluster_by_unit,
        ancestry_inventory_sha256=projection["learned_state_ancestry"]["inventory_sha256"],
        source_records=source_records,
        mandatory_sources=mandatory_sources,
    )
    _validate_exposure_assessments(
        registry["evaluation_exposure_assessments"],
        eligible_ids=eligible_ids,
        candidates=candidates,
        source_records=source_records,
        mandatory_sources=mandatory_sources,
    )
    _validate_bindings(
        registry["binding_map"],
        projection=projection,
        source_records=source_records,
        mandatory_sources=mandatory_sources,
    )
    limitations = _sorted_unique_texts(
        registry["limitations"], context="limitations", minimum=len(REQUIRED_LIMITATIONS)
    )
    if not REQUIRED_LIMITATIONS.issubset(limitations):
        raise DependencyRegistryError("registry omits a required epistemic limitation")
    expected_hash = canonical_artifact_sha256(
        {field: registry[field] for field in TOP_LEVEL_FIELDS - {"registry_body_sha256"}}
    )
    if registry["registry_body_sha256"] != expected_hash:
        raise DependencyRegistryError("registry body is not self-addressed")
    return {
        "ok": True,
        "registry_id": registry["registry_id"],
        "registry_body_sha256": expected_hash,
        "eligible_model_unit_count": len(eligible_ids),
        "dependency_cluster_count": len(set(cluster_by_unit.values())),
        "effective_n": len(set(cluster_by_unit.values())),
        "independence_certified": False,
        "material_source_count": len(mandatory_sources),
        "model_calls_authorized": False,
    }


def _validate_registry_projection_binding(
    registry_value: Mapping[str, Any], authorization_value: Mapping[str, Any]
) -> None:
    validate_dependency_cluster_registry(registry_value)
    registry = _mapping(registry_value, context="dependency cluster registry")
    authorization = _mapping(authorization_value, context="discovery authorization")
    if authorization.get("status") != "authorized":
        raise DependencyRegistryError("binding requires a concrete authorized artifact")
    projection = _mapping(registry["authorization_projection"], context="authorization_projection")
    for field in AUTHORIZATION_PROJECTION_FIELDS:
        if authorization.get(field) != projection[field]:
            raise DependencyRegistryError(
                f"discovery authorization drifted from registry projection field={field}"
            )
    authorized_at = _timestamp(authorization.get("authorized_at"), context="authorized_at")
    evidence_cutoff = _timestamp(registry["evidence_cutoff_at"], context="evidence_cutoff_at")
    if authorized_at < evidence_cutoff:
        raise DependencyRegistryError("authorization predates the registry evidence cutoff")


def validate_registry_authorization_projection(
    registry_value: Mapping[str, Any], authorization_value: Mapping[str, Any]
) -> None:
    """Check exact projection equality without claiming the final gate passed.

    This is an authoring check.  The signed gate receipt and frozen discovery
    readiness validation are still mandatory before any forward pass.
    """

    _validate_registry_projection_binding(registry_value, authorization_value)


def _authority_secret_commitment(
    authority_secret: bytes, *, authorization: Mapping[str, Any]
) -> str:
    if not isinstance(authority_secret, bytes) or len(authority_secret) < 32:
        raise DependencyRegistryError("authority_secret must contain at least 256 bits")
    live_seed = _mapping(
        authorization.get("live_seed_commitment"),
        context="authorization.live_seed_commitment",
    )
    commitment = _sha256(
        live_seed.get("authority_secret_commitment_sha256"),
        context="authorization authority-secret commitment",
    )
    if hashlib.sha256(authority_secret).hexdigest() != commitment:
        raise DependencyRegistryError("authority secret does not open authorization commitment")
    return commitment


def _gate_receipt_unsigned_body(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        field: receipt[field]
        for field in GATE_RECEIPT_FIELDS - {"authority_hmac_sha256", "receipt_sha256"}
    }


def _gate_receipt_hmac(unsigned_body: Mapping[str, Any], *, authority_secret: bytes) -> str:
    payload_hash = canonical_artifact_sha256(unsigned_body).encode("ascii")
    return hmac.new(
        authority_secret,
        GATE_RECEIPT_HMAC_DOMAIN + payload_hash,
        hashlib.sha256,
    ).hexdigest()


def build_registry_authorization_gate_receipt(
    registry_value: Mapping[str, Any],
    authorization_value: Mapping[str, Any],
    *,
    authority_secret: bytes,
    issued_at: str,
) -> dict[str, Any]:
    """Bind the complete registry body to one concrete authorization.

    The frozen authorization cannot acquire a new registry field without
    mutating the design contract.  This authority-HMAC receipt supplies the
    transitive, content-addressed edge instead.  It is necessary but not
    sufficient for a forward pass; frozen discovery readiness remains a
    separate required gate.
    """

    _validate_registry_projection_binding(registry_value, authorization_value)
    registry = _mapping(registry_value, context="dependency cluster registry")
    authorization = _mapping(authorization_value, context="discovery authorization")
    commitment = _authority_secret_commitment(
        authority_secret,
        authorization=authorization,
    )
    issued = _timestamp(issued_at, context="gate receipt issued_at")
    authorized = _timestamp(authorization["authorized_at"], context="authorized_at")
    registry_created = _timestamp(registry["created_at"], context="registry.created_at")
    if issued < authorized or issued < registry_created:
        raise DependencyRegistryError(
            "gate receipt must not predate the registry or concrete authorization"
        )
    projection = _mapping(registry["authorization_projection"], context="authorization_projection")
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "receipt_type": GATE_RECEIPT_TYPE,
        "status": GATE_RECEIPT_STATUS,
        "registry_id": registry["registry_id"],
        "registry_body_sha256": registry["registry_body_sha256"],
        "authorization_id": authorization["discovery_authorization_id"],
        "authorization_sha256": canonical_artifact_sha256(authorization),
        "authorization_projection_sha256": projection["projection_sha256"],
        "authorized_at": authorization["authorized_at"],
        "issued_at": issued_at,
        "authority_secret_commitment_sha256": commitment,
    }
    receipt["authority_hmac_sha256"] = _gate_receipt_hmac(
        _gate_receipt_unsigned_body(receipt),
        authority_secret=authority_secret,
    )
    receipt["receipt_sha256"] = canonical_artifact_sha256(receipt)
    return receipt


def validate_registry_authorization_gate_receipt(
    registry_value: Mapping[str, Any],
    authorization_value: Mapping[str, Any],
    receipt_value: Mapping[str, Any],
    *,
    authority_secret: bytes,
) -> None:
    """Validate the full evidence-packet-to-authorization gate receipt."""

    _validate_registry_projection_binding(registry_value, authorization_value)
    registry = _mapping(registry_value, context="dependency cluster registry")
    authorization = _mapping(authorization_value, context="discovery authorization")
    receipt = _mapping(receipt_value, context="registry authorization gate receipt")
    _exact_keys(receipt, GATE_RECEIPT_FIELDS, context="registry authorization gate receipt")
    if (
        receipt["schema_version"] != SCHEMA_VERSION
        or receipt["receipt_type"] != GATE_RECEIPT_TYPE
        or receipt["status"] != GATE_RECEIPT_STATUS
    ):
        raise DependencyRegistryError("gate receipt identity or status is not frozen")
    commitment = _authority_secret_commitment(
        authority_secret,
        authorization=authorization,
    )
    projection = _mapping(registry["authorization_projection"], context="authorization_projection")
    expected = {
        "registry_id": registry["registry_id"],
        "registry_body_sha256": registry["registry_body_sha256"],
        "authorization_id": authorization["discovery_authorization_id"],
        "authorization_sha256": canonical_artifact_sha256(authorization),
        "authorization_projection_sha256": projection["projection_sha256"],
        "authorized_at": authorization["authorized_at"],
        "authority_secret_commitment_sha256": commitment,
    }
    for field, expected_value in expected.items():
        if receipt[field] != expected_value:
            raise DependencyRegistryError(f"gate receipt drifted at field={field}")
    issued = _timestamp(receipt["issued_at"], context="gate receipt issued_at")
    authorized = _timestamp(receipt["authorized_at"], context="gate receipt authorized_at")
    registry_created = _timestamp(registry["created_at"], context="registry.created_at")
    if issued < authorized or issued < registry_created:
        raise DependencyRegistryError("gate receipt predates its bound parent")
    observed_hmac = _sha256(
        receipt["authority_hmac_sha256"],
        context="gate receipt authority_hmac_sha256",
    )
    expected_hmac = _gate_receipt_hmac(
        _gate_receipt_unsigned_body(receipt),
        authority_secret=authority_secret,
    )
    if not hmac.compare_digest(observed_hmac, expected_hmac):
        raise DependencyRegistryError("gate receipt authority HMAC is invalid")
    observed_receipt_hash = _sha256(
        receipt["receipt_sha256"],
        context="gate receipt receipt_sha256",
    )
    expected_receipt_hash = canonical_artifact_sha256(
        {field: receipt[field] for field in GATE_RECEIPT_FIELDS - {"receipt_sha256"}}
    )
    if observed_receipt_hash != expected_receipt_hash:
        raise DependencyRegistryError("gate receipt is not self-addressed")


def validate_registry_authorization_binding(
    registry_value: Mapping[str, Any],
    authorization_value: Mapping[str, Any],
    *,
    gate_receipt: Mapping[str, Any],
    authority_secret: bytes,
) -> None:
    """Require projection equality plus the transitive signed gate receipt.

    The caller must additionally run frozen ``validate_discovery_readiness``
    with trusted parent hashes before the first forward pass.
    """

    validate_registry_authorization_gate_receipt(
        registry_value,
        authorization_value,
        gate_receipt,
        authority_secret=authority_secret,
    )
