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
