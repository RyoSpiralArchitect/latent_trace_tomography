"""Measurement functions from the frozen run; the caller supplies verified local assets.

The private host bootstrap and historical checkpoint capsules are not distributed.
Importing this file does not load weights, download anything, or run inference.
"""

import time

import common as s


def input_ids(tok, mode, text):
    if mode == "raw":
        ids = tok.encode(text, add_special_tokens=True)
    else:
        s.ok(mode == "chat" and bool(tok.chat_template), "missing native chat template")
        ids = tok.apply_chat_template(
            [{"role": "user", "content": text}],
            tokenize=True,
            add_generation_prompt=True,
        )
    s.ok(
        type(ids) is list and all(type(i) is int for i in ids) and 0 < len(ids) <= 512,
        "unrecognized or too long tokenized input",
    )
    return ids


def load_legacy(out, u, qs, ctx, pf, ph, stage):
    from latent_trace_tomography.measurement_runner import (
        EventJournal,
        RunPermit,
        verify_event_journal,
    )
    from latent_trace_tomography.measurement_model import load_measurement_model

    src, cap, auth, ids, dec, cfg = ctx
    s.ok(
        s.seal([dec[u], cfg[u]]) == pf["compact"][u]["config_sha256"],
        "legacy runtime changed",
    )
    journal = EventJournal(out / "events.jsonl")
    permit = RunPermit(
        mode="live",
        journal=journal,
        logical_limit=len(qs),
        physical_limit=16 * len(qs),
        max_wall_seconds=480,
        model_identities={u: pf["compact"][u]["composite"]},
        allowed_job_ids={u + "/" + q["qid"] for q in qs},
    )
    start = s.now()
    clock = time.monotonic()
    error = None
    n = 0
    try:
        backend = load_measurement_model(
            permit=permit,
            repository_root=src,
            capsule_root=cap,
            construction_authorization=auth,
            inspection={
                **ids[u],
                "construction_authorization_sha256": auth["authorization_sha256"],
            },
            decoding_record=dec[u],
            runtime_record=cfg[u],
        )
        with (out / "observations.jsonl").open("x") as f:
            for q in qs:
                job = u + "/" + q["qid"]
                txt = q["prompt_text"]
                permit.begin_trial(job)
                x = backend.complete(
                    backend.tokenizer.encode(txt, add_special_tokens=False).ids,
                    operation_id=job,
                    prompt_text=txt,
                ).completion_record
                s.ok(
                    x["prompt_sha256"] == q["prompt_sha256"]
                    and x["text"]
                    == backend.tokenizer.decode(x["generated_token_ids"], skip_special_tokens=True),
                    "legacy visible binding",
                )
                row = {
                    "qid": q["qid"],
                    "prompt_sha256": q["prompt_sha256"],
                    "text": x["text"],
                }
                s.append(f, row)
                permit.finish_trial(job, s.seal(row))
                n += 1
        permit.finish()
    except Exception as ex:
        error = {"type": type(ex).__name__, "message": str(ex)[:280]}
        permit.abort(type(ex).__name__)
    finally:
        journal.close()
    return {
        "status": "complete" if error is None and n == len(qs) else "incomplete",
        "unit": u,
        "mode": "anchor_raw",
        "panel": stage,
        "started": start,
        "ended": s.now(),
        "seconds": time.monotonic() - clock,
        "observed": n,
        "physical": permit.counts()["physical_forwards_completed"],
        "counts": permit.counts(),
        "chain": verify_event_journal(out / "events.jsonl"),
        "error": error,
        "plan_sha256": ph,
    }


def big_stage(out, u, mode, sp, net, tok, qs, pf, ph, stage):
    import torch
    from transformers import GenerationConfig

    xx = [input_ids(tok, mode, q["prompt_text"]) for q in qs]
    s.ok(
        s.seal(xx) == pf["scaled"][u]["input_bindings"][stage][mode]["ids_seal"],
        "large input binding drift",
    )
    eos = net.generation_config.eos_token_id
    eos = [eos] if type(eos) is int else list(eos)
    s.ok(eos and all(type(i) is int for i in eos), "missing EOS")
    pad = tok.pad_token_id if tok.pad_token_id is not None else eos[0]
    config = GenerationConfig(
        do_sample=False,
        num_beams=1,
        max_new_tokens=16,
        use_cache=True,
        eos_token_id=eos,
        pad_token_id=pad,
        bos_token_id=tok.bos_token_id,
    )
    forwards = [0, 0]

    def pre(*args):
        forwards[0] += 1

    def post(*args):
        forwards[1] += 1

    h1 = net.register_forward_pre_hook(pre)
    h2 = net.register_forward_hook(post)
    start = s.now()
    clock = time.monotonic()
    error = None
    n = 0
    budget_exits = 0
    try:
        with (
            torch.inference_mode(),
            (out / "observations.jsonl").open("x") as fs,
            (out / "operations.jsonl").open("x") as ops,
        ):
            for q, ids in zip(qs, xx):
                s.ok(time.monotonic() - clock < 600, "per-track wall limit")
                tensor = torch.tensor([ids], dtype=torch.long, device="cuda:0")
                before = forwards[1]
                s.append(
                    ops,
                    {
                        "event": "started",
                        "qid": q["qid"],
                        "input_ids_sha256": s.seal(ids),
                    },
                )
                ret = net.generate(
                    input_ids=tensor,
                    attention_mask=torch.ones_like(tensor),
                    generation_config=config,
                )
                tokens = ret[0, len(ids) :].tolist()
                s.ok(
                    1 <= len(tokens) <= 16 and 1 <= forwards[1] - before <= 16,
                    "greedy bounds",
                )
                text = tok.decode(
                    tokens, skip_special_tokens=True, clean_up_tokenization_spaces=False
                )
                row = {
                    "qid": q["qid"],
                    "prompt_sha256": q["prompt_sha256"],
                    "text": text,
                }
                s.append(fs, row)
                at_cap = tokens[-1] not in eos
                budget_exits += int(at_cap)
                s.append(
                    ops,
                    {
                        "event": "complete",
                        "qid": q["qid"],
                        "row_sha256": s.seal(row),
                        "new_tokens": len(tokens),
                        "token_limit": at_cap,
                        "forwards": forwards[1] - before,
                        "output_ids_sha256": s.seal(tokens),
                    },
                )
                n += 1
        s.ok(forwards[0] == forwards[1], "physical forward closure")
    except Exception as ex:
        error = {"type": type(ex).__name__, "message": str(ex)[:280]}
    finally:
        h1.remove()
        h2.remove()
    return {
        "status": "complete" if error is None and n == len(qs) else "incomplete",
        "unit": u,
        "mode": mode,
        "panel": stage,
        "started": start,
        "ended": s.now(),
        "seconds": time.monotonic() - clock,
        "observed": n,
        "physical": forwards[1],
        "started_forwards": forwards[0],
        "token_limit_exits": budget_exits,
        "parameter_count": net.num_parameters(),
        "eos": eos,
        "error": error,
        "plan_sha256": ph,
    }
