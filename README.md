# SPHEREx WhyLab backend

For the free hosted submission, see [Render deployment](docs/render-deployment.md).
The root `render.yaml` configures one Free Docker web service; the image includes
the verified local observation dataset. Live archive availability and temporary
investigation storage are explained in that guide.

GitHub commit `9c2e3bb` is integrated. Run `python -m whylab --port 8010` and open
<http://127.0.0.1:8010/processing/> for its scientific processing viewer, or `/`
for the sky explorer. See [GitHub processing integration](docs/github-processing-integration.md).

The supplied dataspace scripts and 21-observation dataset are integrated with the
local viewer. See [dataspace integration](docs/dataspace-integration.md) for import,
run commands, script workflows, and scientific limitations.

Original minimal FastAPI backend for the 48-hour project. The starting workspace was empty: no teammate code or AGENTS.md was present. No science algorithms or real archive integration are included. Default health reports all three capabilities unavailable, and dependent endpoints return HTTP 503. Test data is synthetic and exists only in tests.

## Windows PowerShell

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python -m pip install -c constraints.txt -e ".[test]"
Copy-Item .env.example .env
# Load the simple KEY=VALUE file into this process (no shell evaluation).
Get-Content .env | ForEach-Object {
  if ($_ -match '^([A-Z_]+)=(.*)$') {
    [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process')
  }
}
.\.venv\Scripts\python -m uvicorn whylab.app:app --host 127.0.0.1 --port 8000 --workers 1
```

Python 3.11+ is supported. `constraints.txt` pins the dependency versions tested on Python 3.13; Docker uses the same runtime constraints. The application reads environment variables, not `.env` automatically. Frontend URL must appear in WHYLAB_CORS_ORIGINS (comma separated, no wildcard needed).

In another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python scripts/smoke.py
```

Interactive API documentation: http://127.0.0.1:8000/docs ; OpenAPI: `/openapi.json`.

## Integration and deployment

See [adapter contracts](docs/integration-contract.md) and [API workflow](docs/api.md). Set WHYLAB_ADAPTER_FACTORY to a deployment-owned `module:function`. It receives `(settings, trusted_retriever)` and returns `(archive, sequence, motion)` adapters. Use unavailable adapters for unfinished capabilities; no fake fallback. No teammate modules were available to wrap.

Docker: `docker build -t whylab .` then `docker run --rm -p 8000:8000 --env-file .env whylab`. Copy teammate modules into the image and install their dependencies before setting the factory. The supplied image includes only this backend. Use a TLS reverse proxy for a public deployment. Run ONE application process/replica. `/api/v1/health` is the readiness endpoint for the API process, with separate capability flags.

All searches, jobs, investigations, and preview URL mappings are in memory and are LOST on restart. There is no database or authentication. Unused search sessions and disposable generated previews rotate at capacity; repeated requests reuse sessions and results. Completed job records may expire. Attached sequence evidence and verification history are retained with investigations until restart. Saved investigations and their previews remain protected. If saved evidence itself reaches capacity, export it or increase the configured limit. Preview bytes have both per-file and total disk limits. Recognized disposable preview files from earlier runs are reclaimed automatically when needed. Original FITS data and unknown files are preserved. Use a dedicated directory, never a directory shared with another service.

Workers and queue are bounded. Execution deadlines start when work begins; queued jobs may wait. Python threads cannot forcibly stop blocking native code: timed-out jobs stay failed and retain their worker slot until the adapter returns. Adapters MUST enforce upstream/native processing deadlines. Shutdown waits for running work. Sequence publication checks the deadline; late computation cannot publish a successful job. Progress is null because no adapter progress contract exists yet. Heavy retrieval, processing, and verification run in the executor; search awaits its bounded worker asynchronously.

Production hardening beyond this project scope includes durable state, request body/rate limits at the proxy, and process-isolated cancellation if native processing can hang. Output/cache limits prevent unbounded stored results, but adapters must bound their intermediate memory and bytes. Trusted archive hosts are exact HTTPS hostnames; trusted service ownership/DNS is an operator responsibility. Redirects, userinfo and nonstandard ports are rejected. Teammate wrappers must use the provided retriever for every download and must not expose filesystem paths or credentials in metadata.

## Current acceptance boundary

The fixture-backed automated pipeline covers search -> sequence -> preview -> investigation -> held-out verification -> evidence. It is plumbing validation, not proof of astronomical correctness. A real field cannot be completed until teammates provide archive search/cutouts, scientific sequence processing, and motion verification. The handoff contract lists the exact missing pieces and a real-field acceptance procedure.

## Astronomy explorer extension

See [local astronomy explorer](docs/astronomy-explorer.md) for the implemented sky,
Three.js, catalogue lookup, FITS inspection and unverified candidate workflow,
exact local installation/run commands, configuration, provider/cache/coordinate
conventions, attribution and validation limits. No paid services are required.

See [latency and recovery](docs/performance-recovery.md) for result reuse, automatic cache rotation, real download progress, and measured timings.
