"""Astrometric alignment and grid reprojection for SPHEREx WhyLab.

Creates standardized North-up / East-left celestial grids and reprojects
SPHEREx cutouts to a common WCS using `reproject` (with seamless fallback
to `scipy.ndimage.map_coordinates`).
"""

from __future__ import annotations

import warnings as py_warnings
from typing import Any

from astropy.wcs import WCS
import numpy as np

try:
    from reproject import reproject_interp
    _HAS_REPROJECT = True
except ImportError:
    _HAS_REPROJECT = False

from scipy.ndimage import map_coordinates

from backend.processing.io_fits import Observation, build_valid_mask


def make_common_grid(
    ra_deg: float,
    dec_deg: float,
    fov_arcmin: float,
    size_px: int = 256,
) -> WCS:
    """Create a standardized celestial WCS target grid centered on (ra_deg, dec_deg).

    Adheres strictly to astronomical convention:
    - Orientation: North up (+Dec along +Y), East left (+RA along -X).
    - Projection: Gnomonic / Tangent ('RA---TAN', 'DEC--TAN').
    - Reference pixel: Exactly at center of the pixel grid.

    Args:
        ra_deg: Right Ascension of target center in degrees (ICRS).
        dec_deg: Declination of target center in degrees (ICRS).
        fov_arcmin: Desired field of view across the frame in arcminutes.
        size_px: Pixel dimension of the square output grid (default 256).

    Returns:
        WCS: Astropy 2D celestial WCS configured with target parameters.

    Raises:
        ValueError: If fov_arcmin <= 0 or size_px <= 0 or dec_deg out of [-90, 90].
    """
    if fov_arcmin <= 0:
        raise ValueError(f"fov_arcmin must be positive, got {fov_arcmin}")
    if size_px <= 0:
        raise ValueError(f"size_px must be positive, got {size_px}")
    if not (-90.0 <= dec_deg <= 90.0):
        raise ValueError(f"dec_deg must be within [-90, 90], got {dec_deg}")

    fov_deg = fov_arcmin / 60.0
    pixel_scale_deg = fov_deg / size_px

    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.radesys = "ICRS"
    w.wcs.equinox = 2000.0

    # Center reference pixel (1-indexed FITS convention: center of size_px is size_px/2 + 0.5)
    crpix_center = (size_px / 2.0) + 0.5
    w.wcs.crpix = [crpix_center, crpix_center]
    w.wcs.crval = [float(ra_deg), float(dec_deg)]

    # North up (+Y), East left (-X in standard FITS projection matrix):
    # CD1_1 = -pixel_scale, CD2_2 = +pixel_scale
    w.wcs.cd = np.array([
        [-pixel_scale_deg, 0.0],
        [0.0, pixel_scale_deg],
    ])

    # Store expected output shape directly on WCS (NAXIS1, NAXIS2)
    w.pixel_shape = (size_px, size_px)
    w.array_shape = (size_px, size_px)
    return w


def _reproject_with_scipy(
    image: np.ndarray,
    valid_mask: np.ndarray,
    src_wcs: WCS,
    target_wcs: WCS,
    shape_out: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray]:
    """Fallback reprojection using astropy WCS coordinate transforms and scipy.ndimage."""
    ny_out, nx_out = shape_out
    yy, xx = np.indices((ny_out, nx_out), dtype=np.float64)

    # 1. Target pixel -> Sky coordinates
    ra_coords, dec_coords = target_wcs.pixel_to_world_values(xx, yy)

    # 2. Sky coordinates -> Source pixel coordinates
    src_x, src_y = src_wcs.world_to_pixel_values(ra_coords, dec_coords)

    # 3. Interpolate science image (bilinear, order=1)
    coords = np.array([src_y, src_x])
    aligned_img = map_coordinates(
        image,
        coords,
        order=1,
        mode="constant",
        cval=np.nan,
        prefilter=False,
    )

    # 4. Interpolate mask (nearest neighbor, order=0)
    aligned_mask_float = map_coordinates(
        valid_mask.astype(np.float64),
        coords,
        order=0,
        mode="constant",
        cval=0.0,
        prefilter=False,
    )

    ny_in, nx_in = image.shape
    in_bounds = (
        (src_x >= -0.5)
        & (src_x <= nx_in - 0.5)
        & (src_y >= -0.5)
        & (src_y <= ny_in - 0.5)
    )

    aligned_mask = (aligned_mask_float >= 0.5) & in_bounds & np.isfinite(aligned_img)
    aligned_img[~aligned_mask] = np.nan
    return aligned_img, aligned_mask


