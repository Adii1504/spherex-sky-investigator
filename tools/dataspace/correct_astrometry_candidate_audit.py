"""
correct_astrometry_candidate_audit.py

Re-audits the three candidate CSVs without converting catalogue IDs to floats.
All source IDs are loaded as strings to preserve their exact integer digits.

Expected inputs in data/metadata:
  wise0855_catwise_candidates.csv
  epsilon_indi_b_gaia_candidates.csv
  rw_aurigae_gaia_candidates.csv

Run from the project root in PyCharm.
"""

from pathlib import Path
import math
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "data" / "metadata"
OUTPUT_FILE = INPUT_DIR / "astrometry_candidate_audit_corrected.csv"

EPSILON_TARGET_ID = "6412596012146801152"
RW_AUR_PRIORITY_IDS = {
    "156430817820015232",
    "156430822114424576",
}

# Published approximate WISE 0855 proper motion, in arcsec/year.
# This is used only as a screening comparison; it does not identify a source.
WISE_EXPECTED_PMRA = -8.1189
WISE_EXPECTED_PMDEC = 0.6793

# Previously used provisional search centre.
WISE_OLD_RA = 133.81890825
WISE_OLD_DEC = -7.24704800

# Discovery designation position, used only as another positional reference.
WISE_DISCOVERY_RA = 133.795125
WISE_DISCOVERY_DEC = -7.245139


def read_csv_preserve_ids(filename):
    path = INPUT_DIR / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Cannot find {path}\n"
            "Place the original candidate CSV files in data/metadata."
        )
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def number(value):
    try:
        if value == "" or value is None:
            return float("nan")
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def angular_separation_arcsec(ra1, dec1, ra2, dec2):
    ra1, dec1, ra2, dec2 = map(
        math.radians, [ra1, dec1, ra2, dec2]
    )
    cosine = (
        math.sin(dec1) * math.sin(dec2)
        + math.cos(dec1) * math.cos(dec2) * math.cos(ra1 - ra2)
    )
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine)) * 3600.0


def audit_wise():
    df = read_csv_preserve_ids("wise0855_catwise_candidates.csv")

    required = {
        "source_name", "source_id", "ra_pm", "dec_pm",
        "pmra", "pmdec", "meanobsmjd"
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"WISE candidate CSV missing columns: {sorted(missing)}")

    rows = []
    for _, item in df.iterrows():
        ra = number(item["ra_pm"])
        dec = number(item["dec_pm"])
        pmra = number(item["pmra"])
        pmdec = number(item["pmdec"])

        old_sep = (
            angular_separation_arcsec(WISE_OLD_RA, WISE_OLD_DEC, ra, dec)
            if all(map(math.isfinite, [ra, dec])) else float("nan")
        )
        discovery_sep = (
            angular_separation_arcsec(
                WISE_DISCOVERY_RA, WISE_DISCOVERY_DEC, ra, dec
            )
            if all(map(math.isfinite, [ra, dec])) else float("nan")
        )
        pm_difference = (
            math.hypot(pmra - WISE_EXPECTED_PMRA,
                       pmdec - WISE_EXPECTED_PMDEC)
            if all(map(math.isfinite, [pmra, pmdec])) else float("nan")
        )

        rows.append({
            "target": "WISE 0855",
            "catalogue": "CatWISE candidate export",
            "source_id": item["source_id"],  # keep exact string
            "source_name": item["source_name"],
            "ra_pm_deg": item["ra_pm"],
            "dec_pm_deg": item["dec_pm"],
            "pmra_raw": item["pmra"],
            "pmdec_raw": item["pmdec"],
            "meanobsmjd": item["meanobsmjd"],
            "separation_from_old_search_center_arcsec": old_sep,
            "separation_from_discovery_designation_arcsec": discovery_sep,
            "pm_difference_vs_expected_arcsec_per_year": pm_difference,
            "decision": (
                "NO CONFIRMED MATCH - candidate motion does not resemble "
                "the expected high proper motion; verify catalogue units, "
                "epoch and search region"
            )
        })

    result = pd.DataFrame(rows)
    result = result.sort_values(
        "separation_from_discovery_designation_arcsec",
        na_position="last"
    )
    return result


