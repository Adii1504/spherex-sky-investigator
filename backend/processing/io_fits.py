"""FITS I/O and masking for SPHEREx WhyLab.

Loads real and synthetic SPHEREx FITS cutouts into a standardized Observation
dataclass, with robust handling for Multi-Extension FITS (MEF) and single-HDU files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import io
from pathlib import Path
from typing import Any, BinaryIO

from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
import numpy as np


@dataclass
class Observation:
    """Standardized container for a single SPHEREx observation cutout.

    Attributes:
        image: 2D scientific flux array (float64 or float32).
        flags: 2D integer quality/mask array, or None if not present in FITS.
        variance: 2D variance array (sigma^2), or None if not present.
        wcs: 2D celestial World Coordinate System (RA, Dec).
        header_meta: Dictionary of relevant header metadata.
        observed_at_utc: ISO-8601 UTC observation timestamp, or None if unknown.
        detector: Detector identifier (e.g., 1, 2, 'D1'), or None if unknown.
        wavelength_um: Effective wavelength (float in um), 2D wavelength map
            (np.ndarray), or None if unknown.
        warnings: List of warning strings detailing missing data, assumptions,
            or layout anomalies.
    """

    image: np.ndarray
    flags: np.ndarray | None
    variance: np.ndarray | None
    wcs: WCS
    header_meta: dict[str, Any] = field(default_factory=dict)
    observed_at_utc: str | None = None
    detector: int | str | None = None
    wavelength_um: float | np.ndarray | None = None
    warnings: list[str] = field(default_factory=list)


DEFAULT_FATAL_BITMASK: int = 0xFF | (1 << 16) | (1 << 26)


def build_valid_mask(
    flags: np.ndarray | None,
    shape: tuple[int, int] | None = None,
    fatal_bitmask: int = DEFAULT_FATAL_BITMASK,
) -> np.ndarray:
    """Build a boolean usability mask from a flags array.

    In SPHEREx / IPAC astronomical pipelines, the FLAGS image is an integer bitmask.
    Pixels with fatal defect bits (hardware defects 0-7, cosmic rays, uncalibrated)
    are masked, while informational pipeline tags (e.g. catalog matches, zodi subtracted)
    are preserved as valid science pixels.

    Args:
        flags: Integer flag array (2D) or None.
        shape: Expected 2D shape (ny, nx). Required if `flags` is None.
        fatal_bitmask: Bitmask defining fatal unusable pixels (default 0xFF | 1<<16 | 1<<26).

    Returns:
        np.ndarray: Boolean array of shape (ny, nx) where True indicates
            a valid, usable pixel and False indicates a flagged / unusable pixel.

    Raises:
        ValueError: If `flags` is None and `shape` is not specified.
    """
    if flags is not None:
        return (flags & fatal_bitmask) == 0
    if shape is not None:
        return np.ones(shape, dtype=bool)
    raise ValueError("Either `flags` or `shape` must be provided to build_valid_mask.")


def _find_hdu_by_names(hdul: fits.HDUList, candidate_names: list[str]) -> fits.ImageHDU | fits.PrimaryHDU | None:
    """Find an HDU matching candidate names (case-insensitive) that contains data."""
    names_upper = [c.upper() for c in candidate_names]
    for hdu in hdul:
        if hdu.name and hdu.name.upper() in names_upper and hdu.data is not None:
            return hdu
    return None


def _extract_utc_time(header: fits.Header) -> tuple[str | None, list[str]]:
    """Extract observation UTC timestamp from header cards."""
    warnings: list[str] = []
    scale = str(header.get("TIMESYS", "UTC")).strip().lower()
    if "TIMESYS" not in header:
        warnings.append("TIMESYS missing; UTC assumed for this exploratory calculation.")
    if scale not in Time.SCALES:
        warnings.append("Unsupported TIMESYS; observation time unavailable.")
        return None, warnings

    # Priority 1: ISO 8601 string keywords
    for key in ("DATE-OBS", "DATE-BEG", "OBSTIME", "TIME-OBS"):
        val = header.get(key)
        if val and isinstance(val, str) and val.strip():
            try:
                t = Time(val.strip(), format="isot", scale=scale)
                return t.utc.isot, warnings
            except Exception:
                try:
                    t = Time(val.strip(), scale=scale)
                    return t.utc.isot, warnings
                except Exception:
                    pass

    # Priority 2: MJD keywords
    for key in ("MJD-OBS", "MJD-BEG", "MJD"):
        val = header.get(key)
        if val is not None:
            try:
                mjd_val = float(val)
                t = Time(mjd_val, format="mjd", scale=scale)
                return t.utc.isot, warnings
            except Exception:
                pass

    warnings.append("No observation timestamp found in FITS headers; observed_at_utc is None.")
    return None, warnings


def _extract_detector(header: fits.Header, path: Path) -> int | str | None:
    """Extract detector identifier from header or filename."""
    for key in ("DETECTOR", "DET_ID", "BAND", "CHANNEL"):
        val = header.get(key)
        if val is not None:
            val_str = str(val).strip()
            # If value is numeric, return integer
            if val_str.isdigit():
                return int(val_str)
            return val_str

    # Fallback to filename search (e.g. _D1_, _D2., etc.)
    name_upper = path.name.upper()
    for d in range(1, 7):
        if f"_D{d}" in name_upper or f"D{d}_" in name_upper or f"DET{d}" in name_upper:
            return d

    return None


def _extract_wavelength(
    hdul: fits.HDUList,
    img_header: fits.Header,
    primary_header: fits.Header,
) -> tuple[float | np.ndarray | None, list[str]]:
    """Extract wavelength info from CWAVE extension, spectral WCS, or scalar keywords."""
    warnings: list[str] = []

    # Check for CWAVE extension (SPHEREx 2D central wavelength map)
    cwave_hdu = _find_hdu_by_names(hdul, ["CWAVE", "WAVE", "WAVELENGTH_MAP"])
    if cwave_hdu is not None and cwave_hdu.data is not None and cwave_hdu.data.size > 0:
        return cwave_hdu.data.astype(np.float64), warnings

    # Check for scalar wavelength keywords in image or primary header
    for hdr in (img_header, primary_header):
        for key in ("CWAVE", "WAVELEN", "CENTWAVE", "WAVELENGTH", "LAMBDA"):
            val = hdr.get(key)
            if val is not None:
                try:
                    return float(val), warnings
                except (ValueError, TypeError):
                    pass

    # Check for spectral WCS (SPHEREx uses alternate WCS with key='W')
    try:
        spectral_wcs = WCS(img_header, fobj=hdul, key="W")
        if spectral_wcs.has_spectral:
            # We record that spectral WCS exists, but without target coordinates we return None
            warnings.append("Spectral WCS (key='W') detected; wavelength varies spatially across cutout.")
            return None, warnings
    except Exception:
        pass

    warnings.append("No wavelength metadata found in FITS file; wavelength_um is None.")
    return None, warnings


def create_observation_from_array(
    image: np.ndarray,
    wcs: WCS,
    flags: np.ndarray | None = None,
    variance: np.ndarray | None = None,
    observed_at_utc: str | None = None,
    detector: int | str | None = None,
    wavelength_um: float | np.ndarray | None = None,
    header_meta: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> Observation:
    """Construct an Observation directly from in-memory NumPy arrays.

    Ideal for in-memory pipelines, synthetic generators, or Astroquery results
    without saving to disk.

    Args:
        image: 2D float NumPy array of fluxes.
        wcs: 2D celestial astropy.wcs.WCS.
        flags: Optional 2D integer NumPy array of quality flags.
        variance: Optional 2D float NumPy array of variances (sigma^2).
        observed_at_utc: Optional ISO-8601 UTC observation timestamp.
        detector: Optional detector identifier.
        wavelength_um: Optional wavelength float or 2D CWAVE map.
        header_meta: Optional dictionary of metadata cards.
        warnings: Optional initial list of warnings.

    Returns:
        Observation: Standardized observation dataclass.
    """
    warn_list: list[str] = list(warnings or [])

    if image.ndim != 2:
        raise ValueError(f"image must be a 2D array, got shape {image.shape}")

    if not wcs.is_celestial:
        raise ValueError("wcs must be a valid 2D celestial WCS.")

    if flags is not None and flags.shape != image.shape:
        warn_list.append(f"flags shape {flags.shape} does not match image shape {image.shape}; flags ignored.")
        flags = None

    if variance is not None and variance.shape != image.shape:
        warn_list.append(f"variance shape {variance.shape} does not match image shape {image.shape}; variance ignored.")
        variance = None

    return Observation(
        image=image.astype(np.float64),
        flags=np.array(flags, copy=True) if flags is not None else None,
        variance=variance.astype(np.float64) if variance is not None else None,
        wcs=wcs,
        header_meta=header_meta or {},
        observed_at_utc=observed_at_utc,
        detector=detector,
        wavelength_um=wavelength_um,
        warnings=warn_list,
    )


def load_observation(
    source: str | Path | io.BytesIO | BinaryIO | fits.HDUList,
) -> Observation:
    """Load a SPHEREx FITS cutout from disk, in-memory bytes, or an open HDUList.

    Accepts:
    - File path (str or Path)
    - In-memory file-like buffer (io.BytesIO / BinaryIO, e.g. FastAPI UploadFile.file)
    - Open astropy.io.fits.HDUList

    Args:
        source: FITS file path, BytesIO buffer, or open HDUList.

    Returns:
        Observation: Parsed observation structure.
    """
    warnings: list[str] = []
    source_name = "in-memory-source"
    file_path = Path(source) if isinstance(source, (str, Path)) else Path("in_memory.fits")

    if isinstance(source, (str, Path)):
        p = Path(source)
        if not p.is_file():
            raise FileNotFoundError(f"File not found: {p}")
        source_name = p.name
        hdul_ctx = fits.open(p, memmap=False)
        should_close = True
    elif isinstance(source, fits.HDUList):
        hdul_ctx = source
        should_close = False
    elif hasattr(source, "read"):
        source.seek(0)
        hdul_ctx = fits.open(source, memmap=False)
        should_close = True
    else:
        raise TypeError(f"Unsupported source type: {type(source)}")

    try:
        hdul = hdul_ctx
        primary_header = hdul[0].header

        # 1. Locate science image HDU
        image_hdu = _find_hdu_by_names(hdul, ["IMAGE", "SCI"])
        if image_hdu is None:
            # Fall back to PRIMARY if it contains data
            if hdul[0].data is not None:
                image_hdu = hdul[0]
            else:
                # Find first HDU with 2D or 3D data
                for hdu in hdul[1:]:
                    if hdu.data is not None and getattr(hdu.data, "ndim", 0) in (2, 3):
                        image_hdu = hdu
                        break

        if image_hdu is None or image_hdu.data is None:
            raise ValueError(f"No science image array found in {file_path}")

        raw_image = image_hdu.data
        if raw_image.ndim == 3 and raw_image.shape[0] == 1:
            raw_image = raw_image.squeeze(axis=0)
            warnings.append("3D image data with singleton dimension squeezed to 2D.")
        elif raw_image.ndim != 2:
            raise ValueError(
                f"Expected 2D image data in {file_path}, got shape {raw_image.shape}"
            )

        image = raw_image.astype(np.float64)

        # 2. Extract Celestial WCS
        wcs_candidate_headers = [image_hdu.header, primary_header]
        target_wcs: WCS | None = None
        for hdr in wcs_candidate_headers:
            try:
                candidate = WCS(hdr)
                if candidate.is_celestial:
                    target_wcs = candidate
                    break
                if candidate.has_celestial:
                    target_wcs = candidate.celestial
                    break
            except Exception:
                continue

        if target_wcs is None:
            raise ValueError(f"No valid celestial WCS found in {file_path}")
        if target_wcs.sip is not None and not any("-SIP" in str(hdr.get("CTYPE1", "")) for hdr in wcs_candidate_headers):
            warnings.append("SIP distortion coefficients are present without a -SIP CTYPE declaration. Astropy applies them; verify the header convention before interpreting astrometric results.")

        # 3. Locate flags / data quality HDU
        flags_hdu = _find_hdu_by_names(hdul, ["FLAGS", "DQ", "MASK", "QUALITY"])
        flags: np.ndarray | None = None
        if flags_hdu is not None and flags_hdu.data is not None:
            raw_flags = flags_hdu.data
            if raw_flags.shape == image.shape:
                flags = np.array(raw_flags, copy=True)
            else:
                warnings.append(
                    f"Flags shape {raw_flags.shape} does not match image shape {image.shape}; flags set to None."
                )
        else:
            warnings.append("No FLAGS/DQ extension found; flags set to None.")

        # 4. Locate variance HDU
        var_hdu = _find_hdu_by_names(hdul, ["VARIANCE", "VAR", "ERR", "SIGMA"])
        variance: np.ndarray | None = None
        if var_hdu is not None and var_hdu.data is not None:
            raw_var = var_hdu.data
            if raw_var.shape == image.shape:
                if var_hdu.name.upper() in ("ERR", "SIGMA"):
                    variance = (raw_var.astype(np.float64)) ** 2
                    warnings.append(f"Derived variance by squaring '{var_hdu.name}' (uncertainty) extension.")
                else:
                    variance = raw_var.astype(np.float64)
            else:
                warnings.append(
                    f"Variance shape {raw_var.shape} does not match image shape {image.shape}; variance set to None."
                )
        else:
            warnings.append("No VARIANCE extension found; variance set to None.")

        # 5. Extract observation timestamp
        observed_at, time_warn = _extract_utc_time(image_hdu.header)
        if observed_at is None and image_hdu != hdul[0]:
            observed_at, time_warn = _extract_utc_time(primary_header)
        warnings.extend(time_warn)

        # 6. Extract detector
        detector = _extract_detector(image_hdu.header, file_path)
        if detector is None and image_hdu != hdul[0]:
            detector = _extract_detector(primary_header, file_path)
        if detector is None:
            warnings.append("Detector identifier could not be determined; detector is None.")

        # 7. Extract wavelength info
        wavelength_um, wave_warn = _extract_wavelength(hdul, image_hdu.header, primary_header)
        warnings.extend(wave_warn)

        # 8. Collect relevant header metadata
        meta_keys = [
            "TELESCOP", "INSTRUME", "OBJECT", "BUNIT", "EXPTIME", "FILTER",
            "EQUINOX", "RADESYS", "VERSION", "NSTACK", "STACKTYP", "ZODISUB", "OBS_ID", "DATE-OBS", "TIMESYS"
        ]
        header_meta: dict[str, Any] = {}
        for k in meta_keys:
            val = image_hdu.header.get(k, primary_header.get(k))
            if val is not None:
                header_meta[k] = val

        return Observation(
            image=image,
            flags=flags,
            variance=variance,
            wcs=target_wcs,
            header_meta=header_meta,
            observed_at_utc=observed_at,
            detector=detector,
            wavelength_um=wavelength_um,
            warnings=warnings,
        )
    finally:
        if should_close:
            hdul_ctx.close()


def _load_raster_image_as_observation(source: Any) -> Observation:
    """Load standard raster image (PNG, JPG, TIFF) as an astronomical Observation."""
    from PIL import Image

    try:
        pil_img = Image.open(source)
    except Exception as e:
        raise ValueError(f"Could not parse image file as FITS or standard image format: {e}")

    # Convert to grayscale luminance
    gray = pil_img.convert("L")
    arr = np.array(gray, dtype=np.float64)

    ny, nx = arr.shape
    # Construct a valid tangent celestial WCS centered on RA 150.0, Dec 2.0
    w = WCS(naxis=2)
    w.wcs.crpix = [float(nx) / 2.0, float(ny) / 2.0]
    w.wcs.cdelt = [-1.0 / 3600.0, 1.0 / 3600.0]  # 1 arcsec per pixel
    w.wcs.crval = [150.0, 2.0]
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]

    return Observation(
        image=arr,
        flags=np.zeros_like(arr, dtype=np.int32),
        variance=None,
        wcs=w,
        header_meta={"SOURCE_TYPE": "RASTER_IMAGE", "FORMAT": getattr(pil_img, "format", "UNKNOWN")},
        observed_at_utc=None,
        detector="RASTER",
        wavelength_um=None,
        warnings=["Loaded standard raster image format (PNG/JPG); synthesized standard celestial tangent WCS."],
    )
