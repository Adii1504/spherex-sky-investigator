
from astroquery.simbad import Simbad
import pandas as pd
from pathlib import Path


# --------------------------------------------------
# 1. CONNECT TO SIMBAD
# --------------------------------------------------

simbad = Simbad()
simbad.server = "simbad.harvard.edu"

# Request individual proper-motion measurements
simbad.add_votable_fields("mesPM")


# --------------------------------------------------
# 2. TARGETS
# --------------------------------------------------

targets = [
    "Barnard's Star",
    "Epsilon Indi B",
    "WISE J085510.83-071442.5",
    "RW Aurigae",
    "R Draconis"
]


# --------------------------------------------------
# 3. RETRIEVE PROPER-MOTION MEASUREMENTS
# --------------------------------------------------

records = []

for name in targets:

    print("\n" + "=" * 65)
    print("Searching:", name)

    try:

        result = simbad.query_object(name)

        if result is None or len(result) == 0:
            print("No measurements found.")
            continue

        for row in result:

            record = {
                "target_name": name,
                "resolved_name": str(row["main_id"]).strip(),
                "pmra_mas_yr": row["mespm.pmra"],
                "pmdec_mas_yr": row["mespm.pmde"],
                "pm_coordinate_system": row["mespm.coosystem"],
                "proper_motion_reference": row["mespm.bibcode"]
            }

            records.append(record)

            print("\nProper-motion measurement:")
            for key, value in record.items():
                print(key, ":", value)

    except Exception as e:

        print("Error searching:", name)
        print("Reason:", str(e))


# --------------------------------------------------
# 4. SAVE RESULTS
# --------------------------------------------------

output_directory = Path("data/metadata")
output_directory.mkdir(parents=True, exist_ok=True)

output_file = output_directory / "proper_motion_measurements.csv"

if records:

    df = pd.DataFrame(records)

    df.to_csv(
        output_file,
        index=False
    )

    print("\n" + "=" * 65)
    print("PROPER-MOTION RETRIEVAL COMPLETED")
    print("=" * 65)

    print("Measurements retrieved:", len(df))
    print("\n", df.to_string(index=False))

    print("\nSaved:", output_file.resolve())

else:

    print("\nNo proper-motion measurements retrieved.")
