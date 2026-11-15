
import csv
from pathlib import Path
from urllib.parse import urljoin

from astropy.table import Table
from astroquery.ipac.irsa import Irsa

# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
METADATA_DIR = BASE_DIR / "data" / "metadata"

PRODUCT_IDENTIFIER = "2026W24_2B_0242_4D3"

FAILED_FILENAME = (
    "R_Draconis_ad99d16f_level2_2026W24_2B_0242_4D3_"
    "spx_l2b-v27-2026-272.fits"
)

IRSA_BASE_URL = "https://irsa.ipac.caltech.edu/"

# Same values used in your original main.py
RA = 248.16724159
DEC = 66.75502282
CUTOUT_SIZE = 0.1

# ============================================================
# STEP 1: SEARCH SAVED METADATA
# ============================================================

print("=" * 65)
print("FIND R DRACONIS DOWNLOAD URL")
print("=" * 65)

found = False

for csv_file in METADATA_DIR.glob("*.csv"):

    try:
        with open(csv_file, newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)

            for row in reader:
                filename = row.get("filename", "")

                if (
                    FAILED_FILENAME in filename
                    or PRODUCT_IDENTIFIER in filename
                ):
                    print("\nProduct found in saved metadata:")
                    print("Metadata file:", csv_file)
                    print("Filename:", filename)
                    print("Source URI:", row.get("source_uri"))
                    print("Cutout URL:", row.get("cutout_url"))

                    if row.get("cutout_url"):
                        print("\nEXACT DOWNLOAD URL:")
                        print(row["cutout_url"])
                        found = True
                        break

        if found:
            break

    except Exception as error:
        print("Could not read", csv_file.name, error)

# ============================================================
# STEP 2: QUERY SPHEREX TAP IF URL WAS NOT SAVED
# ============================================================

if not found:

    print("\nURL not found in saved CSV files.")
    print("Searching SPHEREx TAP archive...")

    query = f"""
    SELECT
        a.uri AS source_uri,
        p.planeid AS plane_id,
        p.time_bounds_lower AS observation_date,
        p.energy_bandpassname AS bandpass

    FROM spherex.artifact a

    JOIN spherex.plane p
    ON a.planeid = p.planeid

    WHERE p.planeid LIKE '%2026W24_2B_0242%'

    ORDER BY p.time_bounds_lower
    """

    try:
        results = Irsa.query_tap(query).to_table()

        print("\nMatching archive records:", len(results))

        for row in results:

            source_uri = str(row["source_uri"])
            plane_id = str(row["plane_id"])

            print("\nPlane ID:", plane_id)
            print("Source URI:", source_uri)

            if PRODUCT_IDENTIFIER in source_uri or (
                "2026W24_2B_0242" in plane_id
            ):

                if source_uri.startswith("http"):
                    base = source_uri
                else:
                    base = urljoin(
                        IRSA_BASE_URL,
                        source_uri.lstrip("/")
                    )

                cutout_url = (
                    f"{base}?center={RA:.8f},{DEC:.8f}d"
                    f"&size={CUTOUT_SIZE}"
                )

                print("\nPOSSIBLE MATCHING CUTOUT URL:")
                print(cutout_url)

                with open(
                    METADATA_DIR / "rdraconis_recovered_url.txt",
                    "w",
                    encoding="utf-8"
                ) as file:
                    file.write(cutout_url)

                print("\nURL saved to:")
                print(METADATA_DIR / "rdraconis_recovered_url.txt")

                found = True

        if not found:
            print(
                "\nNo matching product found. "
                "Check the returned plane IDs and source URIs."
            )

    except Exception as error:
        print("\nTAP archive query failed:", error)

print("\n" + "=" * 65)
print("SEARCH FINISHED")
print("=" * 65)
