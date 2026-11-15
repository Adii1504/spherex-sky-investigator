"""Real supplied datasets remain usable at their observation epoch without IRSA."""
import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image
from fastapi.testclient import TestClient

from whylab.app import create_app
from whylab.config import Settings
from whylab.dataset import import_dataset
from whylab.fits_preview.routes import ProductRegistry


def test_all_supplied_target_datasets_open_from_catalogue_coordinates(tmp_path):
    import_dataset(Path('PythonProject/final_dataset'),tmp_path)
    with TestClient(create_app(Settings(output_dir=tmp_path/'previews'),
            fits_registry=ProductRegistry.load(tmp_path))) as client:
        query={'ra_deg':269.45207695861876,'dec_deg':4.693364966576667,'fov_arcmin':2}
        for target,count in [('barnards-star',5),('epsilon-indi-b',3),('wise-0855',5),('rw-aurigae',4),('r-draconis',4)]:
            response=client.post('/api/v1/observations/search/target/'+target,json=query)
            assert response.status_code==200, response.text
            result=response.json()
            assert len(result['observations'])==count
            assert result['coverage_summary']['target_id']==target
            assert result['query']['ra_deg']!=query['ra_deg']
            assert response.headers['cache-control']=='no-store'
            for observation in result['observations']:
                assert observation['quality']['dataset']['adopted_astrometry']['source_id']
                assert observation['quality']['predicted_position']
                assert observation['quality']['sha256']
                assert observation['release']=='imported-local'
        response=client.post('/api/v1/observations/search/target/unknown',json=query)
        assert response.status_code==404
        response=client.post('/api/v1/no-such-route',json={})
        assert response.status_code==404
        assert response.json()['code']=='api_route_not_found'


def test_bundled_sky_atlas_retains_its_source_and_contains_every_overview_tile():
    root=Path('frontend/public/hips/dss-overview')
    source=json.loads((root/'source.json').read_text())
    assert hashlib.sha256((root/'Norder3/Allsky.jpg').read_bytes()).hexdigest()==source['allsky_sha256']
    tiles=list((root/'Norder3/Dir0').glob('Npix*.jpg'))
    assert len(tiles)==768
    for path in tiles:
        with Image.open(path) as image:
            assert image.size==(64,64)
    properties=(root/'properties').read_text()
    assert 'hips_order = 3' in properties
    assert 'hips_tile_width = 64' in properties
    assert 'hips_service_url' not in properties
