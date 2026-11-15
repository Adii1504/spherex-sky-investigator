"""Position measurement and centroiding for SPHEREx WhyLab.

Measures source positions around a user-selected sky coordinate using
local background subtraction and 2D Gaussian / centroid fitting.
Derives formal astrometric uncertainty and SNR, strictly returning None
if uncertainty cannot be estimated reliably (Hard Rule 3).
"""

from __future__ import annotations

import math
import warnings as py_warnings
from typing import Any, Sequence

from astropy.wcs import WCS
import numpy as np
from scipy.ndimage import maximum_filter
from scipy.optimize import curve_fit

from backend.processing.io_fits import Observation, build_valid_mask


def _gaussian_2d(
    coords: tuple[np.ndarray, np.ndarray],
    amplitude: float,
    x0: float,
    y0: float,
    sigma: float,
    offset: float,
) -> np.ndarray:
    """Circular 2D Gaussian model for point sources."""
    y, x = coords
    g = offset + amplitude * np.exp(
        -((x - x0) ** 2 + (y - y0) ** 2) / (2.0 * max(sigma, 1e-4) ** 2)
    )
    return g.ravel()


def measure_position(
    aligned_image: np.ndarray,
    mask: np.ndarray,
    wcs: WCS,
    ra_deg: float,
    dec_deg: float,
    search_radius_px: float = 5.0,
    snr_threshold: float = 3.0,
) -> dict[str, Any]:
    """Measure the precise position of a source around given celestial coordinates.

    Uses background subtraction and a 2D Gaussian fit within search_radius_px.
    If the Gaussian fit fails or covariance is singular, falls back to a flux-weighted
    centroid and sets uncertainty_arcsec to None (never fabricated).

    Args:
        aligned_image: 2D float flux array (North up, East left).
        mask: 2D boolean mask (True = usable).
        wcs: Celestial 2D WCS of aligned_image.
        ra_deg: Initial Right Ascension guess in degrees.
        dec_deg: Initial Declination guess in degrees.
        search_radius_px: Search radius in pixels around initial guess (default 5.0).
        snr_threshold: Minimum peak SNR for reliable detection (default 3.0).

    Returns:
        dict[str, Any]:
            {
                "ra_deg": float,
                "dec_deg": float,
                "uncertainty_arcsec": float | None,
                "snr": float | None,
                "status": "ok" | "low_snr" | "masked" | "failed",
                "warnings": list[str]
            }
    """
    warnings: list[str] = []

    # 1. Translate sky coordinates to pixel coordinates
    try:
        x_init, y_init = wcs.world_to_pixel_values(float(ra_deg), float(dec_deg))
        x0 = float(x_init)
        y0 = float(y_init)
    except Exception as e:
        warnings.append(f"Failed to project sky coordinates to pixel space: {e}")
        return {
            "ra_deg": float(ra_deg),
            "dec_deg": float(dec_deg),
            "uncertainty_arcsec": None,
            "snr": None,
            "status": "failed",
            "warnings": warnings,
        }

    ny, nx = aligned_image.shape

    # 2. Check bounds
    if not (-.5 <= x0 <= nx-.5 and -.5 <= y0 <= ny-.5):
        warnings.append(
            f"Target position ({ra_deg:.5f}, {dec_deg:.5f}) falls outside image bounds: px=({x0:.1f}, {y0:.1f})."
        )
        return {
            "ra_deg": float(ra_deg),
            "dec_deg": float(dec_deg),
            "uncertainty_arcsec": None,
            "snr": None,
            "status": "failed",
            "warnings": warnings,
        }

    ix0, iy0 = min(nx-1, int(round(x0))), min(ny-1, int(round(y0)))
    if not mask[iy0, ix0] or not np.isfinite(aligned_image[iy0, ix0]):
        # Check if this is a saturated core with strong surrounding flux within search radius
        r_chk = int(np.ceil(search_radius_px))
        xm0 = max(0, int(np.floor(x0 - r_chk)))
        xm1 = min(nx, int(np.ceil(x0 + r_chk + 1)))
        ym0 = max(0, int(np.floor(y0 - r_chk)))
        ym1 = min(ny, int(np.ceil(y0 + r_chk + 1)))
        sub_chk = aligned_image[ym0:ym1, xm0:xm1]
        msk_chk = mask[ym0:ym1, xm0:xm1] & np.isfinite(sub_chk)

        has_prominent_source = False
        msk_finite = msk_chk & np.isfinite(sub_chk)
        if np.count_nonzero(msk_finite) >= 4:
            valid_pts = sub_chk[msk_finite]
            med_val = float(np.median(valid_pts))
            mad_val = float(np.median(np.abs(valid_pts - med_val))) * 1.4826
            if mad_val > 0 and (float(np.max(valid_pts)) - med_val) > 5.0 * mad_val:
                has_prominent_source = True

        if not has_prominent_source:
            warnings.append("Target pixel is masked or non-finite.")
            return {
                "ra_deg": float(ra_deg),
                "dec_deg": float(dec_deg),
                "uncertainty_arcsec": None,
                "snr": None,
                "status": "masked",
                "warnings": warnings,
            }
        warnings.append("Target central pixel is saturated/masked; centroiding from PSF wings.")

    # 3. Extract sub-region bounding box
    r = int(np.ceil(search_radius_px))
    x_min = max(0, int(np.floor(x0 - r)))
    x_max = min(nx, int(np.ceil(x0 + r + 1)))
    y_min = max(0, int(np.floor(y0 - r)))
    y_max = min(ny, int(np.ceil(y0 + r + 1)))

    sub_img = aligned_image[y_min:y_max, x_min:x_max]
    sub_mask = mask[y_min:y_max, x_min:x_max] & np.isfinite(sub_img)

    if np.count_nonzero(sub_mask) < 4:
        warnings.append("Fewer than 4 unmasked pixels in search region.")
        return {
            "ra_deg": float(ra_deg),
            "dec_deg": float(dec_deg),
            "uncertainty_arcsec": None,
            "snr": None,
            "status": "masked",
            "warnings": warnings,
        }

    # 4. Local background and noise estimation (Median & MAD)
    valid_sub_pixels = sub_img[sub_mask]
    bg = float(np.median(valid_sub_pixels))
    mad = float(np.median(np.abs(valid_sub_pixels - bg)))
    sigma_bg = 1.4826 * mad
    if sigma_bg <= 0.0 or not np.isfinite(sigma_bg):
        std_val = float(np.std(valid_sub_pixels))
        sigma_bg = std_val if std_val > 0.0 else 1e-6

    # Distance grid from initial position
    yy_sub, xx_sub = np.indices(sub_img.shape)
    xx_global = xx_sub + x_min
    yy_global = yy_sub + y_min
    dist = np.hypot(xx_global - x0, yy_global - y0)
    in_circle = (dist <= search_radius_px) & sub_mask

    if not np.any(in_circle):
        warnings.append("No valid pixels within specified search radius.")
        return {
            "ra_deg": float(ra_deg),
            "dec_deg": float(dec_deg),
            "uncertainty_arcsec": None,
            "snr": None,
            "status": "masked",
            "warnings": warnings,
        }

    # 5. Peak signal-to-noise ratio
    net_flux = sub_img - bg
    circle_net = np.where(in_circle, net_flux, -np.inf)
    peak_y_sub, peak_x_sub = np.unravel_index(np.argmax(circle_net), sub_img.shape)
    peak_flux = float(circle_net[peak_y_sub, peak_x_sub])

    snr = float(peak_flux / sigma_bg) if sigma_bg > 0 else None

    if snr is None or snr < snr_threshold:
        warnings.append(
            f"Peak SNR ({f'{snr:.2f}' if snr is not None else 'N/A'}) is below threshold ({snr_threshold})."
        )
        return {
            "ra_deg": float(ra_deg),
            "dec_deg": float(dec_deg),
            "uncertainty_arcsec": None,
            "snr": snr,
            "status": "low_snr",
            "warnings": warnings,
        }

    # 6. Fit position (2D Gaussian with Levenberg-Marquardt)
    pixel_scale_arcsec = float(np.mean([
        s.to_value("arcsec") for s in wcs.proj_plane_pixel_scales()
    ]))

    peak_x_global = float(peak_x_sub + x_min)
    peak_y_global = float(peak_y_sub + y_min)

    fit_success = False
    refined_x = peak_x_global
    refined_y = peak_y_global
    uncertainty_arcsec: float | None = None

    # Initial parameters: amplitude, x0, y0, sigma (px), offset
    p0 = [peak_flux, peak_x_global, peak_y_global, 1.5, bg]
    lower_bounds = [0.0, x_min, y_min, 0.5, -np.inf]
    upper_bounds = [np.inf, x_max, y_max, search_radius_px * 2.0, np.inf]

    coords_fit = (yy_global[sub_mask], xx_global[sub_mask])
    data_fit = sub_img[sub_mask].astype(np.float64)

    try:
        with py_warnings.catch_warnings():
            py_warnings.simplefilter("ignore")
            popt, pcov = curve_fit(
                _gaussian_2d,
                coords_fit,
                data_fit,
                p0=p0,
                bounds=(lower_bounds, upper_bounds),
                maxfev=500,
            )

        amp_fit, fx, fy, fsigma, foff = popt
        var_x = pcov[1, 1]
        var_y = pcov[2, 2]

        # Ensure covariance values are positive, finite, and within reasonable range
        if (
            np.isfinite(var_x)
            and np.isfinite(var_y)
            and var_x > 0.0
            and var_y > 0.0
            and np.hypot(fx - x0, fy - y0) <= search_radius_px * 1.5
        ):
            refined_x = float(fx)
            refined_y = float(fy)
            sigma_px = float(np.sqrt(var_x + var_y))
            uncertainty_arcsec = sigma_px * pixel_scale_arcsec
            fit_success = True
    except Exception:
        fit_success = False

    # Fallback to flux-weighted centroid if Gaussian fit fails
    if not fit_success:
        weights = np.maximum(net_flux, 0.0) * in_circle
        sum_w = float(np.sum(weights))
        if sum_w > 0.0:
            refined_x = float(np.sum(weights * xx_global) / sum_w)
            refined_y = float(np.sum(weights * yy_global) / sum_w)
            # Per Hard Rule 3: Do not invent numbers if uncertainty cannot be reliably calculated
            uncertainty_arcsec = None
            warnings.append(
                "2D Gaussian fit did not converge cleanly; fell back to flux-weighted centroid. "
                "Uncertainty set to None."
            )
        else:
            refined_x = peak_x_global
            refined_y = peak_y_global
            uncertainty_arcsec = None
            warnings.append("Centroid weighting zero; used peak pixel position with uncertainty None.")

    # 7. Convert measured pixel coordinates back to celestial coordinates
    ra_refined, dec_refined = wcs.pixel_to_world_values(refined_x, refined_y)

    return {
        "ra_deg": float(ra_refined),
        "dec_deg": float(dec_refined),
        "uncertainty_arcsec": uncertainty_arcsec,
        "snr": snr,
        "status": "ok",
        "warnings": warnings,
    }


