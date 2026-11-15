"""Tests for backend/processing/compatibility.py.

Includes tests for:
- Missing wavelength metadata resulting in 'unknown' status.
- Compatible and incompatible wavelength classifications.
- Spatially-varying CWAVE map sampling.
- Detector mismatch warnings.
"""

from __future__ import annotations

from astropy.wcs import WCS
import numpy as np
import pytest

from backend.processing.compatibility import check_wavelength_compatibility
from backend.processing.io_fits import Observation


def _make_dummy_obs(
    wavelength: float | np.ndarray | None,
    detector: int | str | None = 1,
) -> Observation:
    """Helper to construct dummy Observation with synthetic data."""
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crpix = [10.5, 10.5]
    w.wcs.crval = [100.0, 0.0]
    w.wcs.cdelt = [-0.001, 0.001]
    return Observation(
        image=np.ones((20, 20), dtype=np.float64),
        flags=np.zeros((20, 20), dtype=np.int32),
        variance=None,
        wcs=w,
        observed_at_utc="2025-01-01T00:00:00",
        detector=detector,
        wavelength_um=wavelength,
        warnings=[],
    )


def test_missing_wavelength_returns_unknown():
    """Verify that any missing wavelength metadata strictly yields status 'unknown'."""
    obs1 = _make_dummy_obs(wavelength=1.2)
    obs2 = _make_dummy_obs(wavelength=None)  # Missing!

    result = check_wavelength_compatibility([obs1, obs2])

    assert result["status"] == "unknown"
    assert result["wavelengths_um"] == [1.2, None]
    assert any("missing or incomplete" in w for w in result["warnings"])


def test_compatible_wavelengths():
    """Verify observations with wavelengths within tolerance return 'compatible'."""
    obs1 = _make_dummy_obs(wavelength=1.00)
    obs2 = _make_dummy_obs(wavelength=1.05)  # ~5% difference, below 15% tolerance

    result = check_wavelength_compatibility([obs1, obs2], tolerance_fraction=0.15)

    assert result["status"] == "compatible"
    assert result["wavelengths_um"] == [1.00, 1.05]


def test_incompatible_wavelengths():
    """Verify observations with wide wavelength disparity return 'incompatible'."""
    obs1 = _make_dummy_obs(wavelength=0.90, detector=1)
    obs2 = _make_dummy_obs(wavelength=3.50, detector=4)

    result = check_wavelength_compatibility([obs1, obs2], tolerance_fraction=0.15)

    assert result["status"] == "incompatible"
    assert any("Wavelength disparity is" in w for w in result["warnings"])
    assert any("chromatic artifacts" in w for w in result["warnings"])


def test_detector_mismatch_warning():
    """Verify detector difference is recorded as a warning even if wavelengths match."""
    obs1 = _make_dummy_obs(wavelength=2.40, detector=3)
    obs2 = _make_dummy_obs(wavelength=2.42, detector=4)  # Overlap at band edge

    result = check_wavelength_compatibility([obs1, obs2], tolerance_fraction=0.15)

    assert result["status"] == "compatible"
    assert any("different detectors" in w for w in result["warnings"])


def test_spatially_varying_cwave_map():
    """Verify extracting wavelength from 2D CWAVE map at a target sky coordinate."""
    # CWAVE varies from 1.0 um at pixel 0 to 2.0 um at pixel 19
    cwave_map = np.tile(np.linspace(1.0, 2.0, 20), (20, 1))
    obs1 = _make_dummy_obs(wavelength=cwave_map)
    obs2 = _make_dummy_obs(wavelength=1.5)

    # Reference center of wcs is at pixel (10.5, 10.5) 1-based = index (10, 10) 0-based
    # RA=100.0, Dec=0.0 maps to index (10, 10), where cwave ~ 1.526 um
    result = check_wavelength_compatibility(
        [obs1, obs2],
        tolerance_fraction=0.15,
        target_coord=(100.0, 0.0),
    )

    assert result["status"] == "compatible"
    assert isinstance(result["wavelengths_um"][0], float)
    assert np.isclose(result["wavelengths_um"][0], 1.526, atol=0.05)


def test_empty_observation_list():
    """Verify handling of empty observation list."""
    result = check_wavelength_compatibility([])
    assert result["status"] == "unknown"
    assert any("No observations provided" in w for w in result["warnings"])
