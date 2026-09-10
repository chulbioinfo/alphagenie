"""Loopback-only viewer and explicit job submission; no public-service routes."""
from __future__ import annotations
from contextlib import asynccontextmanager
import asyncio
import csv
import fcntl
import math
from pathlib import Path
import secrets
import re
import threading

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import ClientDisconnect

from app import job_store, manuscript_release as release, site_v021
from app.request_limits import RateBudget, is_render_path
from .config import ROOT, key_available, read_config, state_dir
from .runner import JobManager
from .validation import parse_variants, preflight

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; connect-src 'self'; frame-src 'none'; object-src 'none'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
BODY_TIMEOUT_SECONDS = 10


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    tsv: str = Field(min_length=1, max_length=100000)
    sequence_length: int = 1048576
    null_depth: int = 1000
    dataset_name: str = Field(default="Local analysis", pattern=r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}$")
    consent: bool = False


def create_app(port=8877):
    state = state_dir()
    manager = JobManager()
    # Deliberately no login: this is not a security boundary against other OS
    # users or local programs. This random token only protects browser writes
    # alongside exact Host/Origin checks; any local client can fetch status.
    token = secrets.token_urlsafe(32)
    analysis_slot = threading.BoundedSemaphore(1)
    analysis_budget = RateBudget(per_client=8, total=8)
    render_slot = threading.BoundedSemaphore(1)
    render_budget = RateBudget(per_client=30, total=120)
    body_slots = threading.BoundedSemaphore(8)
    host = f"127.0.0.1:{port}"
    origin = "http://" + host

    @asynccontextmanager
    async def lifespan(app):
        with (state / "server.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("Another server already uses this private state directory") from exc
            release.manifest()
            manager.recover()
            try:
                yield
            finally:
                manager.stop()

    app = FastAPI(title="AlphaGENIE Local", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.manager = manager
    app.state.analysis_budget = analysis_budget
    app.state.render_slot = render_slot
    app.state.render_budget = render_budget

    async def receive_body(request):
        if not body_slots.acquire(blocking=False):
            return JSONResponse({"detail": "Local request readers are busy. Retry shortly."}, status_code=503,
                                headers={"Retry-After": "1"})
        try:
            # Bound bytes, elapsed upload time and reader count, including
            # chunked requests. This is resource admission, not user identity.
            chunks, total = [], 0
            async with asyncio.timeout(BODY_TIMEOUT_SECONDS):
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > 110_000:
                        return JSONResponse({"detail": "Request too large"}, status_code=413)
                    chunks.append(chunk)
            request._body = b"".join(chunks)
        except TimeoutError:
            return JSONResponse({"detail": "Request body timed out"}, status_code=408)
        except ClientDisconnect:
            return JSONResponse({"detail": "Request disconnected"}, status_code=400)
        finally:
            body_slots.release()

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        if request.headers.getlist("host") != [host]:
            return JSONResponse({"detail": "Use the exact 127.0.0.1 local URL"}, status_code=403)
        if len(request.headers.getlist("origin")) > 1:
            return JSONResponse({"detail": "Exactly one Origin is permitted"}, status_code=403)
        incoming_origin = request.headers.get("origin")
        if (incoming_origin and incoming_origin != origin) or request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Cross-origin requests are not permitted"}, status_code=403)
        if request.method not in {"GET", "HEAD"}:
            if incoming_origin != origin:
                return JSONResponse({"detail": "Exact local Origin required"}, status_code=403)
            if not secrets.compare_digest(request.headers.get("x-alphagenie-token", "").encode(), token.encode()):
                return JSONResponse({"detail": "Local request token required"}, status_code=403)
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"detail": "JSON required"}, status_code=415)
        is_analysis = request.method == "POST" and request.url.path in {"/api/local/validate", "/api/local/jobs"}
        rendering = is_render_path(request.url.path)
        if rendering:
            # Loopback clients share an IP budget. Forwarded headers cannot mint
            # identities; this server is never configured to trust a proxy.
            identity = request.client.host if request.client else "unknown"
            if not render_budget.allow(identity):
                return JSONResponse({"detail": "Too many figure requests. Please wait one minute."}, status_code=429,
                                    headers={"Retry-After": "60"})
        admission_slot = render_slot if rendering else analysis_slot if is_analysis else None
        if admission_slot is not None and not admission_slot.acquire(blocking=False):
            detail = ("A figure is being prepared. Please try again shortly." if rendering
                      else "A reference check or submission is already in progress. Retry shortly.")
            return JSONResponse({"detail": detail}, status_code=503, headers={"Retry-After": "2" if rendering else "1"})
        try:
            if is_analysis:
                if not analysis_budget.allow("local-analysis"):
                    return JSONResponse({"detail": "Analysis request budget reached. Please wait one minute."},
                                        status_code=429, headers={"Retry-After": "60"})
            if request.method not in {"GET", "HEAD"}:
                denied = await receive_body(request)
                if denied is not None:
                    return denied
            return await call_next(request)
        finally:
            if admission_slot is not None:
                admission_slot.release()

    @app.middleware("http")
    async def response_security(request: Request, call_next):
        # Include no-store and the other response boundaries on denials too.
        response = await call_next(request)
        response.headers.update({"Content-Security-Policy": CSP, "Cache-Control": "no-store",
                                 "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
                                 "X-AlphaGENIE-Local": "true"})
        return response

    @app.exception_handler(ValueError)
    async def bad_input(request, exc):
        # Deliberately do not return arbitrary worker/provider exception text.
        from .security import redact
        return JSONResponse({"detail": redact(str(exc))}, status_code=422)

    @app.exception_handler(RequestValidationError)
    async def schema_error(request, exc):
        # Do not reflect arbitrary submitted values, including accidental secrets.
        return JSONResponse({"detail": "Invalid request fields or types. Use the documented form/TSV columns."}, status_code=422)

    app.include_router(site_v021.router)
    app.mount("/static", StaticFiles(directory=ROOT / "app/static"), name="static")

    @app.get("/")
    def index():
        return FileResponse(ROOT / "app/static/v021/index.html", media_type="text/html")

    @app.get("/api/manuscript/figures/{key}/{filename}")
    def artifact(key: str, filename: str):
        return FileResponse(release.asset(f"{release.preset_key(key)}/{filename}"))

    @app.get("/api/release")
    def release_metadata():
        return release.public_release()

    @app.get("/api/local/status")
    def status():
        cfg = read_config()
        return {"token": token, "key_configured": key_available(), "references_configured": bool(cfg),
                "ui_version": "0.23", "engine_version": "0.20", "new_analysis_endpoint": "Brain9",
                "saved_result_endpoint": "Brain9", "key_entry": "terminal only",
                "new_rna_curve": "Frontal cortex; GTEx Brain_Cortex; UBERON:0001870; polyA+; unstranded",
                "external_inference_provider": "Google DeepMind AlphaGenome API"}

    @app.post("/api/local/validate")
    def validate(body: Submission):
        return preflight(parse_variants(body.tsv, body.sequence_length, body.null_depth), read_config())

    @app.post("/api/local/jobs", status_code=202)
    def submit(body: Submission):
        if not body.consent:
            raise HTTPException(422, "Explicit consent to API transmission and applicable terms is required")
        rows = parse_variants(body.tsv, body.sequence_length, body.null_depth)
        jid = manager.launch(rows, body.dataset_name)
        return {"job_id": jid, "status": "submitted", "endpoint": "Brain9", "new_api_run": True}

    def get_job(jid):
        if not re.fullmatch(r"[0-9a-f]{32}(?:_[0-9]{2})?", jid):
            raise HTTPException(404, "Unknown local job")
        job = job_store.get_job(manager.db, jid)
        if not job:
            raise HTTPException(404, "Unknown local job")
        return job

    def public_job(job):
        result = {k: job[k] for k in ("job_id", "status", "stage", "message", "progress_percent", "created_at")}
        from worker.brain9 import ENDPOINT, VERSION
        # Do not relabel pre-upgrade Brain6 jobs merely because the server upgraded.
        result["endpoint"] = (ENDPOINT if job["input"].get("classification_version") == VERSION
                              else "Legacy Brain6 / unversioned analysis (not Brain9)")
        from worker.rna_curve import SPEC_ID as CURVE_SPEC_ID
        result["rna_curve"] = ("Frontal cortex (GTEx Brain_Cortex, UBERON:0001870)"
                               if job["input"].get("curve_spec_id") == CURVE_SPEC_ID
                               else "Legacy curve: inspect the recorded track metadata; not relabeled")
        result["files"] = {key: f"/api/local/jobs/{job['job_id']}/files/{key}" for key, val in job["result"].items()
                           if key != "job_dir" and Path(val).is_file() and Path(val).suffix != ".html"}
        result["requested_variants"] = len(job["input"].get("rows", [job["input"]]))
        return result

    @app.get("/api/local/jobs")
    def jobs():
        return {"jobs": [public_job(j) for j in job_store.list_jobs(manager.db, limit=100)]}

    @app.get("/api/local/jobs/{jid}")
    def job_status(jid: str):
        return public_job(get_job(jid))

    @app.get("/api/local/jobs/{jid}/files/{name}")
    def job_file(jid: str, name: str):
        job = get_job(jid)
        raw = job["result"].get(name)
        if not raw or name == "job_dir":
            raise HTTPException(404, "Unknown job artifact")
        path = Path(raw).resolve()
        root = Path(job["job_dir"]).resolve()
        if not root.is_relative_to(manager.jobs.resolve()) or not path.is_relative_to(root) or not path.is_file() or path.suffix == ".html":
            raise HTTPException(404, "Invalid job artifact")
        return FileResponse(path, filename=path.name)

    return app
