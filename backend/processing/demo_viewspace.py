"""ViewSpace-level multi-wavelength composite and interactive hotspot demo.

Demonstrates:
1. Multi-band RGB false-color composite (SPHEREx D6=Red, D3=Green, D1=Blue).
2. Automated field scanning (`detect_sources`) producing interactive pins.
3. Multi-wavelength Spectral Energy Distribution extraction (`extract_sed`).

Usage:
    python backend/processing/demo_viewspace.py
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

# Ensure repository root is on sys.path
repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from backend.processing.alignment import make_common_grid, reproject_to_grid
from backend.processing.display import create_rgb_composite
from backend.processing.io_fits import load_observation
from backend.processing.measure import detect_sources, extract_sed


def run_viewspace_demo() -> None:
    sample_dir = Path("backend/processing/sample_data")

    # Load real cutouts: D6 (Red / 4.5um), D3 (Green / 2.0um), D1 (Blue / 0.9um)
    f_d6 = sample_dir / "spherex_d6_cutout.fits"
    f_d3 = sample_dir / "spherex_d3_cutout.fits"
    f_d1 = sample_dir / "spherex_d1_cutout.fits"

    print("=" * 70)
    print("SPHEREx WhyLab: ViewSpace Multi-Wavelength Scanning Demo")
    print("=" * 70)

    print(f"Loading Red Band (D6, ~4.5um): {f_d6.name}")
    obs_r = load_observation(f_d6)
    print(f"Loading Green Band (D3, ~2.0um): {f_d3.name}")
    obs_g = load_observation(f_d3)
    print(f"Loading Blue Band (D1, ~0.9um): {f_d1.name}")
    obs_b = load_observation(f_d1)

    # Make shared target grid centered on the primary source
    ra0, dec0 = obs_r.wcs.pixel_to_world_values(7.5, 7.5)
    target_wcs = make_common_grid(float(ra0), float(dec0), fov_arcmin=2.0, size_px=128)

    print("Reprojecting bands to common North-up / East-left grid...")
    r_img, r_mask, _ = reproject_to_grid(obs_r, target_wcs, shape_out=(128, 128))
    g_img, g_mask, _ = reproject_to_grid(obs_g, target_wcs, shape_out=(128, 128))
    b_img, b_mask, _ = reproject_to_grid(obs_b, target_wcs, shape_out=(128, 128))

    out_rgb = Path("backend/processing/viewspace_rgb_composite.png")
    print(f"Rendering ViewSpace False-Color RGB composite -> {out_rgb.name}")
    rgb_arr, rgb_path, _ = create_rgb_composite(
        r_image=r_img,
        g_image=g_img,
        b_image=b_img,
        r_mask=r_mask,
        g_mask=g_mask,
        b_mask=b_mask,
        out_png_path=out_rgb,
    )
    print(f"[SUCCESS] Saved RGB composite to {rgb_path}")

    # Field scanning for interactive tour stops / hotspots
    print("\nScanning composite field for hotspots (detect_sources)...")
    hotspots, _ = detect_sources(g_img, g_mask, target_wcs, snr_threshold=3.0)
    print(f"Detected {len(hotspots)} interactive hotspot pins in the field!")

    # Multi-band Spectral Energy Distribution (SED) for top hotspot
    all_bands = [
        load_observation(sample_dir / f"spherex_d{d}_cutout.fits")
        for d in range(1, 7)
        if (sample_dir / f"spherex_d{d}_cutout.fits").exists()
    ]
    # Assign wavelengths based on SPHEREx central detector bands
    detector_waves = {1: 0.93, 2: 1.38, 3: 2.03, 4: 3.12, 5: 4.12, 6: 4.71}
    for obs in all_bands:
        if obs.detector in detector_waves:
            obs.wavelength_um = detector_waves[obs.detector]

    top_pin = hotspots[0] if hotspots else {"ra_deg": float(ra0), "dec_deg": float(dec0)}
    print(f"\nExtracting Multi-Wavelength SED spectrum for Hotspot {top_pin.get('id', 'pin_1')}...")
    sed_result = extract_sed(
        ra_deg=top_pin["ra_deg"],
        dec_deg=top_pin["dec_deg"],
        observations=all_bands,
    )

    print("\n--- VIEWSPACE PAYLOAD READY FOR PERSON 3 & PERSON 4 ---")
    payload = {
        "viewspace_composite_url": str(out_rgb),
        "hotspots_count": len(hotspots),
        "sample_hotspot": top_pin,
        "sample_spectrum_sed": sed_result,
    }
    print(json.dumps(payload, indent=2))
    print("=" * 70)


if __name__ == "__main__":
    run_viewspace_demo()
