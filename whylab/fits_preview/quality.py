import math
import numpy as np
from astropy.coordinates import SkyCoord
import astropy.units as u
from .reader import json_safe


def report(frame, position, radius):
    geometry = {"status": "unavailable", "reason": None, "wcs_conversion_success": False,
                "x": None, "y": None, "inside_image": None,
                "nearest_boundary_distance_pixels": None, "signed_edge_clearance_pixels": None}
    result = {"schema_version": "1.0", "position": position,
              "note": "Marker is a supplied predicted position; no detection or astrometric verification performed.",
              "geometry": geometry, "aperture": {"status": "unavailable", "radius_pixels": radius},
              "variance": {"status": "unavailable", "reason": "extension_unavailable" if frame.variance is None else "aperture_unavailable"},
              "flags": {"status": "unavailable", "reason": "extension_unavailable" if frame.flags is None else "aperture_unavailable"},
              "warnings": list(frame.metadata["warnings"])}
    reason = ("image_unavailable" if frame.image is None else
              "coordinates_unavailable" if position["ra_deg"] is None else
              "wcs_unavailable" if frame.wcs is None else None)
    if reason:
        geometry["reason"] = reason
        return result
    try:
        # High-level celestial API honors RADESYS/axis ordering and uses origin 0.
        x, y = frame.wcs.world_to_pixel(SkyCoord(position["ra_deg"] * u.deg,
                                               position["dec_deg"] * u.deg, frame="icrs"))
        x, y = float(x), float(y)
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError("Nonfinite WCS result")
    except Exception:
        geometry["reason"] = "wcs_conversion_failed"
        return result
    height, width = frame.image.shape
    inside = -.5 <= x <= width-.5 and -.5 <= y <= height-.5
    clearance = min(x+.5, width-.5-x, y+.5, height-.5-y)
    # Distance to the nearest point on the rectangular pixel boundary, also outside.
    distance = clearance if inside else math.hypot(max(-.5-x, 0, x-(width-.5)), max(-.5-y, 0, y-(height-.5)))
    geometry.update(status="available", wcs_conversion_success=True, x=x, y=y,
                    inside_image=inside, nearest_boundary_distance_pixels=distance,
                    signed_edge_clearance_pixels=clearance)
    yy, xx = np.ogrid[:height, :width]
    aperture = np.hypot(xx-x, yy-y) <= radius
    values = frame.image[aperture]
    finite = int(np.isfinite(values).sum())
    count = int(values.size)
    result["aperture"].update(status="available", truncated=clearance < radius,
                             sampling="pixel centers within circular radius",
                             pixel_count=count, finite_science_count=finite,
                             nonfinite_science_count=count-finite,
                             valid_pixel_fraction=finite/count if count else None,
                             validity_definition="finite science only; no flag or detection classification")
    if frame.variance is not None:
        v = frame.variance[aperture]
        n = int((np.isfinite(v) & (v > 0)).sum())
        result["variance"] = {"status": "available", "finite_positive_count": n,
                              "invalid_count": count-n, "valid_fraction": n/count if count else None,
                              "criterion": "finite and strictly positive; zero counted separately",
                              "zero_count": int((v == 0).sum())}
    if frame.flags is not None:
        if frame.flags.dtype.kind not in "iu":
            result["flags"] = {"status": "unavailable", "reason": "flags_not_integer"}
        else:
            flags = frame.flags[aperture]
            unique, counts = np.unique(flags, return_counts=True)
            result["flags"] = {"status": "available", "value_counts": [
                {"value": int(v), "count": int(n)} for v, n in zip(unique, counts)],
                "bitwise_or": int(np.bitwise_or.reduce(flags)) if flags.size else None,
                "interpretation": "Raw integer masks; nonzero does not imply bad pixels"}
    return json_safe(result)
