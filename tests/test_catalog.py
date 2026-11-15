import json
from urllib.parse import parse_qs, urlsplit
from fastapi.testclient import TestClient
from whylab.app import create_app
from whylab.config import Settings
from whylab.catalog import Simbad, CatalogBusy


def response():
    return json.dumps({'metadata':[{'name':n} for n in ['main_id','ra','dec','otype','coo_bibcode']],
                       'data':[['M  31',10.6847,41.2688,'G','reference']]}).encode()


def test_bounded_templates_escaping_caching_and_no_distance_inference():
    service = Simbad(Settings())
    urls = []
    service.retriever.get = lambda url: urls.append(url) or response()
    result = service.search("Barnard's star")
    query = parse_qs(urlsplit(urls[0]).query)['query'][0]
    assert "TOP 50" in query and "Barnard''s star" in query
    assert result['targets'][0]['distance'] is None
    assert result['targets'][0]['source_identifier'] == 'M  31'
    assert service.search("Barnard's star")['cached'] is True
    assert len(urls) == 1
    service.search(ra=0.,dec=90.,radius=.1)
    assert "CIRCLE('ICRS',0.0000000000,90.0000000000,0.1000000000)" in parse_qs(urlsplit(urls[-1]).query)['query'][0]
    for i in range(18):
        service.search(f'object-{i}')
    import pytest
    with pytest.raises(CatalogBusy):
        service.search('request-over-limit')


def test_validation_and_provider_failure_preserve_other_endpoints(tmp_path):
    with TestClient(create_app(Settings(output_dir=tmp_path/'out'))) as client:
        for query in ['ra=nan&dec=0','ra=360&dec=0','ra=0&dec=0&radius=1','name=x&ra=1&dec=1','ra=0','name=%20','adql=SELECT']:
            assert client.get('/api/catalog/search?'+query).status_code == 422
        client.app.state.catalog.retriever.get = lambda url: (_ for _ in ()).throw(TimeoutError())
        error = client.get('/api/catalog/search?name=M31')
        assert error.status_code == 502
        assert error.json()['code'] == 'catalog_unavailable'
        assert len(client.get('/api/targets').json()['targets']) == 5
        assert client.get('/api/v1/health').status_code == 200


def test_local_unassociated_product_does_not_create_a_target(tmp_path):
    from whylab.fits_preview.routes import ProductRegistry
    registry=ProductRegistry(tmp_path, {'sample':{'path':'missing.fits','footprint_stcs':'POLYGON ICRS 0 0 1 0 0 1'}})
    with TestClient(create_app(Settings(output_dir=tmp_path/'out'),fits_registry=registry)) as client:
        item=client.get('/api/local-products').json()['observations'][0]
        assert item['target_id'] is None and item['predicted_position'] is None
        assert item['available'] is False and 'path' not in item
        assert client.get('/api/targets/barnards-star/observations').json()['observations'] == []
