"""Dependency-neutral canonical content addressing for JSON artifacts.

This module deliberately imports no measurement, execution, registry, or
model-runtime code.  Construction-time generators may therefore use the
frozen canonical JSON convention without loading the OSS-1 evaluation stack.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_artifact_sha256(value: Any) -> str:
    """Return the OSS-1 canonical-JSON SHA-256 for ``value``."""

    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
