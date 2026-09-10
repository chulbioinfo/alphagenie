"""Private configuration outside the checkout. Never expose credential values."""
from __future__ import annotations
import json
import os
from pathlib import Path
import stat
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def state_dir():
    path = Path(os.environ.get("ALPHAGENIE_HOME", Path.home() / ".alphagenie")).expanduser().absolute()
    if path.is_symlink():
        raise ValueError("ALPHAGENIE_HOME must not be a symlink")
    path = path.resolve()
    if path.is_relative_to(ROOT) or path == Path.home().resolve() or path == Path(path.anchor):
        raise ValueError("Use a dedicated private state directory outside the checkout")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.stat().st_uid != os.getuid():
        raise ValueError("Private state directory must be owned by the current user")
    path.chmod(0o700)
    return path


def private_write(path, text):
    if path.is_symlink():
        raise ValueError("Refusing a symlink configuration target")
    fd, temporary = tempfile.mkstemp(prefix=".config-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_config():
    path = state_dir() / "config.json"
    if path.is_symlink():
        raise ValueError("Refusing a symlink configuration file")
    return json.loads(path.read_text()) if path.exists() else {}


def save_config(fasta, gtf, samtools):
    from .validation import validate_references
    config = {"fasta": str(Path(fasta).expanduser().resolve()),
              "gtf": str(Path(gtf).expanduser().resolve()),
              "samtools": str(Path(samtools).expanduser().resolve())}
    validate_references(config)
    private_write(state_dir() / "config.json", json.dumps(config, indent=2) + "\n")


def key_available():
    return bool(os.environ.get("ALPHA_GENOME_API_KEY")) or (state_dir() / "credentials.json").is_file()


def read_key():
    key = os.environ.get("ALPHA_GENOME_API_KEY", "").strip()
    if not key:
        path = state_dir() / "credentials.json"
        if not path.exists():
            raise ValueError("No API key configured. Run: python -m alphagenie key set")
        if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) & 0o077 or path.stat().st_uid != os.getuid():
            raise ValueError("Credential file must be owner-only (chmod 600), owned by you, and not a symlink")
        key = json.loads(path.read_text()).get("api_key", "").strip()
    if not 16 <= len(key) <= 512 or any(c.isspace() for c in key):
        raise ValueError("API key is empty or has an invalid format")
    return key
