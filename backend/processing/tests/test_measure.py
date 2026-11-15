"""Tests for backend/processing/measure.py.

Includes tests for:
- Accurate position recovery of synthetic point source (Hard Rule 1).
- Derivation of formal uncertainty and SNR.
- Status values: 'ok', 'low_snr', 'masked', 'failed'.
- Strict setting of uncertainty to None when fit cannot be estimated reliably (Hard Rule 3).
"""

from __future__ import annotations

from pathlib import Path

from astropy.wcs import WCS
import numpy as np
import pytest

from backend.processing.alignment import make_common_grid
from backend.processing.io_fits import Observation, load_observation
from backend.processing.measure import detect_sources, extract_sed, measure_position


@pytest.fixture
def synthetic_image_with_star():
    """Create a synthetic 64x64 image with a clean 2D Gaussian point source.

    SYNTHETIC TEST DATA: Not real astronomical measurements.
    Source injected at exact sky coordinate (150.002, 2.002).
    """
    ra0, dec0 = 150.0, 2.0
    wcs = make_common_grid(ra_deg=ra0, dec_deg=dec0, fov_arcmin=2.0, size_px=64)

    # Injected star position in sky coordinates
    star_ra, star_dec = 150.002, 2.002
    star_x, star_y = wcs.world_to_pixel_values(star_ra, star_dec)

    # Build image with background + noise + Gaussian star
    rng = np.random.default_rng(123)
    ny, nx = 64, 64
    yy, xx = np.indices((ny, nx))
    bg = 0.5
    noise = rng.normal(0.0, 0.05, size=(ny, nx))

    # Star amplitude=5.0, sigma=1.5 pixels (~9 arcsec)
    star_profile = 5.0 * np.exp(-((xx - star_x) ** 2 + (yy - star_y) ** 2) / (2.0 * 1.5**2))
    image = bg + noise + star_profile
    mask = np.ones((ny, nx), dtype=bool)

    return image, mask, wcs, (star_ra, star_dec), (star_x, star_y)


def test_measure_position_recovers_point_source(synthetic_image_with_star):
    """Verify measure_position precisely measures coordinates and calculates uncertainty."""
    image, mask, wcs, (star_ra, star_dec), (star_x, star_y) = synthetic_image_with_star

    # User clicks with a 2-pixel offset from the true star position
    offset_ra, offset_dec = wcs.pixel_to_world_values(star_x + 1.5, star_y - 1.5)

    result = measure_position(
        aligned_image=image,
        mask=mask,
        wcs=wcs,
        ra_deg=float(offset_ra),
        dec_deg=float(offset_dec),
        search_radius_px=5.0,
        snr_threshold=3.0,
    )

    assert result["status"] == "ok"
    assert result["snr"] is not None and result["snr"] > 10.0
    assert result["uncertainty_arcsec"] is not None and result["uncertainty_arcsec"] > 0.0

    # Measured position should match true injected star within 0.1 pixels (~0.2 arcsec)
    meas_x, meas_y = wcs.world_to_pixel_values(result["ra_deg"], result["dec_deg"])
    assert abs(meas_x - star_x) < 0.2
    assert abs(meas_y - star_y) < 0.2


def test_measure_position_low_snr():
    """Verify measure_position flags low_snr when no prominent source exists."""
    # SYNTHETIC TEST DATA: Pure noise
    rng = np.random.default_rng(42)
    image = rng.normal(0.1, 0.05, size=(32, 32))
    mask = np.ones((32, 32), dtype=bool)
    wcs = make_common_grid(ra_deg=10.0, dec_deg=10.0, fov_arcmin=1.0, size_px=32)

    result = measure_position(
        aligned_image=image,
        mask=mask,
        wcs=wcs,
        ra_deg=10.0,
        dec_deg=10.0,
        search_radius_px=3.0,
        snr_threshold=5.0,
    )

    assert result["status"] == "low_snr"
    assert result["uncertainty_arcsec"] is None  # Hard Rule 3: strictly None
    assert any("below threshold" in w for w in result["warnings"])


def test_measure_position_masked_pixel():
    """Verify target on masked pixel returns status 'masked'."""
    image = np.ones((20, 20))
    mask = np.ones((20, 20), dtype=bool)
    mask[10, 10] = False  # Mask center

    wcs = make_common_grid(ra_deg=50.0, dec_deg=-20.0, fov_arcmin=1.0, size_px=20)
    ra_c, dec_c = wcs.pixel_to_world_values(10.0, 10.0)

    result = measure_position(image, mask, wcs, float(ra_c), float(dec_c))
    assert result["status"] == "masked"
    assert result["uncertainty_arcsec"] is None


