#!/usr/bin/env python3
"""Install reviewed wheels only into this checkout's dedicated .venv."""
import os
from pathlib import Path
import platform
import subprocess
import sys
import sysconfig

if __package__:
    from .dependency_check import LOCKS, ROOT, reviewed_pins, verify_installed
else:
    from dependency_check import LOCKS, ROOT, reviewed_pins, verify_installed


def validate_environment(root=ROOT):
    expected = root / ".venv"
    if expected.is_symlink() or Path(sys.prefix).resolve() != expected.resolve():
        raise ValueError("Run this installer only through scripts/setup.sh in its dedicated .venv")
    if sys.prefix == sys.base_prefix or sys.version_info[:2] != (3, 11):
        raise ValueError("A dedicated Python 3.11 virtual environment is required")
    if platform.python_implementation() != "CPython":
        raise ValueError("Only CPython 3.11 is supported by the wheel lock")
    config = {}
    for line in (expected / "pyvenv.cfg").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            config[key.strip().lower()] = value.strip().lower()
    if config.get("include-system-site-packages") != "false":
        raise ValueError("Virtual environments with system site packages are unsupported")
    for name in ("purelib", "platlib", "scripts", "data"):
        if not Path(sysconfig.get_path(name)).resolve().is_relative_to(expected.resolve()):
            raise ValueError("Virtual environment install paths must remain inside this checkout's .venv")
    machine = platform.machine().lower()
    if sys.platform == "darwin":
        if machine not in {"arm64", "x86_64"} or tuple(map(int, platform.mac_ver()[0].split(".")[:2])) < (12, 0):
            raise ValueError("The lock requires macOS 12+ on Apple Silicon or Intel")
    elif sys.platform == "linux":
        libc, version = platform.libc_ver()
        if machine not in {"aarch64", "x86_64"} or libc != "glibc" or tuple(map(int, version.split(".")[:2])) < (2, 28):
            raise ValueError("The lock requires Linux x86_64/aarch64 with glibc 2.28+")
    else:
        raise ValueError("Native Windows and other platforms are unsupported; use supported Linux/WSL2")


def install_environment():
    validate_environment()
    pins = reviewed_pins()
    # A user's PIP_TARGET/PREFIX/USER/config must not redirect writes or relax checks.
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("PIP_") and key not in {"PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE"}}
    environment["PIP_CONFIG_FILE"] = os.devnull
    environment["PYTHONNOUSERSITE"] = "1"
    for filename in LOCKS:
        subprocess.run([
            sys.executable, "-m", "pip", "--disable-pip-version-check", "--no-input",
            "install", "--index-url", "https://pypi.org/simple", "--require-hashes",
            "--only-binary=:all:", "--no-deps", "--upgrade", "-r", str(ROOT / filename),
        ], env=environment, check=True)
    subprocess.run([sys.executable, "-m", "pip", "check"], env=environment, check=True)
    verify_installed(pins)
    print(f"Verified exact inventory: {len(pins)} reviewed packages")


if __name__ == "__main__":
    try:
        install_environment()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
