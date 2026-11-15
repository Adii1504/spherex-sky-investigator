# Local astronomy explorer

Implemented in the existing React 19/Vite 6 + FastAPI project. Reuses the five
existing `/api/targets` records, `IRSAArchive` SIA2/IBE search/cutout adapter,
sequence workflow, ProductRegistry, and FITS PNG/quality components. No paid API,
model, account, cloud deployment, or new runtime dependency was added.

## Installation and run (PowerShell)

```powershell
Set-Location -LiteralPath 'C:\Users\Aditya Sonavane\OneDrive\Desktop\Spacex'
# First installation only, if .venv is missing:
py -3.13 -m venv .venv
.\.venv\Scripts\python -m pip install -c constraints.txt -e '.[test]'
npm.cmd ci --prefix frontend
npm.cmd run build --prefix frontend

# Real IRSA adapter; Python launcher also reads .env or .env.example literally.
$env:WHYLAB_ADAPTER_FACTORY='whylab.integration:build_adapters'
# The user-supplied sample is 60,157,440 bytes; the default preview limit is 70 MB.
$env:WHYLAB_MAX_CUTOUT_BYTES='70000000'
.\.venv\Scripts\python -m whylab
```

Open http://127.0.0.1:8000. This serves the frontend build and API together.
API documentation: http://127.0.0.1:8000/docs. This installation was checked with
Python 3.13.7, Node 22.19.0, npm 10.9.3 and the existing lockfile/environment.
Internet access is needed once to install dependencies; subsequent local/offline
demonstrations use those installed dependencies.

For development, run the backend as above and, in a second terminal:

```powershell
Set-Location -LiteralPath 'C:\Users\Aditya Sonavane\OneDrive\Desktop\Spacex\frontend'
npm.cmd run dev
```

