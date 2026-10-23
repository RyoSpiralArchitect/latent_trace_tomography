"""Verify that built distributions preserve the repository's packaging contract."""

from __future__ import annotations

import argparse
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Sequence


REQUIRED_FILES = (
    "README.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "CITATION.cff",
    "RESPONSIBLE_USE.md",
    "pyproject.toml",
    "MANIFEST.in",
    "Makefile",
)
REQUIRED_TREES = (
    "docs",
    "schemas",
    "protocols",
    "operations",
    "successors",
    "examples",
    "tests",
    "reports",
)
REQUIRED_WHEEL_PATHS = (
    "latent_trace_tomography/reference_bridge.py",
    "latent_trace_tomography/resources/protocols/synthetic_projection_orbit_v1/protocol.json",
    "latent_trace_tomography/resources/protocols/synthetic_projection_orbit_v1/protocol_manifest.json",
)


def _is_repository_payload(path: Path) -> bool:
    return (
        path.is_file()
        and ".DS_Store" not in path.parts
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    )


def _expected_sdist_paths(repository_root: Path) -> set[str]:
    expected = set(REQUIRED_FILES)
    for relative_tree in REQUIRED_TREES:
        tree = repository_root / relative_tree
        if not tree.is_dir():
            raise AssertionError(f"Required source tree is missing: {relative_tree}")
        tree_files = {
            path.relative_to(repository_root).as_posix()
            for path in tree.rglob("*")
            if _is_repository_payload(path)
        }
        if not tree_files:
            raise AssertionError(f"Required source tree is empty: {relative_tree}")
        expected.update(tree_files)
    return expected


def _sdist_payload_paths(sdist: Path) -> set[str]:
    with tarfile.open(sdist, mode="r:*") as archive:
        members = [member for member in archive.getmembers() if member.isfile()]

    payload: set[str] = set()
    for member in members:
        parts = PurePosixPath(member.name).parts
        if len(parts) > 1:
            payload.add(PurePosixPath(*parts[1:]).as_posix())
    return payload


def verify_dist_dir(dist_dir: Path, repository_root: Path) -> tuple[Path, Path]:
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    wheels = sorted(dist_dir.glob("*.whl"))
    if len(sdists) != 1:
        raise AssertionError(f"Expected exactly one sdist in {dist_dir}, found {sdists}")
    if len(wheels) != 1:
        raise AssertionError(f"Expected exactly one wheel in {dist_dir}, found {wheels}")

    expected = _expected_sdist_paths(repository_root)
    actual = _sdist_payload_paths(sdists[0])
    missing = sorted(expected - actual)
    if missing:
        formatted = "\n".join(f"  - {path}" for path in missing)
        raise AssertionError(f"sdist is missing required paths:\n{formatted}")
    with zipfile.ZipFile(wheels[0]) as archive:
        wheel_paths = set(archive.namelist())
    missing_wheel_paths = sorted(set(REQUIRED_WHEEL_PATHS) - wheel_paths)
    if missing_wheel_paths:
        formatted = "\n".join(f"  - {path}" for path in missing_wheel_paths)
        raise AssertionError(f"wheel is missing required package data:\n{formatted}")
    return sdists[0], wheels[0]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repository_root = Path(__file__).resolve().parents[1]
    sdist, wheel = verify_dist_dir(args.dist_dir.resolve(), repository_root)
    print(f"Verified sdist payload: {sdist}")
    print(f"Found wheel artifact: {wheel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
