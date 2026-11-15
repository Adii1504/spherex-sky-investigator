"""Synthetic integration fixtures ONLY. These are never registered by the application."""
import base64
import time
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from whylab.app import create_app
from whylab.config import Settings
from whylab.models import Observation, Provenance, SearchResult, Cutout, Preview, ProcessedSequence, VerificationResult
from whylab.security import TrustedRetriever

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")
SKY = {"ra_deg": 12, "dec_deg": -5, "fov_arcmin": 2}

def obs(i, exposure=None):
    return Observation(id=str(i), exposure_id=exposure or f"exp-{i}", observed_at=datetime(2025, 1, i, tzinfo=timezone.utc), release="TEST-ONLY", product_id=f"test-{i}", provenance=Provenance(archive="TEST ONLY", source_url="https://irsa.ipac.caltech.edu/test"))

class Archive:
    available = True
    def __init__(self): self.observations = [obs(2), obs(1), obs(3)]
    def search(self, query): return SearchResult(observations=self.observations, coverage_summary={"count": len(self.observations)}, warnings=["Synthetic test fixture"])
    def cutout(self, observation, sky): return Cutout(observation_id=observation.id, data=b"test-only", media_type="application/fits")

class Sequence:
    available = True
    def process(self, observations, cutouts, sky):
        return ProcessedSequence(previews=[Preview(observation_id=o.id, png=PNG) for o in observations], processing_version="test-only-1", processing_settings={"mask": "TEST ONLY"}, shared_display_settings={"stretch": "test-only"}, measurements={"test": 1})

class Motion:
    available = True
    def verify(self, training, reserved, sky, archive):
        self.received = (training, reserved)
        return VerificationResult(outcome="insufficient_evidence", measurements={"test-only": 3}, assumptions=["test assumption"], limitations=["synthetic fixture"], processing_version="test-only-1")

@pytest.fixture
def context(tmp_path):
    archive, sequence, motion = Archive(), Sequence(), Motion()
    settings = Settings(output_dir=tmp_path, timeout_seconds=1)
    with TestClient(create_app(settings, archive, sequence, motion)) as client:
        yield client, archive, sequence, motion

def search(client):
    response = client.post("/api/v1/observations/search", json=SKY)
    assert response.status_code == 200, response.text
    return response.json()["search_id"]

def selection(client): return {**SKY, "search_id": search(client), "observation_ids": ["2", "1", "3"]}

def wait(client, key):
    for _ in range(200):
        result = client.get("/api/v1/jobs/" + key).json()
        if result["status"] in ("succeeded", "failed"): return result
        time.sleep(.01)
    pytest.fail("Job did not finish")

def test_unavailable(tmp_path):
    with TestClient(create_app(Settings(output_dir=tmp_path))) as client:
        health = client.get("/api/v1/health").json()
        assert set(health["capabilities"].values()) == {"unavailable"}
        response = client.post("/api/v1/observations/search", json=SKY)
        assert response.status_code == 503
        assert response.json()["details"]["capability"] == "archive_access"

@pytest.mark.parametrize("extra", [{"ra_deg": 360}, {"ra_deg": -1}, {"dec_deg": -91}, {"fov_arcmin": 31}, {"start_utc": "2025-01-01T00:00:00"}, {"start_utc": "2025-02-01T00:00:00Z", "end_utc": "2025-01-01T00:00:00Z"}, {"ra_deg": "NaN"}, {"dec_deg": "Infinity"}])
def test_validation(context, extra):
    response = context[0].post("/api/v1/observations/search", json={**SKY, **extra})
    assert response.status_code == 422
    assert "code" in response.json()

def test_pipeline_and_evidence(context):
    client, archive, sequence, motion = context
    chosen = selection(client)
    job = client.post("/api/v1/sequences", json=chosen)
    assert job.status_code == 202
    done = wait(client, job.json()["job_id"])
    assert done["status"] == "succeeded", done
    previews = done["result"]["previews"]
    assert [p["observation"]["id"] for p in previews] == ["1", "2", "3"]
    assert client.get(previews[0]["preview_url"]).content == PNG
    inv = client.post("/api/v1/investigations", json={**chosen, "sequence_job_id": job.json()["job_id"]}).json()["investigation_id"]
    response = client.post(f"/api/v1/investigations/{inv}/verify", json={"training_observation_ids": ["1", "2"], "reserved_observation_ids": ["3"]})
    assert response.status_code == 202
    assert wait(client, response.json()["job_id"])["result"]["outcome"] == "insufficient_evidence"
    evidence = client.get(f"/api/v1/investigations/{inv}/evidence").json()
    assert evidence["schema_version"] == "1.0"
    assert evidence["observations"][0]["provenance"]["archive"] == "TEST ONLY"
    assert evidence["observations"][0]["provenance"]["source_url"] == "https://irsa.ipac.caltech.edu/test"
    assert evidence["processing"]["processing_version"] == "test-only-1"
    assert evidence["verification"][0]["result"]["limitations"] == ["synthetic fixture"]
    assert "file_wavelength_um" in evidence["observations"][0]
    assert evidence["observations"][0]["position_wavelength_um"] is None

