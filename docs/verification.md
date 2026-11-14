# Verification record

Verified on 2026-11-14 using Windows PowerShell and Python 3.13.7.

- `python -m pytest -q`: 25 passed. Coverage includes synthetic end-to-end search/sequence/PNG/investigation/verification/evidence integration; coordinate/date/FOV validation; empty coverage; duplicate IDs and canonical exposure separation; partial retrieval failures; sanitized processing failures; upstream timeout and dynamically unavailable capability errors; bounded worker admission; job deadline; missing science capabilities; trusted URLs; path traversal; CORS; evidence redaction; verification evidence retention after job eviction.
- `python scripts/smoke.py`: passed against a real temporary Uvicorn HTTP server. Confirmed startup, capability health, OpenAPI with eight paths, and the default structured archive-unavailable 503. Smoke server shut down after verification.
- `python -m pip check`: no broken requirements.
- One upstream Starlette test-client deprecation warning about httpx; tests still pass.

`constraints.txt` records tested installed dependency versions. Docker configuration was supplied but an image build was not tested. No real archive, image-processing or motion implementation was present, so no real sky field or scientific result was verified. Synthetic fixtures in tests are explicitly labelled and are not imported by application code. Default production capability states remain unavailable.
