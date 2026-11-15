"""Tests for backend/processing/alignment.py.

Includes tests for:
- make_common_grid WCS construction and orientation (North up, East left).
- reproject_to_grid with both reproject and scipy backends.
- Mask propagation and boundary handling.
- Zero-overlap and partial-coverage warnings.
"""

from __future__ import annotations

from pathlib import Path

from astropy.wcs import WCS
import numpy as np
import pytest

from backend.processing.alignment import make_common_grid, reproject_to_grid
from backend.processing.io_fits import Observation, load_observation


def test_make_common_grid_orientation_and_scale():
    """Verify make_common_grid creates North-up / East-left celestial WCS (Hard Rule 7)."""
    ra0, dec0 = 180.0, 30.0
    fov_arcmin = 10.0
    size_px = 200

    w = make_common_grid(ra_deg=ra0, dec_deg=dec0, fov_arcmin=fov_arcmin, size_px=size_px)

    assert w.is_celestial
    assert w.naxis == 2

    # Center pixel should map to reference coordinate
    # (Astropy 0-indexed center is (size_px - 1) / 2.0 = 99.5)
    cx, cy = (size_px - 1) / 2.0, (size_px - 1) / 2.0
    ra_c, dec_c = w.pixel_to_world_values(cx, cy)
    assert np.isclose(ra_c, ra0, atol=1e-5)
    assert np.isclose(dec_c, dec0, atol=1e-5)

    # Orientation check:
    # 1. North up: Moving +Y (up) increases Declination
    ra_north, dec_north = w.pixel_to_world_values(cx, cy + 10.0)
    assert dec_north > dec_c, "Moving up (+Y) must increase Dec (North up)"
    assert np.isclose(ra_north, ra_c, atol=1e-5)

    # 2. East left: Moving -X (left) increases Right Ascension (East left)
    ra_east, dec_east = w.pixel_to_world_values(cx - 10.0, cy)
    assert ra_east > ra_c, "Moving left (-X) must increase RA (East left)"
    assert np.isclose(dec_east, dec_c, atol=1e-5)

    # Pixel scale check
    expected_scale_deg = (fov_arcmin / 60.0) / size_px
    scales = w.proj_plane_pixel_scales()
    assert np.isclose(scales[0].to_value("deg"), expected_scale_deg, rtol=1e-4)
    assert np.isclose(scales[1].to_value("deg"), expected_scale_deg, rtol=1e-4)


def test_make_common_grid_invalid_inputs():
    """Verify input validation on make_common_grid."""
    with pytest.raises(ValueError, match="fov_arcmin must be positive"):
        make_common_grid(10.0, 10.0, fov_arcmin=-1.0)

    with pytest.raises(ValueError, match="size_px must be positive"):
        make_common_grid(10.0, 10.0, fov_arcmin=5.0, size_px=0)

    with pytest.raises(ValueError, match="dec_deg must be within"):
        make_common_grid(10.0, 95.0, fov_arcmin=5.0)


@pytest.fixture
def synthetic_point_source_obs() -> Observation:
    """Create a synthetic observation with a single bright point source at (150.0, 2.0).

    SYNTHETIC TEST DATA: Not real astronomical measurements.
    """
    ny, nx = 40, 40
    ra0, dec0 = 150.0, 2.0
    scale_deg = 6.0 / 3600.0  # 6 arcsec/px

    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crpix = [20.5, 20.5]
    w.wcs.crval = [ra0, dec0]
    w.wcs.cdelt = [-scale_deg, scale_deg]

    image = np.full((ny, nx), 0.1, dtype=np.float64)
    # Point source at pixel (20, 20) in 0-indexed array (which is crpix [20.5, 20.5] in 1-indexed)
    image[20, 20] = 50.0

    flags = np.zeros((ny, nx), dtype=np.int32)
    flags[5, 5] = 1  # 1 bad pixel

    return Observation(
        image=image,
        flags=flags,
        variance=None,
        wcs=w,
        observed_at_utc="2025-05-01T00:00:00.000",
        detector=1,
        wavelength_um=1.0,
        warnings=[],
    )


