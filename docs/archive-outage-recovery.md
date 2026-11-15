# Archive search outage and recovery

On November 15, 2026, the exact field shown in the reported error (RA
269.45207695861876 degrees, Dec 4.693364966576667 degrees, FOV 2 arcmin) returned
HTTP 502 from IRSA's SIA service for both `spherex_dr1` and `spherex_qr3`.
A smaller query and IRSA's documented TAP route also returned 502; POST did not
bypass the failure. IRSA's response identified a proxy error reading its upstream
server. This is distinct from a stopped local application or a browser error.

## Application behavior

- The error reports the upstream status and explains that restarting the local
  platform cannot repair the remote outage. Query values remain available for retry.
- If one configured collection fails but another responds, validated observations
  from the successful collection remain usable. The coverage summary identifies
  failed collections and is explicitly incomplete.
- Partial responses bypass both archive-result and search-session reuse, allowing
  the next request to discover service recovery immediately. Complete successful
  results retain the existing cache behavior.
- If every collection fails, search stays failed. An outage is never represented
  as a successful empty search, and no fixture or synthetic observation is substituted.
- An empty result from only some collections is labelled incomplete coverage,
  rather than claiming the field has no observations.
- The outage panel provides **Open real imported FITS datasets** in a new tab,
  preserving the original archive query. The processing viewer uses local files.

## Continue using real observations during an outage

Open http://127.0.0.1:8010/processing/ and select **Barnards_Star** (or another
real target preset). After the application update, all five registered Barnard's
Star observations were available, the local investigation produced five frames,
and a generated PNG was retrieved and verified. Its scientific outcome was
`insufficient_evidence`; the outage fix does not alter that interpretation.

The local API and viewer can keep running while IRSA recovers. Retry the live
archive search later for current coverage; the local package is a separate,
limited set of imported observations, not a replacement for the full live archive.

## References and checks

- [IRSA SPHEREx data-access documentation](https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-access/)
- [IRSA's TAP cutout tutorial](https://caltech-ipac.github.io/irsa-tutorials/spherex-cutouts/)

Verification: 175 backend tests and 136 frontend tests passed; the production
build completed. New regressions cover per-collection failures, complete outage
followed by recovery, partial-session cache bypass, the explicit local-data link,
and honest empty/partial-result messaging. A live archive request still returned
IRSA HTTP 502 after the local update, while local FITS processing succeeded.
