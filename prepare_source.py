#!/usr/bin/env python3
"""Verify an allowlisted build bundle and patch exactly HSTracker 3.7.0."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
UPSTREAM = "8d5ff46962ad485136cbc863ab62752004bdbe49"


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 prepare_source.py <clean upstream checkout>")
    source = Path(sys.argv[1]).resolve()
    manifest = json.loads((ROOT / "manifest.json").read_text())
    if manifest["upstream_commit"] != UPSTREAM:
        raise SystemExit("Unexpected upstream commit in manifest")
    for rel, expected in manifest["files"].items():
        path = (ROOT / rel).resolve()
        if not path.is_relative_to(ROOT):
            raise SystemExit("Build input escapes bundle")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise SystemExit(f"Changed build input: {rel}")
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if actual != UPSTREAM:
        raise SystemExit("Source checkout is not pinned HSTracker 3.7.0")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=source):
        raise SystemExit("Source checkout must be clean before patching")
    patch = ROOT / "reconnect.patch"
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=source, check=True)
    subprocess.run(["git", "apply", str(patch)], cwd=source, check=True)
    print("Verified build bundle and applied reconnect patch to pinned upstream")


if __name__ == "__main__":
    main()
