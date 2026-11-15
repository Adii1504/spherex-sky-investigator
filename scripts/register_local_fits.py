"""Register one user-supplied local FITS file; never assign a catalogue source."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from datetime import datetime, timezone
from astropy.io import fits
from astropy.wcs import WCS
from whylab.config import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    args = parser.parse_args()
    source = args.path.resolve(strict=True)
    if source.stat().st_size > 100_000_000:
        parser.error('Local demo import limit is 100 MB')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    product_id = 'local-' + digest[:20]
    root = Settings.from_env().output_dir.resolve().parent
    raw = root / 'raw'; raw.mkdir(parents=True, exist_ok=True)
    destination = raw / (product_id + '.fits')
    if not destination.exists():
        shutil.copyfile(source, destination)
    with fits.open(destination, memmap=True) as hdus:
        image = hdus['IMAGE']; header = image.header
        observed_at = header.get('DATE-OBS', hdus[0].header.get('DATE-OBS'))
        footprint = None
        try:
            height, width = image.shape
            points = WCS(header).celestial.pixel_to_world(
                [-.5, width-.5, width-.5, -.5], [-.5, -.5, height-.5, height-.5]).icrs
            footprint = 'POLYGON ICRS ' + ' '.join(f'{ra:.10f} {dec:.10f}' for ra, dec in zip(points.ra.deg, points.dec.deg))
        except Exception:
            pass  # No WCS means unavailable footprint, never an estimated square.
    manifest = root / 'fits_manifest.json'
    entries = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {}
    if product_id not in entries:
        entries[product_id] = {'path': 'raw/' + destination.name, 'target_id': None,
            'label': 'User-supplied SPHEREx sample', 'provenance_status': 'User supplied; source association unverified',
            'provisional': True, 'sha256': digest, 'footprint_stcs': footprint,
            'registered_at': datetime.now(timezone.utc).isoformat(), 'observation': {'observed_at': observed_at}}
        # Never overwrite an existing product's metadata or prediction.
        temporary = manifest.with_suffix('.tmp')
        temporary.write_text(json.dumps(entries, indent=2), encoding='utf-8'); temporary.replace(manifest)
    print('Registered:', product_id)
    print('SHA-256:', digest)
    print('No target association or predicted source position was assigned.')
    if source.stat().st_size > Settings.from_env().max_cutout_bytes:
        print('Before running the backend, set WHYLAB_MAX_CUTOUT_BYTES=70000000 for this 60 MB sample.')


if __name__ == '__main__':
    main()
