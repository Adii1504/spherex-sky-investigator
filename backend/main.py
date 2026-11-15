"""SPHEREx WhyLab - FastAPI Backend Server.

Provides RESTful endpoints for astronomical data ingestion, multi-wavelength
alignment, scientific difference imaging, ViewSpace hotspot discovery,
photometric SED extraction, and hypothesis testing on proper motion.
"""

from __future__ import annotations

import io
import os
import inspect
import json
from functools import wraps
from uuid import uuid4
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
os.environ.setdefault("MPLCONFIGDIR", str(BASE_DIR / ".data" / "mplcache"))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from backend.processing.diagnostic import plot_sed_spectrum, plot_trajectory_fit
from backend.processing import PROCESSING_LOCK
from backend.processing.result_cache import ResultCache
from whylab.generated_cache import trim_directories, CacheCapacity
from backend.processing import targets_registry
from backend.processing.alignment import make_common_grid, reproject_to_grid
from backend.processing.display import create_rgb_composite
from backend.processing.io_fits import load_observation
from backend.processing.measure import extract_sed
from backend.processing.motion import scan_and_track_motion
from backend.processing.pipeline import run_investigation_pipeline
from backend.processing.targets_registry import (
    get_target_manifest,
    get_target_observations,
    load_astrometry_ground_truth,
)

app = FastAPI(
    title="SPHEREx WhyLab API",
    description="NASA SPHEREx Multi-Wavelength Astronomical Investigation & ViewSpace Analysis Suite",
    version="1.0.0",
)

# Enable CORS for React frontend (Person 3)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent.parent
SAMPLE_DATA_DIR = BASE_DIR / "backend" / "processing" / "sample_data"
SEQUENCE_DIR = SAMPLE_DATA_DIR / "sequence"
PREVIEWS_DIR = BASE_DIR / ".data" / "processing" / "previews"
PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)
RESULT_CACHE = ResultCache()


def dataset_signature(preset):
    known = {"Barnards_Star", "WISE_0855", "Epsilon_Indi_B", "RW_Aurigae", "R_Draconis"}
    canonical = next((key for key in known if key.lower() == str(preset).lower()), None)
    if canonical:
        paths = [targets_registry.METADATA_DIR / name for name in
                 ("target_astrometry_master.csv", "target_coordinates_per_observation.csv")]
        paths += sorted(targets_registry.FITS_DIR.glob(canonical + "_*.fits"))
    elif preset == "synthetic_asteroid_sequence":
        paths = sorted(SEQUENCE_DIR.glob("*.fits"))
    elif preset == "nasa_real_6bands":
        paths = sorted(SAMPLE_DATA_DIR.glob("spherex_d*_cutout.fits"))
    else:
        return None
    return tuple((str(path),path.stat().st_size,path.stat().st_mtime_ns) for path in paths if path.is_file())


