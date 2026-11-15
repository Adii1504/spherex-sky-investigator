"""Final validation, manifest, duplicate audit and packaging.

Run AFTER:  python fix_downloads.py
            python build_coverage_outputs.py   (expect no OUTSIDE_IMAGE)

Run from the project folder:   python finalize_dataset.py
Options:  --no-package   only write the CSVs, do not build final_dataset/

Writes into data/metadata/:
  clean_dataset_manifest_final.csv
  excluded_files_final.csv
  duplicate_audit_final.csv
  dataset_summary.txt
and (unless --no-package) builds final_dataset/ with fits/, metadata/,
README.md and SHA256SUMS.txt.
"""
import argparse
import hashlib
import re
import shutil
from collections import defaultdict
from pathlib import Path

import numpy as np
from astropy.io import fits

from build_coverage_outputs import target_key_for
from spherex_astrometry import (BASE_DIR, OBSERVATION_DIR, load_master,
                                metadata_dir, read_csv, write_csv)

PACKAGE_DIR = BASE_DIR / "final_dataset"

MANIFEST_FIELDS = [
    "filename", "package_path", "target_key", "target_name", "sha256",
    "date_obs", "mjd_obs", "detector", "bandpass", "bandpass_source",
    "image_width", "image_height", "image_unit",
    "wavelength_min", "wavelength_max", "wavelength_unit",
    "pipeline_version", "processing_batch", "header_version",
    "astrometry_source", "astrometry_quality_flag",
    "coverage_status", "pixel_x", "pixel_y", "edge_distance_px",
    "flags",
]
EXCLUDED_FIELDS = ["filename", "target_key", "sha256", "exclusion_reason"]
DUPLICATE_FIELDS = ["group", "sha256", "filename", "role", "target_key"]


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def header_value(hdul, keyword):
    for hdu in hdul:
        if keyword in hdu.header:
            return hdu.header[keyword]
    return None


def wavelength_info(hdul):
    """(min, max, unit) over the WCS-WAVE table, as in the earlier scripts."""
    try:
        wave_hdu = hdul["WCS-WAVE"]
        data = wave_hdu.data
        if data is None or "VALUES" not in data.names:
            return None, None, ""
        values = np.asarray(data["VALUES"], dtype=float)
        values = values[np.isfinite(values)]
        if values.size == 0:
            return None, None, ""
        unit = ""
        try:
            unit = str(wave_hdu.columns["VALUES"].unit or "")
        except Exception:
            pass
        return float(values.min()), float(values.max()), unit
    except (KeyError, TypeError, ValueError, AttributeError):
        return None, None, ""


def inspect_file(path):
    info = {"filename": path.name, "sha256": sha256_of(path),
            "valid": False, "error": ""}

    match = re.search(r"_spx_l2b-(v\d+)-(\d+-\d+)\.fits$", path.name)
    info["pipeline_version"] = match.group(1) if match else ""
    info["processing_batch"] = match.group(2) if match else ""

    try:
        with fits.open(path, memmap=False) as hdul:
            hdul.verify("exception")
            if len(hdul) < 2:
                raise ValueError("Invalid FITS structure.")

            info["date_obs"] = header_value(hdul, "DATE-OBS")
            info["mjd_obs"] = header_value(hdul, "MJD-OBS")
            detector = header_value(hdul, "DETECTOR")
            info["detector"] = detector
            info["header_version"] = header_value(hdul, "VERSION")

            image = hdul["IMAGE"]
            if image.data is None:
                raise ValueError("IMAGE extension has no data.")
            height, width = image.data.shape[-2:]
            info.update(image_width=int(width), image_height=int(height),
                        image_unit=image.header.get("BUNIT"))

            wmin, wmax, wunit = wavelength_info(hdul)
            info.update(wavelength_min=wmin, wavelength_max=wmax,
                        wavelength_unit=wunit)

            # The files have no BANDPASS keyword (the old column was empty).
            # The archive's bandpass names are SPHEREx-D<detector>; this
            # matched the archive for all 20 earlier files.
            if detector is not None:
                info["bandpass"] = f"SPHEREx-D{int(detector)}"
                info["bandpass_source"] = "derived_from_DETECTOR"

            info["valid"] = True
    except Exception as error:
        info["error"] = str(error)[:300]

    return info


