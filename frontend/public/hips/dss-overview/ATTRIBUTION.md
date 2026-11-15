# Bundled reference sky

Real Digitized Sky Survey (DSS) imagery: STScI/NASA; colour composition and HiPS
generation: CDS. Downloaded from the NASA/IPAC IRSA DSS2 colour HiPS service.
Original credits and survey description are preserved in `upstream-properties.txt`.

The order-3 Allsky JPEG is retained byte-for-byte. Its 768 existing 64-pixel
thumbnails are repackaged as individual tiles using the IVOA HiPS row-major
Allsky layout. This is a low-resolution navigation overview, not SPHEREx imagery,
a source catalogue, a new measurement, or a fabricated star field.

Source: https://irsa.ipac.caltech.edu/data/hips/CDS/DSS2/color/
HiPS standard: https://www.ivoa.net/documents/HiPS/
Reproduction script: `scripts/bundle_reference_sky.py`.
