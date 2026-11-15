# Supplied dataspace integration

The 26 supplied Python scripts are preserved under `tools/dataspace/` with
checksums. The companion `final_dataset` contains 21 FITS cutouts for five
targets: Barnard's Star (5), Epsilon Indi B (3), WISE 0855 (5), RW Aurigae (4),
and R Draconis (4).

## Import and view (Git Bash)

From the Spacex project root, with the existing virtual environment active:

```bash
python -m whylab.dataset "C:/Users/Aditya Sonavane/OneDrive/Desktop/dataspace"
npm.cmd run build --prefix frontend
python -m whylab
```

Open <http://127.0.0.1:8000>, select one of the five targets, then choose an
observation under **Available observations**. The viewer shows its FITS preview,
predicted marker, raw quality flags, supplied astrometry, coverage, and coarse
detection screen. **Download original FITS** returns the registered file.
Local previews and metadata work without live archive services; the reference
survey and catalogue searches still need network access.

Stop an older server with Ctrl+C before restarting. If port 8000 is occupied:

```bash
python -m uvicorn whylab.app:app --host 127.0.0.1 --port 8001
```

Open <http://127.0.0.1:8001>. No `.env` file is needed for local imported products.
For a different registry root, supply `--root` to the importer and set
`WHYLAB_OUTPUT_DIR` to that root's `previews` directory before starting the server.

## Import guarantees

The importer reads the source directory without modifying it. It verifies every
entry in `SHA256SUMS.txt`, checks unique manifest/table keys and target mappings,
matches manifest hashes and observation dates, and recomputes each supplied
position's WCS pixel coordinates against the real image. Missing, changed,
outside-image, or inconsistent products abort before registry publication.
Only final manifest rows are imported; excluded/historical products are omitted.

Verified package files are copied under ignored `.data/datasets/dataspace-<hash>`.
The existing `.data/fits_manifest.json` is merged atomically, retaining earlier
unassociated samples. Reimporting the same package is idempotent; conflicting
metadata for an existing product ID is rejected. Restart the backend after
importing because the registry is loaded at startup. Source files and the
existing static J2000 catalogue are retained; observation predictions have their
own catalogue, epoch, assumptions, and quality status.

## Run the supplied scripts

Prepare a separate working copy so script outputs do not modify the source
folder, imported package, or registered data:

```bash
python scripts/prepare_dataspace_workspace.py
cd .data/dataspace_work
../../.venv/Scripts/python.exe build_coverage_outputs.py
../../.venv/Scripts/python.exe detection_check.py
../../.venv/Scripts/python.exe finalize_dataset.py --no-package
```

The helper verifies the preserved script inventory and imported package, copies
the scripts with their original sibling imports, supplies the historical tables,
then overlays the final tables and the 21 approved observations. It refuses to
overwrite an existing workspace. Choose `--workspace .data/dataspace_work_2` for
a fresh run. Generated results are isolated; import a newly finalized package
explicitly if you want to use new outputs in the app.

The three offline commands above use the existing astronomy dependencies.
Additional scripts for pandas reports and online Gaia/SIMBAD/IRSA queries need
the optional dependencies:

```bash
python -m pip install -e '.[dataspace]'
```

Online scripts may download files or supersede working observations. Historical
scripts such as `validate_target.py`, `inspect_downloaded_fits.py`, and
`prepare_astrometry_review.py` contain older static/provisional coordinates.
Use `target_astrometry_master.csv` and `build_coverage_outputs.py` for the final
adopted per-observation propagation. Do not import scripts merely to inspect them:
some run their workflow immediately.

## Scientific interpretation

- The adopted Gaia/CatWISE identifiers are preserved as strings without integer
  rounding. Epsilon Indi B has high RUWE; WISE 0855 has provisional CatWISE motion
  and about 2 arcsec stated uncertainty by 2026; RW Aur components are unresolved
  and the supplied source IDs still carry an archive-confirmation caveat.
- The supplied `apply_space_motion` calculation propagates a reference position
  using proper motion, distance (where available), and radial velocity. It does
  not compute observer-dependent annual parallax. Missing radial velocities are
  set to zero where documented. UTC is the supplied scripts' time assumption;
  missing FITS `TIMESYS` remains missing in the API.
- Coverage is not detection. The supplied screen uses a brightest-pixel SNR and
  300 random controls, without FLAGS masking. `DETECTED_CANDIDATE` remains a
  candidate, `ABOVE_THRESHOLD_NOT_UNUSUAL` is not detection evidence, and
  `NOT_DETECTED` reflects this screen's threshold. No photometry or independent
  scientific verification is claimed.
- The final manifest's WCS-WAVE extrema have no wavelength unit in this package.
  Raw values are shown with that limitation; `file_wavelength_um` and the
  position-specific wavelength remain unavailable. Detector-derived band names
  are not converted to wavelengths.

## API

`GET /api/targets/{target_id}/observations` returns the observation's checksum,
footprint, prediction, and `dataset` evidence. `dataset` contains the supplied
adopted astrometry, propagation assumptions, recomputed coverage, detection
screen, pipeline version, and source filename. No raw server filesystem path is
returned. `GET /api/observations/{product_id}/fits` downloads only a product
resolved through the existing local registry; preview and quality URLs are
unchanged. Observations are ordered chronologically.