@pytest.mark.parametrize("training,reserved", [(["1"], ["1"]), (["1", "1"], ["3"]), (["1"], ["3", "3"]), (["missing"], ["3"])])
def test_separation(context, training, reserved):
    client = context[0]
    inv = client.post("/api/v1/investigations", json=selection(client)).json()["investigation_id"]
    response = client.post(f"/api/v1/investigations/{inv}/verify", json={"training_observation_ids": training, "reserved_observation_ids": reserved})
    assert response.status_code == 422

def test_duplicate_exposure(context):
    client, archive, _, _ = context
    archive.observations[0].exposure_id = archive.observations[1].exposure_id
    inv = client.post("/api/v1/investigations", json=selection(client)).json()["investigation_id"]
    response = client.post(f"/api/v1/investigations/{inv}/verify", json={"training_observation_ids": ["1"], "reserved_observation_ids": ["2"]})
    assert response.status_code == 422
    assert response.json()["code"] == "exposure_overlap"

def test_partial_and_failure(context):
    client, archive, sequence, _ = context
    chosen = selection(client)
    original = archive.cutout
    def partial(o, sky):
        if o.id == "2": raise TimeoutError("private path C:/secret")
        return original(o, sky)
    archive.cutout = partial
    result = wait(client, client.post("/api/v1/sequences", json=chosen).json()["job_id"])
    assert result["status"] == "succeeded"
    assert len(result["result"]["previews"]) == 2
    assert result['progress']['completed']==2 and result['progress']['total']==3
    assert result["result"]["warnings"]
    def broken(*args): raise RuntimeError("C:/secret token=password")
    sequence.process = broken
    failed = wait(client, client.post("/api/v1/sequences", json=chosen).json()["job_id"])
    assert failed["error"]["code"] == "processing_failed"
    assert "password" not in str(failed)

def test_empty_coverage(context):
    client, archive, _, _ = context
    archive.observations = []
    response = client.post("/api/v1/observations/search", json=SKY)
    assert response.json()["observations"] == []

def test_trusted_urls():
    retriever = TrustedRetriever(["irsa.ipac.caltech.edu"])
    for url in ["http://irsa.ipac.caltech.edu/a", "https://evil.test/a", "https://irsa.ipac.caltech.edu.evil.test/a", "https://user:pass@irsa.ipac.caltech.edu/a", "file:///etc/passwd", "https://127.0.0.1/a"]:
        with pytest.raises(ValueError): retriever.validate(url)

def test_timeout_and_backpressure(tmp_path):
    archive = Archive()
    def slow(query):
        time.sleep(.2)
        return SearchResult(observations=[], coverage_summary={})
    archive.search = slow
    with TestClient(create_app(Settings(output_dir=tmp_path, workers=1, max_pending=1, timeout_seconds=.03), archive)) as client:
        assert client.post("/api/v1/observations/search", json=SKY).status_code == 504
        jobs = client.app.state.jobs
        jobs.submit(lambda: time.sleep(.2))
        from whylab.jobs import Busy
        with pytest.raises(Busy): jobs.submit(lambda: None)

def test_unknown_and_mismatch(context):
    client = context[0]
    assert client.get("/api/v1/jobs/unknown").status_code == 404
    assert client.get("/api/v1/previews/unknown").status_code == 404
    chosen = selection(client)
    assert client.post("/api/v1/sequences", json={**chosen, "ra_deg": 13}).status_code == 422
    assert client.post("/api/v1/sequences", json={**chosen, "observation_ids": ["1", "1"]}).status_code == 422

def test_export_redaction(context):
    client, _, sequence, _ = context
    original = sequence.process
    def process(*args):
        result = original(*args)
        result.processing_settings = {"api_token": "sensitive", "scratch_path": "C:/secret", "source": "https://user:password@irsa.ipac.caltech.edu/test?token=hidden"}
        return result
    sequence.process = process
    chosen = selection(client)
    key = client.post("/api/v1/sequences", json=chosen).json()["job_id"]
    assert wait(client, key)["status"] == "succeeded"
    inv = client.post("/api/v1/investigations", json={**chosen, "sequence_job_id": key}).json()["investigation_id"]
    text = client.get(f"/api/v1/investigations/{inv}/evidence").text
    assert all(s not in text for s in ["sensitive", "password", "hidden", "C:/secret"])


