"""End-to-end investigation pipeline orchestrator for SPHEREx WhyLab.

Designed specifically for Person 4 (FastAPI) and Person 3 (React UI).
Ties together ingestion, alignment, shared stretching, differencing,
automated source discovery, blinking animations, and hypothesis verification
in a single, robust function call.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, BinaryIO, Sequence

from astropy.wcs import WCS
import numpy as np

from backend.processing.alignment import make_common_grid, reproject_to_grid
from backend.processing.compatibility import check_wavelength_compatibility
from backend.processing.display import (
    compute_shared_stretch,
    generate_blink_animation,
    make_difference,
    render_preview_png,
)
from backend.processing.io_fits import Observation, load_observation
from backend.processing.measure import detect_sources, measure_position
from backend.processing.motion import _sky_separation_arcsec, scan_and_track_motion, test_motion


def run_investigation_pipeline(
    fits_inputs: Sequence[str | Path | io.BytesIO | BinaryIO | Observation],
    target_coord: tuple[float, float] | None = None,
    investigation_id: str = "SPX_INV_001",
    fov_arcmin: float = 2.5,
    grid_size_px: int = 128,
    output_dir: str | Path = "previews",
    base_url_prefix: str = "",
) -> dict[str, Any]:
    """Execute the full SPHEREx WhyLab processing pipeline on a sequence of frames.

    Args:
        fits_inputs: Sequence of FITS paths, BytesIO streams, or Observation objects.
        target_coord: Optional (ra_deg, dec_deg) of suspected moving object clicked by user.
        investigation_id: Unique identifier for this investigation session.
        fov_arcmin: Field of view in arcminutes for the standardized grid (default 2.5).
        grid_size_px: Pixel dimension of the aligned grid (default 128).
        output_dir: Destination folder for output PNG previews, difference images, and blink GIFs.
        base_url_prefix: Optional URL prefix to prepend to image asset paths for frontend delivery.

    Returns:
        dict[str, Any]: Complete API response matching Person 4 and Person 3 contracts:
            {
                "investigation_id": str,
                "outcome": str,
                "frames": list[dict],
                "differences": list[dict],
                "blink_animation_url": str | None,
                "comparison": dict,
                "measurements": list[dict],
                "predictions": list[dict],
                "model_comparison": dict | None,
                "hotspots": list[dict],
                "limitations": list[str],
                "warnings": list[str]
            }
    """
    warnings: list[str] = []
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def _format_url(p: Path | None) -> str | None:
        if p is None:
            return None
        rel_path = str(p.relative_to(out_dir) if out_dir in p.parents else p.name).replace("\\", "/")
        return f"{base_url_prefix.rstrip('/')}/{rel_path}" if base_url_prefix else rel_path

    # 1. Load observations
    observations: list[Observation] = []
    for idx, inp in enumerate(fits_inputs):
        if isinstance(inp, Observation):
            observations.append(inp)
        else:
            try:
                obs = load_observation(inp)
                observations.append(obs)
            except Exception as e:
                warnings.append(f"Failed to load frame {idx}: {e}")

    if len(observations) == 0:
        return {
            "investigation_id": investigation_id,
            "outcome": "insufficient_evidence",
            "frames": [],
            "differences": [],
            "blink_animation_url": None,
            "comparison": {"status": "unknown", "warnings": ["No valid observations loaded."]},
            "measurements": [],
            "predictions": [],
            "model_comparison": None,
            "hotspots": [],
            "limitations": [],
            "warnings": warnings + ["Pipeline aborted: zero valid observations."],
        }

    # 2. Check wavelength compatibility
    for index, observation in enumerate(observations):
        warnings.extend(f"Frame {index+1}: {warning}" for warning in observation.warnings)
    compat_result = check_wavelength_compatibility(observations, target_coord=target_coord)
    warnings.extend(compat_result.get("warnings", []))

    # 3. Determine target celestial center
    if target_coord is not None:
        center_ra, center_dec = float(target_coord[0]), float(target_coord[1])
    else:
        # Fall back to center of first observation
        ny0, nx0 = observations[0].image.shape
        c_ra, c_dec = observations[0].wcs.pixel_to_world_values((nx0 - 1) / 2.0, (ny0 - 1) / 2.0)
        center_ra, center_dec = float(c_ra), float(c_dec)

    target_wcs = make_common_grid(
        ra_deg=center_ra,
        dec_deg=center_dec,
        fov_arcmin=fov_arcmin,
        size_px=grid_size_px,
    )

    # 4. Reproject all frames to common grid
    aligned_images: list[np.ndarray] = []
    aligned_masks: list[np.ndarray] = []
    for idx, obs in enumerate(observations):
        img_al, mask_al, rep_warn = reproject_to_grid(obs, target_wcs, shape_out=(grid_size_px, grid_size_px))
        aligned_images.append(img_al)
        aligned_masks.append(mask_al)
        warnings.extend([f"Frame {idx}: {w}" for w in rep_warn])

    # 5. Shared intensity stretch across all frames (Hard Rule 6)
    stretch = compute_shared_stretch(aligned_images, aligned_masks)

    # 6. Render preview PNGs for each frame
    frame_objs: list[dict[str, Any]] = []
    frame_labels: list[str] = []
    for idx, (obs, img_al, mask_al) in enumerate(zip(observations, aligned_images, aligned_masks)):
        obs_id = obs.header_meta.get("OBS_ID", f"obs_{idx + 1:02d}")
        png_path = out_dir / f"{investigation_id}_frame_{idx + 1:02d}.png"
        render_preview_png(img_al, mask_al, stretch, png_path)

        t_utc = obs.observed_at_utc or f"Epoch {idx + 1}"
        frame_labels.append(t_utc.split("T")[-1] if "T" in t_utc else t_utc)

        eff_wave = compat_result["wavelengths_um"][idx] if idx < len(compat_result["wavelengths_um"]) else None
        frame_objs.append({
            "observation_id": obs_id,
            "epoch_index": idx,
            "observed_at": obs.observed_at_utc,
            "image_url": _format_url(png_path),
            "target_wavelength_um": eff_wave,
            "detector": obs.detector,
            "warnings": list(obs.warnings),
        })

    # 7. Compute difference images between successive frames (Hard Rule 5)
    difference_objs: list[dict[str, Any]] = []
    for idx in range(len(aligned_images) - 1):
        diff_png = out_dir / f"{investigation_id}_diff_{idx + 1}_to_{idx + 2}.png"
        diff_arr, val_msk, _, diff_warn = make_difference(
            a=aligned_images[idx],
            b=aligned_images[idx + 1],
            mask_a=aligned_masks[idx],
            mask_b=aligned_masks[idx + 1],
            out_png_path=diff_png,
        )
        difference_objs.append({
            "a_observation_id": frame_objs[idx]["observation_id"],
            "b_observation_id": frame_objs[idx + 1]["observation_id"],
            "image_url": _format_url(diff_png),
            "interpretation": f"Epoch {idx + 2} minus Epoch {idx + 1}; exploratory comparison",
            "warnings": diff_warn,
        })

    # 8. Generate animated Blink GIF
    blink_url: str | None = None
    if len(aligned_images) >= 2:
        blink_path = out_dir / f"{investigation_id}_blink.gif"
        generate_blink_animation(
            aligned_images,
            aligned_masks,
            stretch,
            out_path=blink_path,
            fps=2.0,
            labels=frame_labels,
        )
        blink_url = _format_url(blink_path)

    # 9. Automated field hotspot discovery
    hotspots_scan = scan_and_track_motion(observations, snr_threshold=3.5)
    for hotspot in hotspots_scan.get("hotspots", []):
        x, y = target_wcs.world_to_pixel_values(hotspot["ra_deg"], hotspot["dec_deg"])
        hotspot["x_px"], hotspot["y_px"] = float(x), float(y)

    # 10. Motion testing on user-selected target coordinate (or brightest moving candidate)
    verification_result: dict[str, Any] = {
        "outcome": "insufficient_evidence",
        "measurements": [],
        "predictions": [],
        "model_comparison": None,
        "limitations": [
            "Linear constant motion assumes no significant orbital curvature or acceleration over baseline.",
            "Precision constrained by SPHEREx ~6.2 arcsec native pixel scale.",
        ],
    }

    if target_coord is not None:
        target_ra, target_dec = float(target_coord[0]), float(target_coord[1])
        # Check if target coordinate matches an automatically tracked hotspot
        matched_hotspot = None
        min_sep = np.inf
        for h in hotspots_scan.get("hotspots", []):
            sep = _sky_separation_arcsec(target_ra, target_dec, h["ra_deg"], h["dec_deg"])
            if sep <= 15.0 and sep < min_sep:
                min_sep = sep
                matched_hotspot = h

        if matched_hotspot and matched_hotspot.get("verification"):
            verification_result = matched_hotspot["verification"]
        else:
            target_meas_list: list[dict[str, Any]] = []
            curr_ra, curr_dec = target_ra, target_dec
            px_scale = (fov_arcmin * 60.0) / float(grid_size_px)
            search_r_px = max(5.0, 15.0 / px_scale)
            for idx, (obs, img_al, mask_al) in enumerate(zip(observations, aligned_images, aligned_masks)):
                meas = measure_position(
                    aligned_image=img_al,
                    mask=mask_al,
                    wcs=target_wcs,
                    ra_deg=curr_ra,
                    dec_deg=curr_dec,
                    search_radius_px=search_r_px,
                )
                if meas["status"] == "ok":
                    curr_ra, curr_dec = meas["ra_deg"], meas["dec_deg"]
                target_meas_list.append({
                    "epoch_id": frame_objs[idx]["observation_id"],
                    "observed_at_utc": obs.observed_at_utc,
                    "ra_deg": meas["ra_deg"],
                    "dec_deg": meas["dec_deg"],
                    "uncertainty_arcsec": meas["uncertainty_arcsec"],
                    "snr": meas["snr"],
                    "status": meas["status"],
                })

            if len(target_meas_list) >= 3:
                training = target_meas_list[:-1]
                reserved = target_meas_list[-1]
                verification_result = test_motion(training, reserved, investigation_id=investigation_id)
            elif len(target_meas_list) >= 2:
                warnings.append("Only 2 epochs available; minimum 3 required for reserved evaluation (Hard Rule 8).")
                verification_result["measurements"] = target_meas_list
    elif hotspots_scan["hotspots"]:
        # Check if any moving candidate was detected by automated scan
        moving_cands = [h for h in hotspots_scan["hotspots"] if h["classification"] == "moving_candidate" and h.get("verification")]
        if moving_cands:
            verification_result = moving_cands[0]["verification"]

    if compat_result["status"] != "compatible":
        verification_result["outcome"] = "insufficient_evidence"
        warnings.append("Motion interpretation is exploratory: wavelengths are unknown or incompatible; no verified source motion is asserted.")
    warnings.extend(verification_result.get("warnings", []))
    return {
        "investigation_id": investigation_id,
        "outcome": verification_result.get("outcome", "insufficient_evidence"),
        "frames": frame_objs,
        "differences": difference_objs,
        "blink_animation_url": blink_url,
        "comparison": {
            "status": compat_result["status"],
            "warnings": compat_result.get("warnings", []),
        },
        "measurements": verification_result.get("measurements", []),
        "predictions": verification_result.get("predictions", []),
        "model_comparison": verification_result.get("model_comparison"),
        "hotspots": hotspots_scan.get("hotspots", []),
        "shared_display_settings": {"stretch": "shared-percentile-linear", "vmin": float(stretch[0]), "vmax": float(stretch[1])},
        "grid": {"ra_deg": center_ra, "dec_deg": center_dec, "fov_arcmin": fov_arcmin, "size_px": grid_size_px},
        "limitations": verification_result.get("limitations", []),
        "warnings": warnings,
    }
