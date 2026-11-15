# SphereXplore deployment on Render Free

This repository contains a Docker-based Render Blueprint in `render.yaml`.
It deploys the React frontend, FastAPI API and `/processing/` viewer together.
No account passwords, verification codes or API tokens belong in the repository.

## Prepare and deploy

1. Review and commit the project source and assets to your own GitHub repository.
   Include `PythonProject/final_dataset` (metadata, checksums and all 21 FITS),
   `frontend/public`, `frontend_viewspace`, `backend`, `whylab`,
   `teammate_integration.py`, `scripts/serve.py`, Dockerfile and render.yaml.
   The ignore rules allow only the bundled dataset and small sample FITS;
   private `.env`, local `.data`, virtual environments and dependencies stay excluded.
2. Sign into Render yourself and select **New > Blueprint**, then connect your
   repository. Review the proposed resource: exactly one **Free** web service,
   with no database or disk. Alternatively create a Docker Web Service manually,
   choose Free and set its health check to `/api/v1/health`.
3. Deploy. The Docker build installs the pinned Python dependencies, builds Vite,
   verifies the dataset checksums, and builds the local product registry inside
   the image. Missing or altered dataset files fail the build visibly.
4. Open the HTTPS `onrender.com` address assigned by Render. The exact name depends
   on availability. No custom domain is required.
5. Test `/`, `/processing/`, `/api/targets`, `/api/v1/health`, a real target preset,
   the 3D views and games. Check live archive search separately: an IRSA outage
   must remain an explicit failure, never be presented as a successful empty query.

Render supplies `PORT`; the entry point binds `0.0.0.0` and runs one Uvicorn
process. Background work is limited to one worker in the Blueprint. The frontend
uses the same origin as the API, so no deployment-specific API URL is necessary.

## Investigations and availability

The reference sky starts from a self-hosted DSS2 colour overview. Optional live
imagery uses official IRSA, ESA and CDS mirrors, with JPEG tiles and automatic
failover to the bundled overview. This imagery is separate from SPHEREx archive
search. A live mirror response does not guarantee every future tile will load.

Live investigation workflow: archive search -> select observations -> build
sequence -> save investigation -> reserve independent exposures -> verify/export.
If IRSA returns HTTP 502, the first step cannot complete. Moving hosts does not
repair that upstream response. Real bundled targets remain accessible through
`/processing/`; this is a separate local-data workflow, not an automatic archive
replacement. Verification may correctly report insufficient evidence when dates,
wavelengths, quality or independent exposures are unsuitable.

The observations panel offers **Search downloaded observations** after a live
search error. It calls `/api/v1/observations/search/local` explicitly, filters the
approved local FITS by actual image WCS and observation dates, and creates a normal
search session. Sequence generation, saving, held-out verification and evidence
export use the same workflow, retrieving the checksum-verified local bytes.
Local results are always labelled and claim no archive completeness. Coverage
means the search centre is inside an image, not that the entire field is covered.
If nothing matches, buttons offer actual centres of the five bundled target
fields; only clicking one changes the query. No nearest-target substitution occurs.

Normal searches now use that local endpoint first by default. Once those results
are visible, the browser calls `/api/v1/observations/search/{search_id}/sync` in
the background. A separate bounded network worker checks IRSA without occupying
the scientific worker. The same search session is reconciled by exact pipeline
product filename (including detector and version), preserving local IDs, original
FITS bytes, selections and existing investigation evidence. New remote products
are appended within the observation limit. Matching metadata is not a scientific
confirmation or a proof of identical file bytes. Unavailable/partial checks retry
after 60 seconds on an active visible page, and on reconnect/focus. No server polling runs without a
browser session. The UI refreshes downloaded data and checks IRSA through the
non-blocking sync path; it does not replace the local panel with an upstream 502.

Selecting a supplied catalogue target now calls
`/api/v1/observations/search/target/{target_id}`. That workflow opens all approved
observations associated by the supplied manifest, exposes their imported metadata,
and uses the mean direction of supplied per-observation positions for the processing
field. It does not reinterpret the static catalogue reference position as a modern
observed position. Each file retains its own predicted position and WCS coverage.

The default Aladin background is now a bundled, real DSS2 colour overview under
`/hips/dss-overview/`, about 2 MB including all 768 order-3 tiles. It needs no
external tile server. **Load live sky imagery** optionally tries the live mirrors;
if all fail it falls back to the bundled survey. The imagery is coarse at high
zoom and is explicitly separate from the SPHEREx FITS observations. Credits,
source checksum and the original survey properties are bundled with the data.

The observations panel opens directly into selection and the observation list.
Introductory local-data notices, sync diagnostics, successful-query coordinates,
dataset shortcuts and expanded search-warning/coverage blocks are omitted from
that view. Background reconciliation continues; observation metadata and exported
scientific evidence still retain their source and limitations. Empty searches
keep dataset choices so users can recover without losing the actual query.

The application shell and API use no-store caching. `/api/v1/health` reports
the deployment revision when Render provides `RENDER_GIT_COMMIT`, plus supported
workflow features. A new frontend served by an old running backend can return
405 for a new POST route; deploy/restart the backend and refresh the page together.

Search sessions, jobs and saved investigations are currently in memory. They
expire on server restart or free-service sleep. Export evidence before leaving;
old investigation links are not durable. Uploaded files and generated previews
are also temporary. The bundled original observations survive because they are
part of the image and their registry is rebuilt on each image build. A durable,
shared investigation store would require a separate persistence implementation.

## Budget and public-demo limits

The Blueprint declares only a Free service. Leave payment details off the account
and do not add paid resources. Render Free sleeps after 15 idle minutes, may take
about a minute to wake and has monthly resource limits. It does not guarantee
uninterrupted service or sufficient memory for every FITS workload. This project
has no user authentication; use it for public, non-sensitive demonstration data.
Do not treat saved investigation IDs as private storage.

Docker is required to verify the final Linux image locally:

```powershell
docker build -t spherexplore .
docker run --rm -p 8000:8000 -e PORT=8000 -e WHYLAB_WORKERS=1 spherexplore
```

Official references: https://render.com/docs/free,
https://render.com/docs/blueprint-spec, https://render.com/docs/web-services.
