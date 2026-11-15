"""Teammate Integration Adapter for SPHEREx WhyLab.

Connects Person 2's scientific image processing & motion verification library
to Person 4's FastAPI backend worker pool (whylab/app.py) as defined in
docs/integration-contract.md.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from backend.processing.alignment import make_common_grid, reproject_to_grid
from backend.processing.display import compute_shared_stretch, render_preview_png, make_difference
from backend.processing.io_fits import load_observation
from backend.processing.measure import measure_position
from backend.processing.motion import fit_constant_motion, test_motion, scan_and_track_motion
from backend.processing.pipeline import run_investigation_pipeline


class SPHERExSequenceAdapter:
    """Scientific sequence processor conforming to SequenceAdapter protocol."""
    available: bool = True

    def __init__(self, settings: Any = None):
        self.settings = settings

    def process(self, observations: list[Any], cutouts: list[Any], sky: Any) -> Any:
        """Process chronological multi-epoch cutouts on a common celestial grid."""
        try:
            from whylab.models import Preview, ProcessedSequence
        except ImportError:
            Preview = None
            ProcessedSequence = dict

        fits_bytes = [io.BytesIO(c.data) if hasattr(c, "data") else c for c in cutouts]
        target_coord = (float(sky.ra_deg), float(sky.dec_deg))
        fov_arcmin = float(sky.fov_arcmin)

        result = run_investigation_pipeline(
            fits_inputs=fits_bytes,
            target_coord=target_coord,
            fov_arcmin=fov_arcmin,
            grid_size_px=getattr(self.settings, "preview_pixels", 128),
        )

        previews_list = []
        for idx, frame in enumerate(result.get("frames", [])):
            obs_id = observations[idx].id if idx < len(observations) else f"obs_{idx + 1}"
            png_bytes = b""
            if frame.get("image_url"):
                local_path = Path(frame["image_url"].lstrip("/"))
                if local_path.exists():
                    png_bytes = local_path.read_bytes()

            if Preview:
                previews_list.append(Preview(
                    observation_id=obs_id,
                    png=png_bytes,
                    metadata={"target_wavelength_um": frame.get("target_wavelength_um")}
                ))
            else:
                previews_list.append({
                    "observation_id": obs_id,
                    "png": png_bytes,
                    "metadata": {"target_wavelength_um": frame.get("target_wavelength_um")}
                })

        payload = {
            "previews": previews_list,
            "processing_version": "SPHEREx-WhyLab-Science-v1.0",
            "processing_settings": {
                "alignment": "reproject_interp-flux-conserving",
                "grid": "North-up/East-left-TAN",
                "fov_arcmin": fov_arcmin,
            },
            "shared_display_settings": {
                "stretch": "shared-percentile-asinh",
                "pmin": 1.0,
                "pmax": 99.0,
            },
            "measurements": {
                "hotspots": result.get("hotspots", []),
                "measurements": result.get("measurements", []),
            },
            "warnings": result.get("warnings", []),
        }

        if ProcessedSequence and ProcessedSequence is not dict:
            return ProcessedSequence(**payload)
        return payload


class SPHERExMotionAdapter:
    """Moving-source verification adapter conforming to MotionAdapter protocol."""
    available: bool = True

    def __init__(self, settings: Any = None):
        self.settings = settings

    def verify(self, training: list[Any], reserved: list[Any], sky: Any, archive: Any) -> Any:
        """Evaluate training exposures vs reserved evaluation epoch."""
        try:
            from whylab.models import VerificationResult
        except ImportError:
            VerificationResult = dict

        # 1. Load training cutouts
        training_measurements = []
        for obs in training:
            cutout = archive.cutout(obs, sky)
            parsed_obs = load_observation(io.BytesIO(cutout.data))
            # Measure centroid near target coordinate
            meas = measure_position(
                aligned_image=parsed_obs.image,
                mask=parsed_obs.flags == 0 if parsed_obs.flags is not None else None,
                wcs=parsed_obs.wcs,
                ra_deg=float(sky.ra_deg),
                dec_deg=float(sky.dec_deg),
            )
            training_measurements.append({
                "epoch_id": obs.id,
                "observed_at_utc": obs.observed_at.isoformat() if hasattr(obs.observed_at, "isoformat") else str(obs.observed_at),
                "ra_deg": meas["ra_deg"],
                "dec_deg": meas["dec_deg"],
                "snr": meas["snr"],
                "uncertainty_arcsec": meas["uncertainty_arcsec"] or 0.5,
                "status": meas["status"],
            })

        # 2. Load reserved cutouts
        reserved_measurements = []
        for obs in reserved:
            cutout = archive.cutout(obs, sky)
            parsed_obs = load_observation(io.BytesIO(cutout.data))
            meas = measure_position(
                aligned_image=parsed_obs.image,
                mask=parsed_obs.flags == 0 if parsed_obs.flags is not None else None,
                wcs=parsed_obs.wcs,
                ra_deg=float(sky.ra_deg),
                dec_deg=float(sky.dec_deg),
            )
            reserved_measurements.append({
                "epoch_id": obs.id,
                "observed_at_utc": obs.observed_at.isoformat() if hasattr(obs.observed_at, "isoformat") else str(obs.observed_at),
                "ra_deg": meas["ra_deg"],
                "dec_deg": meas["dec_deg"],
                "snr": meas["snr"],
                "uncertainty_arcsec": meas["uncertainty_arcsec"] or 0.5,
                "status": meas["status"],
            })

        all_measurements = training_measurements + reserved_measurements
        res = test_motion(
            measurements=all_measurements,
            reserved_epoch_id=reserved_measurements[0]["epoch_id"] if reserved_measurements else None,
            investigation_id=f"VERIFY_RA{sky.ra_deg:.3f}_DEC{sky.dec_deg:.3f}",
        )

        outcome_mapping = {
            "motion_supported": "supported",
            "stationary_plausible": "not_supported",
            "insufficient_evidence": "insufficient_evidence",
        }

        payload = {
            "outcome": outcome_mapping.get(res["outcome"], "insufficient_evidence"),
            "measurements": {
                "training": training_measurements,
                "reserved": reserved_measurements,
                "model_comparison": res.get("model_comparison"),
            },
            "assumptions": [
                "2D linear constant proper motion across observation epochs.",
                "Tangent celestial plane projection at initial training epoch.",
                "Held-out reserved epoch evaluated strictly without fitting.",
            ],
            "limitations": res.get("limitations", [
                "SPHEREx ~6.2 arcsec native pixel scale limits astrometric precision.",
            ]),
            "warnings": res.get("warnings", []),
            "processing_version": "SPHEREx-WhyLab-Science-v1.0",
        }

        if VerificationResult and VerificationResult is not dict:
            return VerificationResult(**payload)
        return payload


def build_adapters(settings: Any = None, trusted_retriever: Any = None) -> tuple[Any, Any, Any]:
    """Factory called by Person 4's whylab server to instantiate real scientific adapters."""
    try:
        from whylab.adapters import Unavailable
        archive_adapter = Unavailable("archive_access")
    except ImportError:
        archive_adapter = None

    return (
        archive_adapter,
        SPHERExSequenceAdapter(settings),
        SPHERExMotionAdapter(settings),
    )
