"""Explicit searches of approved local FITS; never an automatic archive fallback."""
import hashlib
import re
from datetime import timezone

import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS

from .models import Cutout, Observation, Provenance, SearchResult


class LocalArchive:
    def __init__(self, registry, settings):
        self.registry, self.settings = registry, settings

    def search(self, query):
        observations, skipped, fields = [], 0, {}
        for identifier, entry in self.registry.entries.items():
            try:
                path, _ = self.registry.resolve(identifier)
                if not entry.get('sha256'):
                    continue
                with fits.open(path, memmap=True) as hdus:
                    image = hdus['IMAGE']
                    height, width = image.shape
                    wcs = WCS(image.header).celestial
                    target_id = entry.get('target_id')
                    if target_id and target_id not in fields:
                        centre = wcs.pixel_to_world((width-1)/2, (height-1)/2).icrs
                        fields[target_id] = {'target_id':target_id,
                            'label':entry.get('dataset', {}).get('adopted_astrometry', {}).get('target_name') or target_id,
                            'ra_deg':float(centre.ra.deg), 'dec_deg':float(centre.dec.deg),
                            'fov_arcmin':query.fov_arcmin}
                    x, y = wcs.world_to_pixel(SkyCoord(query.ra_deg*u.deg, query.dec_deg*u.deg))
                    if not (-.5 <= x < width-.5 and -.5 <= y < height-.5):
                        continue
                    date = image.header.get('DATE-OBS', hdus[0].header.get('DATE-OBS'))
                    scale = str(image.header.get('TIMESYS', hdus[0].header.get('TIMESYS', 'UTC'))).lower()
                    if not date:
                        raise ValueError('Missing observation date')
                    observed = Time(date, scale=scale).utc.to_datetime(timezone.utc)
                    if query.start_utc and observed < query.start_utc or query.end_utc and observed > query.end_utc:
                        continue
                    filename = entry.get('dataset', {}).get('filename') or entry.get('label', path.name)
                    canonical = re.search(r'level2_(\d{4}W\d{2}_[0-9][A-Z]_\d{4}_[1-4])D[1-6]_spx_', filename)
                    # Unknown identities cannot be used to claim independent exposures.
                    exposure = 'spherex:' + canonical[1] if canonical else 'local:unknown-exposure'
                    detector = image.header.get('DETECTOR', hdus[0].header.get('DETECTOR'))
                observations.append(Observation(
                    id=identifier, product_id=identifier, exposure_id=exposure,
                    release='imported-local', observed_at=observed,
                    detector=str(detector) if detector is not None else None,
                    footprint_stcs=entry.get('footprint_stcs'),
                    provenance=Provenance(archive='Downloaded local SPHEREx FITS',
                        source_url='/api/observations/' + identifier + '/fits',
                        citation='Imported real observation; supplied source association is unconfirmed.'),
                    file_wavelength_um=entry.get('observation', {}).get('file_wavelength_um'),
                    quality={'sha256': entry['sha256'], 'source': 'imported-local',
                        'label': filename, 'coverage': 'query centre inside image'}))
            except (OSError, ValueError, KeyError, TypeError):
                skipped += 1
        observations.sort(key=lambda item: (item.observed_at, item.id))
        count = len(observations)
        return SearchResult(observations=observations[:self.settings.max_observations],
            coverage_summary={'source':'imported-local', 'complete':False,
                'count':min(count,self.settings.max_observations), 'matching_files':count,
                'files_skipped':skipped, 'coverage_rule':'query centre inside actual FITS image',
                'archive_contacted':False, 'available_fields':list(fields.values())}, warnings=[
                'Only downloaded local observations were searched; this is not a live archive result.',
                'Images contain the query centre; coverage of the entire requested field is not guaranteed.',
                'Source association and motion remain unconfirmed. UTC is assumed when TIMESYS is absent.',
            ] + ([f'{skipped} local files could not be checked.'] if skipped else []))

    def cutout(self, observation, sky):
        path, entry = self.registry.resolve(observation.id)
        if path.stat().st_size > self.settings.max_cutout_bytes:
            raise ValueError('Local FITS exceeds cutout byte budget')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry.get('sha256'):
            raise ValueError('Local FITS checksum mismatch')
        return Cutout(observation_id=observation.id, data=data, media_type='application/fits',
            metadata={'source':'imported-local', 'sha256':entry['sha256'],
                'note':'Original downloaded FITS; processing applies the requested output field.'})
