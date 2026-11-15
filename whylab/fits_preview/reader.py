"""Read named science extensions without altering the source file."""
from dataclasses import dataclass
import math
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS


def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


@dataclass
class FitsFrame:
    image: object
    flags: object
    variance: object
    wcs: object
    metadata: dict


def read(path):
    warnings = []
    with fits.open(path, mode="readonly", memmap=False) as hdus:
        inventory = [{"index": i, "name": h.name, "type": type(h).__name__}
                     for i, h in enumerate(hdus)]
        science = hdus["IMAGE"] if "IMAGE" in hdus else None
        headers = [("IMAGE", science.header)] if science is not None else []
        headers.append(("PRIMARY", hdus[0].header))

        def field(key):
            for name, header in headers:
                if key in header:
                    return {"value": json_safe(header[key]), "hdu": name, "keyword": key,
                            "comment": header.comments[key]}
            warnings.append(f"Missing header field {key}")
            return None

        # Retain standard FITS time values and their declared scale; never use DATE
        # (file creation time) as an observation time or invent a missing TIMESYS.
        metadata = {key: field(key) for key in
                    ("BUNIT", "DATE-OBS", "MJD-OBS", "TIMESYS", "DETECTOR")}
        spectral = {}
        for key in ("CTYPE1W", "CTYPE2W", "CUNIT1W", "CUNIT2W", "WCSNAMEW",
                    "PS1_0W", "PS1_1W", "PS1_2W", "PS2_2W"):
            spectral[key] = next(({"value": json_safe(h[key]), "hdu": n,
                                   "comment": h.comments[key]} for n, h in headers if key in h), None)
        if not any(v is not None for v in spectral.values()):
            warnings.append("Wavelength metadata unavailable")
        metadata.update(hdus=inventory, wavelength={"headers": spectral,
                        "lookup_extension_present": "WCS-WAVE" in hdus,
                        "position_wavelength": None}, warnings=warnings)
        arrays = {}
        for name in ("IMAGE", "FLAGS", "VARIANCE"):
            h = hdus[name] if name in hdus else None
            if h is None or not isinstance(h, (fits.ImageHDU, fits.PrimaryHDU, fits.CompImageHDU)) or h.data is None:
                arrays[name] = None
                warnings.append(f"{name} extension unavailable")
            elif h.data.ndim != 2 or h.data.size > 4_500_000:
                arrays[name] = None
                warnings.append(f"{name} requires a 2D image of at most 4500000 pixels")
            else:
                arrays[name] = np.array(h.data, copy=True)
        image = arrays["IMAGE"]
        metadata["dimensions"] = None if image is None else {"width": image.shape[1], "height": image.shape[0]}
        native = None
        if image is not None:
            try:
                candidate = WCS(science.header, hdus).celestial
                if not candidate.has_celestial or candidate.pixel_n_dim != 2:
                    raise ValueError("No celestial WCS")
                if candidate.sip is not None and "-SIP" not in str(science.header.get("CTYPE1", "")):
                    warnings.append("SIP coefficients lack a -SIP CTYPE declaration; Astropy applies the coefficients. Header convention requires scientific review.")
                native = candidate
            except Exception:
                warnings.append("Science celestial WCS unavailable")
        for name in ("FLAGS", "VARIANCE"):
            if arrays[name] is not None and (image is None or arrays[name].shape != image.shape):
                arrays[name] = None
                warnings.append(f"{name} dimensions do not match IMAGE")
        return FitsFrame(image, arrays["FLAGS"], arrays["VARIANCE"], native, metadata)
