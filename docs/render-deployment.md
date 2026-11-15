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

The reference sky uses the same DSS2 colour survey through official IRSA, ESA
and CDS mirrors, with JPEG tiles and automatic failover on errors or timeouts.
This browser-side imagery service is separate from SPHEREx archive search.
Mirror success is not a guarantee that every future tile request will succeed.

Live investigation workflow: archive search -> select observations -> build
sequence -> save investigation -> reserve independent exposures -> verify/export.
If IRSA returns HTTP 502, the first step cannot complete. Moving hosts does not
repair that upstream response. Real bundled targets remain accessible through
`/processing/`; this is a separate local-data workflow, not an automatic archive
replacement. Verification may correctly report insufficient evidence when dates,
wavelengths, quality or independent exposures are unsuitable.

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
