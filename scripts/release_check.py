#!/usr/bin/env python3
"""Read-only allowlist, secret-pattern and sealed-data scanner. Never prints matches."""
import hashlib
import json
from pathlib import Path
import re
import sys
from language_check import check_english_release

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = {"alphagenie", "app", "worker", "pipeline", "data", "docs", "examples", "scripts", "tests", ".github"}
FILES = {"README.md", "README.ko.md", "LICENSE", "NOTICE.md", "SECURITY.md", "requirements.txt",
         "requirements-lock.txt", "package.json", ".gitignore", ".gitattributes", "SOURCE_ORIGIN.json"}
EXCLUDED_PARTS = {"__pycache__", ".git", ".venv", ".pytest_cache", "node_modules", "dist"}
BAD_SUFFIXES = {".sqlite", ".sqlite3", ".db", ".log", ".pem", ".key", ".fa", ".fasta", ".fai", ".gtf"}
PATTERNS = [re.compile(rb"AIza[A-Za-z0-9_-]{30,}"),
            re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
            re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})"),
            re.compile(rb"/(?:Users|Volumes)/[A-Za-z0-9_-]+/")]


def source_files():
    found = []
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS for part in relative.parts) or path.suffix in {".pyc", ".pyo"} or path.name == ".DS_Store":
            continue
        if path.is_symlink():
            raise ValueError(f"Symlink prohibited in source release: {relative}")
        if not path.is_file():
            continue
        if relative.parts[0] not in DIRECTORIES and str(relative) not in FILES:
            raise ValueError(f"Unexpected root file, review before publishing: {relative}")
        if path.suffix in BAD_SUFFIXES or path.name.startswith(".env") or path.name in {"credentials.json", "config.local.json"} or path.name.endswith(".gtf.gz"):
            raise ValueError(f"Runtime/private file prohibited: {relative}")
        found.append(path)
    return found


def verify():
    files = source_files()
    english_files = check_english_release(files)
    for path in files:
        if path.stat().st_size >= 95 * 1024 * 1024:
            raise ValueError(f"File too large for ordinary GitHub source: {path.relative_to(ROOT)}")
        content = path.read_bytes()
        if any(pattern.search(content) for pattern in PATTERNS):
            raise ValueError(f"Potential secret/private path in {path.relative_to(ROOT)}; value suppressed")
    data = ROOT / "data/manuscript_v020_20260909"
    manifest = json.loads((data / "manifest.json").read_text())
    if manifest["data_version"] != "v0.20" or manifest["n_null_per_variant"] != 1000 or manifest["n_variants"] != 17:
        raise ValueError("Wrong manuscript release")
    actual = {str(p.relative_to(data)) for p in files if p.is_relative_to(data) and p.name != "manifest.json"}
    if actual != set(manifest["files"]):
        raise ValueError("Saved manuscript inventory differs from manifest")
    for relative, expected in manifest["files"].items():
        path = (data / relative).resolve()
        if not path.is_relative_to(data.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Saved manuscript integrity failure: {relative}")
    return {"status": "passed", "source_files": len(files), "sealed_assets": len(actual),
            "english_text_files_checked": english_files,
            "size_bytes": sum(p.stat().st_size for p in files), "real_api_calls": 0,
            "warning": "Heuristic scan is not a guarantee; inspect staged files and confirm licensing before publication."}


if __name__ == "__main__":
    try:
        print(json.dumps(verify(), indent=2))
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
