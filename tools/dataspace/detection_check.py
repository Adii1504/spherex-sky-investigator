"""Detection check at the predicted target position, WITH a control test.

Coverage only shows the target is INSIDE an image. This checks whether the
pixels at that position stand out from the local background, and compares
the result with random positions in the same image (controls), because a
plain "peak > 5 sigma" test fires on field stars and noise spikes.

Run after build_coverage_outputs.py:   python detection_check.py
Writes data/metadata/detection_check.csv

Measurement: background = median and robust sigma (1.4826 * MAD) of an
annulus 6-12 px around a position; signal = brightest pixel in a 5x5 box at
that position. FLAGS are not used (some flag bits mark real sources).

Verdicts:
  DETECTED_CANDIDATE            SNR >= 5 AND above the 99th percentile of the
                                control positions in that image
  ABOVE_THRESHOLD_NOT_UNUSUAL   SNR >= 5 but random positions in this image
                                reach it too (crowded/noisy field): NOT evidence
  NOT_DETECTED                  SNR < 5
Even DETECTED_CANDIDATE is not proof: look at the image.
"""
import numpy as np
from astropy.io import fits

from build_coverage_outputs import find_image_hdu
from spherex_astrometry import OBSERVATION_DIR, metadata_dir, read_csv, write_csv

INNER, OUTER = 6, 12
HALF_BOX = 2
SNR_THRESHOLD = 5.0
N_CONTROLS = 300
MIN_CONTROL_SEPARATION = 8  # px from the target
SEED = 12345

FIELDS = ["filename", "target_key", "coverage_status", "pixel_x", "pixel_y",
          "background_median", "background_sigma", "peak_value", "peak_dx",
          "peak_dy", "centroid_dx", "centroid_dy", "snr_peak", "brightest_within_12px_snr",
          "brightest_within_12px_dist_px", "control_n", "control_p99_snr",
          "control_fraction_ge_threshold", "verdict", "note"]


def measure(data, x, y):
    """Return a dict of measurements at (x, y), or {'reason': ...}."""
    height, width = data.shape
    yy, xx = np.indices((height, width))
    radius = np.hypot(xx - x, yy - y)

    annulus = (radius >= INNER) & (radius <= OUTER) & np.isfinite(data)
    if annulus.sum() < 30:
        return {"reason": "INSUFFICIENT_BACKGROUND"}

    values = data[annulus]
    background = float(np.median(values))
    sigma = float(1.4826 * np.median(np.abs(values - background)))
    if not np.isfinite(sigma) or sigma <= 0:
        return {"reason": "BAD_BACKGROUND_NOISE"}

    ix, iy = int(round(x)), int(round(y))
    x0, x1 = max(ix - HALF_BOX, 0), min(ix + HALF_BOX + 1, width)
    y0, y1 = max(iy - HALF_BOX, 0), min(iy + HALF_BOX + 1, height)
    box = data[y0:y1, x0:x1]
    if box.size == 0 or not np.isfinite(box).any():
        return {"reason": "NO_DATA_AT_TARGET"}

    by, bx = np.unravel_index(np.nanargmax(box), box.shape)
    peak = float(box[by, bx])

    # Flux-weighted centroid (background-subtracted, positive pixels only)
    # in a 7x7 window: steadier than the single brightest pixel for very
    # bright or saturated sources.
    cx0, cx1 = max(ix - 3, 0), min(ix + 4, width)
    cy0, cy1 = max(iy - 3, 0), min(iy + 4, height)
    window = np.nan_to_num(data[cy0:cy1, cx0:cx1] - background, nan=0.0)
    window = np.clip(window, 0, None)
    if window.sum() > 0:
        wy, wx = np.indices(window.shape)
        centroid_dx = float((window * (wx + cx0)).sum() / window.sum() - x)
        centroid_dy = float((window * (wy + cy0)).sum() / window.sum() - y)
    else:
        centroid_dx = centroid_dy = float("nan")

    near = np.where((radius <= OUTER) & np.isfinite(data), data, -np.inf)
    ny, nx = np.unravel_index(np.argmax(near), near.shape)

    return {"background": background, "sigma": sigma, "peak": peak,
            "dx": x0 + bx - x, "dy": y0 + by - y,
            "cdx": centroid_dx, "cdy": centroid_dy,
            "snr": (peak - background) / sigma,
            "near_snr": (float(data[ny, nx]) - background) / sigma,
            "near_dist": float(np.hypot(nx - x, ny - y))}


