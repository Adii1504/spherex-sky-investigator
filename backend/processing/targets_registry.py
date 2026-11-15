"""SPHEREx Target Registry & Metadata Loader.

Loads and structures validated Level 2 SPHEREx FITS observations and Gaia DR3
astrometric ground truth for benchmark astronomical targets:
- Barnard's Star (Fastest known stellar proper motion: ~10.37 arcsec/year)
- Epsilon Indi B (High proper motion brown dwarf binary: ~4.7 arcsec/year)
- WISE 0855-0714 (Coldest known sub-brown dwarf / rogue planetary-mass object)
- RW Aurigae (Young stellar object / classical T Tauri binary)
- R Draconis (Mira-type long-period pulsating red giant)
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.processing.io_fits import Observation, load_observation

BASE_DIR = Path(__file__).resolve().parent.parent.parent
FINAL_DATASET_DIR = BASE_DIR / "PythonProject" / "final_dataset"
FITS_DIR = FINAL_DATASET_DIR / "fits"
METADATA_DIR = FINAL_DATASET_DIR / "metadata"


@dataclass
class TargetAstrometryTruth:
    target_key: str
    target_name: str
    ra_deg: float
    dec_deg: float
    ref_epoch_jyear: float
    pmra_cosdec_mas_yr: float
    pmdec_mas_yr: float
    parallax_mas: float | None
    radial_velocity_kms: float | None
    source_catalogue: str
    source_id: str
    ruwe: float | None
    quality_flag: str
    notes: str

    @property
    def total_proper_motion_mas_yr(self) -> float:
        import math
        return math.hypot(self.pmra_cosdec_mas_yr, self.pmdec_mas_yr)

    @property
    def total_proper_motion_arcsec_yr(self) -> float:
        return self.total_proper_motion_mas_yr / 1000.0


def load_astrometry_ground_truth() -> dict[str, TargetAstrometryTruth]:
    """Load adopted Gaia DR3 / CatWISE ground-truth astrometry from master CSV."""
    csv_path = METADATA_DIR / "target_astrometry_master.csv"
    if not csv_path.exists():
        return {}

    truth_dict: dict[str, TargetAstrometryTruth] = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            key = r["target_key"]
            truth_dict[key] = TargetAstrometryTruth(
                target_key=key,
                target_name=r["target_name"],
                ra_deg=float(r["ra_deg"]),
                dec_deg=float(r["dec_deg"]),
                ref_epoch_jyear=float(r["ref_epoch_jyear"]),
                pmra_cosdec_mas_yr=float(r["pmra_cosdec_mas_yr"]),
                pmdec_mas_yr=float(r["pmdec_mas_yr"]),
                parallax_mas=float(r["parallax_mas"]) if r.get("parallax_mas") else None,
                radial_velocity_kms=float(r["radial_velocity_kms"]) if r.get("radial_velocity_kms") else None,
                source_catalogue=r.get("source_catalogue", "Gaia DR3"),
                source_id=r.get("source_id", ""),
                ruwe=float(r["ruwe"]) if r.get("ruwe") else None,
                quality_flag=r.get("quality_flag", "UNKNOWN"),
                notes=r.get("notes", ""),
            )
    return truth_dict


def get_target_manifest() -> list[dict[str, Any]]:
    """Return all validated observation metadata entries from manifest."""
    csv_path = METADATA_DIR / "target_coordinates_per_observation.csv"
    if not csv_path.exists():
        return []

    entries: list[dict[str, Any]] = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            filename = row["filename"]
            fits_path = FITS_DIR / filename
            row["fits_path"] = str(fits_path)
            row["file_exists"] = fits_path.exists()
            entries.append(row)
    return entries


def get_target_observations(target_key: str) -> list[Observation]:
    """Load all chronological SPHEREx Observation objects for a specific target."""
    manifest = get_target_manifest()
    target_entries = [e for e in manifest if e["target_key"].lower() == target_key.lower()]
    # Sort chronologically by date_obs
    target_entries.sort(key=lambda x: x.get("date_obs", ""))

    observations: list[Observation] = []
    for entry in target_entries:
        path = Path(entry["fits_path"])
        if path.exists():
            obs = load_observation(path)
            # Annotate with propagated true coordinates
            if entry.get("ra_at_obs_deg") and entry.get("dec_at_obs_deg"):
                obs.header_meta["TRUE_RA_DEG"] = float(entry["ra_at_obs_deg"])
                obs.header_meta["TRUE_DEC_DEG"] = float(entry["dec_at_obs_deg"])
            obs.header_meta["TARGET_NAME"] = entry.get("target_name", target_key)
            observations.append(obs)
    return observations
