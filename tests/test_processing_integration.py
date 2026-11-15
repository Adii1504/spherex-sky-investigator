"""Exercise the actual mounted API and the adapters used by WhyLab workers."""
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from whylab.app import create_app
from whylab.config import Settings
from whylab.models import Observation, Provenance, Cutout, Sky
from teammate_integration import SPHERExSequenceAdapter, SPHERExMotionAdapter


@pytest.mark.parametrize("preset,count", [
    ("Barnards_Star", 5), ("WISE_0855", 5), ("Epsilon_Indi_B", 3),
    ("RW_Aurigae", 4), ("R_Draconis", 4),
    ("synthetic_asteroid_sequence", 4), ("nasa_real_6bands", 6),
])
def test_real_http_pipeline_and_generated_assets(tmp_path, preset, count):
    with TestClient(create_app(Settings(output_dir=tmp_path / "previews"))) as client:
        response = client.post("/processing/api/investigate", data={"preset_id": preset})
        assert response.status_code == 200, response.text
        result = response.json()
        assert len(result["frames"]) == count
        assert result["outcome"] in ("motion_supported", "stationary_plausible", "insufficient_evidence")
        assert len(result["differences"]) == count - 1
        assert result["shared_display_settings"]["stretch"] == "shared-percentile-linear"
        urls = [frame["image_url"] for frame in result["frames"]]
        urls.extend(d["image_url"] for d in result["differences"])
        urls.append(result["blink_animation_url"])
        if result.get("diagnostic_trajectory_url"):
            urls.append(result["diagnostic_trajectory_url"])
        for url in urls:
            assert url.startswith("/processing/previews/"), url
            image = client.get(url)
            assert image.status_code == 200
            assert image.headers["content-type"].startswith("image/")
        if result["comparison"]["status"] != "compatible":
            assert result["outcome"] == "insufficient_evidence"
        assert "Desktop" not in response.text


def test_mounted_ui_sed_composite_validation_and_existing_app(tmp_path):
    with TestClient(create_app(Settings(output_dir=tmp_path / "previews"))) as client:
        assert client.get("/api/targets").status_code == 200
        assert client.get("/processing/").status_code == 200
        assert client.get("/processing/viewer/").status_code == 200
        assert client.get("/processing/app.js").status_code == 200
        assert client.get("/processing/styles.css").status_code == 200
        for data in [{"investigation_id":"../../escape"}, {"grid_size_px":100000},
                     {"target_ra":1}, {"fov_arcmin":0}, {"target_ra":"nan", "target_dec":0}]:
            assert client.post("/processing/api/investigate",data=data).status_code == 422
        assert client.post("/processing/api/investigate",files={"files":("image.png",b"invalid raster")}).status_code == 422
        assert client.post("/processing/api/composite",data={"red_band":99}).status_code == 422
        response = client.post("/processing/api/composite")
        assert response.status_code == 200, response.text
        assert client.get(response.json()["composite_url"]).status_code == 200
        response = client.get("/processing/api/sed?ra_deg=133.76&dec_deg=-7.24&preset_id=WISE_0855")
        assert response.status_code == 200, response.text
        assert len(response.json()["sed_points"]) == 5
        assert client.get(response.json()["sed_plot_url"]).status_code == 200


def sample_pairs():
    pairs = []
    files = sorted(Path("backend/processing/sample_data/sequence").glob("*.fits"))
    for i,path in enumerate(files):
        observation = Observation(id=f"sample-{i}", exposure_id=f"exp-{i}",
            observed_at=datetime(2025,1,1,i,tzinfo=timezone.utc), release="synthetic",
            product_id=f"product-{i}", provenance=Provenance(archive="synthetic",source_url="https://example.org/test"))
        pairs.append((observation,Cutout(observation_id=observation.id,data=path.read_bytes(),media_type="application/fits")))
    return pairs


def test_worker_sequence_returns_nonempty_previews_with_matching_ids(tmp_path):
    pairs = list(reversed(sample_pairs()))
    adapter = SPHERExSequenceAdapter(Settings(output_dir=tmp_path / "previews",preview_pixels=64))
    result = adapter.process([p[0] for p in pairs],[p[1] for p in pairs],Sky(ra_deg=149.992,dec_deg=1.992,fov_arcmin=2.5))
    assert [p.observation_id for p in result.previews] == [f"sample-{i}" for i in range(4)]
    assert all(p.png.startswith(b"\x89PNG") for p in result.previews)
    assert "whylab-science-" not in str(result.model_dump(exclude={"previews"}))


def test_worker_evaluates_every_reserved_epoch_without_fitting_it(monkeypatch):
    import teammate_integration as module
    pairs = sample_pairs()
    observations = [p[0] for p in pairs]
    cutouts = {p[0].id:p[1] for p in pairs}
    class Archive:
        def cutout(self, observation, sky):
            return cutouts[observation.id]
    calls = []
    def compare(training, reserved):
        calls.append(([row["epoch_id"] for row in training],reserved["epoch_id"]))
        return {"outcome":"motion_supported" if len(calls)==1 else "insufficient_evidence", "warnings":[]}
    monkeypatch.setattr(module,"test_motion",compare)
    result = SPHERExMotionAdapter().verify(observations[:2],observations[2:],Sky(ra_deg=149.992,dec_deg=1.992,fov_arcmin=2.5),Archive())
    assert calls == [(["sample-0","sample-1"],"sample-2"),(["sample-0","sample-1"],"sample-3")]
    assert result.outcome == "insufficient_evidence"
    assert len(result.measurements["reserved"]) == 2


def test_upload_validation_reuses_the_parsed_fits_instead_of_reading_it_twice(tmp_path,monkeypatch):
    import backend.main as main
    import backend.processing.pipeline as pipeline
    original=main.load_observation; calls=[]
    def load(source):
        calls.append(1);return original(source)
    monkeypatch.setattr(main,'load_observation',load)
    monkeypatch.setattr(pipeline,'load_observation',load)
    path=next(Path('backend/processing/sample_data/sequence').glob('*.fits'))
    with TestClient(create_app(Settings(output_dir=tmp_path/'previews'))) as client:
        response=client.post('/processing/api/investigate',files={'files':('observation.fits',path.read_bytes(),'application/fits')})
        assert response.status_code==200,response.text
        assert len(response.json()['frames'])==1
    assert len(calls)==1
