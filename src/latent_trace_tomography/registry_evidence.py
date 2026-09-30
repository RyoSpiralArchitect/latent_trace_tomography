"""Fail-closed local evidence catalogs for the OSS-1 registry authoring bundle.

The v1 dependency registry deliberately records only a content-addressed
``source_records`` envelope.  This successor module does not change that
contract.  It closes a separate, local authoring bundle by binding every v1
source record to exactly one typed JSON payload and by checking both the raw
file bytes and the canonical JSON content.

The typed payloads establish evidence identity, not truth, completeness,
statistical independence, or an interpretation of the evidence body.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from .artifact_hash import canonical_artifact_sha256


SCHEMA_VERSION = "0.1.0"
CATALOG_TYPE = "source_evidence_catalog_v2"
CATALOG_STATUS = "identity_payloads_closed_not_evidence_sufficient"
PAYLOAD_DIRECTORY = "payloads"

SOURCE_RECORD_FIELDS = {
    "source_record_id",
    "source_kind",
    "content_sha256",
    "locator_sha256",
    "evidence_status",
    "recorded_at",
    "source_record_sha256",
}
CATALOG_FIELDS = {
    "schema_version",
    "catalog_type",
    "status",
    "catalog_id",
    "created_at",
    "payload_directory",
    "entries",
    "catalog_body_sha256",
}
ENTRY_FIELDS = {
    "source_record_id",
    "source_kind",
    "content_sha256",
    "locator_sha256",
    "source_record_sha256",
    "relative_path",
    "raw_file_sha256",
    "payload_schema_kind",
}
PAYLOAD_FIELDS = {
    "schema_version",
    "payload_schema_kind",
    "source_kind",
    "source_record_id",
    "payload_id",
    "created_at",
    "identity",
    "evidence",
}

SOURCE_KIND_TO_PAYLOAD_SCHEMA_KIND = {
    "model_manifest": "model_evidence_v1",
    "tokenizer_manifest": "tokenizer_evidence_v1",
    "checkpoint_manifest": "checkpoint_evidence_v1",
    "training_run_manifest": "training_run_evidence_v1",
    "initialization_manifest": "initialization_evidence_v1",
    "rng_manifest": "rng_evidence_v1",
    "training_recipe_manifest": "training_recipe_evidence_v1",
    "training_data_manifest": "training_data_evidence_v1",
    "task_manifest": "task_evidence_v1",
    "ancestry_manifest": "ancestry_evidence_v1",
    "overlap_scan_manifest": "overlap_evidence_v1",
    "evaluation_exposure_scan_manifest": "evaluation_exposure_evidence_v1",
    "environment_manifest": "environment_evidence_v1",
}

# This first typed layer validates only evidence identity.  Kind-specific
# claims remain deliberately opaque inside ``evidence`` until a later schema
# freezes their semantics.
IDENTITY_FIELDS: dict[str, dict[str, str]] = {
    "model_evidence_v1": {
        "model_unit_id": "text",
        "model_artifact_sha256": "sha256",
    },
    "tokenizer_evidence_v1": {
        "model_unit_id": "text",
        "tokenizer_revision": "text",
        "tokenizer_artifact_sha256": "sha256",
    },
    "checkpoint_evidence_v1": {
        "model_unit_id": "text",
        "checkpoint_id": "text",
        "checkpoint_artifact_sha256": "sha256",
    },
    "training_run_evidence_v1": {
        "model_unit_id": "text",
        "training_run_id": "text",
        "descendant_model_artifact_sha256": "sha256",
    },
    "initialization_evidence_v1": {
        "model_unit_id": "text",
        "initialization_state_artifact_sha256": "sha256",
    },
    "rng_evidence_v1": {
        "model_unit_id": "text",
        "rng_manifest_sha256": "sha256",
        "initialization_state_artifact_sha256": "sha256",
    },
    "training_recipe_evidence_v1": {
        "model_unit_id": "text",
        "training_recipe_sha256": "sha256",
    },
    "training_data_evidence_v1": {
        "model_unit_id": "text",
        "stage_id": "text",
        "scope": "text",
        "record_identity_scheme_id": "text",
    },
    "task_evidence_v1": {
        "model_unit_id": "text",
        "task_manifest_sha256": "sha256",
        "generator_artifact_sha256": "sha256",
        "template_set_sha256": "sha256",
    },
    "ancestry_evidence_v1": {
        "inventory_id": "text",
        "inventory_sha256": "sha256",
    },
    "overlap_evidence_v1": {
        "left_model_unit_id": "text",
        "right_model_unit_id": "text",
        "declared_scope": "text",
        "identity_scheme_id": "text",
    },
    "evaluation_exposure_evidence_v1": {
        "model_unit_id": "text",
        "scan_scope_id": "text",
    },
    "environment_evidence_v1": {
        "environment_id": "text",
        "environment_manifest_sha256": "sha256",
    },
}

EVIDENCE_STATUSES = {
    "complete_content_addressed",
    "partial_content_addressed",
    "authority_attested_only",
    "unavailable",
}


class RegistryEvidenceError(ValueError):
    """Raised when a source evidence catalog does not close exactly."""


def _mapping(value: Any, *, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RegistryEvidenceError(f"{context} must be an object")
    return value


def _sequence(value: Any, *, context: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise RegistryEvidenceError(f"{context} must be an array")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], *, context: str) -> None:
    observed = set(value)
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise RegistryEvidenceError(f"{context} fields differ; missing={missing}, extra={extra}")


def _text(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise RegistryEvidenceError(f"{context} must be non-empty text")
    return value


def _sha256(value: Any, *, context: str) -> str:
    digest = _text(value, context=context)
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise RegistryEvidenceError(f"{context} must be lowercase SHA-256")
    if digest == "0" * 64:
        raise RegistryEvidenceError(f"{context} must not be an all-zero placeholder")
    return digest


def _timestamp(value: Any, *, context: str) -> datetime:
    text = _text(value, context=context)
    if not text.endswith("Z"):
        raise RegistryEvidenceError(f"{context} must be an RFC 3339 UTC timestamp ending Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as error:
        raise RegistryEvidenceError(f"{context} must be a valid timestamp") from error
    if parsed.tzinfo != timezone.utc:
        raise RegistryEvidenceError(f"{context} must be UTC")
    return parsed


def _assert_json_domain(value: Any, *, context: str) -> None:
    """Reject values that canonical ``json.dumps`` would accept non-standardly."""

    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RegistryEvidenceError(f"{context} contains a non-finite number")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RegistryEvidenceError(f"{context} contains a non-text object key")
            _assert_json_domain(item, context=f"{context}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _assert_json_domain(item, context=f"{context}[{index}]")
        return
    raise RegistryEvidenceError(f"{context} contains a value outside the JSON data model")


def canonical_locator_sha256(relative_path: str) -> str:
    """Address one normalized, catalog-relative payload locator."""

    normalized = _normalized_relative_path(relative_path)
    return canonical_artifact_sha256({"relative_path": normalized})


def source_record_sha256(source_record: Mapping[str, Any]) -> str:
    """Return the v1 source-record self hash after exact envelope validation."""

    record = _mapping(source_record, context="source_record")
    _exact_keys(record, SOURCE_RECORD_FIELDS, context="source_record")
    return canonical_artifact_sha256(
        {field: record[field] for field in SOURCE_RECORD_FIELDS if field != "source_record_sha256"}
    )


def catalog_body_sha256(catalog: Mapping[str, Any]) -> str:
    """Return the canonical catalog self hash, excluding its hash field."""

    body = _mapping(catalog, context="catalog")
    _exact_keys(body, CATALOG_FIELDS, context="catalog")
    return canonical_artifact_sha256(
        {field: body[field] for field in CATALOG_FIELDS if field != "catalog_body_sha256"}
    )


def raw_file_sha256(path: str | Path) -> str:
    """Hash the exact bytes of a regular, already-authorized local path."""

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _normalized_relative_path(value: Any) -> str:
    relative_path = _text(value, context="relative_path")
    if "\\" in relative_path:
        raise RegistryEvidenceError("relative_path must use POSIX separators")
    path = PurePosixPath(relative_path)
    if path.is_absolute():
        raise RegistryEvidenceError("relative_path must not be absolute")
    if relative_path != path.as_posix() or any(part in {"", ".", ".."} for part in path.parts):
        raise RegistryEvidenceError("relative_path must be normalized and traversal-free")
    if len(path.parts) < 2 or path.parts[0] != PAYLOAD_DIRECTORY:
        raise RegistryEvidenceError(f"relative_path must be below {PAYLOAD_DIRECTORY}/")
    if path.suffix != ".json":
        raise RegistryEvidenceError("catalog payloads must have a .json suffix")
    return relative_path


def _safe_regular_payload(catalog_root: Path, relative_path: str) -> Path:
    parts = PurePosixPath(relative_path).parts
    cursor = catalog_root
    for index, part in enumerate(parts):
        cursor = cursor / part
        try:
            metadata = cursor.lstat()
        except FileNotFoundError as error:
            raise RegistryEvidenceError(f"payload path does not exist: {relative_path}") from error
        if stat.S_ISLNK(metadata.st_mode):
            raise RegistryEvidenceError(f"payload path must not contain a symlink: {relative_path}")
        if index < len(parts) - 1 and not stat.S_ISDIR(metadata.st_mode):
            raise RegistryEvidenceError(f"payload parent is not a directory: {relative_path}")
        if index == len(parts) - 1 and not stat.S_ISREG(metadata.st_mode):
            raise RegistryEvidenceError(f"payload is not a regular file: {relative_path}")

    resolved_root = catalog_root.resolve(strict=True)
    resolved_payload = cursor.resolve(strict=True)
    try:
        resolved_payload.relative_to(resolved_root)
    except ValueError as error:
        raise RegistryEvidenceError(f"payload escapes the catalog root: {relative_path}") from error
    return cursor


def _reject_constant(value: str) -> None:
    raise RegistryEvidenceError(f"JSON contains non-standard numeric constant {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise RegistryEvidenceError(f"JSON object contains duplicate key {key!r}")
        value[key] = item
    return value


def _parse_json_object(raw: bytes, *, context: str) -> Mapping[str, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise RegistryEvidenceError(f"{context} must be UTF-8 JSON") from error
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except RegistryEvidenceError:
        raise
    except json.JSONDecodeError as error:
        raise RegistryEvidenceError(f"{context} is not valid JSON") from error
    return _mapping(value, context=context)


def _validate_source_records(
    value: Any,
) -> dict[str, Mapping[str, Any]]:
    records = _sequence(value, context="source_records")
    if not records:
        raise RegistryEvidenceError("source_records must not be empty")

    by_id: dict[str, Mapping[str, Any]] = {}
    observed_hashes: set[str] = set()
    ordered_ids: list[str] = []
    for index, raw_record in enumerate(records):
        context = f"source_records[{index}]"
        record = _mapping(raw_record, context=context)
        _exact_keys(record, SOURCE_RECORD_FIELDS, context=context)
        record_id = _text(record["source_record_id"], context=f"{context}.source_record_id")
        source_kind = _text(record["source_kind"], context=f"{context}.source_kind")
        if source_kind not in SOURCE_KIND_TO_PAYLOAD_SCHEMA_KIND:
            raise RegistryEvidenceError(f"{context}.source_kind is not supported by catalog v2")
        _sha256(record["content_sha256"], context=f"{context}.content_sha256")
        _sha256(record["locator_sha256"], context=f"{context}.locator_sha256")
        if record["evidence_status"] not in EVIDENCE_STATUSES:
            raise RegistryEvidenceError(f"{context}.evidence_status is not recognized")
        _timestamp(record["recorded_at"], context=f"{context}.recorded_at")
        observed_record_hash = _sha256(
            record["source_record_sha256"], context=f"{context}.source_record_sha256"
        )
        if observed_record_hash != source_record_sha256(record):
            raise RegistryEvidenceError(f"{context} is not self-addressed")
        if record_id in by_id or observed_record_hash in observed_hashes:
            raise RegistryEvidenceError("source_records contain a duplicate id or hash")
        by_id[record_id] = record
        observed_hashes.add(observed_record_hash)
        ordered_ids.append(record_id)

    if ordered_ids != sorted(ordered_ids):
        raise RegistryEvidenceError("source_records must be sorted by source_record_id")
    return by_id


def _validate_payload_envelope(
    payload: Mapping[str, Any],
    *,
    entry: Mapping[str, Any],
    context: str,
) -> datetime:
    _exact_keys(payload, PAYLOAD_FIELDS, context=context)
    if payload["schema_version"] != SCHEMA_VERSION:
        raise RegistryEvidenceError(f"{context}.schema_version is not supported")

    schema_kind = _text(payload["payload_schema_kind"], context=f"{context}.payload_schema_kind")
    if schema_kind != entry["payload_schema_kind"]:
        raise RegistryEvidenceError(f"{context}.payload_schema_kind does not match catalog entry")
    if payload["source_kind"] != entry["source_kind"]:
        raise RegistryEvidenceError(f"{context}.source_kind does not match catalog entry")
    if payload["source_record_id"] != entry["source_record_id"]:
        raise RegistryEvidenceError(f"{context}.source_record_id does not match catalog entry")
    _text(payload["payload_id"], context=f"{context}.payload_id")
    created_at = _timestamp(payload["created_at"], context=f"{context}.created_at")

    identity = _mapping(payload["identity"], context=f"{context}.identity")
    required = IDENTITY_FIELDS[schema_kind]
    _exact_keys(identity, set(required), context=f"{context}.identity")
    for field, field_type in required.items():
        if field_type == "sha256":
            _sha256(identity[field], context=f"{context}.identity.{field}")
        else:
            _text(identity[field], context=f"{context}.identity.{field}")
    _mapping(payload["evidence"], context=f"{context}.evidence")
    return created_at


def _observed_payload_files(catalog_root: Path) -> set[str]:
    payload_root = catalog_root / PAYLOAD_DIRECTORY
    try:
        root_metadata = payload_root.lstat()
    except FileNotFoundError as error:
        raise RegistryEvidenceError(f"catalog is missing {PAYLOAD_DIRECTORY}/") from error
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        raise RegistryEvidenceError(f"{PAYLOAD_DIRECTORY}/ must be a real directory")

    def fail_walk(error: OSError) -> None:
        raise RegistryEvidenceError("payload tree could not be enumerated completely") from error

    observed: set[str] = set()
    for directory, directory_names, file_names in os.walk(
        payload_root,
        followlinks=False,
        onerror=fail_walk,
    ):
        current = Path(directory)
        for name in directory_names:
            child = current / name
            if child.is_symlink():
                raise RegistryEvidenceError("payload tree must not contain symlink directories")
        for name in file_names:
            child = current / name
            if child.is_symlink():
                raise RegistryEvidenceError("payload tree must not contain symlink files")
            if not child.is_file():
                raise RegistryEvidenceError("payload tree must contain regular files only")
            observed.add(child.relative_to(catalog_root).as_posix())
    return observed


def validate_source_evidence_catalog(
    catalog: Mapping[str, Any],
    *,
    catalog_path: str | Path,
    source_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate a parsed catalog and every local payload it declares.

    ``catalog_path`` is the real location of the catalog file; payload locators
    are resolved only below its parent.  The supplied ``source_records`` are
    the authoritative v1 envelopes and must be covered exactly once.
    """

    _assert_json_domain(catalog, context="catalog")
    body = _mapping(catalog, context="catalog")
    _exact_keys(body, CATALOG_FIELDS, context="catalog")
    if body["schema_version"] != SCHEMA_VERSION:
        raise RegistryEvidenceError("catalog.schema_version is not supported")
    if body["catalog_type"] != CATALOG_TYPE:
        raise RegistryEvidenceError("catalog.catalog_type is not supported")
    if body["status"] != CATALOG_STATUS:
        raise RegistryEvidenceError("catalog.status is not closed")
    catalog_id = _text(body["catalog_id"], context="catalog.catalog_id")
    catalog_created_at = _timestamp(body["created_at"], context="catalog.created_at")
    if body["payload_directory"] != PAYLOAD_DIRECTORY:
        raise RegistryEvidenceError(f"catalog.payload_directory must be {PAYLOAD_DIRECTORY!r}")
    observed_catalog_hash = _sha256(
        body["catalog_body_sha256"], context="catalog.catalog_body_sha256"
    )
    if observed_catalog_hash != catalog_body_sha256(body):
        raise RegistryEvidenceError("catalog is not canonically self-addressed")

    authoritative = _validate_source_records(source_records)
    entries = _sequence(body["entries"], context="catalog.entries")
    if not entries:
        raise RegistryEvidenceError("catalog.entries must not be empty")

    path = Path(catalog_path)
    try:
        catalog_metadata = path.lstat()
    except FileNotFoundError as error:
        raise RegistryEvidenceError("catalog path does not exist") from error
    if stat.S_ISLNK(catalog_metadata.st_mode):
        raise RegistryEvidenceError("catalog path must not be a symlink")
    if not stat.S_ISREG(catalog_metadata.st_mode):
        raise RegistryEvidenceError("catalog path must be a regular file")
    on_disk_catalog = _parse_json_object(path.read_bytes(), context="catalog path")
    if on_disk_catalog != body:
        raise RegistryEvidenceError("catalog object differs from catalog_path bytes")
    catalog_root = path.parent.resolve(strict=True)
    entry_ids: list[str] = []
    entry_hashes: set[str] = set()
    declared_paths: set[str] = set()
    verified_payloads: list[dict[str, str]] = []

    for index, raw_entry in enumerate(entries):
        context = f"catalog.entries[{index}]"
        entry = _mapping(raw_entry, context=context)
        _exact_keys(entry, ENTRY_FIELDS, context=context)
        record_id = _text(entry["source_record_id"], context=f"{context}.source_record_id")
        if record_id not in authoritative:
            raise RegistryEvidenceError(f"{context} names an undeclared source_record_id")
        record = authoritative[record_id]
        record_hash = _sha256(
            entry["source_record_sha256"], context=f"{context}.source_record_sha256"
        )
        if record_hash in entry_hashes or record_id in entry_ids:
            raise RegistryEvidenceError("catalog entries contain a duplicate source")
        entry_ids.append(record_id)
        entry_hashes.add(record_hash)

        for field in (
            "source_kind",
            "content_sha256",
            "locator_sha256",
            "source_record_sha256",
        ):
            if entry[field] != record[field]:
                raise RegistryEvidenceError(f"{context}.{field} does not match source record")
        _sha256(entry["content_sha256"], context=f"{context}.content_sha256")
        _sha256(entry["locator_sha256"], context=f"{context}.locator_sha256")
        schema_kind = _text(entry["payload_schema_kind"], context=f"{context}.payload_schema_kind")
        expected_schema_kind = SOURCE_KIND_TO_PAYLOAD_SCHEMA_KIND[record["source_kind"]]
        if schema_kind != expected_schema_kind:
            raise RegistryEvidenceError(f"{context}.payload_schema_kind does not match source_kind")

        relative_path = _normalized_relative_path(entry["relative_path"])
        if relative_path in declared_paths:
            raise RegistryEvidenceError("catalog entries contain a duplicate relative_path")
        declared_paths.add(relative_path)
        if entry["locator_sha256"] != canonical_locator_sha256(relative_path):
            raise RegistryEvidenceError(f"{context}.locator_sha256 does not bind relative_path")

        payload_path = _safe_regular_payload(catalog_root, relative_path)
        raw = payload_path.read_bytes()
        expected_raw_hash = _sha256(entry["raw_file_sha256"], context=f"{context}.raw_file_sha256")
        if hashlib.sha256(raw).hexdigest() != expected_raw_hash:
            raise RegistryEvidenceError(f"{context}.raw_file_sha256 does not match payload bytes")
        payload = _parse_json_object(raw, context=relative_path)
        observed_content_hash = canonical_artifact_sha256(payload)
        if observed_content_hash != entry["content_sha256"]:
            raise RegistryEvidenceError(
                f"{context}.content_sha256 does not match canonical payload"
            )
        payload_created_at = _validate_payload_envelope(payload, entry=entry, context=relative_path)
        source_recorded_at = _timestamp(
            record["recorded_at"], context=f"source record {record_id}.recorded_at"
        )
        if not payload_created_at <= source_recorded_at <= catalog_created_at:
            raise RegistryEvidenceError(
                f"{context} payload/source/catalog chronology does not close"
            )
        verified_payloads.append(
            {
                "source_record_id": record_id,
                "source_kind": record["source_kind"],
                "relative_path": relative_path,
                "content_sha256": observed_content_hash,
                "raw_file_sha256": expected_raw_hash,
            }
        )

    if entry_ids != sorted(entry_ids):
        raise RegistryEvidenceError("catalog.entries must be sorted by source_record_id")
    if set(entry_ids) != set(authoritative):
        missing = sorted(set(authoritative) - set(entry_ids))
        extra = sorted(set(entry_ids) - set(authoritative))
        raise RegistryEvidenceError(
            f"catalog must cover every source exactly once; missing={missing}, extra={extra}"
        )

    observed_paths = _observed_payload_files(catalog_root)
    undeclared = sorted(observed_paths - declared_paths)
    missing_paths = sorted(declared_paths - observed_paths)
    if undeclared or missing_paths:
        raise RegistryEvidenceError(
            "payload JSON inventory differs from catalog; "
            f"undeclared={undeclared}, missing={missing_paths}"
        )

    return {
        "catalog_id": catalog_id,
        "catalog_body_sha256": observed_catalog_hash,
        "entry_count": len(verified_payloads),
        "source_record_ids": tuple(entry_ids),
        "verified_payloads": tuple(verified_payloads),
    }


def load_source_evidence_catalog(
    catalog_path: str | Path,
    *,
    source_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Load a non-symlink catalog file and validate its closed local bundle."""

    path = Path(catalog_path)
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise RegistryEvidenceError("catalog path does not exist") from error
    if stat.S_ISLNK(metadata.st_mode):
        raise RegistryEvidenceError("catalog path must not be a symlink")
    if not stat.S_ISREG(metadata.st_mode):
        raise RegistryEvidenceError("catalog path must be a regular file")
    catalog = _parse_json_object(path.read_bytes(), context="catalog")
    return validate_source_evidence_catalog(
        catalog,
        catalog_path=path,
        source_records=source_records,
    )


def load_and_validate_source_evidence_catalog(
    catalog_path: str | Path,
    *,
    source_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Explicit alias for callers that want the full operation in its name."""

    return load_source_evidence_catalog(catalog_path, source_records=source_records)
