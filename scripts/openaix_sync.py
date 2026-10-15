#!/usr/bin/env python3
"""Vendor OpenAIX schemas, catalogues, coordinates.py and examples at one git rev.

Usage: python scripts/openaix_sync.py REV [--source ../openAIX]

Reads from `git archive REV`, never from the working tree, so a dirty tree does not matter.
Refuses if REV does not resolve. Stdlib only.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "opord_builder" / "openaix" / "vendor"
DEFAULT_SOURCE = ROOT.parent / "openAIX"
REPO = "https://github.com/YoloWingPixie/openAIX"

# (archive path prefix or file) -> vendor path
INCLUDE_DIRS = (
    "schemas/",
    "catalogues/",
    "standards/",
    "examples/minimal/",
    "examples/maximal/",
)
INCLUDE_FILES = {
    "tools/openaix/coordinates.py": "coordinates.py",
    "LICENSE": "LICENSE",
    "NOTICE": "NOTICE",
}


def _git(source: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(source), *args], check=True, capture_output=True
    ).stdout


def _origin(source: Path) -> str:
    try:
        return (
            _git(source, "remote", "get-url", "origin")
            .decode()
            .strip()
            .removesuffix(".git")
        )
    except subprocess.CalledProcessError:
        return REPO


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--source")]
    source = DEFAULT_SOURCE
    if "--source" in argv:
        source = Path(argv[argv.index("--source") + 1])
        args = [a for a in args if a != str(source)]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    rev = args[0]
    if not source.is_dir():
        print(f"openaix_sync: source repo not found: {source}", file=sys.stderr)
        return 1
    try:
        commit = (
            _git(source, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
            .decode()
            .strip()
        )
    except subprocess.CalledProcessError:
        print(
            f"openaix_sync: REV {rev!r} does not resolve in {source}", file=sys.stderr
        )
        return 1

    archive = _git(source, "archive", "--format=tar", commit)
    files: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            name = member.name
            if name in INCLUDE_FILES:
                files[INCLUDE_FILES[name]] = tar.extractfile(member).read()
            elif name.startswith(INCLUDE_DIRS) and name.endswith(".json"):
                files[name] = tar.extractfile(member).read()
    missing = [n for n in INCLUDE_FILES.values() if n not in files]
    if missing or not any(n.startswith("schemas/") for n in files):
        print(
            f"openaix_sync: archive at {commit} lacks {missing or 'schemas/'}",
            file=sys.stderr,
        )
        return 1
    files["__init__.py"] = b'"""Vendored OpenAIX (pinned; see VENDOR.json)."""\n'

    common = json.loads(files["schemas/common.schema.json"])
    match = re.fullmatch(r"urn:openaix:schema:common:(.+)", common["$id"])
    version = match.group(1) if match else "unknown"

    if VENDOR.exists():
        shutil.rmtree(VENDOR)
    for name, data in files.items():
        target = VENDOR / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    manifest = {
        "repo": _origin(source),
        "commit": commit,
        "version": version,
        "files": {n: hashlib.sha256(d).hexdigest() for n, d in sorted(files.items())},
    }
    (VENDOR / "VENDOR.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"vendored {len(files)} files from {commit} (version {version})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
