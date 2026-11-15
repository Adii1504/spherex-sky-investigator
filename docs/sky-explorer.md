# Interactive sky explorer

The existing React/Aladin Lite explorer is retained, including its mounted map,
name/alias search, hover descriptions, selected-marker highlight, keyboard-focusable
target buttons, Centre action, `?target=<stable-id>` navigation and mobile bottom sheet.
Aladin remains pinned to 3.8.2. Its WebGL2 renderer needs a compatible browser and
network access for DSS2 HiPS tiles. Await `A.init` before constructing the view;
retain the Aladin logo/link. The official integration/API documentation was checked:
https://cds-astro.github.io/aladin-lite/ and https://cds-astro.github.io/aladin-lite/Aladin.html.
No catalogue stars are inferred from background imagery. DSS2 is labelled separately
from the FITS-derived SPHEREx product previews.

## API and metadata handoff

- `GET /api/targets`: five supplied catalogue entries.
- `GET /api/targets/{target_id}`: supplied details; unknown IDs return structured 404.
- `GET /api/targets/{target_id}/observations`: only explicit associations from the
  existing approved local FITS registry. No name/coordinate matching is performed.
- The existing `/api/observations/{product_id}/preview` and `/quality` endpoints
  remain responsible for FITS output and use their stored per-product predictions.

`whylab/data/targets.json` is the exact supplied frontend catalogue snapshot (from
`frontend/src/data/targetCatalogue.js`); it is packaged with the Python application.
The frontend loads the target API, with a labelled supplied-catalogue fallback if
unavailable. Stable IDs and provisional labels are unchanged. Catalogue positions
are ICRS/J2000 reference positions, never propagated by this feature.

Extend `.data/fits_manifest.json` entries (see `fits-preview.md`) with:

```json
{
  "approved-product-id": {
    "path": "raw/approved-product.fits",
    "target_id": "barnards-star",
    "provisional": true,
    "provenance_status": "provisional teammate association",
    "observation": {
      "observed_at": null,
      "detector": null,
      "file_wavelength_um": null,
      "position_wavelength_um": null
    }
  }
}
```

Supply actual metadata rather than replacing nulls with estimates. Optional
`predicted_position` contains **that observation's supplied propagated coordinates**
and `astrometry_status`, using the existing FITS manifest format. It is never filled
from the catalogue position. The returned preview therefore uses the exact same
stored prediction as its quality report. Missing predictions remain unavailable.
Optional `references`, `evidence`, and `spectra` arrays contain `{label,url}` links to
public HTTPS resources without credentials or signed query strings. Spectra controls
only appear when links are supplied; no spectra are generated. Unknown manifest
target IDs are not exposed as extra catalogue targets. Local paths are not returned.

The detail pane lists dates, detector, file and position wavelengths independently.
Select an observation to fetch PNG bytes and raw quality JSON through the shared API
client. Raw JSON preserves large integer FLAGS values in the display. Requests are
aborted and late responses ignored on target/product changes; object URLs are revoked.
Loading, missing files, empty associations and API/image errors are explicit, with retry.
Manifest changes require restarting the backend.

## Run and check

From the repository root:

```powershell
.\.venv\Scripts\python -m whylab
```

For frontend development, in another terminal:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Open Vite's local URL, or build with `npm.cmd run build` and open the backend at
http://127.0.0.1:8000/. API reference is http://127.0.0.1:8000/docs.

Tests: `python -m pytest -q` and `npm.cmd test` in `frontend`. Synthetic fixtures
exercise all five target associations, matching PNG/quality routes, missing products,
selection races, raw flags, labels, list/marker equivalence and map-instance retention.
Existing tests cover name search, URL state, mobile stylesheet rules and navigation.
Real target-specific FITS associations/predictions, evidence and spectra remain pending
the teammate's manifest; no real Barnard's Star association is asserted.
