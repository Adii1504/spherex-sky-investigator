"""Tests for backend/processing/io_fits.py.

Includes tests against:
1. Real SPHEREx cutout from NASA/IPAC IRSA / SPHEREx pipeline archives.
2. Synthetic Multi-Extension FITS fixtures (clearly labelled SYNTHETIC TEST DATA).
"""

from __future__ import annotations

from pathlib import Path
import io

from astropy.io import fits
from astropy.wcs import WCS
import numpy as np
import pytest

from backend.processing.io_fits import (
    Observation,
    build_valid_mask,
    create_observation_from_array,
    load_observation,
)


@pytest.fixture
def synthetic_mef_cutout(tmp_path: Path) -> Path:
    """Create a synthetic SPHEREx MEF cutout file for testing.

    SYNTHETIC TEST DATA: Not real astronomical measurements.
    Constructed strictly to test multi-extension FITS ingestion.
    """
    file_path = tmp_path / "synthetic_spherex_cutout_D1.fits"

    ny, nx = 32, 32

    # Primary HDU (metadata only)
    pri_hdr = fits.Header()
    pri_hdr["TELESCOP"] = "SPHEREx"
    pri_hdr["INSTRUME"] = "SPHEREx"
    pri_hdr["VERSION"] = "SYNTHETIC TEST DATA v1.0"
    pri_hdr["OBS_ID"] = "SYNTH_OBS_001"
    pri_hdr["DATE-OBS"] = "2025-06-15T12:00:00.000"
    pri_hdr["COMMENT"] = "SYNTHETIC TEST DATA - DO NOT USE FOR SCIENCE"
    primary_hdu = fits.PrimaryHDU(header=pri_hdr)

    # Science Image HDU
    img_hdr = fits.Header()
    img_hdr["EXTNAME"] = "IMAGE"
    img_hdr["BUNIT"] = "MJy/sr"
    img_hdr["DETECTOR"] = 1
    # Celestial WCS
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crpix = [16.5, 16.5]
    w.wcs.crval = [150.0, 2.0]
    w.wcs.cd = np.array([[-6.15 / 3600.0, 0.0], [0.0, 6.15 / 3600.0]])
    img_hdr.update(w.to_header())

    rng = np.random.default_rng(42)
    fake_flux = rng.normal(loc=0.1, scale=0.01, size=(ny, nx)).astype(np.float32)
    # Inject a synthetic point source
    fake_flux[16, 16] += 2.5
    image_hdu = fits.ImageHDU(data=fake_flux, header=img_hdr, name="IMAGE")

    # Flags HDU: 0 = good, 1 = cosmic ray, 2 = bad pixel
    fake_flags = np.zeros((ny, nx), dtype=np.int32)
    fake_flags[5, 5] = 1   # cosmic ray
    fake_flags[10, 12] = 2 # bad pixel
    flags_hdu = fits.ImageHDU(data=fake_flags, name="FLAGS")

    # Variance HDU
    fake_var = np.full((ny, nx), 0.0001, dtype=np.float32)
    variance_hdu = fits.ImageHDU(data=fake_var, name="VARIANCE")

    # CWAVE HDU: central wavelength map in microns
    fake_cwave = np.linspace(0.75, 1.10, nx, dtype=np.float32)
    cwave_map = np.tile(fake_cwave, (ny, 1))
    cwave_hdu = fits.ImageHDU(data=cwave_map, name="CWAVE")

    hdul = fits.HDUList([primary_hdu, image_hdu, flags_hdu, variance_hdu, cwave_hdu])
    hdul.writeto(file_path, overwrite=True)
    return file_path


def test_build_valid_mask_with_flags():
    """Verify build_valid_mask correctly masks non-zero flag pixels."""
    flags = np.array([[0, 1], [0, 4]], dtype=np.int32)
    mask = build_valid_mask(flags)
    expected = np.array([[True, False], [True, False]], dtype=bool)
    np.testing.assert_array_equal(mask, expected)


def test_build_valid_mask_none_with_shape():
    """Verify build_valid_mask creates all-True mask when flags is None and shape given."""
    mask = build_valid_mask(None, shape=(4, 4))
    assert mask.shape == (4, 4)
    assert np.all(mask)


def test_build_valid_mask_missing_args():
    """Verify ValueError is raised if neither flags nor shape is given."""
    with pytest.raises(ValueError, match="Either `flags` or `shape`"):
        build_valid_mask(None)


