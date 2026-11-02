from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def ok(c, msg):
    if not c:
        raise ValueError(msg)


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(p):
    with Path(p).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def seal(x):
    return hashlib.sha256(
        json.dumps(
            x,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def read(p):
    return json.loads(Path(p).read_text())


def lines(p):
    return [json.loads(v) for v in Path(p).read_text().splitlines()]


def write(p, obj):
    with Path(p).open("x") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())


def append(f, x):
    f.write(json.dumps(x, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n")
    f.flush()
    os.fsync(f.fileno())


def reg():
    return read(ROOT / "registry.json")


def files_ok(plan):
    ok(
        all(
            sha(ROOT / k) == v
            for k, v in plan["source_hashes"].items()
            if k in ("common.py", "remote.py", "protocol.json", "registry.json")
        ),
        "changed remote files",
    )


def family_map(registry):
    return {
        **registry["prior"],
        **{u: r[0] for u, r in registry["remaining"].items()},
        **{u: r["family"] for u, r in registry["scaled"].items()},
    }


def symbol(t):
    ok(type(t) is str, "only visible text is parseable")
    return {"A": "A", "B": "B", "FINAL: A": "A", "FINAL: B": "B"}.get(t.strip())


def make_view(panel, obs):
    ids = {q["qid"] for q in panel}
    ok(len(ids) == len(panel) and set(obs) <= ids, "extra or duplicate planned slot")
    grouped = {}
    for q in panel:
        k = q["qid"].rsplit("/", 1)[0]
        grouped.setdefault(k, {})[q["rep"]] = obs.get(q["qid"])
    v = {}
    for k, r in grouped.items():
        ok(set(r) == {0, 1}, "incorrect repeat count")
        raw = [r[0], r[1]]
        syms = [None if a is None else symbol(a) for a in raw]
        status = (
            "missing"
            if None in raw
            else "unresolved"
            if None in syms
            else "unstable"
            if syms[0] != syms[1]
            else "stable"
        )
        v[k] = {"state": status, "answer": syms[0] if status == "stable" else None}
    return v


def compare(t, v, keys):
    ok(bool(keys), "empty observation surface")
    hit = []
    miss = []
    unknown = []
    for k in keys:
        if t[k]["state"] != "stable" or v[k]["state"] != "stable":
            unknown.append(k)
        elif t[k]["answer"] != v[k]["answer"]:
            miss.append(k)
        else:
            hit.append(k)
    return {
        "verdict": "OUT" if miss else "UNKNOWN" if unknown else "IN",
        "n": len(keys),
        "matches": len(hit),
        "mismatches": len(miss),
        "unresolved": len(unknown),
        "mismatch_cells": miss,
        "unresolved_cells": unknown,
    }


def summarize_bank(obs):
    parts = {
        k: sorted(u for u, rec in obs.items() if rec["verdict"] == k)
        for k in ("IN", "OUT", "UNKNOWN")
    }
    ok(bool(obs), "empty bank")
    return {
        "status": "IN" if parts["IN"] else "UNKNOWN" if parts["UNKNOWN"] else "OUT",
        **parts,
    }


def surfaces(panel):
    return tuple(
        sorted({q["qid"].rsplit("/", 1)[0] for q in panel if q["phase"] == p})
        for p in ("controls", "challenge")
    )


def weak_predict(target_weak, refs, families, weak, held):
    ok(
        set(target_weak) == set(weak) and not set(weak) & set(held),
        "future or missing target features",
    )
    results = {u: compare(target_weak, v, weak) for u, v in refs.items()}
    ws = summarize_bank(results)
    matches = ws["IN"]
    groups = sorted({families[u] for u in matches})
    offers = {}
    reasons = {}
    for k in held:
        if len(groups) < 2:
            offers[k] = []
            reasons[k] = "fewer_than_two_resolved_matching_families"
        elif any(refs[u][k]["state"] != "stable" for u in matches):
            offers[k] = []
            reasons[k] = "matching_reference_with_unresolved_challenge"
        else:
            offers[k] = sorted({refs[u][k]["answer"] for u in matches})
            reasons[k] = None
    return {
        "weak": ws,
        "matching_families": groups,
        "offers": offers,
        "abstention_reasons": reasons,
        "has_uncontradicted_unknown_weak_references": bool(ws["UNKNOWN"]),
    }


def score_bank(t, refs, families, weak, held, pred):
    ok(
        pred == weak_predict({k: t[k] for k in weak}, refs, families, weak, held),
        "weak-only forecast changed",
    )
    by = {
        u: {
            label: compare(t, v, keys)
            for label, keys in (
                ("weak", weak),
                ("conflict", held),
                ("joint", weak + held),
            )
        }
        for u, v in refs.items()
    }
    joint = summarize_bank({u: d["joint"] for u, d in by.items()})
    counts = Counter()
    for k, x in pred["offers"].items():
        if not x:
            tag = "abstained"
        elif t[k]["state"] != "stable":
            tag = "target_unscorable"
        else:
            tag = ("singleton_" if len(x) == 1 else "both_") + (
                "hit" if t[k]["answer"] in x else "miss"
            )
        counts[tag] += 1
    return {
        "individuals": by,
        "weak": pred["weak"],
        "joint": joint,
        "weak_prediction_counts": dict(counts),
        "weak_OUT_but_joint_not_OUT": pred["weak"]["status"] == "OUT"
        and joint["status"] != "OUT",
        "joint_OUT_not_detected_from_weak": joint["status"] == "OUT"
        and pred["weak"]["status"] != "OUT",
    }
