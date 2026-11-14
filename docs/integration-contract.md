# Teammate integration contract v1

Authoritative types are `whylab/models.py` and Protocols in `whylab/adapters.py`. All adapter methods are synchronous and execute in the bounded backend worker pool, outside the event loop. They must be thread-safe, enforce configured limits, and enforce their own I/O/native processing timeouts. Return Pydantic models (search/process/verification also accept model-compatible dictionaries). `available: bool` indicates whether the implementation is ready, not a fabricated success or live upstream probe. Raise `CapabilityUnavailable(capability)` for a capability becoming unavailable and ordinary exceptions for processing failures; errors are sanitized at the API boundary.

## Wiring

Create a deployment-local module `teammate_integration.py` with:

```python
from whylab.adapters import Unavailable

def build_adapters(settings, trusted_retriever):
    # Wrap the team's existing functions here once supplied.
    # Do not insert test fixtures or successful placeholders.
    return (Unavailable("archive_access"),
            Unavailable("image_processing"),
            Unavailable("motion_verification"))
```

Set `WHYLAB_ADAPTER_FACTORY=teammate_integration:build_adapters`. Replace individual unavailable instances with thin wrappers; no backend handler changes are needed. The retriever must be used by wrappers for all upstream downloads. It accepts only exact configured HTTPS hosts, disables redirects and environment proxies, and bounds response bytes. Expose needed public service hostnames through WHYLAB_TRUSTED_HOSTS. No URL from a client request is accepted. The backend does not sandbox trusted Python adapters: bypassing this retriever defeats the restriction.

## Archive teammate supplies

- `search(query: Search) -> SearchResult`: query has finite RA/Dec/FOV and optional timezone-aware date bounds. Honor `settings.max_observations` (truncate with a warning and coverage summary), handle coverage and dates with real archive logic. Empty coverage returns an empty list. Return stable observation IDs scoped to products and canonical globally unambiguous exposure_id across releases/products/detectors, UTC observation time, release, product_id, nullable detector, public archive provenance, nullable wavelength/quality fields. Never derive exposure identity from the product ID if multiple products share the exposure.
- `cutout(observation: Observation, sky: Sky) -> Cutout`: download/cache real FITS data, returning bytes, observation_id, media_type and public scientific metadata. Identity must match. Cache management and FITS retrieval belong to this teammate; enforce cache/byte limits and trusted upstream retrieval. No local paths or signed credentials in returned metadata. Backend may omit failed cutouts and warn. Archive cache keys must include product, release, sky position, FOV and relevant processing/version inputs.

Example search input:

```json
{"ra_deg":12,"dec_deg":-5,"fov_arcmin":2,"start_utc":"2025-01-01T00:00:00Z"}
```

Illustrative response shape (identities below are schema placeholders, not real data):

```json
{"observations":[{"id":"product-id","exposure_id":"canonical-exposure-id","observed_at":"2025-01-01T01:00:00Z","release":"release-id","product_id":"archive-product-id","detector":null,"provenance":{"archive":"IRSA","source_url":"https://irsa.ipac.caltech.edu/","citation":null},"file_wavelength_um":null,"position_wavelength_um":null,"quality":null}],"coverage_summary":{"count":1},"warnings":[]}
```

`file_wavelength_um` is a min/max coverage pair for the file, NOT a measurement at the selected position. Only populate `position_wavelength_um` from a scientifically valid pixel/position calculation. Missing metadata stays null. Archive URLs must be stable/public and on the trusted host list.

## Scientific sequence teammate supplies

`process(observations: list[Observation], cutouts: list[Cutout], sky: Sky) -> ProcessedSequence`.

- Perform all alignment, masking, wavelength compatibility, difference calculations and motion measurements here, never in API handlers.
- Return one PNG `Preview(observation_id, png: bytes, metadata)` per successful observation. Backend orders previews by observation time. Return a subset and warnings for partial failures. No output or unknown/duplicate IDs fails the job. Backend writes opaque filenames; do not supply paths.
- Return `processing_version`, explicit `processing_settings`, `shared_display_settings` applied consistently to all comparable frames, `measurements` and comparison `warnings` (including wavelength/quality/incompatibility limitations). Backend cannot validate scientific comparability; do not label incompatible images as valid differences.
- PNG bytes and intermediate memory must respect configured budgets. Raw adapter outputs are internal Python values; binary cutouts/previews are never serialized into evidence.

Result shape (binary PNG field is Python-only):

```json
{"previews":[],"processing_version":"team-version","processing_settings":{"alignment":"documented-method"},"shared_display_settings":{"stretch":"documented-shared-stretch"},"measurements":{},"warnings":["Describe incompatibility or omitted observations here"]}
```

An empty preview list shown above documents the shape; in a real processing call it results in a failed job.

## Motion teammate supplies

`verify(training: list[Observation], reserved: list[Observation], sky: Sky, archive: ArchiveAdapter) -> VerificationResult`.

Backend validates membership and disjoint canonical exposures before invoking this method. The science adapter MUST fit the prediction using only training observations, then evaluate against reserved observations without fitting to them. Access to cutouts is through the archive adapter. Never silently use reserved observations for alignment or model selection in a way that leaks the target measurement into fitting; document needed common calibration assumptions.

```json
{"outcome":"insufficient_evidence","measurements":{},"assumptions":["State the method and training-only fit assumptions"],"limitations":["Explain why evidence is insufficient"],"warnings":[],"processing_version":"team-version"}
```

Allowed outcomes: supported, not_supported, insufficient_evidence. Measurements are adapter-owned JSON data, not invented backend metrics. No backend confidence percentage or algorithm. Keep coordinate/time units and uncertainty definitions explicit within measurements. All metadata is export-safe JSON: no credentials, secrets, private storage URLs or machine paths; do not put these in free-text strings. Filtering is a safeguard, not a security boundary around malicious adapter code.

## Frontend teammate supplies

Use the `/api/v1` API workflow in [api.md](api.md). Handle 503 per-capability, empty coverage, job failures and warnings visibly. Poll jobs until terminal, respect chronological preview order and shared display settings, show processing limitations, choose explicit training/reserved groups, and download the evidence JSON. Do not present test fixtures as NASA observations.

## Real-field acceptance handoff

1. Register the real archive wrapper and confirm health reports archive access available. Search one known covered sky field and review archive product provenance/date bounds; retain a genuine search response.
2. Register sequence processing, retrieve real cutouts using trusted services, run a sequence, inspect chronological PNGs and shared display settings, and check wavelength/quality warnings with the scientist.
3. Save an investigation attached to that completed sequence and inspect exported provenance/settings/version/measurements.
4. Register motion verification, reserve unused exposures, run verification and preserve its supported/not_supported/insufficient_evidence result with assumptions and limitations in evidence.
5. Have frontend use these IDs/URLs on the configured origin. Test an uncovered field, a failed cutout and an unavailable service.

Until these steps run with teammate implementations, the real astronomy pipeline remains unavailable. Automated test fixtures prove backend integration only.
