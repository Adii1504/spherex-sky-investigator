
from pathlib import Path
import hashlib
import re

import numpy as np
import pandas as pd
from astropy.io import fits


# ============================================================
# SPHEREx CLEAN DATASET PREPARATION
# Member 1 - Archive data preparation
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
OBSERVATION_DIR = BASE_DIR / "data" / "observations"
METADATA_DIR = BASE_DIR / "data" / "metadata"

METADATA_DIR.mkdir(parents=True, exist_ok=True)

TARGETS = {
    "Barnard's Star": ["barnards_star"],
    "Epsilon Indi B": ["epsilon_indi_b"],
    "WISE 0855": ["wise_0855"],
    "RW Aurigae": ["rw_aurigae"],
    "R Draconis": ["r_draconis"],
}


def calculate_sha256(file_path):
    """Calculate the SHA-256 checksum of a file."""
    sha256 = hashlib.sha256()

    with open(file_path, "rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            sha256.update(block)

    return sha256.hexdigest()


def identify_target(filename):
    """Identify one of the five project targets from its filename."""
    name = filename.lower()

    for target, prefixes in TARGETS.items():
        for prefix in prefixes:
            if name.startswith(prefix):
                return target

    return None


def get_header_value(hdul, keyword):
    """Find a FITS header value across all HDUs."""
    for hdu in hdul:
        if keyword in hdu.header:
            return hdu.header[keyword]

    return None


def extract_wavelength_range(hdul):
    """Extract the minimum and maximum wavelength, if available."""
    try:
        wave_hdu = hdul["WCS-WAVE"]
        data = wave_hdu.data

        if data is None or "VALUES" not in data.names:
            return None, None

        values = np.asarray(data["VALUES"], dtype=float)
        values = values[np.isfinite(values)]

        if values.size == 0:
            return None, None

        return float(np.min(values)), float(np.max(values))

    except (KeyError, TypeError, ValueError, AttributeError):
        return None, None


def extract_fits_metadata(file_path):
    """Read useful metadata from a SPHEREx FITS product."""
    metadata = {
        "date_obs": None,
        "mjd_obs": None,
        "detector": None,
        "bandpass": None,
        "image_width": None,
        "image_height": None,
        "image_unit": None,
        "wavelength_min": None,
        "wavelength_max": None,
        "processing_version": None,
        "fits_valid": False,
        "error": None,
    }

    try:
        with fits.open(file_path, memmap=False) as hdul:
            hdul.verify("exception")

            metadata["date_obs"] = get_header_value(hdul, "DATE-OBS")
            metadata["mjd_obs"] = get_header_value(hdul, "MJD-OBS")
            metadata["detector"] = get_header_value(hdul, "DETECTOR")
            metadata["bandpass"] = get_header_value(hdul, "BANDPASS")

            try:
                image_hdu = hdul["IMAGE"]

                if image_hdu.data is not None:
                    height, width = image_hdu.data.shape[-2:]
                    metadata["image_width"] = int(width)
                    metadata["image_height"] = int(height)

                metadata["image_unit"] = image_hdu.header.get("BUNIT")

            except (KeyError, AttributeError, ValueError):
                pass

            wave_min, wave_max = extract_wavelength_range(hdul)
            metadata["wavelength_min"] = wave_min
            metadata["wavelength_max"] = wave_max

            metadata["fits_valid"] = True

    except Exception as error:
        metadata["error"] = str(error)

    # Processing version encoded in the filename, e.g. v27-2026-252
    match = re.search(r"_spx_l2b-(v\d+-\d+-\d+)\.fits$", file_path.name)

    if match:
        metadata["processing_version"] = match.group(1)

    return metadata


def extract_product_name(filename):
    """Extract the archive product name without a target-coordinate prefix."""
    match = re.search(r"(level2_.+?\.fits)$", filename)

    if match:
        return match.group(1)

    return filename


def main():
    print("=" * 65)
    print("SPHEREx CLEAN DATASET PREPARATION")
    print("=" * 65)

    if not OBSERVATION_DIR.exists():
        print("ERROR: Observation directory not found:")
        print(OBSERVATION_DIR)
        return

    fits_files = sorted(OBSERVATION_DIR.rglob("*.fits"))

    if not fits_files:
        print("No FITS files found.")
        return

    print(f"FITS files found: {len(fits_files)}")

    # First pass: calculate checksums to identify exact duplicates.
    checksum_groups = {}

    for file_path in fits_files:
        checksum = calculate_sha256(file_path)
        checksum_groups.setdefault(checksum, []).append(file_path)

    duplicate_files = set()

    for checksum, group in checksum_groups.items():
        if len(group) > 1:
            # Keep the shortest filename as the representative copy.
            # All copies have identical SHA-256 checksums.
            ordered = sorted(group, key=lambda p: (len(p.name), p.name))
            for duplicate in ordered[1:]:
                duplicate_files.add(duplicate)

    # Second pass: build metadata and inclusion decisions.
    records = []

    for index, file_path in enumerate(fits_files, start=1):
        print(f"\nProcessing {index}/{len(fits_files)}")
        print(file_path.name)

        target = identify_target(file_path.name)
        checksum = calculate_sha256(file_path)
        metadata = extract_fits_metadata(file_path)

        reasons = []

        if target is None:
            reasons.append("Not one of the five project targets")

        if file_path in duplicate_files:
            reasons.append("Exact duplicate file")

        if not metadata["fits_valid"]:
            reasons.append("FITS validation failed")

        included = len(reasons) == 0

        record = {
            "filename": file_path.name,
            "relative_path": str(file_path.relative_to(BASE_DIR)),
            "target": target if target else "UNKNOWN / OTHER",
            "product_name": extract_product_name(file_path.name),
            "sha256": checksum,
            "included_in_clean_dataset": included,
            "exclusion_reason": "; ".join(reasons) if reasons else "",
            **metadata,
        }

        records.append(record)

    audit_df = pd.DataFrame(records)

    # Save a complete inventory, including excluded files.
    audit_path = METADATA_DIR / "dataset_file_audit.csv"
    audit_df.to_csv(audit_path, index=False)

    # Save only validated files belonging to the five targets.
    clean_df = audit_df[
        audit_df["included_in_clean_dataset"] == True
    ].copy()

    clean_df = clean_df.sort_values(
        by=["target", "date_obs", "filename"],
        na_position="last"
    )

    manifest_path = METADATA_DIR / "clean_dataset_manifest.csv"
    clean_df.to_csv(manifest_path, index=False)

    # Save excluded files and the reason for exclusion.
    excluded_df = audit_df[
        audit_df["included_in_clean_dataset"] == False
    ].copy()

    excluded_path = METADATA_DIR / "excluded_files.csv"
    excluded_df.to_csv(excluded_path, index=False)

    # Print summary.
    print("\n" + "=" * 65)
    print("CLEAN DATASET SUMMARY")
    print("=" * 65)

    print(f"Total FITS files scanned: {len(audit_df)}")
    print(f"Files included: {len(clean_df)}")
    print(f"Files excluded: {len(excluded_df)}")
    print(f"Exact duplicate files excluded: {len(duplicate_files)}")

    print("\nFILES PER TARGET")

    for target in TARGETS:
        count = len(clean_df[clean_df["target"] == target])
        print(f"{target}: {count}")

    print("\nEXCLUDED FILES")

    if excluded_df.empty:
        print("None")
    else:
        for _, row in excluded_df.iterrows():
            print(f"- {row['filename']}")
            print(f"  Reason: {row['exclusion_reason']}")

    print("\nOUTPUT FILES")
    print(f"Clean manifest: {manifest_path}")
    print(f"Complete audit: {audit_path}")
    print(f"Excluded files: {excluded_path}")

    print("\n" + "=" * 65)
    print("DATASET PREPARATION COMPLETED")
    print("=" * 65)


if __name__ == "__main__":
    main()
