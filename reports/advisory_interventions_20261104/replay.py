"""Replay finite-panel decisions from public prompt/output rows. No model or key."""

from collections import Counter
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import re

DATA = Path(__file__).resolve().parent / "data"
MODELS = ("mixed", "semantic")
PANELS = ("original", "balanced")
MAPS = ("identity", "swap")
SIGNS = ("FAIL", "PASS")
ROUTES = ("context", "value", "relay")
LAW_LINE = "Local law: PASS exactly when candidate_code equals required_code; else FAIL."
PRESENTATIONS = {
    "original": (),
    "neutral": ("Filing note: box = east; tray = north.",),
    "ket_pass": ("Ribbon legend: KET = PASS; VOR = FAIL.",),
    "vor_pass": ("Ribbon legend: KET = FAIL; VOR = PASS.",),
}
FILES = {
    "prompts.jsonl",
    "trials.jsonl",
    "luna.jsonl",
    "context.json",
    "source_hashes.json",
    "cue_protocol.json",
    "joint_protocol.json",
    "preflight_amendment.json",
}


def ck(ok, message):
    if not ok:
        raise ValueError(message)


def opposite(a):
    return {"FAIL": "PASS", "PASS": "FAIL", "A": "B", "B": "A"}[a]


def field(text, regex):
    v = re.findall(regex, text, re.MULTILINE)
    ck(len(v) == 1, "ambiguous or missing prompt field")
    return v[0]


def decode(text):
    m = re.fullmatch(r"(?:FINAL: )?([AB])", text.strip())
    ck(m is not None, "unscorable complete response")
    return m[1]


def parse_prompt(txt, presentation="original"):
    req = field(txt, r"^Required code = (REQ-[A-F0-9]{12})$")
    val = field(txt, r"^Candidate code = (REQ-[A-F0-9]{12})$")
    docket = field(txt, r"^Docket: (DOC-[A-F0-9]{12})$")
    cue = field(txt, r"^Advisory ribbon \(not law\): (PASS|FAIL)$")
    ps = field(txt, r"^- PASS maps to FINAL: ([AB])$")
    fs = field(txt, r"^- FAIL maps to FINAL: ([AB])$")
    ck(ps != fs, "ambiguous response map")
    expected = (
        "Synthetic permit drill; use only this filing.",
        LAW_LINE,
        "Response map:",
        f"- PASS maps to FINAL: {ps}",
        f"- FAIL maps to FINAL: {fs}",
        f"Advisory ribbon (not law): {cue}",
        *PRESENTATIONS[presentation],
        f"Docket: {docket}",
        f"Required code = {req}",
        f"Candidate code = {val}",
        "Emit one response-map marker and nothing else.",
    )
    ck(txt == "\n".join(expected), "written rule, presentation or renderer mismatch")
    return {
        "law": "PASS" if req == val else "FAIL",
        "cue": cue,
        "map": "identity" if ps == "A" else "swap",
        "pass": ps,
        "required": req,
        "candidate": val,
        "docket": docket,
    }


def keys():
    return [
        "/".join((p, str(n), r, k, m, a))
        for p, n, r, k, m, a in product(PANELS, range(6), "XY", "XY", MAPS, SIGNS)
    ]


def arms(study, c):
    p, _, r, _, _, a = c.split("/")
    if study == "cue":
        return (
            {"base", *(f"{s}:{op}" for s, op in product(("cue3", "cue6", "map3"), "STN"))}
            if (p, r) == ("original", "X")
            else set()
        )
    if r == "Y":
        return {"base"}
    donors = [("none", "S")] + (list(product(ROUTES, "TN")) if a == "FAIL" else [])
    return {"base", *(":".join((op, rt, k)) for op, (rt, k) in product("STN", donors))}


def count_cue(cells, read, make_arm):
    """Count actual changes, changes to the donor advice, and transfer on informative pairs."""
    all_changes, directed, transfers = (dict.fromkeys("STN", 0) for _ in range(3))
    informative = 0
    for c in cells:
        stem, sign = c.rsplit("/", 1)
        natural = read(c, "base")
        donor = read(stem + "/" + opposite(sign), "base")
        informative += donor != natural
        for op in "STN":
            edited = read(c, make_arm(op))
            all_changes[op] += edited != natural
            directed[op] += edited != natural and edited == int(sign == "FAIL")
            transfers[op] += donor != natural and edited == donor
    return {
        "n": len(cells),
        "all_changes": all_changes,
        "toward_donor_advice": directed,
        "informative_pairs": informative,
        "to_donor_on_informative": transfers,
        "conditional_donor_rate": {
            k: n / informative if informative else None for k, n in transfers.items()
        },
    }


