"""Capability-conscious contracts for blind, output-only evaluation.

This module deliberately does not pretend that hashes or phase ordering create
blindness.  The evaluation authority must keep labels and held-out challenges
outside the auditor's filesystem capabilities until after the auditor commits
its predictions and estimator artifacts.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import stat
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

from latent_trace_tomography.prospective import (
    BASELINE_PRIORITY,
    CHALLENGE_SLOT_FIELDS,
    GATE_NUMERIC_TOLERANCE,
    PRIMARY_GATE_RELATIVE_REDUCTION,
    PRIMARY_METRIC,
    SECONDARY_METRIC,
    build_weak_observation_evidence,
    derive_relational_challenge_outcome,
    evaluate_verified_candidate_gate,
    validate_challenge_predictions,
    validate_challenge_scoring_key,
    validate_challenge_slot_inventory,
)
from latent_trace_tomography.oss_design import build_oss_design, derive_live_content_seeds
from latent_trace_tomography.split import partition_content_seeds


CONTRACT_VERSION = "0.1.0"
BLIND_BUNDLE_CONTRACT = "ltt.blind_bundle_manifest"
EVALUATION_COMMITMENT_CONTRACT = "ltt.evaluation_commitment"
COMMITMENT_CLOSURE_CONTRACT = "ltt.evaluation_commitment_closure"
COMMITTED_GATE_RESULT_CONTRACT = "ltt.committed_candidate_fold_score"
SEALED_EVALUATION_AUTHORIZATION_CONTRACT = "ltt.sealed_evaluation_authorization"
SEALED_EVALUATION_PAYLOAD_CONTRACT = "ltt.sealed_evaluation_payload"
AUTHORITY_COMMITMENT_SCHEME = "sha256_domain_separated_u64be_length_prefixed_v1"
AUTHORITY_COMMITMENT_FRAMING = (
    "u64be_len(domain)||domain||u64be_len(nonce)||nonce||u64be_len(payload)||payload"
)
AUTHORITY_COMMITMENT_MIN_NONCE_BYTES = 32
AUTHORITY_COMMITMENT_CONFORMANCE_VECTOR = {
    "domain_hex": "6c74742d6576616c756174696f6e2d6b65792d7631",
    "nonce_hex": ("000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"),
    "payload_hex": "7b226b6579223a22666978747572652d7631227d0a",
    "sha256": "1bf349c05ab1bb6535ceed0d147f4391db1f1dd7fb39c0963fa373025f4ef6ee",
}
PAIRING_TOKEN_SCHEME = "hmac_sha256_128bit_domain_separated_v1"
PAIRING_TOKEN_DOMAINS = (
    "target",
    "cluster",
    "fold",
    "case",
    "projection",
    "replicate",
    "challenge_slot",
)
PAIRING_TOKEN_MATERIAL_CONTRACT = {
    "target": (
        "canonical_json_utf8(execution_lock.model_registry record; sorted keys; "
        "compact separators; ensure_ascii=false)"
    ),
    "cluster": (
        "canonical_json_utf8({private_fold_id, execution_lock.dependency_clusters "
        "record}; sorted keys; compact separators; ensure_ascii=false); serialized as "
        "dependency- plus the first 64 HMAC bits for scoring-schema compatibility"
    ),
    "fold": "utf8(private fold_id)",
    "case": "utf8(generator case_id)",
    "projection": "utf8(OSSProjectionKind.value)",
    "replicate": "uint64be(zero_based_replicate_index)",
    "challenge_slot": "ascii(target_id) || NUL || utf8(challenge_kind)",
}
SEALED_EVALUATION_FOLD_COUNT = 3
HELDOUT_DEPENDENCY_CLUSTER_COUNT = 1
DEVELOPMENT_DEPENDENCY_CLUSTER_COUNT = 2
HELDOUT_TARGET_COUNT = 3
DEVELOPMENT_TARGET_COUNT = 6
TARGET_COUNT = HELDOUT_TARGET_COUNT + DEVELOPMENT_TARGET_COUNT
WEAK_TRIAL_COUNT_PER_TARGET = 320
CHALLENGE_TRIAL_COUNT_PER_TARGET_PER_KIND = 64
CHALLENGE_TRIAL_COUNT_PER_TARGET = 2 * CHALLENGE_TRIAL_COUNT_PER_TARGET_PER_KIND
SEALED_WEAK_TRIAL_COUNT = TARGET_COUNT * WEAK_TRIAL_COUNT_PER_TARGET
SEALED_CHALLENGE_TRIAL_COUNT = TARGET_COUNT * CHALLENGE_TRIAL_COUNT_PER_TARGET
SEALED_FORWARD_PASS_COUNT = SEALED_WEAK_TRIAL_COUNT + SEALED_CHALLENGE_TRIAL_COUNT
HELDOUT_WEAK_OBSERVATION_COUNT = HELDOUT_TARGET_COUNT * WEAK_TRIAL_COUNT_PER_TARGET
HELDOUT_CHALLENGE_TRIAL_COUNT = HELDOUT_TARGET_COUNT * CHALLENGE_TRIAL_COUNT_PER_TARGET
DEVELOPMENT_CHALLENGE_TRIAL_COUNT = DEVELOPMENT_TARGET_COUNT * CHALLENGE_TRIAL_COUNT_PER_TARGET
PRE_AUDITOR_CAUSAL_LABEL_FORWARD_PASSES = 8064
PRE_AUDITOR_BEHAVIOR_FIT_FORWARD_PASSES = 4320
PRE_AUDITOR_SEALED_TEST_FORWARD_PASSES = 4032
PRE_AUDITOR_TOTAL_FORWARD_PASSES = (
    PRE_AUDITOR_CAUSAL_LABEL_FORWARD_PASSES
    + PRE_AUDITOR_BEHAVIOR_FIT_FORWARD_PASSES
    + PRE_AUDITOR_SEALED_TEST_FORWARD_PASSES
)
REQUIRED_AUDITOR_ARTIFACT_ROLES = (
    "abstention_rule",
    "analysis_config",
    "calibration_status",
    "estimator",
    "estimator_source",
    "feature_spec",
)
METHOD_DEFINING_AUDITOR_ARTIFACT_ROLES = (
    "abstention_rule",
    "analysis_config",
    "estimator_source",
    "feature_spec",
)
PRIVATE_EXECUTION_IDENTITY_FIELDS = (
    "provider",
    "provider_id",
    "provider_name",
    "model_provider",
    "model_unit_id",
    "independent_training_run_id",
    "checkpoint_id",
    "lineage_id",
    "architecture_family_id",
    "model_id",
    "model_revision",
    "tokenizer_revision",
    "dependency_cluster_id",
)
REQUIRED_DEVELOPMENT_ARTIFACT_ROLES = (
    "development_scoring_key",
    "development_slot_inventory",
)

# This is the entire auditor-visible row surface.  The identifiers are opaque
# pairing tokens; they must not encode model, provider, family, or causal label.
AUDITOR_OBSERVATION_FIELDS = (
    "target_id",
    "case_id",
    "projection_id",
    "replicate_id",
    "prompt_text",
    "output_text",
)
AUDITOR_PAIRING_FIELDS = AUDITOR_OBSERVATION_FIELDS[:4]

# Kept JSON-serializable so protocol/CLI layers can embed the same contract.
CAPABILITY_SECURITY_CONTRACT: dict[str, Any] = {
    "capability_security_provided_by_this_contract": False,
    "same_process_assurance": "prediction_locked_not_blind",
    "required_boundary": "separate OS principal, container, or user-controlled mount",
    "required_key_state_before_auditor_commitment": "unavailable and unmounted",
    "limitation": (
        "Code hashes and phase ordering are audit evidence; they are not capability security."
    ),
}

# This is an externally asserted operating condition, not proof that the OS,
# container runtime, or storage layer enforced the separation.  The production
# coordinator requires three distinct declaration IDs under one barrier and
# closes every prediction commitment before accepting any reveal bytes.
FOLD_WORKER_CAPABILITY_CONTRACT: dict[str, Any] = {
    "scope": "one_fold_precommit_worker",
    "shared_mounts_before_all_fold_commitments": False,
    "shared_caches_before_all_fold_commitments": False,
    "shared_ipc_before_all_fold_commitments": False,
    "physical_attestation_provided": False,
    "limitation": (
        "The capability ID and declaration are audit evidence supplied by the "
        "evaluation authority; they are not physical isolation attestation."
    ),
}

OUTPUT_RUNTIME_EVIDENCE_BOUNDARY: Mapping[str, Any] = MappingProxyType(
    {
        "validated_evidence": (
            "regenerated_D_sealed_prompt_inventory",
            "raw_prompt_and_output_content_hashes",
            "relational_outcomes_derived_from_raw_outputs",
        ),
        "completion_record_sha256_role": "authority_supplied_pointer_only",
        "runtime_attestation_provided": False,
        "limitation": (
            "Per-completion locked-model/runtime provenance and physical forward execution "
            "are not attested without inline typed completion records and an external "
            "runtime attestation boundary."
        ),
    }
)

_HEX_256 = re.compile(r"^[0-9a-f]{64}$")
_OPAQUE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_PAIRING_TOKEN = re.compile(r"^[0-9a-f]{32}$")
_RFC3339_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_OBSERVATION_PATH = re.compile(r"^(?:observations\.jsonl|observations/part-[0-9]{6}\.jsonl)$")
_CHALLENGE_SLOT_PATH = "challenge_slots.jsonl"


class BlindContractError(ValueError):
    """Raised when a blind-evaluation artifact violates the frozen contract."""


def _require_rfc3339_utc(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or _RFC3339_UTC.fullmatch(value) is None:
        raise BlindContractError(f"{context} must be an RFC 3339 UTC timestamp")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise BlindContractError(f"{context} must be an RFC 3339 UTC timestamp") from error
    return value


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_artifact_sha256(payload: Any) -> str:
    return _sha256_bytes(_canonical_json_bytes(payload))


def _canonical_jsonl_bytes(records: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(_canonical_json_bytes(record) + b"\n" for record in records)


def _assert_no_private_identifier_leak(
    private_identifiers: Iterable[str],
    auditor_surfaces: Mapping[str, bytes],
) -> None:
    """Fail closed if a private execution identity reaches an auditor surface."""

    identifiers = tuple(private_identifiers)
    if any(not isinstance(identifier, str) or not identifier for identifier in identifiers):
        raise BlindContractError("private identifier inventory contains an invalid value")
    if not isinstance(auditor_surfaces, Mapping) or not auditor_surfaces:
        raise BlindContractError("auditor surface inventory must be a non-empty mapping")
    for surface_name, payload in auditor_surfaces.items():
        if not isinstance(surface_name, str) or not surface_name:
            raise BlindContractError("auditor surface name must be non-empty text")
        if not isinstance(payload, bytes):
            raise BlindContractError(f"auditor surface {surface_name} must be bytes")
        for identifier in identifiers:
            if identifier.encode("utf-8") in payload:
                raise BlindContractError(
                    "private execution identity leaked onto the "
                    f"auditor-visible surface={surface_name}"
                )


def _parse_canonical_json_object_bytes(payload: bytes, *, context: str) -> Mapping[str, Any]:
    if not isinstance(payload, bytes) or not payload:
        raise BlindContractError(f"{context} must be non-empty canonical JSON bytes")
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BlindContractError(f"{context} must be canonical UTF-8 JSON") from error
    if not isinstance(decoded, Mapping):
        raise BlindContractError(f"{context} must contain one JSON object")
    if _canonical_json_bytes(decoded) != payload:
        raise BlindContractError(f"{context} is not in frozen canonical JSON form")
    return decoded


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], *, context: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise BlindContractError(f"{context} fields mismatch: missing={missing}, extra={extra}")


def _require_opaque_id(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or not _OPAQUE_ID.fullmatch(value):
        raise BlindContractError(
            f"{context} must be a non-empty opaque ASCII identifier without path separators"
        )
    return value


def _require_pairing_token(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or not _PAIRING_TOKEN.fullmatch(value):
        raise BlindContractError(f"{context} must be an opaque lowercase 128-bit hex token")
    return value


def derive_pairing_token(secret: bytes, *, domain: str, material: bytes) -> str:
    """Derive a pseudonymous 128-bit token with a secret, separated domain."""

    if not isinstance(secret, bytes) or len(secret) < 32:
        raise BlindContractError("pairing-token secret must contain at least 256 random bits")
    if domain not in PAIRING_TOKEN_DOMAINS:
        raise BlindContractError(f"unsupported pairing-token domain={domain!r}")
    if not isinstance(material, bytes) or not material:
        raise BlindContractError("pairing-token material must be non-empty bytes")
    message = b"ltt-pairing-token-v1\x00" + domain.encode("ascii") + b"\x00" + material
    return hmac.new(secret, message, hashlib.sha256).hexdigest()[:32]


def _require_sha256(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or not _HEX_256.fullmatch(value):
        raise BlindContractError(f"{context} must be a lowercase SHA-256 digest")
    return value


def _require_positive_int(value: Any, *, context: str) -> int:
    if type(value) is not int or value < 1:
        raise BlindContractError(f"{context} must be a positive integer")
    return value


def _security_boundary() -> dict[str, Any]:
    return dict(CAPABILITY_SECURITY_CONTRACT)


def _validate_security_boundary(value: Any, *, context: str) -> None:
    if value != CAPABILITY_SECURITY_CONTRACT:
        raise BlindContractError(f"{context} must reproduce the frozen capability warning")


def validate_auditor_observations(
    records: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, str], ...]:
    """Validate and normalize the complete auditor-visible observation surface.

    Extra fields are always rejected, including apparently benign telemetry.
    This prevents provider/model identity, internal labels, logits, timing, and
    usage data from silently entering the primary estimator.
    """

    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    expected = set(AUDITOR_OBSERVATION_FIELDS)
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise BlindContractError(f"observation[{index}] must be an object")
        _require_exact_keys(record, expected, context=f"observation[{index}]")
        row: dict[str, str] = {}
        for field in AUDITOR_PAIRING_FIELDS:
            row[field] = _require_pairing_token(
                record[field], context=f"observation[{index}].{field}"
            )
        prompt = record["prompt_text"]
        output = record["output_text"]
        if not isinstance(prompt, str) or not prompt:
            raise BlindContractError(f"observation[{index}].prompt_text must be non-empty text")
        if not isinstance(output, str):
            raise BlindContractError(f"observation[{index}].output_text must be text")
        row["prompt_text"] = prompt
        row["output_text"] = output
        identity = tuple(row[field] for field in AUDITOR_PAIRING_FIELDS)
        if identity in seen:
            raise BlindContractError(f"duplicate auditor observation identity: {identity!r}")
        seen.add(identity)
        normalized.append(row)
    if not normalized:
        raise BlindContractError("auditor observation set must not be empty")
    return tuple(normalized)


def _parse_jsonl_bytes(payload: bytes, *, context: str) -> list[Any]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise BlindContractError(f"{context} must be UTF-8 JSONL") from error
    if not text:
        raise BlindContractError(f"{context} must not be empty")
    rows: list[Any] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            raise BlindContractError(f"{context}:{line_number} contains a blank JSONL row")
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise BlindContractError(f"{context}:{line_number} is not valid JSON") from error
    return rows


def _read_auditor_jsonl(path: Path, *, context: str) -> tuple[dict[str, str], ...]:
    rows = _parse_jsonl_bytes(path.read_bytes(), context=context)
    return validate_auditor_observations(rows)


def _read_challenge_slot_jsonl(path: Path, *, context: str) -> tuple[dict[str, str], ...]:
    rows = _parse_jsonl_bytes(path.read_bytes(), context=context)
    try:
        return validate_challenge_slot_inventory(rows)
    except ValueError as error:
        raise BlindContractError(f"invalid challenge slot inventory: {error}") from error


def _validate_relative_path(relative_path: Any, *, context: str) -> str:
    if not isinstance(relative_path, str) or not relative_path:
        raise BlindContractError(f"{context} must be a non-empty relative POSIX path")
    if "\\" in relative_path or "\x00" in relative_path:
        raise BlindContractError(f"{context} contains a forbidden path character")
    pure = PurePosixPath(relative_path)
    if pure.is_absolute() or relative_path != pure.as_posix():
        raise BlindContractError(f"{context} must be a normalized relative POSIX path")
    if any(part in {"", ".", ".."} for part in pure.parts):
        raise BlindContractError(f"{context} contains traversal or ambiguous components")
    return relative_path


def _validate_observation_path(relative_path: Any, *, context: str) -> str:
    relative = _validate_relative_path(relative_path, context=context)
    if not _OBSERVATION_PATH.fullmatch(relative):
        raise BlindContractError(
            f"{context} must be observations.jsonl or observations/part-NNNNNN.jsonl"
        )
    return relative


def _validate_challenge_slot_path(relative_path: Any, *, context: str) -> str:
    relative = _validate_relative_path(relative_path, context=context)
    if relative != _CHALLENGE_SLOT_PATH:
        raise BlindContractError(f"{context} must be {_CHALLENGE_SLOT_PATH}")
    return relative


def _safe_regular_file(root: Path, relative_path: Any, *, context: str) -> tuple[str, Path]:
    relative = _validate_relative_path(relative_path, context=context)
    root_path = Path(root)
    if root_path.is_symlink():
        raise BlindContractError(f"{context}: artifact root must not be a symlink")
    try:
        resolved_root = root_path.resolve(strict=True)
    except FileNotFoundError as error:
        raise BlindContractError(f"{context}: artifact root does not exist") from error
    if not resolved_root.is_dir():
        raise BlindContractError(f"{context}: artifact root is not a directory")

    current = resolved_root
    for component in PurePosixPath(relative).parts:
        current = current / component
        if current.is_symlink():
            raise BlindContractError(f"{context}: symlink components are forbidden: {relative}")
    try:
        resolved_file = current.resolve(strict=True)
        resolved_file.relative_to(resolved_root)
        mode = resolved_file.stat().st_mode
    except (FileNotFoundError, ValueError) as error:
        raise BlindContractError(f"{context}: unsafe or missing artifact: {relative}") from error
    if not stat.S_ISREG(mode):
        raise BlindContractError(f"{context}: artifact is not a regular file: {relative}")
    return relative, resolved_file


def _basic_file_entry(root: Path, relative_path: str, *, context: str) -> dict[str, Any]:
    relative, path = _safe_regular_file(root, relative_path, context=context)
    return {
        "path": relative,
        "bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
    }


def _self_address(payload: Mapping[str, Any], address_field: str) -> str:
    body = dict(payload)
    body.pop(address_field, None)
    return _sha256_bytes(_canonical_json_bytes(body))


def build_blind_bundle_manifest(
    bundle_root: Path,
    *,
    observation_paths: Sequence[str],
    challenge_slot_path: str = _CHALLENGE_SLOT_PATH,
) -> dict[str, Any]:
    """Build a content-addressed weak-observation and opaque-slot bundle."""

    if not observation_paths:
        raise BlindContractError("at least one observation path is required")
    normalized_paths = [
        _validate_observation_path(path, context=f"observation_paths[{index}]")
        for index, path in enumerate(observation_paths)
    ]
    if len(set(normalized_paths)) != len(normalized_paths):
        raise BlindContractError("observation paths must be unique")

    entries: list[dict[str, Any]] = []
    record_sets: list[dict[str, Any]] = []
    total_records = 0
    for relative_path in sorted(normalized_paths):
        entry = _basic_file_entry(
            bundle_root, relative_path, context=f"observation file {relative_path!r}"
        )
        _, path = _safe_regular_file(
            bundle_root, relative_path, context=f"observation file {relative_path!r}"
        )
        records = _read_auditor_jsonl(path, context=relative_path)
        entry.update(
            {
                "media_type": "application/x-ndjson",
                "record_count": len(records),
                "records_sha256": _sha256_bytes(_canonical_json_bytes(records)),
            }
        )
        entries.append(entry)
        record_sets.append({"path": relative_path, "records": records})
        total_records += len(records)

    challenge_slot_path = _validate_challenge_slot_path(
        challenge_slot_path, context="challenge_slot_path"
    )
    challenge_entry = _basic_file_entry(
        bundle_root, challenge_slot_path, context="challenge slot inventory"
    )
    _, challenge_path = _safe_regular_file(
        bundle_root, challenge_slot_path, context="challenge slot inventory"
    )
    challenge_slots = _read_challenge_slot_jsonl(challenge_path, context=challenge_slot_path)
    observation_targets = {
        record["target_id"]
        for record in validate_auditor_observations(
            record for item in record_sets for record in item["records"]
        )
    }
    slot_targets = {record["target_id"] for record in challenge_slots}
    if observation_targets != slot_targets:
        raise BlindContractError(
            "weak observations and challenge slots must cover the same target set"
        )
    challenge_entry.update(
        {
            "media_type": "application/x-ndjson",
            "record_count": len(challenge_slots),
            "records_sha256": _sha256_bytes(_canonical_json_bytes(challenge_slots)),
        }
    )

    manifest: dict[str, Any] = {
        "schema_version": CONTRACT_VERSION,
        "contract_type": BLIND_BUNDLE_CONTRACT,
        "security_boundary": _security_boundary(),
        "auditor_observation_fields": list(AUDITOR_OBSERVATION_FIELDS),
        "challenge_slot_fields": list(CHALLENGE_SLOT_FIELDS),
        "pairing_identifier_format": "lowercase_128_bit_hex",
        "pairing_token_scheme": PAIRING_TOKEN_SCHEME,
        "pairing_token_domains": list(PAIRING_TOKEN_DOMAINS),
        "pairing_token_material_contract": dict(PAIRING_TOKEN_MATERIAL_CONTRACT),
        "observation_count": total_records,
        "observation_set_sha256": _sha256_bytes(_canonical_json_bytes(record_sets)),
        "observation_files": entries,
        "challenge_slot_count": len(challenge_slots),
        "challenge_slot_set_sha256": _sha256_bytes(_canonical_json_bytes(challenge_slots)),
        "challenge_slot_file": challenge_entry,
    }
    manifest["bundle_sha256"] = _self_address(manifest, "bundle_sha256")
    validate_blind_bundle_manifest(bundle_root, manifest)
    return manifest


def _validate_bundle_document(manifest: Mapping[str, Any]) -> None:
    expected = {
        "schema_version",
        "contract_type",
        "security_boundary",
        "auditor_observation_fields",
        "challenge_slot_fields",
        "pairing_identifier_format",
        "pairing_token_scheme",
        "pairing_token_domains",
        "pairing_token_material_contract",
        "observation_count",
        "observation_set_sha256",
        "observation_files",
        "challenge_slot_count",
        "challenge_slot_set_sha256",
        "challenge_slot_file",
        "bundle_sha256",
    }
    _require_exact_keys(manifest, expected, context="blind bundle manifest")
    if manifest["schema_version"] != CONTRACT_VERSION:
        raise BlindContractError("unsupported blind bundle schema_version")
    if manifest["contract_type"] != BLIND_BUNDLE_CONTRACT:
        raise BlindContractError("unexpected blind bundle contract_type")
    _validate_security_boundary(manifest["security_boundary"], context="blind bundle")
    if manifest["auditor_observation_fields"] != list(AUDITOR_OBSERVATION_FIELDS):
        raise BlindContractError("blind bundle auditor observation allowlist mismatch")
    if manifest["challenge_slot_fields"] != list(CHALLENGE_SLOT_FIELDS):
        raise BlindContractError("blind bundle challenge slot allowlist mismatch")
    if manifest["pairing_identifier_format"] != "lowercase_128_bit_hex":
        raise BlindContractError("blind bundle pairing identifier format mismatch")
    if manifest["pairing_token_scheme"] != PAIRING_TOKEN_SCHEME:
        raise BlindContractError("blind bundle pairing token scheme mismatch")
    if manifest["pairing_token_domains"] != list(PAIRING_TOKEN_DOMAINS):
        raise BlindContractError("blind bundle pairing token domains mismatch")
    if manifest["pairing_token_material_contract"] != PAIRING_TOKEN_MATERIAL_CONTRACT:
        raise BlindContractError("blind bundle pairing token material contract mismatch")
    _require_positive_int(manifest["observation_count"], context="observation_count")
    _require_sha256(manifest["observation_set_sha256"], context="observation_set_sha256")
    _require_positive_int(manifest["challenge_slot_count"], context="challenge_slot_count")
    _require_sha256(manifest["challenge_slot_set_sha256"], context="challenge_slot_set_sha256")
    _require_sha256(manifest["bundle_sha256"], context="bundle_sha256")
    files = manifest["observation_files"]
    if not isinstance(files, list) or not files:
        raise BlindContractError("observation_files must be a non-empty list")
    if manifest["bundle_sha256"] != _self_address(manifest, "bundle_sha256"):
        raise BlindContractError("blind bundle manifest self-address mismatch")


def validate_blind_bundle_manifest(
    bundle_root: Path, manifest: Mapping[str, Any]
) -> dict[str, tuple[dict[str, str], ...]]:
    """Validate manifest shape, content hashes, paths, and observation rows."""

    if not isinstance(manifest, Mapping):
        raise BlindContractError("blind bundle manifest must be an object")
    _validate_bundle_document(manifest)
    files = manifest["observation_files"]
    expected_entry_keys = {
        "path",
        "bytes",
        "sha256",
        "media_type",
        "record_count",
        "records_sha256",
    }
    paths: list[str] = []
    all_records: list[dict[str, str]] = []
    record_sets: list[dict[str, Any]] = []
    for index, raw_entry in enumerate(files):
        if not isinstance(raw_entry, Mapping):
            raise BlindContractError(f"observation_files[{index}] must be an object")
        _require_exact_keys(raw_entry, expected_entry_keys, context=f"observation_files[{index}]")
        relative_path = _validate_observation_path(
            raw_entry["path"], context=f"observation_files[{index}].path"
        )
        relative, path = _safe_regular_file(
            bundle_root,
            relative_path,
            context=f"observation_files[{index}].path",
        )
        paths.append(relative)
        if raw_entry["media_type"] != "application/x-ndjson":
            raise BlindContractError("blind observation media_type must be application/x-ndjson")
        expected_bytes = _require_positive_int(
            raw_entry["bytes"], context=f"observation_files[{index}].bytes"
        )
        expected_hash = _require_sha256(
            raw_entry["sha256"], context=f"observation_files[{index}].sha256"
        )
        expected_count = _require_positive_int(
            raw_entry["record_count"], context=f"observation_files[{index}].record_count"
        )
        expected_records_hash = _require_sha256(
            raw_entry["records_sha256"],
            context=f"observation_files[{index}].records_sha256",
        )
        if path.stat().st_size != expected_bytes or _sha256_file(path) != expected_hash:
            raise BlindContractError(f"blind observation artifact mismatch: {relative}")
        records = _read_auditor_jsonl(path, context=relative)
        if len(records) != expected_count:
            raise BlindContractError(f"blind observation record count mismatch: {relative}")
        if _sha256_bytes(_canonical_json_bytes(records)) != expected_records_hash:
            raise BlindContractError(f"blind observation record hash mismatch: {relative}")
        all_records.extend(records)
        record_sets.append({"path": relative, "records": records})

    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise BlindContractError("observation_files must be sorted and path-unique")
    # Revalidate globally so the same pairing identity cannot be split across files.
    globally_validated = validate_auditor_observations(all_records)
    if len(globally_validated) != manifest["observation_count"]:
        raise BlindContractError("blind bundle observation_count mismatch")
    if _sha256_bytes(_canonical_json_bytes(record_sets)) != manifest["observation_set_sha256"]:
        raise BlindContractError("blind bundle observation_set_sha256 mismatch")

    challenge_entry = manifest["challenge_slot_file"]
    if not isinstance(challenge_entry, Mapping):
        raise BlindContractError("challenge_slot_file must be an object")
    _require_exact_keys(challenge_entry, expected_entry_keys, context="challenge_slot_file")
    challenge_relative = _validate_challenge_slot_path(
        challenge_entry["path"], context="challenge_slot_file.path"
    )
    _, challenge_path = _safe_regular_file(
        bundle_root, challenge_relative, context="challenge_slot_file.path"
    )
    if challenge_entry["media_type"] != "application/x-ndjson":
        raise BlindContractError("challenge slot media_type must be application/x-ndjson")
    if challenge_path.stat().st_size != _require_positive_int(
        challenge_entry["bytes"], context="challenge_slot_file.bytes"
    ) or _sha256_file(challenge_path) != _require_sha256(
        challenge_entry["sha256"], context="challenge_slot_file.sha256"
    ):
        raise BlindContractError("challenge slot artifact mismatch")
    challenge_slots = _read_challenge_slot_jsonl(challenge_path, context=challenge_relative)
    if len(challenge_slots) != _require_positive_int(
        challenge_entry["record_count"], context="challenge_slot_file.record_count"
    ):
        raise BlindContractError("challenge slot record count mismatch")
    challenge_records_sha = _sha256_bytes(_canonical_json_bytes(challenge_slots))
    if (
        challenge_records_sha
        != _require_sha256(
            challenge_entry["records_sha256"], context="challenge_slot_file.records_sha256"
        )
        or challenge_records_sha != manifest["challenge_slot_set_sha256"]
    ):
        raise BlindContractError("challenge slot record hash mismatch")
    if len(challenge_slots) != manifest["challenge_slot_count"]:
        raise BlindContractError("challenge slot manifest count mismatch")
    observation_targets = {record["target_id"] for record in globally_validated}
    slot_targets = {record["target_id"] for record in challenge_slots}
    if observation_targets != slot_targets:
        raise BlindContractError(
            "weak observations and challenge slots must cover the same target set"
        )
    return {"observations": globally_validated, "challenge_slots": challenge_slots}


def _require_nonce(value: Any, *, context: str) -> bytes:
    if not isinstance(value, bytes) or len(value) < AUTHORITY_COMMITMENT_MIN_NONCE_BYTES:
        raise BlindContractError(
            f"{context} must be at least {AUTHORITY_COMMITMENT_MIN_NONCE_BYTES} random bytes"
        )
    return value


def _u64be_length_prefixed(value: bytes, *, context: str) -> bytes:
    if not isinstance(value, bytes):
        raise BlindContractError(f"{context} must be bytes")
    if len(value) >= 2**64:
        raise BlindContractError(f"{context} is too large for u64be framing")
    return len(value).to_bytes(8, "big") + value


def _authority_digest(domain: bytes, nonce: bytes, payload: bytes) -> str:
    frame = b"".join(
        (
            _u64be_length_prefixed(domain, context="authority commitment domain"),
            _u64be_length_prefixed(nonce, context="authority commitment nonce"),
            _u64be_length_prefixed(payload, context="authority commitment payload"),
        )
    )
    return _sha256_bytes(frame)


def build_authority_precommitments(
    *,
    evaluation_key_bytes: bytes,
    challenge_bundle_bytes: bytes,
    evaluation_nonce: bytes,
    challenge_nonce: bytes,
) -> dict[str, str]:
    """Create salted authority commitments without exposing paths or payloads."""

    if not isinstance(evaluation_key_bytes, bytes) or not evaluation_key_bytes:
        raise BlindContractError("evaluation_key_bytes must be non-empty bytes")
    if not isinstance(challenge_bundle_bytes, bytes) or not challenge_bundle_bytes:
        raise BlindContractError("challenge_bundle_bytes must be non-empty bytes")
    evaluation_nonce = _require_nonce(evaluation_nonce, context="evaluation_nonce")
    challenge_nonce = _require_nonce(challenge_nonce, context="challenge_nonce")
    return {
        "scheme": AUTHORITY_COMMITMENT_SCHEME,
        "evaluation_key_commitment": _authority_digest(
            b"ltt-evaluation-key-v1", evaluation_nonce, evaluation_key_bytes
        ),
        "challenge_bundle_commitment": _authority_digest(
            b"ltt-challenge-bundle-v1", challenge_nonce, challenge_bundle_bytes
        ),
    }


def _validate_authority_commitments(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise BlindContractError("authority_commitments must be an object")
    expected = {"scheme", "evaluation_key_commitment", "challenge_bundle_commitment"}
    _require_exact_keys(value, expected, context="authority_commitments")
    if value["scheme"] != AUTHORITY_COMMITMENT_SCHEME:
        raise BlindContractError("unsupported authority commitment scheme")
    _require_sha256(value["evaluation_key_commitment"], context="evaluation_key_commitment")
    _require_sha256(value["challenge_bundle_commitment"], context="challenge_bundle_commitment")


def _validate_pre_auditor_query_ledger(
    value: Any,
    *,
    execution_lock: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Close the output-producing phases while leaving diagnostics pending.

    Cue-mask diagnostics are forbidden before all fold predictions commit.  The
    ordinary post-discovery ledger therefore cannot be the pre-auditor barrier:
    it includes 576 diagnostic forwards.  This narrower ledger closes exactly
    causal labeling, behavior fitting, and sealed weak/challenge collection.
    """

    if not isinstance(value, Mapping):
        raise BlindContractError("pre_auditor_query_ledger must be an object")
    expected = {
        "schema_version",
        "status",
        "execution_lock_sha256",
        "causal_label_forward_passes",
        "behavior_fit_forward_passes",
        "sealed_test_forward_passes",
        "diagnostic_forward_passes",
        "diagnostic_status",
        "total_forward_passes",
        "wall_clock_seconds",
        "ledger_sha256",
    }
    _require_exact_keys(value, expected, context="pre_auditor_query_ledger")
    if value["schema_version"] != CONTRACT_VERSION:
        raise BlindContractError("pre-auditor query ledger schema_version is not frozen")
    if value["status"] != "sealed_outputs_complete_diagnostics_pending":
        raise BlindContractError("pre-auditor ledger status is not frozen")
    lock_sha256 = _canonical_artifact_sha256(execution_lock)
    if value["execution_lock_sha256"] != lock_sha256:
        raise BlindContractError("pre-auditor ledger targets another execution lock")
    expected_counts = {
        "causal_label_forward_passes": PRE_AUDITOR_CAUSAL_LABEL_FORWARD_PASSES,
        "behavior_fit_forward_passes": PRE_AUDITOR_BEHAVIOR_FIT_FORWARD_PASSES,
        "sealed_test_forward_passes": PRE_AUDITOR_SEALED_TEST_FORWARD_PASSES,
        "diagnostic_forward_passes": 0,
        "total_forward_passes": PRE_AUDITOR_TOTAL_FORWARD_PASSES,
    }
    query_plan = execution_lock.get("query_plan")
    if not isinstance(query_plan, Mapping):
        raise BlindContractError("execution lock lacks its final query plan")
    plan_fields = {
        "causal_label_forward_passes": "planned_causal_label_forward_passes",
        "behavior_fit_forward_passes": "planned_behavior_fit_forward_passes",
        "sealed_test_forward_passes": "planned_sealed_test_forward_passes",
    }
    for field, expected_count in expected_counts.items():
        if type(value[field]) is not int or value[field] != expected_count:
            raise BlindContractError(f"pre-auditor exact query count drifted={field}")
        plan_field = plan_fields.get(field)
        if plan_field is not None and query_plan.get(plan_field) != expected_count:
            raise BlindContractError(f"execution query plan drifted={plan_field}")
    if value["diagnostic_status"] != "pending_until_all_fold_prediction_commitments":
        raise BlindContractError("diagnostics must remain pending at the auditor barrier")
    wall = value["wall_clock_seconds"]
    if (
        isinstance(wall, bool)
        or not isinstance(wall, (int, float))
        or not math.isfinite(float(wall))
    ):
        raise BlindContractError("pre-auditor wall_clock_seconds must be finite")
    if float(wall) < 0 or float(wall) > float(query_plan.get("max_wall_clock_seconds", -1)):
        raise BlindContractError("pre-auditor wall-clock budget exceeded")
    _require_sha256(value["ledger_sha256"], context="pre_auditor_query_ledger.ledger_sha256")
    if value["ledger_sha256"] != _self_address(value, "ledger_sha256"):
        raise BlindContractError("pre-auditor query ledger self-address mismatch")
    return value


