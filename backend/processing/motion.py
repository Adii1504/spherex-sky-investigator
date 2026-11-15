"""Constant-motion fitting, position prediction, and hypothesis verification for SPHEREx WhyLab.

Fits linear constant proper motion across multiple epochs in celestial coordinates,
predicts positions at arbitrary UTC timestamps, and evaluates whether a suspected
moving source is consistent with real motion vs a stationary source on a reserved
evaluation epoch.

Adheres strictly to Hackathon Hard Rules:
- No full orbital mechanics or ML classification (Hard Rule 9).
- Missing values are None (Hard Rule 3).
- Must return 'insufficient_evidence' when data is ambiguous (Hard Rule 8).
- Output matches Person 4's FastAPI JSON specification.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Sequence

from astropy.coordinates import SkyCoord
import astropy.units as u
from astropy.time import Time, TimeDelta
import numpy as np

from backend.processing.io_fits import Observation, build_valid_mask
from backend.processing.measure import detect_sources


@dataclass
class MeasurementRecord:
    """Standardized measurement record for motion testing."""

    observed_at_utc: str
    ra_deg: float
    dec_deg: float
    uncertainty_arcsec: float | None = None
    snr: float | None = None
    status: str = "ok"
    epoch_id: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any], default_epoch_id: str = "epoch") -> MeasurementRecord:
        return cls(
            observed_at_utc=str(d.get("observed_at_utc", d.get("observed_at")) or ""),
            ra_deg=float(d["ra_deg"]),
            dec_deg=float(d["dec_deg"]),
            uncertainty_arcsec=float(d["uncertainty_arcsec"]) if d.get("uncertainty_arcsec") is not None else None,
            snr=float(d["snr"]) if d.get("snr") is not None else None,
            status=str(d.get("status", "ok")),
            epoch_id=str(d.get("epoch_id") or d.get("observation_id") or default_epoch_id),
        )


def _usable(record):
    if (record.status != "ok" or not record.observed_at_utc
            or not math.isfinite(record.ra_deg) or not math.isfinite(record.dec_deg)
            or not 0 <= record.ra_deg < 360 or not -90 <= record.dec_deg <= 90):
        return False
    try:
        return math.isfinite(float(Time(record.observed_at_utc, scale="utc").mjd))
    except (ValueError, TypeError):
        return False


def _sky_separation_arcsec(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """Compute great-circle angular separation in arcseconds."""
    c1 = SkyCoord(ra=ra1 * u.deg, dec=dec1 * u.deg, frame="icrs")
    c2 = SkyCoord(ra=ra2 * u.deg, dec=dec2 * u.deg, frame="icrs")
    return float(c1.separation(c2).to_value("arcsec"))


def fit_constant_motion(
    measurements: Sequence[dict[str, Any] | MeasurementRecord],
) -> dict[str, Any]:
    """Fit a 2D linear constant-motion model across observation epochs.

    Parameterizes motion in local tangent plane relative to the initial epoch:
        Delta_x = (RA - RA0) * cos(Dec0) * 3600 = vx * dt
        Delta_y = (Dec - Dec0) * 3600 = vy * dt
    where dt is in hours, and velocities are in arcsec/hour.

    Args:
        measurements: Sequence of measurement dicts or MeasurementRecords.

    Returns:
        dict[str, Any]:
            {
                "ref_time_utc": str | None,
                "ref_ra_deg": float | None,
                "ref_dec_deg": float | None,
                "vx_arcsec_per_hour": float | None,
                "vy_arcsec_per_hour": float | None,
                "total_speed_arcsec_per_hour": float | None,
                "vx_uncertainty": float | None,
                "vy_uncertainty": float | None,
                "speed_uncertainty": float | None,
                "time_baseline_hours": float | None,
                "num_epochs": int,
                "warnings": list[str]
            }
    """
    warnings: list[str] = []

    records: list[MeasurementRecord] = [
        m if isinstance(m, MeasurementRecord) else MeasurementRecord.from_dict(m, f"epoch_{i}")
        for i, m in enumerate(measurements)
    ]

    valid = [r for r in records if _usable(r)]
    if len(valid) < 2:
        warnings.append(
            f"Need at least 2 epochs with status 'ok' to fit motion (received {len(valid)})."
        )
        return {
            "ref_time_utc": None,
            "ref_ra_deg": None,
            "ref_dec_deg": None,
            "vx_arcsec_per_hour": None,
            "vy_arcsec_per_hour": None,
            "total_speed_arcsec_per_hour": None,
            "vx_uncertainty": None,
            "vy_uncertainty": None,
            "speed_uncertainty": None,
            "time_baseline_hours": None,
            "num_epochs": len(valid),
            "warnings": warnings,
        }

    # Sort valid measurements chronologically
    try:
        times = [Time(r.observed_at_utc, scale="utc") for r in valid]
    except Exception as e:
        warnings.append(f"Failed to parse observation timestamps: {e}")
        return {
            "ref_time_utc": None,
            "ref_ra_deg": None,
            "ref_dec_deg": None,
            "vx_arcsec_per_hour": None,
            "vy_arcsec_per_hour": None,
            "total_speed_arcsec_per_hour": None,
            "vx_uncertainty": None,
            "vy_uncertainty": None,
            "speed_uncertainty": None,
            "time_baseline_hours": None,
            "num_epochs": len(valid),
            "warnings": warnings,
        }

    sort_indices = np.argsort([t.mjd for t in times])
    valid = [valid[i] for i in sort_indices]
    times = [times[i] for i in sort_indices]

    t0 = times[0]
    dt_hours = np.array([(t - t0).to_value("hour") for t in times], dtype=np.float64)
    baseline_hours = float(dt_hours[-1] - dt_hours[0])

    if baseline_hours <= 1e-6:
        warnings.append("Time baseline across epochs is zero; cannot determine velocity.")
        return {
            "ref_time_utc": None,
            "ref_ra_deg": valid[0].ra_deg,
            "ref_dec_deg": valid[0].dec_deg,
            "vx_arcsec_per_hour": None,
            "vy_arcsec_per_hour": None,
            "total_speed_arcsec_per_hour": None,
            "vx_uncertainty": None,
            "vy_uncertainty": None,
            "speed_uncertainty": None,
            "time_baseline_hours": 0.0,
            "num_epochs": len(valid),
            "warnings": warnings,
        }

    # Reference coordinate at t0
    ref_ra = valid[0].ra_deg
    ref_dec = valid[0].dec_deg
    cos_dec0 = math.cos(math.radians(ref_dec))

    # Convert angular positions to tangent plane offsets in arcseconds
    dx_arcsec = np.array([
        ((r.ra_deg - ref_ra + 180.0) % 360.0 - 180.0) * cos_dec0 * 3600.0 for r in valid
    ], dtype=np.float64)
    dy_arcsec = np.array([
        (r.dec_deg - ref_dec) * 3600.0 for r in valid
    ], dtype=np.float64)

    # Weights from uncertainties if provided and positive
    uncertainties = [r.uncertainty_arcsec for r in valid]
    has_uncert = all(u is not None and u > 0 for u in uncertainties)
    n_points = len(valid)

    # When N == 2, degrees of freedom is 0; covariance cannot be estimated reliably (Hard Rule 3)
    if n_points > 2 and has_uncert:
        w = 1.0 / np.array(uncertainties, dtype=np.float64)
        try:
            p_x, cov_x = np.polyfit(dt_hours, dx_arcsec, deg=1, w=w, cov=True)
            p_y, cov_y = np.polyfit(dt_hours, dy_arcsec, deg=1, w=w, cov=True)
            vx = float(p_x[0])
            vy = float(p_y[0])
            sigma_vx = float(np.sqrt(cov_x[0, 0])) if cov_x is not None and cov_x[0, 0] > 0 else None
            sigma_vy = float(np.sqrt(cov_y[0, 0])) if cov_y is not None and cov_y[0, 0] > 0 else None
        except Exception:
            p_x = np.polyfit(dt_hours, dx_arcsec, deg=1, w=w)
            p_y = np.polyfit(dt_hours, dy_arcsec, deg=1, w=w)
            vx = float(p_x[0])
            vy = float(p_y[0])
            sigma_vx, sigma_vy = None, None
    elif n_points > 2:
        try:
            p_x, cov_x = np.polyfit(dt_hours, dx_arcsec, deg=1, cov=True)
            p_y, cov_y = np.polyfit(dt_hours, dy_arcsec, deg=1, cov=True)
            vx = float(p_x[0])
            vy = float(p_y[0])
            sigma_vx = float(np.sqrt(cov_x[0, 0])) if cov_x is not None and cov_x[0, 0] > 0 else None
            sigma_vy = float(np.sqrt(cov_y[0, 0])) if cov_y is not None and cov_y[0, 0] > 0 else None
        except Exception:
            p_x = np.polyfit(dt_hours, dx_arcsec, deg=1)
            p_y = np.polyfit(dt_hours, dy_arcsec, deg=1)
            vx = float(p_x[0])
            vy = float(p_y[0])
            sigma_vx, sigma_vy = None, None
    else:
        # N == 2: exact 2-point line fit, uncertainty is None
        p_x = np.polyfit(dt_hours, dx_arcsec, deg=1)
        p_y = np.polyfit(dt_hours, dy_arcsec, deg=1)
        vx = float(p_x[0])
        vy = float(p_y[0])
        sigma_vx, sigma_vy = None, None

    # polyfit estimates both velocity and intercept; the reference position
    # must use that intercept rather than anchoring to one noisy measurement.
    fitted_ra = (ref_ra + float(p_x[1]) / (cos_dec0 * 3600.0)) % 360.0
    fitted_dec = ref_dec + float(p_y[1]) / 3600.0
    v_total = float(math.hypot(vx, vy))

    # Error propagation for total speed
    if sigma_vx is not None and sigma_vy is not None and v_total > 0:
        sigma_v = float(math.sqrt((vx * sigma_vx) ** 2 + (vy * sigma_vy) ** 2) / v_total)
    else:
        sigma_v = None

    return {
        "ref_time_utc": t0.isot,
        "ref_ra_deg": fitted_ra,
        "ref_dec_deg": fitted_dec,
        "tangent_dec_deg": float(ref_dec),
        "vx_arcsec_per_hour": vx,
        "vy_arcsec_per_hour": vy,
        "total_speed_arcsec_per_hour": v_total,
        "vx_uncertainty": sigma_vx,
        "vy_uncertainty": sigma_vy,
        "speed_uncertainty": sigma_v,
        "time_baseline_hours": baseline_hours,
        "num_epochs": len(valid),
        "warnings": warnings,
    }


def predict_position(
    model: dict[str, Any],
    time_utc: str,
) -> tuple[float, float]:
    """Predict celestial coordinates (RA, Dec in degrees) at a given UTC timestamp.

    Args:
        model: Constant-motion model dictionary returned by fit_constant_motion.
        time_utc: Target ISO-8601 UTC timestamp.

    Returns:
        tuple[float, float]: (predicted_ra_deg, predicted_dec_deg).

    Raises:
        ValueError: If model is incomplete or missing reference coordinates.
    """
    ref_time_str = model.get("ref_time_utc")
    ref_ra = model.get("ref_ra_deg")
    ref_dec = model.get("ref_dec_deg")
    vx = model.get("vx_arcsec_per_hour")
    vy = model.get("vy_arcsec_per_hour")

    if None in (ref_time_str, ref_ra, ref_dec, vx, vy):
        raise ValueError("Incomplete motion model provided to predict_position.")

    t_ref = Time(ref_time_str, scale="utc")
    t_target = Time(time_utc, scale="utc")
    dt_hours = (t_target - t_ref).to_value("hour")

    dx_arcsec = float(vx) * dt_hours
    dy_arcsec = float(vy) * dt_hours

    cos_dec0 = math.cos(math.radians(float(model.get("tangent_dec_deg", ref_dec))))
    if abs(cos_dec0) < 1e-7:
        cos_dec0 = 1e-7

    d_ra_deg = (dx_arcsec / 3600.0) / cos_dec0
    d_dec_deg = dy_arcsec / 3600.0

    pred_ra = (float(ref_ra) + d_ra_deg) % 360.0
    pred_dec = float(ref_dec) + d_dec_deg

    pred_dec = max(-90.0, min(90.0, pred_dec))
    return pred_ra, pred_dec


def test_motion(
    training_measurements: Sequence[dict[str, Any] | MeasurementRecord],
    reserved_measurement: dict[str, Any] | MeasurementRecord,
    investigation_id: str = "SPX_INV_001",
) -> dict[str, Any]:
    """Test whether a sequence of measurements supports real motion or stationary null.

    Scientific Decision Rule:
    1. Requirements:
       - At least 2 training epochs with status 'ok' (for constant-velocity fit).
       - Exactly 1 reserved evaluation epoch with status 'ok'.
       - If either requirement is not met, the outcome is strictly 'insufficient_evidence'
         (Hard Rule 8).
    2. Null Hypothesis (Stationary Model, H0):
       - Position is constant at the mean training coordinates (r_stat).
       - Residual on reserved epoch: R_stat = separation(r_stat, r_reserved).
    3. Alternative Hypothesis (Constant Motion Model, H1):
       - Linear velocity fit to training epochs: r_pred(t).
       - Residual on reserved epoch: R_motion = separation(r_pred(t_res), r_reserved).
    4. Decision Thresholds (based on positional uncertainty sigma_eval):
       - If R_stat <= 2.0 * sigma_eval:
           The reserved position is statistically indistinguishable from a stationary
           object within measurement noise -> 'stationary_plausible'.
       - If R_stat > 2.0 * sigma_eval AND R_motion <= 2.5 * sigma_eval AND R_motion < 0.5 * R_stat:
           The object moved significantly beyond noise, and the motion model successfully
           predicted its reserved position -> 'motion_supported'.
       - Otherwise (e.g. object moved, but motion model failed to predict reserved position,
         or residuals are large):
           Data is inconsistent with stationary AND inconsistent with linear motion
           -> 'insufficient_evidence'.

    Output matches Person 4's FastAPI JSON specification:
    {
      "investigation_id": str,
      "outcome": "motion_supported" | "stationary_plausible" | "insufficient_evidence",
      "measurements": [...],
      "predictions": [...],
      "model_comparison": dict | None,
      "limitations": list[str],
      "warnings": list[str]
    }
    """
    warnings: list[str] = []
    limitations: list[str] = [
        "Linear constant motion assumes no significant orbital curvature, acceleration, "
        "or annual parallax over the observation baseline.",
        "Astrometric precision is fundamentally constrained by SPHEREx native pixel scale (~6.2 arcsec/pixel).",
        "Verification relies on statistical model comparison against a single reserved evaluation epoch.",
    ]

    # Convert training inputs to standardized records
    train_records = [
        m if isinstance(m, MeasurementRecord) else MeasurementRecord.from_dict(m, f"train_{i}")
        for i, m in enumerate(training_measurements)
    ]
    res_record = (
        reserved_measurement
        if isinstance(reserved_measurement, MeasurementRecord)
        else MeasurementRecord.from_dict(reserved_measurement, "reserved")
    )

    all_records = train_records + [res_record]
    measurements_json = [asdict(r) for r in all_records]

    # Rule Check: Need at least 2 training epochs and 1 reserved epoch with status "ok"
    valid_train = [r for r in train_records if _usable(r)]
    res_ok = _usable(res_record)
    if res_ok and any((res_record.epoch_id is not None and r.epoch_id == res_record.epoch_id)
                     or abs((Time(r.observed_at_utc)-Time(res_record.observed_at_utc)).to_value("hour")) <= 1e-6
                     for r in valid_train):
        res_ok = False
        warnings.append("Reserved observation must have an independent epoch and identity from training observations.")

    if len(valid_train) < 2 or not res_ok:
        if len(valid_train) < 2:
            warnings.append(
                f"Insufficient valid training epochs: required >= 2 with status 'ok', got {len(valid_train)}."
            )
        if not res_ok:
            warnings.append(
                f"Reserved epoch status is '{res_record.status}'; evaluation requires a successful measurement, valid time and coordinates, and independent identity."
            )
        return {
            "investigation_id": investigation_id,
            "outcome": "insufficient_evidence",
            "measurements": measurements_json,
            "predictions": [],
            "model_comparison": None,
            "limitations": limitations,
            "warnings": warnings,
        }

    # Fit motion on training epochs
    motion_model = fit_constant_motion(valid_train)
    warnings.extend(motion_model.get("warnings", []))

    if motion_model.get("ref_time_utc") is None:
        return {
            "investigation_id": investigation_id,
            "outcome": "insufficient_evidence",
            "measurements": measurements_json,
            "predictions": [],
            "model_comparison": None,
            "limitations": limitations,
            "warnings": warnings,
        }

    # Evaluate predictions across all epochs (training + reserved)
    predictions_json: list[dict[str, Any]] = []
    for r in all_records:
        if r.observed_at_utc:
            try:
                pred_ra, pred_dec = predict_position(motion_model, r.observed_at_utc)
                res_arcsec = _sky_separation_arcsec(r.ra_deg, r.dec_deg, pred_ra, pred_dec)
                predictions_json.append({
                    "epoch_id": r.epoch_id,
                    "observed_at_utc": r.observed_at_utc,
                    "predicted_ra_deg": float(pred_ra),
                    "predicted_dec_deg": float(pred_dec),
                    "residual_arcsec": float(res_arcsec),
                })
            except Exception:
                pass

    # 1. Stationary model prediction (mean of training coordinates)
    angles = np.radians([r.ra_deg for r in valid_train])
    stat_ra = float(np.degrees(np.arctan2(np.mean(np.sin(angles)), np.mean(np.cos(angles)))) % 360)
    stat_dec = float(np.mean([r.dec_deg for r in valid_train]))
    res_stationary_arcsec = _sky_separation_arcsec(
        stat_ra, stat_dec, res_record.ra_deg, res_record.dec_deg
    )

    # 2. Motion model prediction for reserved epoch
    pred_res_ra, pred_res_dec = predict_position(motion_model, res_record.observed_at_utc)
    res_motion_arcsec = _sky_separation_arcsec(
        pred_res_ra, pred_res_dec, res_record.ra_deg, res_record.dec_deg
    )

    # 3. Positional uncertainty scale
    known_uncerts = [
        r.uncertainty_arcsec
        for r in all_records
        if r.uncertainty_arcsec is not None and r.uncertainty_arcsec > 0
    ]
    if res_record.uncertainty_arcsec is not None and res_record.uncertainty_arcsec > 0:
        raw_sigma = float(res_record.uncertainty_arcsec)
    elif known_uncerts:
        raw_sigma = float(np.mean(known_uncerts))
    else:
        raw_sigma = 1.5
        warnings.append(
            "Measurement uncertainties missing; used default nominal 1.5 arcsec astrometric scale."
        )

    # Incorporate realistic astrometric calibration floor and detector discretization
    # SPHEREx native pixel scale is ~6.2 arcsec; 0.5 arcsec corresponds to ~0.08 px centroiding floor.
    astrometric_floor = 0.5
    sigma_eval = float(np.hypot(raw_sigma, astrometric_floor))

    ratio_motion_to_stat = (
        float(res_motion_arcsec / res_stationary_arcsec)
        if res_stationary_arcsec > 0
        else 1.0
    )

    # Decision rule logic
    if res_stationary_arcsec <= 2.0 * sigma_eval:
        outcome = "stationary_plausible"
        decision_desc = (
            f"Stationary plausible: Reserved epoch offset ({res_stationary_arcsec:.2f}'') "
            f"is within 2*sigma uncertainty ({2.0 * sigma_eval:.2f}''). "
            "Data does not require motion."
        )
    elif (
        res_motion_arcsec <= 2.5 * sigma_eval
        and res_motion_arcsec < 0.5 * res_stationary_arcsec
    ):
        outcome = "motion_supported"
        decision_desc = (
            f"Motion supported: Object moved {res_stationary_arcsec:.2f}'' beyond stationary noise (> 2*sigma). "
            f"Constant-motion model successfully predicts reserved position to within {res_motion_arcsec:.2f}'' "
            f"(< 2.5*sigma and < 0.5*stationary residual)."
        )
    else:
        outcome = "insufficient_evidence"
        decision_desc = (
            f"Insufficient evidence: Object moved beyond stationary noise ({res_stationary_arcsec:.2f}'' > 2*sigma), "
            f"but constant-motion prediction residual ({res_motion_arcsec:.2f}'') is too large to support linear motion."
        )

    model_comparison = {
        "stationary_residual_arcsec": float(res_stationary_arcsec),
        "motion_residual_arcsec": float(res_motion_arcsec),
        "uncertainty_arcsec": float(sigma_eval),
        "ratio_residual_motion_to_stat": ratio_motion_to_stat,
        "fitted_speed_arcsec_per_hour": motion_model.get("total_speed_arcsec_per_hour"),
        "decision_criterion": decision_desc,
    }

    return {
        "investigation_id": investigation_id,
        "outcome": outcome,
        "measurements": measurements_json,
        "predictions": predictions_json,
        "model_comparison": model_comparison,
        "limitations": limitations,
        "warnings": warnings,
    }


# Prevent pytest from treating test_motion as a test case
test_motion.__test__ = False


def scan_and_track_motion(
    epoch_observations: Sequence[Observation],
    snr_threshold: float = 3.5,
    match_radius_arcsec: float = 30.0,
) -> dict[str, Any]:
    """Scan all observations across time to detect, match, and categorize sources.

    Powers the ViewSpace interactive hotspot layer:
    - Scans every epoch frame for point sources (`detect_sources`).
    - Cross-matches detected coordinates across observation dates.
    - Classifies every detected hotspot into:
        - 'stationary_star': Present at identical sky coordinates across epochs.
        - 'moving_candidate': Shifts positions linearly across dates; verified via test_motion.
        - 'transient_candidate': Detected in only one epoch (flare, variable, or single pass).

    Args:
        epoch_observations: Chronological sequence of aligned Observation objects.
        snr_threshold: Detection threshold in units of background sigma.
        match_radius_arcsec: Matching radius to associate sources between epochs.

    Returns:
        dict[str, Any]: Complete ViewSpace-style hotspot payload:
            {
                "num_epochs": int,
                "total_hotspots": int,
                "hotspots": list[dict],
                "warnings": list[str]
            }
    """
    warnings: list[str] = []

    if len(epoch_observations) < 2:
        warnings.append("Need at least 2 observations to perform cross-epoch motion tracking.")
        return {
            "num_epochs": len(epoch_observations),
            "total_hotspots": 0,
            "hotspots": [],
            "warnings": warnings,
        }

    # 1. Detect sources on each epoch
    epoch_detections: list[list[dict[str, Any]]] = []
    for ep_idx, obs in enumerate(epoch_observations):
        mask = build_valid_mask(obs.flags, obs.image.shape)
        dets, det_warn = detect_sources(
            aligned_image=obs.image,
            mask=mask,
            wcs=obs.wcs,
            snr_threshold=snr_threshold,
        )
        warnings.extend([f"Epoch {ep_idx}: {w}" for w in det_warn])
        epoch_detections.append(dets)

    # 2. Track detections starting from Epoch 0
    all_hotspots: list[dict[str, Any]] = []
    matched_in_epoch: list[set[int]] = [set() for _ in epoch_observations]

    # Trace each source from Epoch 0 across subsequent epochs
    for src_idx, src in enumerate(epoch_detections[0]):
        matched_in_epoch[0].add(src_idx)
        track = [
            {
                "epoch_idx": 0,
                "observed_at_utc": epoch_observations[0].observed_at_utc or "2025-01-01T00:00:00",
                "ra_deg": src["ra_deg"],
                "dec_deg": src["dec_deg"],
                "snr": src["snr"],
                "uncertainty_arcsec": src["uncertainty_arcsec"],
                "status": "ok",
            }
        ]

        curr_ra, curr_dec = src["ra_deg"], src["dec_deg"]
        for ep_idx in range(1, len(epoch_observations)):
            best_match_idx = None
            best_sep = np.inf
            for cand_idx, cand in enumerate(epoch_detections[ep_idx]):
                if cand_idx in matched_in_epoch[ep_idx]:
                    continue
                sep = _sky_separation_arcsec(curr_ra, curr_dec, cand["ra_deg"], cand["dec_deg"])
                # Allow a generous search window across epochs for moving candidates
                if sep <= match_radius_arcsec * (ep_idx + 1) and sep < best_sep:
                    best_sep = sep
                    best_match_idx = cand_idx

            if best_match_idx is not None:
                matched_in_epoch[ep_idx].add(best_match_idx)
                cand = epoch_detections[ep_idx][best_match_idx]
                track.append({
                    "epoch_idx": ep_idx,
                    "observed_at_utc": epoch_observations[ep_idx].observed_at_utc or f"2025-01-01T{ep_idx:02d}:00:00",
                    "ra_deg": cand["ra_deg"],
                    "dec_deg": cand["dec_deg"],
                    "snr": cand["snr"],
                    "uncertainty_arcsec": cand["uncertainty_arcsec"],
                    "status": "ok",
                })
                curr_ra, curr_dec = cand["ra_deg"], cand["dec_deg"]

        # Classify the tracked source
        n_detected = len(track)
        total_shift_arcsec = _sky_separation_arcsec(
            track[0]["ra_deg"], track[0]["dec_deg"],
            track[-1]["ra_deg"], track[-1]["dec_deg"]
        )

        verification = None
        speed = 0.0
        if n_detected >= 3 and total_shift_arcsec > 2.0:
            # Perform motion test on tracked trajectory
            training = track[:-1]
            reserved = track[-1]
            verification = test_motion(training, reserved, investigation_id=f"AUTO_{src['id']}")
            if verification["outcome"] == "motion_supported":
                classification = "moving_candidate"
                speed = verification.get("model_comparison", {}).get("fitted_speed_arcsec_per_hour", 0.0)
                desc = (
                    f"Confirmed moving candidate moving at {speed:.1f} arcsec/hour; "
                    f"trajectory verified across {n_detected} epochs."
                )
            else:
                classification = "stationary_star" if total_shift_arcsec <= 2.5 else "unclassified_transient"
                desc = f"Source with {total_shift_arcsec:.2f} arcsec displacement; {verification['outcome']}."
        elif n_detected >= 2 and total_shift_arcsec <= 2.0:
            classification = "stationary_star"
            desc = "Stationary field star consistent with fixed celestial coordinates."
        elif n_detected == 1:
            classification = "transient_candidate"
            desc = "Detected in only one epoch (potential variable, flare, or fast asteroid)."
        else:
            classification = "stationary_star"
            desc = "Consistent with stationary field object."

        all_hotspots.append({
            "id": f"pin_{len(all_hotspots) + 1:03d}",
            "classification": classification,
            "ra_deg": src["ra_deg"],
            "dec_deg": src["dec_deg"],
            "x_px": src["x_px"],
            "y_px": src["y_px"],
            "snr": src["snr"],
            "speed_arcsec_per_hour": round(float(speed), 2) if speed else None,
            "epochs_detected": [t["epoch_idx"] for t in track],
            "description": desc,
            "verification": verification,
        })

    return {
        "num_epochs": len(epoch_observations),
        "total_hotspots": len(all_hotspots),
        "hotspots": all_hotspots,
        "warnings": warnings,
    }

