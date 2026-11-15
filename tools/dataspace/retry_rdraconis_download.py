
from pathlib import Path
import time
import requests
from astropy.io import fits

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "data" / "observations"

FILENAME = (
    "R_Draconis_ad99d16f_level2_2026W24_2B_0242_4D3_"
    "spx_l2b-v27-2026-272.fits"
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = OUTPUT_DIR / FILENAME

print("=" * 65)
print("R DRACONIS FAILED DOWNLOAD RETRY")
print("=" * 65)

url = input("\nPaste the exact download URL from your previous script:\n").strip()

if not url.startswith(("https://", "http://")):
    raise ValueError("Please provide a valid HTTP or HTTPS URL.")

if OUTPUT_PATH.exists():
    try:
        with fits.open(OUTPUT_PATH, memmap=False) as hdul:
            hdul.verify("exception")
        print("\nA valid copy already exists. No download needed.")
        raise SystemExit(0)
    except Exception:
        print("\nExisting file is invalid. It will be downloaded again.")
        OUTPUT_PATH.unlink()

session = requests.Session()
session.headers.update({"User-Agent": "SPHEREx-data-research/1.0"})

max_attempts = 6
success = False

for attempt in range(1, max_attempts + 1):
    print(f"\nDownload attempt {attempt}/{max_attempts}")

    temporary_path = OUTPUT_PATH.with_suffix(".fits.part")

    try:
        with session.get(url, stream=True, timeout=(30, 180)) as response:
            print("HTTP status:", response.status_code)
            response.raise_for_status()

            with open(temporary_path, "wb") as file:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        file.write(chunk)

        # Verify that the downloaded file is a readable FITS file.
        with fits.open(temporary_path, memmap=False) as hdul:
            hdul.verify("exception")

            if len(hdul) < 2:
                raise ValueError("Unexpected FITS structure: fewer than 2 HDUs.")

            print("FITS HDUs:", len(hdul))
            print("DATE-OBS:", hdul["IMAGE"].header.get("DATE-OBS"))

        temporary_path.replace(OUTPUT_PATH)
        success = True
        print("\nDownload and FITS validation successful.")
        print("Saved:", OUTPUT_PATH)
        break

    except Exception as error:
        print("Attempt failed:", error)

        if temporary_path.exists():
            temporary_path.unlink()

        if attempt < max_attempts:
            wait = min(15 * (2 ** (attempt - 1)), 180)
            print(f"Retrying in {wait} seconds...")
            time.sleep(wait)

if not success:
    print("\nDownload was unsuccessful after all attempts.")
    print("Check the URL or retry later if the archive server is unavailable.")

session.close()
print("\n" + "=" * 65)
print("RETRY PROCESS FINISHED")
print("=" * 65)
