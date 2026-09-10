"""Lightweight hg38 FASTA extraction via the `samtools faidx` CLI."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


_SAMTOOLS_CACHED: Optional[str] = None


def _which_samtools() -> str:
    global _SAMTOOLS_CACHED
    if _SAMTOOLS_CACHED is not None:
        return _SAMTOOLS_CACHED
    candidates = [
        os.environ.get("AG_CCG_SAMTOOLS"),
        shutil.which("samtools"),
    ]
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            _SAMTOOLS_CACHED = c
            return c
    raise RuntimeError(
        "samtools not found. Set AG_CCG_SAMTOOLS or add samtools to PATH."
    )


@dataclass(frozen=True)
class FastaExtractor:
    """Thin wrapper around `samtools faidx <fa> chr:start-end`.

    Coordinates are 1-based, inclusive at both ends (samtools convention).
    """

    fasta_path: Path

    def __post_init__(self) -> None:
        if not self.fasta_path.exists():
            raise FileNotFoundError(f"FASTA not found: {self.fasta_path}")
        fai = self.fasta_path.with_suffix(self.fasta_path.suffix + ".fai")
        if not fai.exists():
            raise FileNotFoundError(
                f"FASTA index missing: {fai}. Run `samtools faidx {self.fasta_path}`."
            )

    def fetch(self, chrom: str, start1: int, end1: int) -> str:
        """Return uppercase sequence for chrom:start1-end1 (1-based inclusive)."""
        if start1 < 1 or end1 < start1:
            raise ValueError(f"Bad interval {chrom}:{start1}-{end1}")
        region = f"{chrom}:{start1}-{end1}"
        cmd = [_which_samtools(), "faidx", str(self.fasta_path), region]
        out = subprocess.run(
            cmd, check=True, capture_output=True, text=True
        ).stdout
        lines = [l.strip() for l in out.splitlines() if l and not l.startswith(">")]
        seq = "".join(lines).upper()
        expected = end1 - start1 + 1
        if len(seq) != expected:
            raise RuntimeError(
                f"samtools returned {len(seq)} bp for {region}, expected {expected}."
            )
        return seq

    def fetch_bed(self, chrom: str, start0: int, end0: int) -> str:
        """BED-style helper: 0-based half-open coordinates."""
        return self.fetch(chrom, start0 + 1, end0)


_COMPLEMENT = str.maketrans("ACGTNacgtn", "TGCANtgcan")


def reverse_complement(seq: str) -> str:
    return seq.translate(_COMPLEMENT)[::-1]
