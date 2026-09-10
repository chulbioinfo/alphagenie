#!/usr/bin/env python3
"""Generate a reviewed source ZIP, not a backup of private runtime state."""
import hashlib
import json
from pathlib import Path
import zipfile
from release_check import ROOT, source_files, verify

if __name__ == "__main__":
    receipt = verify()
    target = ROOT / "dist/AlphaGENIE-v0.22.0-Brain9-FrontalCortex-English.zip"
    target.parent.mkdir(exist_ok=True)
    # Never silently replace a previously delivered archive.
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in source_files():
            archive.write(path, "AlphaGENIE/" + str(path.relative_to(ROOT)))
    print(json.dumps({**receipt, "archive": str(target.relative_to(ROOT)),
                      "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}, indent=2))
