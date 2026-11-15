from datetime import datetime, timezone
import math

from fastapi.testclient import TestClient
from whylab.app import create_app
from whylab.config import Settings
from whylab.solar_system import positions


def test_offline_ephemerides_and_earth_observer(tmp_path):
    with TestClient(create_app(Settings(output_dir=tmp_path))) as client:
        response = client.get('/api/solar-system')
    assert response.status_code == 200
    payload = response.json()
    assert payload['observer'] == 'Earth center'
    assert abs((datetime.now(timezone.utc)-datetime.fromisoformat(payload['observed_at'].replace('Z','+00:00'))).total_seconds()) < 120
    bodies = {b['id']: b for b in payload['bodies']}
    assert set(bodies) == {'sun','moon','mercury','venus','earth','mars','jupiter','saturn','uranus','neptune'}
    assert bodies['earth']['ra_deg'] is None
    for key, body in bodies.items():
        if key == 'earth': continue
        assert 0 <= body['ra_deg'] < 360 and -90 <= body['dec_deg'] <= 90
        assert math.isfinite(body['distance_au']) and body['distance_au'] > 0
    assert .002 < bodies['moon']['distance_au'] < .003
    assert .98 < bodies['sun']['distance_au'] < 1.02


def test_moving_bodies_are_recomputed_for_observation_time():
    first=positions(29_000_000)
    later=positions(29_001_440)
    assert first['observed_at'] != later['observed_at']
    assert first['bodies'][4]['ra_deg'] != later['bodies'][4]['ra_deg']


def test_3d_scene_is_heliocentric_with_earth_and_physical_orbital_distances(tmp_path):
    import numpy as np
    with TestClient(create_app(Settings(output_dir=tmp_path))) as client:
        response=client.get('/api/solar-system/scene')
    assert response.status_code==200
    payload=response.json();bodies={b['id']:b for b in payload['bodies']}
    assert payload['units']=='AU' and payload['step_days']==1
    assert len(bodies)==10
    assert np.all(np.array(bodies['sun']['samples_au'])==0)
    earth=np.array(bodies['earth']['samples_au'])
    assert earth.shape==(367,3) and np.isfinite(earth).all()
    assert .98<np.linalg.norm(earth[0])<1.02
    assert np.linalg.norm(earth[0]-earth[90])>1
    assert 29<np.linalg.norm(bodies['neptune']['samples_au'][0])<31
    moon=np.array(bodies['moon']['samples_au'])
    assert .002<np.linalg.norm(moon[0]-earth[0])<.003
    for body in bodies.values():
        assert np.isfinite(body['samples_au']).all()
        if body['id'] not in ('sun','moon'):
            orbit=np.array(body['orbit_au'])
            assert orbit.shape==(161,3) and np.isfinite(orbit).all()
            assert np.allclose(orbit[0],orbit[-1])
