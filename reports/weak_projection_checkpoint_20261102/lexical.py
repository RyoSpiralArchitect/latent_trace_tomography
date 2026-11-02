"""Model-free replay of the as-run last-digit panel, two-anchor comparison and controls-only lock.

Extracted from the retained readout. It has no model client, credential, telemetry or
file access. The original module's hash is in the public source pin list.
"""

from collections import Counter
from itertools import product
import hashlib
import json

SCOPE = "ltt_aligned_last_digit_twins_v1"
PAIRS = {
    "gpt2": ("unit-gpt2-mixed", "unit-gpt2-semantic"),
    "smollm2": ("unit-smollm2-mixed", "unit-smollm2-semantic"),
}
UNITS = tuple(u for pair in PAIRS.values() for u in pair)
CONTROLS = ("pass_exact", "fail_legacy", "fail_far")
NEAR = "fail_near"
ARMS = (*CONTROLS, NEAR)
CODEBOOKS = ("identity", "swap")
CELLS = [f"d{d}-{b}" for d, b in product(range(3), CODEBOOKS)]


def check(ok, msg):
    if not ok:
        raise ValueError(msg)


def h(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def seal(v):
    return h(
        json.dumps(v, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=False)
    )


def build():
    panel = []
    for d, book in product(range(3), CODEBOOKS):
        suffix = h(f"{SCOPE}/required/{d}")[:12].upper()
        docket = "DOC-" + h(f"{SCOPE}/docket/{d}")[:12].upper()
        mod = "".join("0123456789ABCDEF"[(int(c, 16) + 1) % 16] for c in suffix)
        req = "REQ-" + suffix
        codes = (req, "ALT-" + mod, "REQ-" + mod, req[:-1] + mod[-1])
        ps, fs = ("A", "B") if book == "identity" else ("B", "A")
        for arm, code in zip(ARMS, codes):
            cue = "PASS" if req == code else "FAIL"
            check((cue == "PASS") == (arm == ARMS[0]), "inconsistent semantic/cue")
            text = "\n".join(
                [
                    "Synthetic permit drill; use only this filing.",
                    "Local law: PASS exactly when candidate_code equals required_code; else FAIL.",
                    "Response map:",
                    f"- PASS maps to FINAL: {ps}",
                    f"- FAIL maps to FINAL: {fs}",
                    f"Advisory ribbon (not law): {cue}",
                    f"Docket: {docket}",
                    f"Required code = {req}",
                    f"Candidate code = {code}",
                    "Emit one response-map marker and nothing else.",
                ]
            )
            cell = f"d{d}-{book}"
            for rep in range(2):
                panel.append(
                    dict(
                        qid=f"{cell}/{arm}/r{rep}",
                        cell=cell,
                        docket=docket,
                        book=book,
                        arm=arm,
                        rep=rep,
                        phase="near" if arm == NEAR else "controls",
                        expected=ps if cue == "PASS" else fs,
                        prompt_text=text,
                        prompt_sha256=h(text),
                        required=req,
                        candidate=code,
                        cue=cue,
                    )
                )
    panel.sort(key=lambda q: (q["phase"] == "near", q["rep"], h(SCOPE + ":" + q["qid"])))
    check(
        len(panel) == len({q["qid"] for q in panel}) == 48
        and len({q["prompt_text"] for q in panel}) == 24,
        "panel count",
    )
    return panel


def symbol(text):
    check(type(text) is str, "visible text only")
    return {"A": "A", "B": "B", "FINAL: A": "A", "FINAL: B": "B"}.get(text.strip())


def view(panel, obs, phase=None):
    """Require exactly the expected prompt slots, even for the controls-only seal."""
    planned = [q for q in panel if phase is None or q["phase"] == phase]
    check(set(obs) == {q["qid"] for q in planned}, "wrong/missing phase inventory")
    data = {}
    for q in planned:
        k = q["cell"], q["arm"]
        data.setdefault(k, []).append((q["rep"], obs[q["qid"]]))
    out = {}
    for k, ps in data.items():
        ps = sorted(ps)
        check([i for i, _ in ps] == [0, 1], "wrong repeats")
        texts = [s for _, s in ps]
        syms = list(map(symbol, texts))
        state = "unresolved" if None in syms else "unstable" if syms[0] != syms[1] else "stable"
        out[k] = {
            "status": state,
            "symbol": syms[0] if state == "stable" else None,
            "symbols": syms,
            "raw_repeat_different": texts[0] != texts[1],
        }
    return out


def classify(ctl, near):
    if any(a["status"] != "stable" for a, expected in ctl):
        return (
            "controls_unresolved"
            if any(a["status"] == "unresolved" for a, _ in ctl)
            else "controls_unstable"
        )
    if any(a["symbol"] != expected for a, expected in ctl):
        return "controls_not_all_correct"
    if any(v["status"] != "stable" for v in near):
        return (
            "near_unresolved" if any(v["status"] == "unresolved" for v in near) else "near_unstable"
        )
    return "near_only_split" if near[0]["symbol"] != near[1]["symbol"] else "near_stable_agreement"


def twin_scores(panel, allobs):
    check(set(allobs) == set(UNITS), "wrong OSS units")
    key = {(q["cell"], q["arm"]): q["expected"] for q in panel}
    v = {u: view(panel, allobs[u]) for u in UNITS}
    result = {}
    for family, (u, w) in PAIRS.items():
        cells = {}
        robust = {}
        for cell in CELLS:
            ctl = [(v[t][cell, a], key[cell, a]) for a in CONTROLS for t in (u, w)]
            near = [v[t][cell, NEAR] for t in (u, w)]
            status = classify(ctl, near)
            direction = (
                "->".join("FAIL" if x["symbol"] == key[cell, NEAR] else "PASS" for x in near)
                if status == "near_only_split"
                else None
            )
            cells[cell] = {
                "classification": status,
                "mixed_to_semantic": direction,
                "by_arm": {a: [v[t][cell, a] for t in (u, w)] for a in ARMS},
            }
        for d in range(3):
            dirs = [cells[f"d{d}-{b}"]["mixed_to_semantic"] for b in CODEBOOKS]
            if dirs[0] and dirs[0] == dirs[1]:
                robust[str(d)] = dirs[0]
        cm = Counter(x["classification"] for x in cells.values())
        result[family] = {
            "units": [u, w],
            "cases": cells,
            "counts": dict(cm),
            "controls_eligible": sum(n for k, n in cm.items() if k.startswith("near_")),
            "near_evaluable": cm["near_only_split"] + cm["near_stable_agreement"],
            "splits": cm["near_only_split"],
            "both_codebooks_by_docket": robust,
            "recurrent_direction": any(n >= 2 for n in Counter(robust.values()).values()),
            "stable_interunit_splits_by_arm": {
                a: sum(
                    v[u][c, a]["status"] == v[w][c, a]["status"] == "stable"
                    and v[u][c, a]["symbol"] != v[w][c, a]["symbol"]
                    for c in CELLS
                )
                for a in ARMS
            },
        }
    return result


def bridge(panel, allobs, endpoint_controls):
    check(set(allobs) == set(UNITS), "wrong OSS units")
    v = {u: view(panel, allobs[u]) for u in UNITS}
    target = view(panel, endpoint_controls, "controls")

    def match(u):
        return all(
            t["status"] == v[u][k]["status"] == "stable" and t["symbol"] == v[u][k]["symbol"]
            for k, t in target.items()
        )

    ids = [u for u in UNITS if match(u)]
    groups = [g for g, p in PAIRS.items() if any(u in ids for u in p)]
    reason = (
        "target_controls_unresolved_or_unstable"
        if any(t["status"] != "stable" for t in target.values())
        else ("fewer_than_two_matching_lineages" if len(groups) < 2 else None)
    )

    def candidates(cell, refs):
        data = [v[u][cell, NEAR] for u in refs]
        if not data or any(d["status"] != "stable" for d in data):
            return []
        return sorted({d["symbol"] for d in data})

    key = {q["cell"]: q["expected"] for q in panel if q["arm"] == NEAR}
    by = {}
    for c in CELLS:
        far = target[c, "fail_far"]
        sel = [] if reason else candidates(c, ids)
        by[c] = {
            "matched": sel,
            "reason": reason or (None if sel else "matched_reference_near_unresolved_or_unstable"),
            "all_oss": candidates(c, UNITS),
            "law": [key[c]],
            "copy_far": [far["symbol"]] if far["status"] == "stable" else [],
        }
    return {
        "matching_ids": ids,
        "matching_base_lineages": groups,
        "global_abstention": reason,
        "cases": by,
        "api_intervention_profile_issued": False,
    }


def close_endpoint(panel, allobs, forecast):
    v = view(panel, allobs)
    key = {(q["cell"], q["arm"]): q["expected"] for q in panel}
    cells = {}
    methods = {name: Counter() for name in ("matched", "all_oss", "copy_far", "law")}
    for c in CELLS:
        n = v[c, NEAR]
        p = forecast["cases"][c]
        for name, counts in methods.items():
            x = p[name]
            kind = "abstention" if not x else "ambiguous" if len(x) > 1 else "singleton"
            counts[kind] += 1
            if x:
                counts[
                    "target_unscorable"
                    if n["status"] != "stable"
                    else kind + ("_hit" if n["symbol"] in x else "_miss")
                ] += 1
        eligible = all(v[c, a]["symbol"] == key[c, a] for a in CONTROLS)
        cells[c] = {
            "all_controls_stably_correct": eligible,
            "near": n,
            "expected_near": key[c, NEAR],
            "outcome": "controls_ineligible"
            if not eligible
            else n["status"]
            if n["status"] != "stable"
            else "near_correct"
            if n["symbol"] == key[c, NEAR]
            else "near_failure",
            "narrowed_and_correct": len(p["all_oss"]) == 2 and p["matched"] == [n["symbol"]],
        }
    return {
        "cases": cells,
        "outcomes": dict(Counter(x["outcome"] for x in cells.values())),
        "methods": {k: dict(t) for k, t in methods.items()},
        "narrowed_and_correct": sum(x["narrowed_and_correct"] for x in cells.values()),
        "by_arm": {
            a: dict(
                stable_correct=sum(v[c, a]["symbol"] == key[c, a] for c in CELLS),
                repeat_unstable=sum(v[c, a]["status"] == "unstable" for c in CELLS),
                unresolved=sum(v[c, a]["status"] == "unresolved" for c in CELLS),
                raw_only_repeat_changes=sum(
                    v[c, a]["status"] == "stable" and v[c, a]["raw_repeat_different"] for c in CELLS
                ),
            )
            for a in ARMS
        },
    }
