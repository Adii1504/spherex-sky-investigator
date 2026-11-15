
from pathlib import Path

import pandas as pd
from astroquery.gaia import Gaia


# Confirmed Gaia DR3 source identifiers
verified_targets = {
    "Barnard's Star": "4472832130942575872",
    "Epsilon Indi B": "6412596012146801152",
    "R Draconis": "1648328016354496384",
}

source_ids = ", ".join(verified_targets.values())

query = f"""
SELECT
    source_id,
    ra,
    dec,
    ref_epoch,
    pmra,
    pmdec,
    parallax,
    radial_velocity,
    phot_g_mean_mag,
    ruwe,
    ra_error,
    dec_error,
    pmra_error,
    pmdec_error,
    parallax_error
FROM gaiadr3.gaia_source
WHERE source_id IN ({source_ids})
"""

print("Retrieving verified Gaia DR3 records...")

job = Gaia.launch_job_async(query)
results = job.get_results()

df = results.to_pandas()

# Add target names
id_to_name = {
    int(source_id): name
    for name, source_id in verified_targets.items()
}

df["target_name"] = df["source_id"].map(id_to_name)

# Put target name first
columns = ["target_name"] + [
    col for col in df.columns if col != "target_name"
]
df = df[columns]

output_file = Path(
    "data/metadata/verified_gaia_sources.csv"
)
output_file.parent.mkdir(parents=True, exist_ok=True)

df.to_csv(output_file, index=False)

print("\nVerified Gaia records:")
print(df.to_string(index=False))

print("\nSaved to:")
print(output_file.resolve())
