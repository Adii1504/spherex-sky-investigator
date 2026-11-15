
from pathlib import Path
from astropy.io import fits
from astropy.wcs import WCS
import pandas as pd
import numpy as np

folder = Path("data/observations")
records = []

for file in folder.glob("*.fits"):

    try:
        with fits.open(file) as hdul:

            image = hdul["IMAGE"].data
            header = hdul["IMAGE"].header

            # Extract WCS information
            wcs = WCS(header)

            height, width = image.shape

            # Image corner pixel coordinates
            pixels = np.array([
                [0, 0],
                [width - 1, 0],
                [0, height - 1],
                [width - 1, height - 1],
                [(width - 1) / 2, (height - 1) / 2]
            ])

            # Convert pixels to sky coordinates
            sky = wcs.pixel_to_world(
                pixels[:, 0],
                pixels[:, 1]
            )

            ra_values = sky.ra.deg
            dec_values = sky.dec.deg

            records.append({
                "filename": file.name,
                "center_ra": ra_values[4],
                "center_dec": dec_values[4],
                "ra_min": np.min(ra_values[:4]),
                "ra_max": np.max(ra_values[:4]),
                "dec_min": np.min(dec_values[:4]),
                "dec_max": np.max(dec_values[:4]),
                "width_pixels": width,
                "height_pixels": height
            })

            print("\nFile:", file.name)
            print("Center RA:", ra_values[4])
            print("Center Dec:", dec_values[4])

    except Exception as e:
        print("Error:", file.name, e)

# Save results
output = Path("data/metadata")
output.mkdir(parents=True, exist_ok=True)

df = pd.DataFrame(records)
df.to_csv(output / "wcs_metadata.csv", index=False)

print("\nWCS extraction completed.")
print("Images processed:", len(df))
print(df.to_string(index=False))
