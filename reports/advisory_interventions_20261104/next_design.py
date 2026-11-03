"""Logic examples for an unexecuted proposal, not a registered protocol or acquisition tool."""

from itertools import product

CELLS = set(product(range(6), ("identity", "swap")))
COMPARATORS = ("cue_only", "cue_plus_last", "cue_plus_span_null")
ARMS = ("cue_plus_span", *COMPARATORS)


def assess(cells, *, controls_valid):
    """An incremental decision only; a tie never tests absolute sufficiency."""
    if controls_valid is not True or set(cells) != CELLS:
        return {"status": "INCONCLUSIVE"}
    if any(
        set(v) != set(ARMS) or any(type(i) is not int or i not in (0, 1) for i in v.values())
        for v in cells.values()
    ):
        return {"status": "INCONCLUSIVE"}
    contrasts = {}
    favorable = {}
    for arm in COMPARATORS:
        dx = {c: v["cue_plus_span"] - v[arm] for c, v in cells.items()}
        by_map = {m: sum(dx[n, m] for n in range(6)) for m in ("identity", "swap")}
        by_docket = {n: dx[n, "identity"] + dx[n, "swap"] for n in range(6)}
        contrasts[arm] = {
            "to_pass": sum(x == 1 for x in dx.values()),
            "to_fail": sum(x == -1 for x in dx.values()),
            "by_map": by_map,
            "by_docket": by_docket,
        }
        favorable[arm] = {n for n, v in by_docket.items() if v > 0}
    common = set.intersection(*favorable.values())
    advance = (
        all(v > 0 for c in contrasts.values() for v in c["by_map"].values()) and len(common) >= 4
    )
    return {
        "status": "ADVANCE_INCREMENT" if advance else "NO_INCREMENT_DEMONSTRATED",
        "common_dockets": sorted(common),
        "contrasts": contrasts,
        "approvals": {a: sum(v[a] for v in cells.values()) for a in ARMS},
    }
