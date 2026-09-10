"""Fail-closed, resumable provenance for AlphaGenome score TSVs.

The shared web helper defines the inference identity.  This module records
actual scoring segments and guards against appending new scores to legacy or
incompatible output.  No API credentials are stored.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable

_WEB_ROOT = Path(__file__).resolve().parents[3]
if str(_WEB_ROOT) not in sys.path:
    sys.path.insert(0, str(_WEB_ROOT))
from worker.inference_provenance import (  # noqa: E402
    inference_identity,
    model_create_kwargs,
    score_provenance_path,
    utc_now,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def scoring_identity() -> dict[str, Any]:
    gtf = os.environ.get("GENCODE_GTF")
    return inference_identity(gencode_gtf=Path(gtf) if gtf else None)


class ScoreProvenance:
    def __init__(
        self, output: Path, *, identity: dict[str, Any],
        inputs: dict[str, Path], sequence_length: int,
        scorers: Iterable[Any], method: str,
    ) -> None:
        self.output = output
        self.path = score_provenance_path(output)
        self.expected = {
            **identity,
            "sequence_length": sequence_length,
            "scorer_configuration": [repr(scorer) for scorer in scorers],
            "input_sha256": {name: sha256_file(path) for name, path in inputs.items()},
            "method": method,
        }
        self.record: dict[str, Any] = {}
        self.digest = hashlib.sha256()
        self.offset = 0
        self.row_count = 0
        self.completed_ids: set[str] = set()
        self.segment: dict[str, Any] | None = None

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + f".tmp.{os.getpid()}")
        temporary.write_text(json.dumps(self.record, indent=2, sort_keys=True) + "\n")
        temporary.replace(self.path)

    def _read_output(self) -> None:
        if not self.output.exists():
            return
        if self.output.stat().st_size < self.offset:
            raise ValueError("Score output shrank during inference; refusing provenance update")
        with self.output.open("rb") as handle:
            handle.seek(self.offset)
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                self.digest.update(block)
                self.offset += len(block)

    def __enter__(self) -> "ScoreProvenance":
        has_output = self.output.exists() and self.output.stat().st_size > 0
        if self.path.exists():
            self.record = json.loads(self.path.read_text())
            changed = [key for key, value in self.expected.items() if self.record.get(key) != value]
            if changed:
                raise ValueError(f"Incompatible score provenance ({', '.join(changed)}); use a new output path")
            self._read_output()
            saved = self.record.get("output", {})
            if saved.get("size_bytes", 0) != self.offset or saved.get("sha256") != self.digest.hexdigest():
                raise ValueError("Score output does not match its recorded checksum; refusing resume")
            self.row_count = int(saved.get("row_count", 0))
            self.completed_ids = set(self.record.get("completed_ids", []))
        elif has_output:
            raise ValueError("Existing score output has no inference provenance; use a new output path")
        else:
            self.record = {
                **self.expected,
                "backend_revision_source": "unresolved_provider_backend",
                "resolved_model_version": None,
                "inference_started_at": None,
                "inference_completed_at": None,
                "status": "pending",
                "segments": [],
            }
        return self

    def start_segment(self) -> None:
        """Call immediately before constructing the client for new scoring."""
        if self.segment is not None:
            return
        started = utc_now()
        self.segment = {
            "inference_started_at": started,
            "inference_completed_at": None,
            "status": "running",
            "rows_written": 0,
            "variants_written": 0,
        }
        self.record["segments"].append(self.segment)
        if self.record["inference_started_at"] is None:
            self.record["inference_started_at"] = started
        self.record["inference_completed_at"] = None
        self.record["status"] = "running"
        self.checkpoint()

    def checkpoint(self, *, rows_written: int = 0, variant_ids: Iterable[str] = ()) -> None:
        new_ids = set(variant_ids) - self.completed_ids
        self.row_count += rows_written
        self.completed_ids.update(new_ids)
        if self.segment is not None:
            self.segment["rows_written"] += rows_written
            self.segment["variants_written"] += len(new_ids)
        self._read_output()
        self.record["completed_ids"] = sorted(self.completed_ids)
        self.record["output"] = {
            "sha256": self.digest.hexdigest(), "size_bytes": self.offset,
            "row_count": self.row_count, "completed_variant_count": len(self.completed_ids),
        }
        self._write()

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        if self.segment is not None:
            finished = utc_now()
            self.segment["inference_completed_at"] = finished
            self.segment["status"] = "complete" if exc_type is None else "incomplete"
            self.record["status"] = self.segment["status"]
            self.record["inference_completed_at"] = finished if exc_type is None else None
            self.checkpoint()
        return False
