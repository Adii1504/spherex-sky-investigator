
from pathlib import Path
from astropy.io import fits
import numpy as np
import pandas as pd
import re

folder = Path("data/observations")
records = []

# Avoid counting duplicate copies of the same product
processed = set()

for file in folder.glob("*.fits"):

    try:
        with fits.open(file) as hdul:

            header = hdul["IMAGE"].header
            primary = hdul[0].header



            product_id = re.sub(
                r"^ra[-\d.]+_dec[+-][\d.]+_",
                "",
                file.name
            )

            product_id = product_id.replace(".fits", "")

            if product_id in processed:
                continue

            processed.add(product_id)

            wave_data = hdul["WCS-WAVE"].data
            values = np.asarray(wave_data["VALUES"][0])

            wavelengths = values[..., 0]

            records.append({
                "filename": file.name,
                "product_id": product_id,
                "observation_date": header.get("DATE-OBS"),
                "mjd_obs": header.get("MJD-OBS"),
                "detector": header.get("DETECTOR"),
                "ra_reference": header.get("CRVAL1"),
                "dec_reference": header.get("CRVAL2"),
                "image_width": hdul["IMAGE"].data.shape[1],
                "image_height": hdul["IMAGE"].data.shape[0],
                "image_unit": header.get("BUNIT"),
                "processing_version": primary.get("VERSION"),
                "wavelength_grid_shape": str(wavelengths.shape),
                "wavelength_min": float(np.nanmin(wavelengths)),
                "wavelength_max": float(np.nanmax(wavelengths))
            })

    except Exception as e:
        print("Error processing:", file.name, e)

output = Path("data/metadata")
output.mkdir(parents=True, exist_ok=True)

df = pd.DataFrame(records)

df.to_csv(output / "fits_metadata.csv", index=False)

print("\nMetadata extraction completed.")
print("Unique products:", len(df))
print(df.to_string(index=False))
