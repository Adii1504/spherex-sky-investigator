"""Tests for backend/processing/pipeline.py and diagnostic.py.

Verifies end-to-end pipeline execution (ingestion, alignment, stretch, differencing,
blinking animation, source discovery, and hypothesis testing) and diagnostic plotting.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.processing.diagnostic import plot_sed_spectrum, plot_trajectory_fit
from backend.processing.pipeline import run_investigation_pipeline

SAMPLE_DATA_DIR = Path(__file__).resolve().parent.parent / "sample_data"
SEQUENCE_DIR = SAMPLE_DATA_DIR / "sequence"


def test_run_investigation_pipeline_synthetic_sequence(tmp_path: Path):
    """Verify run_investigation_pipeline runs end-to-end on synthetic sequence."""
    epoch_paths = sorted(SEQUENCE_DIR.glob("spherex_synth_epoch_*.fits"))
    assert len(epoch_paths) == 4, f"Expected 4 synthetic epochs, found {len(epoch_paths)}"

    target_ra = 150.0 - 0.008
    target_dec = 2.0 - 0.008

    result = run_investigation_pipeline(
        fits_inputs=epoch_paths,
        target_coord=(target_ra, target_dec),
        investigation_id="TEST_ASTEROID_001",
        fov_arcmin=2.5,
        grid_size_px=64,
        output_dir=tmp_path,
        base_url_prefix="/api/assets",
    )

    # 1. Structure verification
    assert result["investigation_id"] == "TEST_ASTEROID_001"
    assert result["outcome"] == "motion_supported"

    # 2. Frames verification
    assert len(result["frames"]) == 4
    for idx, frame in enumerate(result["frames"]):
        assert frame["epoch_index"] == idx
        assert frame["image_url"].startswith("api/assets") or frame["image_url"].startswith("/api/assets")
        assert (tmp_path / f"TEST_ASTEROID_001_frame_{idx + 1:02d}.png").exists()

    # 3. Differences verification (4 frames -> 3 successive differences)
    assert len(result["differences"]) == 3
    for idx, diff in enumerate(result["differences"]):
        assert (tmp_path / f"TEST_ASTEROID_001_diff_{idx + 1}_to_{idx + 2}.png").exists()

    # 4. Blink animation verification
    assert result["blink_animation_url"] is not None
    assert (tmp_path / "TEST_ASTEROID_001_blink.gif").exists()

    # 5. Measurements & Motion verification
    meas = result["measurements"]
    assert len(meas) == 4
    for m in meas:
        assert m["status"] == "ok"
        assert m["snr"] > 5.0
        assert m["uncertainty_arcsec"] is not None

    comp = result["model_comparison"]
    assert comp is not None
    assert comp["motion_residual_arcsec"] < comp["stationary_residual_arcsec"]
    assert comp["fitted_speed_arcsec_per_hour"] > 0.0

    # 6. Hotspots automated discovery verification
    hotspots = result["hotspots"]
    assert len(hotspots) >= 1
    # Moving asteroid candidate should be identified
    classifications = [h["classification"] for h in hotspots]
    assert "moving_candidate" in classifications


def test_run_investigation_pipeline_empty():
    """Verify run_investigation_pipeline handles empty input cleanly."""
    result = run_investigation_pipeline([], investigation_id="EMPTY_001")
    assert result["outcome"] == "insufficient_evidence"
    assert len(result["frames"]) == 0
    assert len(result["differences"]) == 0
    assert result["blink_animation_url"] is None
    assert any("Pipeline aborted: zero valid observations." in w for w in result["warnings"])


def test_run_investigation_pipeline_single_epoch(tmp_path: Path):
    """Verify run_investigation_pipeline handles single epoch without crashing."""
    single_fits = SAMPLE_DATA_DIR / "nasa_spherex_l2_cutout.fits"
    assert single_fits.exists()

    result = run_investigation_pipeline(
        fits_inputs=[single_fits],
        investigation_id="SINGLE_001",
        output_dir=tmp_path,
    )

    assert result["outcome"] == "insufficient_evidence"
    assert len(result["frames"]) == 1
    assert len(result["differences"]) == 0
    assert result["blink_animation_url"] is None


def test_plot_trajectory_fit_valid(tmp_path: Path):
    """Verify plot_trajectory_fit generates a 2-panel diagnostic figure."""
    epoch_paths = sorted(SEQUENCE_DIR.glob("spherex_synth_epoch_*.fits"))
    pipeline_res = run_investigation_pipeline(
        fits_inputs=epoch_paths,
        target_coord=(150.0 - 0.008, 2.0 - 0.008),
        investigation_id="DIAG_TEST",
        output_dir=tmp_path,
    )

    out_png = tmp_path / "trajectory_diagnostic.png"
    diag_path = plot_trajectory_fit(pipeline_res, out_png_path=out_png)

    assert diag_path.exists()
    assert diag_path.stat().st_size > 0


def test_plot_sed_spectrum_valid(tmp_path: Path):
    """Verify plot_sed_spectrum generates a valid SED plot with power-law fit."""
    sed_dict = {
        "ra_deg": 150.0,
        "dec_deg": 2.0,
        "spectral_index": -1.25,
        "sed_points": [
            {"detector": "D1", "wavelength_um": 0.95, "flux": 15.2, "snr": 20.0, "status": "ok"},
            {"detector": "D2", "wavelength_um": 1.45, "flux": 9.1, "snr": 15.0, "status": "ok"},
            {"detector": "D3", "wavelength_um": 2.10, "flux": 5.8, "snr": 12.0, "status": "ok"},
            {"detector": "D4", "wavelength_um": 3.00, "flux": 3.9, "snr": 9.0, "status": "ok"},
            {"detector": "D5", "wavelength_um": 4.10, "flux": 2.7, "snr": 7.0, "status": "ok"},
            {"detector": "D6", "wavelength_um": 4.80, "flux": 2.1, "snr": 5.0, "status": "ok"},
        ],
    }
    out_png = tmp_path / "test_sed.png"
    p = plot_sed_spectrum(sed_dict, out_png_path=out_png)
    assert p.exists()
    assert p.stat().st_size > 0
    with open(p, "rb") as f:
        header = f.read(8)
    assert header == b"\x89PNG\r\n\x1a\n"


def test_plot_sed_spectrum_empty(tmp_path: Path):
    """Verify plot_sed_spectrum handles empty photometry points cleanly."""
    empty_sed = {"ra_deg": 150.0, "dec_deg": 2.0, "sed_points": []}
    out_png = tmp_path / "empty_sed.png"
    p = plot_sed_spectrum(empty_sed, out_png_path=out_png)
    assert p.exists()
    assert p.stat().st_size > 0

    with open(diag_path, "rb") as f:
        header = f.read(8)
    assert header == b"\x89PNG\r\n\x1a\n"


def test_plot_trajectory_fit_insufficient_evidence(tmp_path: Path):
    """Verify plot_trajectory_fit handles empty/insufficient dictionaries cleanly."""
    empty_dict = {"outcome": "insufficient_evidence", "measurements": []}
    out_png = tmp_path / "fallback_diagnostic.png"
    diag_path = plot_trajectory_fit(empty_dict, out_png_path=out_png)

    assert diag_path.exists()
    assert diag_path.stat().st_size > 0


def test_plot_sed_spectrum_valid(tmp_path: Path):
    """Verify plot_sed_spectrum generates a valid SED plot with power-law fit."""
    sed_dict = {
        "ra_deg": 150.0,
        "dec_deg": 2.0,
        "spectral_index": -1.25,
        "sed_points": [
            {"detector": "D1", "wavelength_um": 0.95, "flux": 15.2, "snr": 20.0, "status": "ok"},
            {"detector": "D2", "wavelength_um": 1.45, "flux": 9.1, "snr": 15.0, "status": "ok"},
            {"detector": "D3", "wavelength_um": 2.10, "flux": 5.8, "snr": 12.0, "status": "ok"},
            {"detector": "D4", "wavelength_um": 3.00, "flux": 3.9, "snr": 9.0, "status": "ok"},
            {"detector": "D5", "wavelength_um": 4.10, "flux": 2.7, "snr": 7.0, "status": "ok"},
            {"detector": "D6", "wavelength_um": 4.80, "flux": 2.1, "snr": 5.0, "status": "ok"},
        ],
    }
    out_png = tmp_path / "test_sed.png"
    p = plot_sed_spectrum(sed_dict, out_png_path=out_png)
    assert p.exists()
    assert p.stat().st_size > 0
    with open(p, "rb") as f:
        header = f.read(8)
    assert header == b"\x89PNG\r\n\x1a\n"


def test_plot_sed_spectrum_empty(tmp_path: Path):
    """Verify plot_sed_spectrum handles empty photometry points cleanly."""
    empty_sed = {"ra_deg": 150.0, "dec_deg": 2.0, "sed_points": []}
    out_png = tmp_path / "empty_sed.png"
    p = plot_sed_spectrum(empty_sed, out_png_path=out_png)
    assert p.exists()
    assert p.stat().st_size > 0

