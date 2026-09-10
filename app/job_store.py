from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from alphagenie.security import redact


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                stage TEXT NOT NULL,
                run_mode TEXT NOT NULL,
                input_json TEXT NOT NULL,
                job_dir TEXT NOT NULL,
                message TEXT NOT NULL DEFAULT '',
                result_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(jobs)").fetchall()
        }
        if "progress_percent" not in cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN progress_percent REAL")


def create_job(
    db_path: Path,
    *,
    job_id: str,
    run_mode: str,
    input_payload: dict[str, Any],
    job_dir: Path,
) -> None:
    now = utc_now()
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO jobs (
              job_id, status, stage, run_mode, input_json, job_dir,
              message, result_json, created_at, updated_at, progress_percent
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                "submitted",
                "submitted",
                run_mode,
                json.dumps(redact(input_payload), indent=2, sort_keys=True),
                str(job_dir),
                "",
                "{}",
                now,
                now,
                2.0,
            ),
        )


def update_job(
    db_path: Path,
    job_id: str,
    *,
    status: str | None = None,
    stage: str | None = None,
    message: str | None = None,
    result: dict[str, Any] | None = None,
    progress_percent: float | None = None,
) -> None:
    fields: list[str] = []
    values: list[Any] = []
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if stage is not None:
        fields.append("stage = ?")
        values.append(stage)
    if message is not None:
        fields.append("message = ?")
        values.append(redact(message))
    if result is not None:
        fields.append("result_json = ?")
        values.append(json.dumps(redact(result), indent=2, sort_keys=True))
    if progress_percent is not None:
        fields.append("progress_percent = ?")
        values.append(max(0.0, min(100.0, float(progress_percent))))
    fields.append("updated_at = ?")
    values.append(utc_now())
    values.append(job_id)
    with connect(db_path) as conn:
        conn.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE job_id = ?", values)


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    data["input"] = json.loads(data.pop("input_json"))
    data["result"] = json.loads(data.pop("result_json") or "{}")
    return data


def get_job(db_path: Path, job_id: str) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    return row_to_dict(row)


def list_jobs(db_path: Path, limit: int = 20) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    return [row_to_dict(r) for r in rows if row_to_dict(r) is not None]
