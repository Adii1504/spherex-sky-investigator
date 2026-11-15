"""Shared helpers: load the master astrometry table and propagate positions."""
import csv
import warnings
from pathlib import Path

import astropy.units as u
from astropy.coordinates import Distance, SkyCoord
from astropy.time import Time
from erfa import ErfaWarning

# WISE 0855 has no parallax in the table, so astropy warns about a dummy
# distance. Pure proper-motion propagation is intended there.
warnings.filterwarnings("ignore", category=ErfaWarning)

BASE_DIR = Path(__file__).resolve().parent
OBSERVATION_DIR = BASE_DIR / "data" / "observations"
SUPERSEDED_DIR = BASE_DIR / "data" / "superseded"


def metadata_dir():
    for candidate in (BASE_DIR / "data" / "metadata", BASE_DIR / "metadata"):
        if candidate.exists():
            return candidate
    path = BASE_DIR / "data" / "metadata"
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def write_csv(path, fieldnames, rows):
    temp = Path(str(path) + ".tmp")
    with open(temp, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames,
                                restval="", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def load_master(meta_dir):
    """Return {target_key: row}. Keys match the FITS filename prefixes."""
    path = meta_dir / "target_astrometry_master.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Copy target_astrometry_master.csv there."
        )
    return {row["target_key"]: row for row in read_csv(path)}


def _num(value):
    value = (value or "").strip()
    return float(value) if value else None


def propagate(entry, obs_time):
    """Position of the target at obs_time (astropy Time, UTC)."""
    kwargs = dict(
        ra=_num(entry["ra_deg"]) * u.deg,
        dec=_num(entry["dec_deg"]) * u.deg,
        pm_ra_cosdec=_num(entry["pmra_cosdec_mas_yr"]) * u.mas / u.yr,
        pm_dec=_num(entry["pmdec_mas_yr"]) * u.mas / u.yr,
        obstime=Time(_num(entry["ref_epoch_jyear"]), format="jyear"),
        frame="icrs",
    )

    parallax = _num(entry.get("parallax_mas"))

    if parallax and parallax > 0:
        rv = _num(entry.get("radial_velocity_kms"))
        kwargs["distance"] = Distance(parallax=parallax * u.mas)
        # Missing RV -> zero (documented assumption; effect << 1 pixel).
        kwargs["radial_velocity"] = (rv if rv is not None else 0.0) * u.km / u.s

    return SkyCoord(**kwargs).apply_space_motion(new_obstime=obs_time)
