import json
from fastapi.testclient import TestClient
from whylab.app import create_app
from whylab.config import Settings
from whylab.fits_preview.routes import ProductRegistry
from whylab.targets import load_targets
from test_fits_preview import fixture, position


def test_all_five_targets_and_product_associations(tmp_path):
    targets = load_targets()
    fixture_path = tmp_path/'synthetic.fits'
    w = fixture(fixture_path)
    entries = {f'test-{i}': {'path': 'synthetic.fits', 'target_id': t['id'],
        'predicted_position': position(w), 'provisional': True,
        'observation': {'observed_at': '2025-01-01T00:00:00Z', 'detector': 'test',
                        'file_wavelength_um': [1., 2.]}}
        for i, t in enumerate(targets)}
    entries['test-0']['evidence'] = [{'url': 'file:///private', 'label': 'never expose'}]
    with TestClient(create_app(Settings(output_dir=tmp_path/'outputs'),
                              fits_registry=ProductRegistry(tmp_path, entries))) as client:
        assert len(client.get('/api/targets').json()['targets']) == 5
        for i, t in enumerate(targets):
            assert client.get('/api/targets/'+t['id']).json()['reference_epoch'] == 'J2000'
            response = client.get('/api/targets/'+t['id']+'/observations')
            assert response.status_code == 200
            item = response.json()['observations'][0]
            assert item['product_id'] == f'test-{i}'
            assert item['provisional']
            assert item['predicted_position']['astrometry_status'] == 'provisional'
            assert 'path' not in item
            assert client.get(item['preview_url']).headers['content-type'] == 'image/png'
            q = client.get(item['quality_url']).json()
            assert q['product_id'] == item['product_id']
            assert q['position'] == item['predicted_position']
        assert client.get('/api/targets/not-a-target').status_code == 404
        assert client.get('/api/targets/not-a-target/observations').status_code == 404
        assert client.get('/api/targets/'+targets[0]['id']+'/observations').json()['observations'][0]['evidence'] == []


def test_no_linked_products_is_explicit_unavailable(tmp_path):
    with TestClient(create_app(Settings(output_dir=tmp_path/'outputs'), fits_registry=ProductRegistry(tmp_path))) as client:
        result = client.get('/api/targets/barnards-star/observations').json()
        assert result['status'] == 'unavailable'
        assert result['observations'] == []


def test_missing_file_and_prediction_do_not_invent_positions(tmp_path):
    registry = ProductRegistry(tmp_path, {'missing': {'path': 'missing.fits', 'target_id': 'wise-0855'}})
    with TestClient(create_app(Settings(output_dir=tmp_path/'outputs'), fits_registry=registry)) as client:
        item = client.get('/api/targets/wise-0855/observations').json()['observations'][0]
        assert item['predicted_position'] is None
        assert item['preview_url'] is None
        assert item['astrometry_status'] == 'unavailable'
