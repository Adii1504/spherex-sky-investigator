"""Conservative visualization and exploratory motion measurements, not discovery claims."""
from dataclasses import dataclass
import io
import time
import warnings as warning_module
import numpy as np
from PIL import Image
from astropy.io import fits
from astropy.wcs import WCS
from scipy.ndimage import map_coordinates, maximum_filter, label
from scipy.interpolate import RegularGridInterpolator
from .models import Preview, ProcessedSequence, VerificationResult

VERSION = "whylab-basic-wcs-1.0"

@dataclass
class Frame:
    observation: object
    image: np.ndarray
    valid: np.ndarray
    wavelength: np.ndarray | None
    bandwidth: np.ndarray | None
    unit: str
    metadata: dict

class BasicScience:
    available = True

    def __init__(self, settings): self.settings = settings

    def grid(self, sky):
        n = self.settings.preview_pixels
        if n > 512: raise ValueError("Preview grid limit is 512 pixels")
        scale = sky.fov_arcmin / 60 / n
        grid = WCS(naxis=2)
        grid.wcs.crpix = [(n + 1) / 2, (n + 1) / 2]
        grid.wcs.cdelt = [-scale, scale]
        grid.wcs.crval = [sky.ra_deg, sky.dec_deg]
        grid.wcs.ctype = ["RA---TAN", "DEC--TAN"]
        y, x = np.indices((n, n), dtype=float)
        return grid, grid.all_pix2world(x, y, 0)

    def wavelength(self, hdus, x, y):
        if "WCS-WAVE" not in hdus: return None, None
        wave = hdus["WCS-WAVE"]
        table = wave.data
        if table is None or len(table) != 1: return None, None
        try:
            xs, ys = np.asarray(table["X"][0], dtype=float).ravel(), np.asarray(table["Y"][0], dtype=float).ravel()
            values = np.asarray(table["VALUES"][0], dtype=float)
            if values.shape != (len(ys), len(xs), 2): return None, None
            # FITS lookup control points are 1-based image pixels.
            header = hdus["IMAGE"].header
            # Alternate W WCS maps cutout pixels back to the raw lookup grid.
            raw_x = (x + 1 - float(header.get("CRPIX1W", 1))) * float(header.get("CDELT1W", 1)) + float(header.get("CRVAL1W", 1))
            raw_y = (y + 1 - float(header.get("CRPIX2W", 1))) * float(header.get("CDELT2W", 1)) + float(header.get("CRVAL2W", 1))
            points = np.column_stack((raw_y.ravel(), raw_x.ravel()))
            unit = str(hdus["IMAGE"].header.get("CUNIT1W", hdus["IMAGE"].header.get("CUNIT3", wave.header.get("TUNIT3", "")))).strip().lower()
            factors = {"um": 1, "micron": 1, "microns": 1, "m": 1e6, "nm": .001}
            if unit not in factors: return None, None
            central = RegularGridInterpolator((ys, xs), values[:, :, 0], bounds_error=False, fill_value=np.nan)(points).reshape(x.shape) * factors[unit]
            width = RegularGridInterpolator((ys, xs), values[:, :, 1], bounds_error=False, fill_value=np.nan)(points).reshape(x.shape) * factors[unit]
            return central, width
        except (ValueError, KeyError, IndexError): return None, None

    def frame(self, observation, cutout, sky):
        with fits.open(io.BytesIO(cutout.data), memmap=False, lazy_load_hdus=False) as hdus:
            if "IMAGE" not in hdus or "FLAGS" not in hdus: raise ValueError("Science image and flags are required")
            image = np.asarray(hdus["IMAGE"].data, dtype=float)
            flags = np.asarray(hdus["FLAGS"].data)
            if image.ndim != 2 or image.shape != flags.shape or image.size > 4_500_000: raise ValueError("Unexpected image dimensions")
            with warning_module.catch_warnings():
                warning_module.simplefilter("ignore")
                native = WCS(hdus["IMAGE"].header, hdus, naxis=2).celestial
                _, world = self.grid(sky)
                x, y = native.all_world2pix(*world, 0, quiet=False)
            coordinates = np.array([y, x])
            source_bit = 0
            for key, value in hdus["FLAGS"].header.items():
                if key.startswith("MSKN") and str(value).strip() == "SOURCE": source_bit |= 1 << int(key[4:])
            valid = np.isfinite(image) & ((flags.astype(np.int64) & ~source_bit) == 0)
            if "VARIANCE" in hdus:
                variance = np.asarray(hdus["VARIANCE"].data)
                if variance.shape != image.shape: raise ValueError("Variance dimensions mismatch")
                valid &= np.isfinite(variance) & (variance > 0)
            support = map_coordinates(valid.astype(float), coordinates, order=1, mode="constant", cval=0, prefilter=False)
            projected = map_coordinates(np.where(valid, image, 0), coordinates, order=1, mode="constant", cval=0, prefilter=False)
            mask = (support > .999999) & np.isfinite(projected)
            projected[~mask] = np.nan
            if not mask.any(): raise ValueError("No unflagged sky coverage")
            wavelength, bandwidth = self.wavelength(hdus, x, y)
            center = self.settings.preview_pixels // 2
            wave_center = float(wavelength[center, center]) if wavelength is not None and np.isfinite(wavelength[center, center]) else None
            unit = str(hdus["IMAGE"].header.get("BUNIT", "unknown"))
            return Frame(observation, projected, mask, wavelength, bandwidth, unit, {"valid_fraction": float(mask.mean()), "position_wavelength_um": wave_center, "wavelength_source": "WCS-WAVE visualization lookup" if wavelength is not None else "unavailable", "unit": unit, "orientation": "north up, east left"})

    def compatible(self, a, b):
        if a.unit != b.unit or a.unit == "unknown" or a.wavelength is None or b.wavelength is None or a.bandwidth is None or b.bandwidth is None:
            return np.zeros(a.valid.shape, dtype=bool)
        tolerance = .25 * np.minimum(a.bandwidth, b.bandwidth)
        return a.valid & b.valid & np.isfinite(tolerance) & (tolerance > 0) & np.isfinite(a.wavelength) & np.isfinite(b.wavelength) & (np.abs(a.wavelength - b.wavelength) <= tolerance)

    @staticmethod
    def png(image, valid, lo, hi):
        normalized = np.clip((np.nan_to_num(image, nan=lo) - lo) / max(hi - lo, 1e-12), 0, 1)
        value = (np.arcsinh(normalized * 8) / np.arcsinh(8) * 255).astype(np.uint8)
        rgba = np.zeros((*value.shape, 4), dtype=np.uint8)
        rgba[:, :, :3] = value[:, :, None]
        rgba[:, :, 3] = np.where(valid, 255, 0)
        buffer = io.BytesIO()
        Image.fromarray(np.flipud(rgba)).save(buffer, format="PNG")
        return buffer.getvalue()

    def process(self, observations, cutouts, sky):
        indexed = {c.observation_id: c for c in cutouts}
        frames, warnings = [], ["Exploratory visualization: WCS alignment does not include PSF matching, background matching, or precision astrometric recalibration", "All data-quality flags except the header-defined informational SOURCE bit are masked; wavelength lookup is for visualization, not calibrated spectroscopy"]
        deadline = time.monotonic() + self.settings.timeout_seconds
        for observation in observations:
            if time.monotonic() > deadline: raise TimeoutError("Processing deadline exceeded")
            try: frames.append(self.frame(observation, indexed[observation.id], sky))
            except Exception: warnings.append("Could not process observation " + observation.id)
        if not frames: raise ValueError("No valid science frames")
        frames.sort(key=lambda f: f.observation.observed_at)
        samples = np.concatenate([f.image[f.valid][::max(1, int(f.valid.sum()) // 4096)] for f in frames])
        lo, hi = (float(v) for v in np.percentile(samples, [1, 99]))
        if hi <= lo: hi = lo + 1
        previews, comparisons = [], []
        reference = frames[0]
        for frame in frames:
            metadata = dict(frame.metadata)
            compatible = self.compatible(reference, frame)
            count = int(compatible.sum())
            comparison = {"reference_observation_id": reference.observation.id, "observation_id": frame.observation.id, "wavelength_compatible_pixels": count, "compatible_fraction": float(compatible.mean()), "difference_valid": False}
            if count >= 16 and frame is not reference:
                difference = frame.image[compatible] - reference.image[compatible]
                comparison.update(difference_median=float(np.median(difference)), difference_rms=float(np.sqrt(np.mean(difference ** 2))), difference_unit=frame.unit, difference_valid=True)
            elif frame is not reference:
                warnings.append("No valid wavelength-compatible difference against reference for " + frame.observation.id)
            metadata["comparison"] = comparison
            comparisons.append(comparison)
            previews.append(Preview(observation_id=frame.observation.id, png=self.png(frame.image, frame.valid, lo, hi), metadata=metadata))
        return ProcessedSequence(previews=previews, processing_version=VERSION, processing_settings={"alignment": "Astropy full celestial WCS including available SIP distortions, bilinear resampling", "mask": "finite IMAGE; FLAGS == 0 after excluding header-defined SOURCE bit; finite positive VARIANCE when present; all interpolation neighbors valid", "grid": "ICRS TAN, north up east left", "pixels": self.settings.preview_pixels, "wavelength_tolerance": "per-pixel center difference <= 0.25 * smaller bandwidth; unknown wavelengths excluded", "background_subtracted": False, "psf_matched": False}, shared_display_settings={"stretch": "asinh", "asinh_factor": 8, "minimum": lo, "maximum": hi, "unit": frames[0].unit, "percentiles": [1, 99], "masked_pixels": "transparent"}, measurements={"comparisons": comparisons}, warnings=warnings)

class ExploratoryMotion:
    """Training-only constant-velocity fit. Residuals are not a validated motion claim."""
    available = True

    def __init__(self, science): self.science = science

    def verify(self, training, reserved, sky, archive):
        assumptions = ["A single isolated positive source remains within 18.45 arcsec of the selected coordinate", "A straight line in a common local tangent plane approximates motion over the selected time span", "Training observations alone determine the velocity; held-out exposures are measured after fitting"]
        limitations = ["Exploratory centroid and linear fit; no source association validation, PSF matching or calibrated astrometric uncertainty model", "Residuals are reported without a confidence percentage or supported-motion verdict", "WCS-WAVE wavelengths are visualization estimates; systematic calibration and chromatic centroid shifts may dominate"]
        measurements = {"model": "training-only ordinary least squares in tangent-plane pixel coordinates", "training": [], "reserved": [], "fit": None}
        warnings = []
        def result():
            return VerificationResult(outcome="insufficient_evidence", measurements=measurements, assumptions=assumptions, limitations=limitations, warnings=warnings, processing_version=VERSION)
        combined = training + reserved
        exposures = [o.exposure_id for o in combined]
        if len(exposures) != len(set(exposures)) or len({o.id for o in combined}) != len(combined):
            warnings.append("Duplicate or overlapping exposure identities")
            return result()
        if len(training) < 3 or not reserved:
            warnings.append("At least three training exposures and one reserved exposure are required")
            return result()
        deadline = time.monotonic() + self.science.settings.timeout_seconds
        reference = None
        def measure(observation):
            nonlocal reference
            if time.monotonic() > deadline: raise TimeoutError("Verification deadline exceeded")
            frame = self.science.frame(observation, archive.cutout(observation, sky), sky)
            if reference is None: reference = frame
            n = frame.image.shape[0]
            y, x = np.indices(frame.image.shape)
            scale = sky.fov_arcmin * 60 / n
            radius = 18.45 / scale
            aperture = (x - (n - 1) / 2) ** 2 + (y - (n - 1) / 2) ** 2 <= radius ** 2
            compatible = self.science.compatible(reference, frame)
            usable = frame.valid & compatible & aperture
            if usable.sum() < 12 or np.mean(usable[aperture]) < .8: raise ValueError("Insufficient wavelength-compatible aperture")
            background_values = frame.image[frame.valid & ~aperture]
            if background_values.size < 20: raise ValueError("Insufficient background pixels")
            background = float(np.median(background_values))
            noise = float(1.4826 * np.median(np.abs(background_values - background)))
            if noise <= 0 or not np.isfinite(noise): raise ValueError("No reliable background scatter")
            signal = np.where(usable, frame.image - background, -np.inf)
            peaks = usable & (signal == maximum_filter(signal, size=5)) & (signal > 5 * noise)
            _, count = label(peaks)
            if count != 1: raise ValueError("Aperture source is absent or ambiguous")
            py, px = np.unravel_index(np.argmax(signal), signal.shape)
            local = usable & ((x - px) ** 2 + (y - py) ** 2 <= (12.3 / scale) ** 2)
            weights = np.where(local, np.maximum(frame.image - background, 0), 0)
            weights = np.nan_to_num(weights)
            total = weights.sum()
            if total <= 0: raise ValueError("No positive centroid weight")
            cx, cy = float((weights * x).sum() / total), float((weights * y).sum() / total)
            return {"observation_id": observation.id, "exposure_id": observation.exposure_id, "observed_at": observation.observed_at.isoformat(), "x_pixel": cx, "y_pixel": cy, "background_scatter": noise, "background_unit": frame.unit, "position_wavelength_um": frame.metadata["position_wavelength_um"]}
        try:
            for observation in sorted(training, key=lambda o: o.observed_at): measurements["training"].append(measure(observation))
        except Exception:
            warnings.append("Training source could not be measured reliably; no fit or held-out evaluation performed")
            return result()
        origin = min(o.observed_at for o in training)
        by_id = {o.id: o for o in training}
        times = np.array([(by_id[m["observation_id"]].observed_at - origin).total_seconds() / 86400 for m in measurements["training"]])
        design = np.column_stack((np.ones(len(times)), times))
        if np.linalg.matrix_rank(design) < 2:
            warnings.append("Training observation times do not span a fit baseline")
            return result()
        positions = np.array([[m["x_pixel"], m["y_pixel"]] for m in measurements["training"]])
        coefficients, _, _, _ = np.linalg.lstsq(design, positions, rcond=None)
        scale = sky.fov_arcmin * 60 / self.science.settings.preview_pixels
        measurements["fit"] = {"epoch_utc": origin.isoformat(), "intercept_pixels": coefficients[0].tolist(), "velocity_pixels_per_day": coefficients[1].tolist(), "east_velocity_arcsec_per_day": float(-coefficients[1, 0] * scale), "north_velocity_arcsec_per_day": float(coefficients[1, 1] * scale), "training_residual_rms_arcsec": float(np.sqrt(np.mean((positions - design @ coefficients) ** 2)) * scale)}
        for observation in sorted(reserved, key=lambda o: o.observed_at):
            try:
                measured = measure(observation)
                predicted = np.array([1, (observation.observed_at - origin).total_seconds() / 86400]) @ coefficients
                residual = np.array([measured["x_pixel"], measured["y_pixel"]]) - predicted
                measured.update(predicted_pixels=predicted.tolist(), residual_arcsec=float(np.linalg.norm(residual) * scale))
                measurements["reserved"].append(measured)
            except Exception: warnings.append("Reserved source unavailable or ambiguous for " + observation.id)
        return result()
