"""Synthetic FITS and archive responses exclusively for automated tests."""
import io
from datetime import datetime, timezone
import numpy as np
import pytest
from astropy.io import fits
from astropy.io.votable import from_table, writeto
from astropy.table import Table
from astropy.wcs import WCS
from whylab.archive import IRSAArchive
from whylab.science import BasicScience, ExploratoryMotion
from whylab.config import Settings
from whylab.models import Sky, Search, Cutout, Observation, Provenance

SKY = Sky(ra_deg=12, dec_deg=-5, fov_arcmin=2)

def observation(i):
    return Observation(id=str(i), exposure_id=f"test-{i}", observed_at=datetime(2025,1,i,tzinfo=timezone.utc), release="TEST ONLY", product_id=f"test-{i}", detector="1", provenance=Provenance(archive="TEST ONLY",source_url="https://irsa.ipac.caltech.edu/test"))

def cutout(i, dx=0, shift=0, wavelength=1.0, bad=False):
    n=64
    w=WCS(naxis=2)
    w.wcs.crpix=[32.5+shift,32.5]
    w.wcs.cdelt=[-2/60/n,2/60/n]
    w.wcs.crval=[12,-5]
    w.wcs.ctype=['RA---TAN','DEC--TAN']
    header=w.to_header()
    header['BUNIT']='MJy/sr'
    header['CUNIT1W']='um'
    y,x=np.indices((n,n))
    rng=np.random.default_rng(2026)
    image=10+rng.normal(0,.1,(n,n))+30*np.exp(-((x-(31.5+shift+dx))**2+(y-31.5)**2)/4)
    flags=np.full((n,n),1<<21,dtype=np.int32)
    if bad: flags[:,:]=64
    flag_hdu=fits.ImageHDU(flags,name='FLAGS')
    flag_hdu.header['MSKN0021']='SOURCE'
    flag_hdu.header['MSKN0006']='NONFUNC'
    xs=np.array([1,n],dtype=np.int32)
    values=np.zeros((2,2,2));values[:,:,0]=wavelength;values[:,:,1]=.05
    wave=fits.BinTableHDU.from_columns([fits.Column(name='X',format='2J',array=[xs]),fits.Column(name='Y',format='2J',array=[xs]),fits.Column(name='VALUES',format='8E',dim='(2,2,2)',array=[values])],name='WCS-WAVE')
    hdus=fits.HDUList([fits.PrimaryHDU(),fits.ImageHDU(image,header=header,name='IMAGE'),flag_hdu,fits.ImageHDU(np.ones((n,n)),name='VARIANCE'),wave])
    buffer=io.BytesIO();hdus.writeto(buffer)
    return Cutout(observation_id=str(i),data=buffer.getvalue(),media_type='application/fits')

def test_wcs_alignment_and_source_flag(tmp_path):
    science=BasicScience(Settings(output_dir=tmp_path,preview_pixels=64))
    a=science.frame(observation(1),cutout(1),SKY)
    b=science.frame(observation(2),cutout(2,shift=7),SKY)
    assert a.valid.mean()>.9
    assert a.metadata['position_wavelength_um']==pytest.approx(1)
    # Same sky source remains aligned even though detector CRPIX shifted 7 pixels.
    assert np.linalg.norm(np.array(np.unravel_index(np.nanargmax(a.image),a.image.shape))-np.array(np.unravel_index(np.nanargmax(b.image),b.image.shape)))<=1.5
    with pytest.raises(ValueError): science.frame(observation(3),cutout(3,bad=True),SKY)

def test_wavelength_incompatible_difference_is_rejected(tmp_path):
    science=BasicScience(Settings(output_dir=tmp_path,preview_pixels=64))
    result=science.process([observation(1),observation(2)],[cutout(1),cutout(2,wavelength=2)],SKY)
    assert not result.measurements['comparisons'][1]['difference_valid']
    assert result.measurements['comparisons'][1]['wavelength_compatible_pixels']==0
    assert result.warnings

def test_matching_wavelength_difference(tmp_path):
    science=BasicScience(Settings(output_dir=tmp_path,preview_pixels=64))
    result=science.process([observation(1),observation(2)],[cutout(1),cutout(2)],SKY)
    comparison=result.measurements['comparisons'][1]
    assert comparison['difference_valid']
    assert comparison['difference_rms']==pytest.approx(0,abs=1e-8)

def test_training_fit_is_independent_of_reserved_pixels(tmp_path):
    science=BasicScience(Settings(output_dir=tmp_path,preview_pixels=64))
    class Archive:
        reserved_shift=1.5
        def cutout(self,o,sky):return cutout(int(o.id),dx=(int(o.id)-1)*.5 if o.id!='4' else self.reserved_shift)
    archive=Archive();motion=ExploratoryMotion(science)
    training=[observation(i) for i in [1,2,3]]
    first=motion.verify(training,[observation(4)],SKY,archive)
    archive.reserved_shift=3
    second=motion.verify(training,[observation(4)],SKY,archive)
    assert first.measurements['fit'] is not None
    assert first.measurements['fit']==second.measurements['fit']
    assert len(first.measurements['reserved'])==1
    assert second.measurements['reserved'][0]['residual_arcsec']>first.measurements['reserved'][0]['residual_arcsec']
    assert first.outcome==second.outcome=='insufficient_evidence'

def test_insufficient_motion_does_not_download(tmp_path):
    class Archive:
        def cutout(self,*args): pytest.fail('Should not retrieve insufficient training set')
    result=ExploratoryMotion(BasicScience(Settings(output_dir=tmp_path))).verify([observation(1)],[observation(2)],SKY,Archive())
    assert result.outcome=='insufficient_evidence'
    assert result.measurements['fit'] is None

def sia_bytes():
    table=Table({'access_url':['https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/2025W18_1B/l2b-v27-2026-196/1/level2_2025W18_1B_0162_1D1_spx_l2b-v27-2026-196.fits'], 't_min':[60794.593497], 't_max':[60794.594829], 'em_min':[.75e-6], 'em_max':[1.1e-6], 'calib_level':[2]})
    b=io.BytesIO();writeto(from_table(table),b);return b.getvalue()

def test_real_adapter_mapping_and_bounded_cache(tmp_path):
    class Retriever:
        calls=[]
        def validate(self,url):
            assert url.startswith('https://irsa.ipac.caltech.edu/')
        def get(self,url):
            self.calls.append(url)
            return sia_bytes() if '/SIA?' in url else cutout(1).data
    settings=Settings(output_dir=tmp_path,archive_collections=['spherex_dr1'],max_archive_cache_bytes=250000)
    retriever=Retriever();archive=IRSAArchive(settings,retriever)
    result=archive.search(Search(**SKY.model_dump()))
    o=result.observations[0]
    assert o.exposure_id=='spherex:2025W18_1B_0162_1'
    assert o.detector=='1'
    assert o.file_wavelength_um==pytest.approx((.75,1.1))
    assert o.position_wavelength_um is None
    assert o.observed_at.tzinfo is not None
    first=archive.cutout(o,SKY);second=archive.cutout(o,SKY)
    assert first.data==second.data
    assert len(retriever.calls)==2
    assert archive.cache_bytes<=settings.max_archive_cache_bytes