def _sealed_partition_design(
    authority_secret: bytes,
    *,
    execution_lock: Mapping[str, Any],
) -> Any:
    if not isinstance(authority_secret, bytes) or len(authority_secret) < 32:
        raise BlindContractError("authority_secret must contain at least 256 random bits")
    blind_runtime = execution_lock.get("blind_runtime")
    if not isinstance(blind_runtime, Mapping):
        raise BlindContractError("execution lock lacks blind_runtime")
    if hashlib.sha256(authority_secret).hexdigest() != blind_runtime.get(
        "authority_secret_commitment_sha256"
    ):
        raise BlindContractError("authority secret does not open the execution-lock commitment")
    seeds = derive_live_content_seeds(authority_secret, 64)
    sealed_seeds = partition_content_seeds(seeds)["D_sealed_test"]
    design = build_oss_design(sealed_seeds)
    live_manifest = execution_lock.get("live_material_manifest")
    if not isinstance(live_manifest, Mapping):
        raise BlindContractError("execution lock lacks live_material_manifest")
    partition_records = live_manifest.get("partition_records")
    if not isinstance(partition_records, list):
        raise BlindContractError("execution lock lacks partition records")
    sealed_records = [
        item
        for item in partition_records
        if isinstance(item, Mapping) and item.get("partition_id") == "D_sealed_test"
    ]
    if len(sealed_records) != 1:
        raise BlindContractError("execution lock must bind exactly one D_sealed_test partition")
    sealed_record = sealed_records[0]
    manifest = design.manifest()
    expected_bindings = {
        "content_seed_count": 16,
        "case_count": 128,
        "case_set_sha256": manifest["case_set_sha256"],
        "projection_count": 512,
        "projection_set_sha256": manifest["projection_set_sha256"],
        "weak_observations": WEAK_TRIAL_COUNT_PER_TARGET,
        "heldout_challenges": CHALLENGE_TRIAL_COUNT_PER_TARGET,
    }
    for field, expected_value in expected_bindings.items():
        if sealed_record.get(field) != expected_value:
            raise BlindContractError(f"D_sealed_test material binding drifted={field}")
    return design