def detect_sources(
    aligned_image: np.ndarray,
    mask: np.ndarray,
    wcs: WCS,
    snr_threshold: float = 3.5,
    min_separation_px: int = 3,
    max_sources: int = 50,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Scan the entire image field and detect all candidate astronomical point sources.

    Powers the ViewSpace-style interactive hotspots/pins by discovering all sources
    in the field with their precise centroids, SNR, fluxes, and sky coordinates.

    Uses a local maximum filter to locate peaks, subtracts the global robust background
    (median + MAD noise), and performs sub-pixel centroid refinement on each candidate.

    Args:
        aligned_image: 2D float flux array (North up, East left).
        mask: 2D boolean mask (True = usable).
        wcs: Celestial 2D WCS.
        snr_threshold: Minimum peak SNR for detection (default 3.5).
        min_separation_px: Minimum distance between adjacent detected peaks (default 3).
        max_sources: Maximum number of sources to return, sorted by SNR descending (default 50).

    Returns:
        tuple[list[dict[str, Any]], list[str]]:
            - sources: List of source dictionaries formatted for frontend hotspot pins.
            - warnings: List of warning strings.
    """
    warnings: list[str] = []
    ny, nx = aligned_image.shape

    usable_pixels = mask & np.isfinite(aligned_image)
    if np.count_nonzero(usable_pixels) < 16:
        warnings.append("Insufficient valid pixels in image to perform source detection.")
        return [], warnings

    valid_vals = aligned_image[usable_pixels]
    bg = float(np.median(valid_vals))
    mad = float(np.median(np.abs(valid_vals - bg)))
    sigma_bg = 1.4826 * mad
    if sigma_bg <= 0.0 or not np.isfinite(sigma_bg):
        std_val = float(np.std(valid_vals))
        sigma_bg = std_val if std_val > 0.0 else 1e-6

    net_image = np.where(usable_pixels, aligned_image - bg, -np.inf)

    # Find local maxima using maximum filter with footprint (2*min_sep + 1)
    size = max(3, 2 * min_separation_px + 1)
    local_max = maximum_filter(net_image, size=size, mode="constant", cval=-np.inf)
    is_peak = (net_image == local_max) & (net_image >= snr_threshold * sigma_bg) & usable_pixels

    # Avoid detection directly on boundary edges
    margin = 2
    is_peak[:margin, :] = False
    is_peak[-margin:, :] = False
    is_peak[:, :margin] = False
    is_peak[:, -margin:] = False

    peak_indices = np.argwhere(is_peak)  # list of (y, x)
    if len(peak_indices) == 0:
        warnings.append(f"No sources detected above SNR threshold {snr_threshold}.")
        return [], warnings

    # Sort peaks by net flux descending
    peak_fluxes = [net_image[y, x] for y, x in peak_indices]
    sorted_order = np.argsort(peak_fluxes)[::-1][:max_sources]
    selected_peaks = [peak_indices[i] for i in sorted_order]

    detected_sources: list[dict[str, Any]] = []
    for idx, (py, px) in enumerate(selected_peaks):
        # Local sub-pixel centroiding in 3x3 patch
        y_min = max(0, py - 1)
        y_max = min(ny, py + 2)
        x_min = max(0, px - 1)
        x_max = min(nx, px + 2)

        patch_net = np.maximum(net_image[y_min:y_max, x_min:x_max], 0.0)
        yy_p, xx_p = np.indices(patch_net.shape)
        sum_w = float(np.sum(patch_net))
        if sum_w > 0.0:
            sub_x = float(np.sum(patch_net * (xx_p + x_min)) / sum_w)
            sub_y = float(np.sum(patch_net * (yy_p + y_min)) / sum_w)
        else:
            sub_x, sub_y = float(px), float(py)

        ra_src, dec_src = wcs.pixel_to_world_values(sub_x, sub_y)
        peak_val = float(aligned_image[py, px])
        net_val = float(net_image[py, px])
        snr_val = float(net_val / sigma_bg)

        # Estimate centroid uncertainty from SNR and pixel scale
        pixel_scales = [s.to_value("arcsec") for s in wcs.proj_plane_pixel_scales()]
        scale_arcsec = float(np.mean(pixel_scales))
        uncert_arcsec = float(scale_arcsec / max(snr_val, 1.0))

        detected_sources.append({
            "id": f"src_{idx + 1:03d}",
            "x_px": round(sub_x, 2),
            "y_px": round(sub_y, 2),
            "ra_deg": float(ra_src),
            "dec_deg": float(dec_src),
            "peak_flux": round(peak_val, 4),
            "net_flux": round(net_val, 4),
            "snr": round(snr_val, 2),
            "uncertainty_arcsec": round(uncert_arcsec, 3),
            "status": "ok",
        })

    return detected_sources, warnings


def extract_sed(
    ra_deg: float,
    dec_deg: float,
    observations: Sequence[Observation],
    search_radius_px: float = 4.0,
) -> dict[str, Any]:
    """Extract multi-wavelength spectral energy distribution (SED) at a target coordinate.

    Directly powers the ViewSpace interactive detail drawer: when the user clicks
    a hotspot pin, this function returns its photometry across all available SPHEREx
    bands (e.g. Detectors 1 through 6, 0.75 - 5.0 um).

    Args:
        ra_deg: Right Ascension of the hotspot in degrees.
        dec_deg: Declination of the hotspot in degrees.
        observations: Sequence of Observations across different bands/detectors.
        search_radius_px: Measurement aperture radius in pixels.

    Returns:
        dict[str, Any]:
            {
                "ra_deg": float,
                "dec_deg": float,
                "sed_points": [
                    {
                        "detector": int | str | None,
                        "wavelength_um": float | None,
                        "flux": float | None,
                        "snr": float | None,
                        "status": "ok" | "low_snr" | "masked" | "failed"
                    }, ...
                ],
                "spectral_index": float | None,
                "warnings": list[str]
            }
    """
    warnings: list[str] = []
    sed_points: list[dict[str, Any]] = []

    for obs in observations:
        mask = build_valid_mask(obs.flags, obs.image.shape)
        meas = measure_position(
            aligned_image=obs.image,
            mask=mask,
            wcs=obs.wcs,
            ra_deg=ra_deg,
            dec_deg=dec_deg,
            search_radius_px=search_radius_px,
        )

        eff_wave = None
        if isinstance(obs.wavelength_um, (int, float)):
            eff_wave = float(obs.wavelength_um)
        elif isinstance(obs.wavelength_um, np.ndarray):
            try:
                x, y = obs.wcs.world_to_pixel_values(ra_deg, dec_deg)
                ix, iy = int(round(float(x))), int(round(float(y)))
                if 0 <= ix < obs.wavelength_um.shape[1] and 0 <= iy < obs.wavelength_um.shape[0]:
                    eff_wave = float(obs.wavelength_um[iy, ix])
            except Exception:
                pass

        peak_flux = None
        if meas["status"] == "ok":
            try:
                x, y = obs.wcs.world_to_pixel_values(meas["ra_deg"], meas["dec_deg"])
                ix, iy = int(round(float(x))), int(round(float(y)))
                if 0 <= ix < obs.image.shape[1] and 0 <= iy < obs.image.shape[0]:
                    peak_flux = float(obs.image[iy, ix])
            except Exception:
                pass

        sed_points.append({
            "detector": obs.detector,
            "wavelength_um": eff_wave,
            "flux": peak_flux,
            "snr": meas["snr"],
            "status": meas["status"],
        })

    # Sort sed points by wavelength if available
    valid_wave_points = [p for p in sed_points if p["wavelength_um"] is not None]
    if len(valid_wave_points) >= 2:
        sed_points.sort(key=lambda p: (p["wavelength_um"] is None, p["wavelength_um"]))

    # Fit simple spectral index alpha (Flux ~ lambda^alpha) if >= 3 valid points
    spectral_index = None
    flux_fit_pts = [p for p in sed_points if p["status"] == "ok" and p["flux"] is not None and p["flux"] > 0 and p["wavelength_um"] is not None]
    if len(flux_fit_pts) >= 3:
        try:
            log_lam = np.log([p["wavelength_um"] for p in flux_fit_pts])
            log_flux = np.log([p["flux"] for p in flux_fit_pts])
            fit = np.polyfit(log_lam, log_flux, deg=1)
            spectral_index = round(float(fit[0]), 3)
        except Exception:
            pass

    return {
        "ra_deg": float(ra_deg),
        "dec_deg": float(dec_deg),
        "sed_points": sed_points,
        "spectral_index": spectral_index,
        "warnings": warnings,
    }

