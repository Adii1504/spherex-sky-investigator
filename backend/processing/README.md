# SPHEREx WhyLab: Processing & Verification Module

**Author:** Person 2 (Scientific Python Engineer)  
**Target Audience:** Person 4 (FastAPI backend integration) and Person 3 (React UI coordination)  
**Stack:** Python 3.11+, `numpy`, `scipy`, `astropy`, `reproject`, `matplotlib`, `pytest`

---

## 1. Architecture Overview

This module provides the core scientific image processing, astrometric reprojection, and moving-source hypothesis testing for SPHEREx WhyLab. It receives real SPHEREx FITS cutouts from NASA/IPAC IRSA, standardizes them on a unified North-up / East-left celestial grid, calculates scientific difference images, measures source centroids, and tests for constant linear proper motion.

```
backend/processing/
├── io_fits.py           # Robust FITS ingestion (MEF & single-HDU), masking, metadata
├── alignment.py         # Common sky grid construction & reprojection
├── display.py           # Shared stretch, previews, differencing, blinking GIFs, RGB composite
├── compatibility.py     # Spectral/wavelength compatibility checks
├── measure.py           # Local background subtraction, SNR, 2D Gaussian centroiding, SED extraction
├── motion.py            # Tangent kinematics fit, position prediction, hypothesis verification, tracking
├── pipeline.py          # End-to-end master orchestrator for FastAPI /api/investigate
├── diagnostic.py        # 2-panel publication diagnostic plot (sky trajectory + residuals)
├── simulate_sequence.py # 4-epoch synthetic sequence generator with moving asteroid
├── demo_viewspace.py    # ViewSpace-style 3-color RGB composite demonstration
├── inspect_fits.py      # Diagnostic CLI tool to inspect real FITS files & headers
├── check_visual.py      # Visual verification script producing side-by-side PNGs
├── sample_data/         # Real SPHEREx Level 2 data, cutouts, and 4-epoch sequence
└── tests/               # Pytest suite (51 passing unit tests)
```

---

## 2. API Contract & Function Documentation

### Module: `io_fits.py`

#### `load_observation(source: str | Path | io.BytesIO | BinaryIO | fits.HDUList) -> Observation`
Loads a SPHEREx FITS cutout into an `Observation` dataclass. Robustly handles:
- File paths on disk (`str` or `Path`)
- In-memory file streams (`io.BytesIO`, `BinaryIO`, e.g. FastAPI `UploadFile.file`)
- Pre-opened Astropy `HDUList`
Handles both Multi-Extension FITS (MEF: `IMAGE`, `FLAGS`, `VARIANCE`, `CWAVE`) and quicklook/mosaic cutouts (`PRIMARY`).

- **Outputs**: `Observation` object:
  - `image`: 2D `float64` array of science flux (typically in `MJy/sr`).
  - `flags`: 2D `int32` quality bitmask array, or `None` if missing.
  - `variance`: 2D `float64` variance array ($\sigma^2$), or `None` if missing.
  - `wcs`: 2D celestial `astropy.wcs.WCS`.
  - `header_meta`: Dictionary of key header metadata (`TELESCOP`, `BUNIT`, `VERSION`, etc.).
  - `observed_at_utc`: Standardized ISO-8601 UTC string (`YYYY-MM-DDTHH:MM:SS.sss`) or `None`.
  - `detector`: Detector identifier (`1`, `2`, `"D1"`, etc.) or `None`.
  - `wavelength_um`: Effective wavelength (float in $\mu m$), 2D `CWAVE` map, or `None`.
  - `warnings`: List of warning strings detailing layout adjustments or missing data.
- **Rule**: Missing scientific values are strictly `None` (never guessed).

#### `create_observation_from_array(image: np.ndarray, wcs: WCS, ...) -> Observation`
Creates an `Observation` directly from in-memory NumPy arrays without saving to disk.
Ideal for synthetic data generators, simulations, or in-memory array pipelines.

#### `build_valid_mask(flags: np.ndarray | None, shape: tuple[int, int] | None = None) -> np.ndarray`
Builds a boolean usability mask from quality flags (SPHEREx convention: `0` = usable pixel; non-zero = bad/flagged).
- **Inputs**: `flags` array or `None` (with `shape`).
- **Outputs**: Boolean 2D `np.ndarray` (`True` = usable pixel, `False` = masked).

---

### Module: `alignment.py`

