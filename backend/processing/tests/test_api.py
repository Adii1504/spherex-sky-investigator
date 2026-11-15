"""Tests for backend/main.py FastAPI routes.

Verifies health check, presets, investigation endpoint (both synthetic sequence
and real NASA SPHEREx Level 2 presets with Gaia DR3 truth), SED extraction,
hotspots scanning, and multi-channel false-color composite generation.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from backend.main import (
    build_viewspace_composite,
    get_hotspots,
    get_sed,
    health_check,
    investigate_sequence,
    list_presets,
)


def run_sync(coro):
    """Scientific endpoints are synchronous so FastAPI uses its thread pool."""
    return coro


def test_api_health_check():
    """Verify health_check route returns operational status and detector info."""
    h = run_sync(health_check())
    assert h["status"] == "healthy"
    assert "SPHEREx" in h["service"]
    assert h["sample_sequence_epochs_available"] >= 4
    assert len(h["detectors_supported"]) == 6


def test_api_list_presets():
    """Verify list_presets route returns pre-packaged investigation scenarios."""
    presets = run_sync(list_presets())
    assert len(presets) >= 7
    preset_ids = [p["id"] for p in presets]
    assert "synthetic_asteroid_sequence" in preset_ids
    assert "nasa_real_6bands" in preset_ids
    assert "Barnards_Star" in preset_ids
    assert "WISE_0855" in preset_ids
    assert "Epsilon_Indi_B" in preset_ids
    assert "RW_Aurigae" in preset_ids
    assert "R_Draconis" in preset_ids


def test_api_investigate_synthetic_preset():
    """Verify investigate_sequence runs end-to-end on synthetic asteroid preset."""
    res = run_sync(investigate_sequence(preset_id="synthetic_asteroid_sequence"))
    assert res["outcome"] == "motion_supported"
    assert len(res["frames"]) == 4
    assert len(res["differences"]) == 3
    assert res["blink_animation_url"] is not None
    assert "diagnostic_trajectory_url" in res


def test_api_investigate_barnards_star_preset():
    """Verify investigate_sequence runs on real NASA SPHEREx Barnard's Star with Gaia DR3 truth."""
    res = run_sync(investigate_sequence(preset_id="Barnards_Star"))
    assert res["investigation_id"] == "SPX_BARNARDS_STAR"
    assert len(res["frames"]) == 5
    assert len(res["differences"]) == 4
    assert res["blink_animation_url"] is not None
    assert "gaia_ground_truth" in res
    truth = res["gaia_ground_truth"]
    assert truth["source_catalogue"] == "Gaia DR3"
    assert truth["total_proper_motion_arcsec_yr"] > 10.0


def test_api_get_hotspots_real_target():
    """Verify get_hotspots functions on real NASA target cutouts."""
    scan = run_sync(get_hotspots(preset_id="Barnards_Star"))
    assert "hotspots" in scan
    assert "total_hotspots" in scan
    assert "num_epochs" in scan


def test_api_get_sed():
    """Verify get_sed extracts photometry across real SPHEREx cutouts."""
    sed = run_sync(get_sed(ra_deg=150.0, dec_deg=2.0))
    assert "sed_points" in sed
    assert len(sed["sed_points"]) == 6
    assert "sed_plot_url" in sed


def test_api_build_composite():
    """Verify build_viewspace_composite generates a false-color 3-band composite."""
    comp = run_sync(build_viewspace_composite(red_band=6, green_band=3, blue_band=1))
    assert "composite_url" in comp
    assert comp["composite_url"].endswith(".png")