def reproject_to_grid(
    obs: Observation,
    target_wcs: WCS,
    shape_out: tuple[int, int] | None = None,
    use_library: str = "auto",
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Reproject an Observation's science image and usability mask onto target WCS.

    Preserves masked pixels and marks unobserved / out-of-bounds pixels as invalid.

    Algorithm Choice:
    - Defaults to astropy's official `reproject.reproject_interp` when installed,
      which provides flux-interpolated spherical astrometric mapping.
    - Seamlessly falls back to `scipy.ndimage.map_coordinates` combined with
      astropy WCS coordinate transformations if `reproject` is absent.

    Args:
        obs: Source Observation dataclass.
        target_wcs: Destination celestial WCS grid.
        shape_out: Desired (ny, nx) shape. If None, derived from target_wcs.array_shape
            or defaults to (256, 256).
        use_library: 'auto' (prefer reproject, fallback scipy), 'reproject', or 'scipy'.

    Returns:
        tuple[np.ndarray, np.ndarray, list[str]]:
            - aligned_image: 2D float64 array of shape shape_out (invalid pixels set to NaN).
            - aligned_mask: 2D boolean array of shape shape_out (True = valid, False = unusable).
            - warnings: List of warning strings regarding coverage, interpolation, or boundary clipping.

    Raises:
        ValueError: If target_wcs is not celestial or shape_out cannot be determined.
    """
    warnings: list[str] = list(obs.warnings)

    if not target_wcs.is_celestial:
        raise ValueError("target_wcs must be a valid 2D celestial WCS.")

    # Determine output dimensions
    if shape_out is None:
        if getattr(target_wcs, "array_shape", None) is not None:
            shape_out = target_wcs.array_shape
        elif getattr(target_wcs, "pixel_shape", None) is not None:
            nx, ny = target_wcs.pixel_shape
            shape_out = (ny, nx)
        else:
            shape_out = (256, 256)

    # Generate source valid mask
    src_valid_mask = build_valid_mask(obs.flags, obs.image.shape)
    src_valid_mask &= np.isfinite(obs.image)

    # Choose reprojection engine
    prefer_reproject = (use_library == "reproject") or (use_library == "auto" and _HAS_REPROJECT)

    if prefer_reproject and _HAS_REPROJECT:
        # Reproject science image with flux-conserving bilinear interpolation
        with py_warnings.catch_warnings():
            py_warnings.simplefilter("ignore")
            aligned_img, footprint = reproject_interp(
                (obs.image, obs.wcs),
                target_wcs,
                shape_out=shape_out,
                order="bilinear",
            )
            # Reproject valid mask with nearest-neighbor to prevent blending bad flags
            aligned_valid_float, _ = reproject_interp(
                (src_valid_mask.astype(np.float32), obs.wcs),
                target_wcs,
                shape_out=shape_out,
                order="nearest-neighbor",
            )

        in_coverage = (footprint > 0.0) & np.isfinite(aligned_img)
        aligned_mask = in_coverage & (aligned_valid_float >= 0.5)
        aligned_img[~aligned_mask] = np.nan
    else:
        if use_library == "reproject" and not _HAS_REPROJECT:
            warnings.append("reproject library requested but not installed; falling back to scipy.")
        aligned_img, aligned_mask = _reproject_with_scipy(
            obs.image,
            src_valid_mask,
            obs.wcs,
            target_wcs,
            shape_out=shape_out,
        )

    # Coverage verification and warnings (Hard Rule 4)
    total_pixels = shape_out[0] * shape_out[1]
    valid_pixels = int(np.count_nonzero(aligned_mask))
    coverage_pct = (valid_pixels / total_pixels) * 100.0

    if valid_pixels == 0:
        warnings.append("Zero valid overlap between source observation and target WCS grid.")
    elif coverage_pct < 99.0:
        warnings.append(
            f"Partial coverage: source observation covers {coverage_pct:.1f}% of the target grid."
        )

    return aligned_img, aligned_mask, warnings
