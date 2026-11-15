"""Re-download WISE 0855 cutouts centred on the PROPAGATED position, and
retry the failed R Draconis product.

Why: the old WISE 0855 cutouts were centred on a static ~J2000 SIMBAD position.
The object moves ~8 arcsec/yr, so by 2025-26 it lies ~210 arcsec away,
outside the 0.1 deg (360 arcsec) cutouts.

Run from the project folder:  python fix_downloads.py
"""
import hashlib
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from astropy.io import fits
from astropy.time import Time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from spherex_astrometry import (OBSERVATION_DIR, SUPERSEDED_DIR, load_master,
                                metadata_dir, propagate, read_csv, write_csv)

IRSA_BASE_URL = "https://irsa.ipac.caltech.edu/"
CUTOUT_SIZE = 0.1  # degrees, same as before
# Same URL style the earlier successful run used: center=RA,DECd&size=0.1
R_DRA_RETRY_PRODUCT = "level2_2026W24_2B_0242_4D3_spx_l2b-v27-2026-272.fits"

LOG_FIELDS = ["target_key", "product", "mjd", "center_ra", "center_dec",
              "cutout_url", "filename", "status", "error"]


def make_session():
    retry = Retry(total=8, backoff_factor=5,
                  status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET",))
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": "SPHEREx-data-research/1.0"})
    return session


def validate_fits(path):
    with fits.open(path, memmap=False) as hdul:
        hdul.verify("exception")
        if len(hdul) < 2:
            raise ValueError("Invalid FITS structure.")
        if hdul[1].data is None:
            raise ValueError("IMAGE extension has no data.")


def download(session, url, output_path):
    temp = output_path.with_name(output_path.name + ".part")
    try:
        with session.get(url, stream=True, timeout=(30, 180)) as response:
            response.raise_for_status()
            ctype = response.headers.get("Content-Type", "").lower()
            if "html" in ctype or "xml" in ctype:
                raise ValueError(f"Non-FITS response: {ctype}")
            with open(temp, "wb") as file:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        file.write(chunk)
        validate_fits(temp)
        temp.replace(output_path)
    finally:
        if temp.exists():
            temp.unlink()


def download_with_retries(url, output_path, attempts=5):
    """Retry the WHOLE download on a fresh connection.

    urllib3's Retry only covers failures before the response body starts;
    a connection reset in the middle of the transfer needs this outer loop.
    """
    for attempt in range(1, attempts + 1):
        session = make_session()
        try:
            download(session, url, output_path)
            return
        except Exception as error:
            print(f"  attempt {attempt}/{attempts} failed: {str(error)[:110]}")
            if attempt == attempts:
                raise
            time.sleep(min(15 * attempt, 90))
        finally:
            session.close()


def build_url(source_uri, ra, dec):
    base = (source_uri if source_uri.startswith("http")
            else urljoin(IRSA_BASE_URL, source_uri.lstrip("/")))
    return f"{base}?center={ra:.8f},{dec:.8f}d&size={CUTOUT_SIZE}"


def collect_source_uris(meta_dir):
    """product basename -> (source_uri, mjd) from every observations CSV."""
    found = {}
    for path in meta_dir.glob("*observations*.csv"):
        for row in read_csv(path):
            uri = row.get("source_uri", "")
            if uri:
                found[Path(urlparse(uri).path).name] = (
                    uri, row.get("observation_date", ""))
    return found


def main():
    meta_dir = metadata_dir()
    master = load_master(meta_dir)
    sources = collect_source_uris(meta_dir)
    manifest = read_csv(meta_dir / "clean_dataset_manifest.csv")

    OBSERVATION_DIR.mkdir(parents=True, exist_ok=True)
    SUPERSEDED_DIR.mkdir(parents=True, exist_ok=True)

    jobs = []  # (target_key, product, old_filename_or_None)

    for row in manifest:
        if row["target"] == "WISE 0855":
            jobs.append(("WISE_0855", row["product_name"], row["filename"]))

    jobs.append(("R_Draconis", R_DRA_RETRY_PRODUCT, None))

    log = []

    for job_number, (target_key, product, old_filename) in enumerate(jobs):
        if job_number:
            time.sleep(3)  # be gentle with IRSA; it returns 503 under load
        record = {"target_key": target_key, "product": product,
                  "status": "FAILED", "error": ""}
        log.append(record)

        try:
            # R Draconis: if the earlier retry script already fetched this
            # product (under its own filename), do not download it again.
            if target_key == "R_Draconis":
                for existing_path in OBSERVATION_DIR.glob(f"R_Draconis_*{product}"):
                    try:
                        validate_fits(existing_path)
                        record["filename"] = existing_path.name
                        record["status"] = "CACHED"
                        break
                    except Exception:
                        continue
                if record["status"] == "CACHED":
                    print(f"Already have {record['filename']}")
                    continue

            if product not in sources:
                raise KeyError("source_uri not found in observation CSVs")

            source_uri, mjd = sources[product]
            record["mjd"] = mjd

            position = propagate(master[target_key],
                                 Time(float(mjd), format="mjd", scale="utc"))
            ra, dec = float(position.ra.deg), float(position.dec.deg)
            record["center_ra"], record["center_dec"] = f"{ra:.8f}", f"{dec:.8f}"

            url = build_url(source_uri, ra, dec)
            record["cutout_url"] = url

            digest = hashlib.sha1((source_uri + "|pmc").encode()).hexdigest()[:8]
            clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", product)
            filename = f"{target_key}_pmc_{digest}_{clean}"
            record["filename"] = filename
            output_path = OBSERVATION_DIR / filename

            if output_path.exists():
                validate_fits(output_path)
                record["status"] = "CACHED"
            else:
                print(f"Downloading {filename}")
                download_with_retries(url, output_path)
                record["status"] = "DOWNLOADED"

            # Retire the old static-centred WISE 0855 file.
            if old_filename:
                old_path = OBSERVATION_DIR / Path(old_filename.replace("\\", "/")).name
                if old_path.exists():
                    old_path.replace(SUPERSEDED_DIR / old_path.name)

        except Exception as error:
            record["error"] = str(error)[:400]
            print(f"FAILED {product}: {error}")

    write_csv(meta_dir / "redownload_log.csv", LOG_FIELDS, log)

    ok = sum(r["status"] in ("DOWNLOADED", "CACHED") for r in log)
    print(f"\nDone: {ok}/{len(log)} succeeded. Log: {meta_dir / 'redownload_log.csv'}")
    if ok < len(log):
        print("Some failed. Wait a few minutes and run again; finished files are skipped.")


if __name__ == "__main__":
    main()