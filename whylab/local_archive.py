"""Explicit searches of approved local FITS; never an automatic archive fallback."""
import hashlib
import re
import math
from datetime import timezone

import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS

from .models import Cutout, Observation, Provenance, SearchResult


def align_results(local, remote, limit):
    """Match exact pipeline-product names; never infer identity from proximity."""
    def product(observation):
        name = (observation.quality or {}).get('label') or observation.product_id
        match = re.search(r'(level2_\d{4}W\d{2}_[0-9][A-Z]_\d{4}_[1-4]D[1-6]_spx_l2b(?:_retry)?-v[\w.-]+\.fits)$', name)
        return match[1] if match else None

    by_product = {product(o):o for o in remote.observations if product(o)}
    observations, matched, used = [], 0, set()
    for observation in local.observations:
        found = by_product.get(product(observation)) if product(observation) else None
        if found:
            used.add(found.id)
            if observation.release == 'imported-local':
                matched += 1
                observation = observation.model_copy(update={'quality':{
                    **(observation.quality or {}), 'archive_match':{
                        'product_id':found.product_id, 'source_url':found.provenance.source_url,
                        'method':'exact pipeline product identity; file bytes and source identity not independently verified'}}})
        observations.append(observation)
    known = {o.id for o in observations}
    known_products = {product(o) for o in observations if product(o)}
    additional = []
    for observation in remote.observations:
        identity = product(observation)
        if observation.id in used or observation.id in known or identity and identity in known_products:
            continue
        additional.append(observation)
        known.add(observation.id)
        if identity:
            known_products.add(identity)
    room = max(0, limit-len(observations))
    observations.extend(additional[:room])
    truncated = len(additional)>room
    return SearchResult(observations=observations, coverage_summary={
        **local.coverage_summary, 'source':'local-and-archive', 'archive_contacted':True,
        'complete':bool(remote.coverage_summary.get('complete')) and not truncated,
        'count':len(observations), 'archive_matches':matched,
        'archive_added':min(room,len(additional)), 'archive_coverage':remote.coverage_summary,
    }, warnings=[
        'Downloaded observations were loaded first and reconciled with IRSA by exact pipeline product identity.',
        'Local file bytes are retained; metadata matches do not verify source identification or file equality.',
        'Downloaded images contain the query centre; full-field coverage is not guaranteed.',
    ] + remote.warnings + (['Combined observation limit reached.'] if truncated else []))


class LocalArchive:
    def __init__(self, registry, settings):
        self.registry, self.settings = registry, settings

    def target_query(self, target_id, query):
        positions = [entry.get('predicted_position') for entry in self.registry.entries.values()
            if entry.get('target_id') == target_id and entry.get('predicted_position')]
        if not positions:
            raise KeyError(target_id)
        vectors = [SkyCoord(p['ra_deg']*u.deg,p['dec_deg']*u.deg).cartesian.xyz.value for p in positions]
        x,y,z = [sum(v[i] for v in vectors)/len(vectors) for i in range(3)]
        return query.model_copy(update={'ra_deg':math.degrees(math.atan2(y,x))%360,
            'dec_deg':math.degrees(math.atan2(z,math.hypot(x,y)))})

    def search(self, query, target_id=None):
        observations, skipped, fields = [], 0, {}
        for identifier, entry in self.registry.entries.items():
            if target_id and entry.get('target_id') != target_id:
                continue
            try:
                path, _ = self.registry.resolve(identifier)
                if not entry.get('sha256'):
                    continue
                with fits.open(path, memmap=True) as hdus:
                    image = hdus['IMAGE']
                    height, width = image.shape
                    wcs = WCS(image.header).celestial
                    entry_target = entry.get('target_id')
                    if entry_target and entry_target not in fields:
                        centre = wcs.pixel_to_world((width-1)/2, (height-1)/2).icrs
                        fields[entry_target] = {'target_id':entry_target,
                            'label':entry.get('dataset', {}).get('adopted_astrometry', {}).get('target_name') or entry_target,
                            'ra_deg':float(centre.ra.deg), 'dec_deg':float(centre.dec.deg),
                            'fov_arcmin':query.fov_arcmin}
                    x, y = wcs.world_to_pixel(SkyCoord(query.ra_deg*u.deg, query.dec_deg*u.deg))
                    inside = bool(-.5 <= x < width-.5 and -.5 <= y < height-.5)
                    if not inside and not target_id:
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
                        'label': filename, 'coverage': 'query centre inside image' if inside else 'supplied target association; query centre outside image',
                        'query_centre_inside':inside, 'dataset':entry.get('dataset'),
                        'predicted_position':entry.get('predicted_position'),
                        'association_status':entry.get('provenance_status')}))
            except (OSError, ValueError, KeyError, TypeError):
                skipped += 1
        observations.sort(key=lambda item: (item.observed_at, item.id))
        count = len(observations)
        return SearchResult(observations=observations[:self.settings.max_observations],
            coverage_summary={'source':'imported-local', 'complete':False,
                'count':min(count,self.settings.max_observations), 'matching_files':count,
                'files_skipped':skipped, 'target_id':target_id,
                'coverage_rule':'supplied target dataset; per-image coverage reported' if target_id else 'query centre inside actual FITS image',
                'archive_contacted':False, 'available_fields':list(fields.values())}, warnings=[
                'Only downloaded local observations were searched; this is not a live archive result.',
                'Per-image geometry and supplied target associations are reported; full-field coverage is not guaranteed.' if target_id else 'Images contain the query centre; coverage of the entire requested field is not guaranteed.',
                'Source association and motion remain unconfirmed. UTC is assumed when TIMESYS is absent.',
            ] + (['Target dataset selected using supplied observation-epoch positions, not static catalogue coordinates.'] if target_id else [])
              + ([f'{skipped} local files could not be checked.'] if skipped else []))

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