def control_snrs(data, x, y, rng):
    height, width = data.shape
    snrs = []
    for _ in range(N_CONTROLS * 4):
        cx = rng.uniform(3, width - 4)
        cy = rng.uniform(3, height - 4)
        if np.hypot(cx - x, cy - y) < MIN_CONTROL_SEPARATION:
            continue
        result = measure(data, cx, cy)
        if "snr" in result:
            snrs.append(result["snr"])
        if len(snrs) >= N_CONTROLS:
            break
    return np.array(snrs)


def check(path, x, y):
    with fits.open(path, memmap=False) as hdul:
        hdu = find_image_hdu(hdul)
        data = np.asarray(np.squeeze(hdu.data), dtype=float)

    result = measure(data, x, y)
    if "snr" not in result:
        return {"verdict": result["reason"]}

    rng = np.random.default_rng(SEED)
    controls = control_snrs(data, x, y, rng)

    out = {"background_median": f"{result['background']:.6g}",
           "background_sigma": f"{result['sigma']:.6g}",
           "peak_value": f"{result['peak']:.6g}",
           "peak_dx": f"{result['dx']:.2f}", "peak_dy": f"{result['dy']:.2f}",
           "centroid_dx": f"{result['cdx']:.2f}",
           "centroid_dy": f"{result['cdy']:.2f}",
           "snr_peak": f"{result['snr']:.2f}",
           "brightest_within_12px_snr": f"{result['near_snr']:.2f}",
           "brightest_within_12px_dist_px": f"{result['near_dist']:.2f}"}

    note = []
    if result["near_snr"] > result["snr"] + 5 and result["near_dist"] > 3:
        note.append("Much brighter source within 12 px: possible blend/contamination")

    if len(controls) >= 30:
        p99 = float(np.percentile(controls, 99))
        frac = float(np.mean(controls >= SNR_THRESHOLD))
        out.update(control_n=len(controls), control_p99_snr=f"{p99:.2f}",
                   control_fraction_ge_threshold=f"{frac:.3f}")
    else:
        p99 = float("inf")
        note.append("Too few control positions; cannot calibrate")

    if result["snr"] < SNR_THRESHOLD:
        verdict = "NOT_DETECTED"
    elif result["snr"] > p99:
        verdict = "DETECTED_CANDIDATE"
    else:
        verdict = "ABOVE_THRESHOLD_NOT_UNUSUAL"

    out["verdict"] = verdict
    out["note"] = "; ".join(note)
    return out


def main():
    meta_dir = metadata_dir()
    coverage = read_csv(meta_dir / "fits_coverage_validation.csv")

    rows = []
    for cov in coverage:
        if cov["status"] not in ("INSIDE_IMAGE", "EDGE"):
            continue
        row = {"filename": cov["filename"], "target_key": cov["target_key"],
               "coverage_status": cov["status"],
               "pixel_x": cov["pixel_x"], "pixel_y": cov["pixel_y"]}
        try:
            row.update(check(OBSERVATION_DIR / cov["filename"],
                             float(cov["pixel_x"]), float(cov["pixel_y"])))
        except Exception as error:
            row.update(verdict="ERROR", note=str(error)[:200])
        rows.append(row)

    write_csv(meta_dir / "detection_check.csv", FIELDS, rows)

    summary = {}
    for row in rows:
        counts = summary.setdefault(row["target_key"], {})
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    for key, counts in summary.items():
        print(key, counts)
    print("Wrote:", meta_dir / "detection_check.csv")


if __name__ == "__main__":
    main()