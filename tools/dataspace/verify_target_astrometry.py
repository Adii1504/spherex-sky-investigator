"""
verify_target_astrometry.py

Audits the supplied CatWISE/Gaia candidate CSV files.
It does NOT automatically choose uncertain catalogue matches.

Run from the project root:
    python verify_target_astrometry.py

Expected input files:
    data/metadata/wise0855_catwise_candidates.csv
    data/metadata/epsilon_indi_b_gaia_candidates.csv
    data/metadata/rw_aurigae_gaia_candidates.csv

If your CSV files are currently in the project root, change INPUT_DIR below.
"""

from pathlib import Path
import math
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "data" / "metadata"
OUTPUT_DIR = BASE_DIR / "data" / "metadata"

WISE_FILE = INPUT_DIR / "wise0855_catwise_candidates.csv"
EPSILON_FILE = INPUT_DIR / "epsilon_indi_b_gaia_candidates.csv"
RW_AUR_FILE = INPUT_DIR / "rw_aurigae_gaia_candidates.csv"

# Published CatWISE2020 motion for WISE 0855.
# CatWISE pmra is mu_alpha*cos(dec); values below are arcsec/year.
WISE_EXPECTED_PMRA = -8.1189
WISE_EXPECTED_PMDEC = 0.6793

# Provisional position used by the earlier project search.
WISE_PROVISIONAL_RA = 133.81890825
WISE_PROVISIONAL_DEC = -7.24704800

# Gaia DR3 candidate previously identified for Epsilon Indi B.
EPSILON_PROVISIONAL_ID = "6412596012146801152"

# Two Gaia candidates previously considered for RW Aurigae.
RW_AUR_CANDIDATE_IDS = {
    "156430817820015232",
    "156430822114424576",
}


def angular_separation_arcsec(ra1, dec1, ra2, dec2):
    """Great-circle separation in arcseconds."""
    ra1, dec1, ra2, dec2 = map(
        math.radians, [float(ra1), float(dec1), float(ra2), float(dec2)]
    )
    cos_sep = (
        math.sin(dec1) * math.sin(dec2)
        + math.cos(dec1) * math.cos(dec2) * math.cos(ra1 - ra2)
    )
    cos_sep = max(-1.0, min(1.0, cos_sep))
    return math.degrees(math.acos(cos_sep)) * 3600.0


def require_file(path):
    if not path.exists():
        raise FileNotFoundError(
            f"Missing input file:\n{path}\n\n"
            "Copy the uploaded candidate CSV into data\\metadata, "
            "or edit INPUT_DIR at the top of this script."
        )


def as_text(value):
    if pd.isna(value):
        return ""
    # Avoid displaying Gaia IDs as floating-point values.
    return str(value).replace(".0", "") if str(value).endswith(".0") else str(value)


def audit_wise():
    require_file(WISE_FILE)
    df = pd.read_csv(WISE_FILE)

    required = {
        "source_name", "source_id", "ra", "dec", "pmra", "pmdec",
        "meanobsmjd"
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"WISE CSV is missing columns: {sorted(missing)}")

    rows = []
    for _, row in df.iterrows():
        try:
            sep = angular_separation_arcsec(
                WISE_PROVISIONAL_RA, WISE_PROVISIONAL_DEC,
                row["ra"], row["dec"]
            )
        except Exception:
            sep = float("nan")

        pmra = pd.to_numeric(row["pmra"], errors="coerce")
        pmdec = pd.to_numeric(row["pmdec"], errors="coerce")

        # CatWISE table values are in arcsec/year in this candidate export.
        # This comparison is a screening test, not a final identification.
        pm_difference = float("nan")
        if pd.notna(pmra) and pd.notna(pmdec):
            pm_difference = math.hypot(
                float(pmra) - WISE_EXPECTED_PMRA,
                float(pmdec) - WISE_EXPECTED_PMDEC
            )

        rows.append({
            "target": "WISE 0855",
            "catalogue": "CatWISE candidate CSV",
            "source_name": as_text(row["source_name"]),
            "source_id": as_text(row["source_id"]),
            "ra_deg": row["ra"],
            "dec_deg": row["dec"],
            "ra_pm_at_catwise_reference_epoch_deg": row.get("ra_pm"),
            "dec_pm_at_catwise_reference_epoch_deg": row.get("dec_pm"),
            "separation_from_old_search_center_arcsec": sep,
            "pmra_catalogue_arcsec_per_year": pmra,
            "pmdec_catalogue_arcsec_per_year": pmdec,
            "expected_pmra_arcsec_per_year": WISE_EXPECTED_PMRA,
            "expected_pmdec_arcsec_per_year": WISE_EXPECTED_PMDEC,
            "proper_motion_difference_arcsec_per_year": pm_difference,
            "mean_observation_mjd": row["meanobsmjd"],
            "decision": "UNVERIFIED - inspect position and motion together"
        })

    out = pd.DataFrame(rows).sort_values(
        ["proper_motion_difference_arcsec_per_year",
         "separation_from_old_search_center_arcsec"],
        na_position="last"
    )
    return out