def _fold_registry(
    execution_lock: Mapping[str, Any],
    *,
    fold_id: str,
    heldout_dependency_cluster_id: str,
) -> tuple[
    tuple[Mapping[str, Any], ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    models_raw = execution_lock.get("model_registry")
    clusters_raw = execution_lock.get("dependency_clusters")
    if not isinstance(models_raw, list) or len(models_raw) != TARGET_COUNT:
        raise BlindContractError("execution lock must contain exactly nine model units")
    if not isinstance(clusters_raw, list) or len(clusters_raw) != SEALED_EVALUATION_FOLD_COUNT:
        raise BlindContractError("execution lock must contain exactly three dependency clusters")
    models = tuple(models_raw)
    model_ids = [model.get("model_unit_id") for model in models if isinstance(model, Mapping)]
    if len(model_ids) != TARGET_COUNT or any(
        not isinstance(item, str) or not item for item in model_ids
    ):
        raise BlindContractError("execution model registry has invalid model_unit_id values")
    if model_ids != sorted(model_ids) or len(set(model_ids)) != TARGET_COUNT:
        raise BlindContractError("execution model registry must be sorted and unique")
    clusters = {
        cluster.get("dependency_cluster_id"): tuple(cluster.get("model_unit_ids", ()))
        for cluster in clusters_raw
        if isinstance(cluster, Mapping)
    }
    if (
        len(clusters) != SEALED_EVALUATION_FOLD_COUNT
        or heldout_dependency_cluster_id not in clusters
    ):
        raise BlindContractError("heldout dependency cluster is absent from the execution lock")
    if fold_id != f"holdout-{heldout_dependency_cluster_id}":
        raise BlindContractError("fold_id must be derived from the heldout dependency cluster")
    if any(
        tuple(sorted(members)) != members or len(members) != HELDOUT_TARGET_COUNT
        for members in clusters.values()
    ):
        raise BlindContractError(
            "every pilot dependency cluster must contain exactly three sorted units"
        )
    if set(item for members in clusters.values() for item in members) != set(model_ids):
        raise BlindContractError("dependency clusters do not close the exact model registry")
    heldout_ids = tuple(clusters[heldout_dependency_cluster_id])
    development_clusters = tuple(sorted(set(clusters) - {heldout_dependency_cluster_id}))
    development_ids = tuple(
        sorted(item for cluster_id in development_clusters for item in clusters[cluster_id])
    )
    if len(heldout_ids) != HELDOUT_TARGET_COUNT or len(development_ids) != DEVELOPMENT_TARGET_COUNT:
        raise BlindContractError("fold target counts are not the frozen 3/6 split")
    cluster_by_model = {
        model_id: cluster_id for cluster_id, members in clusters.items() for model_id in members
    }
    for model in models:
        if model.get("dependency_cluster_id") != cluster_by_model[model["model_unit_id"]]:
            raise BlindContractError("model registry cluster id disagrees with the frozen fold")
    return models, heldout_ids, development_clusters, development_ids


def _sealed_trial_sha256(value: Any, *, context: str) -> str:
    return _require_sha256(value, context=context)


def _derive_sealed_evaluation_material(
    *,
    execution_lock: Mapping[str, Any],
    authority_secret: bytes,
    challenge_bundle_bytes: bytes,
    fold_id: str,
    heldout_dependency_cluster_id: str,
) -> dict[str, Any]:
    """Regenerate D_sealed and derive every public row and scoring count."""

    payload = _parse_canonical_json_object_bytes(
        challenge_bundle_bytes, context="revealed challenge bundle"
    )
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "contract_type",
            "execution_lock_sha256",
            "fold_id",
            "heldout_dependency_cluster_id",
            "weak_trials",
            "challenge_trials",
        },
        context="sealed evaluation payload",
    )
    if (
        payload["schema_version"] != CONTRACT_VERSION
        or payload["contract_type"] != SEALED_EVALUATION_PAYLOAD_CONTRACT
    ):
        raise BlindContractError("sealed evaluation payload contract is not frozen")
    lock_sha256 = _canonical_artifact_sha256(execution_lock)
    if payload["execution_lock_sha256"] != lock_sha256:
        raise BlindContractError("sealed evaluation payload targets another execution lock")
    if (
        payload["fold_id"] != fold_id
        or payload["heldout_dependency_cluster_id"] != heldout_dependency_cluster_id
    ):
        raise BlindContractError("sealed evaluation payload targets another fold")
    models, heldout_ids, development_clusters, development_ids = _fold_registry(
        execution_lock,
        fold_id=fold_id,
        heldout_dependency_cluster_id=heldout_dependency_cluster_id,
    )
    design = _sealed_partition_design(authority_secret, execution_lock=execution_lock)
    model_by_id = {model["model_unit_id"]: model for model in models}
    cluster_by_id = {
        cluster["dependency_cluster_id"]: cluster
        for cluster in execution_lock["dependency_clusters"]
    }
    case_by_id = {case.case_id: case for case in design.cases}
    weak_by_id = {projection.projection_id: projection for projection in design.weak_observations}
    challenge_by_id = {
        projection.projection_id: projection for projection in design.heldout_challenges
    }
    target_tokens = {
        model_id: derive_pairing_token(
            authority_secret,
            domain="target",
            material=_canonical_json_bytes(model_by_id[model_id]),
        )
        for model_id in model_by_id
    }
    cluster_tokens = {
        cluster_id: "dependency-"
        + derive_pairing_token(
            authority_secret,
            domain="cluster",
            material=_canonical_json_bytes(
                {
                    "private_fold_id": fold_id,
                    "dependency_cluster": cluster_by_id[cluster_id],
                }
            ),
        )[:16]
        for cluster_id in cluster_by_id
    }
    if len(set(cluster_tokens.values())) != SEALED_EVALUATION_FOLD_COUNT:
        raise BlindContractError("derived cluster pairing tokens collided")
    fold_token = derive_pairing_token(
        authority_secret,
        domain="fold",
        material=fold_id.encode("utf-8"),
    )
    replicate_token = derive_pairing_token(
        authority_secret, domain="replicate", material=(0).to_bytes(8, "big")
    )

    weak_raw = payload["weak_trials"]
    if not isinstance(weak_raw, list) or len(weak_raw) != SEALED_WEAK_TRIAL_COUNT:
        raise BlindContractError("sealed weak evidence must contain exactly 2880 trials")
    weak_fields = {
        "model_unit_id",
        "case_id",
        "projection_id",
        "projection_kind",
        "prompt_text",
        "prompt_sha256",
        "projection_record_sha256",
        "output_text",
        "output_text_sha256",
        "completion_record_sha256",
    }
    expected_weak_identities = [
        (model_id, projection.projection_id)
        for model_id in sorted(model_by_id)
        for projection in sorted(design.weak_observations, key=lambda item: item.projection_id)
    ]
    expected_weak_identity_set = set(expected_weak_identities)
    observed_weak_identities: list[tuple[str, str]] = []
    public_weak_by_model: dict[str, list[dict[str, str]]] = {
        model_id: [] for model_id in model_by_id
    }
    for index, raw in enumerate(weak_raw):
        if not isinstance(raw, Mapping):
            raise BlindContractError(f"weak_trials[{index}] must be an object")
        _require_exact_keys(raw, weak_fields, context=f"weak_trials[{index}]")
        identity = (raw["model_unit_id"], raw["projection_id"])
        observed_weak_identities.append(identity)
        if identity not in expected_weak_identity_set:
            raise BlindContractError("weak trial has an unauthorized model/projection identity")
        projection = weak_by_id[raw["projection_id"]]
        expected_values = {
            "case_id": projection.case_id,
            "projection_kind": projection.kind.value,
            "prompt_text": projection.prompt_text,
            "prompt_sha256": hashlib.sha256(projection.prompt_text.encode("utf-8")).hexdigest(),
            "projection_record_sha256": _canonical_artifact_sha256(projection.to_dict()),
        }
        if any(raw[field] != expected for field, expected in expected_values.items()):
            raise BlindContractError("weak trial differs from regenerated D_sealed material")
        output_text = raw["output_text"]
        if (
            not isinstance(output_text, str)
            or raw["output_text_sha256"] != hashlib.sha256(output_text.encode("utf-8")).hexdigest()
        ):
            raise BlindContractError("weak trial raw output is not content-addressed")
        # This digest is an authority-supplied pointer only.  Without an inline
        # completion record plus a typed validator it is not runtime-closure
        # evidence; the raw prompt/output commitments above remain authoritative.
        _sealed_trial_sha256(
            raw["completion_record_sha256"],
            context=f"weak_trials[{index}].completion_record_sha256",
        )
        public_weak_by_model[raw["model_unit_id"]].append(
            {
                "target_id": target_tokens[raw["model_unit_id"]],
                "case_id": derive_pairing_token(
                    authority_secret, domain="case", material=projection.case_id.encode("utf-8")
                ),
                "projection_id": derive_pairing_token(
                    authority_secret,
                    domain="projection",
                    material=projection.kind.value.encode("utf-8"),
                ),
                "replicate_id": replicate_token,
                "prompt_text": projection.prompt_text,
                "output_text": output_text,
            }
        )
    if observed_weak_identities != expected_weak_identities:
        raise BlindContractError("weak trials must exactly preserve the full D_sealed order")

    challenge_raw = payload["challenge_trials"]
    if not isinstance(challenge_raw, list) or len(challenge_raw) != SEALED_CHALLENGE_TRIAL_COUNT:
        raise BlindContractError("sealed challenge evidence must contain exactly 1152 trials")
    challenge_fields = weak_fields | {
        "semantic_solution",
        "surface_cue",
        "answer_codebook",
        "derived_outcome",
    }
    expected_challenge_identities = [
        (model_id, projection.projection_id)
        for model_id in sorted(model_by_id)
        for projection in sorted(design.heldout_challenges, key=lambda item: item.projection_id)
    ]
    expected_challenge_identity_set = set(expected_challenge_identities)
    observed_challenge_identities: list[tuple[str, str]] = []
    counts: dict[tuple[str, str], dict[str, int]] = {}
    for index, raw in enumerate(challenge_raw):
        if not isinstance(raw, Mapping):
            raise BlindContractError(f"challenge_trials[{index}] must be an object")
        _require_exact_keys(raw, challenge_fields, context=f"challenge_trials[{index}]")
        identity = (raw["model_unit_id"], raw["projection_id"])
        observed_challenge_identities.append(identity)
        if identity not in expected_challenge_identity_set:
            raise BlindContractError(
                "challenge trial has an unauthorized model/projection identity"
            )
        projection = challenge_by_id[raw["projection_id"]]
        case = case_by_id[projection.case_id]
        expected_values = {
            "case_id": projection.case_id,
            "projection_kind": projection.kind.value,
            "prompt_text": projection.prompt_text,
            "prompt_sha256": hashlib.sha256(projection.prompt_text.encode("utf-8")).hexdigest(),
            "projection_record_sha256": _canonical_artifact_sha256(projection.to_dict()),
            "semantic_solution": case.semantic_solution.value,
            "surface_cue": case.surface_cue.value,
            "answer_codebook": case.answer_codebook.value,
        }
        if any(raw[field] != expected for field, expected in expected_values.items()):
            raise BlindContractError("challenge trial differs from regenerated D_sealed material")
        output_text = raw["output_text"]
        if (
            not isinstance(output_text, str)
            or raw["output_text_sha256"] != hashlib.sha256(output_text.encode("utf-8")).hexdigest()
        ):
            raise BlindContractError("challenge trial raw output is not content-addressed")
        # Pointer syntax is checked, but no unmounted completion record is
        # treated as validated runtime evidence.
        _sealed_trial_sha256(
            raw["completion_record_sha256"],
            context=f"challenge_trials[{index}].completion_record_sha256",
        )
        outcome = derive_relational_challenge_outcome(
            output_text,
            semantic_solution=case.semantic_solution,
            surface_cue=case.surface_cue,
            answer_codebook=case.answer_codebook,
        )
        if raw["derived_outcome"] != outcome:
            raise BlindContractError("challenge outcome was not derived from the raw output")
        bucket = counts.setdefault(
            (raw["model_unit_id"], projection.kind.value),
            {"semantic_consistent": 0, "surface_cue_consistent": 0, "parse_failure": 0},
        )
        bucket[outcome] += 1
    if observed_challenge_identities != expected_challenge_identities:
        raise BlindContractError("challenge trials must exactly preserve the full D_sealed order")
    if any(
        sum(bucket.values()) != CHALLENGE_TRIAL_COUNT_PER_TARGET_PER_KIND
        for bucket in counts.values()
    ):
        raise BlindContractError("each target/challenge-kind cell must contain exactly 64 trials")

    slots_by_model: dict[str, list[dict[str, str]]] = {}
    key_by_model: dict[str, list[dict[str, Any]]] = {}
    for model_id in sorted(model_by_id):
        target_id = target_tokens[model_id]
        cluster_id = cluster_tokens[model_by_id[model_id]["dependency_cluster_id"]]
        slots_by_model[model_id] = []
        key_by_model[model_id] = []
        for kind in ("heldout_cue_conflict", "heldout_mismatch_table"):
            slot = {
                "target_id": target_id,
                "challenge_slot_id": derive_pairing_token(
                    authority_secret,
                    domain="challenge_slot",
                    material=target_id.encode("ascii") + b"\x00" + kind.encode("utf-8"),
                ),
                "challenge_kind": kind,
            }
            slots_by_model[model_id].append(slot)
            key_by_model[model_id].append(
                {
                    "schema_version": CONTRACT_VERSION,
                    **slot,
                    "dependency_cluster_id": cluster_id,
                    "outcome_counts": counts[(model_id, kind)],
                    "trial_count": CHALLENGE_TRIAL_COUNT_PER_TARGET_PER_KIND,
                }
            )

    heldout_weak = validate_auditor_observations(
        row for model_id in heldout_ids for row in public_weak_by_model[model_id]
    )
    heldout_slots = validate_challenge_slot_inventory(
        slot for model_id in heldout_ids for slot in slots_by_model[model_id]
    )
    heldout_key = validate_challenge_scoring_key(
        (row for model_id in heldout_ids for row in key_by_model[model_id]), heldout_slots
    )
    development_slots = validate_challenge_slot_inventory(
        slot for model_id in development_ids for slot in slots_by_model[model_id]
    )
    development_key = validate_challenge_scoring_key(
        (row for model_id in development_ids for row in key_by_model[model_id]),
        development_slots,
    )
    if len(heldout_weak) != HELDOUT_WEAK_OBSERVATION_COUNT:
        raise BlindContractError("heldout weak observation count is not exactly 960")
    if sum(row["trial_count"] for row in heldout_key) != HELDOUT_CHALLENGE_TRIAL_COUNT:
        raise BlindContractError("heldout challenge denominator is not exactly 384")
    if sum(row["trial_count"] for row in development_key) != DEVELOPMENT_CHALLENGE_TRIAL_COUNT:
        raise BlindContractError("development challenge denominator is not exactly 768")
    return {
        "execution_lock_sha256": lock_sha256,
        "fold_id": fold_id,
        "fold_token": fold_token,
        "heldout_dependency_cluster_id": heldout_dependency_cluster_id,
        "heldout_dependency_cluster_token": cluster_tokens[heldout_dependency_cluster_id],
        "cluster_tokens": cluster_tokens,
        "heldout_model_unit_ids": heldout_ids,
        "development_dependency_cluster_ids": development_clusters,
        "development_model_unit_ids": development_ids,
        "heldout_weak_observations": heldout_weak,
        "heldout_slots": heldout_slots,
        "heldout_key": heldout_key,
        "development_slots": development_slots,
        "development_key": development_key,
        "sealed_weak_trials_sha256": _canonical_artifact_sha256(weak_raw),
        "sealed_challenge_trials_sha256": _canonical_artifact_sha256(challenge_raw),
        "challenge_bundle_sha256": hashlib.sha256(challenge_bundle_bytes).hexdigest(),
        "evaluation_key_bytes": _canonical_jsonl_bytes(heldout_key),
    }


