# SPHEREx WhyLab — Project Overview

## Purpose

SPHEREx WhyLab is a local astronomy application for exploring the sky, inspecting
SPHEREx FITS observations, comparing images across epochs, and recording evidence
for possible source motion. It combines a sky explorer with a scientific
processing viewer on one FastAPI server.

The application assists investigation. A candidate marker, catalogue association,
or bright pixel is not a confirmed astronomical detection or discovery.

## Quick start

Run these commands from the project root. Keep the server terminal open.

### Git Bash: existing installation

```bash
source .venv/Scripts/activate
python -m whylab --port 8010
```

### PowerShell: existing installation

```powershell
.\.venv\Scripts\python -m whylab --port 8010
```

| Page | Address |
| --- | --- |
| Sky explorer | http://127.0.0.1:8010/ |
| Scientific processing viewer | http://127.0.0.1:8010/processing/ |
| Main API documentation | http://127.0.0.1:8010/docs |
| Main API health | http://127.0.0.1:8010/api/v1/health |

The launcher reads `.env` when present, otherwise `.env.example`. The default
port is 8000 if `--port` is omitted. One server serves both interfaces.

### First installation: PowerShell

Python 3.11 or newer and Node.js/npm are required. The existing environment was
checked with Python 3.13 and Node.js 22.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python -m pip install -c constraints.txt -e '.[test]'
npm.cmd ci --prefix frontend
npm.cmd run build --prefix frontend
.\.venv\Scripts\python -m whylab --port 8010
```

The processing viewer does not need a separate frontend build. Internet access
is needed for dependency installation, live archive queries, catalogue lookups,
and the remote sky survey. Registered local FITS data can be inspected without
live archive access.

## Features

| Feature | What it does |
| --- | --- |
| Interactive sky explorer | Pan and zoom through a survey, inspect coordinates, and select catalogue sources. |
| Solar System explorer | Scroll through planet, Sun, Moon and Earth cards; inspect dated positions and visit a body's surrounding field. |
| Rotating 3D globes and orbits | Click a planet or Earth to open its textured globe, then explore the Sun-centered system with orbit playback and camera controls. |
| Catalogue star close-ups | Select a sky star for its search/details panel, then choose View in 3D for a glowing rotating illustration. Star points inside the 3D viewer open close-ups directly. |
| Target catalogue | Open the five supplied targets and their registered observations. |
| SIMBAD lookup | Search an exact source name or a bounded region around a selected sky position. |
| Observation footprints | Show archive boundaries or supported local IMAGE WCS footprints. |
| Local FITS inspection | Display image previews, metadata, quality flags, and available predicted positions; download the original FITS. |
| Archive observation search | Query IRSA by right ascension, declination, field of view, and supported time constraints. |
| Sequence processing | Retrieve selected observations, align images, and produce previews with shared display settings. |
| Blink and difference views | Compare epochs using animation and signed difference images. |
| Motion diagnostics | Inspect candidate trajectories and reported residuals and outcomes when the evidence supports evaluation. |
| Held-out verification | Fit using selected training observations and evaluate separate reserved observations. |
| Spectral samples and RGB composition | Explore available wavelength samples and compose channels on a shared celestial grid. |
| Candidate pins and export | Mark exploratory candidates in the processing viewer and export its JSON results. |
| Investigation evidence | Save an investigation in the running session and export backend evidence JSON. |
| Recovery and caching | Reuse completed work, rotate disposable previews, retry failed requests, and reconnect after temporary backend outages. |
| Game Zone | Play Nebula Patrol and Asteroid Run with keyboard/touch controls, waves, power-ups, pause/restart, optional sound, and browser-local high scores. |
| 3D Starship Intercept | Pilot a reference-inspired twin-engine fighter, dodge lasers, and destroy three hostile ships for a retro mission-accomplished screen. |

The default Mercator overview fills the rectangular map panel and wraps sky
longitude. Dragging, arrow buttons, and arrow keys move the view. Selecting a
target opens details without changing zoom; **Centre on target** explicitly opens
its field. **Reset view** restores the overview. Mercator distorts polar regions;
use a centered target view when inspecting those regions closely.

## How the application works

1. **Choose a source or field.** Select a supplied target, search the catalogue,
   or enter sky coordinates. RA and Dec use degrees; field of view uses arcminutes.
2. **Find observations.** Use registered local products or search the live archive.
   Archive search returns observation metadata before image downloads begin.
3. **Select compatible observations.** Prefer distinct exposures from the same
   detector and compatible wavelength coverage. Repeated exposure IDs do not
   provide independent epochs.
4. **Generate a sequence.** The server downloads the selected cutouts, processes
   the available data, and produces image previews. The job reports download and
   rendering stages. Partial retrievals retain their available results and warnings.
5. **Inspect the evidence.** Compare images, blink frames, examine differences,
   and read metadata, quality flags, assumptions, and limitations.
6. **Evaluate motion where appropriate.** Keep training and reserved observations
   separate when using held-out verification. Treat `insufficient_evidence` as a
   valid outcome, not a software failure.
7. **Save and export.** Save the investigation within the running session and
   export important evidence before intentionally stopping the server.

## Ways to add observations

### Use the supplied datasets

Open a target in the sky explorer and choose an item under **Available
observations**, or open `/processing/` and choose a dataset preset.

| Real target | FITS observations |
| --- | ---: |
| Barnard's Star | 5 |
| WISE 0855 | 5 |
| Epsilon Indi B | 3 |
| RW Aurigae | 4 |
| R Draconis | 4 |
| **Total** | **21** |

The processing viewer also provides a labelled synthetic four-epoch demonstration
and a supplied six-band field. Synthetic results are demonstrations, not real
source detections.

### Search the live archive

Use the observation search with the desired RA, Dec, field of view, and supported
date filters. Select returned observations, then request sequence processing.
This needs internet access and a working IRSA service. The example configuration
enables the real archive adapter through
`WHYLAB_ADAPTER_FACTORY=whylab.integration:build_adapters`.

### Upload FITS for processing

Open the processing viewer, use its FITS upload controls, and run the investigation.
Inputs are validated and processed as astronomical FITS data. A PNG or JPEG does
not replace FITS metadata, celestial coordinates, or observation times. Uploading
for processing does not permanently register a product in the target catalogue.

### Register a local FITS product

From the project root in PowerShell:

```powershell
.\.venv\Scripts\python scripts/register_local_fits.py 'C:\path\to\observation.fits'
```

Restart the backend after importing so it reloads the registry. A standalone
product can remain unassociated with a target; registration alone does not prove
a source identification.

### Import a finalized dataspace package

```powershell
.\.venv\Scripts\python -m whylab.dataset 'C:\path\to\dataspace'
```

The importer verifies the package, copies approved products into the local data
area, and merges the registry. It reads the source package without changing it.
See [dataspace integration](docs/dataspace-integration.md) for package requirements
and the separate working-copy workflow for the supplied scripts.

## Architecture and source layout

| Location | Responsibility |
| --- | --- |
| `frontend/` | React/Vite sky explorer with Aladin Lite and Three.js. |
| `frontend_viewspace/` | Scientific processing interface in HTML/CSS/JavaScript. |
| `whylab/app.py` | Main FastAPI routes, sessions, jobs, sequences, and investigations. |
| `whylab/archive.py` | IRSA archive search and cutout integration. |
| `whylab/security.py` | Trusted HTTPS retrieval, connection pooling, and download bounds. |
| `whylab/fits_preview/` | Registered FITS preview and quality inspection. |
| `whylab/dataset.py` | Verified dataspace package import. |
| `backend/main.py` | Scientific processing API mounted under `/processing`. |
| `backend/processing/` | FITS reading, alignment, differences, motion diagnostics, and result reuse. |
| `teammate_integration.py` | Adapters connecting the scientific pipeline to WhyLab workers. |
| `PythonProject/final_dataset/` | Supplied 21-observation dataset and associated metadata. |
| `tools/dataspace/` | Preserved supplied astronomy scripts. |
| `.data/` | Local registry, imported data, caches, and generated runtime artifacts. |
| `tests/` | Backend integration and regression tests. |
| `docs/` | Detailed implementation, workflow, and validation documentation. |

The imported scientific implementation came from
`Adii1504/spherex-sky-investigator`, commit
`9c2e3bb8a3c71ed0d67bf97e3d5a35c7d133b116`. See the
[integration record](docs/github-processing-integration.md) for local adaptations.

## Latency and reliability

- Repeated scientific requests reuse completed results when inputs and generated
  assets remain valid. Missing assets trigger regeneration.
- Repeated searches reuse sessions for five minutes. Identical in-flight requests
  share work, and complete sequences can reuse their existing job and previews.
- Archive downloads reuse HTTPS connections and keep at most two downloads in flight.
- Disposable generated previews rotate at capacity. Original FITS and saved
  investigation evidence remain protected.
- Failed and partial sequence requests can retry. Temporary backend outages cause
  automatic browser reconnection checks.

Measured locally: repeated five-frame investigation requests dropped from about
1.8 seconds to 5–8 milliseconds. A three-observation live archive sequence took
26.8 seconds initially and about 4 milliseconds to reopen. These are measurements,
not service guarantees; cold processing and first-time downloads still take time.
See [latency and recovery](docs/performance-recovery.md).

## Validation

### Solar System layer

The **Meet our neighbours** strip below the sky map contains all eight planets,
the Sun, and the Moon. Select a card or coral map marker to read a brief
introduction, then use **Explore around …** to center a 15-degree field. Drag,
scroll, and the existing arrow controls continue to work. The Earth card explains
the observing viewpoint and intentionally has no sky marker.

`GET /api/solar-system` computes positions locally with Astropy's ERFA builtin
ephemeris, cached by UTC minute. **Update positions** refreshes the displayed
epoch. Coordinates are approximate geocentric GCRS directions with ICRS-aligned
axes, overlaid for exploration on the static survey; they are not local horizon
positions, precision pointing coordinates, surface images, or SPHEREx detections.
Planet labels separate automatically in screen space and retain leader lines to their actual sky anchors. Star labels are reserved space. Earth has a visible observer badge, not a fabricated celestial position. Markers and illustrated cards are symbolic, not to scale. Body introductions
link to NASA. The layer can be switched off independently of catalogue sources
and observation footprints.

References: [Astropy get_body](https://docs.astropy.org/en/stable/api/astropy.coordinates.get_body.html)
and [NASA planets](https://science.nasa.gov/solar-system/planets/).

### Latest checks

The latest verification completed **175 Python tests**, **136 frontend tests**,
and the production frontend build. Live archive search, sequence retrieval, and
generated previews were also exercised. Tests establish software behavior, not
astronomical correctness or discovery.

```powershell
.\.venv\Scripts\python -m pytest -q
npm.cmd test --prefix frontend
npm.cmd run build --prefix frontend
```

## Important limitations

- Searches, jobs, and investigations are in memory and are lost on server restart.
  Export important evidence. Downloaded source data and session state have
  different lifetimes.
- Run one application worker. The current implementation has no durable database
  or authentication and is intended for local use.
- Unknown or incompatible wavelengths and uncertain metadata can produce
  `insufficient_evidence`. Catalogue coordinates and predictions do not establish
  independent detections.
- Spectral samples use peak-pixel estimates rather than calibrated integrated
  source photometry. Reprojection is not a claim of flux conservation.
- Coverage does not imply detection. Scientific flag masks, uncertainty floors,
  timing assumptions, and source associations need expert review.
- When all cache capacity is protected by saved evidence, export that evidence
  and increase the appropriate configured limit. Saved work is not silently deleted.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Port already in use / WinError 10048 | Open the existing server URL, stop the older server with Ctrl+C, or choose another `--port`. |
| `.env` does not exist | Use `python -m whylab --port 8010`; its launcher falls back to `.env.example`. |
| Git Bash reports `..venvScriptspython` | Activate the environment and use `python`; backslashes are shell escapes in Bash. |
| Browser cannot connect | Confirm the terminal says Uvicorn is running, then use the matching `http://127.0.0.1:<port>/` URL. |
| Archive search or download fails | Check connectivity, read the returned error, and retry; local FITS inspection may still work. |
| Preview expired | Rerun the search or regenerate the sequence. A routine expired preview does not require a platform restart. |
| New frontend changes are missing | Rebuild `frontend`, then refresh the browser. |
| New registered products are missing | Restart after importing because the product registry loads at startup. |

## Further documentation

- [Astronomy explorer](docs/astronomy-explorer.md)
- [Dataspace integration](docs/dataspace-integration.md)
- [Scientific processing integration](docs/github-processing-integration.md)
- [FITS inspection](docs/fits-preview.md)
- [Latency and recovery](docs/performance-recovery.md)
- [Archive outages and real local FITS recovery](docs/archive-outage-recovery.md)
- [3D Solar System and surface maps](docs/solar-system-3d.md)
- [Game Zone and controls](docs/game-zone.md)
- [API workflow](docs/api.md)
