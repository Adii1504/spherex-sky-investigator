"""Visual alignment verification tool for SPHEREx WhyLab.

Reprojects observations onto a common celestial grid and generates a side-by-side
diagnostic plot comparing raw images, aligned frames, and difference image.

Usage:
    python backend/processing/check_visual.py [fits_file1] [fits_file2] [--out output.png]
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Ensure repository root is on sys.path
repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import matplotlib.pyplot as plt
import numpy as np

from backend.processing.alignment import make_common_grid, reproject_to_grid
from backend.processing.io_fits import load_observation


def run_visual_check(
    fits1: str | Path,
    fits2: str | Path,
    output_png: str | Path = "visual_check_alignment.png",
) -> Path:
    p1 = Path(fits1)
    p2 = Path(fits2)
    out_path = Path(output_png)

    print(f"Loading Observation 1: {p1.name}")
    obs1 = load_observation(p1)
    print(f"Loading Observation 2: {p2.name}")
    obs2 = load_observation(p2)

    # Use center of obs1 as target grid center
    ny1, nx1 = obs1.image.shape
    ra_center, dec_center = obs1.wcs.pixel_to_world_values((nx1 - 1) / 2.0, (ny1 - 1) / 2.0)
    ra_deg = float(ra_center)
    dec_deg = float(dec_center)

    fov_arcmin = 2.0
    size_px = 128
    print(f"Target common grid: RA={ra_deg:.5f} deg, Dec={dec_deg:.5f} deg, FOV={fov_arcmin}' ({size_px}x{size_px})")
    target_wcs = make_common_grid(ra_deg, dec_deg, fov_arcmin=fov_arcmin, size_px=size_px)

    print("Reprojecting Observation 1...")
    img1_aligned, mask1_aligned, warn1 = reproject_to_grid(obs1, target_wcs, shape_out=(size_px, size_px))
    print("Reprojecting Observation 2...")
    img2_aligned, mask2_aligned, warn2 = reproject_to_grid(obs2, target_wcs, shape_out=(size_px, size_px))

    # Compute difference where both masks are valid (Hard Rule 5)
    common_mask = mask1_aligned & mask2_aligned
    diff = np.full_like(img1_aligned, np.nan)
    diff[common_mask] = img2_aligned[common_mask] - img1_aligned[common_mask]

    # Shared stretch percentiles (Hard Rule 6)
    valid_vals = np.concatenate([
        img1_aligned[mask1_aligned],
        img2_aligned[mask2_aligned],
    ]) if (np.any(mask1_aligned) and np.any(mask2_aligned)) else np.array([0.0, 1.0])

    if valid_vals.size > 0:
        vmin = float(np.nanpercentile(valid_vals, 1.0))
        vmax = float(np.nanpercentile(valid_vals, 99.0))
    else:
        vmin, vmax = 0.0, 1.0

    if vmin >= vmax:
        vmax = vmin + 1.0

    # Symmetric scale for difference image
    valid_diff = diff[common_mask]
    if valid_diff.size > 0:
        dmax = float(np.nanpercentile(np.abs(valid_diff), 99.0))
        if dmax == 0:
            dmax = 1.0
    else:
        dmax = 1.0

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # Frame 1
    im0 = axes[0].imshow(img1_aligned, origin="lower", cmap="viridis", vmin=vmin, vmax=vmax)
    axes[0].set_title(f"Aligned Frame 1 ({p1.stem})\nNorth Up, East Left")
    plt.colorbar(im0, ax=axes[0], fraction=0.046, pad=0.04)

    # Frame 2
    im1 = axes[1].imshow(img2_aligned, origin="lower", cmap="viridis", vmin=vmin, vmax=vmax)
    axes[1].set_title(f"Aligned Frame 2 ({p2.stem})\nNorth Up, East Left")
    plt.colorbar(im1, ax=axes[1], fraction=0.046, pad=0.04)

    # Difference (B - A)
    im2 = axes[2].imshow(diff, origin="lower", cmap="coolwarm", vmin=-dmax, vmax=dmax)
    axes[2].set_title("Difference Image (B minus A)\nSymmetric Diverging Scale")
    plt.colorbar(im2, ax=axes[2], fraction=0.046, pad=0.04)

    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"[SUCCESS] Visual verification figure saved to: {out_path.resolve()}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate visual check for SPHEREx alignment.")
    parser.add_argument("fits1", nargs="?", default="backend/processing/sample_data/spherex_d1_cutout.fits")
    parser.add_argument("fits2", nargs="?", default="backend/processing/sample_data/spherex_d2_cutout.fits")
    parser.add_argument("--out", default="backend/processing/visual_check_alignment.png")
    args = parser.parse_args()

    run_visual_check(args.fits1, args.fits2, args.out)


if __name__ == "__main__":
    main()
