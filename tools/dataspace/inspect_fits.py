
from pathlib import Path
from astropy.io import fits

folder = Path("data/observations")

files = list(folder.glob("*.fits"))

if not files:
    print("No FITS files found.")
else:
    for file in files:

        print("\n" + "=" * 50)
        print("FILE:", file.name)

        with fits.open(file) as hdul:

            print("Number of HDUs:", len(hdul))

            print("\nPrimary header information:")

            for key in ["DATE-OBS", "VERSION", "TELESCOP", "INSTRUME"]:
                print(key, ":", hdul[0].header.get(key, "Not available"))

            print("\nFITS extensions:")

            for hdu in hdul:
                print(
                    hdu.name,
                    "Shape:",
                    getattr(hdu.data, "shape", None)
                )
