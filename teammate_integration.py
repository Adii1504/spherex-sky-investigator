"""Connect commit 9c2e3bb's scientific engine to the existing bounded workers."""
from __future__ import annotations

import io
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.processing import PROCESSING_LOCK
from backend.processing.compatibility import check_wavelength_compatibility
from backend.processing.io_fits import build_valid_mask, load_observation
from backend.processing.measure import measure_position
from backend.processing.motion import test_motion
from backend.processing.pipeline import run_investigation_pipeline
from whylab.models import Preview, ProcessedSequence, VerificationResult
from whylab.fits_preview.reader import json_safe


class SPHERExSequenceAdapter:
    available = True

    def __init__(self, settings=None):
        self.settings = settings

    def process(self, observations, cutouts, sky):
        if len(observations) != len(cutouts) or not observations:
            raise ValueError("Each observation requires its matching cutout")
        pairs = sorted(zip(observations, cutouts), key=lambda pair: pair[0].observed_at)
        frames = []
        for observation, cutout in pairs:
            if cutout.observation_id != observation.id:
                raise ValueError("Cutout belongs to another observation")
            frame = load_observation(io.BytesIO(cutout.data))
            frame.header_meta["OBS_ID"] = observation.id
            frames.append(frame)
        with PROCESSING_LOCK, TemporaryDirectory(prefix="whylab-science-") as directory:
            result = run_investigation_pipeline(frames,
                target_coord=(float(sky.ra_deg), float(sky.dec_deg)),
                fov_arcmin=float(sky.fov_arcmin),
                grid_size_px=getattr(self.settings, "preview_pixels", 192),
                output_dir=directory)
            previews = []
            for frame in result["frames"]:
                path = Path(directory) / frame["image_url"]
                previews.append(Preview(observation_id=frame["observation_id"], png=path.read_bytes(),
                    metadata={"target_wavelength_um": frame["target_wavelength_um"],
                              "observed_at": frame["observed_at"], "detector": frame["detector"]}))
        return ProcessedSequence(previews=previews, processing_version="SPHEREx-9c2e3bb-integrated-v1",
            processing_settings={"alignment": "surface-brightness interpolation", "grid": result["grid"],
                "flag_mask": "supplied DEFAULT_FATAL_BITMASK; interpretation requires scientific review"},
            shared_display_settings=result["shared_display_settings"],
            measurements=json_safe({"measurements": result["measurements"], "comparison": result["comparison"]}),
            warnings=result["warnings"] + ["Exploratory processing; source identity is not independently verified."])


class SPHERExMotionAdapter:
    available = True

    def __init__(self, settings=None):
        self.settings = settings

    def verify(self, training, reserved, sky, archive):
        # The caller's split is authoritative. Every held-out observation is
        # evaluated against the same training-only fit, never added to the fit.
        def measure(observation):
            cutout = archive.cutout(observation, sky)
            if cutout.observation_id != observation.id:
                raise ValueError("Cutout belongs to another observation")
            frame = load_observation(io.BytesIO(cutout.data))
            measurement = measure_position(frame.image, build_valid_mask(frame.flags, frame.image.shape),
                frame.wcs, float(sky.ra_deg), float(sky.dec_deg))
            return frame, {"epoch_id": observation.id, "observed_at_utc": frame.observed_at_utc,
                "ra_deg": measurement["ra_deg"], "dec_deg": measurement["dec_deg"],
                "snr": measurement["snr"], "uncertainty_arcsec": measurement["uncertainty_arcsec"],
                "status": measurement["status"]}

        with PROCESSING_LOCK:
            train_pairs = [measure(o) for o in training]
            reserved_pairs = [measure(o) for o in reserved]
            train = [pair[1] for pair in train_pairs]
            held = [pair[1] for pair in reserved_pairs]
            results = [test_motion(train, measurement) for measurement in held]
            compatibility = check_wavelength_compatibility([p[0] for p in train_pairs + reserved_pairs],
                target_coord=(float(sky.ra_deg), float(sky.dec_deg)))
        outcomes = [r["outcome"] for r in results]
        mapping = {"motion_supported": "supported", "stationary_plausible": "not_supported"}
        outcome = mapping.get(outcomes[0], "insufficient_evidence") if outcomes and len(set(outcomes)) == 1 else "insufficient_evidence"
        warnings = [w for r in results for w in r.get("warnings", [])] + compatibility["warnings"]
        if compatibility["status"] != "compatible":
            outcome = "insufficient_evidence"
            warnings.append("Unknown or incompatible wavelengths prevent a verified motion conclusion.")
        return VerificationResult(outcome=outcome,
            measurements=json_safe({"training": train, "reserved": held, "evaluations": results,
                "comparison": compatibility}),
            assumptions=["Linear tangent-plane motion fitted only on training observations.",
                "Engine uses a stated 0.5 arcsec calibration floor; nominal 1.5 arcsec when all uncertainties are missing.",
                "Supplied fatal-flag bitmask is an adopted processing policy requiring scientific review."],
            limitations=["Exploratory centroid association is not source identification.",
                "No orbital model or observer-dependent annual parallax.",
                "Native pixel scale and multi-band morphology limit astrometry."],
            warnings=warnings, processing_version="SPHEREx-9c2e3bb-integrated-v1")


def build_adapters(settings, trusted_retriever):
    from whylab.archive import IRSAArchive
    trusted_retriever.max_bytes = settings.max_cutout_bytes
    return (IRSAArchive(settings, trusted_retriever), SPHERExSequenceAdapter(settings), SPHERExMotionAdapter(settings))
