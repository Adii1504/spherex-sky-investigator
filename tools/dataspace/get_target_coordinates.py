
from astroquery.simbad import Simbad
import pandas as pd
from pathlib import Path


# --------------------------------------------------
# 1. CONNECT TO SIMBAD
# --------------------------------------------------

simbad = Simbad()

# Use the Harvard SIMBAD mirror
simbad.server = "simbad.harvard.edu"

# Request proper-motion information
simbad.add_votable_fields("propermotions")


# --------------------------------------------------
# 2. DEFINE TARGET OBJECTS
# --------------------------------------------------

targets = [
    {
        "target_name": "Barnard's Star",
        "search_name": "Barnard's Star",
        "target_component": "Star"
    },
    {
        "target_name": "Epsilon Indi B",
        "search_name": "Epsilon Indi B",
        "target_component": "Combined Ba/Bb system"
    },
    {
        "target_name": "WISE 0855",
        "search_name": "WISE J085510.83-071442.5",
        "target_component": "WISE 0855"
    },
    {
        "target_name": "RW Aurigae",
        "search_name": "RW Aurigae",
        "target_component": "RW Aur system"
    },
    {
        "target_name": "R Draconis",
        "search_name": "R Draconis",
        "target_component": "Star"
    }
]


# --------------------------------------------------
# 3. HELPER FUNCTIONS
# --------------------------------------------------

def get_value(row, column):
    """
    Safely retrieve a value from a SIMBAD result.
    Missing or masked values are returned as None.
    """

    try:
        value = row[column]

        if value is None:
            return None

        if pd.isna(value):
            return None

        return value

    except (KeyError, TypeError, ValueError):
        return None


def get_float(row, column):
    """
    Retrieve a numeric value safely.
    """

    value = get_value(row, column)

    if value is None:
        return None

    try:
        return float(value)

    except (TypeError, ValueError):
        return None


# --------------------------------------------------
# 4. SEARCH FOR TARGET COORDINATES
# --------------------------------------------------

records = []

for target in targets:

    name = target["target_name"]
    search_name = target["search_name"]

    print("\n" + "=" * 65)
    print("Searching:", name)

    try:

        result = simbad.query_object(search_name)

        if result is None or len(result) == 0:
            print("Object not found:", search_name)
            continue

        row = result[0]

        # ------------------------------------------
        # Extract coordinates
        # ------------------------------------------

        ra = get_float(row, "ra")
        dec = get_float(row, "dec")

        if ra is None or dec is None:
            print("Coordinates unavailable:", name)
            continue

        # ------------------------------------------
        # Extract proper motion
        # ------------------------------------------

        pmra = get_float(row, "pmra")
        pmdec = get_float(row, "pmdec")

        # ------------------------------------------
        # Extract coordinate uncertainties
        # SIMBAD reports these in milliarcseconds
        # ------------------------------------------

        error_major = get_float(row, "coo_err_maj")
        error_minor = get_float(row, "coo_err_min")
        error_angle = get_float(row, "coo_err_angle")

        # ------------------------------------------
        # Extract coordinate reference
        # ------------------------------------------

        coordinate_reference = get_value(
            row, "coo_bibcode"
        )

        coordinate_wavelength = get_value(
            row, "coo_wavelength"
        )

        # ------------------------------------------
        # Create target record
        # ------------------------------------------

        record = {

            # Target identification
            "target_name": name,
            "resolved_name": str(row["main_id"]).strip(),
            "target_component": target["target_component"],

            # Coordinates
            "ra_deg": ra,
            "dec_deg": dec,
            "coordinate_frame": "ICRS",

            # Coordinate epoch
            "coordinate_epoch_jyear": None,
            "epoch_status": "UNVERIFIED",

            # Proper motion
            "pmra_mas_yr": pmra,
            "pmdec_mas_yr": pmdec,
            "proper_motion_unit": "mas/year",

            # Coordinate uncertainties
            "coordinate_error_major_mas": error_major,
            "coordinate_error_minor_mas": error_minor,
            "coordinate_error_angle_deg": error_angle,
            "coordinate_error_unit": "mas",

            # Coordinate reference information
            "coordinate_reference": (
                str(coordinate_reference).strip()
                if coordinate_reference is not None
                else None
            ),

            "coordinate_wavelength": coordinate_wavelength,

            # Source
            "coordinate_source": "SIMBAD Harvard mirror"
        }

        records.append(record)

        # ------------------------------------------
        # Display results
        # ------------------------------------------

        print("Resolved name:", record["resolved_name"])
        print("Target component:", record["target_component"])

        print("RA:", ra, "degrees")
        print("Dec:", dec, "degrees")

        print("Proper motion RA:", pmra, "mas/year")
        print("Proper motion Dec:", pmdec, "mas/year")

        print("Coordinate reference:", coordinate_reference)

        print("Coordinate error major:", error_major, "mas")
        print("Coordinate error minor:", error_minor, "mas")

        print("Coordinate wavelength:", coordinate_wavelength)
        print("Coordinate epoch: UNVERIFIED")

    except Exception as e:

        print("Error searching:", name)
        print("Reason:", str(e))


# --------------------------------------------------
# 5. SAVE RESULTS TO CSV
# --------------------------------------------------

output_directory = Path("data/metadata")
output_directory.mkdir(parents=True, exist_ok=True)

output_file = output_directory / "target_coordinates.csv"

if records:

    df = pd.DataFrame(records)

    df.to_csv(
        output_file,
        index=False,
        na_rep=""
    )

    print("\n" + "=" * 65)
    print("COORDINATE RETRIEVAL COMPLETED")
    print("=" * 65)

    print("Targets retrieved:", len(df))

    print("\nRetrieved target information:")
    print(df.to_string(index=False))

    print("\nCSV file saved successfully:")
    print(output_file.resolve())

    print("\nIMPORTANT:")
    print("Coordinate epochs have not been verified.")
    print("Proper-motion propagation has NOT been performed.")

else:

    print("\nNo target coordinates were retrieved.")
    print("No CSV file was generated.")
