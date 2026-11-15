"""Wavelength and instrument compatibility checking for SPHEREx WhyLab.

Evaluates whether multiple SPHEREx observations are observing at compatible
wavelengths. If wavelengths differ significantly, differencing or visual
comparison will suffer from chromatic artifacts due to differing astronomical SEDs.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from backend.processing.io_fits import Observation


def _get_effective_wavelength(
    obs: Observation,
    target_coord: tuple[float, float] | None = None,
) -> float | None:
    """Extract a scalar effective wavelength (in um) from an Observation."""
    if obs.wavelength_um is None:
        return None

    if isinstance(obs.wavelength_um, (int, float, np.number)):
        value = float(obs.wavelength_um)
        return value if np.isfinite(value) and value > 0 else None

    if isinstance(obs.wavelength_um, np.ndarray):
        if obs.wavelength_um.ndim != 2:
            return None
        # 2D CWAVE map: sample at target_coord or central pixel
        if target_coord is not None:
            ra, dec = target_coord
            try:
                x, y = obs.wcs.world_to_pixel_values(ra, dec)
                ix, iy = int(round(float(x))), int(round(float(y)))
                ny, nx = obs.wavelength_um.shape
                if 0 <= ix < nx and 0 <= iy < ny:
                    val = float(obs.wavelength_um[iy, ix])
                    if np.isfinite(val) and val > 0:
                        return val
            except Exception:
                pass
            # A different position's wavelength cannot replace the requested one.
            return None

        # Fallback to center pixel of map
        ny, nx = obs.wavelength_um.shape
        cy, cx = ny // 2, nx // 2
        val = float(obs.wavelength_um[cy, cx])
        if np.isfinite(val) and val > 0:
            return val
        # Fallback to median finite value
        finite_vals = obs.wavelength_um[np.isfinite(obs.wavelength_um) & (obs.wavelength_um > 0)]
        if finite_vals.size > 0:
            return float(np.median(finite_vals))

    return None


def check_wavelength_compatibility(
    obs_list: Sequence[Observation],
    tolerance_fraction: float = 0.15,
    target_coord: tuple[float, float] | None = None,
) -> dict[str, Any]:
    """Check whether a list of observations are spectral/wavelength compatible.

    Rules:
    - If any observation has missing wavelength metadata, status must be 'unknown'
      (Hard Rule 3 & requirement).
    - If all observations have known wavelengths:
        - If max fractional difference <= tolerance_fraction: 'compatible'.
        - If max fractional difference > tolerance_fraction: 'incompatible'.
    - If detectors are known and differ (e.g. Detector 1 vs Detector 3),
      records explanatory warnings for Person 4 and frontend.

    Args:
        obs_list: Sequence of Observation objects to compare.
        tolerance_fraction: Maximum fractional wavelength difference
            (|lambda_max - lambda_min| / lambda_mean) considered compatible (default 15%).
        target_coord: Optional (ra_deg, dec_deg) coordinate to sample spatially
            varying Linear Variable Filter (CWAVE) maps at the source location.

    Returns:
        dict[str, Any]: Dictionary matching API comparison specification:
            {
                "status": "compatible" | "incompatible" | "unknown",
                "wavelengths_um": list[float | None],
                "detector_bands": list[int | str | None],
                "warnings": list[str],
            }
    """
    warnings: list[str] = []
    if not np.isfinite(tolerance_fraction) or tolerance_fraction < 0:
        raise ValueError("Wavelength tolerance must be finite and nonnegative")

    if not obs_list:
        warnings.append("No observations provided for compatibility check.")
        return {
            "status": "unknown",
            "wavelengths_um": [],
            "detector_bands": [],
            "warnings": warnings,
        }

    wavelengths: list[float | None] = []
    detectors: list[int | str | None] = []

    for idx, obs in enumerate(obs_list):
        eff_wave = _get_effective_wavelength(obs, target_coord=target_coord)
        wavelengths.append(eff_wave)
        detectors.append(obs.detector)
        if eff_wave is None:
            warnings.append(
                f"Observation {idx} (detector={obs.detector}) has no wavelength metadata."
            )

    # Hard Rule: If wavelength metadata is missing, status MUST be "unknown"
    if any(w is None for w in wavelengths):
        warnings.append(
            "Wavelength metadata is missing or incomplete for one or more frames; "
            "compatibility status cannot be scientifically verified."
        )
        return {
            "status": "unknown",
            "wavelengths_um": wavelengths,
            "detector_bands": detectors,
            "warnings": warnings,
        }

    # All wavelengths are valid floats
    valid_waves = [w for w in wavelengths if w is not None]
    min_wave = min(valid_waves)
    max_wave = max(valid_waves)
    mean_wave = sum(valid_waves) / len(valid_waves)

    frac_diff = (max_wave - min_wave) / mean_wave if mean_wave > 0 else 0.0

    # Check detector consistency
    known_detectors = {d for d in detectors if d is not None}
    if len(known_detectors) > 1:
        warnings.append(
            f"Frames come from different detectors: {sorted(known_detectors, key=str)}. "
            "PSF characteristics and detector responses may vary."
        )

    if frac_diff <= tolerance_fraction:
        status = "compatible"
    else:
        status = "incompatible"
        warnings.append(
            f"Wavelength disparity is {frac_diff * 100:.1f}% "
            f"(range {min_wave:.3f} - {max_wave:.3f} um), exceeding the {tolerance_fraction * 100:.1f}% threshold. "
            "Image subtraction will exhibit strong chromatic artifacts."
        )

    return {
        "status": status,
        "wavelengths_um": wavelengths,
        "detector_bands": detectors,
        "warnings": warnings,
    }
