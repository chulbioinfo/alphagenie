"""Inference identity shared by scoring, publication exports, and the web worker.

The API does not expose a server build identifier. New local runs explicitly
record an unresolved provider backend, not an inferred checkpoint or rollout.
Never add a new inference timestamp when merely loading an existing artifact.
"""
from __future__ import annotations

from datetime import datetime, timezone
from importlib import metadata
import json
import os
from pathlib import Path
from typing import Any, Mapping


INFERENCE_BACKEND_REVISION = "unresolved_server_default"
DEFAULT_INFERENCE_RUN_EPOCH = "local_run_epoch_required"
PROVENANCE_SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def alphagenome_client_version() -> str:
    try:
        return metadata.version("alphagenome")
    except metadata.PackageNotFoundError:
        return "unavailable"


def file_identity(path: Path | str | None) -> dict[str, Any]:
    """Use an explicit path/stat identity without hashing multi-GB references."""
    if path is None:
        return {"status": "unspecified"}
    resolved = Path(path).expanduser().resolve()
    identity: dict[str, Any] = {"path": str(resolved)}
    try:
        stat = resolved.stat()
    except OSError:
        identity["status"] = "unavailable"
    else:
        identity.update(status="available", size_bytes=stat.st_size, mtime_ns=stat.st_mtime_ns)
    return identity


def inference_identity(
    payload: Mapping[str, Any] | None = None,
    gencode_gtf: Path | str | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    return {
        "provenance_schema_version": PROVENANCE_SCHEMA_VERSION,
        "inference_backend_revision": str(
            payload.get("inference_backend_revision")
            or os.environ.get("AG_INFERENCE_BACKEND_REVISION")
            or INFERENCE_BACKEND_REVISION
        ),
        "inference_run_epoch": str(
            payload.get("inference_run_epoch")
            or os.environ.get("AG_INFERENCE_RUN_EPOCH")
            or DEFAULT_INFERENCE_RUN_EPOCH
        ),
        "alphagenome_client_version": alphagenome_client_version(),
        "requested_model_version": str(
            payload.get("requested_model_version")
            or os.environ.get("AG_REQUESTED_MODEL_VERSION")
            or "server_default"
        ),
        "genome_build": str(payload.get("genome_build") or "GRCh38"),
        "gencode_gtf_identity": file_identity(gencode_gtf),
    }


def model_create_kwargs(identity: Mapping[str, Any], dna_client: Any) -> dict[str, Any]:
    requested = str(identity.get("requested_model_version") or "server_default")
    if requested == "server_default":
        return {}
    try:
        version = dna_client.ModelVersion[requested]
    except KeyError as exc:
        raise ValueError(f"Unsupported AlphaGenome model version: {requested}") from exc
    return {"model_version": version}


def start_inference(identity: Mapping[str, Any], *, method: str) -> dict[str, Any]:
    return {
        **identity,
        "method": method,
        "backend_revision_source": "unresolved_provider_backend",
        "resolved_model_version": None,
        "inference_started_at": utc_now(),
        "inference_completed_at": None,
    }


def complete_inference(provenance: Mapping[str, Any]) -> dict[str, Any]:
    return {**provenance, "inference_completed_at": utc_now()}


def cache_provenance_matches(
    status: Mapping[str, Any], expected_identity: Mapping[str, Any], cache_key: str
) -> bool:
    provenance = status.get("inference_provenance")
    if status.get("status") != "ok" or status.get("prediction_cache_key") != cache_key:
        return False
    if not isinstance(provenance, dict):
        return False
    if expected_identity.get("alphagenome_client_version") == "unavailable":
        return False
    if not all(provenance.get(key) == value for key, value in expected_identity.items()):
        return False
    try:
        started = datetime.fromisoformat(str(provenance["inference_started_at"]))
        completed = datetime.fromisoformat(str(provenance["inference_completed_at"]))
        if started.tzinfo is None or completed.tzinfo is None or completed < started:
            return False
        return True
    except (KeyError, ValueError, TypeError):
        return False


def force_prediction_refresh(payload: Mapping[str, Any]) -> bool:
    value = payload.get("force_refresh_predictions", os.environ.get("AG_FORCE_REFRESH_PREDICTIONS", "0"))
    return value is True or str(value).strip().lower() in {"1", "true", "yes"}


def score_provenance_path(score_path: Path | str) -> Path:
    return Path(str(score_path) + ".provenance.json")


def load_score_provenance(score_path: Path | str) -> dict[str, Any]:
    """Read recorded scoring metadata; never infer scoring dates from mtime."""
    path = score_provenance_path(score_path)
    if not path.is_file():
        return {"status": "missing_provenance", "provenance_path": str(path)}
    try:
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise ValueError("provenance must be a JSON object")
    except (OSError, ValueError) as exc:
        return {"status": "invalid_provenance", "provenance_path": str(path), "reason": str(exc)}
    return value


def figure_provenance_label(summary: Mapping[str, Any]) -> str:
    """A concise figure footer distinguishing frozen inference from rendering."""
    real = (summary.get('scoring_provenance') or {}).get('real') or summary.get('inference_provenance') or {}
    sdk = real.get('alphagenome_client_version')
    if not sdk:
        return 'Legacy inference: SDK/revision not recorded'
    ended = real.get('inference_completed_at') or summary.get('inference_completed_at') or ''
    date = str(ended).split('T')[0] or 'date not recorded'
    epoch = 'server checkpoint unresolved'
    return f'AlphaGenome SDK {sdk} | inference {date} | {epoch}'
