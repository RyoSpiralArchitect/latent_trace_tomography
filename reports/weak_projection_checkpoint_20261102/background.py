"""Recount the historical diagnostics, not additional independent validation units."""

from collections import Counter, defaultdict
from fractions import Fraction
from itertools import combinations

from lexical import check, symbol


def interface(rows):
    groups = defaultdict(Counter)
    pairs = defaultdict(dict)
    by_study = Counter()
    ids = set()
    for r in rows:
        study, family, task, mode = (r[k] for k in ("study", "family", "kind", "render_mode"))
        i = r["query_id"]
        check(i not in ids and mode in ("bare", "marker"), "duplicate or malformed interface slot")
        ids.add(i)
        y = r["output_text"].strip()
        right = symbol(y) == r["expected_answer"]
        joint = right and y == (
            r["expected_answer"] if mode == "bare" else "FINAL: " + r["expected_answer"]
        )
        group = groups[family + "/" + task + "/" + mode]
        group.update({"slots": 1, "right": int(right), "joint": int(joint)})
        key = (family, r["parent_case_id"], r["replicate_id"])
        check(mode not in pairs[key], "duplicate paired format")
        pairs[key][mode] = (r["output_text"], joint)
        by_study[study] += 1
    check(sorted(by_study.values()) == [96, 96] and len(pairs) == 96, "format panel coverage")
    discordant_same_text = Counter()
    for (family, _, _), pair in pairs.items():
        check(set(pair) == {"bare", "marker"}, "unpaired interface contrast")
        bare, marker = pair["bare"], pair["marker"]
        if bare[1] and not marker[1] and bare[0] == marker[0]:
            discordant_same_text[family] += 1
    return {"groups": dict(groups), "bare_only_same_text": dict(discordant_same_text)}


def historical(orbits, clusters, references, collision):
    """All nine own references are for grading; fit a fold from other lineages only."""
    ids = set(clusters)
    check(set(orbits) == set(references) == ids and len(ids) == 9, "historical cohort")
    check(
        len({tuple(r[0] for r in orbits[i]) for i in ids}) == 1
        and all(len(v) == 80 for v in orbits.values()),
        "historical weak slot alignment",
    )
    sig = {i: tuple(symbol(text) for _, text in obs) for i, obs in orbits.items()}
    check(all(None not in v for v in sig.values()), "archived resolved weak signatures expected")
    ticks = {}
    for i, x in references.items():
        n, inf, bad, t, m = (
            x[k] for k in ("pairs", "informative", "unparseable", "targeted", "matched_null")
        )
        check(
            n == x["targeted_parsed"] == x["null_parsed"] == 16
            and bad == 0
            and 0 <= t <= inf <= n
            and 0 <= m <= inf,
            "incomplete historical reference",
        )
        ticks[i] = t - m if inf else None

    def dist(x, y):
        return sum(a != b for a, b in zip(sig[x], sig[y]))

    detail = {}
    for held in sorted(set(clusters.values())):
        train = {
            g: [i for i in sorted(ids) if clusters[i] == g] for g in set(clusters.values()) - {held}
        }
        check(len(train) == 2 and all(len(v) == 3 for v in train.values()), "whole-lineage split")
        radius = {
            g: max(
                min(dist(i, j) for j in members)
                for h, other in train.items()
                if h != g
                for i in other
            )
            for g, members in train.items()
        }
        blind = [ticks[i] for us in train.values() for i in us if ticks[i] is not None]
        for i in sorted(ids):
            if clusters[i] != held:
                continue
            exact = [ticks[j] for us in train.values() for j in us if sig[i] == sig[j]]
            near, inside = {}, True
            for g, group in train.items():
                ds = min(dist(i, j) for j in group)
                inside &= ds <= radius[g]
                near[g] = [ticks[j] for j in group if dist(i, j) == ds]
            num = [v for vs in near.values() for v in vs if v is not None]
            n_possible = any(None in vs for vs in near.values())
            eligible = inside and all(any(v is not None for v in vs) for vs in near.values())
            span = [min(num), max(num)] if eligible and len(set(num)) > 1 else None
            detail[i] = {
                "state": "M" if ticks[i] is not None else "N",
                "ticks": ticks[i],
                "old_exact": [min(exact), max(exact)] if exact and None not in exact else None,
                "old_bracket": span if not n_possible else None,
                "state_candidates": sorted((["M"] if num else []) + (["N"] if n_possible else []))
                if inside
                else [],
                "conditional_ticks": span,
                "support_ticks": sorted(set(num)) if span else [],
                "blind_ticks": [min(blind), max(blind)],
            }

    def contains(bounds, v):
        return bounds[0] <= v <= bounds[1]

    scored = [d for d in detail.values() if d["conditional_ticks"] and d["state"] == "M"]
    exact_scored = [d for d in detail.values() if d["old_exact"] and d["state"] == "M"]
    both_issued = [d for d in detail.values() if d["conditional_ticks"]]
    labels = sorted(Fraction(n, 16) for n in collision["net_transfers"])
    check(
        len(labels) == 2
        and labels[0] < labels[1]
        and len({r["prompt_text"] for r in collision["common_orbit"]})
        == len(collision["common_orbit"])
        == 40,
        "wrong historical collision",
    )

    def width(key):
        return sum(d[key][1] - d[key][0] for d in scored) / (16 * len(scored)) if scored else None

    return {
        "twins_with_opposite_panel_states": sorted(
            [
                list(pair)
                for pair in combinations(sorted(ids), 2)
                if orbits[pair[0]] == orbits[pair[1]]
                and clusters[pair[0]] == clusters[pair[1]]
                and (ticks[pair[0]] is None) != (ticks[pair[1]] is None)
            ]
        ),
        "per_unit": detail,
        "old_exact_scored": len(exact_scored),
        "old_exact_hits": sum(contains(x["old_exact"], x["ticks"]) for x in exact_scored),
        "old_bracket_offers": sum(x["old_bracket"] is not None for x in detail.values()),
        "conditional_offers": len(both_issued),
        "scored_M": len(scored),
        "conditional_hits": sum(contains(d["conditional_ticks"], d["ticks"]) for d in scored),
        "exact_support_hits": sum(d["ticks"] in d["support_ticks"] for d in scored),
        "unconditional_offers": sum(d["state_candidates"] == ["M"] for d in both_issued),
        "mean_width_local": width("conditional_ticks"),
        "mean_width_blind_same_units": width("blind_ticks"),
        "collision_point_error_floor": str((labels[1] - labels[0]) / 2),
        "collision_width_floor": str(labels[1] - labels[0]),
    }
