"""Generate artifacts for server-manifest entries, or a clearly labelled synthetic demo."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from whylab.config import Settings
from whylab.fits_preview.routes import ArtifactCache, ProductRegistry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--product-id', help='Process one manifest ID; omit to process every entry')
    parser.add_argument('--synthetic-demo', action='store_true')
    args = parser.parse_args()
    settings = Settings.from_env()
    root = settings.output_dir.resolve().parent
    registry = ProductRegistry.load(root)
    if args.synthetic_demo:
        import numpy as np
        from astropy.io import fits
        from astropy.wcs import WCS
        raw = root/'fits-fixtures'
        raw.mkdir(parents=True, exist_ok=True)
        path = raw/'synthetic-preview.fits'
        w = WCS(naxis=2)
        w.wcs.crpix = [32.5, 32.5]
        w.wcs.crval = [120, 20]
        w.wcs.cdelt = [-.001, .001]
        w.wcs.ctype = ['RA---TAN', 'DEC--TAN']
        header = w.to_header()
        header['BUNIT'] = 'adu'
        yy, xx = np.indices((64, 64))
        image = np.random.default_rng(42).normal(size=(64, 64))
        image += 20*np.exp(-((xx-31.5)**2+(yy-31.5)**2)/8)
        image[0, 0] = np.nan
        if not path.exists():
            fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(image, header=header, name='IMAGE'),
                          fits.ImageHDU(np.zeros((64, 64), dtype=np.int32), name='FLAGS'),
                          fits.ImageHDU(np.ones((64, 64)), name='VARIANCE')]).writeto(path)
        registry = ProductRegistry(root, {'synthetic-preview': {
            'path': str(path.relative_to(root)), 'label': 'Synthetic fixture; not real SPHEREx data',
            'provenance_status': 'synthetic', 'predicted_position': {
                'ra_deg': 120., 'dec_deg': 20., 'astrometry_status': 'synthetic provisional'}}})
    if not registry.entries:
        parser.error('No local fits_manifest.json entries; supply the approved manifest or use --synthetic-demo')
    cache = ArtifactCache(settings, registry)
    ids = [args.product_id] if args.product_id else registry.entries
    for product_id in ids:
        try:
            print(json.dumps({'product_id': product_id, 'artifacts': str(cache.artifacts(product_id))}))
        except Exception as exc:
            print(json.dumps({'product_id': product_id, 'error': type(exc).__name__}))
            raise


if __name__ == '__main__':
    main()
