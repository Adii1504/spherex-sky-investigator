
from pathlib import Path
import csv
import warnings

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from astropy.coordinates import SkyCoord
from astropy.time import Time
import astropy.units as u


# ---------------------------------------------------------
# PROJECT PATHS
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
OBSERVATION_DIR = BASE_DIR / "data" / "observations"
METADATA_DIR = BASE_DIR / "data" / "metadata"

OUTPUT_FILE = METADATA_DIR / "fits_inspection_report.csv"


# ---------------------------------------------------------
# TARGET SEARCH COORDINATES
# These are the coordinates currently used by main.py.
# Provisional targets are marked as such in the report.
# ---------------------------------------------------------

TARGET_COORDINATES = {
    "Barnards_Star": {
        "ra": 269.44639795,
        "dec": 4.76653378,
        "status": "GAIA_MATCHED"
    },
    "Epsilon_Indi_B": {
        "ra": 331.09546968,
        "dec": -56.80026146,
        "status": "PROVISIONAL_HIGH_RUWE"
    },
    "WISE_0855": {
        "ra": 133.81890825,
        "dec": -7.247048,
        "status": "PROVISIONAL"
    },
    "RW_Aurigae": {
        "ra": 76.95652603,
        "dec": 30.40143817,
        "status": "PROVISIONAL"
    },
    "R_Draconis": {
        "ra": 248.16724159,
        "dec": 66.75502282,
        "status": "GAIA_MATCHED"
    }
}


# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------

def get_target_name(filename):
    """Identify the target from the downloaded filename."""

    for target_name in TARGET_COORDINATES:
        if filename.startswith(target_name + "_"):
            return target_name

    return "UNKNOWN"


def get_header_value(hdul, keyword):
    """Find a FITS header value across all HDUs."""

    for hdu in hdul:
        if keyword in hdu.header:
            return hdu.header[keyword]

    return None


def find_image_hdu(hdul):
    """Find the main two-dimensional image extension."""

    for hdu in hdul:
        if hdu.name.upper() == "IMAGE" and hdu.data is not None:
            if np.ndim(hdu.data) >= 2:
                return hdu

    for hdu in hdul:
        if hdu.data is not None and np.ndim(hdu.data) >= 2:
            return hdu

    return None


def inspect_wavelength(hdul):
    """Extract wavelength values from the WCS-WAVE table."""

    for hdu in hdul:
        if hdu.name.upper() == "WCS-WAVE" and hdu.data is not None:

            if hdu.data.dtype.names is None:
                return None, None, None

            for column_name in hdu.data.dtype.names:

                if column_name.upper() == "VALUES":

                    values = np.asarray(
                        hdu.data[column_name],
                        dtype=float
                    )

                    valid_values = values[np.isfinite(values)]

                    if len(valid_values) == 0:
                        return None, None, None

                    column_unit = (
                        hdu.columns[column_name].unit
                        if column_name in hdu.columns.names
                        else None
                    )

                    return (
                        float(np.min(valid_values)),
                        float(np.max(valid_values)),
                        column_unit
                    )

    return None, None, None


def inspect_target_position(image_hdu, target_name):
    """
    Convert target sky coordinates to image pixel coordinates.

    This checks whether the search coordinate falls inside
    the image. It does not prove that the target is detected.
    """

    target = TARGET_COORDINATES.get(target_name)

    if target is None:
        return None, None, "UNKNOWN_TARGET"

    try:
        image_wcs = WCS(image_hdu.header)

        if not image_wcs.has_celestial:
            return None, None, "NO_CELESTIAL_WCS"

        celestial_wcs = image_wcs.celestial

        sky_position = SkyCoord(
            ra=target["ra"] * u.deg,
            dec=target["dec"] * u.deg,
            frame="icrs"
        )

        x_pixel, y_pixel = celestial_wcs.world_to_pixel(sky_position)

        height, width = image_hdu.data.shape[-2:]

        inside = (
            -0.5 <= x_pixel < width - 0.5
            and -0.5 <= y_pixel < height - 0.5
        )

        status = "INSIDE_IMAGE" if inside else "OUTSIDE_IMAGE"

        return (
            round(float(x_pixel), 3),
            round(float(y_pixel), 3),
            status
        )

    except Exception as error:
        return None, None, "WCS_ERROR: " + str(error)


# ---------------------------------------------------------
# INSPECT ONE FITS FILE
# ---------------------------------------------------------