_SEALED_EVALUATION_AUTHORIZATION_FIELDS = {
    "schema_version",
    "contract_type",
    "status",
    "authorization_id",
    "authorized_at",
    "pilot_barrier_id",
    "fold_worker_capability_id",
    "fold_worker_capability_contract",
    "parent_design_manifest_sha256",
    "execution_lock_sha256",
    "pre_auditor_query_ledger_sha256",
    "fold_id",
    "fold_token",
    "heldout_dependency_cluster_id",
    "heldout_model_unit_ids",
    "development_dependency_cluster_ids",
    "development_model_unit_ids",
    "counts",
    "blind_bundle_sha256",
    "prospective_contract",
    "sealed_weak_trials_sha256",
    "sealed_challenge_trials_sha256",
    "challenge_bundle_sha256",
    "evaluation_key_sha256",
    "weak_observation_records_sha256",
    "heldout_slot_inventory_sha256",
    "heldout_scoring_key_sha256",
    "development_slot_inventory_sha256",
    "development_scoring_key_sha256",
    "authority_commitments",
    "authorization_sha256",
}


def _sealed_evaluation_counts() -> dict[str, int]:
    return {
        "target_count": TARGET_COUNT,
        "heldout_target_count": HELDOUT_TARGET_COUNT,
        "development_target_count": DEVELOPMENT_TARGET_COUNT,
        "sealed_weak_trial_count": SEALED_WEAK_TRIAL_COUNT,
        "sealed_challenge_trial_count": SEALED_CHALLENGE_TRIAL_COUNT,
        "sealed_forward_pass_count": SEALED_FORWARD_PASS_COUNT,
        "heldout_weak_observation_count": HELDOUT_WEAK_OBSERVATION_COUNT,
        "trial_count_per_slot": CHALLENGE_TRIAL_COUNT_PER_TARGET_PER_KIND,
        "heldout_challenge_trial_count": HELDOUT_CHALLENGE_TRIAL_COUNT,
        "development_challenge_trial_count": DEVELOPMENT_CHALLENGE_TRIAL_COUNT,
    }


def validate_sealed_evaluation_authorization_template(
    value: Mapping[str, Any], *, expected_parent_design_manifest_sha256: str
) -> None:
    """Validate the checked-in call-free post-output authorization template."""

    if not isinstance(value, Mapping):
        raise BlindContractError("sealed evaluation authorization template must be an object")
    _require_exact_keys(
        value,
        _SEALED_EVALUATION_AUTHORIZATION_FIELDS,
        context="sealed evaluation authorization template",
    )
    if (
        value["schema_version"] != CONTRACT_VERSION
        or value["contract_type"] != SEALED_EVALUATION_AUTHORIZATION_CONTRACT
        or value["status"] != "unassigned"
    ):
        raise BlindContractError("sealed evaluation authorization template is not unassigned")
    expected_parent = _require_sha256(
        expected_parent_design_manifest_sha256,
        context="expected_parent_design_manifest_sha256",
    )
    if value["parent_design_manifest_sha256"] != expected_parent:
        raise BlindContractError("sealed evaluation template parent design hash mismatch")
    if value["counts"] != _sealed_evaluation_counts():
        raise BlindContractError("sealed evaluation template exact counts drifted")
    for field in (
        "heldout_model_unit_ids",
        "development_dependency_cluster_ids",
        "development_model_unit_ids",
    ):
        if value[field] != []:
            raise BlindContractError("sealed evaluation template contains assigned arrays")
    fixed = {
        "schema_version",
        "contract_type",
        "status",
        "parent_design_manifest_sha256",
        "counts",
        "heldout_model_unit_ids",
        "development_dependency_cluster_ids",
        "development_model_unit_ids",
    }
    if any(value[field] is not None for field in _SEALED_EVALUATION_AUTHORIZATION_FIELDS - fixed):
        raise BlindContractError("sealed evaluation template contains assigned fields")


