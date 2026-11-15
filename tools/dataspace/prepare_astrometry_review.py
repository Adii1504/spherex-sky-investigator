
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "data" / "metadata"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "target_astrometry_review.csv"

# Gaia DR3 and SIMBAD values collected during the earlier investigation.
# Epochs are populated only for the Gaia DR3 entries.
records = [
    {
        "target": "Barnard's Star",
        "ra_deg": 269.448503,
        "dec_deg": 4.739420,
        "coord_epoch_jyear": 2016.0,
        "pm_ra_cosdec_masyr": -801.550978,
        "pm_dec_masyr": 10362.394207,
        "parallax_mas": 546.975940,
        "radial_velocity_kms": -110.468224,
        "astrometry_source": "Gaia DR3",
        "source_id": "4472832130942575872",
        "ruwe": 1.084851,
        "status": "GOOD_GAIA_SOLUTION",
        "notes": "Gaia DR3 astrometry; measured radial velocity available."
    },
    {
        "target": "Epsilon Indi B",
        "ra_deg": 331.076453,
        "dec_deg": -56.793812,
        "coord_epoch_jyear": 2016.0,
        "pm_ra_cosdec_masyr": 3981.976663,
        "pm_dec_masyr": -2466.831815,
        "parallax_mas": 270.658032,
        "radial_velocity_kms": None,
        "astrometry_source": "Gaia DR3",
        "source_id": "6412596012146801152",
        "ruwe": 4.295541,
        "status": "PROVISIONAL_HIGH_RUWE",
        "notes": "High RUWE; verify whether this solution represents the intended combined Ba/Bb system. RV unavailable."
    },
    {
        "target": "R Draconis",
        "ra_deg": 248.167378,
        "dec_deg": 66.755007,
        "coord_epoch_jyear": 2016.0,
        "pm_ra_cosdec_masyr": -20.642812,
        "pm_dec_masyr": 6.148819,
        "parallax_mas": 1.250918,
        "radial_velocity_kms": None,
        "astrometry_source": "Gaia DR3",
        "source_id": "1648328016354496384",
        "ruwe": 1.297982,
        "status": "GAIA_RV_MISSING",
        "notes": "Gaia DR3 solution; RV unavailable. Initial propagation will omit perspective correction."
    },
    {
        "target": "WISE 0855",
        "ra_deg": 133.81890825,
        "dec_deg": -7.247048,
        "coord_epoch_jyear": None,
        "pm_ra_cosdec_masyr": -8123.7,
        "pm_dec_masyr": 673.2,
        "parallax_mas": None,
        "radial_velocity_kms": None,
        "astrometry_source": "SIMBAD / CatWISE reference",
        "source_id": "",
        "ruwe": None,
        "status": "EPOCH_UNVERIFIED",
        "notes": "Starting coordinates and proper motion need a verified catalogue reference epoch."
    },
    {
        "target": "RW Aurigae",
        "ra_deg": 76.95652603458333,
        "dec_deg": 30.401438173888888,
        "coord_epoch_jyear": None,
        "pm_ra_cosdec_masyr": 7.23,
        "pm_dec_masyr": -20.33,
        "parallax_mas": None,
        "radial_velocity_kms": None,
        "astrometry_source": "SIMBAD",
        "source_id": "",
        "ruwe": None,
        "status": "EPOCH_AND_MATCH_UNVERIFIED",
        "notes": "Gaia crossmatch was ambiguous. Verify component-specific astrometry and reference epoch."
    }
]

df = pd.DataFrame(records)

df.to_csv(OUTPUT_FILE, index=False)

print("=" * 65)
print("TARGET ASTROMETRY REVIEW FILE CREATED")
print("=" * 65)

print(df[[
    "target",
    "astrometry_source",
    "coord_epoch_jyear",
    "status"
]].to_string(index=False))

print("\nSaved to:")
print(OUTPUT_FILE)

print("\nIMPORTANT:")
print("1. Verify the Epsilon Indi B Gaia solution and its component association.")
print("2. Verify the WISE 0855 and RW Aur coordinate epochs.")
print("3. Do not fill an epoch based only on a bibliography year.")
print("4. Edit this CSV only after checking the original catalogue records.")