def tally(prompts, trial_rows, api_rows, context):
    cases = keys()
    luna = [
        "/".join(("luna", f"d{n}", s, m, a))
        for n, s, m, a in product(
            range(3), SIGNS, MAPS, ("original", "neutral", "ket_pass", "vor_pass")
        )
    ]
    ck(
        len(prompts) == len(dict(prompts)) and set(dict(prompts)) == set(cases + luna),
        "prompt inventory",
    )
    q = {
        k: parse_prompt(txt, k.split("/")[-1] if k.startswith("luna/") else "original")
        for k, txt in prompts
    }
    codes = {}
    dockets = {}
    for c in cases:
        p, n, req, val, m, a = c.split("/")
        v = q[c]
        ck(
            (a, m, req == val) == (v["cue"], v["map"], v["law"] == "PASS"),
            "condition/prompt mismatch",
        )
        for k, vv in (((p, n, req), v["required"]), ((p, n, val), v["candidate"])):
            ck(codes.setdefault(k, vv) == vv, "literal code changed between sibling conditions")
        ck(dockets.setdefault((p, n), v["docket"]) == v["docket"], "docket changed")
    ck(len(set(dockets.values())) == 12, "dockets reused across reference panels")
    endpoint_dockets, endpoint_codes = {}, {}
    exact_text = dict(prompts)
    ck(len({exact_text[c] for c in luna}) == 48, "duplicate Luna user text")
    for c in luna:
        _, n, law, m, _ = c.split("/")
        ck((law, m, law) == (q[c]["law"], q[c]["map"], q[c]["cue"]), "endpoint not aligned")
        v = q[c]
        ck(
            endpoint_dockets.setdefault(n, (v["docket"], v["required"]))
            == (v["docket"], v["required"]),
            "Luna docket changed",
        )
        ck(
            endpoint_codes.setdefault((n, law), v["candidate"]) == v["candidate"],
            "Luna presentation siblings changed codes",
        )
    ck(len({d for d, _ in endpoint_dockets.values()}) == 3, "Luna dockets not distinct")
    wanted = {
        (s, u, c, a) for s, u, c in product(("cue", "joint"), MODELS, cases) for a in arms(s, c)
    }
    texts = {}
    forwards = Counter()
    for s, u, c, a, txt, nf in trial_rows:
        k = (s, u, c, a)
        ck(
            k in wanted and k not in texts and type(nf) is int and nf > 0,
            "unexpected/duplicate trial",
        )
        decode(txt)
        texts[k] = txt
        forwards[s] += nf
    ck(set(texts) == wanted, "missing trial")

    def y(s, u, c, a):
        return int(decode(texts[s, u, c, a]) == q[c]["pass"])

    stable = {s: 0 for s in ("cue", "joint")}
    old = Counter()
    direct = {}
    factors = {}
    posctrl = {}
    for s, u in product(("cue", "joint"), MODELS):
        src = [c for c in cases if (s, u, c, "base") in texts]
        for c in src:
            for a in ("cue3:S", "cue6:S", "map3:S") if s == "cue" else ("S:none:S",):
                if (s, u, c, a) in texts:
                    ck(
                        texts[s, u, c, "base"] == texts[s, u, c, a],
                        "self replacement changed response",
                    )
                    stable[s] += 1
            if s == "joint" and ("cue", u, c, "base") in texts:
                for a, b in [("base", "base"), ("T:none:S", "cue6:T")]:
                    ck(texts[s, u, c, a] == texts["cue", u, c, b], "historical output drift")
                    old[a] += 1
        if s == "cue":
            posctrl[u] = {}
            for mode in "STN":
                moves = 0
                for c in src:
                    parts = c.split("/")
                    parts[4] = "swap" if parts[4] == "identity" else "identity"
                    d = "/".join(parts)
                    sym = decode(texts[s, u, c, "map3:" + mode])
                    ref = decode(texts[s, u, c, "base"])
                    donor = decode(texts[s, u, d, "base"])
                    ck(ref != donor, "uninterpretable answer-map control")
                    moves += int(ref != sym and sym == donor)
                posctrl[u][mode] = moves
        for panel, sign, law in product(PANELS, SIGNS, (*SIGNS, "ALL")):
            cells = [
                c
                for c in src
                if c.startswith(panel + "/")
                and c.split("/")[2] == "X"
                and q[c]["cue"] == sign
                and (law == "ALL" or q[c]["law"] == law)
            ]
            if not cells:
                continue
            ck(len(cells) == (24 if law == "ALL" else 12), "wrong stratum denominator")
            for site in ("cue3", "cue6") if s == "cue" else ("cue6",):
                direct["/".join((s, u, panel, site, sign, law))] = count_cue(
                    cells,
                    lambda c, op: y(s, u, c, op),
                    lambda op: site + ":" + op if s == "cue" else op + ":none:S",
                )
    for u, p, law, route in product(MODELS, PANELS, SIGNS, ROUTES):
        cells = [
            c
            for c in cases
            if c.startswith(p + "/")
            and c.split("/")[2] == "X"
            and (q[c]["cue"], q[c]["law"]) == ("FAIL", law)
        ]
        count = Counter()
        maps = Counter()
        docs = Counter()
        switches = Counter()
        for c in cells:
            values = {
                a + b: y("joint", u, c, ":".join((a, "none" if b == "S" else route, b)))
                for a, b in product("STN", repeat=2)
            }
            count.update(values)
            dx = values["TT"] - values["TS"]
            switches[dx] += 1
            maps[q[c]["map"]] += dx
            docs[c.split("/")[1]] += dx
        dt = count["TT"] - count["TS"]
        contrasts = [
            dt,
            dt - count["ST"] + count["SS"],
            count["TT"] - count["TN"] - count["NT"] + count["NN"],
            count["TT"] - count["TN"],
        ]
        sign = 1 if law == "FAIL" else -1
        follows = all(
            y("joint", u, c, "base") == int(q[c]["cue"] == "PASS")
            for c in cases
            if c.startswith(p + "/") and c.split("/")[2] == "X"
        )
        support = (
            all(x * sign > 0 for x in [*contrasts, *maps.values()])
            and sum(x * sign > 0 for x in docs.values()) >= 4
            and follows
        )
        factors["/".join((u, p, law, route))] = {
            "pass": dict(count),
            "n": len(cells),
            "contrasts": contrasts,
            "by_map": dict(maps),
            "by_docket": dict(docs),
            "paired_switches": {
                "to_pass": switches[1],
                "to_fail": switches[-1],
                "unchanged": switches[0],
            },
            "primary_gate": support if (u, p, route) == ("mixed", "balanced", "context") else None,
        }
    api = {}
    arms_api = {}
    for c, rep, txt in api_rows:
        ck(
            c in luna and type(rep) is int and rep in (0, 1) and (c, rep) not in api,
            "duplicate or unexpected API row",
        )
        correct = (decode(txt) == q[c]["pass"]) == (q[c]["law"] == "PASS")
        mark = txt.strip().startswith("FINAL: ")
        a = arms_api.setdefault(c.split("/")[-1], Counter())
        a["correct"] += int(correct)
        a["marker" if mark else "bare"] += 1
        api[c, rep] = txt
    ck(len(api) == 96, "missing API trial")
    ck(arms_api == context["literal_luna"]["calls"], "retained endpoint recount disagrees")
    api_changes = sum(api[c, 0] != api[c, 1] for c in luna)
    semantic = [(k, txt) for k, txt in texts.items() if k[0:2] == ("joint", "semantic")]
    return {
        "generations": dict(Counter(k[0] for k in texts)),
        "forwards": dict(forwards),
        "self_shams": stable,
        "historical_exact_text": dict(old),
        "cue_changes": direct,
        "map_control": posctrl,
        "factorials": factors,
        "joint_semantic_mapped_pass": sum(decode(txt) == q[k[2]]["pass"] for k, txt in semantic),
        "luna_by_arm": {k: dict(v) for k, v in arms_api.items()},
        "luna_changed_repeat_texts": api_changes,
    }


def load(root=DATA):
    manifest = json.loads((root / "manifest.json").read_bytes())
    ck(set(manifest) == FILES, "public manifest inventory")
    for n, h in manifest.items():
        ck(sha256((root / n).read_bytes()).hexdigest() == h, "public digest: " + n)

    def jr(n):
        return [json.loads(x) for x in (root / n).read_bytes().splitlines()]

    return (
        jr("prompts.jsonl"),
        jr("trials.jsonl"),
        jr("luna.jsonl"),
        json.loads((root / "context.json").read_bytes()),
    )


def replay(root=DATA):
    return tally(*load(root))


if __name__ == "__main__":
    out = replay()
    selected = {
        k: out[k]
        for k in (
            "generations",
            "forwards",
            "self_shams",
            "historical_exact_text",
            "joint_semantic_mapped_pass",
            "luna_by_arm",
            "luna_changed_repeat_texts",
        )
    }
    selected["fresh_primary"] = {
        law: out["factorials"][f"mixed/balanced/{law}/context"] for law in SIGNS
    }
    selected["cue_direction_comparisons"] = {
        k: v for k, v in out["cue_changes"].items() if k.endswith("/ALL")
    }
    print(json.dumps(selected, indent=2, sort_keys=True))
