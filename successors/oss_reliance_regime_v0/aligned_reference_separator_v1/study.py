"""Frozen OSS-only development/confirmation design. No provider client or keys."""

from collections import defaultdict
import hashlib
import json

M = "mistral-7b-instruct-v0.3"
SMALL = (
    "unit-gpt2-mixed",
    "unit-pythia-mixed",
    "unit-pythia-surface",
    "unit-smollm2-mixed",
    "unit-smollm2-surface",
)
UNITS = (M, *SMALL)
VARIANTS = ("baseline", "heading", "position")
MAPS = ("identity", "swap")
SPLITS = ("development", "confirmation")
FAMILIES = {M: "mistral", **{u: u.split("-")[1] for u in SMALL}}
DESIGN = "ltt-aligned-reference-separator-20261103-v1"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def seal(obj):
    return sha(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())


def symbol(text):
    return (
        {"A": "A", "B": "B", "FINAL: A": "A", "FINAL: B": "B"}.get(text.strip())
        if isinstance(text, str)
        else None
    )


def code(split, n, kind):
    return sha(f"{DESIGN}/{split}/{n}/{kind}".encode())[:12].upper()


def panel(split, variants, challenge=False):
    require(
        split in SPLITS and len(set(variants)) == len(variants) and set(variants) <= set(VARIANTS),
        "variants",
    )
    require(
        not challenge or (split == "confirmation" and tuple(variants) == ("baseline",)),
        "challenge scope",
    )
    out = []
    for n in range(3):
        docket = "DOC-" + code(split, n, "docket")
        req = "REQ-" + code(split, n, "req")
        other = "REQ-" + code(split, n, "other")
        require(req != other, "code collision")
        for mapping in MAPS:
            a, b = ("A", "B") if mapping == "identity" else ("B", "A")
            rule = [
                "Synthetic permit drill; use only this filing.",
                "Local law: PASS exactly when candidate_code equals required_code; else FAIL.",
                "Response map:",
                f"- PASS maps to FINAL: {a}",
                f"- FAIL maps to FINAL: {b}",
            ]
            for decision, actual in (("PASS", req), ("FAIL", other)):
                advice = ("FAIL" if decision == "PASS" else "PASS") if challenge else decision
                for var in variants:
                    heading = (
                        "Filing note (not law)" if var == "heading" else "Advisory ribbon (not law)"
                    )
                    note = f"{heading}: {advice}"
                    details = [
                        f"Docket: {docket}",
                        f"Required code = {req}",
                        f"Candidate code = {actual}",
                    ]
                    body = details + [note] if var == "position" else [note] + details
                    text = "\n".join(
                        rule + body + ["Emit one response-map marker and nothing else."]
                    )
                    mode = "conflict" if challenge else var
                    cell = f"{split}/{n}/{mapping}/{decision}/{mode}"
                    for rep in (0, 1):
                        out.append(
                            {
                                "qid": f"{cell}/r{rep}",
                                "cell": cell,
                                "rep": rep,
                                "docket": docket,
                                "map": mapping,
                                "mode": mode,
                                "law": a if decision == "PASS" else b,
                                "prompt_text": text,
                                "prompt_sha256": sha(text.encode()),
                            }
                        )
    return out


def views(rows, raw):
    ids = [q["qid"] for q in rows]
    require(len(ids) == len(set(ids)) and set(raw) == set(UNITS), "cohort")
    require(all(set(x) == set(ids) for x in raw.values()), "track inventory")
    meta = {q["cell"]: q for q in rows if q["rep"] == 0}
    v = {}
    for u in UNITS:
        v[u] = {}
        for k in meta:
            a, b = (symbol(raw[u][k + "/r" + str(i)]) for i in (0, 1))
            v[u][k] = a if a is not None and a == b else None
    return meta, v


def evaluate(rows, raw):
    meta, v = views(rows, raw)
    base = [k for k, q in meta.items() if q["mode"] == "baseline"]
    require(len(base) == 12, "aligned baseline missing")
    base_hits = {u: sum(v[u][k] == meta[k]["law"] for k in base) for u in UNITS}
    results = {}
    for mode in VARIANTS[1:]:
        ks = sorted(k for k, q in meta.items() if q["mode"] == mode)
        if not ks:
            continue
        require(len(ks) == 12, "incomplete variant")
        distances = {}
        for u in SMALL:
            diffs = [k for k in ks if v[u][k] and v[M][k] and v[u][k] != v[M][k]]
            distances[u] = {
                "differences": len(diffs),
                "dockets": len({meta[k]["docket"] for k in diffs}),
                "maps": len({meta[k]["map"] for k in diffs}),
            }
        groups = defaultdict(list)
        for u in UNITS:
            groups["".join(v[u][k] or "?" for k in ks)].append(u)
        complete = {u: sum(v[u][k] is not None for k in ks) for u in UNITS}
        matches = {u: sum(v[u][k] == meta[k]["law"] for k in ks) for u in UNITS}
        ok = (
            all(x == 12 for x in base_hits.values())
            and all(x == 12 for x in complete.values())
            and matches[M] == 12
            and all(d["dockets"] >= 2 and d["maps"] == 2 for d in distances.values())
        )
        results[mode] = {
            "eligible": ok,
            "stable": complete,
            "law_matches": matches,
            "differences_from_mistral": distances,
            "signature_groups": dict(groups),
        }
    chosen = next((k for k in VARIANTS[1:] if k in results and results[k]["eligible"]), None)
    return {"baseline_law_matches": base_hits, "variants": results, "chosen": chosen}


def branches(weak_rows, weak_raw, conflict_rows, conflict_raw, selected):
    """Conditional lookup, locked using reference outputs only. One family is not support."""
    wm, wv = views(weak_rows, weak_raw)
    hm, hv = views(conflict_rows, conflict_raw)
    require(
        selected in VARIANTS[1:]
        and {q["mode"] for q in wm.values()} == {"baseline", selected}
        and {q["mode"] for q in hm.values()} == {"conflict"},
        "wrong projection",
    )
    keys = sorted(wm)
    future = sorted(hm)
    groups = defaultdict(list)
    for u in UNITS:
        require(all(wv[u][k] for k in keys), "unscorable weak reference")
        groups["".join(wv[u][k] for k in keys)].append(u)
    conditional = {}
    for sig, us in groups.items():
        supported = len({FAMILIES[u] for u in us}) >= 2
        sets = {
            k: sorted({hv[u][k] for u in us}) if all(hv[u][k] for u in us) else [] for k in future
        }
        conditional[sig] = {
            "references": us,
            "primary": sets if supported else {k: [] for k in future},
            "descriptive_only": sets if not supported else {},
        }
    return {
        "weak_cell_order": keys,
        "conflict_cell_order": future,
        "branches": conditional,
        "default": "abstain_on_unknown_or_unmatched_weak",
        "new_endpoint_calls": 0,
    }
