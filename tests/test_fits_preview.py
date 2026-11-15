"""Synthetic fixtures validate geometry and raw quality values, not real astrometry."""
import hashlib
import io
import json
import numpy as np
import pytest
from PIL import Image
from astropy.io import fits
from astropy.wcs import WCS
from fastapi.testclient import TestClient
from whylab.app import create_app
from whylab.config import Settings
from whylab.fits_preview.reader import read
from whylab.fits_preview.quality import report
from whylab.fits_preview.preview import render
from whylab.fits_preview.routes import ProductRegistry, ArtifactCache


def fixture(path, missing=(), invalid=False, constant=False):
    w = WCS(naxis=2)
    w.wcs.crpix = [6, 6]
    w.wcs.crval = [120, 20]
    w.wcs.cdelt = [-.01, .01]
    w.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    h = w.to_header()
    h['BUNIT'] = 'MJy/sr'
    primary = fits.PrimaryHDU()
    primary.header['DATE-OBS'] = '2025-01-01T00:00:00'
    primary.header['TIMESYS'] = 'UTC'
    primary.header['DETECTOR'] = 2
    image = np.full((11, 11), 7.) if constant else np.arange(121, dtype=float).reshape(11, 11)
    image[0, 0] = np.nan
    if invalid:
        image[:] = np.nan
    flags = np.full(image.shape, np.uint64(2**63+3), dtype=np.uint64)
    hdus = [primary]
    for name, data in [('IMAGE', image), ('FLAGS', flags), ('VARIANCE', np.ones(image.shape))]:
        if name not in missing:
            hdus.append(fits.ImageHDU(data, header=h if name == 'IMAGE' else None, name=name))
    fits.HDUList(hdus).writeto(path, overwrite=True)
    return w


def position(w, x=5, y=5):
    sky = w.pixel_to_world(x, y)
    return dict(ra_deg=float(sky.ra.deg), dec_deg=float(sky.dec.deg), astrometry_status='provisional')


def test_center_marker_metadata_flags_and_source_unchanged(tmp_path):
    path = tmp_path/'input.fits'
    w = fixture(path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    frame = read(path)
    q = report(frame, position(w), 2)
    assert q['geometry']['x'] == pytest.approx(5)
    assert q['geometry']['y'] == pytest.approx(5)
    assert q['geometry']['nearest_boundary_distance_pixels'] == pytest.approx(5.5)
    assert q['flags']['bitwise_or'] == 2**63+3
    assert q['flags']['value_counts'][0]['value'] == 2**63+3
    assert frame.metadata['DETECTOR']['hdu'] == 'PRIMARY'
    png, meta = render(frame, q, 110)
    rgb = np.asarray(Image.open(io.BytesIO(png)))
    assert (rgb[48:62, 48:62, 0] > rgb[48:62, 48:62, 1]).any()
    assert meta['image_panel_height'] == 110
    # Top-left corresponds to highest FITS y, not row zero (which is invalid).
    assert rgb[0, 0, 0] > rgb[109, 0, 0]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    json.dumps(q, allow_nan=False)


def test_outside_truncation_and_boundaries(tmp_path):
    path = tmp_path/'input.fits'
    w = fixture(path)
    frame = read(path)
    q = report(frame, position(w, -.25, 5), 2)
    assert q['geometry']['inside_image']
    assert q['aperture']['truncated']
    q = report(frame, position(w, -2, 5), 3)
    assert not q['geometry']['inside_image']
    assert q['geometry']['nearest_boundary_distance_pixels'] == pytest.approx(1.5)
    q = report(frame, position(w, -10, 5), 1)
    assert q['aperture']['pixel_count'] == 0
    assert q['aperture']['valid_pixel_fraction'] is None


@pytest.mark.parametrize('missing', [('IMAGE',), ('FLAGS', 'VARIANCE')])
def test_missing_extensions(tmp_path, missing):
    path = tmp_path/'input.fits'
    w = fixture(path, missing=missing)
    frame = read(path)
    q = report(frame, position(w), 2)
    assert q['flags']['status'] == 'unavailable'
    assert q['variance']['status'] == 'unavailable'
    if 'IMAGE' in missing:
        assert q['geometry']['reason'] == 'image_unavailable'
    assert render(frame, q)[0].startswith(b'\x89PNG')


@pytest.mark.parametrize('invalid,constant,status', [(True, False, 'all_invalid'), (False, True, 'constant')])
def test_invalid_constant(tmp_path, invalid, constant, status):
    path = tmp_path/'input.fits'
    w = fixture(path, invalid=invalid, constant=constant)
    f = read(path)
    q = report(f, position(w), 3)
    assert render(f, q)[1]['status'] == status
    assert q['aperture']['valid_pixel_fraction'] == (0 if invalid else 1)
    json.dumps(q, allow_nan=False)


def test_unavailable_wcs_coordinates_and_malformed_extensions(tmp_path):
    path = tmp_path/'input.fits'
    w = fixture(path)
    f = read(path)
    q = report(f, dict(ra_deg=None, dec_deg=None, astrometry_status='pending'), 3)
    assert q['geometry']['reason'] == 'coordinates_unavailable'
    f.wcs = None
    assert report(f, position(w), 3)['geometry']['reason'] == 'wcs_unavailable'
    f = read(path)
    f.flags = np.ones((11, 11), dtype=float)
    f.variance[5, 5] = np.inf
    q = report(f, position(w), 2)
    assert q['flags']['reason'] == 'flags_not_integer'
    assert q['variance']['invalid_count'] == 1
    q = report(f, position(w, 0, 0), 1)
    assert q['aperture']['nonfinite_science_count'] == 1


def test_endpoints_registry_cache_validation(tmp_path):
    path = tmp_path/'input.fits'
    w = fixture(path)
    registry = ProductRegistry(tmp_path, {'test_product': {'path': 'input.fits', 'predicted_position': position(w)}})
    settings = Settings(output_dir=tmp_path/'outputs')
    with TestClient(create_app(settings, fits_registry=registry)) as client:
        root = '/api/observations/test_product/'
        assert client.get(root+'preview').headers['content-type'] == 'image/png'
        response = client.get(root+'quality')
        assert response.status_code == 200
        assert response.json()['position']['astrometry_status'] == 'provisional'
        assert len(list((settings.output_dir/'fits').iterdir())) == 1
        for endpoint in ['preview', 'quality']:
            assert client.get(root+endpoint, params={'ra_deg': 12}).status_code == 422
            assert client.get(root+endpoint, params={'ra_deg': 'nan', 'dec_deg': 0, 'astrometry_status': 'pending'}).status_code == 422
            assert client.get('/api/observations/unknown/'+endpoint).status_code == 404
        query = {**position(w, 2, 2), 'aperture_radius': 4}
        assert client.get(root+'quality', params=query).status_code == 200
        assert len(list((settings.output_dir/'fits').iterdir())) == 2
        fixture(path, constant=True)
        assert client.get(root+'quality').status_code == 200
        assert len(list((settings.output_dir/'fits').iterdir())) == 3
    bad = ProductRegistry(tmp_path/'outputs', {'escape': {'path': '../input.fits'}})
    with pytest.raises(FileNotFoundError):
        bad.resolve('escape')