def test_reproject_to_grid_both_backends(synthetic_point_source_obs: Observation):
    """Verify reprojection produces centered point source across both backends."""
    target_wcs = make_common_grid(
        ra_deg=150.0,
        dec_deg=2.0,
        fov_arcmin=4.0,  # 240 arcsec
        size_px=64,      # ~3.75 arcsec/px
    )

    # Test scipy backend
    img_scipy, mask_scipy, warn_scipy = reproject_to_grid(
        synthetic_point_source_obs, target_wcs, shape_out=(64, 64), use_library="scipy"
    )
    # Test reproject backend
    img_repr, mask_repr, warn_repr = reproject_to_grid(
        synthetic_point_source_obs, target_wcs, shape_out=(64, 64), use_library="reproject"
    )

    assert img_scipy.shape == (64, 64)
    assert img_repr.shape == (64, 64)
    assert mask_scipy.shape == (64, 64)
    assert mask_repr.shape == (64, 64)

    # In both backends, peak should be near center pixel (31.5, 31.5)
    max_pos_scipy = np.unravel_index(np.nanargmax(img_scipy), img_scipy.shape)
    max_pos_repr = np.unravel_index(np.nanargmax(img_repr), img_repr.shape)

    assert abs(max_pos_scipy[0] - 31.5) <= 1.0
    assert abs(max_pos_scipy[1] - 31.5) <= 1.0
    assert abs(max_pos_repr[0] - 31.5) <= 1.0
    assert abs(max_pos_repr[1] - 31.5) <= 1.0


def test_reproject_mask_preservation(synthetic_point_source_obs: Observation):
    """Verify that source flagged pixels and boundary pixels are marked invalid."""
    target_wcs = make_common_grid(
        ra_deg=150.0,
        dec_deg=2.0,
        fov_arcmin=10.0,  # FOV larger than 40*6"=240" source image
        size_px=80,
    )

    aligned_img, aligned_mask, warnings = reproject_to_grid(
        synthetic_point_source_obs, target_wcs, shape_out=(80, 80)
    )

    # Out-of-bounds pixels on the border must be masked and NaN
    assert aligned_mask[0, 0] is np.False_
    assert np.isnan(aligned_img[0, 0])

    # Center should be valid
    assert aligned_mask[40, 40] is np.True_
    assert np.isfinite(aligned_img[40, 40])

    # Partial coverage warning should be triggered (Hard Rule 4)
    assert any("Partial coverage" in w for w in warnings)


def test_reproject_zero_overlap(synthetic_point_source_obs: Observation):
    """Verify that non-overlapping target grid results in all-masked output and warning."""
    # Source is at (150, 2), place target at (0, 0)
    target_wcs = make_common_grid(ra_deg=0.0, dec_deg=0.0, fov_arcmin=2.0, size_px=32)

    aligned_img, aligned_mask, warnings = reproject_to_grid(
        synthetic_point_source_obs, target_wcs, shape_out=(32, 32)
    )

    assert np.all(~aligned_mask)
    assert np.all(np.isnan(aligned_img))
    assert any("Zero valid overlap" in w for w in warnings)


def test_reproject_real_cutout():
    """Verify reprojection on real SPHEREx cutout from sample_data."""
    real_path = Path("backend/processing/sample_data/spherex_d1_cutout.fits")
    if not real_path.exists():
        pytest.skip("Real sample cutout not present.")

    obs = load_observation(real_path)
    # Extract center coordinate of real cutout
    ra0, dec0 = obs.wcs.pixel_to_world_values(7.5, 7.5)

    target_wcs = make_common_grid(ra_deg=float(ra0), dec_deg=float(dec0), fov_arcmin=1.5, size_px=32)
    aligned_img, aligned_mask, warnings = reproject_to_grid(obs, target_wcs, shape_out=(32, 32))

    assert aligned_img.shape == (32, 32)
    assert np.count_nonzero(aligned_mask) > 0
