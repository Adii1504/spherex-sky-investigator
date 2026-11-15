
from pathlib import Path
import csv
import warnings

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from astropy.coordinates import SkyCoord, Distance
from astropy.time import Time
import astropy.units as u


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

OBSERVATION_DIR = BASE_DIR / "data" / "observations"
METADATA_DIR = BASE_DIR / "data" / "metadata"

OUTPUT_FILE = METADATA_DIR / "target_coverage_report.csv"


# =========================================================
# TARGET ASTROMETRY
#
# Gaia DR3 positions are at reference epoch J2016.0.
# pm_ra_cosdec = Gaia pmra
# pm_dec       = Gaia pmdec
#
# Radial velocity is in km/s.
# Missing radial velocities are provisionally set to zero.
# =========================================================

TARGETS = {

    "Barnards_Star": {
        "method": "GAIA_DR3",
        "ra": 269.448503,
        "dec": 4.739420,
        "pm_ra_cosdec": -801.550978,
        "pm_dec": 10362.394207,
        "parallax": 546.975940,
        "radial_velocity": -110.468224,
        "ruwe": 1.084851,
        "status": "GAIA_ASTROMETRY"
    },

    "Epsilon_Indi_B": {
        "method": "GAIA_DR3",
        "ra": 331.076453,
        "dec": -56.793812,
        "pm_ra_cosdec": 3981.976663,
        "pm_dec": -2466.831815,
        "parallax": 270.658032,
        "radial_velocity": 0.0,
        "ruwe": 4.295541,
        "status": "PROVISIONAL_HIGH_RUWE_ZERO_RV"
    },

    "R_Draconis": {
        "method": "GAIA_DR3",
        "ra": 248.167378,
        "dec": 66.755007,
        "pm_ra_cosdec": -20.642812,
        "pm_dec": 6.148819,
        "parallax": 1.250918,
        "radial_velocity": 0.0,
        "ruwe": 1.297982,
        "status": "GAIA_ASTROMETRY_ZERO_RV"
    },

    "WISE_0855": {
        "method": "SIMBAD_STATIC",
        "ra": 133.81890825,
        "dec": -7.247048,
        "status": "PROVISIONAL_EPOCH_UNVERIFIED"
    },

    "RW_Aurigae": {
        "method": "SIMBAD_STATIC",
        "ra": 76.95652603458333,
        "dec": 30.401438173888888,
        "status": "PROVISIONAL_EPOCH_UNVERIFIED"
    }
}


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def identify_target(filename):

    for target_name in TARGETS:

        if filename.startswith(target_name + "_"):
            return target_name

    return None


def get_image_hdu(hdul):

    for hdu in hdul:

        if (
            hdu.name.upper() == "IMAGE"
            and hdu.data is not None
            and np.ndim(hdu.data) >= 2
        ):
            return hdu

    return None


def get_observation_time(hdul):

    for hdu in hdul:

        date_obs = hdu.header.get("DATE-OBS")

        if date_obs:
            return Time(date_obs, scale="utc")

        mjd_obs = hdu.header.get("MJD-OBS")

        if mjd_obs is not None:
            return Time(float(mjd_obs), format="mjd", scale="utc")

    raise ValueError("DATE-OBS and MJD-OBS not found")


# =========================================================
# CALCULATE TARGET POSITION AT OBSERVATION EPOCH
# =========================================================

def calculate_target_position(target_name, observation_time):

    target = TARGETS[target_name]

    # Gaia astrometry available.
    if target["method"] == "GAIA_DR3":

        distance = Distance(
            parallax=target["parallax"] * u.mas
        )

        reference_epoch = Time(2016.0, format="jyear")

        coordinate = SkyCoord(

            ra=target["ra"] * u.deg,
            dec=target["dec"] * u.deg,

            pm_ra_cosdec=(
                target["pm_ra_cosdec"] * u.mas / u.yr
            ),

            pm_dec=(
                target["pm_dec"] * u.mas / u.yr
            ),

            distance=distance,

            radial_velocity=(
                target["radial_velocity"] * u.km / u.s
            ),

            obstime=reference_epoch,
            frame="icrs"
        )

        propagated = coordinate.apply_space_motion(
            new_obstime=observation_time
        )

        return (
            propagated,
            "PROPAGATED_FROM_J2016.0"
        )

    # Provisional coordinates without verified epoch.
    coordinate = SkyCoord(
        ra=target["ra"] * u.deg,
        dec=target["dec"] * u.deg,
        frame="icrs"
    )

    return (
        coordinate,
        "STATIC_COORDINATES_EPOCH_UNVERIFIED"
    )


# =========================================================
# INSPECT ONE FITS FILE
# =========================================================

