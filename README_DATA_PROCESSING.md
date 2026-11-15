# SPHEREx WhyLab: Scientific Data Processing & Verification Module

**Role:** Person 2 (Senior Scientific Python Engineer)  
**Branch:** `feature/data-processing`  
**Target:** Ready for immediate integration by Person 4 (Backend) and Person 3 (Frontend)  
**Status:** **65 / 65 Passing Unit Tests (100% Pass Rate)**  

---

## 1. Summary of Deliverables

1. **Pure Scientific Image Processing Engine (`backend/processing/`)**:
   - `alignment.py`: WCS tangent celestial grid construction (`North-up`, `East-left`) and spherical flux-conserving reprojection (`reproject_interp` / `scipy.ndimage.map_coordinates`).
   - `display.py`: Shared multi-epoch percentile dynamic range stretching (Hard Rule 6), digital image differencing ($B - A$), animated blink GIF synthesis, and 3-channel false-color RGB synthesis (ViewSpace style).
   - `measure.py`: Local background noise estimation via Median Absolute Deviation (MAD), 2D Gaussian PSF fitting via Levenberg-Marquardt (`scipy.optimize.curve_fit`), saturated core wing centroiding, and 6-band photometric SED extraction.
   - `motion.py`: Tangent celestial kinematics fitting, position prediction at arbitrary UTC timestamps, reserved-epoch hypothesis verification (Hard Rule 9: no full orbital mechanics; Hard Rule 8: `insufficient_evidence` when ambiguous), and automated multi-epoch hotspot tracking.
   - `pipeline.py`: Master orchestrator for end-to-end multi-wavelength ingestion, differencing, blinking, and hypothesis testing.
   - `diagnostic.py`: Publication-grade 2-panel diagnostic astrometric diagrams (celestial track + residual comparison against $2\sigma$ threshold).

2. **Real NASA SPHEREx Level 2 Benchmark Dataset (`PythonProject/final_dataset/`)**:
   - **21 Validated MEF FITS Cutouts** spanning all 6 SPHEREx detector arrays (D1 to D6).
   - **5 Benchmark Astronomical Targets** with Gaia DR3 and CatWISE2020 ground truth:
     - `Barnards_Star`: Fastest stellar motion (~10.39''/yr); textbook signed dipole in difference imaging.
     - `WISE_0855`: Coldest known sub-brown dwarf (T ~ 250 K); verified with `MOTION_SUPPORTED`.
     - `Epsilon_Indi_B`: Nearby methane brown dwarf binary (T1 + T6); sub-arcsecond Gaia DR3 alignment (0.12'' to 0.88'').
     - `RW_Aurigae`: Classical T Tauri binary with circumstellar disk (`STATIONARY_PLAUSIBLE`).
     - `R_Draconis`: Long-period Mira pulsating red giant in Draco.

3. **Backend Integration (`teammate_integration.py` & `backend/main.py`)**:
   - `teammate_integration.py`: Official adapter implementing `build_adapters(settings, trusted_retriever)` conforming to Person 4's `docs/integration-contract.md` (`SequenceAdapter` and `MotionAdapter`).
   - `backend/main.py`: Fully operational FastAPI server exposing `/api/presets`, `/api/investigate`, `/api/hotspots`, `/api/sed`, and `/api/composite`.

4. **ViewSpace Interactive Astronomy UI (`frontend_viewspace/`)**:
   - Replica of ViewSpace UI: Top tour stops dropdown, `< 1 / 6 >` pagination, ViewSpace metadata card (Location, Distance, Image Size, Observatories), Gaia DR3 ground truth verification card, difference dipole tab, SED tab, and UniverseFinder 3D WebGL starfield engine.

5. **Exhaustive Unit Test Suite (`backend/processing/tests/`)**:
   - **65 unit tests** verifying every component, all passing in ~4 seconds.

---

## 2. How to Run the Tests

```powershell
python -m pytest backend/processing/tests -v
```

---

## 3. How Person 4 Wires This Into `whylab`

In `whylab/config.py` or `.env`:
```env
WHYLAB_ADAPTER_FACTORY=teammate_integration:build_adapters
```
No changes to backend API handlers are needed. `SPHERExSequenceAdapter` and `SPHERExMotionAdapter` execute synchronously inside the backend bounded worker pool.

---

## 4. Benchmark Ground Truth Report
See [REAL_DATASET_ANALYSIS.md](REAL_DATASET_ANALYSIS.md) for full astrometric residuals, figures, and Gaia DR3 comparison tables.