def audit_epsilon():
    require_file(EPSILON_FILE)
    df = pd.read_csv(EPSILON_FILE)

    if "source_id" not in df.columns:
        raise ValueError("Epsilon CSV must contain source_id.")

    rows = []
    for _, row in df.iterrows():
        source_id = as_text(row["source_id"])
        selected = source_id == EPSILON_PROVISIONAL_ID
        ruwe = pd.to_numeric(row.get("ruwe"), errors="coerce")

        if selected:
            decision = (
                "PROVISIONAL TARGET MATCH - high RUWE; verify Ba/Bb "
                "component association before precision use"
            )
        else:
            decision = "ALTERNATIVE CANDIDATE - not selected"

        rows.append({
            "target": "Epsilon Indi B",
            "catalogue": "Gaia DR3",
            "source_id": source_id,
            "ra_deg": row.get("ra"),
            "dec_deg": row.get("dec"),
            "reference_epoch": row.get("ref_epoch"),
            "parallax_mas": row.get("parallax"),
            "pmra_mas_per_year": row.get("pmra"),
            "pmdec_mas_per_year": row.get("pmdec"),
            "radial_velocity_km_per_s": row.get("radial_velocity"),
            "ruwe": ruwe,
            "decision": decision
        })

    return pd.DataFrame(rows)


def audit_rw_aur():
    require_file(RW_AUR_FILE)
    df = pd.read_csv(RW_AUR_FILE)

    if "source_id" not in df.columns:
        raise ValueError("RW Aur CSV must contain source_id.")

    rows = []
    for _, row in df.iterrows():
        source_id = as_text(row["source_id"])
        ruwe = pd.to_numeric(row.get("ruwe"), errors="coerce")
        is_priority = source_id in RW_AUR_CANDIDATE_IDS

        if is_priority:
            decision = (
                "PRIORITY FOR COMPONENT CHECK - not confirmed; "
                "compare with resolved/component-aware astrometry"
            )
        else:
            decision = "OTHER NEARBY GAIA SOURCE - do not assume target"

        rows.append({
            "target": "RW Aurigae",
            "catalogue": "Gaia DR3",
            "source_id": source_id,
            "ra_deg": row.get("ra"),
            "dec_deg": row.get("dec"),
            "reference_epoch": row.get("ref_epoch"),
            "parallax_mas": row.get("parallax"),
            "pmra_mas_per_year": row.get("pmra"),
            "pmdec_mas_per_year": row.get("pmdec"),
            "radial_velocity_km_per_s": row.get("radial_velocity"),
            "ruwe": ruwe,
            "decision": decision
        })

    out = pd.DataFrame(rows)
    if "ruwe" in out.columns:
        out = out.sort_values("ruwe", na_position="last")
    return out


def main():
    wise = audit_wise()
    epsilon = audit_epsilon()
    rw_aur = audit_rw_aur()

    # Keep a common, readable audit table. Columns not applicable to a
    # particular catalogue are intentionally left blank.
    combined = pd.concat(
        [wise, epsilon, rw_aur],
        ignore_index=True,
        sort=False
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / "astrometry_candidate_audit.csv"
    combined.to_csv(output_file, index=False)

    print("=" * 72)
    print("ASTROMETRY CANDIDATE AUDIT COMPLETED")
    print("=" * 72)

    print("\nWISE 0855: five closest proper-motion candidates")
    print(
        wise[
            [
                "source_name", "source_id",
                "ra_pm_at_catwise_reference_epoch_deg",
                "dec_pm_at_catwise_reference_epoch_deg",
                "separation_from_old_search_center_arcsec",
                "pmra_catalogue_arcsec_per_year",
                "pmdec_catalogue_arcsec_per_year",
                "proper_motion_difference_arcsec_per_year"
            ]
        ].head(5).to_string(index=False)
    )

    print("\nEpsilon Indi B candidates")
    print(
        epsilon[
            ["source_id", "parallax_mas", "pmra_mas_per_year",
             "pmdec_mas_per_year", "ruwe", "decision"]
        ].to_string(index=False)
    )

    print("\nRW Aurigae priority candidates")
    print(
        rw_aur[
            ["source_id", "parallax_mas", "pmra_mas_per_year",
             "pmdec_mas_per_year", "ruwe", "decision"]
        ].head(12).to_string(index=False)
    )

    print("\nSaved audit:")
    print(output_file)

    print("\nIMPORTANT:")
    print("1. This script does not declare a final WISE 0855 match.")
    print("2. Gaia candidates for RW Aurigae remain unconfirmed.")
    print("3. Epsilon Indi B remains provisional because its selected")
    print("   Gaia source has high RUWE and the system is a close binary.")
    print("4. Do not run final coordinate validation using unverified matches.")


if __name__ == "__main__":
    main()
