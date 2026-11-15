"""
WISE 0855 CatWISE2020 re-query
--------------------------------
Run from the Eco/SPHEREx project root (the folder containing data/metadata).

Queries the official IRSA CatWISE2020 table around the published designation
CWISE J085508.34-071439.2, using a 180-arcsec cone. It saves the raw query
result and a ranked candidate table. No candidate is automatically declared
to be WISE 0855: the output is an audit for manual verification.

Requirements:
    pip install requests pandas astropy

The script uses the IRSA TAP synchronous API and the documented CatWISE2020
column units. PMRA and PMDec are in arcsec/year; RA/Dec are degrees.
"""

from pathlib import Path
import sys
import requests
import pandas as pd
from astropy.coordinates import SkyCoord
import astropy.units as u

# Published CatWISE designation: CWISE J085508.34-071439.2
TARGET_NAME = "CWISE J085508.34-071439.2"
CENTER_RA_DEG = 133.784750
CENTER_DEC_DEG = -7.244222
SEARCH_RADIUS_DEG = 0.05  # 180 arcsec; deliberately broad for high-PM source
EXPECTED_PMRA_ARCSEC_YR = -8.119
EXPECTED_PMDEC_ARCSEC_YR = 0.679

TAP_URL = "https://irsa.ipac.caltech.edu/TAP/sync"

PROJECT_ROOT = Path(__file__).resolve().parent
METADATA_DIR = PROJECT_ROOT / "data" / "metadata"
RAW_FILE = METADATA_DIR / "wise0855_catwise2020_raw.csv"
AUDIT_FILE = METADATA_DIR / "wise0855_catwise2020_requery_audit.csv"

# Keep this list conservative and aligned with the CatWISE2020 column
# dictionary. If IRSA reports a missing optional column, the script retries
# with the essential astrometry columns only.
FULL_COLUMNS = [
    "source_name", "source_id", "ra", "dec", "ra_pm", "dec_pm",
    "sigra", "sigdec", "sigra_pm", "sigdec_pm",
    "pmra", "pmdec", "sigpmra", "sigpmdec",
    "w1mpro_pm", "w2mpro_pm", "w1snr_pm", "w2snr_pm"
]
ESSENTIAL_COLUMNS = [
    "source_name", "source_id", "ra", "dec", "ra_pm", "dec_pm",
    "pmra", "pmdec", "sigpmra", "sigpmdec"
]


def query_irsa(columns):
    column_sql = ", ".join(columns)
    adql = (
        f"SELECT TOP 1000 {column_sql} "
        "FROM catwise_2020 "
        "WHERE CONTAINS("
        "POINT('ICRS', ra, dec), "
        f"CIRCLE('ICRS', {CENTER_RA_DEG}, {CENTER_DEC_DEG}, "
        f"{SEARCH_RADIUS_DEG})"
        ") = 1"
    )
    response = requests.post(
        TAP_URL,
        data={
            "REQUEST": "doQuery",
            "LANG": "ADQL",
            "FORMAT": "csv",
            "QUERY": adql,
        },
        timeout=180,
    )
    response.raise_for_status()
    content = response.text
    if not content.strip() or content.lstrip().startswith("<"):
        raise RuntimeError(
            "IRSA returned a non-CSV response. First 1500 characters:\n"
            + content[:1500]
        )
    from io import StringIO
    return pd.read_csv(StringIO(content), dtype={"source_id": "string"})


