"""Tests for backend/processing/motion.py.

Includes tests for:
- fit_constant_motion velocity and uncertainty estimation.
- predict_position forward astrometric projection.
- test_motion outcomes: 'motion_supported', 'stationary_plausible', 'insufficient_evidence' (Hard Rule 8).
- Output compliance with Person 4's FastAPI JSON specification.
"""

from __future__ import annotations

import math
from astropy.time import Time, TimeDelta
import numpy as np
import pytest

from backend.processing.alignment import make_common_grid
from backend.processing.io_fits import Observation
from backend.processing.motion import (
    fit_constant_motion,
    predict_position,
    scan_and_track_motion,
    test_motion,
)


def test_fit_constant_motion_and_predict():
    """Verify velocity fitting and forward position prediction on a moving trajectory.

    SYNTHETIC TEST DATA: Not real astronomical measurements.
    Simulating a near-Earth asteroid moving at 10 arcsec/hour along RA at Dec = 0.
    """
    times = ["2025-05-01T00:00:00", "2025-05-01T02:00:00", "2025-05-01T04:00:00"]
    speed_deg_per_hr = 10.0 / 3600.0

    measurements = [
        {
            "epoch_id": f"ep_{i}",
            "observed_at_utc": times[i],
            "ra_deg": 100.0 + i * 2.0 * speed_deg_per_hr,
            "dec_deg": 0.0,
            "uncertainty_arcsec": 0.2,
            "status": "ok",
        }
        for i in range(3)
    ]

    model = fit_constant_motion(measurements)

    assert model["ref_time_utc"] == "2025-05-01T00:00:00.000"
    assert np.isclose(model["vx_arcsec_per_hour"], 10.0, atol=1e-3)
    assert np.isclose(model["vy_arcsec_per_hour"], 0.0, atol=1e-3)
    assert np.isclose(model["total_speed_arcsec_per_hour"], 10.0, atol=1e-3)
    assert np.isclose(model["time_baseline_hours"], 4.0, atol=1e-5)

    # Predict position at t = 6 hours (2025-05-01T06:00:00)
    pred_ra, pred_dec = predict_position(model, "2025-05-01T06:00:00")
    expected_ra = 100.0 + 6.0 * speed_deg_per_hr
    assert np.isclose(pred_ra, expected_ra, atol=1e-5)
    assert np.isclose(pred_dec, 0.0, atol=1e-5)


def test_motion_supported():
    """Verify outcome is 'motion_supported' when reserved epoch follows constant motion."""
    # SYNTHETIC TEST DATA: Speed 15 arcsec/hour
    t0 = Time("2025-06-01T12:00:00", scale="utc")

    def _make_meas(hours: float, ep_id: str):
        t = t0 + TimeDelta(hours * 3600.0, format="sec")
        return {
            "epoch_id": ep_id,
            "observed_at_utc": t.isot,
            "ra_deg": 50.0 + (hours * 15.0 / 3600.0),
            "dec_deg": 10.0,
            "uncertainty_arcsec": 0.3,
            "status": "ok",
        }

    training = [_make_meas(0.0, "t1"), _make_meas(2.0, "t2"), _make_meas(4.0, "t3")]
    reserved = _make_meas(6.0, "res")

    result = test_motion(training, reserved, investigation_id="INV_ASTEROID_01")

    assert result["investigation_id"] == "INV_ASTEROID_01"
    assert result["outcome"] == "motion_supported"
    assert result["model_comparison"] is not None
    assert result["model_comparison"]["motion_residual_arcsec"] < 0.5
    assert result["model_comparison"]["stationary_residual_arcsec"] > 30.0  # Moved 90 arcsec
    assert len(result["predictions"]) == 4


def test_stationary_plausible():
    """Verify outcome is 'stationary_plausible' for a stationary star."""
    # SYNTHETIC TEST DATA: Fixed position with minor centroid noise (0.1")
    t0 = Time("2025-06-01T12:00:00", scale="utc")

    def _make_star(hours: float, ep_id: str):
        t = t0 + TimeDelta(hours * 3600.0, format="sec")
        return {
            "epoch_id": ep_id,
            "observed_at_utc": t.isot,
            "ra_deg": 120.00000,
            "dec_deg": -30.00000,
            "uncertainty_arcsec": 0.5,
            "status": "ok",
        }

    training = [_make_star(0.0, "s1"), _make_star(2.0, "s2")]
    # Reserved epoch has small 0.2" shift (well within 2*sigma = 1.0")
    t_res = t0 + TimeDelta(4.0 * 3600.0, format="sec")
    reserved = {
        "epoch_id": "s_res",
        "observed_at_utc": t_res.isot,
        "ra_deg": 120.00000 + (0.2 / 3600.0) / math.cos(math.radians(-30.0)),
        "dec_deg": -30.00000,
        "uncertainty_arcsec": 0.5,
        "status": "ok",
    }

    result = test_motion(training, reserved)

    assert result["outcome"] == "stationary_plausible"
    assert result["model_comparison"] is not None
    assert result["model_comparison"]["stationary_residual_arcsec"] < 1.0