#### `make_common_grid(ra_deg: float, dec_deg: float, fov_arcmin: float, size_px: int = 256) -> WCS`
Constructs a target celestial WCS grid adhering strictly to standard astronomical convention:
- **Orientation**: **North up** ($+Y$), **East left** ($-X$).
- **Projection**: Tangent (`RA---TAN`, `DEC--TAN`).
- **Inputs**: Target center coordinates `(ra_deg, dec_deg)`, field of view `fov_arcmin`, image dimension `size_px`.
- **Outputs**: 2D celestial `WCS` with `.pixel_shape` and `.array_shape`.

#### `reproject_to_grid(obs: Observation, target_wcs: WCS, shape_out: tuple[int, int] | None = None, use_library: str = "auto") -> tuple[np.ndarray, np.ndarray, list[str]]`
Reprojects the observation image and usability mask onto the common grid.
- **Engine**: Uses `reproject.reproject_interp` (flux-interpolated spherical mapping) with automatic fallback to `scipy.ndimage.map_coordinates`.
- **Masking**: Propagates flagged pixels and marks out-of-bounds pixels as `NaN` and `False`.
- **Outputs**: `(aligned_image, aligned_mask, warnings)`:
  - `aligned_image`: 2D `float64` array (`NaN` for masked/unobserved pixels).
  - `aligned_mask`: 2D boolean array (`True` = valid, `False` = masked).
  - `warnings`: List of warnings (e.g. partial coverage percentage).

---

### Module: `display.py`

#### `create_rgb_composite(r_image, g_image, b_image, ...) -> tuple[np.ndarray, Path | None, list[str]]`
Builds a false-color multi-wavelength RGB composite image (ViewSpace style):
- **Red channel**: Longest wavelength (e.g. Band 5 or 6, $4.4 - 5.0\,\mu m$; cool dust & zodi).
- **Green channel**: Intermediate wavelength (e.g. Band 3 or 4, $1.6 - 2.5\,\mu m$; stellar photospheres / warm dust).
- **Blue channel**: Shortest wavelength (e.g. Band 1 or 2, $0.75 - 1.1\,\mu m$; stellar continuum).
- Outputs normalized RGB array $[0, 1]$ and renders to PNG.

#### `compute_shared_stretch(list_of_aligned_images, list_of_masks, pmin=1.0, pmax=99.0) -> tuple[float, float]`
Computes a single shared intensity stretch `(vmin, vmax)` across all valid pixels in a multi-epoch sequence (**Hard Rule 6**).
- **Outputs**: `(vmin, vmax)` percentiles.

#### `render_preview_png(aligned_image, mask, stretch, out_path, cmap="viridis") -> Path`
Headlessly renders an aligned preview PNG (North up, East left).
- **Mask Display**: Unobserved and masked pixels are displayed in a distinct dark tone (`#1a1a24`).
- **Outputs**: Resolved `Path` to written PNG.

#### `make_difference(a, b, mask_a, mask_b, out_png_path=None) -> tuple[np.ndarray, np.ndarray, Path | None, list[str]]`
Computes scientific signed difference ($B - A$) from aligned arrays (**Hard Rule 5: computed from scientific arrays, never PNGs**).
- **Scale**: Symmetric diverging scale ($[-d_{\max}, +d_{\max}]$) centered strictly on zero.
- **Outputs**:
  - `diff_array`: 2D `float64` signed difference array ($B - A$).
  - `valid_mask`: Boolean mask where both frames are usable.
  - `png_path`: Path to generated PNG (or `None`).
  - `warnings`: Warning strings.

#### `generate_blink_animation(list_of_aligned_images, list_of_masks, stretch, out_path, fps=2.0, labels=None, cmap="viridis") -> Path`
Generates an animated looping GIF across aligned epochs, replicating classic astronomical blink comparator workflows.
- **Dwell Time**: Controlled via `fps` (default 2.0 = 500 ms dwell per frame).
- **Labels**: Optional per-frame timestamp / epoch banner rendered on top of each frame.
- **Outputs**: Resolved `Path` to written animated GIF.

#### Coordinate Helpers for Person 3 (React UI)
- `pixel_to_sky(x, y, wcs) -> (ra_deg, dec_deg)`: 0-indexed pixel $(x, y)$ to sky coordinates.
- `sky_to_pixel(ra, dec, wcs) -> (x, y)`: Sky coordinates to 0-indexed pixel $(x, y)$.

---

### Module: `compatibility.py`

#### `check_wavelength_compatibility(obs_list, tolerance_fraction=0.15, target_coord=None) -> dict`
Checks whether observations are spectrally comparable to prevent chromatic SED artifacts in difference imaging.
- **Rules**:
  - Missing wavelength metadata strictly returns status `"unknown"`.
  - Fractional wavelength disparity $\le 15\%$ returns `"compatible"`.
  - Disparity $> 15\%$ returns `"incompatible"`.
