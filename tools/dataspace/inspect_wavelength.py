
from pathlib import Path
from astropy.io import fits

folder = Path("data/observations")

for file in folder.glob("*.fits"):

    print("\n" + "=" * 60)
    print("FILE:", file.name)

    with fits.open(file) as hdul:

        # Read IMAGE metadata
        image_header = hdul["IMAGE"].header

        print("\nOBSERVATION INFORMATION")
        print("Date:", image_header.get("DATE-OBS"))
        print("Detector:", image_header.get("DETECTOR"))
        print("RA reference:", image_header.get("CRVAL1"))
        print("Dec reference:", image_header.get("CRVAL2"))

        # Inspect wavelength extension
        wave_hdu = hdul["WCS-WAVE"]

        print("\nWAVELENGTH EXTENSION")
        print("Columns:")

        if wave_hdu.data is not None:

            print(wave_hdu.columns.names)

            print("\nFirst 5 rows:")

            for row in wave_hdu.data[:5]:
                print(row)

            print("\nNumber of wavelength records:")
            print(len(wave_hdu.data))

        else:
            print("No wavelength table data found.")
