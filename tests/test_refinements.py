"""Regressions for boundary cases discovered during the application audit."""
import numpy as np
import pytest
from astropy.time import Time, TimeDelta
from fastapi.testclient import TestClient

from backend.processing.alignment import make_common_grid
from backend.processing.compatibility import check_wavelength_compatibility
from backend.processing.io_fits import create_observation_from_array
from backend.processing.measure import measure_position
from backend.processing.motion import fit_constant_motion, predict_position, test_motion as evaluate_motion
from whylab.app import create_app
from whylab.config import Settings


@pytest.mark.parametrize("x,y", [(15.4,8),(8,15.4),(-.2,8),(8,-.2),(15.8,8),(8,15.8)])
def test_measurement_at_pixel_boundaries_never_indexes_outside_image(x,y):
    wcs = make_common_grid(120,20,2,16)
    image = np.random.default_rng(31).normal(size=(16,16))
    ra,dec = wcs.pixel_to_world_values(x,y)
    result = measure_position(image,np.ones_like(image,dtype=bool),wcs,float(ra),float(dec))
    assert result["status"] in ("ok","low_snr","masked","failed")
    if x > 15.5 or y > 15.5:
        assert result["status"] == "failed"


@pytest.mark.parametrize("value", [float("nan"),float("inf"),0.,-1.])
def test_invalid_wavelength_is_unknown_and_json_safe(value):
    wcs = make_common_grid(120,20,2,16)
    frame = create_observation_from_array(np.ones((16,16)),wcs,wavelength_um=value)
    result = check_wavelength_compatibility([frame,frame])
    assert result["status"] == "unknown"
    assert result["wavelengths_um"] == [None,None]


def test_wavelength_map_does_not_substitute_another_position():
    wcs = make_common_grid(120,20,2,16)
    frame = create_observation_from_array(np.ones((16,16)),wcs,wavelength_um=np.ones((16,16)))
    ra,dec = wcs.pixel_to_world_values(100,100)
    result = check_wavelength_compatibility([frame],target_coord=(float(ra),float(dec)))
    assert result["status"] == "unknown"


def record(index, ra=120., time=None):
    return {"epoch_id":str(index), "ra_deg":ra, "dec_deg":0.,
        "observed_at_utc":time or (Time("2025-01-01")+TimeDelta(index*3600,format="sec")).isot,
        "uncertainty_arcsec":.1,"status":"ok"}


def test_single_epoch_cannot_support_a_motion_or_stationary_verdict():
    rows = [record(i,time="2025-01-01T00:00:00") for i in range(3)]
    assert evaluate_motion(rows[:2],rows[2])["outcome"] == "insufficient_evidence"
    model = fit_constant_motion(rows[:2])
    assert model["total_speed_arcsec_per_hour"] is None
    with pytest.raises(ValueError):
        predict_position(model,"2025-01-02T00:00:00")


def test_invalid_reserved_time_and_reused_identity_are_insufficient():
    training = [record(0),record(1)]
    for reserved in [record(2,time="not-a-time"),{**record(2),"observed_at_utc":None},
                     {**record(2),"epoch_id":"0"}]:
        assert evaluate_motion(training,reserved)["outcome"] == "insufficient_evidence"


def test_motion_fit_crosses_ra_zero_without_a_full_circle_jump():
    training = [record(0,359.999),record(1,.001)]
    model = fit_constant_motion(training)
    assert model["total_speed_arcsec_per_hour"] == pytest.approx(7.2)
    ra,dec = predict_position(model,record(2)["observed_at_utc"])
    assert ra == pytest.approx(.003,abs=1e-9)
    assert dec == 0.


def test_motion_prediction_uses_the_fitted_intercept():
    rows = [record(i,120.+offset/3600) for i,offset in enumerate([0,3,1])]
    model = fit_constant_motion(rows)
    ra,_ = predict_position(model,rows[0]["observed_at_utc"])
    expected = np.polyfit([0,1,2],[0,3,1],1)[1]
    assert (ra-120.)*3600 == pytest.approx(expected,abs=1e-7)


def test_empty_processing_request_requires_an_explicit_dataset(tmp_path):
    with TestClient(create_app(Settings(output_dir=tmp_path/"outputs"))) as client:
        response = client.post("/processing/api/investigate")
        assert response.status_code == 422
        assert "Choose a dataset" in response.json()["detail"]