def cached_processing(function):
    signature = inspect.signature(function)
    @wraps(function)
    def run(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        values = {key:getattr(value,"default",value) for key,value in bound.arguments.items()}
        # User uploads are private, potentially mutable inputs; never memoize them.
        if values.get('files'):
            return function(*args,**kwargs)
        preset = values.get('preset_id', 'nasa_real_6bands')
        fingerprint = dataset_signature(preset)
        if fingerprint is None:
            return function(*args,**kwargs)
        request = values.pop('request',None)
        prefix = request.scope.get('root_path','') if request else ''
        key = (function.__name__,str(PREVIEWS_DIR.resolve()),prefix,
               json.dumps(values,sort_keys=True,default=str,allow_nan=False),fingerprint)
        result = RESULT_CACHE.get(key)
        if result is not None:
            return result
        # One computation per key; cached requests bypass unrelated plotting work.
        with PROCESSING_LOCK:
            result = RESULT_CACHE.get(key)
            if result is None:
                result = function(*args,**kwargs)
                expected_frames = sum(str(path).endswith('.fits') for path,_,_ in fingerprint)
                if function.__name__ != 'investigate_sequence' or len(result.get('frames',[])) == expected_frames:
                    RESULT_CACHE.put(key,result,PREVIEWS_DIR)
            return result
    return run


def serialized(function):
    @wraps(function)
    def run(*args, **kwargs):
        with PROCESSING_LOCK:
            return function(*args, **kwargs)
    return run


def new_output(request=None):
    try:
        trim_directories(PREVIEWS_DIR,0,100_000_000,128)
    except CacheCapacity as exc:
        raise HTTPException(413, str(exc))
    token = uuid4().hex
    directory = PREVIEWS_DIR / token
    directory.mkdir(parents=True)
    prefix = (request.scope.get("root_path", "") if request else "") + "/previews/" + token
    return directory, prefix

# Mount static previews directory
app.mount("/previews", StaticFiles(directory=str(PREVIEWS_DIR)), name="previews")


@app.get("/api/health")
def health_check() -> dict[str, Any]:
    """Return system status, module health, and available sample datasets."""
    synthetic_epochs = sorted(SEQUENCE_DIR.glob("spherex_synth_epoch_*.fits"))
    real_bands = sorted(SAMPLE_DATA_DIR.glob("spherex_d*_cutout.fits"))
    return {
        "status": "healthy",
        "service": "SPHEREx WhyLab Scientific Processing API",
        "version": "1.0.0",
        "sample_sequence_epochs_available": len(synthetic_epochs),
        "real_nasa_bands_available": len(real_bands),
        "detectors_supported": ["D1 (0.75-1.11 um)", "D2 (1.11-1.64 um)", "D3 (1.64-2.42 um)",
                                "D4 (2.42-3.82 um)", "D5 (3.82-4.42 um)", "D6 (4.42-5.00 um)"],
    }


@app.get("/api/presets")
def list_presets() -> list[dict[str, Any]]:
    """Return available pre-packaged astronomical investigation presets."""
    presets = [
        {
            "id": "Barnards_Star",
            "title": "Barnard's Star (NASA Real Level 2, ~10.4''/yr Proper Motion)",
            "description": "Real NASA SPHEREx cutouts across 2025-2026 for the fastest-moving star in the sky. Demonstrates textbook signed dipole differencing and Gaia DR3 ground-truth tracking.",
            "num_frames": 5,
            "target_coord": [269.4464, 4.7671],
            "category": "real_nasa_l2",
            "expected_outcome": "proper_motion_benchmark",
        },
        {
            "id": "WISE_0855",
            "title": "WISE 0855-0714 (NASA Real Level 2, Cold Rogue World)",
            "description": "Real SPHEREx multi-epoch cutouts of the coldest known sub-brown dwarf (T ~ 250 K). Confirmed ~8.0''/yr proper motion verified by pipeline hypothesis testing.",
            "num_frames": 5,
            "target_coord": [133.7618, -7.2420],
            "category": "real_nasa_l2",
            "expected_outcome": "motion_supported",
        },
        {
            "id": "Epsilon_Indi_B",
            "title": "Epsilon Indi B (NASA Real Level 2, Brown Dwarf Binary)",
            "description": "Real SPHEREx Level 2 observations of nearby high proper motion brown dwarf binary (~4.7''/yr) with sub-arcsecond Gaia DR3 alignment.",
            "num_frames": 3,
            "target_coord": [331.0973, -56.8009],
            "category": "real_nasa_l2",
            "expected_outcome": "sub_arcsec_astrometry",
        },
        {
            "id": "RW_Aurigae",
            "title": "RW Aurigae A (NASA Real Level 2, Classical T Tauri)",
            "description": "Multi-band SPHEREx cutouts across detectors D1, D2, D3, D4 showing young stellar accretion and circumstellar disk environment.",
            "num_frames": 4,
            "target_coord": [76.9561, 30.4011],
            "category": "real_nasa_l2",
            "expected_outcome": "stationary_plausible",
        },
        {
            "id": "R_Draconis",
            "title": "R Draconis (NASA Real Level 2, Mira-Type Variable)",
            "description": "Real SPHEREx observations of long-period pulsating red giant across detector bands D1 to D3.",
            "num_frames": 4,
            "target_coord": [248.1672, 66.7550],
            "category": "real_nasa_l2",
            "expected_outcome": "pulsating_variable",
        },
        {
            "id": "synthetic_asteroid_sequence",
            "title": "Solar System Asteroid Discovery (4 Epochs)",
            "description": "Multi-epoch SPHEREx sequence simulating a 12.0 arcsec/hr asteroid moving across stationary field stars. Ideal for testing differencing, blinking, and hypothesis testing.",
            "num_frames": 4,
            "target_coord": [149.992, 1.992],
            "category": "synthetic_benchmark",
            "expected_outcome": "motion_supported",
        },
        {
            "id": "nasa_real_6bands",
            "title": "Real NASA SPHEREx Level 2 Multi-Band Field (D1 to D6)",
            "description": "Real Level 2 MEF observations downloaded directly from NASA IRSA across all 6 detector arrays (0.75 - 5.0 um). Replicates signature ViewSpace multi-wavelength false-color analysis.",
            "num_frames": 6,
            "target_coord": [150.0, 2.0],
            "category": "viewspace_composite",
            "expected_outcome": "viewspace_composite",
        },
    ]


    for preset in presets:
        if preset["id"] in ("Barnards_Star", "WISE_0855", "Epsilon_Indi_B", "RW_Aurigae", "R_Draconis"):
            preset["description"] = "Supplied SPHEREx Level 2 observations with adopted Gaia/CatWISE astrometry. Examine processing notes and source quality; field coverage does not confirm source detection or motion."
            preset["expected_outcome"] = "requires_evidence"
        elif preset["id"] == "synthetic_asteroid_sequence":
            preset["title"] = "Synthetic moving-source demonstration (4 observations)"
            preset["description"] = "Explicitly simulated observations for testing alignment, blinking and motion hypotheses; not a real discovery."
    return presets


@app.post("/api/investigate")
@cached_processing
@serialized
def investigate_sequence(
    files: list[UploadFile] | None = File(None),
    preset_id: str | None = Form(None),
    target_ra: float | None = Form(None, ge=0, lt=360, allow_inf_nan=False),
    target_dec: float | None = Form(None, ge=-90, le=90, allow_inf_nan=False),
    investigation_id: str = Form("SPX_INV_001", max_length=80, pattern=r"^[A-Za-z0-9_-]+$"),
    fov_arcmin: float = Form(3.0, gt=0, le=30, allow_inf_nan=False),
    grid_size_px: int = Form(128, ge=32, le=512),
    request: Request = None,
) -> dict[str, Any]:
    """Execute the full SPHEREx WhyLab processing pipeline.

    Accepts uploaded FITS files or a preset identifier (e.g. 'Barnards_Star', 'synthetic_asteroid_sequence').
    """
    if hasattr(files, "default"):
        files = None
    if hasattr(preset_id, "default"):
        preset_id = preset_id.default
    if hasattr(target_ra, "default"):
        target_ra = target_ra.default
    if hasattr(target_dec, "default"):
        target_dec = target_dec.default
    if hasattr(investigation_id, "default"):
        investigation_id = str(investigation_id.default)
    else:
        investigation_id = str(investigation_id)
    if hasattr(fov_arcmin, "default"):
        fov_arcmin = float(fov_arcmin.default)
    else:
        fov_arcmin = float(fov_arcmin)
    if hasattr(grid_size_px, "default"):
        grid_size_px = int(grid_size_px.default)
    else:
        grid_size_px = int(grid_size_px)

    fits_inputs: list[Any] = []
    if not preset_id and not files:
        raise HTTPException(422, "Choose a dataset preset or upload FITS files.")
    if (target_ra is None) != (target_dec is None):
        raise HTTPException(422, "Both target coordinates are required together.")
    target_coord = (float(target_ra), float(target_dec)) if target_ra is not None and target_dec is not None else None

    real_targets = ["Barnards_Star", "WISE_0855", "Epsilon_Indi_B", "RW_Aurigae", "R_Draconis"]
    matched_target = next((t for t in real_targets if preset_id and t.lower() == preset_id.lower()), None)

    if isinstance(files, list) and len(files) > 0 and getattr(files[0], "filename", None):
        if len(files) > 12:
            raise HTTPException(413, "At most 12 FITS inputs are supported per request.")
        uploaded_bytes = 0
        for f in files:
            content = f.file.read(50_000_001)
            uploaded_bytes += len(content)
            if len(content) > 50_000_000:
                raise HTTPException(413, "FITS input exceeds the 50 MB processing limit.")
            if uploaded_bytes > 100_000_000:
                raise HTTPException(413, "Combined FITS inputs exceed the 100 MB processing limit.")
            try:
                observation = load_observation(io.BytesIO(content))
            except Exception:
                raise HTTPException(422, "Upload must contain a FITS science image with celestial WCS.")
            fits_inputs.append(observation)
    elif matched_target:
        obs_list = get_target_observations(matched_target)
        if not obs_list:
            raise HTTPException(status_code=404, detail=f"No FITS cutouts found for target {matched_target}")
        fits_inputs = obs_list
        if target_coord is None and obs_list[0].header_meta.get("TRUE_RA_DEG"):
            target_coord = (
                float(obs_list[0].header_meta["TRUE_RA_DEG"]),
                float(obs_list[0].header_meta["TRUE_DEC_DEG"]),
            )
        investigation_id = f"SPX_{matched_target.upper()}"
    elif preset_id == "synthetic_asteroid_sequence" or (not files and not preset_id):
        epoch_paths = sorted(SEQUENCE_DIR.glob("spherex_synth_epoch_*.fits"))
        if not epoch_paths:
            raise HTTPException(status_code=404, detail="Synthetic sequence dataset not found on disk.")
        fits_inputs = epoch_paths
        if target_coord is None:
            target_coord = (149.992, 1.992)
    elif preset_id == "nasa_real_6bands":
        band_paths = sorted(SAMPLE_DATA_DIR.glob("spherex_d*_cutout.fits"))
        if not band_paths:
            raise HTTPException(status_code=404, detail="Real NASA multi-band cutouts not found on disk.")
        fits_inputs = band_paths
    else:
        raise HTTPException(status_code=400, detail=f"Invalid preset or missing FITS files: '{preset_id}'")

    output, prefix = new_output(request)
    result = run_investigation_pipeline(
        fits_inputs=fits_inputs,
        target_coord=target_coord,
        investigation_id=investigation_id,
        fov_arcmin=fov_arcmin,
        grid_size_px=grid_size_px,
        output_dir=output,
        base_url_prefix=prefix,
    )

    # Attach Gaia DR3 ground truth if target matches
    if matched_target:
        truth_dict = load_astrometry_ground_truth()
        truth = truth_dict.get(matched_target)
        if truth:
            result["gaia_ground_truth"] = {
                "source_catalogue": truth.source_catalogue,
                "source_id": truth.source_id,
                "ref_epoch": truth.ref_epoch_jyear,
                "proper_motion_ra_mas_yr": truth.pmra_cosdec_mas_yr,
                "proper_motion_dec_mas_yr": truth.pmdec_mas_yr,
                "total_proper_motion_arcsec_yr": round(truth.total_proper_motion_arcsec_yr, 3),
                "quality_flag": truth.quality_flag,
                "notes": truth.notes,
            }

    # Automatically generate diagnostic trajectory plot if motion was evaluated
    if result.get("outcome") in ("motion_supported", "stationary_plausible", "insufficient_evidence") and result.get("measurements"):
        diag_path = output / f"{investigation_id}_trajectory_diagnostic.png"
        plot_trajectory_fit(result, out_png_path=diag_path)
        result["diagnostic_trajectory_url"] = f"{prefix}/{diag_path.name}"

    result["preset_id"] = matched_target or preset_id
    result["data_kind"] = "synthetic demonstration" if preset_id == "synthetic_asteroid_sequence" else "supplied FITS observations"
    result["warnings"].append("Exploratory processing: catalogue association and adopted flag policy require independent scientific review.")
    if matched_target:
        result["warnings"].append("Gaia/CatWISE values are adopted reference astrometry, not measured source truth.")
        if truth:
            result["warnings"].append(truth.notes)

    return result


@app.get("/api/hotspots")
@cached_processing
@serialized
def get_hotspots(preset_id: str = "synthetic_asteroid_sequence") -> dict[str, Any]:
    """Return all detected celestial hotspots, classifications, and proper motion tracks."""
    real_targets = ["Barnards_Star", "WISE_0855", "Epsilon_Indi_B", "RW_Aurigae", "R_Draconis"]
    matched_target = next((t for t in real_targets if preset_id and t.lower() == preset_id.lower()), None)

    if matched_target:
        obs_list = get_target_observations(matched_target)
        if not obs_list:
            raise HTTPException(status_code=404, detail=f"No FITS cutouts found for target {matched_target}")
    elif preset_id == "synthetic_asteroid_sequence":
        epoch_paths = sorted(SEQUENCE_DIR.glob("spherex_synth_epoch_*.fits"))
        obs_list = [load_observation(p) for p in epoch_paths]
    elif preset_id == "nasa_real_6bands":
        epoch_paths = sorted(SAMPLE_DATA_DIR.glob("spherex_d*_cutout.fits"))
        obs_list = [load_observation(p) for p in epoch_paths]
    else:
        raise HTTPException(status_code=400, detail=f"Unknown preset: '{preset_id}'")

    scan = scan_and_track_motion(obs_list, snr_threshold=3.5, match_radius_arcsec=30.0)
    return scan


@app.get("/api/sed")
@cached_processing
@serialized
def get_sed(
    ra_deg: float = Query(150.0, ge=0, lt=360, allow_inf_nan=False),
    dec_deg: float = Query(2.0, ge=-90, le=90, allow_inf_nan=False),
    preset_id: str = "nasa_real_6bands",
    request: Request = None,
) -> dict[str, Any]:
    """Extract Spectral Energy Distribution (SED) across all 6 real SPHEREx detector bands."""
    if preset_id in ("Barnards_Star", "WISE_0855", "Epsilon_Indi_B", "RW_Aurigae", "R_Draconis"):
        observations = get_target_observations(preset_id)
    elif preset_id == "synthetic_asteroid_sequence":
        observations = [load_observation(p) for p in sorted(SEQUENCE_DIR.glob("spherex_synth_epoch_*.fits"))]
    elif preset_id == "nasa_real_6bands":
        observations = [load_observation(p) for p in sorted(SAMPLE_DATA_DIR.glob("spherex_d*_cutout.fits"))]
    else:
        raise HTTPException(404, "Unknown SED dataset")
    if not observations:
        raise HTTPException(404, "No observations for this SED dataset")
    sed_result = extract_sed(ra_deg=ra_deg, dec_deg=dec_deg, observations=observations)

    # Generate SED diagnostic plot
    output, prefix = new_output(request)
    out_sed_png = output / "sed.png"
    plot_sed_spectrum(sed_result, out_png_path=out_sed_png)
    sed_result["sed_plot_url"] = f"{prefix}/{out_sed_png.name}"
    sed_result["warnings"].append("Exploratory peak-pixel spectral samples; not calibrated integrated source photometry.")

    return sed_result


@app.post("/api/composite")
@cached_processing
@serialized
def build_viewspace_composite(
    red_band: int = Form(6, ge=1, le=6),
    green_band: int = Form(3, ge=1, le=6),
    blue_band: int = Form(1, ge=1, le=6),
    request: Request = None,
) -> dict[str, Any]:
    """Generate a 3-channel false-color RGB composite replicating ViewSpace visualization."""
    if hasattr(red_band, "default"):
        red_band = int(red_band.default)
    else:
        red_band = int(red_band)
    if hasattr(green_band, "default"):
        green_band = int(green_band.default)
    else:
        green_band = int(green_band)
    if hasattr(blue_band, "default"):
        blue_band = int(blue_band.default)
    else:
        blue_band = int(blue_band)

    r_path = SAMPLE_DATA_DIR / f"spherex_d{red_band}_cutout.fits"
    g_path = SAMPLE_DATA_DIR / f"spherex_d{green_band}_cutout.fits"
    b_path = SAMPLE_DATA_DIR / f"spherex_d{blue_band}_cutout.fits"

    for p in (r_path, g_path, b_path):
        if not p.exists():
            raise HTTPException(status_code=404, detail=f"Band cutout {p.name} not found.")

    obs_r = load_observation(r_path)
    obs_g = load_observation(g_path)
    obs_b = load_observation(b_path)

    # Channels must refer to the same celestial grid before RGB composition.
    height, width = obs_r.image.shape
    ra, dec = obs_r.wcs.pixel_to_world_values((width-1)/2, (height-1)/2)
    grid = make_common_grid(float(ra), float(dec), 3.0, 128)
    aligned = [reproject_to_grid(obs, grid, (128, 128)) for obs in (obs_r, obs_g, obs_b)]
    output, prefix = new_output(request)
    out_png = output / "composite.png"
    _, saved_path, warnings = create_rgb_composite(
        r_image=aligned[0][0], g_image=aligned[1][0], b_image=aligned[2][0],
        r_mask=aligned[0][1], g_mask=aligned[1][1], b_mask=aligned[2][1],
        out_png_path=out_png,
    )

    return {
        "title": "ViewSpace False-Color RGB Composite",
        "red_channel": f"SPHEREx Band {red_band} (Long wavelength, dust/zodi)",
        "green_channel": f"SPHEREx Band {green_band} (Intermediate wavelength, warm dust/ices)",
        "blue_channel": f"SPHEREx Band {blue_band} (Short wavelength, stellar continuum)",
        "composite_url": f"{prefix}/{out_png.name}",
        "warnings": warnings + [w for _, _, items in aligned for w in items],
    }


# Serve the interactive ViewSpace UI
FRONTEND_DIR = BASE_DIR / "frontend_viewspace"
if FRONTEND_DIR.exists():
    app.mount("/viewer", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="viewer")


@app.get("/", response_class=HTMLResponse)
def root_redirect():
    """Redirect or serve the ViewSpace web viewer."""
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return HTMLResponse("<h1>SPHEREx WhyLab API</h1><p>Visit <a href='/docs'>/docs</a> for interactive OpenAPI documentation.</p>")


if FRONTEND_DIR.exists():
    # Register after API routes; the page's relative CSS/JS also work at '/'.
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="viewer-assets")