def audit_epsilon():
    df = read_csv_preserve_ids("epsilon_indi_b_gaia_candidates.csv")
    if "source_id" not in df.columns:
        raise ValueError("Epsilon CSV has no source_id column.")

    rows = []
    for _, item in df.iterrows():
        source_id = item["source_id"].strip()
        is_target = source_id == EPSILON_TARGET_ID
        rows.append({
            "target": "Epsilon Indi B",
            "catalogue": "Gaia DR3",
            "source_id": source_id,
            "ra_deg": item.get("ra", ""),
            "dec_deg": item.get("dec", ""),
            "reference_epoch": item.get("ref_epoch", ""),
            "parallax_mas": item.get("parallax", ""),
            "pmra_mas_per_year": item.get("pmra", ""),
            "pmdec_mas_per_year": item.get("pmdec", ""),
            "radial_velocity_km_per_s": item.get("radial_velocity", ""),
            "ruwe": item.get("ruwe", ""),
            "decision": (
                "PROVISIONAL TARGET CANDIDATE - exact source ID match; "
                "RUWE is high and Ba/Bb component association still needs "
                "verification"
                if is_target else
                "ALTERNATIVE FIELD SOURCE - not selected"
            )
        })
    return pd.DataFrame(rows)


def audit_rw_aur():
    df = read_csv_preserve_ids("rw_aurigae_gaia_candidates.csv")
    if "source_id" not in df.columns:
        raise ValueError("RW Aurigae CSV has no source_id column.")

    rows = []
    for _, item in df.iterrows():
        source_id = item["source_id"].strip()
        is_priority = source_id in RW_AUR_PRIORITY_IDS
        rows.append({
            "target": "RW Aurigae",
            "catalogue": "Gaia DR3",
            "source_id": source_id,
            "ra_deg": item.get("ra", ""),
            "dec_deg": item.get("dec", ""),
            "reference_epoch": item.get("ref_epoch", ""),
            "parallax_mas": item.get("parallax", ""),
            "pmra_mas_per_year": item.get("pmra", ""),
            "pmdec_mas_per_year": item.get("pmdec", ""),
            "radial_velocity_km_per_s": item.get("radial_velocity", ""),
            "ruwe": item.get("ruwe", ""),
            "decision": (
                "PRIORITY COMPONENT CANDIDATE - exact source ID match; "
                "not yet confirmed as the intended RW Aur component"
                if is_priority else
                "OTHER CANDIDATE - component identity not established"
            )
        })
    return pd.DataFrame(rows)


def main():
    INPUT_DIR.mkdir(parents=True, exist_ok=True)

    wise = audit_wise()
    epsilon = audit_epsilon()
    rw = audit_rw_aur()

    # Preserve all IDs as strings in the combined output.
    combined = pd.concat(
        [wise, epsilon, rw], ignore_index=True, sort=False
    )
    combined.to_csv(OUTPUT_FILE, index=False)

    print("=" * 76)
    print("CORRECTED ASTROMETRY CANDIDATE AUDIT")
    print("=" * 76)

    print("\nWISE 0855 - closest 8 candidates to discovery-designation position")
    print(wise[[
        "source_name", "source_id",
        "separation_from_discovery_designation_arcsec",
        "pmra_raw", "pmdec_raw",
        "pm_difference_vs_expected_arcsec_per_year"
    ]].head(8).to_string(index=False))

    print("\nWISE proper-motion screening range in supplied candidate file")
    print("pmra min/max:", wise["pmra_raw"].map(number).min(),
          "/", wise["pmra_raw"].map(number).max())
    print("pmdec min/max:", wise["pmdec_raw"].map(number).min(),
          "/", wise["pmdec_raw"].map(number).max())

    print("\nEpsilon Indi B - exact source ID check")
    print(epsilon[[
        "source_id", "parallax_mas", "pmra_mas_per_year",
        "pmdec_mas_per_year", "ruwe", "decision"
    ]].to_string(index=False))

    print("\nRW Aurigae - exact priority source ID check")
    priority = rw[rw["source_id"].isin(RW_AUR_PRIORITY_IDS)]
    if priority.empty:
        print("WARNING: neither priority ID was found in this CSV.")
    else:
        print(priority[[
            "source_id", "ra_deg", "dec_deg", "parallax_mas",
            "pmra_mas_per_year", "pmdec_mas_per_year", "ruwe",
            "decision"
        ]].to_string(index=False))

    print("\nSaved:", OUTPUT_FILE)
    print("\nINTERPRETATION:")
    print("- Source IDs were read as strings; no scientific-notation conversion.")
    print("- Epsilon Indi B's exact Gaia candidate is identified provisionally.")
    print("- Both RW Aurigae priority candidates are now identified exactly.")
    print("- No WISE 0855 candidate is confirmed by this CSV.")
    print("- Do not run final coordinate validation until remaining matches")
    print("  and reference epochs have been verified.")


if __name__ == "__main__":
    main()
