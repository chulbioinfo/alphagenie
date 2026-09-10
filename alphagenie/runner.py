"""Explicit fresh inference only. No network is used when importing this module."""
from __future__ import annotations
import json
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import uuid

from app import job_store
from .config import ROOT, read_config, read_key, state_dir
from .security import child_environment
from .validation import preflight


class JobManager:
    def __init__(self):
        self.state = state_dir()
        self.db = self.state / "jobs.sqlite"
        self.jobs = self.state / "jobs"
        self.jobs.mkdir(mode=0o700, exist_ok=True)
        job_store.init_db(self.db)
        self.lock = threading.Lock()
        self.process = None
        self.current_id = None
        self.closed = False

    def recover(self):
        # A separate OS-level server lock is held before this is called.
        try:
            lock = self.acquire_job_lock()
        except ValueError:
            return  # A surviving worker still owns the lock; never relabel or duplicate it.
        try:
            with job_store.connect(self.db) as conn:
                conn.execute("UPDATE jobs SET status='interrupted', stage='interrupted', "
                             "message='Previous process ended; automatic API retry is disabled' "
                             "WHERE status IN ('submitted', 'running')")
        finally:
            lock.close()

    def acquire_job_lock(self):
        lock = (self.state / "analysis.lock").open("a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            lock.close()
            raise ValueError("A local analysis is still alive, possibly from an earlier server. Wait for it to finish; no duplicate job started.") from exc
        return lock

    def launch(self, rows, dataset_name="Local analysis"):
        with self.lock:
            if self.closed or (self.process and self.process.poll() is None):
                raise ValueError("An analysis is already running or the server is stopping")
            config = read_config()
            validation = preflight(rows, config)
            # Check presence/permissions without placing credentials in arguments or DB.
            read_key()
            job_lock = self.acquire_job_lock()
            try:
                jid = uuid.uuid4().hex
                root = self.jobs / jid
                root.mkdir(mode=0o700)
                from worker.brain9 import VERSION, ANALYSIS_MODE
                from worker.rna_curve import SPEC_ID as CURVE_SPEC_ID
                rows = [{**row, "analysis_mode": ANALYSIS_MODE, "classification_version": VERSION, "curve_spec_id": CURVE_SPEC_ID} for row in rows]
                payload = {"rows": rows, "dataset_name": dataset_name,
                           "analysis_mode": ANALYSIS_MODE, "classification_version": VERSION,
                           "curve_spec_id": CURVE_SPEC_ID, "validation": validation,
                           "reference_variant_group_id": rows[0]["variant_group_id"],
                           "sequence_length": rows[0]["sequence_length"], "null_depth": rows[0]["null_depth"],
                           "inference_run_epoch": jid, "inference_backend_revision": "unresolved_server_default",
                           "requested_model_version": "server_default", "config": config}
                job_store.create_job(self.db, job_id=jid, run_mode="api_full", input_payload=payload, job_dir=root)
            except Exception:
                job_lock.close()
                raise
            env = child_environment(state=self.state)
            # An environment-only key must reach the worker; file keys are read there.
            if os.environ.get("ALPHA_GENOME_API_KEY"):
                env["ALPHA_GENOME_API_KEY"] = os.environ["ALPHA_GENOME_API_KEY"]
            self.current_id = jid
            try:
                self.process = subprocess.Popen([sys.executable, "-m", "alphagenie", "_worker", jid,
                                                 "--lock-fd", str(job_lock.fileno())],
                                                cwd=ROOT, env=env, start_new_session=True,
                                                pass_fds=(job_lock.fileno(),),
                                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                job_lock.close()
                job_store.update_job(self.db, jid, status="failed", stage="failed", message="Could not start worker")
                raise
            threading.Thread(target=self._watch, args=(self.process, jid, job_lock), daemon=True).start()
            return jid

    def _watch(self, proc, jid, job_lock):
        code = proc.wait()
        # Close, do not LOCK_UN: an orphaned scoring child may retain the same lock.
        job_lock.close()
        job = job_store.get_job(self.db, jid)
        if job and job["status"] not in {"complete", "failed", "interrupted"}:
            job_store.update_job(self.db, jid, status="failed", stage="failed",
                                 message=f"Worker ended without a result (exit {code}); no automatic retry")

    def stop(self):
        with self.lock:
            self.closed = True
            if self.process:
                if self.process.poll() is not None:
                    try:
                        unused = self.acquire_job_lock()
                    except ValueError:
                        pass  # A scoring descendant may still hold the inherited lock.
                    else:
                        unused.close()
                        return  # Completed group: do not signal an old, reusable PID.
                try:
                    os.killpg(self.process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    self.process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    pass
                # Cover descendants even if their leader exited first; ESRCH is normal.
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.process.wait()
                job_store.update_job(self.db, self.current_id, status="interrupted", stage="interrupted",
                                     message="Local server stopped; already sent API requests cannot be recalled")


def execute_worker(jid, lock_fd):
    if len(jid) != 32 or any(c not in "0123456789abcdef" for c in jid):
        raise ValueError("Invalid job identifier")
    state = state_dir()
    db = state / "jobs.sqlite"
    job = job_store.get_job(db, jid)
    if not job or job["status"] != "submitted":
        raise ValueError("Only a newly submitted local job may start")
    payload = job["input"]
    key = read_key()
    os.fstat(lock_fd)  # Required inherited lock, retained until process exit.
    env = child_environment(api_key=key, state=state)
    env.update(AG_WEB_ENABLE_API_FULL="1", AG_INFERENCE_BACKEND_REVISION="unresolved_server_default",
               AG_INFERENCE_RUN_EPOCH=jid, AG_REQUESTED_MODEL_VERSION="server_default",
               AG_CCG_SAMTOOLS=payload["config"]["samtools"], AG_LOCAL_RUN_LOCK_FD=str(lock_fd))
    os.environ.clear()
    os.environ.update(env)
    args = dict(db_path=str(db), job_id=jid, job_dir=job["job_dir"],
                v04_reference_run=str(state / "NO_LEGACY_CACHE"),
                v04_pipeline_dir=str(ROOT / "pipeline"), hg38_fasta=payload["config"]["fasta"],
                gencode_gtf=payload["config"]["gtf"])
    # Annotation/FASTA may have changed after validation: check again before network.
    preflight(payload["rows"], payload["config"])
    if len(payload["rows"]) == 1:
        from worker.run_single_variant_job import run_job
        run_job(**args, payload=payload["rows"][0], run_mode="api_full")
    else:
        from worker.run_multi_variant_job import run_multi_variant_job
        run_multi_variant_job(**args, payload=payload)
