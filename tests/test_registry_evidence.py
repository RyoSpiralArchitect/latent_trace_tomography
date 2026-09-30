from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any

from jsonschema import FormatChecker
from jsonschema.validators import validator_for

from latent_trace_tomography.registry_evidence import (
    CATALOG_STATUS,
    CATALOG_TYPE,
    IDENTITY_FIELDS,
    SCHEMA_VERSION,
    SOURCE_KIND_TO_PAYLOAD_SCHEMA_KIND,
    RegistryEvidenceError,
    canonical_artifact_sha256,
    canonical_locator_sha256,
    catalog_body_sha256,
    load_source_evidence_catalog,
    source_record_sha256,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    ROOT
    / "operations"
    / "oss1_registry_authoring_v2"
    / "schemas"
    / "source_evidence_catalog.schema.json"
)
CREATED_AT = "2026-07-18T10:00:00Z"
RECORDED_AT = "2026-07-18T09:00:00Z"

KIND_ROWS = tuple(sorted(SOURCE_KIND_TO_PAYLOAD_SCHEMA_KIND.items()))


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _identity(schema_kind: str, index: int) -> dict[str, str]:
    values: dict[str, str] = {}
    for field, field_type in IDENTITY_FIELDS[schema_kind].items():
        values[field] = (
            _digest(f"{schema_kind}:{field}:{index}")
            if field_type == "sha256"
            else (f"{field}-{index}")
        )
    return values


