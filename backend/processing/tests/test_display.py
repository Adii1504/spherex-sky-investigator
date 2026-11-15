"""Tests for backend/processing/display.py.

Includes tests for:
- compute_shared_stretch across sequences (Hard Rule 6).
- render_preview_png file generation and mask rendering.
- make_difference calculation directly from scientific arrays (Hard Rule 5)
  and symmetric scale creation.
- pixel_to_sky and sky_to_pixel coordinate transformations.
"""

from __future__ import annotations

from pathlib import Path

from astropy.wcs import WCS
import numpy as np
import pytest

from backend.processing.alignment import make_common_grid
from backend.processing.display import (
    compute_shared_stretch,
    create_rgb_composite,
    generate_blink_animation,
    make_difference,
    pixel_to_sky,
    render_preview_png,
    sky_to_pixel,
)
from PIL import Image


def test_compute_shared_stretch_basic():
    """Verify compute_shared_stretch calculates percentiles over all valid sequence pixels."""
    # Frame 1: values from 10 to 50
    img1 = np.linspace(10, 50, 100).reshape(10, 10)
    mask1 = np.ones((10, 10), dtype=bool)

    # Frame 2: values from 0 to 100 with some masked pixels
    img2 = np.linspace(0, 100, 100).reshape(10, 10)
    mask2 = np.ones((10, 10), dtype=bool)
    mask2[0, 0] = False  # Mask lowest value (0)

    vmin, vmax = compute_shared_stretch([img1, img2], [mask1, mask2], pmin=5.0, pmax=95.0)

    assert vmin < vmax
    # 0 was masked, so vmin should be > 0
    assert vmin > 0.0
    assert vmax <= 100.0


def test_compute_shared_stretch_all_masked():
    """Verify fallback when all pixels are masked."""
    img = np.zeros((10, 10))
    mask = np.zeros((10, 10), dtype=bool)

    vmin, vmax = compute_shared_stretch([img], [mask])
    assert (vmin, vmax) == (0.0, 1.0)


def test_render_preview_png(tmp_path: Path):
    """Verify render_preview_png creates a valid PNG file."""
    img = np.linspace(0, 10, 64).reshape(8, 8)
    mask = np.ones((8, 8), dtype=bool)
    mask[0, 0] = False  # masked pixel

    out_file = tmp_path / "test_preview.png"
    result_path = render_preview_png(
        aligned_image=img,
        mask=mask,
        stretch=(0.0, 10.0),
        out_path=out_file,
    )

    assert result_path.exists()
    assert result_path.stat().st_size > 0
    with open(result_path, "rb") as f:
        header = f.read(8)
    assert header == b"\x89PNG\r\n\x1a\n"


def test_make_difference_scientific_arrays(tmp_path: Path):
    """Verify make_difference calculates B - A directly from scientific arrays (Hard Rule 5)."""
    # SYNTHETIC TEST DATA
    shape = (10, 10)
    a = np.full(shape, 5.0, dtype=np.float64)
    b = np.full(shape, 8.0, dtype=np.float64)

    mask_a = np.ones(shape, dtype=bool)
    mask_b = np.ones(shape, dtype=bool)
    # Mask a pixel in A and another in B
    mask_a[2, 2] = False
    mask_b[4, 4] = False

    out_png = tmp_path / "diff.png"
    diff, valid_mask, png_path, warnings = make_difference(
        a, b, mask_a, mask_b, out_png_path=out_png
    )

    # Valid overlap: all pixels except (2,2) and (4,4)
    assert valid_mask[0, 0] is np.True_
    assert valid_mask[2, 2] is np.False_
    assert valid_mask[4, 4] is np.False_

    # Difference should be exactly B - A = 8.0 - 5.0 = 3.0
    assert np.isclose(diff[0, 0], 3.0)
    assert np.isnan(diff[2, 2])
    assert np.isnan(diff[4, 4])

    assert png_path is not None and png_path.exists()
    assert len(warnings) == 0


def test_make_difference_no_overlap():
    """Verify make_difference handles zero valid overlap gracefully with warning."""
    shape = (5, 5)
    a = np.ones(shape)
    b = np.ones(shape)
    mask_a = np.zeros(shape, dtype=bool)  # All masked
    mask_b = np.ones(shape, dtype=bool)

    diff, valid_mask, png_path, warnings = make_difference(a, b, mask_a, mask_b)

    assert not np.any(valid_mask)
    assert np.all(np.isnan(diff))
    assert any("No overlapping valid pixels" in w for w in warnings)


