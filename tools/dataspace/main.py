import csv
import hashlib
import re
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urljoin, urlparse

import astropy.units as u
import requests
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.utils.data import conf
from astroquery.ipac.irsa import Irsa
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ============================================================
# CONFIGURATION
# ============================================================

conf.remote_timeout = 180
Irsa.TIMEOUT = 180  # applies to astroquery's own requests

BASE_DIR = Path(__file__).parent

OBSERVATION_DIR = BASE_DIR / "data" / "observations"
METADATA_DIR = BASE_DIR / "data" / "metadata"

OBSERVATION_DIR.mkdir(parents=True, exist_ok=True)
METADATA_DIR.mkdir(parents=True, exist_ok=True)

CUTOUT_SIZE = 0.1  # degrees
MAX_DOWNLOADS_PER_TARGET = 3

IRSA_BASE_URL = "https://irsa.ipac.caltech.edu/"

# VERIFY these against one real, working cutout URL from IRSA.
# They are kept explicit so the URL format is easy to change in one place.
CENTER_UNIT_SUFFIX = "d"      # e.g. center=269.4,4.7d
SIZE_UNIT_SUFFIX = ""         # "" = default (degrees); try "deg" if needed

MASTER_METADATA_FILE = METADATA_DIR / "all_observations.csv"

FIELDS = [
    "target_name",
    "target_ra",
    "target_dec",
    "coordinate_source",
    "coordinate_epoch",
    "astrometry_status",
    "cutout_size_deg",
    "plane_id",
    "observation_date",
    "bandpass",
    "source_uri",
    "cutout_center_ra",
    "cutout_center_dec",
    "cutout_url",
    "filename",
    "processing_version",
    "status",
    "error",
]


# ============================================================
# TARGET CONFIGURATION
# ============================================================

# Coordinates for the Gaia-confirmed targets are propagated
# to 2025-06-01 using the previous script.
#
# WISE 0855 and RW Aurigae still use provisional SIMBAD
# coordinates. Their astrometry must be verified separately.
#
# Optional: fill pmra_mas_yr / pmdec_mas_yr (pmra INCLUDES cos(dec),
# as in Gaia) to re-center each cutout at the observation epoch.
# Leave as None to use the fixed coordinates.

TARGETS = [
    {
        "name": "Barnards_Star",
        "ra": 269.44639795,
        "dec": 4.76653378,
        "coordinate_source": "Gaia DR3 propagated",
        "coordinate_epoch": "2025-06-01",
        "astrometry_status": "GAIA_MATCHED",
        "pmra_mas_yr": None,
        "pmdec_mas_yr": None,
    },
    {
        "name": "Epsilon_Indi_B",
        "ra": 331.09546968,
        "dec": -56.80026146,
        "coordinate_source": "Gaia DR3 propagated",
        "coordinate_epoch": "2025-06-01",
        "astrometry_status": "PROVISIONAL_HIGH_RUWE",
        "pmra_mas_yr": None,
        "pmdec_mas_yr": None,
    },
    {
        "name": "WISE_0855",
        "ra": 133.81890825,
        "dec": -7.24704800,
        "coordinate_source": "SIMBAD",
        "coordinate_epoch": "UNVERIFIED",
        "astrometry_status": "PROVISIONAL",
        "pmra_mas_yr": None,
        "pmdec_mas_yr": None,
    },
    {
        "name": "RW_Aurigae",
        "ra": 76.95652603,
        "dec": 30.40143817,
        "coordinate_source": "SIMBAD",
        "coordinate_epoch": "UNVERIFIED",
        "astrometry_status": "PROVISIONAL",
        "pmra_mas_yr": None,
        "pmdec_mas_yr": None,
    },
    {
        "name": "R_Draconis",
        "ra": 248.16724159,
        "dec": 66.75502282,
        "coordinate_source": "Gaia DR3 propagated",
        "coordinate_epoch": "2025-06-01",
        "astrometry_status": "GAIA_MATCHED",
        "pmra_mas_yr": None,
        "pmdec_mas_yr": None,
    },
]


# ============================================================
# HELPERS
# ============================================================