def test_insufficient_evidence_erratic_motion():
    """Verify outcome is 'insufficient_evidence' when motion does not fit linear track (Hard Rule 8)."""
    # SYNTHETIC TEST DATA: Erratic jump
    t0 = Time("2025-06-01T12:00:00", scale="utc")
    t1 = t0 + TimeDelta(1.0 * 3600.0, format="sec")
    t2 = t0 + TimeDelta(2.0 * 3600.0, format="sec")

    training = [
        {"epoch_id": "e1", "observed_at_utc": t0.isot, "ra_deg": 10.0, "dec_deg": 0.0, "uncertainty_arcsec": 0.3, "status": "ok"},
        {"epoch_id": "e2", "observed_at_utc": t1.isot, "ra_deg": 10.001, "dec_deg": 0.0, "uncertainty_arcsec": 0.3, "status": "ok"},
    ]
    # Reserved epoch jumps wildly away from linear trajectory
    reserved = {
        "epoch_id": "e_res",
        "observed_at_utc": t2.isot,
        "ra_deg": 10.05,
        "dec_deg": 0.05,
        "uncertainty_arcsec": 0.3,
        "status": "ok",
    }

    result = test_motion(training, reserved)

    assert result["outcome"] == "insufficient_evidence"
    assert result["model_comparison"] is not None
    assert "insufficient evidence" in result["model_comparison"]["decision_criterion"].lower()


def test_insufficient_evidence_fewer_than_2_training_epochs():
    """Verify outcome is 'insufficient_evidence' if only 1 training epoch is provided."""
    training = [
        {"epoch_id": "e1", "observed_at_utc": "2025-01-01T00:00:00", "ra_deg": 10.0, "dec_deg": 0.0, "status": "ok"}
    ]
    reserved = {
        "epoch_id": "e_res", "observed_at_utc": "2025-01-01T01:00:00", "ra_deg": 10.001, "dec_deg": 0.0, "status": "ok"
    }

    result = test_motion(training, reserved)
    assert result["outcome"] == "insufficient_evidence"
    assert result["model_comparison"] is None
    assert any("Insufficient valid training epochs" in w for w in result["warnings"])


def test_insufficient_evidence_masked_reserved_epoch():
    """Verify outcome is 'insufficient_evidence' if reserved epoch is masked or failed."""
    training = [
        {"epoch_id": "e1", "observed_at_utc": "2025-01-01T00:00:00", "ra_deg": 10.0, "dec_deg": 0.0, "status": "ok"},
        {"epoch_id": "e2", "observed_at_utc": "2025-01-01T01:00:00", "ra_deg": 10.001, "dec_deg": 0.0, "status": "ok"},
    ]
    reserved = {
        "epoch_id": "e_res", "observed_at_utc": "2025-01-01T02:00:00", "ra_deg": 10.002, "dec_deg": 0.0, "status": "masked"
    }

    result = test_motion(training, reserved)
    assert result["outcome"] == "insufficient_evidence"
    assert result["model_comparison"] is None
    assert any("Reserved epoch status is 'masked'" in w for w in result["warnings"])


def test_scan_and_track_motion():
    """Verify scan_and_track_motion detects hotspots and categorizes stationary vs moving objects."""
    # SYNTHETIC TEST DATA
    wcs = make_common_grid(ra_deg=100.0, dec_deg=0.0, fov_arcmin=2.0, size_px=50)

    # 3 epochs, 1 hour apart
    # Object 1 (Stationary Star) stays at (15, 15)
    # Object 2 (Moving Asteroid) moves from (30, 20) to (30, 25) to (30, 30) (5 px/hr ~ 12.5 arcsec/hr)
    epochs_obs = []
    times = ["2025-05-01T00:00:00", "2025-05-01T01:00:00", "2025-05-01T02:00:00"]
    y_moving = [20, 25, 30]

    for ep_idx, (t_str, ym) in enumerate(zip(times, y_moving)):
        img = np.full((50, 50), 0.1, dtype=np.float64)
        # Stationary star
        img[15, 15] = 12.0
        # Moving asteroid
        img[ym, 30] = 8.0

        obs = Observation(
            image=img,
            flags=None,
            variance=None,
            wcs=wcs,
            observed_at_utc=t_str,
            detector=1,
            wavelength_um=1.0,
            warnings=[],
        )
        epochs_obs.append(obs)

    result = scan_and_track_motion(epochs_obs, snr_threshold=3.0, match_radius_arcsec=6.0)

    assert result["num_epochs"] == 3
    assert result["total_hotspots"] >= 2

    # Check classifications
    classifications = [h["classification"] for h in result["hotspots"]]
    assert "stationary_star" in classifications
    assert "moving_candidate" in classifications

