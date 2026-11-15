# Refinement audit — 15 November 2026

Reproduced and corrected:

- Index errors when a sky position rounded beyond the final image pixel.
  Measurements now use the physical pixel boundary and clamp array indexes.
- NaN, infinity, zero and negative wavelengths were accepted as compatible.
  Invalid values now remain unavailable; a requested position outside a wavelength
  map does not inherit the map centre's wavelength.
- Single-epoch observations could produce a stationary verdict with a fictitious
  zero velocity. Independent evaluation epochs and identities are now required;
  missing or malformed times produce insufficient evidence.
- Motion fits jumped across RA zero and predictions ignored the fitted intercept.
  RA offsets now wrap correctly, the stationary mean is circular, and predictions
  use the fitted reference position.
- The supplied 60 MB sample failed against the 50 MB default preview limit.
  Both configuration defaults now allow 70 MB. The upload processing endpoint
  keeps its separately documented 50 MB per-file / 100 MB total limit.
- Empty processing requests silently chose a synthetic dataset. They now ask
  for an explicit preset or FITS upload.
- Re-measuring a selected candidate reverted to the original target coordinates.
  Selection coordinates and dataset identity now stay paired.

The processing viewer now has a responsive layout, a square image stage aligned
with candidate overlays, readable status messages, collapsible assumptions,
retry and stop-waiting controls, frame date/detector metadata, and a reopenable
evidence panel. Its upload dialog supports keyboard focus, Escape, validation,
and focus restoration. Non-JSON server responses receive a readable error.
External web fonts are no longer needed. Local unassociated FITS files now have
download links, and their return links do not contain a null target identifier.

Matplotlib colormap calls were updated to avoid the imported deprecations.
Duplicate test definitions that hid dead test code were removed.
Supplied FITS headers with SIP distortion coefficients but no matching CTYPE
declaration now carry an explicit review warning. Their metadata is retained;
the implementation does not guess which distortion convention was intended.

Validation: 149 Python tests and 117 frontend tests passed, plus the production
build. Regression tests cover the reproduced boundary cases, motion predictions,
missing evidence, selected-coordinate SED requests, keyboard interaction, and
error recovery. Live-data checks are recorded in the task response. Scientific
processing remains exploratory and requires independent source verification.