def validate_coordinates(ra, dec):

    if not 0 <= ra < 360:
        raise ValueError("RA must be between 0 and 360 degrees.")

    if not -90 <= dec <= 90:
        raise ValueError("Dec must be between -90 and 90 degrees.")

    return SkyCoord(
        ra=ra * u.degree,
        dec=dec * u.degree,
        frame="icrs"
    )


def make_session():
    """HTTP session with retries for flaky IRSA responses."""

    retry = Retry(
        total=4,
        backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )

    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def validate_fits(path):
    """Single validation routine for both cached and fresh files.

    Returns the processing version string. Raises on any problem.
    """

    with fits.open(path) as hdul:

        hdul.verify("exception")

        if len(hdul) < 2:
            raise ValueError("Invalid FITS structure.")

        if hdul[1].data is None:
            raise ValueError("FITS IMAGE extension has no image data.")

        return str(hdul[0].header.get("VERSION", "Unknown"))


def build_cutout_url(source_uri, ra, dec, size):
    """Build the cutout URL in Python (no fragile string concatenation in SQL)."""

    if source_uri.startswith("http"):
        base = source_uri
    else:
        base = urljoin(IRSA_BASE_URL, source_uri.lstrip("/"))

    return (
        f"{base}?center={ra:.8f},{dec:.8f}{CENTER_UNIT_SUFFIX}"
        f"&size={size}{SIZE_UNIT_SUFFIX}"
    )


def center_at_observation(target, observation_date):
    """Return (ra, dec) to center the cutout on.

    If proper motion is supplied and the observation date (MJD) is valid,
    propagate from the coordinate epoch to the observation epoch.
    Otherwise return the fixed catalogue coordinates.
    """

    ra, dec = target["ra"], target["dec"]

    pmra = target.get("pmra_mas_yr")
    pmdec = target.get("pmdec_mas_yr")

    if pmra is None or pmdec is None:
        return ra, dec

    try:
        epoch = Time(target["coordinate_epoch"])
        obs_time = Time(float(observation_date), format="mjd")
    except (ValueError, TypeError):
        # UNVERIFIED epoch or non-numeric date: fall back to fixed coords
        return ra, dec

    coord = SkyCoord(
        ra=ra * u.deg,
        dec=dec * u.deg,
        pm_ra_cosdec=pmra * u.mas / u.yr,
        pm_dec=pmdec * u.mas / u.yr,
        frame="icrs",
        obstime=epoch,
    )

    moved = coord.apply_space_motion(new_obstime=obs_time)
    return float(moved.ra.deg), float(moved.dec.deg)


def safe_filename(target_name, source_uri, plane_id):
    """Stable filename: independent of coordinates, unique per source URI."""

    original = Path(urlparse(source_uri).path).name
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]", "_", original)

    if not cleaned:
        cleaned = f"observation_{plane_id}.fits"

    digest = hashlib.sha1(source_uri.encode("utf-8")).hexdigest()[:8]

    return f"{target_name}_{digest}_{cleaned}"


# ============================================================
# STEP 1: SEARCH SPHEREX ARCHIVE
# ============================================================

def query_tap_with_retry(query, attempts=3):
    """Irsa.query_tap does not use the requests Session retries."""

    for attempt in range(1, attempts + 1):

        try:
            print(f"Archive query attempt {attempt}/{attempts}")
            return Irsa.query_tap(query)

        except Exception as error:

            print("Archive query failed:", error)

            if attempt == attempts:
                raise

            wait_time = attempt * 5
            print(f"Retrying in {wait_time} seconds...")
            time.sleep(wait_time)


