
from pathlib import Path

import astropy.units as u
import pandas as pd
from astropy.coordinates import SkyCoord
from astropy.time import Time


INPUT_FILE = Path(
    "data/metadata/verified_gaia_sources.csv"
)

OUTPUT_FILE = Path(
    "data/metadata/propagated_target_coordinates.csv"
)

# Initial reference epoch of Gaia DR3 astrometry
REFERENCE_EPOCH = Time(2016.0, format="jyear")

# Generate an initial position table for these dates.
# We will later calculate exact positions using each
# observation's actual DATE-OBS value.
TARGET_EPOCHS = [
    "2025-01-01T00:00:00",
    "2025-06-01T00:00:00",
    "2025-12-31T00:00:00",
]

df = pd.read_csv(INPUT_FILE)

output_rows = []

for _, row in df.iterrows():

    target_name = row["target_name"]

    print("\n" + "=" * 60)
    print("Target:", target_name)

    # Gaia reference position
    ra = row["ra"]
    dec = row["dec"]

    # Proper motion
    pmra = row["pmra"]
    pmdec = row["pmdec"]

    # Parallax in milliarcseconds
    parallax = row["parallax"]

    if pd.isna(pmra) or pd.isna(pmdec):
        print("Missing proper motion. Skipping.")
        continue

    if pd.isna(parallax) or parallax <= 0:
        print("Invalid parallax. Skipping.")
        continue

    distance = (parallax * u.mas).to(
        u.pc,
        equivalencies=u.parallax()
    )

    # Radial velocity, when available
    radial_velocity = row["radial_velocity"]

    if pd.isna(radial_velocity):
        radial_velocity = 0.0
        rv_status = "ASSUMED_ZERO"
    else:
        rv_status = "MEASURED"

    coordinate = SkyCoord(
        ra=ra * u.deg,
        dec=dec * u.deg,
        distance=distance,
        pm_ra_cosdec=pmra * u.mas / u.yr,
        pm_dec=pmdec * u.mas / u.yr,
        radial_velocity=radial_velocity * u.km / u.s,
        obstime=REFERENCE_EPOCH,
        frame="icrs"
    )

    for epoch_string in TARGET_EPOCHS:

        observation_epoch = Time(epoch_string)

        propagated = coordinate.apply_space_motion(
            new_obstime=observation_epoch
        )

        result = {
            "target_name": target_name,
            "gaia_source_id": int(row["source_id"]),
            "reference_epoch": 2016.0,
            "target_epoch": epoch_string,
            "ra_deg": propagated.ra.deg,
            "dec_deg": propagated.dec.deg,
            "radial_velocity_status": rv_status,
            "ruwe": row["ruwe"],
        }

        output_rows.append(result)

        print(
            f"{epoch_string}: "
            f"RA={propagated.ra.deg:.8f}, "
            f"Dec={propagated.dec.deg:.8f}"
        )

result_df = pd.DataFrame(output_rows)

OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)

result_df.to_csv(OUTPUT_FILE, index=False)

print("\n" + "=" * 60)
print("COORDINATE PROPAGATION COMPLETED")
print("Saved:", OUTPUT_FILE.resolve())
