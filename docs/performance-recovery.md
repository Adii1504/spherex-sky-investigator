# Latency and recovery improvements

## Measured locally

The same five-frame Barnard investigation previously recomputed on every call
(1.842 s and 1.803 s in the initial measurements). After result reuse, repeated
requests measured 0.0078 s and 0.0053 s. The first request after loading the new
server took 2.5893 s; the improvement is for repeated work, not a claim that a
fresh scientific calculation is instantaneous.

An actual 100-observation IRSA search took 3.0932 s; repeating it took 0.0275 s
and reused the same search session. A complete three-observation live archive
sequence took 26.755 s on first retrieval, then 0.0044 s to reopen the completed
job. First-time network requests still depend on IRSA availability and download
time. The raw measurements are in ignored `.data/latency-validation.json`.

## Recovery behavior

- Identical preset, SED and composite requests reuse completed results. File
  identity, parameters and mount prefix are part of the cache key. Missing
  generated assets invalidate the entry and cause regeneration. Uploads are
  not memoized; partial results are not treated as complete reusable results.
- Concurrent identical requests share work. Cached processing results bypass
  the plotting lock, so an unrelated slow render does not delay a cache hit.
- Preview and quality requests for one FITS product share its read/render.
  Unrelated FITS products do not hold one global render lock. A failed read
  clears its in-flight state so the next request can retry.
- Uploaded FITS reuse the observation parsed during validation instead of
  decoding it twice. Cache cleanup skips files temporarily locked by Windows
  and attempts another disposable entry.
- Unused search sessions rotate at capacity. A repeated search reuses its
  session for five minutes; saved investigations keep their referenced search.
  Re-saving an identical investigation reuses that investigation.
- Disposable previews rotate using recent-use order. Saved investigation
  previews remain protected. Hash-named generated directories can be reclaimed;
  original FITS, unknown files and source metadata are never removed.
- Repeated complete sequences reuse their job and image bytes. Partial or
  failed sequences can be retried. Preview content hashes prevent duplicate
  image storage. Expired disposable previews can be regenerated without
  restarting the server.
- Archive calls reuse a verified HTTPS client and connection pool. Sequence
  retrieval keeps at most two downloads in flight and reserves time for
  rendering. Download and rendering stages report actual observation counts;
  no artificial overall completion percentage is supplied.
- The browser retries a temporary backend outage with bounded backoff and
  immediately rechecks when the network returns or the window regains focus.
  Incremental builds retain hashed assets needed by already-open tabs.

Saved evidence is not silently deleted to make space. If all capacity is pinned
by saved work, export that evidence and increase the configured limit. Searches,
jobs and investigations are still in memory, so export important evidence before
intentionally stopping the server. This change does not introduce a database.

## Verification

Python tests exercise repeated use beyond cache capacity, saved-evidence
protection, complete-job reuse, partial-job retry, full-width FITS processing,
single-read sharing, independent concurrent renders, failure recovery, generated
asset regeneration and safe cache pruning. Frontend tests cover automatic
reconnection as well as the existing user workflows. Live archive search,
download, rendering and repeat requests were also exercised through HTTP.

Final verification: 169 Python tests and 118 frontend tests passed; the Vite
production build completed. After the final server reload, the five-frame
Barnard investigation took 2.2681 seconds cold and 0.0076 seconds repeated;
the generated preview was fetched and its PNG signature verified. Both the
main page and processing page returned HTTP 200.