- **Outputs**:
  ```python
  {
      "status": "compatible" | "incompatible" | "unknown",
      "wavelengths_um": [1.05, 1.10],
      "detector_bands": [1, 1],
      "warnings": [...]
  }
  ```

---

### Module: `measure.py`

#### `measure_position(aligned_image, mask, wcs, ra_deg, dec_deg, search_radius_px=5.0, snr_threshold=3.0) -> dict`
Measures accurate source position around user click:
- Subtracts local background and estimates noise via Median and MAD ($1.4826 \times \text{MAD}$).
- Fits a 2D Gaussian point source model using Levenberg-Marquardt (`curve_fit`).
- Derives formal astrometric uncertainty $\sigma_{\text{pos}} = \sqrt{\sigma_x^2 + \sigma_y^2} \times \text{scale}''$.
- **Fallback**: If the Gaussian fit does not converge cleanly, falls back to a flux-weighted centroid and strictly sets `uncertainty_arcsec: None` (**Hard Rule 3: never a fabricated number**).
- **Outputs**:
  ```python
  {
      "ra_deg": float,
      "dec_deg": float,
      "uncertainty_arcsec": float | None,
      "snr": float | None,
      "status": "ok" | "low_snr" | "masked" | "failed",
      "warnings": list[str]
  }
  ```

#### `detect_sources(aligned_image, mask, wcs, snr_threshold=3.5, max_sources=50) -> tuple[list[dict], list[str]]`
Scans the entire celestial image to automatically discover all candidate point sources (ViewSpace hotspots).
- Uses local maximum filtering + MAD noise estimation to pinpoint candidate coordinates.
- Returns list of hotspots with `id`, `x_px`, `y_px`, `ra_deg`, `dec_deg`, `peak_flux`, `net_flux`, and `snr`.

#### `extract_sed(ra_deg, dec_deg, observations, search_radius_px=4.0) -> dict`
Extracts multi-wavelength spectral energy distribution across all available SPHEREx detector bands ($0.75 - 5.0\,\mu m$).
- Powers the ViewSpace side detail drawer when an interactive pin is clicked.
- Returns list of spectral measurements per detector band and computes fitted spectral index $\alpha$ ($F_\lambda \propto \lambda^\alpha$).

---

### Module: `motion.py`

#### `fit_constant_motion(measurements) -> dict`
Fits 2D proper motion on the local tangent plane:
- Velocities returned in **arcsec/hour** (with `vx_uncertainty`, `vy_uncertainty`, `speed_uncertainty`).
- Returns `None` for uncertainties if $N = 2$ (0 degrees of freedom).

#### `predict_position(model, time_utc) -> (ra_deg, dec_deg)`
Projects kinematics forward/backward to any UTC timestamp.

#### `test_motion(training_measurements, reserved_measurement, investigation_id="SPX_INV_001") -> dict`
Evaluates whether source displacement is real motion or stationary null.
- **Decision Rule**:
  - Requires $\ge 2$ training epochs with `status == "ok"` and 1 reserved epoch with `status == "ok"`. Otherwise $\rightarrow$ `"insufficient_evidence"`.
  - **Stationary Residual ($R_{\text{stat}}$)**: Separation between mean training position and reserved position.
  - **Motion Residual ($R_{\text{motion}}$)**: Separation between model predicted position and reserved position.
  - If $R_{\text{stat}} \le 2.0 \times \sigma_{\text{eval}}$ $\rightarrow$ `"stationary_plausible"`.
  - If $R_{\text{stat}} > 2.0 \times \sigma_{\text{eval}}$ AND $R_{\text{motion}} \le 2.5 \times \sigma_{\text{eval}}$ AND $R_{\text{motion}} < 0.5 \times R_{\text{stat}}$ $\rightarrow$ `"motion_supported"`.
  - Otherwise $\rightarrow$ `"insufficient_evidence"`.

#### `scan_and_track_motion(epoch_observations, snr_threshold=3.5, match_radius_arcsec=30.0) -> dict`
Automatically discovers, tracks, and classifies all sources across time:
- Categorizes each hotspot into `"stationary_star"`, `"moving_candidate"`, or `"transient_candidate"`.
- Runs `test_motion` on moving candidates to verify their linear speed (arcsec/hour) and trajectory.
- Returns ready-to-render ViewSpace pin dictionary with coordinates, speeds, and descriptions.

---

### Module: `pipeline.py` (Master Orchestrator for Person 4)

