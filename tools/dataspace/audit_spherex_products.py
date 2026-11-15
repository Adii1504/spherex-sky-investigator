
from pathlib import Path
import csv
import hashlib
import re
from collections import defaultdict

from astropy.io import fits


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

OBSERVATION_DIR = BASE_DIR / "data" / "observations"
METADATA_DIR = BASE_DIR / "data" / "metadata"

OUTPUT_FILE = METADATA_DIR / "product_audit_report.csv"


# =========================================================
# TARGET NAMES
# =========================================================

TARGET_NAMES = [
    "Barnards_Star",
    "Epsilon_Indi_B",
    "WISE_0855",
    "RW_Aurigae",
    "R_Draconis"
]


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def identify_target(filename):

    for target in TARGET_NAMES:
        if filename.startswith(target + "_"):
            return target

    return "UNKNOWN"


def calculate_sha256(file_path):

    sha256 = hashlib.sha256()

    with open(file_path, "rb") as file:

        for block in iter(
            lambda: file.read(1024 * 1024),
            b""
        ):
            sha256.update(block)

    return sha256.hexdigest()


def extract_product_name(filename):

    match = re.search(
        r"(level2_.+\.fits)$",
        filename
    )

    if match:
        return match.group(1)

    return filename


def extract_product_information(product_name):

    # Remove processing version and build information.
    match = re.match(
        r"(level2_.+?)_spx_l2b-v(\d+)-(\d+)\.fits$",
        product_name
    )

    if match:

        observation_key = match.group(1)
        processing_version = (
            "v{}-{}".format(match.group(2), match.group(3))
        )

    else:

        observation_key = product_name
        processing_version = "UNKNOWN"

    return observation_key, processing_version


def read_fits_metadata(file_path):

    try:

        with fits.open(
            file_path,
            mode="readonly",
            memmap=False
        ) as hdul:

            date_obs = None
            mjd_obs = None
            detector = None
            bandpass = None

            for hdu in hdul:

                date_obs = date_obs or hdu.header.get("DATE-OBS")
                mjd_obs = mjd_obs or hdu.header.get("MJD-OBS")
                detector = detector or hdu.header.get("DETECTOR")
                bandpass = bandpass or hdu.header.get("BANDPASS")

            return {
                "observation_date": date_obs,
                "mjd_obs": mjd_obs,
                "detector": detector,
                "bandpass": bandpass,
                "fits_status": "VALID"
            }

    except Exception as error:

        return {
            "observation_date": None,
            "mjd_obs": None,
            "detector": None,
            "bandpass": None,
            "fits_status": "ERROR: " + str(error)
        }


# =========================================================
# AUDIT ONE FILE
# =========================================================

def audit_file(file_path):

    product_name = extract_product_name(file_path.name)

    observation_key, processing_version = (
        extract_product_information(product_name)
    )

    metadata = read_fits_metadata(file_path)

    return {

        "filename": file_path.name,
        "target": identify_target(file_path.name),

        "product_name": product_name,
        "observation_key": observation_key,
        "processing_version": processing_version,

        "sha256": calculate_sha256(file_path),
        "file_size_bytes": file_path.stat().st_size,

        "observation_date": metadata["observation_date"],
        "mjd_obs": metadata["mjd_obs"],

        "detector": metadata["detector"],
        "bandpass": metadata["bandpass"],

        "fits_status": metadata["fits_status"],

        "exact_duplicate": "NO",
        "repeated_product": "NO",
        "multiple_processing_versions": "NO"
    }


# =========================================================
# MAIN AUDIT
# =========================================================

def main():

    print("=" * 65)
    print("SPHEREx PRODUCT DUPLICATE AND REPROCESSING AUDIT")
    print("=" * 65)

    METADATA_DIR.mkdir(parents=True, exist_ok=True)

    fits_files = sorted(
        OBSERVATION_DIR.rglob("*.fits")
    )

    print("FITS files found:", len(fits_files))

    if not fits_files:
        print("No FITS files found.")
        return

    reports = []

    for index, file_path in enumerate(fits_files, start=1):

        print("\nAuditing {}/{}".format(index, len(fits_files)))
        print(file_path.name)

        reports.append(audit_file(file_path))

    # -----------------------------------------------------
    # GROUP FILES BY CHECKSUM
    # -----------------------------------------------------

    checksum_groups = defaultdict(list)

    for row in reports:
        checksum_groups[row["sha256"]].append(row)

    exact_duplicate_groups = {
        key: rows
        for key, rows in checksum_groups.items()
        if len(rows) > 1
    }

    for rows in exact_duplicate_groups.values():

        for row in rows:
            row["exact_duplicate"] = "YES"

    # -----------------------------------------------------
    # GROUP BY PRODUCT NAME
    # -----------------------------------------------------

    product_groups = defaultdict(list)

    for row in reports:
        product_groups[row["product_name"]].append(row)

    repeated_product_groups = {
        key: rows
        for key, rows in product_groups.items()
        if len(rows) > 1
    }

    for rows in repeated_product_groups.values():

        for row in rows:
            row["repeated_product"] = "YES"

    # -----------------------------------------------------
    # GROUP BY OBSERVATION KEY
    # -----------------------------------------------------

    observation_groups = defaultdict(list)

    for row in reports:
        observation_groups[row["observation_key"]].append(row)

    reprocessing_groups = {}

    for key, rows in observation_groups.items():

        versions = {
            row["processing_version"]
            for row in rows
        }

        if len(versions) > 1:

            reprocessing_groups[key] = rows

            for row in rows:
                row["multiple_processing_versions"] = "YES"

    # -----------------------------------------------------
    # SAVE CSV
    # -----------------------------------------------------

    fieldnames = list(reports[0].keys())

    with open(
        OUTPUT_FILE,
        "w",
        newline="",
        encoding="utf-8"
    ) as csv_file:

        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerows(reports)

    # -----------------------------------------------------
    # PRINT SUMMARY
    # -----------------------------------------------------

    print("\n" + "=" * 65)
    print("AUDIT SUMMARY")
    print("=" * 65)

    print("Total files:", len(reports))

    print(
        "Unique SHA-256 checksums:",
        len(checksum_groups)
    )

    print(
        "Exact duplicate groups:",
        len(exact_duplicate_groups)
    )

    print(
        "Repeated product-name groups:",
        len(repeated_product_groups)
    )

    print(
        "Multiple processing-version groups:",
        len(reprocessing_groups)
    )

    print("\nEXACT DUPLICATES")

    if exact_duplicate_groups:

        for group_number, rows in enumerate(
            exact_duplicate_groups.values(),
            start=1
        ):

            print("\nGroup", group_number)

            for row in rows:
                print(" -", row["filename"])

    else:
        print("No exact duplicate files found.")

    print("\nREPEATED PRODUCT NAMES")

    if repeated_product_groups:

        for product_name, rows in repeated_product_groups.items():

            print("\nProduct:", product_name)

            for row in rows:
                print(" -", row["filename"])

    else:
        print("No repeated product names found.")

    print("\nMULTIPLE PROCESSING VERSIONS")

    if reprocessing_groups:

        for observation_key, rows in reprocessing_groups.items():

            print("\nObservation:", observation_key)

            for row in rows:

                print(
                    " -",
                    row["filename"],
                    "|",
                    row["processing_version"]
                )

    else:
        print("No multiple processing versions detected.")

    print("\n" + "=" * 65)
    print("AUDIT COMPLETED")
    print("=" * 65)

    print("\nReport saved to:")
    print(OUTPUT_FILE)


if __name__ == "__main__":
    main()
