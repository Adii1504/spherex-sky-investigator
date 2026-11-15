# FITS preview and quality checks

This module visualizes supplied predictions. It performs no source identification,
epoch propagation, detection, or astrometric verification. Provisional status text
is retained in the PNG footer and JSON. Coordinates are supplied ICRS RA/Dec degrees;
Astropy transforms them into the science extension's celestial frame. Pixel coordinates
are zero based. Native orientation is preserved (x right, y up), with FITS row zero
at the bottom of the PNG image panel. The image is not reprojected north-up.

## Local product handoff

The existing search registry stores remote provenance URLs, not approved local paths
or predictions. No local manifest was present. `ProductRegistry` is the narrow adapter
for that missing handoff; it does not modify archive or sequence processing. A trusted
teammate can supply it via `create_app(fits_registry=...)`, or place `fits_manifest.json`
beside the configured output directory (`.data/fits_manifest.json` by default):

```json
{
  "teammate-product-id": {
    "path": "raw/approved-product.fits",
    "label": "Barnard's Star — provisional teammate association",
    "provenance_status": "provisional",
    "predicted_position": {
      "ra_deg": 120.0,
      "dec_deg": 20.0,
      "astrometry_status": "provisional"
    }
  }
}
```

These are illustrative coordinates, not Barnard's Star coordinates. Replace all entry
values with the teammate's supplied values. Paths must resolve within the manifest's
directory, including symlinks; no HTTP parameter can register a product or supply a path.
Omit `predicted_position` when unavailable: image rendering still works but geometry and
aperture reports explicitly remain unavailable. Restart after editing the manifest.

## Run

```powershell
.\.venv\Scripts\python -m uvicorn whylab.app:app --host 127.0.0.1 --port 8000 --workers 1
```

- `GET /api/observations/{product_id}/preview` returns `image/png`.
- `GET /api/observations/{product_id}/quality` returns strict JSON.
- Optional overrides for **either** endpoint must supply all three query parameters:
  `ra_deg`, `dec_deg`, `astrometry_status`. Values must be finite, RA in [0,360),
  Dec in [-90,90], status 1–120 printable ASCII characters (preserved verbatim).
- Both accept `aperture_radius` in pixels (default 3, range >0 through 512) and
  `render_size` (default 512, range 32–1024).
- Unknown IDs return 404 `product_not_found`; invalid inputs return structured 422;
  missing approved files/cache exhaustion return structured 503. No local paths leak
  through these errors. Sync FastAPI handlers perform FITS work in the thread pool.

For example: `http://127.0.0.1:8000/api/observations/teammate-product-id/quality?ra_deg=120&dec_deg=20&astrometry_status=provisional`.

## Artifacts and semantics

Artifacts are stored under `WHYLAB_OUTPUT_DIR/fits/<cache-key>/`: `preview.png`,
`metadata.json`, `quality_report.json`. The key includes source identity (path,
device/inode, size, nanosecond modification/change times), product metadata, coordinates,
status, aperture radius, render size and rendering version/settings. Cache is bounded by
existing byte/count limits and returns 503 when full. Original files are read-only.
Identity is checked after processing. Products must be immutable during service use.
This local module serializes cache publication within the supported single API process.

Science is selected by extension name `IMAGE`, never HDU order or filename. Missing or
incompatible extensions produce warnings/unavailable statuses. Header values retain
their originating HDU/keyword/comment. `DATE-OBS`, `MJD-OBS`, `TIMESYS`, `BUNIT` and
`DETECTOR` are read from IMAGE then PRIMARY. Missing values are null; `DATE` is never
used as an observation time. Wavelength WCS descriptors and the presence of `WCS-WAVE`
are reported without inventing a wavelength at the selected position.

Geometry uses the closed pixel rectangle [-0.5,width-0.5] × [-0.5,height-0.5]. Distance
is the shortest Euclidean distance to its boundary; signed edge clearance is positive
inside and negative outside. Apertures include pixel **centers** within the requested
radius; truncation concerns the circular footprint crossing that rectangle. Empty
apertures have zero counts and null fractions. Valid-pixel fraction means finite science
samples only; it does not combine flags, variance, or source detection. Variance reports
finite positive values, invalid values, and zero count separately. FLAGS remain exact
integers (including uint64); nonzero masks are never classified as bad. JavaScript
consumers must use an integer-safe JSON parser for flag values above 2^53-1.

The display uses finite science pixels, 1st–99th percentiles and an asinh stretch.
Constant and all-invalid images produce labelled previews. An inside-image prediction
gets a red ring regardless of science-pixel validity; that ring implies geometric
coverage only. Unavailable or outside predictions get no marker.

## Validation and batch generation

```powershell
.\.venv\Scripts\python -m pytest tests/test_fits_preview.py -q
.\.venv\Scripts\python scripts/fits_preview.py --synthetic-demo
.\.venv\Scripts\python scripts/fits_preview.py --product-id teammate-product-id
# Omit --product-id to process every local manifest entry.
```

No supplied local manifest establishes a Barnard's Star association or predicted
coordinates. `.data/real-cutout.fits` exists, but must not be relabelled as Barnard's Star
without teammate provenance. Synthetic demo artifacts validate the workflow; real
Barnard's Star and remaining manifest-entry verification await the approved handoff.
The existing real cutout was also processed successfully with no supplied position
(explicit unavailable geometry); its SHA-256 was unchanged after artifact generation.
Validation: 39 backend tests passed, including eight focused FITS tests; generated
synthetic and existing-cutout PNGs were visually inspected. Compilation and whitespace
checks passed. The separate subprocess/Uvicorn smoke check timed out waiting for server
readiness in this environment (also outside the sandbox); standalone HTTP startup remains
unverified. FastAPI TestClient checks passed for both new endpoints and error cases.

Reference semantics: [Astropy FITS](https://docs.astropy.org/en/stable/io/fits/index.html)
and [celestial WCS API](https://docs.astropy.org/en/stable/wcs/wcsapi.html).
