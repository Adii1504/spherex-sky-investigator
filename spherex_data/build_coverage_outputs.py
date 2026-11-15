"""Propagate each target to every FITS observation date and check coverage.

Writes (into the metadata folder):
  target_coordinates_per_observation.csv
  fits_coverage_validation.csv

Run from the project folder:  python build_coverage_outputs.py
Files in data/observations whose names do not start with a target key
(e.g. the M101 experiment files) are skipped.
"""
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS

from spherex_astrometry import (OBSERVATION_DIR, load_master, metadata_dir,
                                propagate, write_csv)

EDGE_MARGIN_PX = 8  # inside the image but closer than this to an edge -> EDGE

COORD_FIELDS = ["filename", "target_key", "target_name", "detector",
                "date_obs", "mjd_obs", "ref_epoch_jyear", "source_catalogue",
                "source_id", "ra_at_obs_deg", "dec_at_obs_deg",
                "rv_status", "quality_flag", "method"]

COVERAGE_FIELDS = ["filename", "target_key", "quality_flag", "pixel_x",
                   "pixel_y", "image_width", "image_height",
                   "edge_distance_px", "center_offset_px", "status",
                   "note", "error"]


def find_image_hdu(hdul):
    for hdu in hdul:
        if (hdu.name.upper() == "IMAGE" and hdu.data is not None
                and np.ndim(hdu.data) >= 2):
            return hdu
    return None


def observation_time(hdul):
    for hdu in hdul:
        date_obs = hdu.header.get("DATE-OBS")
        if date_obs:
            return Time(date_obs, scale="utc"), str(date_obs)
        mjd = hdu.header.get("MJD-OBS")
        if mjd is not None:
            return Time(float(mjd), format="mjd", scale="utc"), ""
    raise ValueError("DATE-OBS / MJD-OBS not found")


def target_key_for(filename, keys):
    # longest key first so e.g. "Epsilon_Indi_B" is matched exactly
    for key in sorted(keys, key=len, reverse=True):
        if filename.startswith(key + "_"):
            return key
    return None


def main():
    meta_dir = metadata_dir()
    master = load_master(meta_dir)

    coord_rows, coverage_rows, skipped = [], [], []

    for path in sorted(Path(OBSERVATION_DIR).glob("*.fits")):
        key = target_key_for(path.name, master)

        if key is None:
            skipped.append(path.name)
            continue

        entry = master[key]
        coord = {"filename": path.name, "target_key": key,
                 "target_name": entry["target_name"],
                 "ref_epoch_jyear": entry["ref_epoch_jyear"],
                 "source_catalogue": entry["source_catalogue"],
                 "source_id": entry["source_id"],
                 "rv_status": entry["rv_status"],
                 "quality_flag": entry["quality_flag"],
                 "method": "PROPAGATED_PM_PARALLAX_RV"}
        cov = {"filename": path.name, "target_key": key,
               "quality_flag": entry["quality_flag"], "status": "ERROR"}

        try:
            with fits.open(path, memmap=False) as hdul:
                obs_time, date_text = observation_time(hdul)
                coord["date_obs"] = date_text or obs_time.isot
                coord["mjd_obs"] = f"{obs_time.mjd:.9f}"
                coord["detector"] = hdul[0].header.get("DETECTOR", "")

                image_hdu = find_image_hdu(hdul)
                if image_hdu is None:
                    raise ValueError("IMAGE extension not found")

                height, width = image_hdu.data.shape[-2:]

                position = propagate(entry, obs_time)
                coord["ra_at_obs_deg"] = f"{position.ra.deg:.9f}"
                coord["dec_at_obs_deg"] = f"{position.dec.deg:.9f}"

                wcs = WCS(image_hdu.header, fobj=hdul).celestial
                if not wcs.has_celestial:
                    raise ValueError("Celestial WCS unavailable")

                x, y = (float(v) for v in wcs.world_to_pixel(position))

                edge = min(x + 0.5, width - 0.5 - x, y + 0.5, height - 0.5 - y)
                centre = float(np.hypot(x - (width - 1) / 2,
                                        y - (height - 1) / 2))

                if edge < 0:
                    status, note = "OUTSIDE_IMAGE", "Target not in this image"
                elif edge < EDGE_MARGIN_PX:
                    status = "EDGE"
                    note = (f"Inside but within {EDGE_MARGIN_PX} px of an edge "
                            "(cutout may be clipped by detector boundary)")
                else:
                    status, note = "INSIDE_IMAGE", ""

                cov.update(pixel_x=f"{x:.3f}", pixel_y=f"{y:.3f}",
                           image_width=width, image_height=height,
                           edge_distance_px=f"{edge:.3f}",
                           center_offset_px=f"{centre:.3f}",
                           status=status,
                           note=(note + "; " if note else "")
                           + "Coverage is not detection.")

        except Exception as error:
            cov["error"] = str(error)[:300]

        coord_rows.append(coord)
        coverage_rows.append(cov)

    write_csv(meta_dir / "target_coordinates_per_observation.csv",
              COORD_FIELDS, coord_rows)
    write_csv(meta_dir / "fits_coverage_validation.csv",
              COVERAGE_FIELDS, coverage_rows)

    counts = {}
    for row in coverage_rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1

    print("Files checked:", len(coverage_rows))
    print("Status counts:", counts)
    print("Skipped (not a project target):", len(skipped))
    for name in skipped:
        print("  ", name)
    for row in coverage_rows:
        if row["status"] != "INSIDE_IMAGE":
            print(f"  {row['status']:14s} {row['filename']}  {row.get('error', '')}")
    print("Wrote:", meta_dir / "target_coordinates_per_observation.csv")
    print("Wrote:", meta_dir / "fits_coverage_validation.csv")


if __name__ == "__main__":
    main()