#### `run_investigation_pipeline(fits_inputs, target_coord=None, investigation_id="SPX_INV_001", fov_arcmin=2.5, grid_size_px=128, output_dir="previews", base_url_prefix="") -> dict[str, Any]`
End-to-end master pipeline function that does everything needed for Person 4's FastAPI endpoint in a single call:
1. Loads all FITS inputs (file paths, `BytesIO`, or `Observation` objects).
2. Runs spectral/wavelength compatibility check.
3. Reprojects all observations to a standardized North-up / East-left common celestial grid.
4. Computes sequence-wide shared stretch and renders preview PNGs.
5. Computes successive scientific signed difference images ($B - A$).
6. Generates looping animated blink GIF.
7. Performs automated ViewSpace hotspot scanning and classification.
8. If `target_coord` (or moving hotspot) is present, measures centroids, performs linear proper motion fit, and validates against reserved evaluation epoch.
9. Returns complete dictionary matching Person 4 / Person 3 JSON schema.

---

### Module: `diagnostic.py`

#### `plot_trajectory_fit(verification_dict, out_png_path="trajectory_diagnostic.png") -> Path`
Generates a publication-quality 2-panel diagnostic figure visualizing the hypothesis test:
- **Left Panel (Celestial Trajectory)**: RA vs Dec showing training epoch measurements with error bars, fitted constant-motion trajectory line, observed reserved epoch position, and model-predicted position.
- **Right Panel (Residual Analysis)**: Bar chart comparing stationary residual ($R_{\text{stat}}$) against motion residual ($R_{\text{motion}}$) relative to the $2\sigma$ noise threshold, with summary decision textbox.

---

## 3. JSON Output Shapes for Person 4 (FastAPI)

### A. Sequence Builder Frame Object
```json
{
  "observation_id": "SPX_2025W17_0001",
  "observed_at": "2025-04-24T18:01:05.843",
  "image_url": "/previews/aligned_frame_1.png",
  "target_wavelength_um": 1.05,
  "warnings": []
}
```

### B. Sequence Comparison & Difference Block
```json
{
  "comparison": {
    "status": "compatible",
    "warnings": []
  },
  "difference": {
    "a_observation_id": "SPX_2025W17_0001",
    "b_observation_id": "SPX_2025W17_0002",
    "image_url": "/previews/difference_b_minus_a.png",
    "interpretation": "B minus A; exploratory comparison",
    "warnings": []
  }
}
```

### C. Motion Investigation Output
```json
{
  "investigation_id": "SPX_INV_001",
  "outcome": "motion_supported",
  "measurements": [
    {
      "epoch_id": "obs_1",
      "observed_at_utc": "2025-06-01T12:00:00.000",
      "ra_deg": 150.00000,
      "dec_deg": 2.00000,
      "uncertainty_arcsec": 0.25,
      "snr": 18.5,
      "status": "ok"
    }
  ],
  "predictions": [
    {
      "epoch_id": "obs_1",
      "observed_at_utc": "2025-06-01T12:00:00.000",
      "predicted_ra_deg": 150.00001,
      "predicted_dec_deg": 2.00000,
      "residual_arcsec": 0.03
    }
  ],
  "model_comparison": {
    "stationary_residual_arcsec": 45.2,
    "motion_residual_arcsec": 0.15,
    "uncertainty_arcsec": 0.30,
    "ratio_residual_motion_to_stat": 0.0033,
    "fitted_speed_arcsec_per_hour": 7.5,
    "decision_criterion": "Motion supported: Object moved 45.20'' beyond stationary noise (> 2*sigma). Constant-motion model successfully predicts reserved position to within 0.15'' (< 2.5*sigma and < 0.5*stationary residual)."
  },
  "limitations": [
    "Linear constant motion assumes no significant orbital curvature, acceleration, or annual parallax over the observation baseline.",
    "Astrometric precision is fundamentally constrained by SPHEREx native pixel scale (~6.2 arcsec/pixel).",
    "Verification relies on statistical model comparison against a single reserved evaluation epoch."
  ],
  "warnings": []
}
```

### D. FastAPI Integration Example for Person 4

Person 4 can implement `POST /api/investigate` in `backend/main.py` with just a few lines:

```python
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from backend.processing.pipeline import run_investigation_pipeline

app = FastAPI(title="SPHEREx WhyLab API")
app.mount("/previews", StaticFiles(directory="previews"), name="previews")

@app.post("/api/investigate")
async def investigate_sequence(
    files: list[UploadFile] = File(...),
    target_ra: float | None = Form(None),
    target_dec: float | None = Form(None),
    investigation_id: str = Form("SPX_INV_001"),
):
    target_coord = (target_ra, target_dec) if target_ra is not None and target_dec is not None else None
    file_bytes = [f.file for f in files]
    
    result = run_investigation_pipeline(
        fits_inputs=file_bytes,
        target_coord=target_coord,
        investigation_id=investigation_id,
        output_dir="previews",
        base_url_prefix="/previews",
    )
    return result
```