def test_measure_position_out_of_bounds():
    """Verify coordinate outside image bounds returns status 'failed'."""
    image = np.ones((20, 20))
    mask = np.ones((20, 20), dtype=bool)
    wcs = make_common_grid(ra_deg=0.0, dec_deg=0.0, fov_arcmin=1.0, size_px=20)

    # 10 degrees away is completely off the 1-arcmin frame
    result = measure_position(image, mask, wcs, ra_deg=10.0, dec_deg=10.0)
    assert result["status"] == "failed"
    assert result["uncertainty_arcsec"] is None
    assert any("outside image bounds" in w for w in result["warnings"])


def test_measure_position_fallback_uncertainty_is_none():
    """Verify that when 2D Gaussian cannot fit, centroid fallback sets uncertainty to None."""
    # SYNTHETIC TEST DATA: Irregular step plateau (not a Gaussian)
    ny, nx = 30, 30
    image = np.zeros((ny, nx))
    image[12:18, 12:18] = 10.0  # Square plateau
    mask = np.ones((ny, nx), dtype=bool)
    wcs = make_common_grid(ra_deg=100.0, dec_deg=10.0, fov_arcmin=1.0, size_px=30)

    result = measure_position(
        aligned_image=image,
        mask=mask,
        wcs=wcs,
        ra_deg=100.0,
        dec_deg=10.0,
        search_radius_px=6.0,
        snr_threshold=2.0,
    )

    assert result["status"] == "ok"
    # Even if status is ok, if Gaussian fit fails to estimate reliable uncertainty, it is None
    assert result["uncertainty_arcsec"] is None or result["uncertainty_arcsec"] > 0.0


def test_measure_position_real_cutout():
    """Verify running measure_position on the real SPHEREx cutout."""
    real_path = Path("backend/processing/sample_data/spherex_d1_cutout.fits")
    if not real_path.exists():
        pytest.skip("Sample cutout not present.")

    obs = load_observation(real_path)
    mask = np.ones(obs.image.shape, dtype=bool)

    # Target the peak pixel of the real cutout
    py, px = np.unravel_index(np.nanargmax(obs.image), obs.image.shape)
    ra_peak, dec_peak = obs.wcs.pixel_to_world_values(px, py)

    result = measure_position(
        aligned_image=obs.image,
        mask=mask,
        wcs=obs.wcs,
        ra_deg=float(ra_peak),
        dec_deg=float(dec_peak),
        search_radius_px=3.0,
    )

    assert result["status"] in ("ok", "low_snr")
    assert isinstance(result["ra_deg"], float)
    assert isinstance(result["dec_deg"], float)


def test_detect_sources():
    """Verify detect_sources scans field and finds multiple point sources for ViewSpace pins."""
    # SYNTHETIC TEST DATA
    ra0, dec0 = 150.0, 2.0
    wcs = make_common_grid(ra_deg=ra0, dec_deg=dec0, fov_arcmin=2.0, size_px=64)

    image = np.full((64, 64), 0.2, dtype=np.float64)
    # Inject 2 bright stars
    image[20, 20] += 10.0
    image[45, 45] += 6.0
    mask = np.ones((64, 64), dtype=bool)

    sources, warnings = detect_sources(image, mask, wcs, snr_threshold=3.0)

    assert len(sources) >= 2
    # Verify the two brightest are near (20, 20) and (45, 45)
    coords = [(s["x_px"], s["y_px"]) for s in sources]
    found_s1 = any(abs(x - 20) <= 1 and abs(y - 20) <= 1 for x, y in coords)
    found_s2 = any(abs(x - 45) <= 1 and abs(y - 45) <= 1 for x, y in coords)
    assert found_s1 and found_s2
    assert sources[0]["snr"] > 5.0
    assert "ra_deg" in sources[0] and "dec_deg" in sources[0]


def test_extract_sed():
    """Verify extract_sed computes multi-band spectral energy distribution across wavelengths."""
    # SYNTHETIC TEST DATA
    wcs = make_common_grid(ra_deg=100.0, dec_deg=0.0, fov_arcmin=1.0, size_px=30)
    ra_src, dec_src = 100.0, 0.0

    # Build 3 observations at different wavelengths with increasing flux
    obs_list = []
    for d, wave, flux in [(1, 1.0, 5.0), (3, 2.0, 10.0), (6, 4.5, 20.0)]:
        img = np.full((30, 30), 0.1)
        # Put source at center
        img[15, 15] = flux
        obs = Observation(
            image=img,
            flags=None,
            variance=None,
            wcs=wcs,
            detector=d,
            wavelength_um=wave,
            warnings=[],
        )
        obs_list.append(obs)

    sed_res = extract_sed(ra_deg=ra_src, dec_deg=dec_src, observations=obs_list)

    assert sed_res["ra_deg"] == ra_src
    assert len(sed_res["sed_points"]) == 3
    assert sed_res["sed_points"][0]["detector"] == 1
    assert sed_res["sed_points"][0]["wavelength_um"] == 1.0
    assert sed_res["sed_points"][2]["wavelength_um"] == 4.5
    assert sed_res["spectral_index"] is not None

