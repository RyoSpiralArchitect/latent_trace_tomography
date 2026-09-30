from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema.validators import validator_for

from latent_trace_tomography.protocol import (
    OSS_FROZEN_SECTION_SHA256,
    _resolve_protocol_artifact,
    _sha256_json_value,
    _validate_design_manifest_metadata,
    _validate_freeze_layer_shape,
    _validate_frozen_asset_contracts,
    _validate_oss_scientific_seal,
    preflight_protocol,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class ProtocolTests(unittest.TestCase):
    def test_oss_design_freeze_preflight_is_call_free_and_execution_unassigned(self) -> None:
        result = preflight_protocol(
            REPO_ROOT / "protocols" / "oss_reliance_regime_v0" / "protocol.json"
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["design_ready"])
        self.assertFalse(result["discovery_ready"])
        self.assertFalse(result["execution_ready"])
        self.assertFalse(result["sealed_evaluation_ready"])
        self.assertEqual(result["preflight_level"], "design_freeze_validation")
        self.assertEqual(result["external_calls"], 0)
        warning_text = " ".join(result["warnings"])
        self.assertIn("discovery authorization is unassigned", warning_text)
        self.assertIn("final execution lock is unassigned", warning_text)
        self.assertIn("sealed evaluation authorization is unassigned", warning_text)
        self.assertIn("task_generator_conformance", result["validated_checks"])
        self.assertIn("intervention_and_null_contract", result["validated_checks"])
        self.assertIn("dependency_cluster_split_contract", result["validated_checks"])
        self.assertIn("blind_auditor_surface_contract", result["validated_checks"])
        self.assertIn("prospective_scoring_contract", result["validated_checks"])
        self.assertIn("causal_profile_arithmetic_contract", result["validated_checks"])
        self.assertIn("runtime_source_identity", result["validated_checks"])
        self.assertIn("unassigned_discovery_authorization_template", result["validated_checks"])
        self.assertIn("unassigned_execution_template", result["validated_checks"])
        self.assertIn(
            "unassigned_sealed_evaluation_authorization_template",
            result["validated_checks"],
        )
        self.assertTrue(result["not_validated"])
        self.assertEqual(len(result["sha256"]), 64)
        self.assertTrue(result["manifest_path"])
        self.assertEqual(len(result["design_manifest_sha256"]), 64)

    def test_preflight_rejects_a_copied_freeze_when_another_checkout_is_imported(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            copied_root = Path(temporary_directory) / "copied-repository"
            shutil.copytree(
                REPO_ROOT,
                copied_root,
                ignore=shutil.ignore_patterns(".git", "build", "dist", "*.egg-info", "__pycache__"),
            )
            result = preflight_protocol(
                copied_root / "protocols" / "oss_reliance_regime_v0" / "protocol.json"
            )

        self.assertFalse(result["ok"])
        self.assertFalse(result["design_ready"])
        self.assertTrue(any("runtime source path mismatch=" in error for error in result["errors"]))

    def test_retrospective_scaffold_cannot_masquerade_as_preregistration(self) -> None:
        result = preflight_protocol(
            REPO_ROOT / "protocols" / "synthetic_projection_orbit_v1" / "protocol.json"
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["warnings"])
        self.assertIn("retrospective", result["warnings"][0])

    def test_design_linter_rejects_the_retired_single_fold_hash_bridge(self) -> None:
        protocol_dir = REPO_ROOT / "protocols" / "oss_reliance_regime_v0"
        manifest = json.loads(
            (protocol_dir / "design_freeze_manifest.json").read_text(encoding="utf-8")
        )
        assets_by_id = {item["asset_id"]: REPO_ROOT / item["path"] for item in manifest["assets"]}
        prospective = json.loads(
            assets_by_id["prospective_scoring_contract"].read_text(encoding="utf-8")
        )
        closure = prospective["committed_baseline_input_closure"]
        closure.pop("caller_supplied_candidate_baseline_closure_or_expected_hashes")
        closure.pop("six_verifier_derived_sha256_values")
        closure["authoritative_gate_function"] = (
            "latent_trace_tomography.blind.evaluate_committed_candidate_gate"
        )
        closure["caller_supplied_baseline_predictions_or_scores"] = (
            "forbidden; the gate API has no baseline-vector or baseline-score parameter"
        )
        closure["separately_required_expected_sha256_arguments"] = [
            "expected_weak_observation_records_sha256",
            "expected_weak_observation_inventory_sha256",
            "expected_development_scoring_key_sha256",
            "expected_development_slot_inventory_sha256",
            "expected_heldout_scoring_key_sha256",
            "expected_heldout_slot_inventory_sha256",
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            mutated_contract = Path(temporary_directory) / "prospective.json"
            mutated_contract.write_text(json.dumps(prospective), encoding="utf-8")
            assets_by_id["prospective_scoring_contract"] = mutated_contract
            errors: list[str] = []
            _validate_frozen_asset_contracts(
                assets_by_id,
                errors=errors,
                validated_checks=[],
            )

        self.assertTrue(
            any("prospective pilot gate must derive six hashes" in error for error in errors)
        )

    def test_design_linter_binds_runtime_limit_and_cross_fold_method_roles(self) -> None:
        protocol_dir = REPO_ROOT / "protocols" / "oss_reliance_regime_v0"
        manifest = json.loads(
            (protocol_dir / "design_freeze_manifest.json").read_text(encoding="utf-8")
        )
        base_assets = {item["asset_id"]: REPO_ROOT / item["path"] for item in manifest["assets"]}
        blind_contract = json.loads(
            base_assets["blind_evaluation_contract"].read_text(encoding="utf-8")
        )
        mutations = {
            "runtime attestation": lambda value: value["output_runtime_evidence"].__setitem__(
                "runtime_attestation_provided", True
            ),
            "method role": lambda value: value["cross_fold_method_identity"]["common_roles"].remove(
                "feature_spec"
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(mutation=label):
                candidate = copy.deepcopy(blind_contract)
                mutate(candidate)
                with tempfile.TemporaryDirectory() as temporary_directory:
                    mutated_contract = Path(temporary_directory) / "blind.json"
                    mutated_contract.write_text(json.dumps(candidate), encoding="utf-8")
                    assets_by_id = dict(base_assets)
                    assets_by_id["blind_evaluation_contract"] = mutated_contract
                    errors: list[str] = []
                    _validate_frozen_asset_contracts(
                        assets_by_id,
                        errors=errors,
                        validated_checks=[],
                    )
                self.assertTrue(
                    any(
                        marker in error
                        for error in errors
                        for marker in (
                            "output-runtime evidence boundary",
                            "cross-fold method identity contract",
                        )
                    )
                )

    def test_scientific_seal_rejects_exposure_claim_and_amendment_drift(self) -> None:
        protocol_dir = REPO_ROOT / "protocols" / "oss_reliance_regime_v0"
        protocol = json.loads((protocol_dir / "protocol.json").read_text(encoding="utf-8"))
        mutations = {
            "model calls": lambda value: value["outcome_exposure"].__setitem__(
                "oss_model_calls", 1
            ),
            "outcomes exposed": lambda value: value["outcome_exposure"].__setitem__(
                "oss_outcomes_exposed", True
            ),
            "claim strengthened": lambda value: value.__setitem__(
                "claim_ceiling", "This design recovers proprietary hidden chain of thought."
            ),
            "claim tier": lambda value: value["scope"].__setitem__(
                "three_cluster_claim_tier", "population_confirmatory"
            ),
            "independent unit": lambda value: value["scope"].__setitem__(
                "primary_independent_unit", "target_id"
            ),
            "auditor input": lambda value: value["scope"]["auditor_primary_inputs"].append(
                "logprobs"
            ),
            "estimator": lambda value: value["analysis_contract"].__setitem__(
                "primary_estimator", "choose the best estimator after heldout scoring"
            ),
            "primary readout": lambda value: value["primary_readouts"].__setitem__(
                0, "target-level accuracy"
            ),
            "mutable amendment": lambda value: value["amendment_rule"].__setitem__(
                "mode", "mutable"
            ),
            "shadow override": lambda value: value.__setitem__("freeze_override", True),
        }
        for label, mutate in mutations.items():
            with self.subTest(mutation=label):
                candidate = copy.deepcopy(protocol)
                mutate(candidate)
                errors: list[str] = []
                _validate_oss_scientific_seal(candidate, errors=errors)
                self.assertTrue(errors)

    def test_design_manifest_metadata_rejects_exposure_and_identity_drift(self) -> None:
        protocol_dir = REPO_ROOT / "protocols" / "oss_reliance_regime_v0"
        protocol = json.loads((protocol_dir / "protocol.json").read_text(encoding="utf-8"))
        manifest = json.loads(
            (protocol_dir / "design_freeze_manifest.json").read_text(encoding="utf-8")
        )
        mutations = {
            "outcomes exposed": lambda value: value.__setitem__("oss_outcomes_exposed", True),
            "panel": lambda value: value.__setitem__("panel_id", "another_panel"),
            "amendment": lambda value: value.__setitem__("amendment_mode", "mutable"),
            "extra field": lambda value: value.__setitem__("unfrozen_note", "drift"),
        }
        for label, mutate in mutations.items():
            with self.subTest(mutation=label):
                candidate = copy.deepcopy(manifest)
                mutate(candidate)
                errors: list[str] = []
                _validate_design_manifest_metadata(candidate, protocol, errors=errors)
                self.assertTrue(errors)

    def test_freeze_layer_shape_rejects_shadow_layers_and_fields(self) -> None:
        protocol = json.loads(
            (REPO_ROOT / "protocols" / "oss_reliance_regime_v0" / "protocol.json").read_text(
                encoding="utf-8"
            )
        )
        freeze = protocol["freeze_layers"]
        errors: list[str] = []
        _validate_freeze_layer_shape(freeze, errors=errors)
        self.assertEqual(errors, [])

        extra_layer = copy.deepcopy(freeze)
        extra_layer["shadow"] = {}
        errors = []
        _validate_freeze_layer_shape(extra_layer, errors=errors)
        self.assertTrue(errors)
        for layer_name in freeze:
            with self.subTest(layer=layer_name):
                extra_field = copy.deepcopy(freeze)
                extra_field[layer_name]["shadow"] = "drift"
                errors = []
                _validate_freeze_layer_shape(extra_field, errors=errors)
                self.assertTrue(errors)

    def test_protocol_artifacts_reject_ancestor_symlinks_and_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            base = root / "protocol"
            outside = root / "outside"
            base.mkdir()
            outside.mkdir()
            (outside / "template.json").write_text("{}", encoding="utf-8")
            (base / "link").symlink_to(outside, target_is_directory=True)
            errors: list[str] = []
            resolved = _resolve_protocol_artifact(
                base,
                Path("link/template.json"),
                field="test template",
                errors=errors,
            )
        self.assertIsNone(resolved)
        self.assertTrue(any("symlinked path component" in error for error in errors))

    def test_design_manifest_dag_excludes_protocol_and_external_freeze_layers(self) -> None:
        protocol_dir = REPO_ROOT / "protocols" / "oss_reliance_regime_v0"
        manifest = json.loads(
            (protocol_dir / "design_freeze_manifest.json").read_text(encoding="utf-8")
        )
        asset_paths = {item["path"] for item in manifest["assets"]}
        cyclic_paths = {
            "protocols/oss_reliance_regime_v0/design_freeze_manifest.json",
            "protocols/oss_reliance_regime_v0/discovery_authorization.json",
            "protocols/oss_reliance_regime_v0/execution_lock.json",
            "protocols/oss_reliance_regime_v0/sealed_evaluation_authorization.json",
            "protocols/oss_reliance_regime_v0/protocol.json",
            "protocols/oss_reliance_regime_v0/protocol_manifest.json",
        }
        self.assertFalse(asset_paths & cyclic_paths)

    def test_scientific_body_hashes_are_stratified_below_dynamic_freeze_layers(self) -> None:
        protocol = json.loads(
            (REPO_ROOT / "protocols" / "oss_reliance_regime_v0" / "protocol.json").read_text(
                encoding="utf-8"
            )
        )
        before = {
            section: _sha256_json_value(protocol[section]) for section in OSS_FROZEN_SECTION_SHA256
        }
        self.assertEqual(before, OSS_FROZEN_SECTION_SHA256)
        protocol["freeze_layers"]["design"]["manifest_sha256"] = "f" * 64
        after = {
            section: _sha256_json_value(protocol[section]) for section in OSS_FROZEN_SECTION_SHA256
        }
        self.assertEqual(after, before)

    def test_actual_python_s_preflight_cli_has_no_network_or_child_process_surface(self) -> None:
        protocol_path = REPO_ROOT / "protocols" / "oss_reliance_regime_v0" / "protocol.json"
        guard = """
import http.client
import runpy
import socket
import subprocess
import sys
import urllib.request

def blocked(*args, **kwargs):
    raise RuntimeError("forbidden external-call surface")

def audit(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system"}:
        raise RuntimeError("forbidden audit event: " + event)

sys.addaudithook(audit)
socket.socket.connect = blocked
socket.create_connection = blocked
urllib.request.urlopen = blocked
http.client.HTTPConnection.connect = blocked
http.client.HTTPSConnection.connect = blocked
subprocess.Popen = blocked
sys.argv = ["ltt", "preflight", "--protocol", sys.argv[1]]
runpy.run_module("latent_trace_tomography", run_name="__main__")
"""
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(REPO_ROOT / "src")
        completed = subprocess.run(
            [sys.executable, "-S", "-c", guard, str(protocol_path)],
            cwd=REPO_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        combined_output = completed.stdout + completed.stderr
        self.assertNotIn("forbidden external-call surface", combined_output)
        self.assertNotIn("forbidden audit event", combined_output)
        self.assertIn(completed.returncode, {0, 2}, combined_output)

    def test_malformed_design_and_protocol_manifests_fail_as_reports(self) -> None:
        source = REPO_ROOT / "protocols" / "oss_reliance_regime_v0"
        frozen_filenames = (
            "protocol.json",
            "protocol_manifest.json",
            "design_freeze_manifest.json",
            "discovery_authorization.json",
            "execution_lock.json",
            "sealed_evaluation_authorization.json",
        )
        for malformed_bytes in (b"{", b"[]"):
            with self.subTest(design_manifest=malformed_bytes):
                with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
                    copied = Path(temporary_directory)
                    for filename in frozen_filenames:
                        shutil.copy2(source / filename, copied / filename)
                    (copied / "design_freeze_manifest.json").write_bytes(malformed_bytes)
                    protocol = json.loads((copied / "protocol.json").read_text(encoding="utf-8"))
                    design_sha = hashlib.sha256(malformed_bytes).hexdigest()
                    protocol["freeze_layers"]["design"]["manifest_sha256"] = design_sha
                    protocol_bytes = (
                        json.dumps(
                            protocol,
                            indent=2,
                            ensure_ascii=False,
                        ).encode("utf-8")
                        + b"\n"
                    )
                    (copied / "protocol.json").write_bytes(protocol_bytes)
                    protocol_manifest = json.loads(
                        (copied / "protocol_manifest.json").read_text(encoding="utf-8")
                    )
                    protocol_manifest["design_freeze_manifest_sha256"] = design_sha
                    protocol_manifest["protocol_sha256"] = hashlib.sha256(
                        protocol_bytes
                    ).hexdigest()
                    (copied / "protocol_manifest.json").write_text(
                        json.dumps(protocol_manifest),
                        encoding="utf-8",
                    )
                    result = preflight_protocol(copied / "protocol.json")
                self.assertFalse(result["ok"])
                self.assertTrue(
                    any("design freeze manifest" in error for error in result["errors"])
                )

        for malformed_bytes in (b"{", b"[]"):
            with self.subTest(protocol_manifest=malformed_bytes):
                with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
                    copied = Path(temporary_directory)
                    for filename in frozen_filenames:
                        shutil.copy2(source / filename, copied / filename)
                    (copied / "protocol_manifest.json").write_bytes(malformed_bytes)
                    result = preflight_protocol(copied / "protocol.json")
                self.assertFalse(result["ok"])
                self.assertTrue(any("protocol manifest" in error for error in result["errors"]))

    def test_malformed_protocol_and_nested_types_fail_as_reports(self) -> None:
        for malformed_bytes in (b"{", b"[]"):
            with self.subTest(protocol=malformed_bytes):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    path = Path(temporary_directory) / "protocol.json"
                    path.write_bytes(malformed_bytes)
                    result = preflight_protocol(path)
                self.assertFalse(result["ok"])
                self.assertEqual(result["preflight_level"], "parse_validation")

        source = json.loads(
            (REPO_ROOT / "protocols" / "oss_reliance_regime_v0" / "protocol.json").read_text(
                encoding="utf-8"
            )
        )
        for field in ("phase_contract", "scope", "outcome_exposure", "freeze_layers"):
            with self.subTest(field=field):
                candidate = copy.deepcopy(source)
                candidate[field] = []
                with tempfile.TemporaryDirectory() as temporary_directory:
                    path = Path(temporary_directory) / "protocol.json"
                    path.write_text(json.dumps(candidate), encoding="utf-8")
                    result = preflight_protocol(path)
                self.assertFalse(result["ok"])
                self.assertTrue(result["errors"])

    def test_checked_in_json_schemas_are_valid_and_keep_labels_separate(self) -> None:
        schema_dir = REPO_ROOT / "schemas"
        schemas = {
            path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in schema_dir.glob("*.json")
        }
        self.assertGreaterEqual(len(schemas), 9)
        for name, schema in schemas.items():
            with self.subTest(schema=name):
                validator_for(schema).check_schema(schema)
        observation = schemas["text_observation.schema.json"]
        self.assertFalse(
            {"regime", "intervention_id", "logprobs", "latency_ms"}
            & observation["properties"].keys()
        )

        protocol_dir = REPO_ROOT / "protocols" / "oss_reliance_regime_v0"
        schema_instances = {
            "design_freeze_manifest.schema.json": "design_freeze_manifest.json",
            "discovery_authorization.schema.json": "discovery_authorization.json",
            "execution_lock.schema.json": "execution_lock.json",
            "sealed_evaluation_authorization.schema.json": ("sealed_evaluation_authorization.json"),
        }
        for schema_name, instance_name in schema_instances.items():
            schema = schemas[schema_name]
            instance = json.loads((protocol_dir / instance_name).read_text(encoding="utf-8"))
            with self.subTest(instance=instance_name):
                validator_for(schema)(schema).validate(instance)

    def test_packaged_synthetic_protocol_matches_the_research_contract(self) -> None:
        repository_protocol = (
            REPO_ROOT / "protocols" / "synthetic_projection_orbit_v1" / "protocol.json"
        )
        packaged_protocol = (
            REPO_ROOT
            / "src"
            / "latent_trace_tomography"
            / "resources"
            / "protocols"
            / "synthetic_projection_orbit_v1"
            / "protocol.json"
        )
        repository_manifest = repository_protocol.with_name("protocol_manifest.json")
        packaged_manifest = packaged_protocol.with_name("protocol_manifest.json")
        self.assertEqual(repository_protocol.read_bytes(), packaged_protocol.read_bytes())
        self.assertEqual(repository_manifest.read_bytes(), packaged_manifest.read_bytes())


if __name__ == "__main__":
    unittest.main()
