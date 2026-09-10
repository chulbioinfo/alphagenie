#!/usr/bin/env python3
"""Refresh wheel hashes for already reviewed pins; never select newer versions.

Run from an installed, locked environment (requires its pinned packaging module).
PyPI JSON is the initial trust source, not an independent authenticity guarantee.
This is not a dependency resolver: review the complete pin set, then validate
fresh installs with pip check and tests on all four supported platform families.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import re
import sys

from packaging.specifiers import SpecifierSet
from packaging.tags import compatible_tags, cpython_tags, mac_platforms
from packaging.utils import parse_wheel_filename

if __package__:
    from .dependency_check import ROOT, normalize, read_pins, request_json
else:
    from dependency_check import ROOT, normalize, read_pins, request_json

HEADER = """# Reviewed complete runtime pin set; AlphaGenome 0.8.0 is unchanged.
# SHA256 wheel hashes from official PyPI JSON; initially reviewed 2026-09-10.
# CPython 3.11: macOS 12+ arm64/x86_64; Linux glibc 2.28+ aarch64/x86_64.
# Includes wheels usable on newer macOS; no source, Windows or musl artifacts.
# Install through scripts/setup.sh, which also checks the exact inventory.
# Regenerate only after review: python scripts/refresh_dependency_lock.py --write
"""


def tags_for(platforms):
    return set(cpython_tags((3, 11), abis=["cp311"], platforms=platforms)) | set(
        compatible_tags((3, 11), interpreter="cp311", platforms=platforms))


def linux_platforms(arch):
    return [f"manylinux_2_{minor}_{arch}" for minor in range(28, 4, -1)] + [
        f"manylinux2014_{arch}", f"manylinux2010_{arch}", f"manylinux1_{arch}"]


TARGETS = {
    "macos-arm64": tags_for(list(mac_platforms((12, 0), "arm64"))),
    "macos-x86_64": tags_for(list(mac_platforms((12, 0), "x86_64"))),
    "linux-aarch64": tags_for(linux_platforms("aarch64")),
    "linux-x86_64": tags_for(linux_platforms("x86_64")),
}


def allowed_platform(tag):
    return tag == "any" or bool(re.fullmatch(
        r"macosx_\d+_\d+_(?:arm64|x86_64|universal2)|manylinux(?:\d+|_\d+_\d+)_(?:aarch64|x86_64)", tag))


def wheel_hashes(item, request=request_json):
    name, record = item
    version = record["version"]
    data = request(f"https://pypi.org/pypi/{name}/{version}/json")
    if normalize(data["info"]["name"]) != name or data["info"]["version"] != version:
        raise ValueError(f"PyPI metadata identity mismatch: {name}")
    hashes = set()
    covered = set()
    for artifact in data["urls"]:
        if artifact["packagetype"] != "bdist_wheel" or artifact.get("yanked"):
            continue
        if artifact.get("requires_python") and not SpecifierSet(artifact["requires_python"]).contains("3.11.0"):
            continue
        wheel_name, wheel_version, _, tags = parse_wheel_filename(artifact["filename"])
        if wheel_name != name or str(wheel_version) != version:
            raise ValueError(f"PyPI wheel identity mismatch: {name}")
        platforms = [tag.platform for tag in tags if allowed_platform(tag.platform)]
        if not platforms or not (tags & tags_for(platforms)):
            continue
        digest = artifact["digests"]["sha256"]
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError(f"Invalid PyPI SHA256: {name}")
        hashes.add(digest)
        covered.update(target for target, target_tags in TARGETS.items() if tags & target_tags)
    missing = set(TARGETS) - covered
    if missing:
        raise ValueError(f"No compatible non-yanked wheel for {name} on {', '.join(sorted(missing))}")
    return name, version, sorted(hashes)


def render_lock(records):
    lines = [HEADER.rstrip()]
    for name, version, hashes in sorted(records):
        lines.append(f"{name}=={version} \\")
        for index, digest in enumerate(hashes):
            continuation = " \\" if index + 1 < len(hashes) else ""
            lines.append(f"    --hash=sha256:{digest}{continuation}")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Replace runtime lock hashes after reviewing the existing pins")
    args = parser.parse_args()
    path = ROOT / "requirements-lock.txt"
    pins = read_pins(path, require_hashes=False)
    with ThreadPoolExecutor(max_workers=6) as executor:
        generated = render_lock(executor.map(wheel_hashes, pins.items()))
    if args.write:
        path.write_text(generated, encoding="utf-8")
        print(f"Wrote hashes for {len(pins)} unchanged runtime pins; review the diff and run fresh-install tests.")
    elif generated != path.read_text(encoding="utf-8"):
        raise ValueError("PyPI wheel set differs from the reviewed lock; inspect before using --write")
    else:
        print(f"Official PyPI wheel hashes match {len(pins)} reviewed runtime pins on four platform families.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