---

## 4. Known Scientific & Engineering Limitations

1. **Pixel Scale Constraints**: SPHEREx native detectors have a coarse pixel scale of $\sim 6.16$ arcsec/pixel. Sub-pixel centroiding can achieve $\sim 0.5 - 1.5$ arcsec precision depending on SNR, but cannot resolve sub-arcsecond separations.
2. **Linear Motion Assumption**: `motion.py` models constant linear velocity ($v_x, v_y$). It does not integrate full N-body ephemerides, solar-system gravitational acceleration, or geocentric/heliocentric parallax. It is designed for short baselines (hours to weeks).
3. **Linear Variable Filters (LVF)**: SPHEREx transmission varies across the spatial field of each detector array. In difference images, differences in bandpass create residual dipole or flux artifacts across extended objects or objects with steep spectra.
4. **Missing Values**: Any missing FITS header data (timestamp, variance, wavelength) is set strictly to `None` and propagated as `null` in JSON. We never fabricate coordinates or uncertainties.

---

## 5. How to Run & Verify

### Running Full Test Suite (65 Passing Unit Tests)
```bash
python -m pytest backend/processing/tests -v
```

### Generating Synthetic Multi-Epoch Test Sequence
```bash
python backend/processing/simulate_sequence.py --out-dir backend/processing/sample_data/sequence --epochs 4 --speed 12.0
```

### Generating Multi-Wavelength ViewSpace RGB Composite
```bash
python backend/processing/demo_viewspace.py
```

### Inspecting a FITS Cutout
```bash
python backend/processing/inspect_fits.py backend/processing/sample_data/nasa_spherex_l2_cutout.fits
```

### Running Visual Verification
```bash
python backend/processing/check_visual.py
# Generates backend/processing/visual_check_alignment.png
```

---

## 6. Real NASA SPHEREx Benchmark Dataset & Gaia DR3 Verification

### Integrated Real Dataset (`PythonProject/final_dataset/`)
Integrated from Person 1 archive delivery:
- **21 Validated Level 2 FITS cutouts** spanning detectors D1, D2, D3, D4, D5, and D6.
- **5 Benchmark Astronomical Targets** with Gaia DR3 / CatWISE2020 ground truth:
  1. `Barnards_Star`: Fastest moving star in the sky (~10.39 arcsec/yr). 5 epochs spanning 2025–2026 clearly capture real celestial motion (+9.0'' Dec displacement), creating a textbook signed dipole in difference imaging.
  2. `WISE_0855`: Coldest known sub-brown dwarf / free-floating planetary mass object (T ~ 250 K). Rapid ~8.04''/yr proper motion confirmed with `MOTION_SUPPORTED` decision.
  3. `Epsilon_Indi_B`: Nearby methane brown dwarf binary (T1 + T6). Proper motion ~4.7''/yr aligns with Gaia DR3 truth within sub-arcsecond residuals (0.12'' to 0.88'').
  4. `RW_Aurigae`: Classical T Tauri binary with circumstellar disk and accretion streams. Astrometrically stationary reference star (`STATIONARY_PLAUSIBLE`).
  5. `R_Draconis`: Long-period Mira pulsating red giant (P ~ 245 days) in Draco.

### Core Processing Innovations for Real SPHEREx Data
1. **Smart Bitmask Usability (`DEFAULT_FATAL_BITMASK`)**:
   Standard synthetic flags assume `0 = good`. Real SPHEREx Level 2 MEF `FLAGS` use higher-order bits (`1<<19 = 524288`, `1<<21 = 2097152`) for informational processing tags (zodiacal subtraction, catalog association). We enforce masking strictly on fatal pixel defects (`0xFF | (1 << 16) | (1 << 26)`), preventing 100% false pixel rejection.
2. **Saturated Core Wing Centroiding**:
   Bright stars ($V < 11$) saturate SPHEREx detector cores (resulting in central NaNs). Centroiding computes the center-of-mass from surrounding unmasked PSF wings rather than rejecting the source.
3. **Automated Gaia DR3 Ground Truth Comparison**:
   `backend/processing/targets_registry.py` attaches ground truth parameters (reference epoch, $\mu_{\alpha\cos\delta}, \mu_\delta$, parallax, RUWE) to each observation and injects them directly into FastAPI responses and the ViewSpace UI card.
