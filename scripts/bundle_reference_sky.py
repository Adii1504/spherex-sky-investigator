"""Package real DSS Allsky thumbnails as a small, self-hosted HiPS overview.

The IVOA Allsky layout is row-major HEALPix tile number, 27 columns at order 3.
No invented stars, photometry, interpolation or source-identification claims.
"""
import hashlib
import io
import json
from pathlib import Path
import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parents[1] / 'frontend/public/hips/dss-overview'
SOURCE = 'https://irsa.ipac.caltech.edu/data/hips/CDS/DSS2/color'


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=30) as client:
        response = client.get(SOURCE+'/Norder3/Allsky.jpg'); response.raise_for_status()
        data = response.content
        response = client.get(SOURCE+'/properties'); response.raise_for_status()
        original = response.text
    image = Image.open(io.BytesIO(data)).convert('RGB')
    if image.size != (1728,1856):
        raise ValueError(f'Unexpected order-3 Allsky atlas geometry: {image.size}')
    directory = ROOT/'Norder3'; directory.mkdir(exist_ok=True)
    (directory/'Allsky.jpg').write_bytes(data)
    tiles = directory/'Dir0'; tiles.mkdir(exist_ok=True)
    for pixel in range(768):
        x,y = (pixel%27)*64,(pixel//27)*64
        image.crop((x,y,x+64,y+64)).save(tiles/f'Npix{pixel}.jpg',quality=95)
    (ROOT/'upstream-properties.txt').write_text(original,encoding='utf8')
    (ROOT/'properties').write_text('\n'.join([
        'creator_did = ivo://spherexplore/local-dss-overview',
        'obs_title = Bundled DSS2 colour overview',
        'obs_description = Low-resolution DSS2 colour Allsky thumbnails, repackaged for offline navigation. Not SPHEREx data.',
        'obs_copyright = DSS STScI/NASA; colour composition CDS; original service NASA/IPAC IRSA',
        'hips_version = 1.4', 'hips_release_date = 2026-11-15T00:00:00Z',
        'hips_status = public master clonableOnce', 'dataproduct_type = image',
        'hips_frame = equatorial', 'hips_order = 3', 'hips_order_min = 3',
        'hips_tile_width = 64', 'hips_tile_format = jpeg',
        'hips_pixel_cut = 0 255', 'moc_sky_fraction = 1', '',
    ]),encoding='utf8')
    (ROOT/'source.json').write_text(json.dumps({'source':SOURCE,
        'allsky_sha256':hashlib.sha256(data).hexdigest(), 'tiles':768,
        'tile_pixels':64,'order':3, 'note':'Real survey thumbnail data; overview resolution only.'},indent=2)+'\n',encoding='utf8')
    print('Bundled DSS overview:', len(list(tiles.glob('*.jpg'))), 'tiles')


if __name__=='__main__':
    main()