def validate_file(file_path):

    target_name = identify_target(file_path.name)

    if target_name is None:
        return None

    result = {

        "filename": file_path.name,
        "target": target_name,
        "astrometry_source": TARGETS[target_name]["method"],
        "astrometry_status": TARGETS[target_name]["status"],

        "observation_date": None,
        "observation_mjd": None,

        "target_ra_observation": None,
        "target_dec_observation": None,

        "pixel_x": None,
        "pixel_y": None,

        "image_width": None,
        "image_height": None,

        "center_offset_pixels": None,
        "target_position_status": None,

        "coordinate_method": None,
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

                hdul.verify("exception")

                # Find observation date.
                observation_time = get_observation_time(hdul)

                result["observation_date"] = observation_time.isot
                result["observation_mjd"] = float(
                    observation_time.mjd
                )

                # Find science image.
                image_hdu = get_image_hdu(hdul)

                if image_hdu is None:
                    raise ValueError("IMAGE extension not found")

                image_data = image_hdu.data

                height, width = image_data.shape[-2:]

                result["image_width"] = width
                result["image_height"] = height

                # Get target's position at observation epoch.
                sky_position, coordinate_method = (
                    calculate_target_position(
                        target_name,
                        observation_time
                    )
                )

                result["coordinate_method"] = coordinate_method

                result["target_ra_observation"] = float(
                    sky_position.ra.deg
                )

                result["target_dec_observation"] = float(
                    sky_position.dec.deg
                )

                # Convert sky coordinates to image pixels.
                image_wcs = WCS(
                    image_hdu.header,
                    fobj=hdul
                ).celestial

                if not image_wcs.has_celestial:
                    raise ValueError("Celestial WCS unavailable")

                x, y = image_wcs.world_to_pixel(sky_position)

                result["pixel_x"] = float(x)
                result["pixel_y"] = float(y)

                # Distance from geometric image center.
                center_x = (width - 1) / 2
                center_y = (height - 1) / 2

                offset = np.sqrt(
                    (x - center_x) ** 2
                    + (y - center_y) ** 2
                )

                result["center_offset_pixels"] = float(offset)

                # Pixel boundaries.
                inside = (
                    -0.5 <= x < width - 0.5
                    and -0.5 <= y < height - 0.5
                )

                result["target_position_status"] = (
                    "INSIDE_IMAGE" if inside else "OUTSIDE_IMAGE"
                )

    except Exception as error:

        result["target_position_status"] = "ERROR"
        result["error"] = str(error)

    return result


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 65)
    print("SPHEREx OBSERVATION-EPOCH TARGET VALIDATION")
    print("=" * 65)

    METADATA_DIR.mkdir(parents=True, exist_ok=True)

    fits_files = sorted(
        OBSERVATION_DIR.rglob("*.fits")
    )

    print("Total FITS files:", len(fits_files))

    reports = []

    for index, file_path in enumerate(fits_files, start=1):

        target_name = identify_target(file_path.name)

        if target_name is None:
            print("\nSkipping unrelated file:", file_path.name)
            continue

        print("\nInspecting {}/{}".format(index, len(fits_files)))
        print("Target:", target_name)
        print("File:", file_path.name)

        result = validate_file(file_path)

        if result is not None:

            reports.append(result)

            print("Observation date:", result["observation_date"])
            print("Coordinate method:", result["coordinate_method"])
            print("Pixel position:", result["pixel_x"], result["pixel_y"])
            print("Center offset:", result["center_offset_pixels"])
            print("Coverage:", result["target_position_status"])

            if result["error"]:
                print("Error:", result["error"])

    # Save detailed CSV report.
    if not reports:
        print("\nNo target FITS files found.")
        return

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

    # Summary by target.
    print("\n" + "=" * 65)
    print("TARGET COVERAGE SUMMARY")
    print("=" * 65)

    for target_name in TARGETS:

        target_rows = [
            row for row in reports
            if row["target"] == target_name
        ]

        inside = sum(
            row["target_position_status"] == "INSIDE_IMAGE"
            for row in target_rows
        )

        outside = sum(
            row["target_position_status"] == "OUTSIDE_IMAGE"
            for row in target_rows
        )

        errors = sum(
            row["target_position_status"] == "ERROR"
            for row in target_rows
        )

        print("\n{}".format(target_name))
        print("Files checked:", len(target_rows))
        print("Inside:", inside)
        print("Outside:", outside)
        print("Errors:", errors)

    propagated_count = sum(
        row["coordinate_method"] == "PROPAGATED_FROM_J2016.0"
        for row in reports
    )

    provisional_count = sum(
        row["coordinate_method"]
        == "STATIC_COORDINATES_EPOCH_UNVERIFIED"
        for row in reports
    )

    print("\n" + "=" * 65)
    print("TOTAL FILES CHECKED:", len(reports))
    print("Gaia-propagated positions:", propagated_count)
    print("Provisional static positions:", provisional_count)

    print("\nReport saved to:")
    print(OUTPUT_FILE)

    print("\nValidation completed.")


if __name__ == "__main__":
    main()