def test_load_observation_synthetic_mef(synthetic_mef_cutout: Path):
    """Verify loading a complete synthetic SPHEREx MEF cutout."""
    obs = load_observation(synthetic_mef_cutout)

    assert isinstance(obs, Observation)
    assert obs.image.shape == (32, 32)
    assert obs.flags is not None
    assert obs.flags.shape == (32, 32)
    assert obs.flags[5, 5] == 1
    assert obs.variance is not None
    assert obs.variance.shape == (32, 32)
    assert obs.wcs.is_celestial
    assert obs.observed_at_utc == "2025-06-15T12:00:00.000"
    assert obs.detector == 1
    assert isinstance(obs.wavelength_um, np.ndarray)
    assert obs.wavelength_um.shape == (32, 32)

    # Test usability mask
    mask = build_valid_mask(obs.flags)
    assert mask[16, 16] is np.True_
    assert mask[5, 5] is np.False_
    assert mask[10, 12] is np.False_


def test_load_observation_real_cutout():
    """Verify loading real SPHEREx cutout from sample_data."""
    real_path = Path("backend/processing/sample_data/spherex_d1_cutout.fits")
    if not real_path.exists():
        pytest.skip("Real sample cutout not present.")

    obs = load_observation(real_path)
    assert isinstance(obs, Observation)
    assert obs.image.shape == (16, 16)
    assert obs.wcs.is_celestial
    assert obs.wcs.naxis == 2

    # Verify that missing components are strictly None (Hard Rule 3)
    assert obs.flags is None
    assert obs.variance is None
    # Warnings must record missing flags/variance (Hard Rule 4)
    assert any("No FLAGS/DQ extension found" in w for w in obs.warnings)
    assert any("No VARIANCE extension found" in w for w in obs.warnings)

    # Valid mask should handle None flags given shape
    mask = build_valid_mask(obs.flags, obs.image.shape)
    assert mask.shape == (16, 16)
    assert np.all(mask)


def test_load_observation_nonexistent_file():
    """Verify FileNotFoundError is raised for non-existent files."""
    with pytest.raises(FileNotFoundError):
        load_observation("backend/processing/sample_data/non_existent.fits")


def test_load_observation_header_mjd(tmp_path: Path):
    """Verify timestamp parsing when only MJD-OBS is present.

    SYNTHETIC TEST DATA: Not real astronomical measurements.
    """
    file_path = tmp_path / "synthetic_mjd.fits"

    hdr = fits.Header()
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crpix = [5.0, 5.0]
    w.wcs.crval = [100.0, 20.0]
    w.wcs.cdelt = [-0.001, 0.001]
    hdr.update(w.to_header())
    hdr["MJD-OBS"] = 60000.5  # 2023-02-25 12:00:00

    data = np.ones((10, 10), dtype=np.float32)
    fits.PrimaryHDU(data=data, header=hdr).writeto(file_path)

    obs = load_observation(file_path)
    assert obs.observed_at_utc is not None
    assert "2023-02-25" in obs.observed_at_utc


def test_create_observation_from_numpy_array():
    """Verify creating an Observation directly from in-memory NumPy arrays."""
    # SYNTHETIC TEST DATA
    img = np.full((30, 30), 10.0, dtype=np.float64)
    flags = np.zeros((30, 30), dtype=np.int32)
    flags[5, 5] = 1

    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crpix = [15.5, 15.5]
    w.wcs.crval = [180.0, 45.0]
    w.wcs.cdelt = [-0.001, 0.001]

    obs = create_observation_from_array(
        image=img,
        wcs=w,
        flags=flags,
        variance=np.full((30, 30), 0.01),
        observed_at_utc="2025-07-01T00:00:00",
        detector=2,
        wavelength_um=1.25,
    )

    assert isinstance(obs, Observation)
    assert obs.image.shape == (30, 30)
    assert obs.flags[5, 5] == 1
    assert obs.detector == 2
    assert obs.wavelength_um == 1.25
    assert obs.observed_at_utc == "2025-07-01T00:00:00"


def test_load_observation_from_bytes_io(synthetic_mef_cutout: Path):
    """Verify loading from an in-memory BytesIO stream (e.g. FastAPI upload)."""
    with open(synthetic_mef_cutout, "rb") as f:
        data_bytes = f.read()

    buf = io.BytesIO(data_bytes)
    obs = load_observation(buf)

    assert isinstance(obs, Observation)
    assert obs.image.shape == (32, 32)
    assert obs.flags is not None
    assert obs.detector == 1
