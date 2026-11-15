"""Importer integrity and API boundaries, using an explicitly synthetic package."""
import csv
import json
from pathlib import Path

from astropy.time import Time
from fastapi.testclient import TestClient
import pytest

from whylab.app import create_app
from whylab.config import Settings
from whylab.dataset import import_dataset, sha256
from whylab.fits_preview.routes import ProductRegistry
from test_fits_preview import fixture, position


def write_table(package, name, rows):
    path = package / "metadata" / name
    path.parent.mkdir(exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def seal(package):
    lines = [f"{sha256(p)}  {p.relative_to(package).as_posix()}" for p in sorted(package.rglob("*"))
             if p.is_file() and p.name != "SHA256SUMS.txt"]
    (package / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def package(tmp_path):
    package = tmp_path / "source" / "final_dataset"
    (package / "fits").mkdir(parents=True)
    name = "Barnards_Star_synthetic.fits"
    wcs = fixture(package / "fits" / name)
    prediction = position(wcs)
    write_table(package, "clean_dataset_manifest_final.csv", [{
        "filename": name, "package_path": "fits/" + name, "target_key": "Barnards_Star",
        "sha256": sha256(package / "fits" / name), "coverage_status": "EDGE",
        "image_width": 11, "image_height": 11, "date_obs": "2025-01-01T00:00:00",
        "wavelength_min": .1, "wavelength_max": 1.2, "wavelength_unit": "",
        "flags": "TARGET_NEAR_IMAGE_EDGE", "pipeline_version": "synthetic"}])
    write_table(package, "target_astrometry_master.csv", [{
        "target_key": "Barnards_Star", "source_catalogue": "synthetic", "source_id": "4472832130942575872",
        "ref_epoch_jyear": 2016, "quality_flag": "PROVISIONAL", "notes": "Synthetic test only"}])
    write_table(package, "target_coordinates_per_observation.csv", [{
        "filename": name, "target_key": "Barnards_Star", "ra_at_obs_deg": prediction["ra_deg"],
        "dec_at_obs_deg": prediction["dec_deg"], "date_obs": "2025-01-01T00:00:00",
        "mjd_obs": Time("2025-01-01").mjd, "quality_flag": "PROVISIONAL",
        "method": "SYNTHETIC", "rv_status": "MISSING_ASSUMED_ZERO"}])
    write_table(package, "fits_coverage_validation.csv", [{"filename": name,
        "target_key": "Barnards_Star", "status": "EDGE", "pixel_x": 5, "pixel_y": 5}])
    write_table(package, "detection_check.csv", [{"filename": name,
        "target_key": "Barnards_Star", "verdict": "NOT_DETECTED", "note": "Synthetic screen",
        "snr_peak": 2.5, "control_n": 300, "control_p99_snr": 8.2}])
    seal(package)
    return package


def change_row(package, name, field, value):
    path = package / "metadata" / name
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    rows[0][field] = value
    write_table(package, name, rows)
    seal(package)


def test_import_preserves_existing_entries_source_bytes_and_reimport(package, tmp_path):
    root = tmp_path / "appdata"
    root.mkdir()
    original = {"unassociated": {"path": "raw/old.fits", "target_id": None}}
    (root / "fits_manifest.json").write_text(json.dumps(original))
    before = {p.relative_to(package): sha256(p) for p in package.rglob("*") if p.is_file()}
    result = import_dataset(package.parent, root)
    assert result["products"] == result["targets"] == 1
    registry = ProductRegistry.load(root)
    assert registry.entries["unassociated"] == original["unassociated"]
    item = next(v for k, v in registry.entries.items() if k != "unassociated")
    assert item["observation"]["file_wavelength_um"] is None
    assert item["observation"]["file_wavelength"]["unit"] is None
    assert item["dataset"]["adopted_astrometry"]["source_id"] == "4472832130942575872"
    assert item["dataset"]["detection_screen"]["verdict"] == "NOT_DETECTED"
    contents = (root / "fits_manifest.json").read_bytes()
    assert import_dataset(package, root) == result
    assert (root / "fits_manifest.json").read_bytes() == contents
    assert before == {p.relative_to(package): sha256(p) for p in package.rglob("*") if p.is_file()}


@pytest.mark.parametrize("table,field,value", [
    ("target_coordinates_per_observation.csv", "target_key", "WISE_0855"),
    ("target_coordinates_per_observation.csv", "ra_at_obs_deg", "nan"),
    ("target_coordinates_per_observation.csv", "ra_at_obs_deg", "180"),
    ("target_coordinates_per_observation.csv", "date_obs", "2026-01-01T00:00:00"),
    ("fits_coverage_validation.csv", "pixel_x", "8"),
    ("fits_coverage_validation.csv", "status", "OUTSIDE_IMAGE"),
    ("clean_dataset_manifest_final.csv", "image_width", "12"),
    ("clean_dataset_manifest_final.csv", "package_path", "../escape.fits"),
    ("detection_check.csv", "target_key", "WISE_0855"),
])
def test_inconsistent_package_cannot_publish_registry(package, tmp_path, table, field, value):
    change_row(package, table, field, value)
    root = tmp_path / "appdata"
    with pytest.raises(ValueError):
        import_dataset(package, root)
    assert not root.exists()


def test_checksum_tampering_and_path_escape_are_rejected(package, tmp_path):
    (package / "metadata/detection_check.csv").write_text("changed after packaging")
    with pytest.raises(ValueError, match="Checksum mismatch"):
        import_dataset(package, tmp_path / "appdata")
    (package / "SHA256SUMS.txt").write_text("0" * 64 + "  ../outside.txt\n")
    with pytest.raises(ValueError, match="unsafe path"):
        import_dataset(package, tmp_path / "appdata")


def test_imported_observation_preview_quality_and_download(package, tmp_path):
    root = tmp_path / "appdata"
    import_dataset(package, root)
    with TestClient(create_app(Settings(output_dir=root / "previews"))) as client:
        response = client.get("/api/targets/barnards-star/observations")
        assert response.status_code == 200
        assert "appdata" not in response.text
        item = response.json()["observations"][0]
        assert "path" not in item and item["provisional"]
        assert item["footprint_stcs"].startswith("POLYGON ICRS")
        assert client.get(item["preview_url"]).headers["content-type"] == "image/png"
        quality = client.get(item["quality_url"]).json()
        assert quality["geometry"]["inside_image"]
        assert quality["position"] == item["predicted_position"]
        download = client.get(item["fits_url"])
        assert download.headers["content-type"] == "application/fits"
        original = next((package / "fits").iterdir()).read_bytes()
        assert download.content == original
        assert client.get("/api/observations/unknown/fits").status_code == 404


def test_conflict_does_not_overwrite_registry(package, tmp_path):
    root = tmp_path / "appdata"
    import_dataset(package, root)
    path = root / "fits_manifest.json"
    entries = json.loads(path.read_text())
    next(iter(entries.values()))["provisional"] = False
    path.write_text(json.dumps(entries))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="conflicts"):
        import_dataset(package, root)
    assert path.read_bytes() == before
