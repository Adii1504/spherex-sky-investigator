
from pathlib import Path

import pandas as pd
import pyvo
from astroquery.gaia import Gaia


# ---------------------------------------------------------
# PATHS
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
METADATA_DIR = BASE_DIR / "data" / "metadata"
METADATA_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------
# TARGET COORDINATES
# ---------------------------------------------------------

TARGETS = {
    "WISE_0855": {
        "ra": 133.81890825,
        "dec": -7.247048,
        "radius_deg": 0.02
    },
    "Epsilon_Indi_B": {
        "ra": 331.076453,
        "dec": -56.793812,
        "radius_deg": 0.01
    },
    "RW_Aurigae": {
        "ra": 76.9565260346,
        "dec": 30.4014381739,
        "radius_deg": 0.02
    }
}


# ---------------------------------------------------------
# 1. QUERY CATWISE2020 FOR WISE 0855
# ---------------------------------------------------------

def query_catwise():

    print("\n" + "=" * 65)
    print("CATWISE2020: WISE 0855")
    print("=" * 65)

    target = TARGETS["WISE_0855"]

    service = pyvo.dal.TAPService(
        "https://irsa.ipac.caltech.edu/TAP"
    )

    query = f"""
    SELECT TOP 100
        source_name,
        source_id,
        ra,
        dec,
        ra_pm,
        dec_pm,
        PMRA,
        PMDec,
        MeanObsMJD,
        pmcode,
        sigra_pm,
        sigdec_pm,
        sigPMRA,
        sigPMDec,
        w1snr_pm,
        w2snr_pm
    FROM catwise_2020
    WHERE 1 = CONTAINS(
        POINT('ICRS', ra, dec),
        CIRCLE(
            'ICRS',
            {target['ra']},
            {target['dec']},
            {target['radius_deg']}
        )
    )
    """

    try:
        result = service.search(query).to_table()
        df = result.to_pandas()

        output = METADATA_DIR / "wise0855_catwise_candidates.csv"
        df.to_csv(output, index=False)

        print("Candidates found:", len(df))
        print(df.head(20).to_string(index=False))
        print("\nSaved:", output)

    except Exception as error:
        print("CatWISE query failed:")
        print(error)


# ---------------------------------------------------------
# 2. QUERY GAIA DR3 FOR EPSILON INDI B AND RW AUR
# ---------------------------------------------------------

def query_gaia(target_name):

    print("\n" + "=" * 65)
    print("GAIA DR3:", target_name)
    print("=" * 65)

    target = TARGETS[target_name]

    query = f"""
    SELECT TOP 100
        source_id,
        ra,
        dec,
        ref_epoch,
        parallax,
        parallax_error,
        pmra,
        pmra_error,
        pmdec,
        pmdec_error,
        radial_velocity,
        ruwe,
        astrometric_params_solved,
        phot_g_mean_mag
    FROM gaiadr3.gaia_source
    WHERE CONTAINS(
        POINT('ICRS', ra, dec),
        CIRCLE(
            'ICRS',
            {target['ra']},
            {target['dec']},
            {target['radius_deg']}
        )
    ) = 1
    ORDER BY phot_g_mean_mag ASC
    """

    try:
        job = Gaia.launch_job_async(query)
        result = job.get_results()

        df = result.to_pandas()

        # Preserve Gaia's 64-bit identifiers exactly.
        df["source_id"] = df["source_id"].astype("string")

        filename = (
            target_name.lower()
            + "_gaia_candidates.csv"
        )

        output = METADATA_DIR / filename
        df.to_csv(output, index=False)

        print("Candidates found:", len(df))
        print(df.head(30).to_string(index=False))
        print("\nSaved:", output)

    except Exception as error:
        print("Gaia query failed:")
        print(error)


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

if __name__ == "__main__":

    query_catwise()

    query_gaia("Epsilon_Indi_B")

    query_gaia("RW_Aurigae")

    print("\n" + "=" * 65)
    print("CATALOGUE SEARCH COMPLETED")
    print("=" * 65)
