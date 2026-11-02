"""Offline acquisition on separately supplied, hash-verified historical model assets."""

import argparse
import gc
import importlib.util
import os
from pathlib import Path
import sys

import study as s

ROOT = Path(__file__).resolve().parent
RUNTIME = "028dbb1e734b842c68bdcd9c540d3ef5933072ef5a921d7f5931b4311ce4f1a7"
HELPER = "597bc968e6c962c6d78377d7e74d2cc08549d12854bb209f3bf9d8735a6a98de"
PREFLIGHT = "2ba56dda8365480faf8eae7d958d333137d6b6d94fc310862cdd7618b5d8577b"
SCALED_PLAN = "b056387e3864a74d5e88aaf773c2466360f7f25e5aabb0e71d0088006b0e002b"
EXTRA = {
    "unit-gpt2-mixed": "f6530287c23bb054fcbdbaaa1c53c5f91e4143546a02aabdac0a47b38a88d5bf",
    "unit-smollm2-mixed": "c5a4f383ff7e56ed1a207e8a87880dcbc47aa1ab86b6f93c18eed42baed8cdd1",
}


def digest(p):
    return s.sha(p.read_bytes())


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def run(a):
    import study_io as io

    rows = io.allowed_rows(a.stage, a.evidence)
    lock = io.verify(a.plan)
    prior = a.prior.resolve(strict=True)
    s.require(
        all(
            digest(prior / k) == v
            for k, v in {
                "remote.py": RUNTIME,
                "common.py": HELPER,
                "preflight.json": PREFLIGHT,
                "plan.json": SCALED_PLAN,
            }.items()
        ),
        "historical run drift",
    )
    s.require(
        all(
            os.environ.get(k) == v
            for k, v in {
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "CUBLAS_WORKSPACE_CONFIG": ":4096:8",
            }.items()
        ),
        "offline deterministic environment",
    )
    sys.path.insert(0, str(prior))
    r = load(prior / "remote.py", "prior_scaled")
    c = r.s
    oldpf = c.read(prior / "preflight.json")
    dest = a.evidence / (a.stage + "-" + a.group)
    dest.mkdir(mode=0o700)
    import torch

    torch.manual_seed(0)
    torch.cuda.manual_seed_all(0)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    receipts = {}
    if a.group == "small":
        src, cap, auth, _, _, _ = r.context()
        pilot = load(r.PARENT / "pilot.py", "prior_matched")
        historical = c.read(r.PARENT / "plan.json")
        _, ad = pilot.validate(historical)
        conf = c.read(Path(historical["package_root"]) / "discovery_authorization.draft.json")
        ids = {
            v["model_unit_id"]: v for v in ad["model_identities"] if v["model_unit_id"] in s.SMALL
        }
        cfgs = [
            {v["model_unit_id"]: v for v in conf[k]["records"] if v["model_unit_id"] in s.SMALL}
            for k in ("discovery_decoding_config", "model_runtime_configuration")
        ]
        dec, cfg = cfgs
        from latent_trace_tomography.anchor_reconstruction import inspect_anchor_reconstruction
        from tokenizers import Tokenizer

        old_reg = c.read(prior / "plan.json")["registry"]["remaining"]
        pf = {"compact": {}}
        for u in s.SMALL:
            i = ids[u]
            measured = inspect_anchor_reconstruction(
                repository_root=src,
                capsule_root=cap,
                construction_authorization=auth,
                expected_construction_authorization_sha256=auth["authorization_sha256"],
                training_run_id=i["training_run_id"],
                expected_checkpoint_sha256=i["checkpoint_sha256"],
                expected_completion_receipt_sha256=i["completion_receipt_sha256"],
                require_base_weights=True,
            )
            expected = EXTRA[u] if u in EXTRA else old_reg[u][1]
            s.require(
                measured["composite_model_artifact_sha256"]
                == expected
                == i["composite_model_artifact_sha256"]
                and measured["adapter_sha256"] == i["adapter_sha256"],
                "anchor identity",
            )
            base = next(
                b
                for b in auth["bases"]
                if b["base_model_unit_id"] == measured["base_model_unit_id"]
            )
            tok = Tokenizer.from_file(str(cap / base["asset_directory"] / "tokenizer.json"))
            s.require(
                not tok.truncation
                and not tok.padding
                and all(
                    0 < len(tok.encode(q["prompt_text"], add_special_tokens=False).ids) <= 256
                    for q in rows
                )
                and dec[u]["max_new_tokens"] == 16
                and not dec[u]["do_sample"],
                "anchor input bounds",
            )
            pin = c.seal([dec[u], cfg[u]])
            if u in oldpf["compact"]:
                s.require(pin == oldpf["compact"][u]["config_sha256"], "changed config")
            pf["compact"][u] = {"composite": expected, "config_sha256": pin}
        ctx = (src, cap, auth, ids, dec, cfg)
        # Exclude content overlap before looking at outputs.
        dockets = {q["docket"] for q in rows}
        existing = {
            t["prompt_text"]
            for train in auth["runs"]
            for t in c.read(cap / train["payload_path"])["cases"]
        }
        existing.update(
            q["prompt_text"] for qs in c.read(prior / "plan.json")["panels"].values() for q in qs
        )
        s.require(
            not any(any(x in t for x in dockets) for t in existing),
            "known training/archive docket overlap",
        )
        for u in s.SMALL:
            dr = dest / u
            dr.mkdir()
            rec = r.load_legacy(dr, u, rows, ctx, pf, a.plan, a.stage)
            receipts[u] = r.finalize(dr, rec)
            gc.collect()
            torch.cuda.empty_cache()
    else:
        from transformers import AutoModelForCausalLM, AutoTokenizer

        sp = c.read(prior / "plan.json")["registry"]["scaled"][s.M]
        s.require(
            all(oldpf["scaled"][s.M][k] == v for k, v in r.assets(sp).items()),
            "Mistral snapshot drift",
        )
        path = str(r.snapshot(sp))
        tok = AutoTokenizer.from_pretrained(
            path, local_files_only=True, trust_remote_code=False, use_fast=True
        )
        ids = [r.input_ids(tok, "chat", q["prompt_text"]) for q in rows]
        pf = {"scaled": {s.M: {"input_bindings": {a.stage: {"chat": {"ids_seal": c.seal(ids)}}}}}}
        net = (
            AutoModelForCausalLM.from_pretrained(
                path,
                local_files_only=True,
                trust_remote_code=False,
                use_safetensors=True,
                dtype=torch.bfloat16,
                attn_implementation="eager",
            )
            .to("cuda:0")
            .eval()
        )
        dr = dest / s.M
        dr.mkdir()
        rec = r.big_stage(dr, s.M, "chat", sp, net, tok, rows, pf, a.plan, a.stage)
        receipts[s.M] = r.finalize(dr, rec)
    records = [c.read(dest / u / "receipt.json") for u in receipts]
    c.write(
        dest / "receipt.json",
        {
            "plan": a.plan,
            "stage": a.stage,
            "group": a.group,
            "gate": io.predecessor(a.stage, a.evidence),
            "prompt_seal": s.seal(rows),
            "tracks": receipts,
            "complete": all(rec["status"] == "complete" for rec in records),
            "logical": sum(rec["observed"] for rec in records),
            "physical": sum(rec["physical"] for rec in records),
            "design_id": lock["id"],
            "new_endpoint_calls": 0,
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage", choices=("development", "confirmation", "conflict"))
    p.add_argument("group", choices=("small", "large"))
    p.add_argument("--prior", type=Path, required=True)
    p.add_argument("--plan", required=True)
    p.add_argument("--evidence", type=Path, required=True)
    run(p.parse_args())
