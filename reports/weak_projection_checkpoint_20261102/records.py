"""Small, strict readers shared by the offline replay and opt-in export."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = HERE / "data"
OLD = ROOT / "reports/mistral_bridge_20261029/data"
FORMAT = ROOT / "successors/oss_reliance_regime_v0/output_contract_probe_v1/fixtures"
FILES = (
    "as_run_protocol.json",
    "panel.json",
    "oss.jsonl",
    "api_controls.jsonl",
    "api_near.jsonl",
    "forecast_lock.json",
    "execution.json",
    "reference_counts.json",
    "surface_collision.json",
    "interface.jsonl",
)
SOURCE_PIN = "7b4e120a7b14d6d5e7a74ccea9184fdf8693f644da86ea44b379fe4082ddd29b"


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse(text):
    def unique(ps):
        out = {}
        for k, v in ps:
            require(k not in out, "duplicate JSON field")
            out[k] = v
        return out

    def bad(_):
        raise ValueError("non-finite JSON")

    return json.loads(text, object_pairs_hook=unique, parse_constant=bad)


def read(path):
    return parse(Path(path).read_text(encoding="utf8"))


def rows(path):
    return [parse(x) for x in Path(path).read_text(encoding="utf8").splitlines()]


def layers(r, keys):
    return {k: r[k] for k in keys}


def checked_pins():
    p = HERE / "source_pins.json"
    require(sha(p) == SOURCE_PIN, "reviewed source pin list changed")
    return read(p)
