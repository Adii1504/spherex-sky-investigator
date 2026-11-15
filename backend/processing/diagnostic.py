"""Diagnostic astrometric plotting tools for SPHEREx WhyLab.

Generates publication-quality diagnostic diagrams visualizing the sky trajectory,
fitted velocity vectors, error ellipses, and the hypothesis comparison residuals
(Observed minus Calculated) on the reserved evaluation epoch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def plot_trajectory_fit(
    verification_dict: dict[str, Any],
    out_png_path: str | Path = "trajectory_diagnostic.png",
) -> Path:
    """Generate a 2-panel astrometric diagnostic plot from a test_motion result.

    Panel 1 (Left): Celestial Trajectory (RA vs Dec)
        - Plots training epoch measurements with error bars.
        - Overlays the fitted constant-velocity linear trajectory.
        - Shows the reserved epoch observed position vs model prediction.
        - Marks the stationary null hypothesis coordinate.

    Panel 2 (Right): Residual Comparison (Observed minus Calculated)
        - Compares stationary residual (R_stat) vs motion residual (R_motion)
          against the 2*sigma noise threshold.
        - Displays summary text box with outcome, velocity, and statistical decision.

    Args:
        verification_dict: Output dictionary from test_motion (or pipeline result).
        out_png_path: Output target path for the diagnostic PNG figure.

    Returns:
        Path: Resolved absolute path to saved diagnostic PNG.
    """
    out_file = Path(out_png_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    meas = verification_dict.get("measurements", [])
    preds = verification_dict.get("predictions", [])
    comp = verification_dict.get("model_comparison")
    outcome = verification_dict.get("outcome", "insufficient_evidence")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6), dpi=120)

    if not meas or comp is None:
        fig.text(0.5, 0.5, f"Insufficient Evidence / Incomplete Model\nOutcome: {outcome}",
                 ha="center", va="center", fontsize=14, color="gray")
        fig.savefig(out_file, bbox_inches="tight")
        plt.close(fig)
        return out_file

    # Extract coordinates
    ras = [m["ra_deg"] for m in meas]
    decs = [m["dec_deg"] for m in meas]
    uncerts = [m.get("uncertainty_arcsec") or comp.get("uncertainty_arcsec", 1.0) for m in meas]

    # Convert RA error to degrees: delta_ra = delta_arcsec / (3600 * cos(dec))
    cos_dec = np.cos(np.radians(np.mean(decs)))
    ra_err_deg = [(u / 3600.0) / cos_dec for u in uncerts]
    dec_err_deg = [u / 3600.0 for u in uncerts]

    # Training epochs (all except last) vs reserved epoch (last)
    train_ras, train_decs = ras[:-1], decs[:-1]
    train_ra_err, train_dec_err = ra_err_deg[:-1], dec_err_deg[:-1]
    res_ra, res_dec = ras[-1], decs[-1]
    res_ra_err, res_dec_err = ra_err_deg[-1], dec_err_deg[-1]

    # Panel 1: Trajectory
    ax1.errorbar(
        train_ras,
        train_decs,
        xerr=train_ra_err,
        yerr=train_dec_err,
        fmt="o",
        color="#2ecc71",
        ecolor="#27ae60",
        elinewidth=1.5,
        capsize=3,
        label=f"Training Epochs (N={len(train_ras)})",
        zorder=4,
    )

    ax1.errorbar(
        [res_ra],
        [res_dec],
        xerr=[res_ra_err],
        yerr=[res_dec_err],
        fmt="*",
        markersize=12,
        color="#3498db",
        ecolor="#2980b9",
        elinewidth=1.5,
        capsize=4,
        label="Reserved Epoch (Observed)",
        zorder=5,
    )

    # Plot predicted positions if available
    if preds:
        pred_ras = [p["predicted_ra_deg"] for p in preds]
        pred_decs = [p["predicted_dec_deg"] for p in preds]
        # Line through predictions
        ax1.plot(pred_ras, pred_decs, "--", color="#e74c3c", alpha=0.8, label="Constant-Motion Model Track", zorder=3)
        # Reserved prediction
        ax1.scatter(
            [pred_ras[-1]],
            [pred_decs[-1]],
            marker="s",
            s=80,
            color="#e74c3c",
            edgecolors="black",
            label="Reserved Epoch (Predicted)",
            zorder=6,
        )

    # Stationary model point (mean of training)
    stat_ra = np.mean(train_ras)
    stat_dec = np.mean(train_decs)
    ax1.scatter(
        [stat_ra],
        [stat_dec],
        marker="X",
        s=100,
        color="#9b59b6",
        label="Stationary Null Position",
        zorder=4,
    )

    # Format Panel 1
    ax1.set_xlabel("Right Ascension [deg]")
    ax1.set_ylabel("Declination [deg]")
    ax1.set_title("Astrometric Sky Trajectory & Fit")
    # Invert X axis for astronomical convention (East to left)
    ax1.invert_xaxis()
    ax1.grid(True, linestyle=":", alpha=0.6)
    ax1.legend(loc="best", fontsize=9)

    # Panel 2: Model Comparison Residuals
    r_stat = comp.get("stationary_residual_arcsec", 0.0)
    r_motion = comp.get("motion_residual_arcsec", 0.0)
    sigma_eval = comp.get("uncertainty_arcsec", 1.0)
    thresh_2sigma = 2.0 * sigma_eval
    speed = comp.get("fitted_speed_arcsec_per_hour", 0.0)

    categories = ["Stationary Null (H0)", "Constant Motion (H1)"]
    residuals = [r_stat, r_motion]
    colors = ["#9b59b6", "#e74c3c" if outcome != "motion_supported" else "#2ecc71"]

    bars = ax2.bar(categories, residuals, color=colors, width=0.45, edgecolor="black", alpha=0.85)

    # Overlay 2*sigma threshold line
    ax2.axhline(
        thresh_2sigma,
        color="#e67e22",
        linestyle="--",
        linewidth=2,
        label=f"2-Sigma Noise Threshold ({thresh_2sigma:.2f}'')",
    )

    for bar, val in zip(bars, residuals):
        ax2.text(bar.get_x() + bar.get_width() / 2.0, val + (max(residuals) * 0.02 + 0.1),
                 f"{val:.2f}''", ha="center", va="bottom", fontweight="bold", fontsize=10)

    ax2.set_ylabel("Reserved Epoch Residual [arcsec]")
    ax2.set_title("Hypothesis Testing: Stationary vs Motion")
    ax2.grid(True, axis="y", linestyle=":", alpha=0.6)
    ax2.legend(loc="upper right", fontsize=9)

    # Summary Outcome Banner
    outcome_color = "#27ae60" if outcome == "motion_supported" else ("#2980b9" if outcome == "stationary_plausible" else "#e67e22")
    speed_text = f" | Velocity: {speed:.1f} ''/hr" if speed else ""
    fig.suptitle(
        f"Investigation: {verification_dict.get('investigation_id', 'SPX_INV')}\n"
        f"OUTCOME: {outcome.upper()}{speed_text}",
        fontsize=13,
        fontweight="bold",
        color=outcome_color,
        y=0.98,
    )

    plt.tight_layout()
    fig.savefig(out_file, bbox_inches="tight")
    plt.close(fig)
    return out_file


def plot_sed_spectrum(
    sed_dict: dict[str, Any],
    out_png_path: str | Path = "sed_spectrum.png",
    title: str | None = None,
) -> Path:
    """Generate a publication-quality Spectral Energy Distribution (SED) plot.

    Visualizes multi-wavelength photometry across SPHEREx detector bands (0.75 - 5.0 um),
    overlaying measured flux points, SNR indications, and fitted spectral index alpha.

    Args:
        sed_dict: Dictionary output from extract_sed.
        out_png_path: Target file path for the generated PNG plot.
        title: Optional custom plot title.

    Returns:
        Path: Resolved absolute path to saved diagnostic PNG.
    """
    out_file = Path(out_png_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    points = [
        p for p in sed_dict.get("sed_points", [])
        if p.get("wavelength_um") is not None and p.get("flux") is not None
    ]

    fig, ax = plt.subplots(figsize=(8, 5), dpi=120)

    if not points:
        fig.text(0.5, 0.5, "No Valid Multi-Band Photometry Available", ha="center", va="center", color="gray", fontsize=12)
        fig.savefig(out_file, bbox_inches="tight")
        plt.close(fig)
        return out_file

    wavelengths = [p["wavelength_um"] for p in points]
    fluxes = [p["flux"] for p in points]
    snrs = [p.get("snr") or 0.0 for p in points]
    detectors = [str(p.get("detector") or f"Band {i+1}") for i, p in enumerate(points)]

    # Estimate 1-sigma flux uncertainty from SNR if available
    flux_err = [f / max(s, 1.0) if s > 0 else f * 0.2 for f, s in zip(fluxes, snrs)]

    # Plot photometry points
    ax.errorbar(
        wavelengths,
        fluxes,
        yerr=flux_err,
        fmt="o",
        color="#00e5ff",
        ecolor="#3498db",
        elinewidth=1.5,
        capsize=4,
        markersize=8,
        label="SPHEREx Photometry",
        zorder=5,
    )

    # Annotate detector bands
    for lam, flx, det in zip(wavelengths, fluxes, detectors):
        ax.annotate(
            det,
            (lam, flx),
            textcoords="offset points",
            xytext=(0, 10),
            ha="center",
            fontsize=9,
            fontweight="bold",
            color="#ecf0f1",
        )

    # Plot power law fit if spectral index alpha exists
    alpha = sed_dict.get("spectral_index")
    if alpha is not None and len(wavelengths) >= 2:
        lam_fine = np.linspace(min(wavelengths), max(wavelengths), 100)
        # Anchor at geometric mean
        lam0 = np.median(wavelengths)
        flx0 = np.median(fluxes)
        fit_curve = flx0 * (lam_fine / lam0) ** alpha
        ax.plot(
            lam_fine,
            fit_curve,
            "--",
            color="#ffcc00",
            linewidth=2,
            label=f"Power-Law Fit (alpha = {alpha:+.2f})",
            zorder=4,
        )

    ra = sed_dict.get("ra_deg", 0.0)
    dec = sed_dict.get("dec_deg", 0.0)
    plot_title = title or f"Spectral Energy Distribution (SED) at RA={ra:.4f}, Dec={dec:.4f}"
    ax.set_title(plot_title, fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("Wavelength [um]", fontsize=11)
    ax.set_ylabel("Flux Density [MJy/sr]", fontsize=11)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.grid(True, which="both", linestyle=":", alpha=0.5)
    ax.legend(loc="best", fontsize=9)

    plt.tight_layout()
    fig.savefig(out_file, bbox_inches="tight")
    plt.close(fig)
    return out_file
