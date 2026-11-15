"""Display utilities, stretching, preview generation, and coordinate transforms.

Computes shared stretches across observation sequences, renders preview PNGs,
builds scientific difference images with symmetric diverging scales, and translates
between 0-indexed pixel coordinates and sky coordinates (RA, Dec).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

import matplotlib
# Headless backend for server and CLI safety
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from astropy.wcs import WCS
import numpy as np
from PIL import Image, ImageDraw


def compute_shared_stretch(
    list_of_aligned_images: Sequence[np.ndarray],
    list_of_masks: Sequence[np.ndarray],
    pmin: float = 1.0,
    pmax: float = 99.0,
) -> tuple[float, float]:
    """Compute a single shared intensity stretch across all frames in a sequence.

    Hard Rule 6: Use ONE shared intensity stretch across all frames of a sequence
    so that visual comparisons across epochs remain scientifically honest.

    Args:
        list_of_aligned_images: Sequence of 2D aligned flux arrays.
        list_of_masks: Sequence of corresponding 2D boolean masks (True = usable).
        pmin: Lower percentile cutoff (default 1.0).
        pmax: Upper percentile cutoff (default 99.0).

    Returns:
        tuple[float, float]: (vmin, vmax) intensity limits.
    """
    valid_pixels_list: list[np.ndarray] = []
    for img, mask in zip(list_of_aligned_images, list_of_masks):
        valid = mask & np.isfinite(img)
        if np.any(valid):
            valid_pixels_list.append(img[valid].ravel())

    if not valid_pixels_list:
        return 0.0, 1.0

    all_valid = np.concatenate(valid_pixels_list)
    if all_valid.size == 0:
        return 0.0, 1.0

    vmin = float(np.nanpercentile(all_valid, pmin))
    vmax = float(np.nanpercentile(all_valid, pmax))

    if vmin >= vmax:
        vmax = vmin + (1.0 if vmin == 0.0 else abs(vmin) * 0.1)

    return vmin, vmax


def render_preview_png(
    aligned_image: np.ndarray,
    mask: np.ndarray,
    stretch: tuple[float, float],
    out_path: str | Path,
    cmap: str = "viridis",
) -> Path:
    """Render an aligned preview image to PNG with North up, East left.

    Masked or non-finite pixels are displayed distinctly in neutral dark gray.

    Args:
        aligned_image: 2D float array (North up, East left).
        mask: 2D boolean mask (True = usable pixel).
        stretch: (vmin, vmax) intensity stretch.
        out_path: Target file path for the output PNG.
        cmap: Matplotlib colormap name.

    Returns:
        Path: Resolved absolute path to the written PNG file.
    """
    out_file = Path(out_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    vmin, vmax = stretch
    display_data = np.copy(aligned_image)
    display_data[~mask | ~np.isfinite(display_data)] = np.nan

    cm = plt.get_cmap(cmap).with_extremes(bad="#1a1a24")  # Distinct neutral dark tone for masked pixels

    ny, nx = aligned_image.shape
    dpi = 100
    figsize = (nx / dpi, ny / dpi)

    fig = plt.figure(figsize=figsize, dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")

    ax.imshow(
        display_data,
        origin="lower",
        cmap=cm,
        vmin=vmin,
        vmax=vmax,
        interpolation="nearest",
    )

    fig.savefig(out_file, dpi=dpi, bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    return out_file


def make_difference(
    a: np.ndarray,
    b: np.ndarray,
    mask_a: np.ndarray,
    mask_b: np.ndarray,
    out_png_path: str | Path | None = None,
) -> tuple[np.ndarray, np.ndarray, Path | None, list[str]]:
    """Compute scientific signed difference (B minus A) from aligned scientific arrays.

    Hard Rule 5: Difference images must be computed directly from scientific flux arrays
    (after masks and alignment), NEVER from display PNGs or stretched bytes.

    Uses a symmetric diverging scale centered strictly at 0:
    - Neutral/White: Zero difference (constant brightness).
    - Red / Warm: Positive difference (source brighter in B than A).
    - Blue / Cold: Negative difference (source dimmer in B than A).
    - Masked pixels: Distinct dark background.

    Args:
        a: Epoch A 2D aligned flux array.
        b: Epoch B 2D aligned flux array.
        mask_a: Usability mask for epoch A (True = usable).
        mask_b: Usability mask for epoch B (True = usable).
        out_png_path: Optional path to save difference PNG.

    Returns:
        tuple[np.ndarray, np.ndarray, Path | None, list[str]]:
            - diff_array: 2D float64 signed difference array (B - A), NaNs for masked pixels.
            - valid_mask: 2D boolean mask where both frames are usable.
            - png_path: Path to rendered PNG file if out_png_path provided, else None.
            - warnings: List of warnings regarding overlap or masking.
    """
    warnings: list[str] = []

    if a.shape != b.shape:
        raise ValueError(f"Array shapes must match for differencing: {a.shape} vs {b.shape}")

    valid_mask = mask_a & mask_b & np.isfinite(a) & np.isfinite(b)
    diff_array = np.full_like(b, np.nan, dtype=np.float64)

    num_valid = int(np.count_nonzero(valid_mask))
    if num_valid == 0:
        warnings.append("No overlapping valid pixels between Epoch A and Epoch B for difference imaging.")
        dmax = 1.0
    else:
        diff_array[valid_mask] = b[valid_mask] - a[valid_mask]
        valid_vals = np.abs(diff_array[valid_mask])
        dmax = float(np.nanpercentile(valid_vals, 99.0))
        if dmax <= 0.0:
            dmax = 1.0

    png_out: Path | None = None
    if out_png_path is not None:
        png_out = Path(out_png_path).resolve()
        png_out.parent.mkdir(parents=True, exist_ok=True)

        cm = plt.get_cmap("coolwarm").with_extremes(bad="#1a1a24")

        ny, nx = diff_array.shape
        dpi = 100
        fig = plt.figure(figsize=(nx / dpi, ny / dpi), dpi=dpi)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis("off")

        ax.imshow(
            diff_array,
            origin="lower",
            cmap=cm,
            vmin=-dmax,
            vmax=dmax,
            interpolation="nearest",
        )

        fig.savefig(png_out, dpi=dpi, bbox_inches="tight", pad_inches=0)
        plt.close(fig)

    return diff_array, valid_mask, png_out, warnings


def pixel_to_sky(
    x: float | np.ndarray,
    y: float | np.ndarray,
    wcs: WCS,
) -> tuple[float | np.ndarray, float | np.ndarray]:
    """Convert 0-indexed pixel coordinates (x, y) to celestial coordinates (RA, Dec in degrees).

    Directly supports frontend coordinate probing (Person 3).

    Args:
        x: Horizontal coordinate (0 to nx - 1).
        y: Vertical coordinate (0 to ny - 1).
        wcs: 2D celestial WCS.

    Returns:
        tuple[float | np.ndarray, float | np.ndarray]: (ra_deg, dec_deg) in degrees.
    """
    ra, dec = wcs.pixel_to_world_values(x, y)
    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
        return float(ra), float(dec)
    return ra, dec


def sky_to_pixel(
    ra: float | np.ndarray,
    dec: float | np.ndarray,
    wcs: WCS,
) -> tuple[float | np.ndarray, float | np.ndarray]:
    """Convert celestial coordinates (RA, Dec in degrees) to 0-indexed pixel coordinates (x, y).

    Directly supports frontend coordinate probing (Person 3).

    Args:
        ra: Right Ascension in degrees.
        dec: Declination in degrees.
        wcs: 2D celestial WCS.

    Returns:
        tuple[float | np.ndarray, float | np.ndarray]: (x, y) in 0-indexed pixel coordinates.
    """
    x, y = wcs.world_to_pixel_values(ra, dec)
    if isinstance(ra, (int, float)) and isinstance(dec, (int, float)):
        return float(x), float(y)
    return x, y


def create_rgb_composite(
    r_image: np.ndarray,
    g_image: np.ndarray,
    b_image: np.ndarray,
    r_mask: np.ndarray | None = None,
    g_mask: np.ndarray | None = None,
    b_mask: np.ndarray | None = None,
    out_png_path: str | Path | None = None,
    pmin: float = 1.0,
    pmax: float = 99.5,
) -> tuple[np.ndarray, Path | None, list[str]]:
    """Build a multi-wavelength false-color RGB composite image.

    Replicates the signature NASA / ViewSpace multi-wavelength visualization:
    - Red channel: Longest wavelength (e.g. SPHEREx Band 5 or 6, 4.4 - 5.0 um; cool dust/zodi).
    - Green channel: Intermediate wavelength (e.g. Band 3 or 4, 1.6 - 2.5 um; warm dust/ices).
    - Blue channel: Shortest wavelength (e.g. Band 1 or 2, 0.75 - 1.1 um; stellar emission).

    Args:
        r_image: 2D array for Red channel.
        g_image: 2D array for Green channel.
        b_image: 2D array for Blue channel.
        r_mask: Usability mask for Red channel.
        g_mask: Usability mask for Green channel.
        b_mask: Usability mask for Blue channel.
        out_png_path: Optional output path to write composite PNG.
        pmin: Lower percentile for channel intensity stretch.
        pmax: Upper percentile for channel intensity stretch.

    Returns:
        tuple[np.ndarray, Path | None, list[str]]:
            - rgb_array: Normalized (ny, nx, 3) float array in [0.0, 1.0].
            - png_path: Resolved path to written PNG file if out_png_path provided.
            - warnings: List of warning strings.
    """
    warnings: list[str] = []

    if r_image.shape != g_image.shape or r_image.shape != b_image.shape:
        raise ValueError(
            f"All channel images must have matching shapes: R={r_image.shape}, G={g_image.shape}, B={b_image.shape}"
        )

    channels = [r_image, g_image, b_image]
    masks = [
        r_mask if r_mask is not None else np.ones(r_image.shape, dtype=bool),
        g_mask if g_mask is not None else np.ones(g_image.shape, dtype=bool),
        b_mask if b_mask is not None else np.ones(b_image.shape, dtype=bool),
    ]

    norm_channels: list[np.ndarray] = []
    for i, (ch, m) in enumerate(zip(channels, masks)):
        valid = m & np.isfinite(ch)
        if np.any(valid):
            v0 = float(np.nanpercentile(ch[valid], pmin))
            v1 = float(np.nanpercentile(ch[valid], pmax))
            if v1 <= v0:
                v1 = v0 + 1.0
            norm = np.clip((ch - v0) / (v1 - v0), 0.0, 1.0)
            norm[~valid] = 0.0
        else:
            warnings.append(f"Channel {i} has no valid pixels; rendered as black.")
            norm = np.zeros(ch.shape, dtype=np.float64)
        norm_channels.append(norm)

    # Combine channels: R, G, B
    rgb_composite = np.stack(norm_channels, axis=-1)

    # Set fully unobserved areas to a dark tone (cosmic background)
    combined_mask = masks[0] | masks[1] | masks[2]
    rgb_composite[~combined_mask] = 0.04

    png_out: Path | None = None
    if out_png_path is not None:
        png_out = Path(out_png_path).resolve()
        png_out.parent.mkdir(parents=True, exist_ok=True)

        ny, nx, _ = rgb_composite.shape
        dpi = 100
        fig = plt.figure(figsize=(nx / dpi, ny / dpi), dpi=dpi)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis("off")

        ax.imshow(rgb_composite, origin="lower", interpolation="nearest")
        fig.savefig(png_out, dpi=dpi, bbox_inches="tight", pad_inches=0)
        plt.close(fig)

    return rgb_composite, png_out, warnings


def generate_blink_animation(
    list_of_aligned_images: Sequence[np.ndarray],
    list_of_masks: Sequence[np.ndarray],
    stretch: tuple[float, float],
    out_path: str | Path,
    fps: float = 2.0,
    labels: Sequence[str] | None = None,
    cmap: str = "viridis",
) -> Path:
    """Generate an animated looping blink GIF across aligned sequence epochs.

    Replicates astronomical 'blink comparator' techniques used to discover
    asteroids, comets, and proper motion stars.

    Args:
        list_of_aligned_images: List of 2D aligned flux arrays.
        list_of_masks: List of corresponding boolean masks.
        stretch: Shared (vmin, vmax) intensity stretch.
        out_path: Destination path for animated GIF file.
        fps: Frames per second (default 2.0 = 500ms dwell time).
        labels: Optional label per frame (e.g. observation timestamps).
        cmap: Colormap name to use for rendering frames.

    Returns:
        Path: Resolved path to the written animated GIF.
    """
    out_file = Path(out_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    vmin, vmax = stretch
    cm = plt.get_cmap(cmap).with_extremes(bad="#111118")

    pil_frames: list[Image.Image] = []

    for idx, (img, msk) in enumerate(zip(list_of_aligned_images, list_of_masks)):
        valid = msk & np.isfinite(img)
        # Normalize in [0, 1]
        norm = np.clip((img - vmin) / (vmax - vmin), 0.0, 1.0) if vmax > vmin else np.zeros_like(img)
        # Apply colormap -> RGBA
        rgba = cm(norm)
        # Invert vertical axis for standard North-up rendering in PIL (since PIL origin is top-left)
        rgba_flipped = np.flipud(rgba)
        rgba_flipped[~np.flipud(valid)] = [0.08, 0.08, 0.12, 1.0]

        img_8bit = (rgba_flipped * 255).astype(np.uint8)
        frame_pil = Image.fromarray(img_8bit, mode="RGBA").convert("RGB")

        # Overlay text label if provided
        if labels and idx < len(labels) and labels[idx]:
            draw = ImageDraw.Draw(frame_pil)
            lbl = str(labels[idx])
            # Draw semi-transparent banner
            draw.rectangle([(2, 2), (min(len(lbl) * 7 + 6, frame_pil.width - 2), 14)], fill=(0, 0, 0))
            draw.text((4, 2), lbl, fill=(255, 255, 255))

        pil_frames.append(frame_pil)

    duration_ms = int(1000.0 / max(fps, 0.1))
    pil_frames[0].save(
        out_file,
        save_all=True,
        append_images=pil_frames[1:],
        duration=duration_ms,
        loop=0,
    )

    return out_file