def test_make_difference_shape_mismatch():
    """Verify ValueError is raised if image shapes differ."""
    a = np.zeros((10, 10))
    b = np.zeros((8, 8))
    m = np.ones((10, 10), dtype=bool)
    with pytest.raises(ValueError, match="shapes must match"):
        make_difference(a, b, m, m)


def test_coordinate_transforms_roundtrip():
    """Verify pixel_to_sky and sky_to_pixel roundtrip conversion for Person 3."""
    wcs = make_common_grid(ra_deg=200.0, dec_deg=-15.0, fov_arcmin=5.0, size_px=100)

    # Test single pixel center (0-indexed)
    px_x, px_y = 49.5, 49.5
    ra, dec = pixel_to_sky(px_x, px_y, wcs)
    assert isinstance(ra, float)
    assert isinstance(dec, float)
    assert np.isclose(ra, 200.0, atol=1e-5)
    assert np.isclose(dec, -15.0, atol=1e-5)

    back_x, back_y = sky_to_pixel(ra, dec, wcs)
    assert np.isclose(back_x, px_x, atol=1e-5)
    assert np.isclose(back_y, px_y, atol=1e-5)

    # Test array coordinates
    xs = np.array([10.0, 50.0, 80.0])
    ys = np.array([10.0, 50.0, 80.0])
    ras, decs = pixel_to_sky(xs, ys, wcs)
    re_xs, re_ys = sky_to_pixel(ras, decs, wcs)
    np.testing.assert_allclose(re_xs, xs, atol=1e-5)
    np.testing.assert_allclose(re_ys, ys, atol=1e-5)


def test_create_rgb_composite(tmp_path: Path):
    """Verify create_rgb_composite generates 3-channel false-color image for ViewSpace view."""
    # SYNTHETIC TEST DATA
    shape = (20, 20)
    # Red: gradient along rows
    r = np.linspace(0, 10, 400).reshape(shape)
    # Green: gradient along cols
    g = np.linspace(0, 5, 400).reshape(shape).T
    # Blue: centered peak
    b = np.zeros(shape)
    b[10, 10] = 50.0

    out_file = tmp_path / "rgb_composite.png"
    rgb_arr, png_path, warnings = create_rgb_composite(
        r_image=r,
        g_image=g,
        b_image=b,
        out_png_path=out_file,
    )

    assert rgb_arr.shape == (20, 20, 3)
    assert np.all(rgb_arr >= 0.0) and np.all(rgb_arr <= 1.0)
    assert png_path is not None and png_path.exists()
    assert png_path.stat().st_size > 0


def test_generate_blink_animation(tmp_path: Path):
    """Verify generate_blink_animation produces a valid multi-frame looping GIF."""
    shape = (32, 32)
    # 3 frames with a moving spot
    f1 = np.zeros(shape)
    f1[10, 10] = 100.0
    f2 = np.zeros(shape)
    f2[15, 15] = 100.0
    f3 = np.zeros(shape)
    f3[20, 20] = 100.0

    masks = [np.ones(shape, dtype=bool) for _ in range(3)]
    out_gif = tmp_path / "test_blink.gif"

    result_path = generate_blink_animation(
        list_of_aligned_images=[f1, f2, f3],
        list_of_masks=masks,
        stretch=(0.0, 100.0),
        out_path=out_gif,
        fps=4.0,
        labels=["Epoch 1", "Epoch 2", "Epoch 3"],
    )

    assert result_path.exists()
    assert result_path.stat().st_size > 0

    # Inspect GIF properties using PIL
    with Image.open(result_path) as im:
        assert im.format == "GIF"
        assert getattr(im, "is_animated", False)
        assert im.n_frames == 3
        assert im.size == (32, 32)


def test_generate_blink_animation_no_labels(tmp_path: Path):
    """Verify generate_blink_animation works cleanly when labels are omitted."""
    shape = (16, 16)
    f1 = np.ones(shape) * 10
    f2 = np.ones(shape) * 20
    masks = [np.ones(shape, dtype=bool), np.ones(shape, dtype=bool)]

    out_gif = tmp_path / "no_labels.gif"
    result_path = generate_blink_animation(
        list_of_aligned_images=[f1, f2],
        list_of_masks=masks,
        stretch=(0.0, 30.0),
        out_path=out_gif,
        fps=2.0,
    )

    assert result_path.exists()
    with Image.open(result_path) as im:
        assert im.format == "GIF"
        assert im.n_frames == 2


