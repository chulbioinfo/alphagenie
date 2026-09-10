"""Small, dependency-free local privacy boundaries (not an OS sandbox)."""
from __future__ import annotations
import os
import re


def redact(value):
    if isinstance(value, dict):
        return {k: "[REDACTED]" if re.search(r"api.?key|token|password|secret", str(k), re.I)
                else redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if not isinstance(value, str):
        return value
    key = os.environ.get("ALPHA_GENOME_API_KEY", "")
    if key:
        value = value.replace(key, "[REDACTED]")
    return re.sub(r"AIza[A-Za-z0-9_-]{30,}", "[REDACTED]", value)


def child_environment(*, api_key=None, state=None):
    # Do not inherit proxy settings, cloud credentials, PYTHONPATH or AG overrides.
    allowed = ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP",
               "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR")
    env = {k: os.environ[k] for k in allowed if k in os.environ}
    env.update(PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1", MPLBACKEND="Agg")
    if state:
        env["ALPHAGENIE_HOME"] = str(state)
        env["MPLCONFIGDIR"] = str(state / "matplotlib")
    if api_key:
        env["ALPHA_GENOME_API_KEY"] = api_key
    return env
