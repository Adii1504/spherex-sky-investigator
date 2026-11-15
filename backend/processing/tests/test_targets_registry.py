"""Unit tests for SPHEREx Target Registry & Real Dataset Integration.

Validates loading of real NASA SPHEREx Level 2 FITS cutouts, metadata manifests,
and Gaia DR3 / CatWISE2020 astrometric ground truth for 5 benchmark targets:
- Barnard's Star
- WISE 0855-0714
- Epsilon Indi B
- RW Aurigae
- R Draconis
"""

from __future__ import annotations

import math
from pathlib import Path
import pytest

from backend.processing.targets_registry import (
    load_astrometry_ground_truth,
    get_target_manifest,
    get_target_observations,
    TargetAstrometryTruth,
)
from backend.processing.io_fits import Observation


def test_load_astrometry_ground_truth():
    """Verify ground truth loader parses all 5 benchmark targets correctly."""
    truth = load_astrometry_ground_truth()
    assert len(truth) >= 5, "Expected at least 5 benchmark targets in ground truth CSV"

    # Check Barnard's Star (~10.4''/yr)
    assert "Barnards_Star" in truth
    barnard = truth["Barnards_Star"]
    assert isinstance(barnard, TargetAstrometryTruth)
    assert barnard.source_catalogue == "Gaia DR3"
    assert math.isclose(barnard.pmdec_mas_yr, 10362.5, rel_tol=1e-3)
    assert barnard.total_proper_motion_arcsec_yr > 10.0

    # Check WISE 0855 (~8.0''/yr)
    assert "WISE_0855" in truth
    wise = truth["WISE_0855"]
    assert wise.total_proper_motion_arcsec_yr > 7.5

    # Check Epsilon Indi B (~4.7''/yr)
    assert "Epsilon_Indi_B" in truth
    eps = truth["Epsilon_Indi_B"]
    assert eps.total_proper_motion_arcsec_yr > 4.5

    # Check stationary / slow targets
    assert "RW_Aurigae" in truth
    assert "R_Draconis" in truth


def test_get_target_manifest():
    """Verify manifest lists all 21 observations and confirms files exist on disk."""
    manifest = get_target_manifest()
    assert len(manifest) >= 21, f"Expected 21 cutouts in manifest, found {len(manifest)}"

    # All files in manifest must physically exist
    for entry in manifest:
        assert entry["file_exists"] is True, f"FITS file missing: {entry['fits_path']}"
        assert entry["target_key"] in {"Barnards_Star", "WISE_0855", "Epsilon_Indi_B", "RW_Aurigae", "R_Draconis"}
        assert Path(entry["fits_path"]).suffix == ".fits"


def test_get_target_observations_barnards_star():
    """Verify loading chronological Observation objects for Barnard's Star."""
    obs_list = get_target_observations("Barnards_Star")
    assert len(obs_list) == 5, f"Expected 5 epochs for Barnard's Star, got {len(obs_list)}"

    for obs in obs_list:
        assert isinstance(obs, Observation)
        assert obs.image is not None
        assert obs.wcs is not None
        assert obs.flags is not None
        assert "TRUE_RA_DEG" in obs.header_meta
        assert "TRUE_DEC_DEG" in obs.header_meta
        # Barnard's Star coordinates around RA ~ 269.45, Dec ~ 4.7-4.8
        assert 269.0 < obs.header_meta["TRUE_RA_DEG"] < 270.0
        assert 4.5 < obs.header_meta["TRUE_DEC_DEG"] < 5.0

    # Verify chronological sorting
    dates = [obs.header_meta.get("DATE-OBS") or obs.header_meta.get("DATE_OBS", "") for obs in obs_list]
    assert dates == sorted(dates), "Observations should be sorted chronologically"


def test_get_target_observations_wise_0855():
    """Verify loading chronological Observation objects for WISE 0855."""
    obs_list = get_target_observations("WISE_0855")
    assert len(obs_list) == 5, f"Expected 5 epochs for WISE 0855, got {len(obs_list)}"

    for obs in obs_list:
        assert isinstance(obs, Observation)
        assert obs.image.ndim == 2
        assert obs.image.shape[0] > 0 and obs.image.shape[1] > 0
        assert "TRUE_RA_DEG" in obs.header_meta
        # WISE 0855 coordinates around RA ~ 133.76, Dec ~ -7.24
        assert 133.0 < obs.header_meta["TRUE_RA_DEG"] < 134.5
        assert -8.0 < obs.header_meta["TRUE_DEC_DEG"] < -6.5


def test_get_target_observations_case_insensitive():
    """Verify lookup is case-insensitive."""
    obs_lower = get_target_observations("barnards_star")
    obs_upper = get_target_observations("BARNARDS_STAR")
    assert len(obs_lower) == 5
    assert len(obs_upper) == 5
