"""Sustained use and cache recovery without restarting the application."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading

from fastapi.testclient import TestClient

from whylab.app import create_app
from whylab.config import Settings
from whylab.models import ProcessedSequence, Preview
from whylab.fits_preview.routes import ArtifactCache, ProductRegistry
from test_backend import Archive, Sequence, Motion, SKY, PNG, wait
from test_fits_preview import fixture


def test_search_reuse_and_old_unpinned_sessions_do_not_fill_workspace(tmp_path):
    archive = Archive()
    calls = []
    original = archive.search
    def search(query):
        calls.append(query.ra_deg)
        return original(query)
    archive.search = search
    with TestClient(create_app(Settings(output_dir=tmp_path,cache_size=2),archive,Sequence(),Motion())) as client:
        ids=[]
        for index in range(8):
            response=client.post('/api/v1/observations/search',json={**SKY,'ra_deg':12+index})
            assert response.status_code==200,response.text
            ids.append(response.json()['search_id'])
        response=client.post('/api/v1/observations/search',json={**SKY,'ra_deg':19})
        assert response.json()['search_id']==ids[-1]
        assert len(calls)==8


def test_repeat_sequence_reuses_job_and_generated_bytes(tmp_path):
    sequence=Sequence(); calls=[]; original=sequence.process
    def process(*args):
        calls.append(1);return original(*args)
    sequence.process=process
    with TestClient(create_app(Settings(output_dir=tmp_path,cache_size=2),Archive(),sequence,Motion())) as client:
        search=client.post('/api/v1/observations/search',json=SKY).json()['search_id']
        selection={**SKY,'search_id':search,'observation_ids':['1','2','3']}
        first=client.post('/api/v1/sequences',json=selection).json()['job_id']
        record=wait(client,first)
        assert record['status']=='succeeded'
        assert record['progress']['completed']==record['progress']['total']==3
        for _ in range(8):
            assert client.post('/api/v1/sequences',json=selection).json()['job_id']==first
        assert len(calls)==1
        assert len(list(tmp_path.glob('*.png')))==1
        identifiers=[]
        for _ in range(6):
            response=client.post('/api/v1/investigations',json={**selection,'sequence_job_id':first})
            assert response.status_code==201,response.text
            identifiers.append(response.json()['investigation_id'])
        assert len(set(identifiers))==1


def test_disposable_previews_rotate_but_saved_evidence_remains_available(tmp_path):
    class ChangingSequence(Sequence):
        count=0
        def process(self,observations,cutouts,sky):
            self.count+=1
            return ProcessedSequence(previews=[Preview(observation_id=o.id,png=PNG+str(self.count).encode()) for o in observations],
                processing_version='synthetic-test',processing_settings={},shared_display_settings={})
    with TestClient(create_app(Settings(output_dir=tmp_path,cache_size=2),Archive(),ChangingSequence(),Motion())) as client:
        saved_url=None
        for index in range(5):
            query={**SKY,'ra_deg':12+index}
            search=client.post('/api/v1/observations/search',json=query)
            assert search.status_code==200,search.text
            selection={**query,'search_id':search.json()['search_id'],'observation_ids':['1','2','3']}
            job=client.post('/api/v1/sequences',json=selection).json()['job_id']
            record=wait(client,job);assert record['status']=='succeeded',record
            url=record['result']['previews'][0]['preview_url']
            if index==0:
                saved_url=url
                assert client.post('/api/v1/investigations',json={**selection,'sequence_job_id':job}).status_code==201
            assert client.get(url).status_code==200
            assert client.get(saved_url).status_code==200
        assert len(list(tmp_path.glob('*.png')))<=2


def test_fits_cache_rotates_and_regenerates_without_changing_originals(tmp_path):
    for name in ['a','b']:fixture(tmp_path/(name+'.fits'))
    originals={name:(tmp_path/(name+'.fits')).read_bytes() for name in ['a','b']}
    registry=ProductRegistry(tmp_path,{name:{'path':name+'.fits'} for name in ['a','b']})
    with TestClient(create_app(Settings(output_dir=tmp_path/'outputs',cache_size=1),fits_registry=registry)) as client:
        for name in ['a','b','a','b']:
            response=client.get('/api/observations/'+name+'/preview')
            assert response.status_code==200,response.text
            assert response.content.startswith(b'\x89PNG')
        assert len(list((tmp_path/'outputs'/'fits').iterdir()))==1
    assert all((tmp_path/(name+'.fits')).read_bytes()==data for name,data in originals.items())


def test_preview_and_quality_share_one_fits_read(tmp_path,monkeypatch):
    import whylab.fits_preview.routes as routes
    fixture(tmp_path/'a.fits')
    cache=ArtifactCache(Settings(output_dir=tmp_path/'outputs'),ProductRegistry(tmp_path,{'a':{'path':'a.fits'}}))
    original=routes.read; calls=[]; entered=threading.Event();release=threading.Event()
    def read(path):
        calls.append(1);entered.set();assert release.wait(2);return original(path)
    monkeypatch.setattr(routes,'read',read)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(cache.payloads,'a');assert entered.wait(2)
        second=pool.submit(cache.payloads,'a');release.set()
        assert first.result()[1]==second.result()[1]
    assert len(calls)==1


def test_different_fits_products_do_not_wait_on_one_global_render_lock(tmp_path,monkeypatch):
    import whylab.fits_preview.routes as routes
    for name in ['a','b']:fixture(tmp_path/(name+'.fits'))
    cache=ArtifactCache(Settings(output_dir=tmp_path/'outputs'),ProductRegistry(tmp_path,{name:{'path':name+'.fits'} for name in ['a','b']}))
    original=routes.read; barrier=threading.Barrier(2)
    def read(path):
        barrier.wait(timeout=2);return original(path)
    monkeypatch.setattr(routes,'read',read)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(cache.payloads,['a','b']))
    assert all(result[1]['preview.png'].startswith(b'\x89PNG') for result in results)


def test_failed_fits_read_does_not_poison_later_requests(tmp_path,monkeypatch):
    import pytest
    import whylab.fits_preview.routes as routes
    fixture(tmp_path/'a.fits')
    cache=ArtifactCache(Settings(output_dir=tmp_path/'outputs'),ProductRegistry(tmp_path,{'a':{'path':'a.fits'}}))
    original=routes.read;calls=[]
    def read(path):
        calls.append(1)
        if len(calls)==1:raise OSError('Temporary read failure')
        return original(path)
    monkeypatch.setattr(routes,'read',read)
    with pytest.raises(OSError):cache.payloads('a')
    assert cache.inflight=={}
    assert cache.payloads('a')[1]['preview.png'].startswith(b'\x89PNG')


def test_cache_pruning_never_removes_raw_fits_or_unknown_user_files(tmp_path):
    from whylab.generated_cache import trim_directories
    source=tmp_path/('a'*64);source.mkdir();(source/'original.fits').write_bytes(b'original observation')
    generated=tmp_path/('b'*64);generated.mkdir();(generated/'preview.png').write_bytes(b'generated image')
    trim_directories(tmp_path,5,10,1)
    assert (source/'original.fits').read_bytes()==b'original observation'
    assert not generated.exists()


def test_cache_pruning_skips_a_temporarily_locked_windows_file(tmp_path,monkeypatch):
    import os
    from whylab.generated_cache import trim_directories
    locked=tmp_path/('a'*64);locked.mkdir();(locked/'preview.png').write_bytes(b'123456')
    other=tmp_path/('b'*64);other.mkdir();(other/'preview.png').write_bytes(b'123456')
    os.utime(locked,(1,1));os.utime(other,(2,2))
    original=Path.unlink
    def unlink(path,*args,**kwargs):
        if path.parent==locked:raise PermissionError('Image is open')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'unlink',unlink)
    trim_directories(tmp_path,5,12,2)
    assert (locked/'preview.png').is_file()
    assert not other.exists()


def test_processing_cache_reuses_results_bypasses_busy_renderer_and_heals_missing_asset(monkeypatch):
    import backend.main as main
    from backend.processing.result_cache import ResultCache
    monkeypatch.setattr(main,'RESULT_CACHE',ResultCache())
    original=main.run_investigation_pipeline; calls=[]
    def run(*args,**kwargs):
        calls.append(1);return original(*args,**kwargs)
    monkeypatch.setattr(main,'run_investigation_pipeline',run)
    first=main.investigate_sequence(preset_id='synthetic_asteroid_sequence',grid_size_px=64)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with main.PROCESSING_LOCK:
            second=pool.submit(main.investigate_sequence,preset_id='synthetic_asteroid_sequence',grid_size_px=64).result(timeout=2)
    assert first==second and len(calls)==1
    path=(main.PREVIEWS_DIR/first['frames'][0]['image_url'].split('/previews/',1)[1]).resolve()
    assert path.is_relative_to(main.PREVIEWS_DIR.resolve())
    path.unlink()  # Only the disposable image generated by this test.
    repaired=main.investigate_sequence(preset_id='synthetic_asteroid_sequence',grid_size_px=64)
    assert len(calls)==2
    assert repaired['frames'][0]['image_url']!=first['frames'][0]['image_url']
