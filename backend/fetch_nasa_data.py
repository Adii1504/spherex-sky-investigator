"""NASA / IPAC IRSA SPHEREx Data Fetcher.

Designed for Person 1 (Archive Data Specialist) and the entire SPHEREx WhyLab team.
Connects directly to the NASA/IPAC Infrared Science Archive (IRSA) TAP service,
queries SPHEREx observations (spherex.obscore), and downloads Level 2 MEF FITS files.

Usage:
    # Query and download observations near RA=150.0, Dec=2.0
    python backend/fetch_nasa_data.py --ra 150.0 --dec 2.0 --radius 0.2 --limit 4

    # List available SPHEREx fields in the archive
    python backend/fetch_nasa_data.py --list-fields
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

import certifi
import requests

IRSA_TAP_URL = "https://irsa.ipac.caltech.edu/TAP/sync"


def query_spherex_tap(
    ra_deg: float | None = None,
    dec_deg: float | None = None,
    radius_deg: float = 0.1,
    limit: int = 10,
    table: str = "spherex.obscore",
) -> list[dict[str, Any]]:
    """Query NASA IRSA Table Access Protocol (TAP) for SPHEREx observations."""
    if ra_deg is not None and dec_deg is not None:
        adql = f"""
        SELECT TOP {limit}
            target_name, s_ra, s_dec, t_min, t_max, em_min, em_max,
            access_url, access_format, obs_id, obs_collection
        FROM {table}
        WHERE 1 = CONTAINS(
            POINT('ICRS', s_ra, s_dec),
            CIRCLE('ICRS', {ra_deg}, {dec_deg}, {radius_deg})
        )
        """
    else:
        adql = f"""
        SELECT TOP {limit}
            target_name, s_ra, s_dec, t_min, t_max, em_min, em_max,
            access_url, access_format, obs_id, obs_collection
        FROM {table}
        """

    params = {
        "REQUEST": "doQuery",
        "LANG": "ADQL",
        "FORMAT": "json",
        "QUERY": adql.strip(),
    }

    try:
        response = requests.post(
            IRSA_TAP_URL,
            data=params,
            verify=certifi.where(),
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        fields = [f["name"] for f in data.get("metadata", [])]
        rows = data.get("data", [])
        return [dict(zip(fields, row)) for row in rows]
    except Exception as e:
        print(f"[ERROR] Failed to query IRSA TAP service: {e}", file=sys.stderr)
        return []


def download_fits_file(url: str, out_path: Path, chunk_size: int = 1024 * 1024) -> Path | None:
    """Download a FITS file with progress reporting and SSL certificate verification."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        print(f"Downloading from: {url}")
        with requests.get(url, stream=True, verify=certifi.where(), timeout=60) as r:
            r.raise_for_status()
            total_size = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            pct = (downloaded / total_size) * 100
                            print(f"\r  Progress: {downloaded / 1024 / 1024:.1f} MB / {total_size / 1024 / 1024:.1f} MB ({pct:.1f}%)", end="")
            print(f"\n[SAVED] {out_path.resolve()} ({out_path.stat().st_size / 1024 / 1024:.1f} MB)")
            return out_path
    except Exception as e:
        print(f"\n[ERROR] Failed to download {url}: {e}", file=sys.stderr)
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch real SPHEREx Level 2 FITS data from NASA/IPAC IRSA.")
    parser.add_argument("--ra", type=float, default=None, help="Right Ascension in degrees")
    parser.add_argument("--dec", type=float, default=None, help="Declination in degrees")
    parser.add_argument("--radius", type=float, default=0.2, help="Search cone radius in degrees")
    parser.add_argument("--limit", type=int, default=5, help="Maximum number of observations to fetch")
    parser.add_argument("--out-dir", type=str, default="backend/processing/sample_data/downloads", help="Output directory")
    parser.add_argument("--list-fields", action="store_true", help="List available archive observations")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    print("=" * 70)
    print(" SPHEREx WhyLab - NASA/IPAC IRSA Data Fetcher")
    print("=" * 70)

    records = query_spherex_tap(ra_deg=args.ra, dec_deg=args.dec, radius_deg=args.radius, limit=args.limit)
    print(f"Discovered {len(records)} SPHEREx observations matching criteria.")

    for i, r in enumerate(records):
        print(f"[{i + 1}] OBS_ID: {r.get('obs_id')} | RA: {r.get('s_ra')} | Dec: {r.get('s_dec')} | Target: {r.get('target_name')}")
        if args.list_fields:
            continue
        access_url = r.get("access_url")
        if access_url:
            filename = f"spherex_{r.get('obs_id', f'obs_{i+1}')}.fits"
            download_fits_file(access_url, out_dir / filename)


if __name__ == "__main__":
    main()
