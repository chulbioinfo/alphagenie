#!/usr/bin/env python3
"""Strict lock/inventory checks; optional fail-closed public OSV advisory query.

The network mode submits only public PyPI names and versions, never local paths,
credentials, references or scientific inputs. It does not install or upgrade.
"""
import argparse
import importlib.metadata
import json
from pathlib import Path
import re
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LOCKS = ("requirements-installer.txt", "requirements-lock.txt")
PIN = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([0-9][A-Za-z0-9.!+_-]*)")
HASH = re.compile(r"--hash=sha256:([a-f0-9]{64})")


def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def read_pins(path, *, require_hashes=True):
    """Accept only exact pins and SHA256s: no URLs, includes, options or markers."""
    records = {}
    pending = ""
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        pending += " " + line.removesuffix("\\").strip()
        if line.endswith("\\"):
            continue
        fields = pending.split()
        pending = ""
        match = PIN.fullmatch(fields[0])
        if not match:
            raise ValueError(f"Invalid exact pin in {Path(path).name}")
        name, version = match.groups()
        name = normalize(name)
        if name in records:
            raise ValueError(f"Duplicate pin: {name}")
        hashes = []
        for field in fields[1:]:
            match = HASH.fullmatch(field)
            if not match:
                raise ValueError(f"Invalid hash or unsupported requirement option: {name}")
            hashes.append(match.group(1))
        if require_hashes and not hashes:
            raise ValueError(f"Missing SHA256 hashes: {name}")
        if len(set(hashes)) != len(hashes):
            raise ValueError(f"Duplicate SHA256 hashes: {name}")
        records[name] = {"version": version, "hashes": sorted(hashes)}
    if pending:
        raise ValueError(f"Unfinished requirement in {Path(path).name}")
    if not records:
        raise ValueError(f"Empty requirements file: {Path(path).name}")
    return records


def reviewed_pins(root=ROOT):
    installers, runtime = (read_pins(root / name) for name in LOCKS)
    if set(installers) != {"pip", "setuptools"}:
        raise ValueError("Installer lock must contain only pip and setuptools")
    if set(installers) & set(runtime):
        raise ValueError("Installer packages must not be duplicated in runtime lock")
    # These floors close the installer advisories found in the release audit.
    for name, floor in (("pip", (26, 2)), ("setuptools", (83, 0))):
        version = installers[name]["version"]
        if not re.fullmatch(r"\d+(?:\.\d+)+", version):
            raise ValueError(f"Installer must use a reviewed stable release: {name}")
        if tuple(map(int, version.split("."))) < floor:
            raise ValueError(f"Installer is below the security floor: {name}")
    direct = read_pins(root / "requirements.txt", require_hashes=False)
    for name, record in direct.items():
        if name not in runtime or runtime[name]["version"] != record["version"]:
            raise ValueError(f"Direct dependency differs from runtime lock: {name}")
    if runtime.get("alphagenome", {}).get("version") != "0.8.0":
        raise ValueError("Scientific SDK must remain alphagenome==0.8.0")
    return {**installers, **runtime}


def verify_installed(pins, distributions=None):
    if distributions is None:
        distributions = importlib.metadata.distributions()
    actual = {}
    for distribution in distributions:
        name = normalize(distribution.metadata["Name"])
        if name in actual:
            raise ValueError(f"Duplicate installed distribution: {name}")
        actual[name] = distribution.version
    expected = {name: record["version"] for name, record in pins.items()}
    problems = []
    for name in sorted(set(actual) | set(expected)):
        if name not in expected:
            problems.append(f"unexpected {name}")
        elif name not in actual:
            problems.append(f"missing {name}")
        elif actual[name] != expected[name]:
            problems.append(f"version mismatch {name}")
    if problems:
        raise ValueError("Installed inventory differs from lock: " + ", ".join(problems)
                         + ". Use a fresh dedicated virtual environment; nothing was removed.")


def request_json(url, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={
        "Accept": "application/json", "User-Agent": "AlphaGENIE-dependency-review",
        **({"Content-Type": "application/json"} if payload is not None else {}),
    })
    # One bounded retry, with normal certificate validation; never fail open.
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.load(response)
        except (OSError, ValueError):
            if attempt:
                raise RuntimeError("Public dependency metadata request failed; no clean result is claimed") from None


def query_advisories(pins, request=request_json):
    names = sorted(pins)
    response = request("https://api.osv.dev/v1/querybatch", {"queries": [
        {"package": {"name": name, "ecosystem": "PyPI"}, "version": pins[name]["version"]}
        for name in names
    ]})
    results = response.get("results") if isinstance(response, dict) else None
    if not isinstance(results, list) or len(results) != len(names):
        raise ValueError("Incomplete OSV response; no clean result is claimed")
    findings = {}
    for name, result in zip(names, results):
        if not isinstance(result, dict) or result.get("error") or result.get("next_page_token"):
            raise ValueError("Incomplete or paginated OSV response; no clean result is claimed")
        vulns = result.get("vulns", [])
        if not isinstance(vulns, list) or any(not isinstance(v, dict) or not isinstance(v.get("id"), str) for v in vulns):
            raise ValueError("Invalid OSV findings; no clean result is claimed")
        if vulns:
            findings[name] = sorted({v["id"] for v in vulns})
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed", action="store_true", help="Require exact installed inventory")
    parser.add_argument("--advisories", action="store_true", help="Query public OSV; fail on any match or request failure")
    args = parser.parse_args()
    pins = reviewed_pins()
    if args.installed:
        verify_installed(pins)
    receipt = {"locked_packages": len(pins), "lock_check": "passed", "real_api_calls": 0}
    if args.installed:
        receipt["installed_inventory"] = "exact"
    if args.advisories:
        findings = query_advisories(pins)
        receipt.update({"advisory_source": "https://api.osv.dev", "findings": findings,
                        "warning": "No match is not proof of safety; advisories change over time."})
        print(json.dumps(receipt, indent=2))
        return int(bool(findings))
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
