"""Bounded output-only observability bridge. API secrets stay in local memory."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gc
import hashlib
import http.client
import importlib.util
from itertools import product
import json
import math
import os
from pathlib import Path
import re
import ssl
import time

SCOPE = "output_only_bridge_20261023_v1"
MODEL = "gpt-4.1-mini-2025-04-14"
HOST = "api.openai.com"
ROLES = ("weak_baseline", "weak_rule_paraphrase", "weak_evidence_reorder",
         "weak_irrelevant_distractor", "weak_cue_salience_attenuation")
CHALLENGES = ("challenge_conflict", "challenge_table")
STATES = ("A", "B", "parse_failure")
CELLS = tuple(product((True, False), repeat=3))
FIELDS = {"target_id", "case_id", "projection_id", "replicate_id", "prompt_text", "output_text"}
API_N = 112
OSS_N = 9 * API_N
INPUT_BOUND = 8192
OUTPUT_CAP = 32
INPUT_RATE, OUTPUT_RATE = 0.40 / 1_000_000, 1.60 / 1_000_000
RESERVATION = INPUT_BOUND * INPUT_RATE + OUTPUT_CAP * OUTPUT_RATE
PRICE_CAP = 0.50
PARENT_SCRIPT_SHA = "93850e3d20a06b3c04be28107fecf1ef9d317d803593500c0ff90adfec8e03cb"
PARENT_PLAN_SHA = "2e3752a2349cd708ee5f6c0b354f35149a69b429bd8c1f16cd5ed62567c9381f"


def check(condition, message):
    if not condition:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def seal(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write_new(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def marker(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    matches = [line[-1] for line in lines if re.fullmatch(r"FINAL: [AB]", line)]
    return matches[0] if len(matches) == 1 and lines[-1] == "FINAL: " + matches[0] else "parse_failure"


def content(index):
    return {name: prefix + seal([SCOPE, index, name])[:12].upper()
            for name, prefix in (("required", "REQ-"), ("alternate", "ALT-"), ("entity", "DOC-"))}


def render(index, cell, role):
    semantic, cue, identity = CELLS[cell]
    values = content(index)
    candidate = values["required"] if semantic else values["alternate"]
    rule = "Local law: PASS exactly when candidate_code equals required_code; else FAIL."
    if role == "weak_rule_paraphrase":
        rule = "Local law: If required_code and candidate_code are identical, PASS; otherwise FAIL."
    cue_text = "PASS" if cue else "FAIL"
    if role == "weak_cue_salience_attenuation":
        cue_text = "faded lettering: " + " ".join(cue_text.lower())
    evidence = [f"Required code = {values['required']}", f"Candidate code = {candidate}"]
    if role == "weak_evidence_reorder":
        evidence.reverse()
    if role == "weak_irrelevant_distractor":
        evidence.append("Paper color = teal (irrelevant to the law).")
    if role == "challenge_table":
        evidence = ["required_code | candidate_code", f"{values['required']} | {candidate}"]
    return "\n".join([
        "Synthetic permit drill; use only this filing.", rule, "Response map:",
        f"- PASS maps to FINAL: {'A' if identity else 'B'}",
        f"- FAIL maps to FINAL: {'B' if identity else 'A'}",
        f"Advisory ribbon (not law): {cue_text}", f"Docket: {values['entity']}",
        *evidence, "Emit one response-map marker and nothing else."])


def panel():
    result = []
    for phase in ("weak", "challenge"):
        for repeat in range(2):
            for index in range(2):
                for cell, (semantic, cue, _) in enumerate(CELLS):
                    if (semantic == cue) != (phase == "weak"):
                        continue
                    for role in ROLES if phase == "weak" else CHALLENGES:
                        text = render(index, cell, role)
                        result.append({"query_id": f"{phase}:{index}:{cell}:{role}:r{repeat}",
                                       "phase": phase, "content": index, "cell": cell,
                                       "case_id": f"case-{index}-{cell}-r{repeat}",
                                       "replicate_id": f"r{repeat}", "projection_id": role,
                                       "prompt_text": text, "prompt_sha256": hashlib.sha256(text.encode()).hexdigest()})
    check(len(result) == API_N and len({q["query_id"] for q in result}) == API_N, "panel inventory mismatch")
    check(all(q["prompt_text"].isascii() and len(q["prompt_text"].encode()) <= 4096 for q in result), "prompt byte bound exceeded")
    return result


def observation(query, target, text):
    return {"target_id": target, **{key: query[key] for key in ("case_id", "projection_id", "replicate_id", "prompt_text")}, "output_text": text}


def features(observations):
    check(len(observations) == 80 and len({r["target_id"] for r in observations}) == 1, "one complete weak target required")
    grouped = defaultdict(dict)
    for row in observations:
        check(set(row) == FIELDS and row["projection_id"] in ROLES, "feature interface leaked fields or challenge")
        key = (row["case_id"], row["replicate_id"])
        check(row["projection_id"] not in grouped[key], "duplicate projection")
        grouped[key][row["projection_id"]] = marker(row["output_text"])
    check(len(grouped) == 16 and all(set(v) == set(ROLES) for v in grouped.values()), "weak orbit incomplete")
    values = [0] * 51
    for group in grouped.values():
        states = [STATES.index(group[role]) for role in ROLES]
        for index, state in enumerate(states):
            values[index * 3 + state] += 1
        for index, state in enumerate(states[1:]):
            values[15 + index * 9 + states[0] * 3 + state] += 1
    return {"counts": values, "denominator": 16}


def request_body(query):
    return {"model": MODEL, "input": query["prompt_text"], "temperature": 0,
            "max_output_tokens": OUTPUT_CAP, "store": False, "service_tier": "default",
            "tools": [], "stream": False}


class SafeAPIError(RuntimeError):
    def __init__(self, category, status=None):
        self.category, self.status = category, status
        super().__init__(category)


def decode_response(response):
    check(response.get("model") == MODEL, "API snapshot changed")
    check(type(response.get("id")) is str and 0 < len(response["id"]) <= 256, "invalid response identity")
    check(response.get("status") in ("completed", "incomplete"), "unexpected response status")
    usage = response.get("usage") or {}
    counts = [usage.get(key) for key in ("input_tokens", "output_tokens", "total_tokens")]
    check(all(type(x) is int and x >= 0 for x in counts) and counts[0] + counts[1] == counts[2], "missing or inconsistent API usage")
    check(counts[0] <= INPUT_BOUND and counts[1] <= OUTPUT_CAP, "returned API usage exceeded reservation")
    text, refusal = [], False
    for item in response.get("output", []):
        check(item.get("type") == "message" and item.get("role") == "assistant", "unexpected API output item")
        for part in item.get("content", []):
            if part.get("type") == "output_text":
                check(type(part.get("text")) is str, "invalid output text")
                text.append(part["text"])
            elif part.get("type") == "refusal":
                check(type(part.get("refusal")) is str, "invalid refusal")
                text.append(part["refusal"])
                refusal = True
            else:
                raise ValueError("unexpected API message content")
    safe = {"model": MODEL, "response_id": response.get("id"), "status": response["status"],
            "refusal": refusal, "usage": dict(zip(("input_tokens", "output_tokens", "total_tokens"), counts)),
            "estimated_uncached_cost_usd": counts[0] * INPUT_RATE + counts[1] * OUTPUT_RATE}
    return "\n".join(text), safe


def http_request(body, key):
    # No SDK retries, proxy discovery, redirect following, or credential logging.
    connection = http.client.HTTPSConnection(HOST, 443, timeout=45, context=ssl.create_default_context())
    try:
        connection.request("POST", "/v1/responses", body=canonical(body).encode(),
                           headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        response = connection.getresponse()
        raw = response.read(1_000_001)
        if response.status != 200:
            category = {400: "request_rejected", 401: "authentication_failed", 403: "permission_denied",
                        404: "model_or_endpoint_unavailable", 429: "rate_limit_or_quota"}.get(response.status, "http_failure")
            raise SafeAPIError(category, response.status)
        check(len(raw) <= 1_000_000 and key.encode() not in raw, "unsafe or oversized API response")
        return json.loads(raw)
    except SafeAPIError:
        raise
    except Exception:
        raise SafeAPIError("network_or_response_unknown") from None
    finally:
        connection.close()


class Journal:
    def __init__(self, path):
        self.stream = Path(path).open("x")
        self.previous, self.sequence = "0" * 64, 0

    def add(self, kind, payload):
        row = {"sequence": self.sequence, "previous_sha256": self.previous,
               "time": now(), "event": kind, "payload": payload}
        row["sha256"] = seal(row)
        self.stream.write(canonical(row) + "\n")
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.previous, self.sequence = row["sha256"], self.sequence + 1

    def close(self):
        self.stream.close()


def parent_module(root):
    path = Path(root) / "pilot.py"
    check(digest(path) == PARENT_SCRIPT_SHA and digest(Path(root) / "plan.json") == PARENT_PLAN_SHA, "parent pilot pin mismatch")
    spec = importlib.util.spec_from_file_location("matched_parent_pilot", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate(plan):
    check(plan["scope"] == SCOPE and plan["script_sha256"] == digest(__file__)
          and plan["contract_sha256"] == digest(Path(__file__).with_name("README.md")), "bridge source/contract changed")
    check(plan["panel"] == panel() and plan["api_model"] == MODEL, "panel/model changed")
    check(plan["api_price_cap_usd"] == PRICE_CAP and plan["api_reserved_ceiling_usd"] == API_N * RESERVATION, "budget changed")
    check(len(plan["targets"]) == 9 and len({u["target_id"] for u in plan["targets"]}) == 9, "reference cohort changed")


def prepare(args):
    parent = parent_module(args.parent_root)
    old_plan = read(Path(args.parent_root) / "plan.json")
    source, admission = parent.validate(old_plan)
    capsule = Path(old_plan["capsule_root"])
    construction = read(capsule / "construction_authorization.json")
    prompts = {q["prompt_text"] for q in panel()}
    training = {c["prompt_text"] for run in construction["runs"] for c in read(capsule / run["payload_path"])["cases"]}
    check(not prompts & training, "training prompt overlap")
    from tokenizers import Tokenizer
    tokenizers = {}
    for base in construction["bases"]:
        tokenizer = Tokenizer.from_file(str(capsule / base["asset_directory"] / "tokenizer.json"))
        check(tokenizer.padding is None and tokenizer.truncation is None, "tokenizer changes prompt")
        maximum = max(len(tokenizer.encode(t, add_special_tokens=False).ids) for t in prompts)
        check(maximum <= 256, "reference prompt too long")
        tokenizers[base["base_model_unit_id"]] = maximum
    targets = [{**u, "target_id": f"target-{index + 1:02d}"}
               for index, u in enumerate(sorted(admission["model_units"], key=lambda r: r["model_unit_id"]))]
    plan = {"scope": SCOPE, "script_sha256": digest(__file__),
            "contract_sha256": digest(Path(__file__).with_name("README.md")),
            "parent_root": str(Path(args.parent_root).resolve()), "parent_plan_sha256": PARENT_PLAN_SHA,
            "parent_script_sha256": PARENT_SCRIPT_SHA, "source_root": str(source),
            "targets": targets, "api_target_id": "target-10", "api_model": MODEL,
            "api_price_cap_usd": PRICE_CAP, "api_reserved_ceiling_usd": API_N * RESERVATION,
            "panel": panel(), "new_unique_prompts": len(prompts), "training_unique_prompts": len(training),
            "exact_training_overlap": 0, "tokenizer_max_inputs": tokenizers,
            "authority_basis": "User requested Furnace and API experiments and accepted reuse of the existing API key in this chat, 2026-10-23 JST",
            "claim_ceiling": "output-only observability and exploratory behavior forecast; no internal attribution"}
    check("torch" not in __import__("sys").modules, "prepare imported torch")
    validate(plan)
    write_new(args.output, plan)
    print(canonical({"status": "prepared", "sha256": digest(args.output), "queries_per_target": API_N,
                     "api_reserved_ceiling_usd": API_N * RESERVATION, "live_calls": 0}))


def rehearse(args):
    plan = read(args.plan)
    validate(plan)
    for q in plan["panel"]:
        body = request_body(q)
        check(body["store"] is False and body["max_output_tokens"] == 32 and body["tools"] == [], "API request contract changed")
        text, meta = decode_response({"model": MODEL, "id": "fixture-only", "status": "completed",
            "usage": {"input_tokens": 200, "output_tokens": 5, "total_tokens": 205},
            "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "FINAL: A"}]}]})
        check(text == "FINAL: A" and meta["usage"]["output_tokens"] == 5, "mock extraction mismatch")
    write_new(args.output, {"scope": SCOPE, "plan_sha256": digest(args.plan), "script_sha256": digest(__file__),
                           "status": "mock_contracts_passed", "simulated_requests": API_N, "network_calls": 0, "model_calls": 0})
    print(canonical({"status": "mock_contracts_passed", "simulated_requests": API_N, "network_calls": 0}))


def furnace(args):
    check(args.execute and digest(args.plan) == args.expected_plan_sha256, "explicit pinned execution required")
    plan = read(args.plan)
    validate(plan)
    parent = parent_module(plan["parent_root"])
    old_plan = read(Path(plan["parent_root"]) / "plan.json")
    source, admission = parent.validate(old_plan)
    check([dict((k, v) for k, v in u.items() if k != "target_id") for u in plan["targets"]]
          == sorted(admission["model_units"], key=lambda r: r["model_unit_id"]), "target registry changed")
    check(os.environ.get("HF_HUB_OFFLINE") == "1" and os.environ.get("TRANSFORMERS_OFFLINE") == "1"
          and os.environ.get("CUBLAS_WORKSPACE_CONFIG") == ":4096:8", "retained offline runtime required")
    write_new(Path(args.plan).parent / "furnace.claim.json", {"scope": SCOPE, "plan_sha256": args.expected_plan_sha256, "resume": False})
    output = Path(args.output)
    output.mkdir(mode=0o700)
    from latent_trace_tomography.measurement_runner import EventJournal, RunPermit, verify_event_journal
    from latent_trace_tomography.measurement_model import load_measurement_model
    identities = {r["model_unit_id"]: r for r in admission["model_identities"]}
    journal = EventJournal(output / "events.jsonl")
    jobs = {u["model_unit_id"] + ":" + q["query_id"] for u in plan["targets"] for q in plan["panel"]}
    permit = RunPermit(mode="live", journal=journal, logical_limit=OSS_N, physical_limit=OSS_N * 16,
                       max_wall_seconds=600, model_identities={k: r["composite_model_artifact_sha256"] for k, r in identities.items()}, allowed_job_ids=jobs)
    capsule = Path(old_plan["capsule_root"])
    authorization = read(capsule / "construction_authorization.json")
    old = read(Path(old_plan["package_root"]) / "discovery_authorization.draft.json")
    decodings = {r["model_unit_id"]: r for r in old["discovery_decoding_config"]["records"]}
    runtimes = {r["model_unit_id"]: r for r in old["model_runtime_configuration"]["records"]}
    count, error, started, clock = 0, None, now(), time.monotonic()
    try:
        with (output / "results.jsonl").open("x") as stream:
            for unit in plan["targets"]:
                uid = unit["model_unit_id"]
                backend = load_measurement_model(permit=permit, repository_root=source, capsule_root=capsule,
                    construction_authorization=authorization,
                    inspection={**identities[uid], "construction_authorization_sha256": authorization["authorization_sha256"]},
                    decoding_record=decodings[uid], runtime_record=runtimes[uid])
                for q in plan["panel"]:
                    job_id = uid + ":" + q["query_id"]
                    permit.begin_trial(job_id)
                    ids = backend.tokenizer.encode(q["prompt_text"], add_special_tokens=False).ids
                    result = backend.complete(ids, operation_id=job_id, prompt_text=q["prompt_text"])
                    row = {"job_id": job_id, "query_id": q["query_id"], "phase": q["phase"],
                           "observation": observation(q, unit["target_id"], result.output_text),
                           "telemetry": result.completion_record}
                    stream.write(canonical(row) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                    permit.finish_trial(job_id, seal(row))
                    count += 1
                del backend
                gc.collect()
                import torch
                torch.cuda.empty_cache()
                print(canonical({"completed_target": unit["target_id"], "completed_queries": count}), flush=True)
        permit.finish()
    except BaseException as exc:
        error = {"category": type(exc).__name__}
        permit.abort(type(exc).__name__)
        raise
    finally:
        journal.close()
        receipt = {"scope": SCOPE, "stage": "furnace", "status": "complete" if error is None and count == OSS_N else "failed",
                   "plan_sha256": args.expected_plan_sha256, "started_at": started, "completed_at": now(),
                   "wall_seconds": time.monotonic() - clock, "counts": permit.counts(), "error": error,
                   "event_chain": verify_event_journal(output / "events.jsonl"),
                   "artifacts": {p.name: digest(p) for p in output.iterdir() if p.is_file()}}
        write_new(output / "attempt_receipt.json", receipt)
        print(canonical({k: v for k, v in receipt.items() if k != "artifacts"}), flush=True)


def checked_results(directory, plan_sha):
    directory = Path(directory)
    receipt = read(directory / "attempt_receipt.json")
    check(receipt["status"] == "complete" and receipt["plan_sha256"] == plan_sha, "incomplete or different source attempt")
    for filename, expected in receipt["artifacts"].items():
        check(digest(directory / filename) == expected, "source evidence changed")
    return rows(directory / "results.jsonl")


def lock_forecast(args):
    plan = read(args.plan)
    validate(plan)
    plan_sha = digest(args.plan)
    check(not (Path(args.output).parent / "api-challenge.claim.json").exists(), "challenge already started")
    reference = checked_results(args.furnace, plan_sha)
    weak = checked_results(args.weak, plan_sha)
    target_feature = features([r["observation"] for r in weak])
    reference_features = {u["target_id"]: features([r["observation"] for r in reference
                          if r["phase"] == "weak" and r["observation"]["target_id"] == u["target_id"]]) for u in plan["targets"]}
    matches = [u for u in plan["targets"] if reference_features[u["target_id"]] == target_feature]
    predictions = []
    for q in [q for q in plan["panel"] if q["phase"] == "challenge"]:
        probabilities = None
        if matches:
            families = sorted({u["base_model_unit_id"] for u in matches})
            distributions = []
            for family in families:
                targets = {u["target_id"] for u in matches if u["base_model_unit_id"] == family}
                selected = [r for r in reference if r["phase"] == "challenge"
                            and r["observation"]["target_id"] in targets
                            and r["query_id"].rsplit(":r", 1)[0] == q["query_id"].rsplit(":r", 1)[0]]
                counts = Counter({state: 1 for state in STATES})
                counts.update(marker(r["observation"]["output_text"]) for r in selected)
                distributions.append([counts[state] / sum(counts.values()) for state in STATES])
            probabilities = [sum(d[i] for d in distributions) / len(distributions) for i in range(3)]
        predictions.append({"query_id": q["query_id"], "probabilities_A_B_failure": probabilities})
    value = {"scope": SCOPE, "created_at": now(), "plan_sha256": plan_sha,
             "weak_receipt_sha256": digest(Path(args.weak) / "attempt_receipt.json"),
             "furnace_receipt_sha256": digest(Path(args.furnace) / "attempt_receipt.json"),
             "api_feature": target_feature, "reference_features": reference_features,
             "support_targets": [u["target_id"] for u in matches],
             "status": "behavior_only_forecast" if matches else "abstain_outside_exact_reference_support",
             "mechanism_attribution": "not_attempted", "predictions": predictions}
    write_new(args.output, value)
    print(canonical({"status": value["status"], "support_count": len(matches), "lock_sha256": digest(args.output), "new_model_calls": 0}))


def api(args):
    check(args.execute and digest(args.plan) == args.expected_plan_sha256, "explicit pinned API execution required")
    plan = read(args.plan)
    validate(plan)
    root = Path(args.plan).parent
    rehearsal = read(root / "rehearsal.json")
    check(rehearsal["status"] == "mock_contracts_passed" and rehearsal["plan_sha256"] == args.expected_plan_sha256, "API mock rehearsal missing")
    lock_hash = None
    if args.phase == "challenge":
        check(args.lock and args.expected_lock_sha256 and digest(args.lock) == args.expected_lock_sha256, "frozen forecast required")
        lock_hash = digest(args.lock)
        lock = read(args.lock)
        check(lock["plan_sha256"] == args.expected_plan_sha256 and len(lock["predictions"]) == 32, "forecast panel differs")
        check(lock["weak_receipt_sha256"] == digest(root / "api-weak-attempt-001/attempt_receipt.json"), "weak receipt changed")
        check(read(root / "api-weak-attempt-001/attempt_receipt.json")["status"] == "complete", "weak phase incomplete")
    key = os.environ.get("OPENAI_API_KEY", "")
    check(key.startswith("sk-") and len(key) > 20, "existing API key unavailable")
    check(not os.environ.get("OPENAI_BASE_URL"), "custom API destination not permitted")
    check(API_N * RESERVATION < PRICE_CAP, "reservation exceeds pilot cost ceiling")
    write_new(root / ("api-" + args.phase + ".claim.json"), {"scope": SCOPE, "phase": args.phase,
              "plan_sha256": args.expected_plan_sha256, "lock_sha256": lock_hash, "resume": False})
    output = Path(args.output)
    output.mkdir(mode=0o700)
    journal = Journal(output / "events.jsonl")
    started, clock = now(), time.monotonic()
    attempted = completed = 0
    usage = Counter()
    error, estimated = None, 0.0
    queries = [q for q in plan["panel"] if q["phase"] == args.phase]
    journal.add("phase_opened", {"phase": args.phase, "plan_sha256": args.expected_plan_sha256, "lock_sha256": lock_hash})
    try:
        with (output / "results.jsonl").open("x") as stream:
            for q in queries:
                check(time.monotonic() - clock <= 900, "API wall-clock cap exceeded")
                journal.add("request_reserved", {"query_id": q["query_id"], "request_sha256": seal(request_body(q)), "reserved_usd": RESERVATION})
                attempted += 1
                response = http_request(request_body(q), key)
                text, meta = decode_response(response)
                check(key not in text and key not in canonical(meta), "unsafe API response")
                row = {"query_id": q["query_id"], "phase": q["phase"],
                       "observation": observation(q, plan["api_target_id"], text), "telemetry": meta}
                stream.write(canonical(row) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
                journal.add("response_saved", {"query_id": q["query_id"], "result_sha256": seal(row)})
                completed += 1
                usage.update(meta["usage"])
                estimated += meta["estimated_uncached_cost_usd"]
                check(estimated <= PRICE_CAP, "observed API cost ceiling exceeded")
                if completed % 20 == 0:
                    print(canonical({"phase": args.phase, "completed": completed, "estimated_cost_usd": estimated}), flush=True)
    except BaseException as exc:
        error = {"category": exc.category if isinstance(exc, SafeAPIError) else type(exc).__name__,
                 "http_status": exc.status if isinstance(exc, SafeAPIError) else None,
                 "outcome_may_be_unknown": attempted > completed}
        journal.add("phase_stopped", error)
        # Suppress raw exception/response messages, which can include sensitive headers.
    finally:
        journal.add("phase_closed", {"attempted": attempted, "completed": completed, "error": error})
        journal.close()
        receipt = {"scope": SCOPE, "stage": "api-" + args.phase,
                   "status": "complete" if error is None and completed == len(queries) else "failed",
                   "plan_sha256": args.expected_plan_sha256, "lock_sha256": lock_hash,
                   "started_at": started, "completed_at": now(), "wall_seconds": time.monotonic() - clock,
                   "attempted_requests": attempted, "completed_requests": completed,
                   "reserved_cost_ceiling_usd": attempted * RESERVATION, "estimated_uncached_cost_usd": estimated,
                   "usage": dict(usage), "error": error,
                   "artifacts": {p.name: digest(p) for p in output.iterdir() if p.is_file()}}
        write_new(output / "attempt_receipt.json", receipt)
        print(canonical({k: v for k, v in receipt.items() if k != "artifacts"}), flush=True)
    if error is not None:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--parent-root", required=True)
    p.add_argument("--output", required=True)
    p = sub.add_parser("rehearse")
    p.add_argument("--plan", required=True)
    p.add_argument("--output", required=True)
    for name in ("furnace", "api"):
        p = sub.add_parser(name)
        for arg in ("plan", "expected-plan-sha256", "output"):
            p.add_argument("--" + arg, required=True)
        p.add_argument("--execute", action="store_true")
        if name == "api":
            p.add_argument("--phase", choices=("weak", "challenge"), required=True)
            p.add_argument("--lock")
            p.add_argument("--expected-lock-sha256")
    p = sub.add_parser("lock")
    for arg in ("plan", "furnace", "weak", "output"):
        p.add_argument("--" + arg, required=True)
    args = parser.parse_args()
    {"prepare": prepare, "rehearse": rehearse, "furnace": furnace, "api": api, "lock": lock_forecast}[args.command](args)


if __name__ == "__main__":
    main()
