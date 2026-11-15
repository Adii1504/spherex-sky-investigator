"""Local search must respect real coverage and complete the normal investigation flow."""
import hashlib
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from whylab.app import create_app
from whylab.config import Settings
from whylab.dataset import import_dataset
from whylab.fits_preview.routes import ProductRegistry
from whylab.local_archive import LocalArchive
from whylab.models import Search, Sky
from teammate_integration import SPHERExSequenceAdapter, SPHERExMotionAdapter
from test_fits_preview import fixture


class OfflineArchive:
    available = True

    def search(self, query):
        raise AssertionError('Local search must not contact the archive')

    def cutout(self, observation, sky):
        raise AssertionError('Local processing must not contact the archive')


def test_local_coverage_dates_identity_and_checksum(tmp_path):
    path = tmp_path/'sample.fits'
    fixture(path)
    registry = ProductRegistry(tmp_path, {'sample':{'path':'sample.fits',
        'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}})
    archive = LocalArchive(registry, Settings())
    query = Search(ra_deg=120,dec_deg=20,fov_arcmin=2)
    result = archive.search(query)
    assert len(result.observations) == 1
    assert not result.coverage_summary['complete']
    assert not result.coverage_summary['archive_contacted']
    assert result.observations[0].exposure_id == 'local:unknown-exposure'
    assert not archive.search(query.model_copy(update={'ra_deg':0})).observations
    later = Search(ra_deg=120,dec_deg=20,fov_arcmin=2,start_utc='2026-01-01T00:00:00Z')
    assert not archive.search(later).observations
    assert archive.cutout(result.observations[0], Sky(ra_deg=120,dec_deg=20,fov_arcmin=2)).data == path.read_bytes()
    path.write_bytes(path.read_bytes()+b'changed')
    with pytest.raises(ValueError, match='checksum'):
        archive.cutout(result.observations[0], query)


def test_real_downloaded_search_sequence_save_and_evidence_without_network(tmp_path):
    import_dataset(Path('PythonProject/final_dataset'), tmp_path)
    registry = ProductRegistry.load(tmp_path)
    entry = next(e for e in registry.entries.values() if e['target_id']=='wise-0855')
    position = entry['predicted_position']
    query = dict(ra_deg=position['ra_deg'],dec_deg=position['dec_deg'],fov_arcmin=2)
    settings = Settings(output_dir=tmp_path/'previews', preview_pixels=64, workers=1)
    with TestClient(create_app(settings, archive=OfflineArchive(),
            sequence=SPHERExSequenceAdapter(settings), motion=SPHERExMotionAdapter(settings),
            fits_registry=registry)) as client:
        response = client.post('/api/v1/observations/search/local',json=query)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['observations']
        assert result['coverage_summary']['source']=='imported-local'
        assert all(o['release']=='imported-local' for o in result['observations'])
        selection = {**query,'search_id':result['search_id'],
            'observation_ids':[o['id'] for o in result['observations']]}
        response = client.post('/api/v1/sequences',json=selection)
        assert response.status_code == 202, response.text
        job_id = response.json()['job_id']
        for _ in range(500):
            record = client.get('/api/v1/jobs/'+job_id).json()
            if record['status'] in ('failed','succeeded'): break
            time.sleep(.02)
        assert record['status']=='succeeded', record
        assert len(record['result']['previews']) == len(selection['observation_ids'])
        response = client.post('/api/v1/investigations',json={**selection,'sequence_job_id':job_id})
        assert response.status_code == 201, response.text
        evidence = client.get('/api/v1/investigations/'+response.json()['investigation_id']+'/evidence')
        assert evidence.status_code == 200
        assert evidence.json()['observations'][0]['release']=='imported-local'
        assert str(tmp_path) not in evidence.text
        unique = list({o['exposure_id']:o['id'] for o in result['observations']}.values())
        assert len(unique) >= 4
        response = client.post('/api/v1/investigations/'+response.json()['investigation_id']+'/verify',
            json={'training_observation_ids':unique[:3], 'reserved_observation_ids':unique[3:4]})
        assert response.status_code == 202, response.text
        for _ in range(500):
            verification = client.get('/api/v1/jobs/'+response.json()['job_id']).json()
            if verification['status'] in ('failed','succeeded'): break
            time.sleep(.02)
        assert verification['status']=='succeeded', verification
        assert verification['result']['outcome'] in ('supported','not_supported','insufficient_evidence')


def test_no_coverage_offers_real_image_fields_without_replacing_query(tmp_path):
    import_dataset(Path('PythonProject/final_dataset'), tmp_path)
    archive = LocalArchive(ProductRegistry.load(tmp_path), Settings())
    query = Search(ra_deg=133.81890825,dec_deg=-7.247048,fov_arcmin=2)
    result = archive.search(query)
    assert not result.observations
    fields = result.coverage_summary['available_fields']
    assert len(fields)==5
    for field in fields:
        assert archive.search(Search(**{k:field[k] for k in ['ra_deg','dec_deg','fov_arcmin']})).observations
    assert query.ra_deg == 133.81890825


def test_archive_reconciliation_preserves_local_ids_and_deduplicates_exact_product(tmp_path):
    from whylab.local_archive import align_results
    from whylab.models import Observation, Provenance, SearchResult
    filename = 'level2_2026W36_1A_0510_1D1_spx_l2b-v27-2026-252.fits'
    local = Observation(id='local-file',product_id='local-file',exposure_id='spherex:exposure',
        release='imported-local', observed_at='2026-09-02T00:00:00Z',
        provenance=Provenance(archive='local',source_url='/api/observations/local-file/fits'),
        quality={'label':'Barnards_Star_'+filename,'sha256':'unchanged'})
    same = local.model_copy(update={'id':'remote-same','product_id':filename,'release':'spherex_dr1',
        'quality':{},'provenance':Provenance(archive='IRSA',source_url='https://irsa.ipac.caltech.edu/ibe/data/spherex/'+filename)})
    newer = same.model_copy(update={'id':'remote-version','product_id':filename.replace('v27','v28')})
    before = SearchResult(observations=[local],coverage_summary={'source':'imported-local','complete':False})
    duplicate = same.model_copy(update={'id':'remote-other-collection','release':'spherex_qr3'})
    remote = SearchResult(observations=[same,duplicate,newer],coverage_summary={'complete':True})
    result = align_results(before,remote,100)
    assert [o.id for o in result.observations] == ['local-file','remote-version']
    assert result.observations[0].quality['sha256']=='unchanged'
    assert result.observations[0].quality['archive_match']['product_id']==filename
    assert result.coverage_summary['archive_matches']==1
    assert 'archive_match' not in before.observations[0].quality
    again = align_results(result, remote, 100)
    assert [o.id for o in again.observations] == ['local-file','remote-version']
    assert again.coverage_summary['archive_matches']==1
    assert len(align_results(before,remote,1).observations)==1
    assert not align_results(before,remote,1).coverage_summary['complete']


def test_sync_failure_keeps_local_search_and_success_reuses_same_session(tmp_path):
    from whylab.models import SearchResult
    path = tmp_path/'sample.fits'; fixture(path)
    registry = ProductRegistry(tmp_path, {'sample':{'path':'sample.fits',
        'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}})
    class RecoveringArchive:
        available = True
        fail = True
        def search(self, query):
            if self.fail: raise TimeoutError('test archive unavailable')
            return SearchResult(observations=[], coverage_summary={'complete':True})
    remote = RecoveringArchive()
    with TestClient(create_app(Settings(output_dir=tmp_path/'previews'),archive=remote,fits_registry=registry)) as client:
        local = client.post('/api/v1/observations/search/local',json={'ra_deg':120,'dec_deg':20,'fov_arcmin':2}).json()
        search_id = local['search_id']
        response = client.post(f'/api/v1/observations/search/{search_id}/sync')
        assert response.status_code==503
        selection={'ra_deg':120,'dec_deg':20,'fov_arcmin':2,'search_id':search_id,'observation_ids':['sample']}
        assert client.post('/api/v1/investigations',json=selection).status_code==201
        remote.fail = False
        response = client.post(f'/api/v1/observations/search/{search_id}/sync')
        assert response.status_code==200, response.text
        assert response.json()['search_id']==search_id
        assert response.json()['observations'][0]['id']=='sample'
        assert response.json()['coverage_summary']['source']=='local-and-archive'


def test_slow_archive_sync_does_not_block_local_processing_worker(tmp_path):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    started, release, processed = threading.Event(), threading.Event(), threading.Event()
    path = tmp_path/'sample.fits'; fixture(path)
    registry = ProductRegistry(tmp_path, {'sample':{'path':'sample.fits',
        'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}})
    class SlowArchive:
        available = True
        def search(self, query):
            started.set(); release.wait(5)
            raise TimeoutError('synthetic archive unavailable')
    class ProbeSequence:
        available = True
        def process(self, *args):
            processed.set()
            raise ValueError('Synthetic test ends after entering processing')
    settings = Settings(output_dir=tmp_path/'previews',workers=1)
    with TestClient(create_app(settings,archive=SlowArchive(),sequence=ProbeSequence(),fits_registry=registry)) as client:
        query={'ra_deg':120,'dec_deg':20,'fov_arcmin':2}
        local=client.post('/api/v1/observations/search/local',json=query).json()
        with ThreadPoolExecutor(max_workers=1) as requests:
            pending=requests.submit(client.post,f"/api/v1/observations/search/{local['search_id']}/sync")
            try:
                assert started.wait(2)
                assert client.post('/api/v1/sequences',json={**query,'search_id':local['search_id'],
                    'observation_ids':['sample']}).status_code==202
                assert processed.wait(2), 'Background sync blocked the only processing worker'
            finally:
                release.set()
            assert pending.result().status_code==503