def test_dynamic_upstream_errors(context):
    from whylab.adapters import CapabilityUnavailable
    client, archive, _, _ = context
    def unavailable(query): raise CapabilityUnavailable("archive_access")
    archive.search = unavailable
    response = client.post("/api/v1/observations/search", json=SKY)
    assert response.status_code == 503
    assert response.json()["details"]["capability"] == "archive_access"
    def timeout(query): raise TimeoutError("sensitive upstream address")
    archive.search = timeout
    response = client.post("/api/v1/observations/search", json=SKY)
    assert response.status_code == 504
    assert response.json()["code"] == "upstream_timeout"


def test_network_failure_explains_server_access_without_exposing_exception(context):
    import httpx
    client, archive, _, _ = context
    def disconnected(query):
        raise httpx.ConnectError("private upstream diagnostics and filesystem path")
    archive.search = disconnected
    response = client.post("/api/v1/observations/search", json=SKY)
    assert response.status_code == 502
    assert response.json()["code"] == "upstream_unreachable"
    assert "server's network access" in response.json()["message"]
    assert "private upstream" not in response.text


def test_failed_observation_downloads_recover_on_retry_without_restart(context):
    import httpx
    client,archive,_,_=context
    chosen=selection(client)
    original=archive.cutout
    def unavailable(*args):raise httpx.ConnectError('private connection diagnostic')
    archive.cutout=unavailable
    first=client.post('/api/v1/sequences',json=chosen).json()['job_id']
    failed=wait(client,first)
    assert failed['error']['code']=='upstream_unreachable'
    assert 'private connection' not in str(failed)
    archive.cutout=original
    second=client.post('/api/v1/sequences',json=chosen).json()['job_id']
    assert second!=first
    assert wait(client,second)['status']=='succeeded'


def test_upstream_http_status_is_reported_without_private_url(context):
    import httpx
    client, archive, _, _ = context
    def rejected(query):
        request = httpx.Request("GET", "https://irsa.ipac.caltech.edu/private?token=hidden")
        response = httpx.Response(503, request=request)
        raise httpx.HTTPStatusError("private upstream response",request=request,response=response)
    archive.search = rejected
    response = client.post("/api/v1/observations/search", json=SKY)
    assert response.status_code == 502
    assert response.json()["code"] == "upstream_http_error"
    assert response.json()["details"]["upstream_status"] == 503
    assert "hidden" not in response.text
    assert 'NASA/IPAC IRSA' in response.json()['message']
    assert 'restarting' in response.json()['message']


def test_partial_search_sessions_do_not_hide_service_recovery(context):
    client,archive,_,_=context
    original=archive.search;calls=[]
    def partial(query):
        calls.append(1)
        value=original(query)
        value.coverage_summary.update(complete=False,collections_failed=[{'collection':'spherex_qr3','upstream_status':502}])
        return value
    archive.search=partial
    first=client.post('/api/v1/observations/search',json=SKY).json()
    second=client.post('/api/v1/observations/search',json=SKY).json()
    assert len(calls)==2 and first['search_id']!=second['search_id']


def test_missing_processing_capabilities(tmp_path):
    with TestClient(create_app(Settings(output_dir=tmp_path), archive=Archive())) as client:
        chosen = selection(client)
        response = client.post("/api/v1/sequences", json=chosen)
        assert response.status_code == 503
        assert response.json()["details"]["capability"] == "image_processing"
        inv = client.post("/api/v1/investigations", json=chosen).json()["investigation_id"]
        response = client.post(f"/api/v1/investigations/{inv}/verify", json={"training_observation_ids": ["1"], "reserved_observation_ids": ["3"]})
        assert response.status_code == 503
        assert response.json()["details"]["capability"] == "motion_verification"


def test_preview_traversal_and_cors(tmp_path):
    settings = Settings(output_dir=tmp_path, cors_origins=["http://localhost:5173"])
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/previews/%2e%2e%2fsecret")
        assert response.status_code == 404
        response = client.options("/api/v1/observations/search", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
        denied = client.options("/api/v1/observations/search", headers={"Origin": "https://evil.test", "Access-Control-Request-Method": "POST"})
        assert "access-control-allow-origin" not in denied.headers


def test_verification_evidence_survives_job_eviction(tmp_path):
    with TestClient(create_app(Settings(output_dir=tmp_path, cache_size=2), Archive(), Sequence(), Motion())) as client:
        chosen = selection(client)
        inv = client.post("/api/v1/investigations", json=chosen).json()["investigation_id"]
        key = client.post(f"/api/v1/investigations/{inv}/verify", json={"training_observation_ids": ["1"], "reserved_observation_ids": ["3"]}).json()["job_id"]
        wait(client, key)
        for _ in range(3):
            job = client.app.state.jobs.submit(lambda: {})
            wait(client, job)
        assert client.get("/api/v1/jobs/" + key).status_code == 404
        evidence = client.get(f"/api/v1/investigations/{inv}/evidence").json()
        assert evidence["verification"][0]["result"]["outcome"] == "insufficient_evidence"