def main():
    METADATA_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 76)
    print("WISE 0855 - CATWISE2020 RE-QUERY")
    print("=" * 76)
    print(f"Target designation : {TARGET_NAME}")
    print(f"Search centre      : {CENTER_RA_DEG:.6f}, {CENTER_DEC_DEG:.6f}")
    print(f"Search radius      : {SEARCH_RADIUS_DEG * 3600:.1f} arcsec")
    print("Proper-motion units: arcsec/year (CatWISE2020 documentation)")
    print()

    try:
        df = query_irsa(FULL_COLUMNS)
    except Exception as first_error:
        print("Full-column query failed; retrying with essential astrometry columns.")
        print("Reason:", first_error)
        try:
            df = query_irsa(ESSENTIAL_COLUMNS)
        except Exception as second_error:
            print("\nIRSA query failed.")
            print(second_error)
            print("\nCheck internet access and the IRSA TAP service, then retry.")
            sys.exit(1)

    if df.empty:
        print("No CatWISE2020 rows returned in the search cone.")
        print("No output candidate file was created.")
        return

    # Preserve the unmodified catalogue result.
    df.to_csv(RAW_FILE, index=False)

    required = {"ra", "dec"}
    if not required.issubset(df.columns):
        raise RuntimeError(f"Query response is missing required columns: {required - set(df.columns)}")

    center = SkyCoord(CENTER_RA_DEG * u.deg, CENTER_DEC_DEG * u.deg)
    positions = SkyCoord(
        pd.to_numeric(df["ra"], errors="coerce").to_numpy() * u.deg,
        pd.to_numeric(df["dec"], errors="coerce").to_numpy() * u.deg,
    )
    df["separation_from_designation_arcsec"] = center.separation(positions).arcsec

    # CatWISE ra_pm/dec_pm are positions at the CatWISE2020 reference epoch
    # MJD 57170 (2015.405). Report their separation separately from ra/dec.
    if {"ra_pm", "dec_pm"}.issubset(df.columns):
        pm_positions = SkyCoord(
            pd.to_numeric(df["ra_pm"], errors="coerce").to_numpy() * u.deg,
            pd.to_numeric(df["dec_pm"], errors="coerce").to_numpy() * u.deg,
        )
        df["separation_using_pm_position_arcsec"] = center.separation(pm_positions).arcsec

    if {"pmra", "pmdec"}.issubset(df.columns):
        pmra = pd.to_numeric(df["pmra"], errors="coerce")
        pmdec = pd.to_numeric(df["pmdec"], errors="coerce")
        df["pm_difference_vs_expected_arcsec_per_year"] = (
            (pmra - EXPECTED_PMRA_ARCSEC_YR) ** 2
            + (pmdec - EXPECTED_PMDEC_ARCSEC_YR) ** 2
        ) ** 0.5
    else:
        df["pm_difference_vs_expected_arcsec_per_year"] = float("nan")

    sort_columns = ["separation_from_designation_arcsec"]
    if "pm_difference_vs_expected_arcsec_per_year" in df.columns:
        # Position is the primary sort; PM agreement is a secondary diagnostic.
        df = df.sort_values(
            ["separation_from_designation_arcsec",
             "pm_difference_vs_expected_arcsec_per_year"],
            ascending=[True, True],
            na_position="last",
        )

    df.to_csv(AUDIT_FILE, index=False)

    display_columns = [
        c for c in [
            "source_name", "source_id", "ra", "dec",
            "separation_from_designation_arcsec",
            "ra_pm", "dec_pm", "separation_using_pm_position_arcsec",
            "pmra", "pmdec", "sigpmra", "sigpmdec",
            "pm_difference_vs_expected_arcsec_per_year",
            "w1mpro_pm", "w2mpro_pm", "w1snr_pm", "w2snr_pm"
        ] if c in df.columns
    ]

    print(f"Rows returned: {len(df)}")
    print("\nClosest 20 candidates:")
    print(df[display_columns].head(20).to_string(index=False))
    print("\nSaved raw result :", RAW_FILE)
    print("Saved audit      :", AUDIT_FILE)
    print("\nIMPORTANT:")
    print("- This is a candidate search, not an automatic source identification.")
    print("- Compare both position and proper motion, plus uncertainties and photometry.")
    print("- CatWISE2020 PMRA/PMDec are arcsec/year; do not multiply by 1000.")
    print("- CatWISE2020 ra_pm/dec_pm refer to MJD 57170 (2015.405).")
    print("- Do not use this result for final SPHEREx cutout centering until verified.")


if __name__ == "__main__":
    main()
