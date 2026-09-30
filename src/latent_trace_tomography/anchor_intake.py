"""Metadata-only base-model intake for the controlled OSS-1 anchor successor."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .dependency_registry import (
    DESIGN_FREEZE_BOUNDARY,
    DependencyRegistryError,
    canonical_artifact_sha256,
)


SCHEMA_VERSION = "0.1.0"
INTAKE_TYPE = "controlled_anchor_base_model_intake_v1"
STATUS = "metadata_only_pre_training_frozen"
AUTHORIZATION_EFFECT = "none"
EXPECTED_PARENT = {
    "design_freeze_id": "oss_reliance_regime_v0_design_20260717",
    "design_manifest_sha256": ("8c974390ceea3f1defaae19067359c909b4182dd26c321075c9e25ee1518e64b"),
    "protocol_sha256": ("5c49316503b2cec2ad26d4bf47dc59c02f0b61d9f6896b84035e6d0412dced11"),
    "operational_manifest_sha256": (
        "d9ea2369a14983756dcb60cb985d4eabea10f2471f934a5c3598478dbf4dc93c"
    ),
}

TOP_LEVEL_FIELDS = {
    "schema_version",
    "intake_type",
    "status",
    "intake_id",
    "created_at",
    "parent",
    "retrieval_boundary",
    "records",
    "limitations",
    "authorization_effect",
    "intake_body_sha256",
}

RECORD_FIELDS = {
    "base_model_unit_id",
    "repo_id",
    "revision",
    "repository_created_at",
    "revision_last_modified_at",
    "architecture_family_id",
    "model_type",
    "license_id",
    "private",
    "gated",
    "source_urls",
    "model_config",
    "weight_artifact",
    "tokenizer_bundle",
    "record_sha256",
}


def _mapping(value: Any, *, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DependencyRegistryError(f"{context} must be an object")
    return value


def _sequence(value: Any, *, context: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise DependencyRegistryError(f"{context} must be an array")
    return value


def _text(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise DependencyRegistryError(f"{context} must be a non-empty string")
    return value


def _sha256(value: Any, *, context: str) -> str:
    text = _text(value, context=context)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise DependencyRegistryError(f"{context} must be lowercase SHA-256")
    if text == "0" * 64:
        raise DependencyRegistryError(f"{context} must not be an all-zero placeholder")
    return text


def _token_id_array(value: Any, *, context: str, min_items: int) -> list[int]:
    if not isinstance(value, list):
        raise DependencyRegistryError(f"{context} token IDs must be a JSON array")
    if len(value) < min_items:
        raise DependencyRegistryError(f"{context} token IDs are too short")
    if any(
        not isinstance(token_id, int) or isinstance(token_id, bool) or token_id < 0
        for token_id in value
    ):
        raise DependencyRegistryError(
            f"{context} token IDs must be nonnegative, non-boolean integers"
        )
    return list(value)


def _timestamp(value: Any, *, context: str) -> datetime:
    text = _text(value, context=context)
    if not text.endswith("Z"):
        raise DependencyRegistryError(f"{context} must use RFC3339 UTC Z")
    try:
        return datetime.fromisoformat(text[:-1] + "+00:00").astimezone(timezone.utc)
    except ValueError as error:
        raise DependencyRegistryError(f"{context} is not a valid timestamp") from error


def _body_hash(value: Mapping[str, Any], field: str) -> str:
    return canonical_artifact_sha256({key: value[key] for key in value if key != field})


def validate_anchor_base_model_intake(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an exact three-family metadata intake without granting authority."""

    intake = _mapping(value, context="base-model intake")
    if set(intake) != TOP_LEVEL_FIELDS:
        raise DependencyRegistryError("base-model intake fields are not exact")
    if (
        intake["schema_version"] != SCHEMA_VERSION
        or intake["intake_type"] != INTAKE_TYPE
        or intake["status"] != STATUS
    ):
        raise DependencyRegistryError("base-model intake identity drifted")
    _text(intake["intake_id"], context="intake_id")
    created_at = _timestamp(intake["created_at"], context="intake.created_at")
    parent = _mapping(intake["parent"], context="intake.parent")
    if dict(parent) != EXPECTED_PARENT:
        raise DependencyRegistryError("base-model intake parent drifted")
    boundary = _mapping(intake["retrieval_boundary"], context="retrieval_boundary")
    expected_boundary_fields = {
        "metadata_provider",
        "metadata_requests",
        "configuration_files_downloaded",
        "tokenizer_files_downloaded",
        "weight_files_downloaded",
        "model_loads",
        "forward_calls",
        "backward_calls",
        "generation_calls",
        "api_inference_calls",
    }
    if set(boundary) != expected_boundary_fields:
        raise DependencyRegistryError("retrieval boundary fields are not exact")
    if boundary["metadata_provider"] != "hugging_face_hub_public_api":
        raise DependencyRegistryError("metadata provider drifted")
    for field in (
        "metadata_requests",
        "configuration_files_downloaded",
        "tokenizer_files_downloaded",
    ):
        count = boundary[field]
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise DependencyRegistryError(f"retrieval boundary {field} must be nonnegative")
    for field in (
        "weight_files_downloaded",
        "model_loads",
        "forward_calls",
        "backward_calls",
        "generation_calls",
        "api_inference_calls",
    ):
        if boundary[field] != 0:
            raise DependencyRegistryError(f"metadata intake forbids nonzero {field}")

    records = _sequence(intake["records"], context="intake.records")
    if len(records) != 3:
        raise DependencyRegistryError("base-model intake requires exactly three records")
    order: list[str] = []
    families: set[str] = set()
    revisions: set[tuple[str, str]] = set()
    weights: set[str] = set()
    tokenizers: set[str] = set()
    for index, raw in enumerate(records):
        record = _mapping(raw, context=f"base record[{index}]")
        if set(record) != RECORD_FIELDS:
            raise DependencyRegistryError("base-model record fields are not exact")
        base_id = _text(record["base_model_unit_id"], context="base_model_unit_id")
        order.append(base_id)
        repo_id = _text(record["repo_id"], context=f"{base_id}.repo_id")
        revision = _text(record["revision"], context=f"{base_id}.revision")
        if len(revision) != 40 or any(char not in "0123456789abcdef" for char in revision):
            raise DependencyRegistryError("Hub revision must be immutable lowercase Git SHA-1")
        revisions.add((repo_id, revision))
        if (
            _timestamp(record["repository_created_at"], context=f"{base_id}.repository_created_at")
            >= DESIGN_FREEZE_BOUNDARY
            or _timestamp(
                record["revision_last_modified_at"],
                context=f"{base_id}.revision_last_modified_at",
            )
            >= DESIGN_FREEZE_BOUNDARY
        ):
            raise DependencyRegistryError("base repository revision must predate design freeze")
        families.add(_text(record["architecture_family_id"], context=f"{base_id}.family"))
        _text(record["model_type"], context=f"{base_id}.model_type")
        _text(record["license_id"], context=f"{base_id}.license")
        if record["private"] is not False or record["gated"] is not False:
            raise DependencyRegistryError("base models must be public and ungated")
        urls = _mapping(record["source_urls"], context=f"{base_id}.source_urls")
        if set(urls) != {"api", "immutable_tree"}:
            raise DependencyRegistryError("base source URLs are not exact")
        for field in urls:
            url = _text(urls[field], context=f"{base_id}.source_urls.{field}")
            if not url.startswith("https://huggingface.co/"):
                raise DependencyRegistryError("base source URL must be a Hugging Face URL")

        config = _mapping(record["model_config"], context=f"{base_id}.model_config")
        if set(config) != {
            "relative_path",
            "raw_sha256",
            "byte_size",
            "transformer_block_count",
            "hidden_size",
        }:
            raise DependencyRegistryError("model config fields are not exact")
        if config["relative_path"] != "config.json":
            raise DependencyRegistryError("model config relative path drifted")
        _sha256(config["raw_sha256"], context=f"{base_id}.config hash")
        for field in ("byte_size", "transformer_block_count", "hidden_size"):
            if (
                not isinstance(config[field], int)
                or isinstance(config[field], bool)
                or config[field] <= 0
            ):
                raise DependencyRegistryError("model config counts must be positive")

        weight = _mapping(record["weight_artifact"], context=f"{base_id}.weight")
        if set(weight) != {
            "relative_path",
            "sha256",
            "byte_size",
            "digest_source",
            "downloaded",
            "loaded",
        }:
            raise DependencyRegistryError("weight artifact fields are not exact")
        if weight["relative_path"] != "model.safetensors":
            raise DependencyRegistryError("weight artifact relative path drifted")
        weights.add(_sha256(weight["sha256"], context=f"{base_id}.weight hash"))
        if weight["digest_source"] != "hugging_face_lfs_sha256":
            raise DependencyRegistryError("weight digest source drifted")
        if (
            not isinstance(weight["byte_size"], int)
            or isinstance(weight["byte_size"], bool)
            or weight["byte_size"] <= 0
            or weight["downloaded"] is not False
            or weight["loaded"] is not False
        ):
            raise DependencyRegistryError("weight retrieval boundary was violated")

        tokenizer = _mapping(record["tokenizer_bundle"], context=f"{base_id}.tokenizer_bundle")
        if set(tokenizer) != {
            "revision",
            "artifact_sha256",
            "files",
            "preflight",
        }:
            raise DependencyRegistryError("tokenizer bundle fields are not exact")
        if tokenizer["revision"] != revision:
            raise DependencyRegistryError("tokenizer revision must equal the base revision")
        tokenizers.add(_sha256(tokenizer["artifact_sha256"], context=f"{base_id}.tokenizer hash"))
        files = _sequence(tokenizer["files"], context=f"{base_id}.tokenizer files")
        expected_bundle_hash = canonical_artifact_sha256({"files": list(files)})
        if tokenizer["artifact_sha256"] != expected_bundle_hash:
            raise DependencyRegistryError("tokenizer bundle hash does not close")
        file_paths: list[str] = []
        for file in files:
            file = _mapping(file, context=f"{base_id}.tokenizer file")
            if set(file) != {"path", "byte_size", "sha256"}:
                raise DependencyRegistryError("tokenizer file fields are not exact")
            file_paths.append(_text(file["path"], context="tokenizer file path"))
            _sha256(file["sha256"], context="tokenizer file hash")
            if (
                not isinstance(file["byte_size"], int)
                or isinstance(file["byte_size"], bool)
                or file["byte_size"] <= 0
            ):
                raise DependencyRegistryError("tokenizer file byte size must be positive")
        if file_paths != sorted(set(file_paths)):
            raise DependencyRegistryError("tokenizer files must be unique and sorted")
        preflight = _mapping(tokenizer["preflight"], context=f"{base_id}.preflight")
        if set(preflight) != {
            "add_special_tokens",
            "prefix_text",
            "a_text",
            "b_text",
            "prefix_token_ids",
            "a_token_ids",
            "b_token_ids",
            "single_distinct_continuation",
        }:
            raise DependencyRegistryError("tokenizer preflight fields are not exact")
        prefix = _token_id_array(
            preflight["prefix_token_ids"],
            context=f"{base_id}.prefix_token_ids",
            min_items=1,
        )
        a_ids = _token_id_array(
            preflight["a_token_ids"],
            context=f"{base_id}.a_token_ids",
            min_items=2,
        )
        b_ids = _token_id_array(
            preflight["b_token_ids"],
            context=f"{base_id}.b_token_ids",
            min_items=2,
        )
        derived_pass = (
            preflight["add_special_tokens"] is False
            and preflight["prefix_text"] == "FINAL:"
            and preflight["a_text"] == "FINAL: A"
            and preflight["b_text"] == "FINAL: B"
            and len(a_ids) == len(prefix) + 1
            and len(b_ids) == len(prefix) + 1
            and a_ids[:-1] == prefix
            and b_ids[:-1] == prefix
            and a_ids[-1] != b_ids[-1]
        )
        if preflight["single_distinct_continuation"] is not derived_pass or not derived_pass:
            raise DependencyRegistryError("tokenizer continuation preflight failed")
        if record["record_sha256"] != _body_hash(record, "record_sha256"):
            raise DependencyRegistryError("base-model record is not self-addressed")

    if order != sorted(set(order)) or len(revisions) != 3:
        raise DependencyRegistryError("base-model identities must be sorted and unique")
    if len(families) != 3 or len(weights) != 3 or len(tokenizers) != 3:
        raise DependencyRegistryError(
            "controlled successor requires three distinct families, weights, and tokenizers"
        )
    limitations = list(_sequence(intake["limitations"], context="limitations"))
    if limitations != sorted(set(limitations)) or len(limitations) < 3:
        raise DependencyRegistryError("base intake limitations must be sorted and explicit")
    if intake["authorization_effect"] != AUTHORIZATION_EFFECT:
        raise DependencyRegistryError("base intake cannot authorize calls")
    if intake["intake_body_sha256"] != _body_hash(intake, "intake_body_sha256"):
        raise DependencyRegistryError("base-model intake is not self-addressed")
    return {
        "ok": True,
        "base_model_count": 3,
        "architecture_family_count": 3,
        "tokenizer_preflight_pass_count": 3,
        "weight_files_downloaded": 0,
        "model_loads": 0,
        "model_calls_authorized": False,
        "intake_body_sha256": intake["intake_body_sha256"],
        "validated_at": created_at.isoformat().replace("+00:00", "Z"),
    }