Open the Vite URL (normally http://127.0.0.1:5173). Its existing `/api` proxy
targets port 8000. `npm.cmd run preview` does not proxy the API. Restart/reload
after changes to environment variables or a production build. One backend
worker is required by the existing in-memory job/registry workflow.

## Optional supplied FITS sample

Already imported locally during implementation; reproduce on a fresh checkout:

```powershell
.\.venv\Scripts\python scripts/register_local_fits.py 'C:\Users\Aditya Sonavane\Downloads\spherex_sample.fits'
```

Restart the backend after importing. The script copies once into the existing
`.data/raw` area and merges `.data/fits_manifest.json` without replacing existing
entries. The ID is `local-bb695ea06638d98c7c65`; SHA-256:
`bb695ea06638d98c7c65156905e2bb5c435c6addcb4b7e841e7adaad16b630e9`.
The original was read only. The file is not committed or downloaded on clicks.
An ICRS boundary is calculated from IMAGE WCS pixel corners, not an estimated
square. It is displayed as a separate footprint, without a source association or
predicted marker. Inspect it under **Local FITS evidence · unassociated**.
The IMAGE header supplies `2025-04-29T00:24:27.897`; the UI preserves that raw
time rather than inventing a time scale. Existing quality JSON contains the
originating header/time-scale information and exact FLAGS text.

## Configuration

No API keys, tokens or billing credentials are required. Existing `.env.example`
remains the complete backend configuration; the added/important settings are:

| Variable | Default / meaning |
| --- | --- |
| `WHYLAB_ADAPTER_FACTORY` | `whylab.integration:build_adapters` in the example; omit to keep existing unavailable adapters |
| `WHYLAB_SIMBAD_TAP_URL` | `https://simbad.cfa.harvard.edu/simbad/sim-tap/sync` |
| `WHYLAB_CATALOG_HOSTS` | Exact HTTPS allowlist: `simbad.cds.unistra.fr,simbad.cfa.harvard.edu` |
| `WHYLAB_IRSA_SIA_URL` | `https://irsa.ipac.caltech.edu/SIA` |
| `WHYLAB_TRUSTED_HOSTS` | Existing IRSA exact HTTPS host allowlist |
| `WHYLAB_ARCHIVE_COLLECTIONS` | Existing `spherex_dr1,spherex_qr3`; supported deep variants remain opt-in |
| `WHYLAB_MAX_CUTOUT_BYTES` | 70,000,000; supports the supplied 60 MB local sample |
| `WHYLAB_TIMEOUT_SECONDS` | Existing 60 s archive/worker deadline; SIMBAD capped at 12 s |
| `WHYLAB_CACHE_SIZE` | Existing 128 archive metadata/cutout/session capacity |
| `WHYLAB_CORS_ORIGINS` | Only needed for separate origins; Vite normally proxies |
| `VITE_API_BASE` | Existing empty default; frontend API origin override |
| `VITE_HIPS_URL` | `https://skies.esac.esa.int/DSSColor`, direct public survey mirror |

Provider URLs are operator configuration, never request parameters. Exact host
allowlists must be updated deliberately with a provider change. HTTPS validation,
certificate verification, redirect rejection and bounded bytes use the existing
TrustedRetriever. No browser request contains ADQL. SIMBAD receives server-built
templates, with escaped exact-name literals and validated numeric cone inputs.

## Workflow and contracts

- **Sky survey** retains Aladin pan/zoom/reset, source hover/selection and a direct
  DSS2 HiPS survey. Gold source markers and cyan observation boundaries have
  independent switches. Boundaries come from returned `s_region` or approved
  local IMAGE WCS; missing/unsupported geometry is omitted.
- Empty-sky clicks report ICRS coordinates without creating/selecting a record.
  Clicking a catalogue point uses its stable ID to open the details panel.
- **Search SIMBAD** debounces by 450 ms and aborts/discards obsolete responses.
  Exact names or a 0.1-degree cone around the last sky click/selected source use
  `GET /api/catalog/search?name=...` or `?ra=...&dec=...&radius=...`.
  Server cone radii are capped at 0.5 degrees and results at 50 rows.
- Existing `POST /api/v1/observations/search` searches SPHEREx field coverage.
  Its optional additive `observations[].footprint_stcs` preserves SIA `s_region`.
  **Search SPHEREx field**, select products, **Generate sequence**, then **Sky
  explorer** shows that field's observations/PNG metadata and footprints.
  The existing **Open observations / sequence** action preserves its in-memory
  source/search/observation selection and uses the original sequence viewer.
- Explicit local source associations still use `/api/targets/{id}/observations`.
  Their **Inspect observation** link keeps both `target` and `product` URL IDs,
  and wraps the existing ObservationProduct FITS preview/quality component.
  The inspection page checks that the requested product belongs to that target.
  `/api/local-products` exposes approved *unassociated* registry products without
  paths; it never assigns them to a catalogue source.
- Candidate notes are labelled **user annotations / unverified**, saved only in
  browser localStorage by source+product ID, and exportable as JSON with evidence
  references. They do not alter catalogue/science data or assert discovery.

## Coordinates, distances and graphics

RA/Dec are degrees, ICRS; reference epochs are displayed when supplied. Static
catalogue positions are not propagated to SPHEREx observation dates. The pure
conversion is `x=r cos(dec) cos(ra)`, `y=r cos(dec) sin(ra)`, `z=r sin(dec)`:
right handed, +X RA 0°, +Y RA 90°, +Z north. Astropy's Galactic Centre reference
direction and the equatorial/pole axes were used as independent checks.

**3D sources** lazy-loads Three.js/OrbitControls. Points share a BufferGeometry
and PointsMaterial, with one separate highlight. The default is a unit celestial
sphere: radius represents direction only. Spatial mode is linear in parsecs and
omits every source lacking an eligible `distance` object:

```json
{"value_pc": 5.0, "uncertainty_pc": 0.2, "trustworthy": true,
 "method": "published distance posterior", "provenance": "publication/reference"}
```

These numbers illustrate the schema, not an astronomical record. Eligibility
also requires a finite positive distance and relative uncertainty <=20%. This
is a conservative display policy, not a proof of scientific trustworthiness.
No brightness inference or parallax inversion is performed. All bundled entries
have unavailable distances, so spatial mode correctly starts disabled. The
camera fit/zoom changes framing only; relative physical distances are linear.
Selection is shared with the map and details; labels are limited to five.

Three geometry/materials, observers, event listeners, RAF and renderer resources
are disposed on unmount. `threeRenderer.js` handles an observed compatibility bug:
Aladin 3.8.2 assigns `window.self` to GUI objects, whereas Three captures `self`
for animation cleanup. Construction temporarily binds the actual Window and
restores the prior value; no third-party library code is changed. Aladin itself
has no supported public destroy API in 3.8.2; its existing wrapper clears its
callbacks/overlays/owned DOM and retains a single instance during normal use.

Without WebGL, the source list/details, offline SVG atlas, notes, and FITS PNG/
quality workflow remain usable. Failed lazy imports have a local error boundary.

## Data, cache and notices

The existing five-source SIMBAD/CDS snapshot retains its recorded retrieval/check
date **2026-11-14** and per-source bibliography/links. **Offline snapshot** uses
only those bundled records, not live SIMBAD additions; it is an ICRS equirectangular
coordinate chart, not survey imagery. Vite bundles all application code locally;
survey tiles and live providers require network access. No synthetic sky source
is mixed into this snapshot. Existing synthetic development fixtures keep their
separate labels.

SIMBAD success metadata is cached in memory for 15 minutes (128 queries), with
20 upstream requests/minute globally per process, two concurrent calls, 2 MB
response cap, 12 s timeout. Failures are not cached. IRSA search metadata is cached
for 5 minutes (existing configured cache count), with 20 uncached searches/minute
per process. Existing worker/queue/time/observation limits still apply. Existing
IBE cutout and FITS artifact caches are reused. Source selection never downloads
a full remote FITS; sequence generation explicitly requests small IBE cutouts.
All memory cache/session state resets on restart; approved local FITS/artifact
files remain. See `fits-preview.md` for disk limits and immutable file identity.

Official references checked on 2026-11-14:

- [Aladin integration/API](https://cds-astro.github.io/aladin-lite/), including the
  pinned installed 3.8.2 source for click/overlay behavior.
- [CDS service status and recommended mirrors](https://aladin.cds.unistra.fr/).
- [ESA DSS2 survey metadata](https://skies.esac.esa.int/DSSColor/properties).
- [SIMBAD Harvard TAP service/schema](https://simbad.cfa.harvard.edu/simbad/sim-tap/)
  and [official Astroquery SIMBAD fields](https://docs.astropy.org/projects/astroquery/en/stable/simbad/simbad.html).
  Live Harvard queries verified `main_id`, `ra`, `dec`, `otype`, `coo_bibcode`
  and the ICRS/J2000 metadata. Exact `M 31` lookup succeeded. The mirror's parser
  requires unqualified `ORDER BY main_id`; this is reflected in the template.
- [IRSA SPHEREx access](https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-access/)
  and [official spectral-image tutorial/schema](https://caltech-ipac.github.io/irsa-tutorials/spherex-intro/).
- [Three.js documentation](https://threejs.org/docs/).

Keep Aladin's visible logo/link. `/notices/THIRD_PARTY.txt` links/references data
attributions and installed software notices; full Aladin LGPL/GPL and Three/React
MIT texts are shipped in `frontend/public/notices`. Data are not relicensed by
the application. The installed Aladin package metadata tag says GPL-3 whereas
its LICENSE/COPYING.LESSER contain LGPL v3; both supplied license texts are retained.

## Checks and limits

```powershell
.\.venv\Scripts\python -m pytest -q -p no:cacheprovider --basetemp .data/explorer-test-temp
npm.cmd test --prefix frontend
npm.cmd run build --prefix frontend
```

Use a fresh basename for `--basetemp` if old test files are owned by another
Windows account. Tests cover source-ID selection, empty-sky behavior, layer
independence, coordinate conversion, missing/noisy distances, provider failure/
validation/rate/cache behavior, footprint mapping and the original FITS workflow.
The production build retains size warnings for the existing lazy Three/Aladin
libraries. They are warnings, not build failures.

Limitations: no new source detection, automatic catalogue-to-observation matching,
proper-motion propagation, Bayesian distance estimation, or discovery claims.
Distances are intentionally unavailable until supplied with reviewed provenance.
The live SIMBAD Strasbourg service returned 404 during validation; Harvard worked.
The live IRSA schema probe timed out, so current remote search availability is
not established by offline tests; the existing adapter is retained and provider
errors remain recoverable. Local sample PNG/quality and WCS evidence do not
depend on remote provider availability. Candidate notes are browser-local,
without accounts, collaboration, a database or cross-device synchronization.