def search_spherex(ra, dec):

    coord = validate_coordinates(ra, dec)

    print("\nSearching SPHEREx archive...")
    print(f"RA: {coord.ra.deg}")
    print(f"Dec: {coord.dec.deg}")

    query = f"""
    SELECT
        a.uri AS source_uri,
        p.planeid AS plane_id,
        p.time_bounds_lower AS observation_date,
        p.energy_bandpassname AS bandpass

    FROM spherex.artifact a

    JOIN spherex.plane p
    ON a.planeid = p.planeid

    WHERE 1 = CONTAINS(
        POINT('ICRS', {coord.ra.deg}, {coord.dec.deg}),
        p.poly
    )

    ORDER BY p.time_bounds_lower
    """

    tap_results = query_tap_with_retry(query)

    # TAP results expose fieldnames, not colnames; to_table() gives a
    # normal astropy Table so colnames/indexing behave as expected.
    results = tap_results.to_table()

    if len(results) > 0:
        first_value = results[0]["observation_date"]
        print("\nObservation date diagnostic:")
        print("Value:", repr(first_value))
        print("Python type:", type(first_value))

    # Convert to plain dicts and drop duplicate artifacts
    rows = []
    seen = set()

    for row in results:
        record = {name: row[name] for name in results.colnames}
        key = str(record["source_uri"])

        if key in seen:
            continue

        seen.add(key)
        rows.append(record)

    print("\nSearch completed!")
    print("Observations found:", len(results))
    print("Unique artifacts:", len(rows))

    return rows


# ============================================================
# STEP 2: SELECT A USEFUL SPREAD OF OBSERVATIONS
# ============================================================

def select_observations(rows, max_downloads):
    """Round-robin across bandpasses, newest observation first in each.

    Gives a spread of wavelength channels instead of the N earliest
    (probably near-identical) exposures.
    """

    def sort_key(row):
        try:
            return float(row["observation_date"])
        except (TypeError, ValueError):
            return float("-inf")

    groups = defaultdict(list)

    for row in rows:
        groups[str(row["bandpass"])].append(row)

    for group in groups.values():
        group.sort(key=sort_key, reverse=True)

    keys = sorted(groups)
    selected = []

    while len(selected) < max_downloads and any(groups[k] for k in keys):

        for key in keys:

            if groups[key] and len(selected) < max_downloads:
                selected.append(groups[key].pop(0))

    return selected


# ============================================================
# STEP 3: METADATA (MERGE, NEVER DUPLICATE)
# ============================================================