def _validate_sealed_evaluation_authorization_document(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise BlindContractError("sealed evaluation authorization must be an object")
    _require_exact_keys(
        value,
        _SEALED_EVALUATION_AUTHORIZATION_FIELDS,
        context="sealed evaluation authorization",
    )
    if value["schema_version"] != CONTRACT_VERSION:
        raise BlindContractError("sealed evaluation authorization schema_version is not frozen")
    if value["contract_type"] != SEALED_EVALUATION_AUTHORIZATION_CONTRACT:
        raise BlindContractError("sealed evaluation authorization contract_type is not frozen")
    if value["status"] != "sealed_before_auditor_fit":
        raise BlindContractError("sealed evaluation authorization status is not frozen")
    _require_opaque_id(value["authorization_id"], context="authorization_id")
    _require_rfc3339_utc(value["authorized_at"], context="authorized_at")
    _require_opaque_id(value["pilot_barrier_id"], context="pilot_barrier_id")
    _require_opaque_id(value["fold_worker_capability_id"], context="fold_worker_capability_id")
    if value["fold_worker_capability_contract"] != FOLD_WORKER_CAPABILITY_CONTRACT:
        raise BlindContractError("fold worker capability declaration is not frozen")
    for field in (
        "parent_design_manifest_sha256",
        "execution_lock_sha256",
        "pre_auditor_query_ledger_sha256",
        "blind_bundle_sha256",
        "sealed_weak_trials_sha256",
        "sealed_challenge_trials_sha256",
        "challenge_bundle_sha256",
        "evaluation_key_sha256",
        "weak_observation_records_sha256",
        "heldout_slot_inventory_sha256",
        "heldout_scoring_key_sha256",
        "development_slot_inventory_sha256",
        "development_scoring_key_sha256",
        "authorization_sha256",
    ):
        _require_sha256(value[field], context=f"sealed_evaluation_authorization.{field}")
    _require_opaque_id(value["fold_id"], context="fold_id")
    _require_pairing_token(value["fold_token"], context="fold_token")
    _require_opaque_id(
        value["heldout_dependency_cluster_id"], context="heldout_dependency_cluster_id"
    )
    array_counts = {
        "heldout_model_unit_ids": HELDOUT_TARGET_COUNT,
        "development_dependency_cluster_ids": DEVELOPMENT_DEPENDENCY_CLUSTER_COUNT,
        "development_model_unit_ids": DEVELOPMENT_TARGET_COUNT,
    }
    for field, count in array_counts.items():
        values = value[field]
        if (
            not isinstance(values, list)
            or len(values) != count
            or values != sorted(values)
            or len(set(values)) != count
            or any(not isinstance(item, str) or not item for item in values)
        ):
            raise BlindContractError(f"sealed authorization has invalid {field}")
    counts = value["counts"]
    expected_counts = _sealed_evaluation_counts()
    if counts != expected_counts:
        raise BlindContractError("sealed evaluation authorization counts are not frozen")
    _validate_prospective_contract(value["prospective_contract"])
    _validate_authority_commitments(value["authority_commitments"])
    if value["authorization_sha256"] != _self_address(value, "authorization_sha256"):
        raise BlindContractError("sealed evaluation authorization self-address mismatch")


def _assert_blind_bundle_equals_derived(
    *,
    bundle: Mapping[str, tuple[dict[str, str], ...]],
    material: Mapping[str, Any],
) -> None:
    def weak_sort(row: Mapping[str, Any]) -> tuple[Any, ...]:
        return tuple(row[field] for field in AUDITOR_PAIRING_FIELDS)

    actual_weak = tuple(sorted(bundle["observations"], key=weak_sort))
    expected_weak = tuple(sorted(material["heldout_weak_observations"], key=weak_sort))
    if actual_weak != expected_weak:
        raise BlindContractError(
            "blind weak rows do not equal the lock-derived D_sealed heldout evidence"
        )
    if tuple(bundle["challenge_slots"]) != tuple(material["heldout_slots"]):
        raise BlindContractError(
            "blind challenge slots do not equal the lock-derived heldout fold inventory"
        )


def build_sealed_evaluation_authorization(
    *,
    execution_lock: Mapping[str, Any],
    pre_auditor_query_ledger: Mapping[str, Any],
    authority_secret: bytes,
    challenge_bundle_bytes: bytes,
    blind_bundle_root: Path,
    blind_bundle_manifest: Mapping[str, Any],
    authorization_id: str,
    authorized_at: str,
    pilot_barrier_id: str,
    fold_worker_capability_id: str,
    fold_id: str,
    heldout_dependency_cluster_id: str,
    evaluation_nonce: bytes,
    challenge_nonce: bytes,
) -> dict[str, Any]:
    """Seal one 3-vs-6 fold after outputs exist and before auditor fitting."""

    _require_opaque_id(authorization_id, context="authorization_id")
    _require_rfc3339_utc(authorized_at, context="authorized_at")
    _require_opaque_id(pilot_barrier_id, context="pilot_barrier_id")
    _require_opaque_id(fold_worker_capability_id, context="fold_worker_capability_id")
    ledger = _validate_pre_auditor_query_ledger(
        pre_auditor_query_ledger, execution_lock=execution_lock
    )
    material = _derive_sealed_evaluation_material(
        execution_lock=execution_lock,
        authority_secret=authority_secret,
        challenge_bundle_bytes=challenge_bundle_bytes,
        fold_id=fold_id,
        heldout_dependency_cluster_id=heldout_dependency_cluster_id,
    )
    bundle = validate_blind_bundle_manifest(blind_bundle_root, blind_bundle_manifest)
    _assert_blind_bundle_equals_derived(bundle=bundle, material=material)
    authority_commitments = build_authority_precommitments(
        evaluation_key_bytes=material["evaluation_key_bytes"],
        challenge_bundle_bytes=challenge_bundle_bytes,
        evaluation_nonce=evaluation_nonce,
        challenge_nonce=challenge_nonce,
    )
    weak_evidence = build_weak_observation_evidence(material["heldout_weak_observations"])
    authorization: dict[str, Any] = {
        "schema_version": CONTRACT_VERSION,
        "contract_type": SEALED_EVALUATION_AUTHORIZATION_CONTRACT,
        "status": "sealed_before_auditor_fit",
        "authorization_id": authorization_id,
        "authorized_at": authorized_at,
        "pilot_barrier_id": pilot_barrier_id,
        "fold_worker_capability_id": fold_worker_capability_id,
        "fold_worker_capability_contract": dict(FOLD_WORKER_CAPABILITY_CONTRACT),
        "parent_design_manifest_sha256": execution_lock["parent_design_manifest_sha256"],
        "execution_lock_sha256": material["execution_lock_sha256"],
        "pre_auditor_query_ledger_sha256": ledger["ledger_sha256"],
        "fold_id": fold_id,
        "fold_token": material["fold_token"],
        "heldout_dependency_cluster_id": heldout_dependency_cluster_id,
        "heldout_model_unit_ids": list(material["heldout_model_unit_ids"]),
        "development_dependency_cluster_ids": list(material["development_dependency_cluster_ids"]),
        "development_model_unit_ids": list(material["development_model_unit_ids"]),
        "counts": _sealed_evaluation_counts(),
        "blind_bundle_sha256": blind_bundle_manifest["bundle_sha256"],
        "prospective_contract": dict(execution_lock["prospective_contract"]),
        "sealed_weak_trials_sha256": material["sealed_weak_trials_sha256"],
        "sealed_challenge_trials_sha256": material["sealed_challenge_trials_sha256"],
        "challenge_bundle_sha256": material["challenge_bundle_sha256"],
        "evaluation_key_sha256": hashlib.sha256(material["evaluation_key_bytes"]).hexdigest(),
        "weak_observation_records_sha256": weak_evidence["records_sha256"],
        "heldout_slot_inventory_sha256": _canonical_artifact_sha256(material["heldout_slots"]),
        "heldout_scoring_key_sha256": _canonical_artifact_sha256(material["heldout_key"]),
        "development_slot_inventory_sha256": _canonical_artifact_sha256(
            material["development_slots"]
        ),
        "development_scoring_key_sha256": _canonical_artifact_sha256(material["development_key"]),
        "authority_commitments": authority_commitments,
    }
    authorization["authorization_sha256"] = _self_address(authorization, "authorization_sha256")
    _validate_sealed_evaluation_authorization_document(authorization)
    return authorization


def verify_sealed_evaluation_authorization(
    value: Mapping[str, Any],
    *,
    execution_lock: Mapping[str, Any],
    pre_auditor_query_ledger: Mapping[str, Any],
    authority_secret: bytes,
    challenge_bundle_bytes: bytes,
    evaluation_key_bytes: bytes,
    evaluation_nonce: bytes,
    challenge_nonce: bytes,
    blind_bundle_root: Path,
    blind_bundle_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Open one sealed authorization and return only validator-derived inputs."""

    _validate_sealed_evaluation_authorization_document(value)
    ledger = _validate_pre_auditor_query_ledger(
        pre_auditor_query_ledger, execution_lock=execution_lock
    )
    material = _derive_sealed_evaluation_material(
        execution_lock=execution_lock,
        authority_secret=authority_secret,
        challenge_bundle_bytes=challenge_bundle_bytes,
        fold_id=value["fold_id"],
        heldout_dependency_cluster_id=value["heldout_dependency_cluster_id"],
    )
    bundle = validate_blind_bundle_manifest(blind_bundle_root, blind_bundle_manifest)
    _assert_blind_bundle_equals_derived(bundle=bundle, material=material)
    expected_values = {
        "parent_design_manifest_sha256": execution_lock["parent_design_manifest_sha256"],
        "execution_lock_sha256": material["execution_lock_sha256"],
        "pre_auditor_query_ledger_sha256": ledger["ledger_sha256"],
        "fold_token": material["fold_token"],
        "heldout_model_unit_ids": list(material["heldout_model_unit_ids"]),
        "development_dependency_cluster_ids": list(material["development_dependency_cluster_ids"]),
        "development_model_unit_ids": list(material["development_model_unit_ids"]),
        "blind_bundle_sha256": blind_bundle_manifest["bundle_sha256"],
        "prospective_contract": dict(execution_lock["prospective_contract"]),
        "sealed_weak_trials_sha256": material["sealed_weak_trials_sha256"],
        "sealed_challenge_trials_sha256": material["sealed_challenge_trials_sha256"],
        "challenge_bundle_sha256": hashlib.sha256(challenge_bundle_bytes).hexdigest(),
        "evaluation_key_sha256": hashlib.sha256(evaluation_key_bytes).hexdigest(),
        "weak_observation_records_sha256": build_weak_observation_evidence(
            material["heldout_weak_observations"]
        )["records_sha256"],
        "heldout_slot_inventory_sha256": _canonical_artifact_sha256(material["heldout_slots"]),
        "heldout_scoring_key_sha256": _canonical_artifact_sha256(material["heldout_key"]),
        "development_slot_inventory_sha256": _canonical_artifact_sha256(
            material["development_slots"]
        ),
        "development_scoring_key_sha256": _canonical_artifact_sha256(material["development_key"]),
    }
    for field, expected in expected_values.items():
        if value[field] != expected:
            raise BlindContractError(f"sealed evaluation authorization drifted={field}")
    if evaluation_key_bytes != material["evaluation_key_bytes"]:
        raise BlindContractError(
            "revealed evaluation key is not the canonical key derived from raw challenge outputs"
        )
    expected_commitments = build_authority_precommitments(
        evaluation_key_bytes=evaluation_key_bytes,
        challenge_bundle_bytes=challenge_bundle_bytes,
        evaluation_nonce=evaluation_nonce,
        challenge_nonce=challenge_nonce,
    )
    if value["authority_commitments"] != expected_commitments:
        raise BlindContractError("sealed authority openings do not close the authorization")
    return material


def _prediction_records(
    payload: bytes,
    *,
    context: str,
    expected_slots: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    rows = _parse_jsonl_bytes(payload, context=context)
    try:
        return validate_challenge_predictions(rows, expected_slots)
    except ValueError as error:
        raise BlindContractError(f"invalid challenge predictions: {error}") from error


def _prediction_entry(
    root: Path,
    relative_path: str,
    *,
    expected_slots: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    entry = _basic_file_entry(root, relative_path, context="prediction artifact")
    _, path = _safe_regular_file(root, relative_path, context="prediction artifact")
    records = _prediction_records(
        path.read_bytes(), context=relative_path, expected_slots=expected_slots
    )
    slot_ids = sorted(record["challenge_slot_id"] for record in records)
    entry.update(
        {
            "media_type": "application/x-ndjson",
            "record_count": len(records),
            "challenge_slot_ids_sha256": _sha256_bytes(_canonical_json_bytes(slot_ids)),
        }
    )
    return entry


def _auditor_artifact_entry(root: Path, role: str, relative_path: str) -> dict[str, Any]:
    entry = _basic_file_entry(root, relative_path, context=f"auditor artifact role={role}")
    entry["role"] = role
    entry["media_type"] = "application/octet-stream"
    return entry


def _development_records(
    payload: bytes,
    *,
    role: str,
    context: str,
    expected_slots: Iterable[Mapping[str, Any]] | None = None,
) -> tuple[dict[str, Any], ...]:
    rows = _parse_jsonl_bytes(payload, context=context)
    try:
        if role == "development_slot_inventory":
            return validate_challenge_slot_inventory(rows)
        if role == "development_scoring_key" and expected_slots is not None:
            return validate_challenge_scoring_key(rows, expected_slots)
    except ValueError as error:
        raise BlindContractError(f"invalid {role.replace('_', ' ')}: {error}") from error
    raise BlindContractError(f"unsupported or incomplete development artifact role={role!r}")


def _development_artifact_entry(
    root: Path,
    role: str,
    relative_path: str,
    *,
    expected_slots: Iterable[Mapping[str, Any]] | None = None,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    entry = _basic_file_entry(root, relative_path, context=f"development artifact role={role}")
    _, path = _safe_regular_file(
        root,
        relative_path,
        context=f"development artifact role={role}",
    )
    records = _development_records(
        path.read_bytes(),
        role=role,
        context=relative_path,
        expected_slots=expected_slots,
    )
    entry.update(
        {
            "role": role,
            "media_type": "application/x-ndjson",
            "record_count": len(records),
            "records_sha256": _sha256_bytes(_canonical_json_bytes(records)),
        }
    )
    return entry, records


def _build_development_artifacts(
    root: Path,
    *,
    scoring_key_path: str,
    slot_inventory_path: str,
) -> list[dict[str, Any]]:
    normalized_paths = {
        "development_scoring_key": _validate_relative_path(
            scoring_key_path,
            context="development_scoring_key_path",
        ),
        "development_slot_inventory": _validate_relative_path(
            slot_inventory_path,
            context="development_slot_inventory_path",
        ),
    }
    if len(set(normalized_paths.values())) != len(normalized_paths):
        raise BlindContractError("development artifact paths must be distinct")
    slot_entry, slots = _development_artifact_entry(
        root,
        "development_slot_inventory",
        normalized_paths["development_slot_inventory"],
    )
    key_entry, _ = _development_artifact_entry(
        root,
        "development_scoring_key",
        normalized_paths["development_scoring_key"],
        expected_slots=slots,
    )
    by_role = {
        "development_scoring_key": key_entry,
        "development_slot_inventory": slot_entry,
    }
    return [by_role[role] for role in REQUIRED_DEVELOPMENT_ARTIFACT_ROLES]


def build_evaluation_commitment(
    artifact_root: Path,
    *,
    blind_bundle_root: Path,
    blind_bundle_manifest: Mapping[str, Any],
    evaluation_id: str,
    protocol_id: str,
    prediction_path: str,
    development_scoring_key_path: str,
    development_slot_inventory_path: str,
    auditor_artifact_paths: Mapping[str, str],
    sealed_evaluation_authorization: Mapping[str, Any],
) -> dict[str, Any]:
    """Commit handed-off auditor artifacts in the private evaluator realm.

    This builder is authority/evaluator-side and runs only after the isolated
    fold worker has handed off its prediction and auditor artifacts.  The
    private sealed authorization, raw execution registry, and raw cluster/model
    identifiers must never be mounted in the auditor worker realm.  The
    serialized commitment contains only the HMAC-derived fold token.
    """

    evaluation_id = _require_opaque_id(evaluation_id, context="evaluation_id")
    protocol_id = _require_opaque_id(protocol_id, context="protocol_id")
    bundle = validate_blind_bundle_manifest(blind_bundle_root, blind_bundle_manifest)
    _validate_sealed_evaluation_authorization_document(sealed_evaluation_authorization)
    if (
        blind_bundle_manifest["bundle_sha256"]
        != sealed_evaluation_authorization["blind_bundle_sha256"]
    ):
        raise BlindContractError("blind bundle is not the sealed authorization bundle")
    if not isinstance(auditor_artifact_paths, Mapping) or set(auditor_artifact_paths) != set(
        REQUIRED_AUDITOR_ARTIFACT_ROLES
    ):
        raise BlindContractError(
            "auditor artifacts must contain exactly the frozen required role set"
        )
    normalized_artifact_paths = {
        role: _validate_relative_path(path, context=f"auditor_artifact_paths.{role}")
        for role, path in auditor_artifact_paths.items()
    }
    if len(set(normalized_artifact_paths.values())) != len(normalized_artifact_paths):
        raise BlindContractError("auditor artifact paths must be unique")
    prediction = _prediction_entry(
        artifact_root,
        prediction_path,
        expected_slots=bundle["challenge_slots"],
    )
    artifacts = [
        _auditor_artifact_entry(artifact_root, role, normalized_artifact_paths[role])
        for role in REQUIRED_AUDITOR_ARTIFACT_ROLES
    ]
    development_artifacts = _build_development_artifacts(
        artifact_root,
        scoring_key_path=development_scoring_key_path,
        slot_inventory_path=development_slot_inventory_path,
    )
    development_by_role = {entry["role"]: entry for entry in development_artifacts}
    if (
        development_by_role["development_scoring_key"]["records_sha256"]
        != sealed_evaluation_authorization["development_scoring_key_sha256"]
        or development_by_role["development_slot_inventory"]["records_sha256"]
        != sealed_evaluation_authorization["development_slot_inventory_sha256"]
    ):
        raise BlindContractError(
            "development artifacts do not equal the payload-derived other-two-cluster material"
        )
    all_paths = [
        prediction["path"],
        *(entry["path"] for entry in artifacts),
        *(entry["path"] for entry in development_artifacts),
    ]
    if len(all_paths) != len(set(all_paths)):
        raise BlindContractError(
            "prediction, auditor, and development artifact paths must be pairwise distinct"
        )
    prospective_contract = dict(sealed_evaluation_authorization["prospective_contract"])

    commitment: dict[str, Any] = {
        "schema_version": CONTRACT_VERSION,
        "contract_type": EVALUATION_COMMITMENT_CONTRACT,
        "phase": "pre_reveal",
        "evaluation_id": evaluation_id,
        "protocol_id": protocol_id,
        "execution_lock_sha256": sealed_evaluation_authorization["execution_lock_sha256"],
        "sealed_evaluation_authorization_sha256": sealed_evaluation_authorization[
            "authorization_sha256"
        ],
        "fold_token": sealed_evaluation_authorization["fold_token"],
        "blind_bundle_sha256": blind_bundle_manifest["bundle_sha256"],
        "authority_commitments": dict(sealed_evaluation_authorization["authority_commitments"]),
        "prospective_contract": prospective_contract,
        "prediction_artifact": prediction,
        "development_artifacts": development_artifacts,
        "auditor_artifacts": artifacts,
        "security_boundary": _security_boundary(),
    }
    commitment["commitment_sha256"] = _self_address(commitment, "commitment_sha256")
    validate_evaluation_commitment(commitment)
    return commitment


def _validate_prediction_artifact_entry(entry: Any) -> None:
    if not isinstance(entry, Mapping):
        raise BlindContractError("prediction_artifact must be an object")
    expected = {
        "path",
        "bytes",
        "sha256",
        "media_type",
        "record_count",
        "challenge_slot_ids_sha256",
    }
    _require_exact_keys(entry, expected, context="prediction_artifact")
    _validate_relative_path(entry["path"], context="prediction_artifact.path")
    _require_positive_int(entry["bytes"], context="prediction_artifact.bytes")
    _require_sha256(entry["sha256"], context="prediction_artifact.sha256")
    if entry["media_type"] != "application/x-ndjson":
        raise BlindContractError("prediction artifact must be JSONL")
    _require_positive_int(entry["record_count"], context="prediction_artifact.record_count")
    _require_sha256(
        entry["challenge_slot_ids_sha256"],
        context="prediction_artifact.challenge_slot_ids_sha256",
    )


def _validate_auditor_artifacts(entries: Any) -> None:
    if not isinstance(entries, list):
        raise BlindContractError("auditor_artifacts must be a list")
    if len(entries) != len(REQUIRED_AUDITOR_ARTIFACT_ROLES):
        raise BlindContractError("auditor_artifacts must contain exactly one entry per role")
    roles: list[str] = []
    paths: list[str] = []
    expected = {"role", "path", "bytes", "sha256", "media_type"}
    for index, entry in enumerate(entries):
        context = f"auditor_artifacts[{index}]"
        if not isinstance(entry, Mapping):
            raise BlindContractError(f"{context} must be an object")
        _require_exact_keys(entry, expected, context=context)
        role = entry["role"]
        if role not in REQUIRED_AUDITOR_ARTIFACT_ROLES:
            raise BlindContractError(f"{context}.role is not a frozen auditor artifact role")
        path = _validate_relative_path(entry["path"], context=f"{context}.path")
        _require_positive_int(entry["bytes"], context=f"{context}.bytes")
        _require_sha256(entry["sha256"], context=f"{context}.sha256")
        if entry["media_type"] != "application/octet-stream":
            raise BlindContractError("auditor artifacts must use application/octet-stream")
        roles.append(role)
        paths.append(path)
    if roles != list(REQUIRED_AUDITOR_ARTIFACT_ROLES):
        raise BlindContractError(
            "auditor_artifacts must be in frozen role order with no duplicates"
        )
    if len(paths) != len(set(paths)):
        raise BlindContractError("auditor artifact paths must be unique")


def _validate_development_artifacts(entries: Any) -> None:
    if not isinstance(entries, list):
        raise BlindContractError("development_artifacts must be a list")
    if len(entries) != len(REQUIRED_DEVELOPMENT_ARTIFACT_ROLES):
        raise BlindContractError(
            "development_artifacts must contain exactly one entry per frozen role"
        )
    expected = {
        "role",
        "path",
        "bytes",
        "sha256",
        "media_type",
        "record_count",
        "records_sha256",
    }
    roles: list[str] = []
    paths: list[str] = []
    for index, entry in enumerate(entries):
        context = f"development_artifacts[{index}]"
        if not isinstance(entry, Mapping):
            raise BlindContractError(f"{context} must be an object")
        _require_exact_keys(entry, expected, context=context)
        role = entry["role"]
        if role not in REQUIRED_DEVELOPMENT_ARTIFACT_ROLES:
            raise BlindContractError(f"{context}.role is not a frozen development role")
        paths.append(_validate_relative_path(entry["path"], context=f"{context}.path"))
        _require_positive_int(entry["bytes"], context=f"{context}.bytes")
        _require_sha256(entry["sha256"], context=f"{context}.sha256")
        if entry["media_type"] != "application/x-ndjson":
            raise BlindContractError("development artifacts must be JSONL")
        _require_positive_int(entry["record_count"], context=f"{context}.record_count")
        _require_sha256(entry["records_sha256"], context=f"{context}.records_sha256")
        roles.append(role)
    if roles != list(REQUIRED_DEVELOPMENT_ARTIFACT_ROLES):
        raise BlindContractError(
            "development_artifacts must be in frozen role order with no duplicates"
        )
    if len(paths) != len(set(paths)):
        raise BlindContractError("development artifact paths must be unique")


def _verify_development_artifacts(
    root: Path,
    entries: Any,
) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    _validate_development_artifacts(entries)
    by_role = {entry["role"]: entry for entry in entries}
    slot_entry = by_role["development_slot_inventory"]
    slot_path = _verify_file_entry(
        root,
        slot_entry,
        context="development artifact role=development_slot_inventory",
    )
    slots = _development_records(
        slot_path.read_bytes(),
        role="development_slot_inventory",
        context=slot_entry["path"],
    )
    key_entry = by_role["development_scoring_key"]
    key_path = _verify_file_entry(
        root,
        key_entry,
        context="development artifact role=development_scoring_key",
    )
    key = _development_records(
        key_path.read_bytes(),
        role="development_scoring_key",
        context=key_entry["path"],
        expected_slots=slots,
    )
    for role, records in (
        ("development_scoring_key", key),
        ("development_slot_inventory", slots),
    ):
        entry = by_role[role]
        if len(records) != entry["record_count"]:
            raise BlindContractError(f"{role} record count changed after commitment")
        if _sha256_bytes(_canonical_json_bytes(records)) != entry["records_sha256"]:
            raise BlindContractError(f"{role} canonical records changed after commitment")
    return key, slots


def _validate_prospective_contract(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise BlindContractError("prospective_contract must be an object")
    expected = {
        "challenge_slot_schema_sha256",
        "prediction_schema_sha256",
        "scoring_key_schema_sha256",
        "scoring_contract_sha256",
        "scoring_source_sha256",
    }
    _require_exact_keys(value, expected, context="prospective_contract")
    for field in sorted(expected):
        _require_sha256(value[field], context=f"prospective_contract.{field}")


def validate_evaluation_commitment(commitment: Mapping[str, Any]) -> None:
    """Validate a serialized pre-reveal commitment without opening any key."""

    if not isinstance(commitment, Mapping):
        raise BlindContractError("evaluation commitment must be an object")
    expected = {
        "schema_version",
        "contract_type",
        "phase",
        "evaluation_id",
        "protocol_id",
        "execution_lock_sha256",
        "sealed_evaluation_authorization_sha256",
        "fold_token",
        "blind_bundle_sha256",
        "authority_commitments",
        "prospective_contract",
        "prediction_artifact",
        "development_artifacts",
        "auditor_artifacts",
        "security_boundary",
        "commitment_sha256",
    }
    _require_exact_keys(commitment, expected, context="evaluation commitment")
    if commitment["schema_version"] != CONTRACT_VERSION:
        raise BlindContractError("unsupported evaluation commitment schema_version")
    if commitment["contract_type"] != EVALUATION_COMMITMENT_CONTRACT:
        raise BlindContractError("unexpected evaluation commitment contract_type")
    if commitment["phase"] != "pre_reveal":
        raise BlindContractError("evaluation commitment phase must be pre_reveal")
    _require_opaque_id(commitment["evaluation_id"], context="evaluation_id")
    _require_opaque_id(commitment["protocol_id"], context="protocol_id")
    _require_sha256(commitment["execution_lock_sha256"], context="execution_lock_sha256")
    _require_sha256(
        commitment["sealed_evaluation_authorization_sha256"],
        context="sealed_evaluation_authorization_sha256",
    )
    _require_pairing_token(commitment["fold_token"], context="fold_token")
    _require_sha256(commitment["blind_bundle_sha256"], context="blind_bundle_sha256")
    _validate_authority_commitments(commitment["authority_commitments"])
    _validate_prospective_contract(commitment["prospective_contract"])
    _validate_prediction_artifact_entry(commitment["prediction_artifact"])
    _validate_development_artifacts(commitment["development_artifacts"])
    _validate_auditor_artifacts(commitment["auditor_artifacts"])
    artifact_paths = [
        commitment["prediction_artifact"]["path"],
        *(entry["path"] for entry in commitment["development_artifacts"]),
        *(entry["path"] for entry in commitment["auditor_artifacts"]),
    ]
    if len(artifact_paths) != len(set(artifact_paths)):
        raise BlindContractError(
            "prediction, development, and auditor artifact paths must be pairwise distinct"
        )
    _validate_security_boundary(commitment["security_boundary"], context="commitment")
    _require_sha256(commitment["commitment_sha256"], context="commitment_sha256")
    if commitment["commitment_sha256"] != _self_address(commitment, "commitment_sha256"):
        raise BlindContractError("evaluation commitment self-address mismatch")


def _verify_file_entry(root: Path, entry: Mapping[str, Any], *, context: str) -> Path:
    _, path = _safe_regular_file(root, entry["path"], context=context)
    if path.stat().st_size != entry["bytes"] or _sha256_file(path) != entry["sha256"]:
        raise BlindContractError(f"{context} changed after commitment")
    return path


def verify_commitment_closure(
    artifact_root: Path,
    commitment: Mapping[str, Any],
    *,
    blind_bundle_root: Path,
    blind_bundle_manifest: Mapping[str, Any],
    sealed_evaluation_authorization: Mapping[str, Any],
    expected_prospective_contract: Mapping[str, Any],
    revealed_evaluation_key_bytes: bytes,
    revealed_challenge_bundle_bytes: bytes,
    evaluation_nonce: bytes,
    challenge_nonce: bytes,
) -> dict[str, Any]:
    """Verify artifact immutability and authority precommitments after reveal.

    The returned closure contains digests but never a path to the evaluation
    key.  Its status proves hash closure only; capability separation must be
    supplied by the external authority boundary named in the contract.
    """

    validate_evaluation_commitment(commitment)
    _validate_sealed_evaluation_authorization_document(sealed_evaluation_authorization)
    commitment_authorization_fields = {
        "execution_lock_sha256": sealed_evaluation_authorization["execution_lock_sha256"],
        "sealed_evaluation_authorization_sha256": sealed_evaluation_authorization[
            "authorization_sha256"
        ],
        "fold_token": sealed_evaluation_authorization["fold_token"],
        "blind_bundle_sha256": sealed_evaluation_authorization["blind_bundle_sha256"],
        "prospective_contract": dict(sealed_evaluation_authorization["prospective_contract"]),
        "authority_commitments": dict(sealed_evaluation_authorization["authority_commitments"]),
    }
    for field, expected_value in commitment_authorization_fields.items():
        if commitment[field] != expected_value:
            raise BlindContractError(
                f"evaluation commitment drifted from sealed authorization={field}"
            )
    _validate_prospective_contract(expected_prospective_contract)
    if dict(commitment["prospective_contract"]) != dict(expected_prospective_contract):
        raise BlindContractError(
            "committed prospective hashes do not match the frozen execution contract"
        )
    bundle = validate_blind_bundle_manifest(blind_bundle_root, blind_bundle_manifest)
    if blind_bundle_manifest["bundle_sha256"] != commitment["blind_bundle_sha256"]:
        raise BlindContractError("blind bundle does not match the committed bundle address")
    if not isinstance(revealed_evaluation_key_bytes, bytes):
        raise BlindContractError("revealed_evaluation_key_bytes must be bytes")
    if not isinstance(revealed_challenge_bundle_bytes, bytes):
        raise BlindContractError("revealed_challenge_bundle_bytes must be bytes")
    evaluation_nonce = _require_nonce(evaluation_nonce, context="evaluation_nonce")
    challenge_nonce = _require_nonce(challenge_nonce, context="challenge_nonce")

    prediction_entry = commitment["prediction_artifact"]
    prediction_path = _verify_file_entry(
        artifact_root, prediction_entry, context="prediction artifact"
    )
    prediction_records = _prediction_records(
        prediction_path.read_bytes(),
        context=prediction_entry["path"],
        expected_slots=bundle["challenge_slots"],
    )
    prediction_slot_ids = sorted(record["challenge_slot_id"] for record in prediction_records)
    if len(prediction_records) != prediction_entry["record_count"]:
        raise BlindContractError("prediction record count changed after commitment")
    if (
        _sha256_bytes(_canonical_json_bytes(prediction_slot_ids))
        != prediction_entry["challenge_slot_ids_sha256"]
    ):
        raise BlindContractError("prediction challenge-slot set changed after commitment")
    for entry in commitment["auditor_artifacts"]:
        _verify_file_entry(
            artifact_root,
            entry,
            context=f"auditor artifact role={entry['role']}",
        )
    development_key, development_slots = _verify_development_artifacts(
        artifact_root,
        commitment["development_artifacts"],
    )

    authority = commitment["authority_commitments"]
    evaluation_digest = _authority_digest(
        b"ltt-evaluation-key-v1", evaluation_nonce, revealed_evaluation_key_bytes
    )
    challenge_digest = _authority_digest(
        b"ltt-challenge-bundle-v1", challenge_nonce, revealed_challenge_bundle_bytes
    )
    if evaluation_digest != authority["evaluation_key_commitment"]:
        raise BlindContractError("revealed evaluation key does not close its authority commitment")
    if challenge_digest != authority["challenge_bundle_commitment"]:
        raise BlindContractError(
            "revealed challenge bundle does not close its authority commitment"
        )

    scoring_key_rows = _parse_jsonl_bytes(
        revealed_evaluation_key_bytes, context="revealed evaluation key"
    )
    try:
        scoring_key = validate_challenge_scoring_key(scoring_key_rows, bundle["challenge_slots"])
    except ValueError as error:
        raise BlindContractError(f"invalid revealed challenge scoring key: {error}") from error

    observation_targets = {record["target_id"] for record in bundle["observations"]}
    prediction_targets = {record["target_id"] for record in prediction_records}
    scoring_targets = {record["target_id"] for record in scoring_key}
    if not observation_targets == prediction_targets == scoring_targets:
        raise BlindContractError(
            "weak observations, predictions, and scoring key must cover the same target set"
        )
    scoring_slot_ids = sorted(record["challenge_slot_id"] for record in scoring_key)
    if scoring_slot_ids != prediction_slot_ids:
        raise BlindContractError(
            "revealed scoring key does not match the committed prediction slot set"
        )

    development_targets = {record["target_id"] for record in development_key}
    development_slot_ids = {record["challenge_slot_id"] for record in development_key}
    development_clusters = {record["dependency_cluster_id"] for record in development_key}
    heldout_clusters = {record["dependency_cluster_id"] for record in scoring_key}
    if (
        development_targets & scoring_targets
        or development_slot_ids & set(scoring_slot_ids)
        or development_clusters & heldout_clusters
    ):
        raise BlindContractError(
            "development and heldout target, slot, and dependency-cluster identities "
            "must be disjoint"
        )

    weak_evidence = build_weak_observation_evidence(bundle["observations"])
    derived_input_hashes = {
        "weak_observation_records_sha256": weak_evidence["records_sha256"],
        "weak_observation_inventory_sha256": weak_evidence["composite_inventory_sha256"],
        "development_scoring_key_sha256": _sha256_bytes(_canonical_json_bytes(development_key)),
        "development_slot_inventory_sha256": _sha256_bytes(
            _canonical_json_bytes(development_slots)
        ),
        "heldout_scoring_key_sha256": _sha256_bytes(_canonical_json_bytes(scoring_key)),
        "heldout_slot_inventory_sha256": _sha256_bytes(
            _canonical_json_bytes(bundle["challenge_slots"])
        ),
    }
    prediction_records_sha256 = _sha256_bytes(_canonical_json_bytes(prediction_records))

    closure: dict[str, Any] = {
        "schema_version": CONTRACT_VERSION,
        "contract_type": COMMITMENT_CLOSURE_CONTRACT,
        "status": "artifact_closure_verified",
        "evaluation_id": commitment["evaluation_id"],
        "commitment_sha256": commitment["commitment_sha256"],
        "execution_lock_sha256": commitment["execution_lock_sha256"],
        "sealed_evaluation_authorization_sha256": commitment[
            "sealed_evaluation_authorization_sha256"
        ],
        "fold_token": commitment["fold_token"],
        "blind_bundle_sha256": commitment["blind_bundle_sha256"],
        "prediction_target_count": len(prediction_targets),
        "prediction_challenge_slot_count": len(prediction_slot_ids),
        "scoring_key_record_count": len(scoring_key),
        "development_scoring_key_record_count": len(development_key),
        "development_slot_inventory_record_count": len(development_slots),
        "derived_input_hashes": derived_input_hashes,
        "prediction_records_sha256": prediction_records_sha256,
        "prospective_contract": dict(commitment["prospective_contract"]),
        "revealed_evaluation_key_sha256": _sha256_bytes(revealed_evaluation_key_bytes),
        "revealed_challenge_bundle_sha256": _sha256_bytes(revealed_challenge_bundle_bytes),
        "security_boundary": _security_boundary(),
    }
    closure["closure_sha256"] = _self_address(closure, "closure_sha256")
    return closure


def evaluate_committed_candidate_fold_non_authoritative(
    artifact_root: Path,
    commitment: Mapping[str, Any],
    *,
    discovery_authorization: Mapping[str, Any],
    execution_lock: Mapping[str, Any],
    site_discovery_report: Mapping[str, Any],
    pre_auditor_query_ledger: Mapping[str, Any],
    sealed_evaluation_authorization: Mapping[str, Any],
    authority_secret: bytes,
    expected_parent_design_manifest_sha256: str,
    expected_parent_discovery_template_sha256: str,
    expected_parent_execution_template_sha256: str,
    blind_bundle_root: Path,
    blind_bundle_manifest: Mapping[str, Any],
    expected_prospective_contract: Mapping[str, Any],
    revealed_evaluation_key_bytes: bytes,
    revealed_challenge_bundle_bytes: bytes,
    evaluation_nonce: bytes,
    challenge_nonce: bytes,
) -> dict[str, Any]:
    """Verify and score one committed fold without authorizing the pilot.

    This fold-local helper intentionally accepts no
    candidate rows, baseline rows, precomputed closure, or expected normalized
    input hashes. Candidate predictions come only from the content-addressed
    prediction file; weak observations and heldout slots come only from the
    content-addressed blind bundle; development artifacts come only from their
    exact commitment roles; and the heldout key comes only from the nonce-bound
    authority opening.  It first authenticates the complete discovery/execution
    ancestry and the post-output, pre-auditor sealed authorization.  A
    Its local pass flag is descriptive only: it cannot authorize the pilot.
    Production use must call ``evaluate_committed_pilot_gate``, which closes all
    three prediction commitments before any heldout reveal and applies the gate
    to equal means across the three folds.
    """

    # Import locally: execution.py imports the frozen blind constants.  Calling
    # the concrete validators here, rather than accepting a caller callback,
    # prevents a no-op validator from becoming a fake trust root.
    from latent_trace_tomography.execution import (
        ExecutionContractError,
        validate_discovery_readiness,
        validate_execution_lock,
    )

    trusted_roots = {
        "expected_parent_design_manifest_sha256": expected_parent_design_manifest_sha256,
        "expected_parent_discovery_template_sha256": (expected_parent_discovery_template_sha256),
        "expected_parent_execution_template_sha256": (expected_parent_execution_template_sha256),
    }
    try:
        validate_discovery_readiness(
            discovery_authorization,
            authority_secret=authority_secret,
            **trusted_roots,
        )
        validate_execution_lock(
            execution_lock,
            authorization=discovery_authorization,
            site_discovery_report=site_discovery_report,
            expected_prospective_contract=expected_prospective_contract,
            **trusted_roots,
        )
    except ExecutionContractError as error:
        raise BlindContractError(
            f"sealed evaluation execution ancestry failed validation: {error}"
        ) from error
    material = verify_sealed_evaluation_authorization(
        sealed_evaluation_authorization,
        execution_lock=execution_lock,
        pre_auditor_query_ledger=pre_auditor_query_ledger,
        authority_secret=authority_secret,
        challenge_bundle_bytes=revealed_challenge_bundle_bytes,
        evaluation_key_bytes=revealed_evaluation_key_bytes,
        evaluation_nonce=evaluation_nonce,
        challenge_nonce=challenge_nonce,
        blind_bundle_root=blind_bundle_root,
        blind_bundle_manifest=blind_bundle_manifest,
    )

    closure = verify_commitment_closure(
        artifact_root,
        commitment,
        blind_bundle_root=blind_bundle_root,
        blind_bundle_manifest=blind_bundle_manifest,
        sealed_evaluation_authorization=sealed_evaluation_authorization,
        expected_prospective_contract=expected_prospective_contract,
        revealed_evaluation_key_bytes=revealed_evaluation_key_bytes,
        revealed_challenge_bundle_bytes=revealed_challenge_bundle_bytes,
        evaluation_nonce=evaluation_nonce,
        challenge_nonce=challenge_nonce,
    )

    # Re-open every scoring input from the already verified, typed source. This
    # is deliberately redundant with closure verification: no caller-provided
    # object is allowed to bridge closure evidence to the pure scorer.
    bundle = validate_blind_bundle_manifest(blind_bundle_root, blind_bundle_manifest)
    prediction_entry = commitment["prediction_artifact"]
    prediction_path = _verify_file_entry(
        artifact_root,
        prediction_entry,
        context="prediction artifact",
    )
    predictions = _prediction_records(
        prediction_path.read_bytes(),
        context=prediction_entry["path"],
        expected_slots=bundle["challenge_slots"],
    )
    development_key, development_slots = _verify_development_artifacts(
        artifact_root,
        commitment["development_artifacts"],
    )
    if tuple(development_key) != tuple(material["development_key"]) or tuple(
        development_slots
    ) != tuple(material["development_slots"]):
        raise BlindContractError(
            "committed development files differ from payload-derived other-cluster data"
        )
    try:
        heldout_key = material["heldout_key"]
        gate_result = evaluate_verified_candidate_gate(
            predictions,
            heldout_key,
            bundle["challenge_slots"],
            weak_observations=bundle["observations"],
            development_scoring_key=development_key,
            development_slots=development_slots,
        )
    except ValueError as error:
        raise BlindContractError(f"committed prospective scoring failed: {error}") from error

    if gate_result["derived_input_hashes"] != closure["derived_input_hashes"]:
        raise BlindContractError(
            "pure scorer input hashes do not match the verified commitment closure"
        )
    prediction_records_sha256 = _sha256_bytes(_canonical_json_bytes(predictions))
    if prediction_records_sha256 != closure["prediction_records_sha256"]:
        raise BlindContractError(
            "pure scorer predictions do not match the verified commitment closure"
        )

    return {
        "schema_version": CONTRACT_VERSION,
        "contract_type": COMMITTED_GATE_RESULT_CONTRACT,
        "status": "fold_score_non_authoritative",
        "authoritative_for_pilot": False,
        "evaluation_id": commitment["evaluation_id"],
        "fold_token": commitment["fold_token"],
        "gate_result": gate_result,
        "closure_evidence": {
            "commitment_sha256": commitment["commitment_sha256"],
            "execution_lock_sha256": commitment["execution_lock_sha256"],
            "sealed_evaluation_authorization_sha256": commitment[
                "sealed_evaluation_authorization_sha256"
            ],
            "closure_sha256": closure["closure_sha256"],
            "derived_input_hashes": dict(closure["derived_input_hashes"]),
            "prediction_records_sha256": prediction_records_sha256,
            "security_boundary": _security_boundary(),
        },
    }


def evaluate_committed_candidate_gate(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Reject the retired single-fold production-gate name.

    A one-fold pass can be favorable while the frozen equal-three-fold gate
    fails.  Keeping this fail-closed shim avoids silently granting production
    authority to older integrations.
    """

    del args, kwargs
    raise BlindContractError(
        "single-fold scoring is non-authoritative; call evaluate_committed_pilot_gate"
    )


def _aggregate_equal_three_fold_gate(
    fold_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Apply the frozen pilot gate to equal means, never per-fold pass flags."""

    if len(fold_results) != SEALED_EVALUATION_FOLD_COUNT:
        raise BlindContractError("global gate requires exactly three fold scores")

    def equal_mean(path: tuple[str, ...]) -> float:
        values: list[float] = []
        for index, result in enumerate(fold_results):
            value: Any = result
            try:
                for field in path:
                    value = value[field]
            except (KeyError, TypeError) as error:
                raise BlindContractError(
                    f"fold_results[{index}] lacks global metric path={'.'.join(path)}"
                ) from error
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise BlindContractError("global fold metric must be numeric")
            numeric = float(value)
            if not math.isfinite(numeric) or numeric < 0.0:
                raise BlindContractError("global fold metric must be finite and non-negative")
            values.append(numeric)
        return math.fsum(values) / SEALED_EVALUATION_FOLD_COUNT

    candidate_loss = equal_mean(("gate_result", "candidate_score", PRIMARY_METRIC))
    candidate_brier = equal_mean(("gate_result", "candidate_score", SECONDARY_METRIC))
    candidate_coverage = equal_mean(
        (
            "gate_result",
            "candidate_score",
            "macro_dependency_cluster_slot_coverage",
        )
    )
    baseline_losses = {
        baseline_id: equal_mean(("gate_result", "baseline_scores", baseline_id, PRIMARY_METRIC))
        for baseline_id in BASELINE_PRIORITY
    }
    baseline_brier = {
        baseline_id: equal_mean(("gate_result", "baseline_scores", baseline_id, SECONDARY_METRIC))
        for baseline_id in BASELINE_PRIORITY
    }
    baseline_coverage = {
        baseline_id: equal_mean(
            (
                "gate_result",
                "baseline_scores",
                baseline_id,
                "macro_dependency_cluster_slot_coverage",
            )
        )
        for baseline_id in BASELINE_PRIORITY
    }
    priority = {baseline_id: index for index, baseline_id in enumerate(BASELINE_PRIORITY)}
    stronger_baseline_id = min(
        BASELINE_PRIORITY,
        key=lambda baseline_id: (baseline_losses[baseline_id], priority[baseline_id]),
    )
    stronger_loss = baseline_losses[stronger_baseline_id]
    maximum_passing_loss = (1.0 - PRIMARY_GATE_RELATIVE_REDUCTION) * stronger_loss
    observed_reduction = (
        (stronger_loss - candidate_loss) / stronger_loss if stronger_loss > 0.0 else None
    )
    passes = stronger_loss > 0.0 and candidate_loss <= maximum_passing_loss + GATE_NUMERIC_TOLERANCE
    return {
        "primary_metric": PRIMARY_METRIC,
        "aggregation": "equal_mean_over_three_one_cluster_heldout_fold_scores",
        "required_relative_reduction": PRIMARY_GATE_RELATIVE_REDUCTION,
        "candidate_log_loss": candidate_loss,
        "baseline_log_losses": baseline_losses,
        "candidate_multiclass_brier": candidate_brier,
        "baseline_multiclass_brier": baseline_brier,
        "candidate_slot_coverage": candidate_coverage,
        "baseline_slot_coverage": baseline_coverage,
        "stronger_baseline_id": stronger_baseline_id,
        "stronger_baseline_log_loss": stronger_loss,
        "maximum_passing_candidate_log_loss": maximum_passing_loss,
        "observed_relative_reduction": observed_reduction,
        "passes_primary_gate": passes,
    }


def evaluate_committed_pilot_gate(
    fold_runs: Sequence[Mapping[str, Any]],
    *,
    authority_opening_provider: Callable[[Mapping[str, Any]], Mapping[str, bytes]],
    discovery_authorization: Mapping[str, Any],
    execution_lock: Mapping[str, Any],
    site_discovery_report: Mapping[str, Any],
    pre_auditor_query_ledger: Mapping[str, Any],
    authority_secret: bytes,
    expected_parent_design_manifest_sha256: str,
    expected_parent_discovery_template_sha256: str,
    expected_parent_execution_template_sha256: str,
    expected_prospective_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Authoritatively evaluate the frozen equal-three-fold LOCO pilot.

    Each cluster is development material in two folds and held out in one.  A
    sequential reveal would therefore leak a later fold's outcomes.  This
    coordinator verifies that all three candidate commitments are immutable and
    cover the exact three clusters before it invokes the authority opening
    provider.  Reveal bytes are therefore absent from ``fold_runs``.  The
    provider is only a post-barrier delivery mechanism: every returned byte is
    independently opened and rederived, never trusted as a validation callback.
    Fold scores are descriptive; only the equal mean across all three folds is
    compared with the globally stronger named baseline.
    """

    if not isinstance(fold_runs, Sequence) or isinstance(fold_runs, (str, bytes)):
        raise BlindContractError("fold_runs must be a sequence")
    if len(fold_runs) != SEALED_EVALUATION_FOLD_COUNT:
        raise BlindContractError("pilot scoring requires exactly three fold commitments")
    if not callable(authority_opening_provider):
        raise BlindContractError("authority_opening_provider must be callable")
    required = {
        "artifact_root",
        "commitment",
        "blind_bundle_root",
        "blind_bundle_manifest",
        "sealed_evaluation_authorization",
    }
    expected_lock_sha256 = _canonical_artifact_sha256(execution_lock)
    from latent_trace_tomography.execution import (
        ExecutionContractError,
        validate_discovery_readiness,
        validate_execution_lock,
    )

    trusted_roots = {
        "expected_parent_design_manifest_sha256": expected_parent_design_manifest_sha256,
        "expected_parent_discovery_template_sha256": (expected_parent_discovery_template_sha256),
        "expected_parent_execution_template_sha256": (expected_parent_execution_template_sha256),
    }
    try:
        validate_discovery_readiness(
            discovery_authorization,
            authority_secret=authority_secret,
            **trusted_roots,
        )
        validate_execution_lock(
            execution_lock,
            authorization=discovery_authorization,
            site_discovery_report=site_discovery_report,
            expected_prospective_contract=expected_prospective_contract,
            **trusted_roots,
        )
    except ExecutionContractError as error:
        raise BlindContractError(f"pilot execution ancestry failed validation: {error}") from error
    _validate_pre_auditor_query_ledger(pre_auditor_query_ledger, execution_lock=execution_lock)
    cluster_records = execution_lock.get("dependency_clusters")
    if not isinstance(cluster_records, list) or len(cluster_records) != 3:
        raise BlindContractError("pilot execution lock must contain exactly three clusters")
    expected_clusters = {
        record.get("dependency_cluster_id")
        for record in cluster_records
        if isinstance(record, Mapping)
    }
    observed_clusters: set[str] = set()
    commitment_hashes: set[str] = set()
    fold_tokens: set[str] = set()
    capability_ids: set[str] = set()
    common_anchors: dict[str, Any] | None = None
    common_method_artifact_hashes: dict[str, str] | None = None
    ordered_runs: list[Mapping[str, Any]] = []

    identity_records = [
        record for record in execution_lock.get("model_registry", []) if isinstance(record, Mapping)
    ] + [record for record in cluster_records if isinstance(record, Mapping)]
    private_identifiers = {
        value
        for record in identity_records
        for field in PRIVATE_EXECUTION_IDENTITY_FIELDS
        if isinstance((value := record.get(field)), str) and value
    }

    # Phase one: no authority opening or scoring.  Revalidate every committed
    # candidate and bundle so the complete barrier exists first.
    for index, run in enumerate(fold_runs):
        if not isinstance(run, Mapping):
            raise BlindContractError(f"fold_runs[{index}] must be an object")
        _require_exact_keys(run, required, context=f"fold_runs[{index}]")
        commitment = run["commitment"]
        authorization = run["sealed_evaluation_authorization"]
        validate_evaluation_commitment(commitment)
        _validate_sealed_evaluation_authorization_document(authorization)
        method_artifact_hashes = {
            entry["role"]: entry["sha256"]
            for entry in commitment["auditor_artifacts"]
            if entry["role"] in METHOD_DEFINING_AUDITOR_ARTIFACT_ROLES
        }
        if set(method_artifact_hashes) != set(METHOD_DEFINING_AUDITOR_ARTIFACT_ROLES):
            raise BlindContractError("pilot fold lacks the frozen method artifact roles")
        if common_method_artifact_hashes is None:
            common_method_artifact_hashes = method_artifact_hashes
        elif method_artifact_hashes != common_method_artifact_hashes:
            raise BlindContractError("method-defining auditor artifact hashes differ across folds")
        development_by_role = {
            entry["role"]: entry for entry in commitment["development_artifacts"]
        }
        expected_development_hashes = {
            "development_scoring_key": authorization["development_scoring_key_sha256"],
            "development_slot_inventory": authorization["development_slot_inventory_sha256"],
        }
        for role, expected_hash in expected_development_hashes.items():
            if development_by_role[role]["records_sha256"] != expected_hash:
                raise BlindContractError(
                    "committed development material detached from its sealed "
                    f"authorization role={role}"
                )
        if (
            commitment["execution_lock_sha256"] != expected_lock_sha256
            or authorization["execution_lock_sha256"] != expected_lock_sha256
        ):
            raise BlindContractError("pilot fold targets another execution lock")
        if (
            commitment["sealed_evaluation_authorization_sha256"]
            != authorization["authorization_sha256"]
            or commitment["fold_token"] != authorization["fold_token"]
            or commitment["blind_bundle_sha256"] != authorization["blind_bundle_sha256"]
        ):
            raise BlindContractError("pilot commitment is detached from its sealed authorization")
        anchors = {
            "parent_design_manifest_sha256": authorization["parent_design_manifest_sha256"],
            "execution_lock_sha256": authorization["execution_lock_sha256"],
            "pre_auditor_query_ledger_sha256": authorization["pre_auditor_query_ledger_sha256"],
            "pilot_barrier_id": authorization["pilot_barrier_id"],
            "prospective_contract": dict(authorization["prospective_contract"]),
            "sealed_weak_trials_sha256": authorization["sealed_weak_trials_sha256"],
            "sealed_challenge_trials_sha256": authorization["sealed_challenge_trials_sha256"],
        }
        if common_anchors is None:
            common_anchors = anchors
        elif anchors != common_anchors:
            raise BlindContractError(
                "pilot folds do not share one design, ledger, raw evidence roots, "
                "prospective contract, and reveal barrier"
            )
        if anchors["parent_design_manifest_sha256"] != (expected_parent_design_manifest_sha256):
            raise BlindContractError("pilot fold targets another design manifest")
        if anchors["prospective_contract"] != dict(expected_prospective_contract):
            raise BlindContractError("pilot fold prospective contract drifted")
        capability_id = authorization["fold_worker_capability_id"]
        if capability_id in capability_ids:
            raise BlindContractError(
                "pilot fold workers must declare three distinct capability realms"
            )
        capability_ids.add(capability_id)
        fold_token = authorization["fold_token"]
        if fold_token in fold_tokens:
            raise BlindContractError("pilot contains a duplicate opaque fold token")
        fold_tokens.add(fold_token)
        cluster_id = authorization["heldout_dependency_cluster_id"]
        if cluster_id in observed_clusters:
            raise BlindContractError("pilot contains a duplicate heldout dependency cluster")
        observed_clusters.add(cluster_id)
        commitment_hash = commitment["commitment_sha256"]
        if commitment_hash in commitment_hashes:
            raise BlindContractError("pilot contains a duplicate prediction commitment")
        commitment_hashes.add(commitment_hash)
        bundle = validate_blind_bundle_manifest(
            Path(run["blind_bundle_root"]), run["blind_bundle_manifest"]
        )
        if run["blind_bundle_manifest"]["bundle_sha256"] != commitment["blind_bundle_sha256"]:
            raise BlindContractError("pilot blind bundle detached from prediction commitment")
        prediction_entry = commitment["prediction_artifact"]
        prediction_path = _verify_file_entry(
            Path(run["artifact_root"]),
            prediction_entry,
            context=f"fold_runs[{index}] prediction artifact",
        )
        prediction_bytes = prediction_path.read_bytes()
        _prediction_records(
            prediction_bytes,
            context=prediction_entry["path"],
            expected_slots=bundle["challenge_slots"],
        )
        development_surface = bytearray()
        for entry in commitment["development_artifacts"]:
            path = _verify_file_entry(
                Path(run["artifact_root"]),
                entry,
                context=f"fold_runs[{index}] development artifact",
            )
            development_surface.extend(path.read_bytes())
        auditor_artifact_surface = bytearray()
        for entry in commitment["auditor_artifacts"]:
            path = _verify_file_entry(
                Path(run["artifact_root"]),
                entry,
                context=f"fold_runs[{index}] auditor artifact role={entry['role']}",
            )
            auditor_artifact_surface.extend(path.read_bytes())
        _assert_no_private_identifier_leak(
            private_identifiers,
            {
                "blind_bundle": _canonical_json_bytes(
                    {"manifest": run["blind_bundle_manifest"], "records": bundle}
                ),
                "development_files": bytes(development_surface),
                "prediction_file": prediction_bytes,
                "auditor_artifact_files": bytes(auditor_artifact_surface),
                "serialized_commitment": _canonical_json_bytes(commitment),
            },
        )
        ordered_runs.append(run)
    if observed_clusters != expected_clusters or len(expected_clusters) != 3:
        raise BlindContractError("pilot folds do not hold out each frozen cluster exactly once")

    if len(capability_ids) != SEALED_EVALUATION_FOLD_COUNT:
        raise BlindContractError("pilot does not declare exactly three capability realms")

    # Phase two begins only after all three predictions passed the immutable
    # barrier.  The capability declarations are auditable claims, not physical
    # attestation.  Reveals remain evaluator-local and are never returned.
    ordered_runs = sorted(
        ordered_runs,
        key=lambda item: item["sealed_evaluation_authorization"]["heldout_dependency_cluster_id"],
    )
    materials: list[Mapping[str, Any]] = []
    openings: list[Mapping[str, bytes]] = []
    for run in ordered_runs:
        opening = authority_opening_provider(run["sealed_evaluation_authorization"])
        if not isinstance(opening, Mapping):
            raise BlindContractError("authority opening provider must return an object")
        _require_exact_keys(
            opening,
            {
                "revealed_evaluation_key_bytes",
                "revealed_challenge_bundle_bytes",
                "evaluation_nonce",
                "challenge_nonce",
            },
            context="authority opening",
        )
        if any(not isinstance(value, bytes) for value in opening.values()):
            raise BlindContractError("every authority opening value must be bytes")
        openings.append(opening)
        materials.append(
            verify_sealed_evaluation_authorization(
                run["sealed_evaluation_authorization"],
                execution_lock=execution_lock,
                pre_auditor_query_ledger=pre_auditor_query_ledger,
                authority_secret=authority_secret,
                challenge_bundle_bytes=opening["revealed_challenge_bundle_bytes"],
                evaluation_key_bytes=opening["revealed_evaluation_key_bytes"],
                evaluation_nonce=opening["evaluation_nonce"],
                challenge_nonce=opening["challenge_nonce"],
                blind_bundle_root=Path(run["blind_bundle_root"]),
                blind_bundle_manifest=run["blind_bundle_manifest"],
            )
        )
    for index, material in enumerate(materials):
        other_materials = [
            other for other_index, other in enumerate(materials) if other_index != index
        ]
        expected_development_slots = validate_challenge_slot_inventory(
            slot for other in other_materials for slot in other["heldout_slots"]
        )
        retokenized_other_keys = []
        for other in other_materials:
            current_fold_cluster_token = material["cluster_tokens"][
                other["heldout_dependency_cluster_id"]
            ]
            for row in other["heldout_key"]:
                retokenized_other_keys.append(
                    {**row, "dependency_cluster_id": current_fold_cluster_token}
                )
        expected_development_key = validate_challenge_scoring_key(
            retokenized_other_keys,
            expected_development_slots,
        )
        if tuple(material["development_slots"]) != tuple(expected_development_slots) or tuple(
            material["development_key"]
        ) != tuple(expected_development_key):
            raise BlindContractError(
                "fold development material is not the exact fold-local-retokenized "
                "union of the other two folds' heldout material"
            )

    results: list[dict[str, Any]] = []
    for run, opening in zip(ordered_runs, openings, strict=True):
        results.append(
            evaluate_committed_candidate_fold_non_authoritative(
                Path(run["artifact_root"]),
                run["commitment"],
                discovery_authorization=discovery_authorization,
                execution_lock=execution_lock,
                site_discovery_report=site_discovery_report,
                pre_auditor_query_ledger=pre_auditor_query_ledger,
                sealed_evaluation_authorization=run["sealed_evaluation_authorization"],
                authority_secret=authority_secret,
                expected_parent_design_manifest_sha256=(expected_parent_design_manifest_sha256),
                expected_parent_discovery_template_sha256=(
                    expected_parent_discovery_template_sha256
                ),
                expected_parent_execution_template_sha256=(
                    expected_parent_execution_template_sha256
                ),
                blind_bundle_root=Path(run["blind_bundle_root"]),
                blind_bundle_manifest=run["blind_bundle_manifest"],
                expected_prospective_contract=expected_prospective_contract,
                revealed_evaluation_key_bytes=opening["revealed_evaluation_key_bytes"],
                revealed_challenge_bundle_bytes=opening["revealed_challenge_bundle_bytes"],
                evaluation_nonce=opening["evaluation_nonce"],
                challenge_nonce=opening["challenge_nonce"],
            )
        )
    pilot_result: dict[str, Any] = {
        "schema_version": CONTRACT_VERSION,
        "contract_type": "ltt.committed_pilot_gate_result",
        "status": "pilot_scored_after_all_fold_commitments_closed_before_any_reveal",
        "execution_lock_sha256": expected_lock_sha256,
        "pilot_barrier_id": common_anchors["pilot_barrier_id"],
        "fold_count": SEALED_EVALUATION_FOLD_COUNT,
        "capability_realm_declarations": {
            "fold_worker_capability_ids": sorted(capability_ids),
            "contract": dict(FOLD_WORKER_CAPABILITY_CONTRACT),
        },
        "method_defining_auditor_artifact_hashes": dict(common_method_artifact_hashes),
        "output_runtime_evidence": dict(OUTPUT_RUNTIME_EVIDENCE_BOUNDARY),
        "global_gate_result": _aggregate_equal_three_fold_gate(results),
        "fold_results": results,
    }
    pilot_result["result_sha256"] = _self_address(pilot_result, "result_sha256")
    return pilot_result