def build_readme(master, included, counts, pipeline_versions, n_batches,
                 detection=None):
    lines = [
        "# SPHEREx target dataset",
        "",
        f"{len(included)} validated Level 2 FITS cutouts for "
        f"{len(master)} targets.",
        "",
        "## Contents",
        "- fits/                      validated FITS cutouts",
        "- metadata/clean_dataset_manifest_final.csv  one row per FITS file",
        "- metadata/target_astrometry_master.csv      adopted astrometry",
        "- metadata/rw_aur_component_reference.csv    RW Aur A/B details",
        "- metadata/target_coordinates_per_observation.csv  position at each DATE-OBS",
        "- metadata/fits_coverage_validation.csv     pixel position / edge checks",
        "- metadata/duplicate_audit_final.csv, excluded_files_final.csv",
        "- SHA256SUMS.txt",
        "",
        "## Targets and astrometry",
    ]
    for key, row in master.items():
        lines.append(
            f"- {row['target_name']} ({key}): {row['source_catalogue']} "
            f"{row['source_id']}, epoch {row['ref_epoch_jyear']}, "
            f"flag {row['quality_flag']}"
        )
    lines += [
        "",
        "## Assumptions and limitations",
        "- Cutouts are centred on the target position propagated to each "
        "observation date (proper motion; parallax and RV where available).",
        "- WISE 0855 uses CatWISE2020 J085508.34-071439.2 at epoch 2015.405; "
        "position uncertainty is ~2 arcsec by 2026.",
        "- Epsilon Indi B is provisional (high Gaia RUWE); Ba/Bb are treated "
        "as one combined source.",
        "- RW Aur A and B are ~1.5 arcsec apart and unresolved by SPHEREx.",
        "- Missing radial velocities (Epsilon Indi B, R Draconis) are set to "
        "zero; the effect is far below one pixel.",
        "- Being inside an image does not prove the source was detected; see "
        "detection_check.csv if it was produced.",
        "- 'bandpass' is derived from the DETECTOR header value.",
        f"- Pipeline version(s) in filenames: {', '.join(sorted(pipeline_versions))}; "
        f"{n_batches} distinct processing-batch suffixes (probably "
        "year-day-of-year of processing; not confirmed against IRSA docs).",
        "",
        "## Coverage summary",
        "- " + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())),
        "",
    ]
    if detection:
        lines += [
            "## Detection check (detection_check.csv)",
            "Brightest-pixel SNR at the predicted position, compared with "
            "random control positions in the same image. A coarse screen, "
            "not photometry.",
        ]
        for key, verdicts in sorted(detection.items()):
            lines.append(f"- {key}: " + ", ".join(
                f"{v}={n}" for v, n in sorted(verdicts.items())))
        lines += [
            "- DETECTED_CANDIDATE = clearly above random positions; "
            "ABOVE_THRESHOLD_NOT_UNUSUAL = not distinguishable from field "
            "noise or neighbouring stars (not a detection); NOT_DETECTED = "
            "SNR below 5.",
            "",
        ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-package", action="store_true")
    args = parser.parse_args()

    meta_dir = metadata_dir()
    master = load_master(meta_dir)

    cov_path = meta_dir / "fits_coverage_validation.csv"
    if not cov_path.exists():
        raise SystemExit("Run build_coverage_outputs.py first.")
    coverage = {r["filename"]: r for r in read_csv(cov_path)}

    infos = [inspect_file(p) for p in sorted(OBSERVATION_DIR.glob("*.fits"))]
    for info in infos:
        info["target_key"] = target_key_for(info["filename"], master)

    # ---- duplicates (identical bytes) ----
    groups = defaultdict(list)
    for info in infos:
        groups[info["sha256"]].append(info)

    duplicate_rows, duplicate_of = [], {}
    group_number = 0
    for sha, members in groups.items():
        if len(members) < 2:
            continue
        group_number += 1
        members.sort(key=lambda i: (i["target_key"] is None, i["filename"]))
        keeper = members[0]
        for member in members:
            role = "KEEP" if member is keeper else "DUPLICATE"
            if member is not keeper:
                duplicate_of[member["filename"]] = keeper["filename"]
            duplicate_rows.append({"group": group_number, "sha256": sha,
                                   "filename": member["filename"],
                                   "role": role,
                                   "target_key": member["target_key"] or ""})

    # ---- include / exclude ----
    included, excluded = [], []
    for info in infos:
        name, key = info["filename"], info["target_key"]
        reasons = []

        if key is None:
            reasons.append("Not a project target")
        if not info["valid"]:
            reasons.append(f"Invalid FITS: {info['error']}")
        if name in duplicate_of:
            reasons.append(f"Exact duplicate of {duplicate_of[name]}")
        if key is not None:
            cov = coverage.get(name)
            if cov is None:
                reasons.append("No coverage result (rerun build_coverage_outputs.py)")
            elif cov["status"] not in ("INSIDE_IMAGE", "EDGE"):
                reasons.append(f"Coverage status {cov['status']}")

        if reasons:
            excluded.append({"filename": name, "target_key": key or "",
                             "sha256": info["sha256"],
                             "exclusion_reason": "; ".join(reasons)})
            continue

        cov = coverage[name]
        entry = master[key]
        flags = []
        if cov["status"] == "EDGE":
            flags.append("TARGET_NEAR_IMAGE_EDGE")
        if entry["quality_flag"].startswith(("PROVISIONAL", "GAIA_RUWE")):
            flags.append("ASTROMETRY_CAUTION")

        info.update(
            package_path=f"fits/{name}", target_name=entry["target_name"],
            astrometry_source=f"{entry['source_catalogue']} {entry['source_id']}",
            astrometry_quality_flag=entry["quality_flag"],
            coverage_status=cov["status"], pixel_x=cov["pixel_x"],
            pixel_y=cov["pixel_y"], edge_distance_px=cov["edge_distance_px"],
            flags=";".join(flags))
        included.append(info)

    write_csv(meta_dir / "clean_dataset_manifest_final.csv",
              MANIFEST_FIELDS, included)
    write_csv(meta_dir / "excluded_files_final.csv",
              EXCLUDED_FIELDS, excluded)
    write_csv(meta_dir / "duplicate_audit_final.csv",
              DUPLICATE_FIELDS, duplicate_rows)

    # ---- summary ----
    per_target = defaultdict(int)
    for info in included:
        per_target[info["target_key"]] += 1
    counts = defaultdict(int)
    for info in included:
        counts[info["coverage_status"]] += 1
    pipeline_versions = {i["pipeline_version"] for i in included}
    batches = {i["processing_batch"] for i in included}

    summary = [
        f"Files scanned: {len(infos)}",
        f"Included: {len(included)}",
        f"Excluded: {len(excluded)}",
        "Per target: " + ", ".join(f"{k}={v}" for k, v in sorted(per_target.items())),
        "Coverage: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())),
        f"Pipeline versions: {sorted(pipeline_versions)}",
        f"Distinct processing batches: {len(batches)}",
        f"Duplicate groups: {group_number}",
        "Targets with no included file: "
        + (", ".join(k for k in master if per_target[k] == 0) or "none"),
    ]
    (meta_dir / "dataset_summary.txt").write_text("\n".join(summary) + "\n",
                                                  encoding="utf-8")
    print("\n".join(summary))
    for row in excluded:
        print(f"  EXCLUDED {row['filename']}: {row['exclusion_reason']}")

    if len(pipeline_versions) > 1:
        print("WARNING: more than one pipeline version among included files.")

    # ---- package ----
    if args.no_package:
        return

    (PACKAGE_DIR / "fits").mkdir(parents=True, exist_ok=True)
    (PACKAGE_DIR / "metadata").mkdir(parents=True, exist_ok=True)

    for info in included:
        src = OBSERVATION_DIR / info["filename"]
        dst = PACKAGE_DIR / "fits" / info["filename"]
        if not dst.exists() or dst.stat().st_size != src.stat().st_size:
            shutil.copy2(src, dst)

    for name in ["clean_dataset_manifest_final.csv", "excluded_files_final.csv",
                 "duplicate_audit_final.csv", "target_astrometry_master.csv",
                 "rw_aur_component_reference.csv",
                 "target_coordinates_per_observation.csv",
                 "fits_coverage_validation.csv", "detection_check.csv",
                 "dataset_summary.txt"]:
        src = meta_dir / name
        if src.exists():
            shutil.copy2(src, PACKAGE_DIR / "metadata" / name)

    detection = {}
    det_path = meta_dir / "detection_check.csv"
    if det_path.exists():
        names = {i["filename"] for i in included}
        for row in read_csv(det_path):
            if row["filename"] in names:
                bucket = detection.setdefault(row["target_key"], {})
                bucket[row["verdict"]] = bucket.get(row["verdict"], 0) + 1

    (PACKAGE_DIR / "README.md").write_text(
        build_readme(master, included, counts, pipeline_versions, len(batches),
                     detection),
        encoding="utf-8")

    lines = []
    for path in sorted(PACKAGE_DIR.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            lines.append(f"{sha256_of(path)}  {path.relative_to(PACKAGE_DIR).as_posix()}")
    (PACKAGE_DIR / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n",
                                                encoding="utf-8")
    print("Package written to:", PACKAGE_DIR)


if __name__ == "__main__":
    main()