def _write_json(path: Path, value: Any) -> bytes:
    raw = (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return raw


def _close_catalog(catalog: dict[str, Any], catalog_path: Path) -> None:
    catalog["catalog_body_sha256"] = catalog_body_sha256(catalog)
    _write_json(catalog_path, catalog)


def _bundle(root: Path) -> dict[str, Any]:
    payload_root = root / "payloads"
    payload_root.mkdir()
    source_records: list[dict[str, Any]] = []
    payloads: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []

    for index, (source_kind, schema_kind) in enumerate(KIND_ROWS):
        record_id = f"source-{index:02d}"
        relative_path = f"payloads/{record_id}.json"
        payload = {
            "schema_version": SCHEMA_VERSION,
            "payload_schema_kind": schema_kind,
            "source_kind": source_kind,
            "source_record_id": record_id,
            "payload_id": f"payload-{index:02d}",
            "created_at": RECORDED_AT,
            "identity": _identity(schema_kind, index),
            "evidence": {
                "authority_note": f"identity fixture for {source_kind}",
                "claim_validation_deferred": True,
            },
        }
        raw = _write_json(root / relative_path, payload)
        content_hash = canonical_artifact_sha256(payload)
        locator_hash = canonical_locator_sha256(relative_path)
        source_record = {
            "source_record_id": record_id,
            "source_kind": source_kind,
            "content_sha256": content_hash,
            "locator_sha256": locator_hash,
            "evidence_status": "complete_content_addressed",
            "recorded_at": RECORDED_AT,
            "source_record_sha256": _digest("temporary source record hash"),
        }
        source_record["source_record_sha256"] = source_record_sha256(source_record)
        entry = {
            "source_record_id": record_id,
            "source_kind": source_kind,
            "content_sha256": content_hash,
            "locator_sha256": locator_hash,
            "source_record_sha256": source_record["source_record_sha256"],
            "relative_path": relative_path,
            "raw_file_sha256": hashlib.sha256(raw).hexdigest(),
            "payload_schema_kind": schema_kind,
        }
        source_records.append(source_record)
        payloads.append(payload)
        entries.append(entry)

    catalog = {
        "schema_version": SCHEMA_VERSION,
        "catalog_type": CATALOG_TYPE,
        "status": CATALOG_STATUS,
        "catalog_id": "oss1-source-evidence-catalog-fixture",
        "created_at": CREATED_AT,
        "payload_directory": "payloads",
        "entries": entries,
        "catalog_body_sha256": _digest("temporary catalog hash"),
    }
    catalog_path = root / "source_evidence_catalog.json"
    _close_catalog(catalog, catalog_path)
    return {
        "catalog": catalog,
        "catalog_path": catalog_path,
        "entries": entries,
        "payloads": payloads,
        "source_records": source_records,
    }


def _replace_payload(bundle: dict[str, Any], index: int, payload: dict[str, Any]) -> None:
    entry = bundle["entries"][index]
    record = bundle["source_records"][index]
    raw = _write_json(bundle["catalog_path"].parent / entry["relative_path"], payload)
    content_hash = canonical_artifact_sha256(payload)
    record["content_sha256"] = content_hash
    record["source_record_sha256"] = source_record_sha256(record)
    entry["content_sha256"] = content_hash
    entry["source_record_sha256"] = record["source_record_sha256"]
    entry["raw_file_sha256"] = hashlib.sha256(raw).hexdigest()
    bundle["payloads"][index] = payload
    _close_catalog(bundle["catalog"], bundle["catalog_path"])


def _rebind_locator(bundle: dict[str, Any], index: int, locator_hash: str) -> None:
    record = bundle["source_records"][index]
    entry = bundle["entries"][index]
    record["locator_sha256"] = locator_hash
    record["source_record_sha256"] = source_record_sha256(record)
    entry["locator_sha256"] = locator_hash
    entry["source_record_sha256"] = record["source_record_sha256"]
    _close_catalog(bundle["catalog"], bundle["catalog_path"])


class SourceEvidenceCatalogTests(unittest.TestCase):
    def test_valid_catalog_closes_all_v1_typed_payload_kinds(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        validator_cls = validator_for(schema)
        validator_cls.check_schema(schema)

        with tempfile.TemporaryDirectory() as directory:
            bundle = _bundle(Path(directory))
            validator_cls(schema, format_checker=FormatChecker()).validate(bundle["catalog"])

            typed_payload_schema = {
                "$schema": schema["$schema"],
                "$defs": schema["$defs"],
                "$ref": "#/$defs/typedPayload",
            }
            typed_validator_cls = validator_for(typed_payload_schema)
            typed_validator_cls.check_schema(typed_payload_schema)
            typed_validator = typed_validator_cls(
                typed_payload_schema,
                format_checker=FormatChecker(),
            )
            for payload in bundle["payloads"]:
                with self.subTest(payload_schema_kind=payload["payload_schema_kind"]):
                    typed_validator.validate(payload)

            result = load_source_evidence_catalog(
                bundle["catalog_path"], source_records=bundle["source_records"]
            )
            self.assertEqual(result["entry_count"], len(KIND_ROWS))
            self.assertEqual(
                {row["source_kind"] for row in result["verified_payloads"]},
                set(SOURCE_KIND_TO_PAYLOAD_SCHEMA_KIND),
            )

    def test_raw_file_hash_detects_byte_drift_even_when_json_content_is_equal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = _bundle(Path(directory))
            payload_path = Path(directory) / bundle["entries"][0]["relative_path"]
            payload_path.write_bytes(payload_path.read_bytes() + b" \n")

            with self.assertRaisesRegex(RegistryEvidenceError, "raw_file_sha256"):
                load_source_evidence_catalog(
                    bundle["catalog_path"], source_records=bundle["source_records"]
                )

    def test_canonical_content_hash_detects_semantic_drift_after_raw_hash_is_updated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = _bundle(Path(directory))
            payload_path = Path(directory) / bundle["entries"][0]["relative_path"]
            payload = copy.deepcopy(bundle["payloads"][0])
            payload["evidence"]["authority_note"] = "mutated claim body"
            raw = _write_json(payload_path, payload)
            bundle["entries"][0]["raw_file_sha256"] = hashlib.sha256(raw).hexdigest()
            _close_catalog(bundle["catalog"], bundle["catalog_path"])

            with self.assertRaisesRegex(RegistryEvidenceError, "content_sha256"):
                load_source_evidence_catalog(
                    bundle["catalog_path"], source_records=bundle["source_records"]
                )

    def test_catalog_entry_is_bound_to_source_record_kind_id_hash_and_locator(self) -> None:
        mutations = {
            "source_record_id": "source-does-not-exist",
            "source_kind": "rng_manifest",
            "source_record_sha256": _digest("wrong source record hash"),
            "locator_sha256": _digest("wrong locator hash"),
        }
        for field, replacement in mutations.items():
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                bundle = _bundle(Path(directory))
                bundle["entries"][0][field] = replacement
                _close_catalog(bundle["catalog"], bundle["catalog_path"])
                with self.assertRaises(RegistryEvidenceError):
                    load_source_evidence_catalog(
                        bundle["catalog_path"], source_records=bundle["source_records"]
                    )

    def test_source_record_self_hash_is_recomputed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = _bundle(Path(directory))
            bundle["source_records"][0]["source_record_sha256"] = _digest("forged")
            with self.assertRaisesRegex(RegistryEvidenceError, "not self-addressed"):
                load_source_evidence_catalog(
                    bundle["catalog_path"], source_records=bundle["source_records"]
                )

    def test_payload_schema_kind_must_match_source_kind(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = _bundle(Path(directory))
            bundle["entries"][0]["payload_schema_kind"] = "checkpoint_evidence_v1"
            _close_catalog(bundle["catalog"], bundle["catalog_path"])
            with self.assertRaisesRegex(RegistryEvidenceError, "payload_schema_kind"):
                load_source_evidence_catalog(
                    bundle["catalog_path"], source_records=bundle["source_records"]
                )

    def test_each_typed_payload_requires_its_identity_fields(self) -> None:
        for index, (_, schema_kind) in enumerate(KIND_ROWS):
            with self.subTest(schema_kind=schema_kind), tempfile.TemporaryDirectory() as directory:
                bundle = _bundle(Path(directory))
                payload = copy.deepcopy(bundle["payloads"][index])
                payload["identity"].pop(next(iter(IDENTITY_FIELDS[schema_kind])))
                _replace_payload(bundle, index, payload)
                with self.assertRaisesRegex(RegistryEvidenceError, "fields differ"):
                    load_source_evidence_catalog(
                        bundle["catalog_path"], source_records=bundle["source_records"]
                    )

    def test_catalog_must_cover_every_source_exactly_once(self) -> None:
        for mode in ("missing", "duplicate"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                bundle = _bundle(Path(directory))
                if mode == "missing":
                    bundle["entries"].pop()
                else:
                    bundle["entries"].insert(1, copy.deepcopy(bundle["entries"][0]))
                _close_catalog(bundle["catalog"], bundle["catalog_path"])
                with self.assertRaises(RegistryEvidenceError):
                    load_source_evidence_catalog(
                        bundle["catalog_path"], source_records=bundle["source_records"]
                    )

    def test_catalog_rejects_undeclared_json_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = _bundle(Path(directory))
            _write_json(Path(directory) / "payloads" / "undeclared.json", {"not": "declared"})
            with self.assertRaisesRegex(RegistryEvidenceError, "undeclared"):
                load_source_evidence_catalog(
                    bundle["catalog_path"], source_records=bundle["source_records"]
                )

    def test_catalog_rejects_undeclared_non_json_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = _bundle(Path(directory))
            (Path(directory) / "payloads" / "undeclared.bin").write_bytes(b"opaque")
            with self.assertRaisesRegex(RegistryEvidenceError, "undeclared"):
                load_source_evidence_catalog(
                    bundle["catalog_path"], source_records=bundle["source_records"]
                )

    def test_direct_validator_rejects_a_catalog_object_that_differs_from_path(self) -> None:
        from latent_trace_tomography.registry_evidence import (
            validate_source_evidence_catalog,
        )

        with tempfile.TemporaryDirectory() as directory:
            bundle = _bundle(Path(directory))
            drift = copy.deepcopy(bundle["catalog"])
            drift["catalog_id"] = "different-but-self-addressed"
            drift["catalog_body_sha256"] = catalog_body_sha256(drift)
            with self.assertRaisesRegex(RegistryEvidenceError, "differs"):
                validate_source_evidence_catalog(
                    drift,
                    catalog_path=bundle["catalog_path"],
                    source_records=bundle["source_records"],
                )

    def test_payload_source_and_catalog_chronology_must_close(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = _bundle(Path(directory))
            payload = copy.deepcopy(bundle["payloads"][0])
            payload["created_at"] = "2026-07-18T09:30:00Z"
            _replace_payload(bundle, 0, payload)
            with self.assertRaisesRegex(RegistryEvidenceError, "chronology"):
                load_source_evidence_catalog(
                    bundle["catalog_path"], source_records=bundle["source_records"]
                )

    def test_catalog_rejects_traversal_and_absolute_paths(self) -> None:
        unsafe_paths = ("payloads/../outside.json", "/tmp/outside.json")
        for unsafe_path in unsafe_paths:
            with self.subTest(path=unsafe_path), tempfile.TemporaryDirectory() as directory:
                bundle = _bundle(Path(directory))
                bundle["entries"][0]["relative_path"] = unsafe_path
                _rebind_locator(bundle, 0, _digest(f"locator:{unsafe_path}"))
                with self.assertRaises(RegistryEvidenceError):
                    load_source_evidence_catalog(
                        bundle["catalog_path"], source_records=bundle["source_records"]
                    )

    def test_catalog_rejects_payload_and_catalog_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = _bundle(Path(directory))
            payload_path = Path(directory) / bundle["entries"][0]["relative_path"]
            external = Path(directory) / "external.json"
            external.write_bytes(payload_path.read_bytes())
            payload_path.unlink()
            try:
                os.symlink(external, payload_path)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"symlinks unavailable: {error}")
            with self.assertRaisesRegex(RegistryEvidenceError, "symlink"):
                load_source_evidence_catalog(
                    bundle["catalog_path"], source_records=bundle["source_records"]
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = _bundle(root)
            real_catalog = bundle["catalog_path"]
            linked_catalog = root / "linked_catalog.json"
            os.symlink(real_catalog, linked_catalog)
            with self.assertRaisesRegex(RegistryEvidenceError, "symlink"):
                load_source_evidence_catalog(
                    linked_catalog, source_records=bundle["source_records"]
                )

    def test_catalog_canonical_self_hash_is_mandatory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = _bundle(Path(directory))
            bundle["catalog"]["catalog_id"] = "mutated-after-seal"
            _write_json(bundle["catalog_path"], bundle["catalog"])
            with self.assertRaisesRegex(RegistryEvidenceError, "self-addressed"):
                load_source_evidence_catalog(
                    bundle["catalog_path"], source_records=bundle["source_records"]
                )

    def test_duplicate_json_keys_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = _bundle(Path(directory))
            payload_path = Path(directory) / bundle["entries"][0]["relative_path"]
            raw = b'{"schema_version":"0.1.0","schema_version":"0.1.0"}'
            payload_path.write_bytes(raw)
            bundle["entries"][0]["raw_file_sha256"] = hashlib.sha256(raw).hexdigest()
            _close_catalog(bundle["catalog"], bundle["catalog_path"])
            with self.assertRaisesRegex(RegistryEvidenceError, "duplicate key"):
                load_source_evidence_catalog(
                    bundle["catalog_path"], source_records=bundle["source_records"]
                )


if __name__ == "__main__":
    unittest.main()
