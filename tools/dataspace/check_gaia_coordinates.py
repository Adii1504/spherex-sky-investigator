
import astropy.units as u
import pandas as pd

from pathlib import Path
from astropy.coordinates import SkyCoord
from astroquery.gaia import Gaia


# --------------------------------------------------
# 1. CONFIGURE GAIA
# --------------------------------------------------

Gaia.MAIN_GAIA_TABLE = "gaiadr3.gaia_source"
Gaia.ROW_LIMIT = 50


# --------------------------------------------------
# 2. LOAD TARGET COORDINATES
# --------------------------------------------------

input_file = Path("data/metadata/target_coordinates.csv")

if not input_file.exists():
    raise FileNotFoundError(
        "target_coordinates.csv was not found."
    )

targets_df = pd.read_csv(input_file)

required_columns = [
    "target_name",
    "ra_deg",
    "dec_deg"
]

for column in required_columns:
    if column not in targets_df.columns:
        raise ValueError(
            f"Missing required column: {column}"
        )


# --------------------------------------------------
# 3. SEARCH GAIA DR3
# --------------------------------------------------

records = []

for _, target in targets_df.iterrows():

    name = target["target_name"]

    ra = float(target["ra_deg"])
    dec = float(target["dec_deg"])

    print("\n" + "=" * 70)
    print("Searching Gaia DR3:", name)

    try:

        coordinate = SkyCoord(
            ra=ra * u.degree,
            dec=dec * u.degree,
            frame="icrs"
        )

        job = Gaia.cone_search_async(
            coordinate,
            radius=30 * u.arcsec
        )

        results = job.get_results()

        if len(results) == 0:

            print("No Gaia DR3 candidates found.")

            records.append({
                "target_name": name,
                "gaia_source_id": None,
                "match_status": "NO GAIA MATCH"
            })

            continue

        print("Candidates found:", len(results))

        # Examine the closest candidates first
        results.sort("dist")

        for row in results:

            record = {
                "target_name": name,

                "gaia_source_id": str(
                    row["source_id"]
                ),

                "designation": str(
                    row["designation"]
                ),

                "ra_deg": float(row["ra"]),
                "dec_deg": float(row["dec"]),

                "reference_epoch": float(
                    row["ref_epoch"]
                ),

                "pmra_mas_yr": row["pmra"],
                "pmdec_mas_yr": row["pmdec"],

                "parallax_mas": row["parallax"],

                "radial_velocity_km_s": row[
                    "radial_velocity"
                ],

                "g_magnitude": row["phot_g_mean_mag"],

                "ruwe": row["ruwe"],

                "separation_arcsec": (
                    float(row["dist"]) * 3600
                ),

                "match_status": "CANDIDATE - VERIFY IDENTITY"
            }

            records.append(record)

            print("\nGaia candidate:")
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

output_file = (
    output_directory / "gaia_dr3_candidates.csv"
)

if records:

    df = pd.DataFrame(records)

    df.to_csv(
        output_file,
        index=False
    )

    print("\n" + "=" * 70)
    print("GAIA CROSS-MATCH COMPLETED")
    print("=" * 70)

    print("Total candidate records:", len(df))

    print("\nSaved:")
    print(output_file.resolve())

else:

    print("No results were retrieved.")