def inspect_fits_file(file_path):

    target_name = get_target_name(file_path.name)

    report = {
        "filename": file_path.name,
        "target": target_name,
        "astrometry_status": (
            TARGET_COORDINATES.get(target_name, {}).get("status", "UNKNOWN")
        ),
        "validation": "FAILED",
        "observation_date": None,
        "mjd_obs": None,
        "detector": None,
        "bandpass": None,
        "image_width": None,
        "image_height": None,
        "image_unit": None,
        "finite_pixels": None,
        "total_pixels": None,
        "pixel_min": None,
        "pixel_max": None,
        "pixel_median": None,
        "wavelength_min": None,
        "wavelength_max": None,
        "wavelength_unit": None,
        "target_x_pixel": None,
        "target_y_pixel": None,
        "target_position_status": None,
        "error": None
    }

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            with fits.open(
                file_path,
                mode="readonly",
                memmap=False
            ) as hdul:

                # Validate FITS structure.
                hdul.verify("exception")

                report["validation"] = "VALID"

                # Observation information.
                report["observation_date"] = get_header_value(
                    hdul, "DATE-OBS"
                )

                mjd_value = get_header_value(hdul, "MJD-OBS")

                if mjd_value is not None:
                    report["mjd_obs"] = float(mjd_value)

                    if not report["observation_date"]:
                        report["observation_date"] = (
                            Time(
                                float(mjd_value),
                                format="mjd",
                                scale="utc"
                            ).isot
                        )

                # Detector and band information.
                report["detector"] = get_header_value(
                    hdul, "DETECTOR"
                )

                report["bandpass"] = get_header_value(
                    hdul, "BANDPASS"
                )

                # Main image.
                image_hdu = find_image_hdu(hdul)

                if image_hdu is not None:

                    image_data = np.asarray(
                        image_hdu.data,
                        dtype=float
                    )

                    report["image_unit"] = (
                        image_hdu.header.get("BUNIT")
                    )

                    report["image_height"] = image_data.shape[-2]
                    report["image_width"] = image_data.shape[-1]

                    finite_pixels = image_data[
                        np.isfinite(image_data)
                    ]

                    report["finite_pixels"] = len(finite_pixels)
                    report["total_pixels"] = image_data.size

                    if len(finite_pixels) > 0:
                        report["pixel_min"] = float(
                            np.min(finite_pixels)
                        )

                        report["pixel_max"] = float(
                            np.max(finite_pixels)
                        )

                        report["pixel_median"] = float(
                            np.median(finite_pixels)
                        )

                    # Target position in image.
                    x, y, position_status = inspect_target_position(
                        image_hdu,
                        target_name
                    )

                    report["target_x_pixel"] = x
                    report["target_y_pixel"] = y
                    report["target_position_status"] = position_status

                else:
                    report["validation"] = "VALID_NO_IMAGE"

                # Wavelength information.
                wave_min, wave_max, wave_unit = inspect_wavelength(hdul)

                report["wavelength_min"] = wave_min
                report["wavelength_max"] = wave_max
                report["wavelength_unit"] = wave_unit

    except Exception as error:
        report["validation"] = "FAILED"
        report["error"] = str(error)

    return report


# ---------------------------------------------------------
# MAIN PROGRAM
# ---------------------------------------------------------

def main():

    print("=" * 65)
    print("SPHEREx DOWNLOADED FITS INSPECTION")
    print("=" * 65)

    if not OBSERVATION_DIR.exists():
        print("Observation directory does not exist:")
        print(OBSERVATION_DIR)
        return

    METADATA_DIR.mkdir(parents=True, exist_ok=True)

    fits_files = sorted(
        OBSERVATION_DIR.rglob("*.fits")
    )

    print("FITS files found:", len(fits_files))

    if not fits_files:
        print("No FITS files found.")
        return

    reports = []

    for index, file_path in enumerate(fits_files, start=1):

        print("\nInspecting {}/{}".format(index, len(fits_files)))
        print(file_path.name)

        report = inspect_fits_file(file_path)
        reports.append(report)

        print("Validation:", report["validation"])
        print("Observation date:", report["observation_date"])
        print("Image size:", report["image_width"], "x",
              report["image_height"])
        print("Target position:", report["target_position_status"])

        if report["error"]:
            print("Error:", report["error"])

    # Write CSV report.
    fieldnames = list(reports[0].keys())

    with open(
        OUTPUT_FILE,
        "w",
        newline="",
        encoding="utf-8"
    ) as csv_file:

        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerows(reports)

    # Summary.
    valid_count = sum(
        row["validation"] == "VALID"
        for row in reports
    )

    failed_count = sum(
        row["validation"] == "FAILED"
        for row in reports
    )

    inside_count = sum(
        row["target_position_status"] == "INSIDE_IMAGE"
        for row in reports
    )

    outside_count = sum(
        row["target_position_status"] == "OUTSIDE_IMAGE"
        for row in reports
    )

    print("\n" + "=" * 65)
    print("INSPECTION SUMMARY")
    print("=" * 65)

    print("Total files:", len(reports))
    print("Valid FITS files:", valid_count)
    print("Failed FITS files:", failed_count)
    print("Target coordinates inside image:", inside_count)
    print("Target coordinates outside image:", outside_count)

    print("\nReport saved to:")
    print(OUTPUT_FILE)

    print("\nInspection completed.")


if __name__ == "__main__":
    main()
