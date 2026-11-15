"""Import the supplied SPHEREx final_dataset without running its research scripts.

Only checksum-verified, manifest-listed products are registered. Source files are
read only; registry publication happens after every product has been validated.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import shutil

import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time

from .config import Settings
from .fits_preview.reader import read
from .fits_preview.routes import validate_position


TARGET_IDS = {
    "Barnards_Star": "barnards-star", "Epsilon_Indi_B": "epsilon-indi-b",
    "WISE_0855": "wise-0855", "RW_Aurigae": "rw-aurigae", "R_Draconis": "r-draconis",
}
SCREEN_NOTE = (
    "Supplied brightest-pixel/background screen with random controls; not confirmed "
    "source identification or photometry. FLAGS were not used by this screen."
)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_path(root, name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name:
        raise ValueError("Package contains an unsafe path")
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"Missing package file: {name}")
    return path


def number(value):
    if value in (None, ""):
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Nonfinite dataset number")
    return result


def table(package, name, checksums, key):
    relative = "metadata/" + name
    if relative not in checksums:
        raise ValueError(f"Missing checksummed metadata: {name}")
    with safe_path(package, relative).open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    result = {}
    for row in rows:
        if not row.get(key) or row[key] in result:
            raise ValueError(f"Missing or duplicate {key} in {name}")
        result[row[key]] = row
    return result


def verify_package(package):
    checksums = {}
    for line in (package / "SHA256SUMS.txt").read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        digest, name = line.split("  ", 1)
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest) or name in checksums:
            raise ValueError("Invalid or duplicate package checksum")
        if sha256(safe_path(package, name)) != digest:
            raise ValueError(f"Checksum mismatch: {name}")
        checksums[name] = digest
    if not checksums:
        raise ValueError("Empty dataset package")
    return checksums


def import_dataset(source, root=None):
    source = Path(source).resolve(strict=True)
    package = source / "final_dataset" if (source / "final_dataset").is_dir() else source
    checksums = verify_package(package)
    manifest = table(package, "clean_dataset_manifest_final.csv", checksums, "filename")
    master = table(package, "target_astrometry_master.csv", checksums, "target_key")
    coordinates = table(package, "target_coordinates_per_observation.csv", checksums, "filename")
    coverage = table(package, "fits_coverage_validation.csv", checksums, "filename")
    detections = table(package, "detection_check.csv", checksums, "filename")
    if not manifest:
        raise ValueError("No products in dataset manifest")
    root = Path(root or Settings.from_env().output_dir.resolve().parent).resolve()
    if root.is_relative_to(source) or source.is_relative_to(root):
        raise ValueError("Import destination must be separate from the source")
    identity = hashlib.sha256(json.dumps(checksums, sort_keys=True).encode()).hexdigest()
    relative_root = Path("datasets") / ("dataspace-" + identity[:20])
    destination = root / relative_root
    planned = {}
    for filename, row in manifest.items():
        key = row["target_key"]
        if key not in TARGET_IDS or key not in master:
            raise ValueError(f"Unknown target in manifest: {key}")
        if filename != Path(filename).name or row["package_path"] != "fits/" + filename:
            raise ValueError("Unexpected manifest product path")
        if checksums.get(row["package_path"]) != row["sha256"]:
            raise ValueError(f"Manifest checksum mismatch: {filename}")
        coord, cov, screen = coordinates[filename], coverage[filename], detections.get(filename)
        if any(item["target_key"] != key for item in (coord, cov)) or (screen and screen["target_key"] != key):
            raise ValueError(f"Mismatched target association: {filename}")
        if cov["status"] not in ("INSIDE_IMAGE", "EDGE") or row["coverage_status"] != cov["status"]:
            raise ValueError(f"Unapproved coverage: {filename}")
        position = validate_position({"ra_deg": number(coord["ra_at_obs_deg"]),
            "dec_deg": number(coord["dec_at_obs_deg"]), "astrometry_status": coord["quality_flag"]})
        if position["ra_deg"] is None or position["dec_deg"] is None:
            raise ValueError(f"Missing predicted position: {filename}")
        frame = read(safe_path(package, row["package_path"]))
        if frame.image is None or frame.wcs is None:
            raise ValueError(f"Missing science image or celestial WCS: {filename}")
        height, width = frame.image.shape
        if (width, height) != (int(row["image_width"]), int(row["image_height"])):
            raise ValueError(f"Image dimensions disagree with manifest: {filename}")
        date = frame.metadata["DATE-OBS"]
        if not date or date["value"] != row["date_obs"] or coord["date_obs"] != row["date_obs"]:
            raise ValueError(f"Observation dates disagree: {filename}")
        if abs(Time(row["date_obs"], scale="utc").mjd - float(coord["mjd_obs"])) > 1e-7:
            raise ValueError(f"Observation MJD disagrees: {filename}")
        x, y = (float(v) for v in frame.wcs.world_to_pixel(SkyCoord(
            position["ra_deg"] * u.deg, position["dec_deg"] * u.deg, frame="icrs")))
        edge = min(x+.5, width-.5-x, y+.5, height-.5-y)
        if not math.isfinite(edge) or edge < 0 or abs(x-float(cov["pixel_x"])) > .01 or abs(y-float(cov["pixel_y"])) > .01:
            raise ValueError(f"Prediction disagrees with FITS coverage: {filename}")
        corners = frame.wcs.pixel_to_world([-.5,width-.5,width-.5,-.5],[-.5,-.5,height-.5,height-.5]).icrs
        footprint = "POLYGON ICRS " + " ".join(f"{ra:.10f} {dec:.10f}" for ra, dec in zip(corners.ra.deg,corners.dec.deg))
        wave = {"min": number(row["wavelength_min"]), "max": number(row["wavelength_max"]),
                "unit": row["wavelength_unit"] or None, "source": "supplied WCS-WAVE table extrema"}
        wave_um = None
        if wave["unit"] and wave["min"] is not None and wave["max"] is not None:
            unit = u.Unit(wave["unit"])
            wave_um = [(wave[k] * unit).to_value(u.um) for k in ("min", "max")]
        adopted = dict(master[key])  # Identifiers remain strings (Gaia IDs exceed JS integer precision).
        screen_data = None if not screen else {"verdict": screen["verdict"], "note": screen["note"],
            "method_note": SCREEN_NOTE, **{field: number(screen.get(field)) for field in (
                "snr_peak", "control_n", "control_p99_snr", "control_fraction_ge_threshold",
                "centroid_dx", "centroid_dy", "brightest_within_12px_dist_px")}}
        product_id = "dataspace-" + row["sha256"][:20]
        if product_id in planned:
            raise ValueError("Duplicate FITS bytes in final manifest")
        planned[product_id] = {"path": (relative_root / row["package_path"]).as_posix(),
            "target_id": TARGET_IDS[key], "label": filename, "sha256": row["sha256"],
            "provisional": True, "provenance_status": "Supplied target association; FITS coverage checked; source identification unconfirmed",
            "predicted_position": position, "footprint_stcs": footprint,
            "dataset": {"name": "SPHEREx dataspace", "package_sha256": identity,
                "filename": filename, "adopted_astrometry": adopted,
                "propagation": {"method": coord["method"], "rv_status": coord["rv_status"],
                    "time_scale_assumption": "UTC (as used by supplied scripts)",
                    "note": "Space-motion prediction; not observer-dependent annual parallax or a measured centroid."},
                "coverage": {"status": cov["status"], "pixel_x": x, "pixel_y": y,
                    "edge_distance_px": edge, "note": "Coverage is not detection."},
                "detection_screen": screen_data, "flags": row["flags"],
                "pipeline_version": row["pipeline_version"]},
            "observation": {"observed_at": row["date_obs"],
                "time_scale": (frame.metadata["TIMESYS"] or {}).get("value"),
                "detector": (frame.metadata["DETECTOR"] or {}).get("value"),
                "file_wavelength_um": wave_um, "file_wavelength": wave, "position_wavelength_um": None}}
    # Validate the whole package and existing registry before writing anything.
    registry_path = root / "fits_manifest.json"
    entries = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.is_file() else {}
    for product_id, entry in planned.items():
        if product_id in entries and entries[product_id] != entry:
            raise ValueError(f"Existing product metadata conflicts: {product_id}")
    for name, digest in checksums.items():
        output = destination / name
        output.parent.mkdir(parents=True, exist_ok=True)
        if not output.is_file() or sha256(output) != digest:
            temporary = output.with_suffix(output.suffix + ".tmp")
            shutil.copyfile(safe_path(package, name), temporary)
            if sha256(temporary) != digest:
                raise ValueError("Source changed during import")
            temporary.replace(output)
    shutil.copyfile(package / "SHA256SUMS.txt", destination / "SHA256SUMS.txt")
    entries.update(planned)
    root.mkdir(parents=True, exist_ok=True)
    temporary = registry_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(entries, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(registry_path)
    return {"products": len(planned), "targets": len({e["target_id"] for e in planned.values()}),
            "package": str(destination), "package_sha256": identity}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="dataspace folder or final_dataset folder")
    parser.add_argument("--root", type=Path, help="Registry/data root (default: configured .data)")
    args = parser.parse_args()
    try:
        print(json.dumps(import_dataset(args.source, args.root), indent=2))
        print("Restart the backend to load the imported products.")
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(1, f"Dataset import failed: {exc}\n")


if __name__ == "__main__":
    main()
