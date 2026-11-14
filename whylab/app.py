import asyncio
import importlib
import threading
import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .models import Search, Selection, Investigation, Verify, Sky, SearchResult, ProcessedSequence, VerificationResult
from .adapters import Unavailable
from .config import Settings
from .jobs import Jobs, Busy
from .security import TrustedRetriever

class APIError(Exception):
    def __init__(self, status, code, message, details=None):
        self.status, self.code, self.message, self.details = status, code, message, details

def create_app(settings=None, archive=None, sequence=None, motion=None):
    settings = settings or Settings.from_env()
    # Deployment-local factory; no client can select or import a module.
    import os
    factory_path = os.getenv("WHYLAB_ADAPTER_FACTORY")
    if factory_path and archive is None and sequence is None and motion is None:
        module, name = factory_path.split(":", 1)
        archive, sequence, motion = getattr(importlib.import_module(module), name)(settings, TrustedRetriever(settings.trusted_hosts, settings.timeout_seconds))
    archive = archive or Unavailable("archive_access")
    sequence = sequence or Unavailable("image_processing")
    motion = motion or Unavailable("motion_verification")
    jobs = Jobs(settings)
    searches, investigations, previews = {}, {}, {}
    lock = threading.RLock()
    output = settings.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    @asynccontextmanager
    async def lifespan(app):
        yield
        jobs.close()
    app = FastAPI(title="SPHEREx WhyLab", version="0.1.0", lifespan=lifespan)
    app.state.jobs = jobs
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
    @app.exception_handler(APIError)
    async def api_error(request, exc):
        body = {"code": exc.code, "message": exc.message}
        if exc.details is not None: body["details"] = exc.details
        return JSONResponse(body, status_code=exc.status)
    @app.exception_handler(RequestValidationError)
    async def validation(request, exc):
        return JSONResponse({"code": "invalid_request", "message": "Request validation failed", "details": [{"field": list(e["loc"]), "message": e["msg"]} for e in exc.errors()]}, status_code=422)
    from starlette.exceptions import HTTPException
    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return JSONResponse({"code": "http_error", "message": str(exc.detail)}, status_code=exc.status_code)
    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        return JSONResponse({"code": "internal_error", "message": "Internal operation failed"}, status_code=500)

    def require(adapter, capability):
        if not adapter.available: raise APIError(503, "capability_unavailable", "Required teammate adapter is unavailable", {"capability": capability})
    def capacity(store):
        if len(store) >= settings.cache_size: raise APIError(503, "cache_full", "Session capacity reached; restart or increase cache limit")
    def sky_check(value):
        if value.fov_arcmin > settings.max_fov_arcmin: raise APIError(422, "limit_exceeded", "Field of view exceeds configured limit")
    def selected(value):
        sky_check(value)
        with lock: found = searches.get(value.search_id)
        if not found: raise APIError(404, "search_not_found", "Search not found")
        if value.ra_deg != found[0].ra_deg or value.dec_deg != found[0].dec_deg or value.fov_arcmin != found[0].fov_arcmin:
            raise APIError(422, "search_mismatch", "Selection must use the searched sky field")
        ids = value.observation_ids
        if len(ids) > settings.max_observations or len(set(ids)) != len(ids): raise APIError(422, "invalid_selection", "Observation IDs must be unique and within limits")
        indexed = {o.id: o for o in found[1].observations}
        if any(i not in indexed for i in ids): raise APIError(422, "invalid_selection", "Observation does not belong to search")
        return sorted([indexed[i] for i in ids], key=lambda o: o.observed_at)
    def submit(fn, retain=False):
        try: return jobs.submit(fn, retain=retain)
        except Busy: raise APIError(503, "queue_full", "Worker capacity reached; retry later")
    def public(value):
        # Defense in depth: adapters must supply export-safe values, never opaque secret blobs.
        if isinstance(value, dict):
            return {k: public(v) for k, v in value.items() if not any(s in k.lower() for s in ("secret", "token", "password", "authorization", "path"))}
        if isinstance(value, list): return [public(v) for v in value]
        if isinstance(value, str):
            import re
            if value.startswith(("https://", "http://")):
                from urllib.parse import urlsplit, urlunsplit
                p = urlsplit(value)
                return urlunsplit((p.scheme, p.hostname or "", p.path, "", ""))
            if re.search(r"(?i)([a-z]:[\\/]|file:|/(?:home|tmp|var|users)/)", value): return "[redacted local reference]"
        return value

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "capabilities": {k: "available" if a.available else "unavailable" for k, a in [("archive_access", archive), ("image_processing", sequence), ("motion_verification", motion)]}}

    @app.post("/api/v1/observations/search")
    async def search(query: Search):
        sky_check(query)
        require(archive, "archive_access")
        def operation():
            result = SearchResult.model_validate(archive.search(query))
            if len(result.observations) > settings.max_observations: raise ValueError("Archive must honor observation limit")
            if len({o.id for o in result.observations}) != len(result.observations): raise ValueError("Duplicate archive IDs")
            for o in result.observations: TrustedRetriever(settings.trusted_hosts).validate(o.provenance.source_url)
            return result.model_dump(mode="json")
        search_record = submit(operation, retain=True)
        while True:
            with jobs.lock: record = dict(search_record)
            if record["status"] in ("succeeded", "failed"): break
            await asyncio.sleep(0.02)
        if record["status"] == "failed":
            error = record["error"]
            status = 503 if error["code"] == "capability_unavailable" else 504 if error["code"] in ("job_timeout", "upstream_timeout") else 502
            raise APIError(status, error["code"], "Archive search failed", error.get("details"))
        result = SearchResult.model_validate(record["result"])
        with lock:
            capacity(searches)
            search_id = uuid.uuid4().hex
            searches[search_id] = (query, result)
        return public({"search_id": search_id, **result.model_dump(mode="json")})

    @app.post("/api/v1/sequences", status_code=202)
    def make_sequence(value: Selection):
        observations = selected(value)
        require(archive, "archive_access")
        require(sequence, "image_processing")
        def operation():
            deadline = time.monotonic() + settings.timeout_seconds
            sky = Sky(**value.model_dump(include={"ra_deg", "dec_deg", "fov_arcmin"}))
            cutouts, warnings = [], []
            cutout_bytes = 0
            for observation in observations:
                if time.monotonic() >= deadline: raise TimeoutError("Sequence retrieval deadline exceeded")
                try:
                    cutout = archive.cutout(observation, sky)
                    if cutout.observation_id != observation.id: raise ValueError("Cutout identity mismatch")
                    if cutout_bytes + len(cutout.data) > settings.max_sequence_bytes:
                        warnings.append("Sequence cutout byte budget reached; remaining observations omitted")
                        break
                    cutout_bytes += len(cutout.data)
                    cutouts.append(cutout)
                except Exception: warnings.append("Cutout unavailable for observation " + observation.id)
            if not cutouts: raise ValueError("No usable cutouts")
            usable = [o for o in observations if o.id in {c.observation_id for c in cutouts}]
            result = ProcessedSequence.model_validate(sequence.process(usable, cutouts, sky))
            by_id = {p.observation_id: p for p in result.previews}
            if len(by_id) != len(result.previews) or not set(by_id).issubset({o.id for o in usable}) or not by_id: raise ValueError("Invalid preview identities")
            rendered = []
            with lock:
                if time.monotonic() >= deadline: raise TimeoutError("Sequence deadline exceeded")
                total = sum(p.stat().st_size for p in output.glob("*.png"))
                required = sum(len(p.png) for p in result.previews)
                if total + required > settings.max_output_bytes or len(previews) + len(by_id) > settings.cache_size: raise ValueError("Preview cache full")
                for observation in observations:
                    preview = by_id.get(observation.id)
                    if preview is None:
                        warnings.append("No processed preview for observation " + observation.id)
                        continue
                    if len(preview.png) > settings.max_preview_bytes or not preview.png.startswith(b"\x89PNG\r\n\x1a\n"): raise ValueError("Invalid PNG preview")
                for observation in observations:
                    preview = by_id.get(observation.id)
                    if preview is None: continue
                    identifier = uuid.uuid4().hex
                    path = output / (identifier + ".png")
                    path.write_bytes(preview.png)
                    previews[identifier] = path
                    rendered.append({"observation": observation.model_dump(mode="json"), "preview_url": "/api/v1/previews/" + identifier, "metadata": preview.metadata})
            return public({"search_id": value.search_id, "observation_ids": value.observation_ids, "previews": rendered, **result.model_dump(exclude={"previews"}), "warnings": result.warnings + warnings})
        return {"job_id": submit(operation)}

    @app.get("/api/v1/previews/{identifier}")
    def preview(identifier: str):
        with lock: path = previews.get(identifier)
        if path is None: raise APIError(404, "preview_not_found", "Preview not found")
        return FileResponse(path, media_type="image/png")

    @app.get("/api/v1/jobs/{job_id}")
    def get_job(job_id: str):
        record = jobs.get(job_id)
        if record is None: raise APIError(404, "job_not_found", "Job not found")
        return record

    @app.post("/api/v1/investigations", status_code=201)
    def investigate(value: Investigation):
        observations = selected(value)
        sequence_result = None
        if value.sequence_job_id:
            record = jobs.get(value.sequence_job_id)
            if not record or record["status"] != "succeeded" or record["result"].get("search_id") != value.search_id or set(record["result"].get("observation_ids", [])) != set(value.observation_ids):
                raise APIError(422, "invalid_sequence", "Sequence must be a successful job for this selection")
            sequence_result = record["result"]
        with lock:
            capacity(investigations)
            key = uuid.uuid4().hex
            investigations[key] = {"selection": value, "observations": observations, "sequence": sequence_result, "verification_jobs": []}
        return {"investigation_id": key}

    def investigation(key):
        with lock: found = investigations.get(key)
        if found is None: raise APIError(404, "investigation_not_found", "Investigation not found")
        return found

    @app.post("/api/v1/investigations/{key}/verify", status_code=202)
    def verify(key: str, value: Verify):
        found = investigation(key)
        indexed = {o.id: o for o in found["observations"]}
        ids = value.training_observation_ids + value.reserved_observation_ids
        if any(i not in indexed for i in ids): raise APIError(422, "invalid_selection", "Verification IDs must belong to investigation")
        exposures = [indexed[i].exposure_id for i in ids]
        if len(set(ids)) != len(ids) or len(set(exposures)) != len(exposures): raise APIError(422, "exposure_overlap", "Training and reserved observations must have unique, disjoint exposure identities")
        require(motion, "motion_verification")
        require(archive, "archive_access")
        sky = Sky(**found["selection"].model_dump(include={"ra_deg", "dec_deg", "fov_arcmin"}))
        def operation():
            result = VerificationResult.model_validate(motion.verify([indexed[i] for i in value.training_observation_ids], [indexed[i] for i in value.reserved_observation_ids], sky, archive))
            return public({**result.model_dump(mode="json"), **value.model_dump()})
        with lock:
            if len(found["verification_jobs"]) >= settings.cache_size: raise APIError(503, "cache_full", "Verification history full")
            job_id = submit(operation)
            with jobs.lock: found["verification_jobs"].append(jobs.records[job_id])
        return {"job_id": job_id}

    @app.get("/api/v1/investigations/{key}/evidence")
    def evidence(key: str):
        found = investigation(key)
        return public({"schema_version": "1.0", "investigation_id": key, "selection": found["selection"].model_dump(mode="json"), "observations": [o.model_dump(mode="json") for o in found["observations"]], "processing": found["sequence"], "warnings": [] if found["sequence"] else ["No processed sequence attached"], "verification": [dict(j) for j in found["verification_jobs"]]})
    if (settings.frontend_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
    return app

app = create_app()
