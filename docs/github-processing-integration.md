# GitHub processing integration

Integrated source: [commit 9c2e3bb8a3c71ed0d67bf97e3d5a35c7d133b116](https://github.com/Adii1504/spherex-sky-investigator/commit/9c2e3bb8a3c71ed0d67bf97e3d5a35c7d133b116)
from `Adii1504/spherex-sky-investigator`.

## Run in Git Bash

From the Spacex project root, with the virtual environment activated:

```bash
python -m pip install -c constraints.txt -e '.[test]'
npm.cmd run build --prefix frontend
python -m whylab --port 8010
```

Open <http://127.0.0.1:8010/processing/> for the imported processing viewer.
The original sky explorer is at <http://127.0.0.1:8010/> and links to
**Processing viewer**. The same server serves both applications.
`python -m whylab` still uses port 8000 by default. Keep the server running;
Ctrl+C stops it. The launcher loads `.env` or `.env.example` literally.

The processing viewer is plain HTML/CSS/JavaScript and needs no separate build.
Its seven presets include all five real target datasets, a clearly labelled
four-epoch synthetic demonstration, and the supplied six-band field. It
supports aligned images, blinking with speed/step controls, signed differences,
trajectory plots, exploratory spectral samples, candidate pins, JSON export,
and FITS upload. The decorative 3D starfield is a separate page.

For standalone compatibility, `python -m uvicorn backend.main:app --host
127.0.0.1 --port 8002` serves the processing API/viewer without the sky explorer.

## Imported files and local adaptations

- `backend/processing/`: supplied scientific pipeline, CLI utilities, tests,
  sample FITS files, and diagnostic figures.
- `backend/main.py`: processing API mounted at `/processing` in WhyLab.
- `frontend_viewspace/`: supplied viewer layout with live API integration.
- `PythonProject/final_dataset/`: all 21 FITS observations and checksummed
  metadata; package checksums were verified after copying.
- `previews/`, `README_DATA_PROCESSING.md`, `REAL_DATASET_ANALYSIS.md`: supplied
  historical figures and upstream reports. These are reference artifacts; the
  viewer computes its displayed results from the API.
- `teammate_integration.py`: corrected worker adapters. Sequence outputs are
  read from their actual temporary directory; chronological IDs stay paired
  with their cutouts. Motion evaluation uses only training observations for
  fitting and evaluates every reserved observation separately. IRSA archive
  access remains connected to the existing trusted retriever.

Existing WhyLab code and the earlier dataspace integration were preserved.
The pre-integration local source is backed up in ignored
`.data/before-9c2e3bb.zip`; an isolated checkout of the exact commit and a source
inventory are retained under `.data/` for comparison. Existing Git history was
not replaced, and nothing was pushed to GitHub.

The integration fixes the upstream `frontend`/`frontend_viewspace` folder
mismatch, serves CSS/JS alongside the root page, and generates absolute asset
URLs that also work under `/processing`. Heavy processing runs in FastAPI's
thread pool; a shared lock protects Matplotlib rendering. Outputs use unique
directories under `.data/processing/previews/`, with a 100 MB admission budget.
The API bounds grid sizes, coordinates, upload counts and bytes, validates
paired coordinates, and prevents investigation IDs from becoming paths.
RGB channels are reprojected onto the same celestial grid before composition.

FITS flags retain their full integer width. FITS failures do not turn raster
images into invented celestial observations. Declared time scales are converted
to UTC; missing `TIMESYS` is explicitly recorded as an assumption.

## Interpretation

The UI shows actual returned values, missing-value states, and request errors.
It does not substitute preset SNR, speed, residuals, pins, or successful outcomes
when processing fails or evidence is insufficient. Stale investigation and SED
responses cannot overwrite a newer selection. SED requests use the selected
dataset instead of silently measuring the unrelated six-band sample field.

Unknown or incompatible wavelengths produce `insufficient_evidence` for motion
interpretation. The supplied fatal-flag bitmask and uncertainty floors remain
adopted processing assumptions requiring scientific review. Interpolation is
surface-brightness interpolation, not a claim of flux conservation. Spectral
samples are peak-pixel estimates, not calibrated integrated source photometry.
Gaia/CatWISE values are adopted catalogue astrometry, not independent proof of
source identification. Original upstream reports retain their original claims;
they are not a validation report for this integration.

## Verification

```bash
python -m pytest -q
npm.cmd test --prefix frontend
npm.cmd run build --prefix frontend
```

Verified 133 Python tests (including the supplied 65), 114 frontend tests, and
the production build. Added actual HTTP tests for every preset and its generated
assets, mounted viewer files, SED dataset selection, composite rendering, invalid
uploads and input bounds, worker preview bytes and IDs, and every held-out epoch.
Viewer tests cover insufficient evidence, zero-valued measurements, missing
residuals, API failure cleanup, and stale preset responses. These checks prove
software behavior; they do not establish astronomical discovery or calibrated
astrometric accuracy.