def write_csv_atomic(path, records):

    temp = path.with_name(path.name + ".tmp")

    with open(temp, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=FIELDS,
            restval="",
            extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(records)

    temp.replace(path)


def load_csv(path):

    if not path.exists():
        return []

    with open(path, newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def record_key(record):
    return (str(record["plane_id"]), str(record["source_uri"]))


def update_target_metadata(target_name, new_records):
    """Merge new records into the target file; rerun-safe."""

    metadata_file = METADATA_DIR / f"{target_name}_observations.csv"

    merged = {record_key(r): r for r in load_csv(metadata_file)}

    for record in new_records:
        merged[record_key(record)] = record

    write_csv_atomic(metadata_file, list(merged.values()))

    return metadata_file


def rebuild_master_metadata():
    """Rebuild the master file from the per-target files (single source of truth)."""

    all_records = {}

    for path in sorted(METADATA_DIR.glob("*_observations.csv")):

        if path.resolve() == MASTER_METADATA_FILE.resolve():
            continue

        for record in load_csv(path):
            key = (record["target_name"],) + record_key(record)
            all_records[key] = record

    write_csv_atomic(MASTER_METADATA_FILE, list(all_records.values()))


# ============================================================
# STEP 4: DOWNLOAD AND VALIDATE OBSERVATIONS
# ============================================================

def download_observations(
    rows,
    target,
    session,
    max_downloads=MAX_DOWNLOADS_PER_TARGET
):

    target_name = target["name"]

    selected_rows = select_observations(rows, max_downloads)

    records = []

    print("\nSelected observations:", len(selected_rows))

    for index, row in enumerate(selected_rows):

        plane_id = str(row["plane_id"])
        source_uri = str(row["source_uri"])
        observation_date = str(row["observation_date"])
        bandpass = str(row["bandpass"])

        center_ra, center_dec = center_at_observation(
            target, observation_date
        )

        cutout_url = build_cutout_url(
            source_uri, center_ra, center_dec, CUTOUT_SIZE
        )

        safe_name = safe_filename(target_name, source_uri, plane_id)

        output_path = OBSERVATION_DIR / safe_name
        temporary_path = output_path.with_name(output_path.name + ".part")

        record = {
            "target_name": target_name,
            "target_ra": target["ra"],
            "target_dec": target["dec"],
            "coordinate_source": target["coordinate_source"],
            "coordinate_epoch": target["coordinate_epoch"],
            "astrometry_status": target["astrometry_status"],
            "cutout_size_deg": CUTOUT_SIZE,
            "plane_id": plane_id,
            "observation_date": observation_date,
            "bandpass": bandpass,
            "source_uri": source_uri,
            "cutout_center_ra": f"{center_ra:.8f}",
            "cutout_center_dec": f"{center_dec:.8f}",
            "cutout_url": cutout_url,
            "filename": safe_name,
            "processing_version": "",
            "status": "FAILED",
            "error": "",
        }

        try:

            if output_path.exists():

                print(f"\nAlready downloaded: {safe_name}")

                record["processing_version"] = validate_fits(output_path)
                record["status"] = "CACHED"

            else:

                print(f"\nDownloading {index + 1}/{len(selected_rows)}")
                print(safe_name)

                with session.get(
                    cutout_url,
                    stream=True,
                    timeout=(30, 180)
                ) as response:

                    response.raise_for_status()

                    content_type = response.headers.get(
                        "Content-Type", ""
                    ).lower()

                    # IRSA can return an HTML/XML error page with HTTP 200
                    if "html" in content_type or "xml" in content_type:
                        raise ValueError(
                            f"Server returned non-FITS content: {content_type}"
                        )

                    with open(temporary_path, "wb") as download_file:

                        for chunk in response.iter_content(
                            chunk_size=1024 * 1024
                        ):

                            if chunk:
                                download_file.write(chunk)

                record["processing_version"] = validate_fits(temporary_path)

                # Move only validated files
                temporary_path.replace(output_path)

                record["status"] = "DOWNLOADED"

                print("Download successful!")

        except Exception as error:

            print("Download failed:", error)
            record["error"] = str(error)[:500]

            if temporary_path.exists():
                temporary_path.unlink()

            # A cached file that failed validation should not stay "valid"
            record["status"] = "FAILED"

        records.append(record)

    metadata_file = update_target_metadata(target_name, records)

    downloaded = sum(r["status"] == "DOWNLOADED" for r in records)
    cached = sum(r["status"] == "CACHED" for r in records)
    failed = sum(r["status"] == "FAILED" for r in records)

    print("\n========== TARGET DOWNLOAD SUMMARY ==========")
    print("Target:", target_name)
    print("Selected:", len(selected_rows))
    print("Downloaded:", downloaded)
    print("Cached:", cached)
    print("Failed:", failed)
    print("Target metadata:", metadata_file)


# ============================================================
# STEP 5: PROCESS ALL TARGETS
# ============================================================

def main():

    print("=" * 65)
    print("SPHEREx MULTI-TARGET SEARCH")
    print("=" * 65)

    print("Total targets:", len(TARGETS))

    if not 0 < CUTOUT_SIZE <= 1:
        raise ValueError(
            "CUTOUT_SIZE must be greater than 0 and at most 1 degree."
        )

    session = make_session()

    for target in TARGETS:

        print("\n\n")
        print("#" * 65)
        print("TARGET:", target["name"])
        print("#" * 65)

        print("Coordinate source:", target["coordinate_source"])
        print("Coordinate epoch:", target["coordinate_epoch"])
        print("Astrometry status:", target["astrometry_status"])

        if target["astrometry_status"] != "GAIA_MATCHED":
            print(
                "WARNING: astrometry is not fully verified; "
                "check cutout centering before analysis."
            )

        print("RA:", target["ra"])
        print("Dec:", target["dec"])

        try:

            rows = search_spherex(target["ra"], target["dec"])

            if len(rows) == 0:
                print("No observations found for this target.")
                continue

            download_observations(
                rows=rows,
                target=target,
                session=session,
                max_downloads=MAX_DOWNLOADS_PER_TARGET
            )

        except Exception as error:

            print(f"\nError processing {target['name']}:", error)
            continue

    rebuild_master_metadata()

    print("\n")
    print("=" * 65)
    print("MULTI-TARGET SEARCH COMPLETED")
    print("=" * 65)

    print("Observation directory:", OBSERVATION_DIR)
    print("Metadata directory:", METADATA_DIR)
    print("Combined metadata:", MASTER_METADATA_FILE)


if __name__ == "__main__":
    main()