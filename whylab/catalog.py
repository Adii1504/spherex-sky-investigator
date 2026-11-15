"""Bounded SIMBAD TAP adapter. Clients supply names/coordinates, never ADQL."""
from collections import OrderedDict, deque
from datetime import datetime, timezone
import hashlib
import json
import threading
import time
from urllib.parse import urlencode, quote, urlsplit
from fastapi import Query
from .security import TrustedRetriever


class Simbad:
    def __init__(self, settings):
        self.url = settings.simbad_tap_url
        self.retriever = TrustedRetriever(settings.catalog_hosts, min(settings.timeout_seconds, 12), 2_000_000)
        self.retriever.validate(self.url)
        self.cache, self.calls = OrderedDict(), deque()
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(2)

    def search(self, name=None, ra=None, dec=None, radius=.1):
        if name:
            # A fixed exact-name template; escaping is in addition to HTTP validation.
            condition = "b.oid=i.oidref AND i.id='" + name.replace("'", "''") + "'"
            tables = "basic AS b JOIN ident AS i ON b.oid=i.oidref"
        else:
            tables = "basic AS b"
            condition = f"1=CONTAINS(POINT('ICRS',b.ra,b.dec),CIRCLE('ICRS',{ra:.10f},{dec:.10f},{radius:.10f}))"
        sql = f"SELECT TOP 50 b.main_id,b.ra,b.dec,b.otype,b.coo_bibcode FROM {tables} WHERE {condition} ORDER BY main_id"
        now = time.monotonic()
        with self.lock:
            cached = self.cache.get(sql)
            if cached and now - cached[0] < 900:
                self.cache.move_to_end(sql)
                return {**cached[1], "cached": True}
            while self.calls and now - self.calls[0] > 60:
                self.calls.popleft()
            if len(self.calls) >= 20:
                raise CatalogBusy()
            self.calls.append(now)
        if not self.slots.acquire(blocking=False):
            raise CatalogBusy()
        try:
            data = json.loads(self.retriever.get(self.url + '?' + urlencode({
                'request': 'doQuery', 'lang': 'ADQL', 'format': 'json', 'maxrec': 50, 'query': sql})))
            fields = [c['name'].lower() for c in data['metadata']]
            if not {'main_id', 'ra', 'dec', 'otype', 'coo_bibcode'} <= set(fields):
                raise ValueError('Unexpected SIMBAD schema')
            targets = []
            for values in data['data'][:50]:
                row = dict(zip(fields, values))
                import math
                if not all(isinstance(row[k], (float, int)) and math.isfinite(row[k]) for k in ('ra', 'dec')):
                    continue
                if not (0 <= row['ra'] < 360 and -90 <= row['dec'] <= 90):
                    continue
                identifier = row['main_id']
                targets.append({'id': 'simbad-' + hashlib.sha256(identifier.encode()).hexdigest()[:20],
                    'name': identifier, 'source_identifier': identifier, 'object_type': row['otype'],
                    'ra_deg': row['ra'], 'dec_deg': row['dec'], 'coordinate_frame': 'ICRS',
                    'reference_epoch': 'J2000', 'coordinate_reference': row['coo_bibcode'],
                    'source': 'SIMBAD / CDS', 'provisional': True, 'distance': None,
                    'astrometry_status': 'Catalogue position; observation association unverified',
                    'references': [{'label': 'SIMBAD catalogue record', 'url':
                        'https://' + urlsplit(self.url).hostname + '/simbad/sim-id?Ident=' + quote(identifier, safe='')}]})
            result = {'targets': targets, 'provider': 'SIMBAD / CDS', 'cached': False,
                      'retrieved_at': datetime.now(timezone.utc).isoformat(),
                      'limit': 50, 'possibly_truncated': len(data['data']) >= 50}
            with self.lock:
                self.cache[sql] = (time.monotonic(), result)
                while len(self.cache) > 128:
                    self.cache.popitem(last=False)
            return result
        finally:
            self.slots.release()


class CatalogBusy(Exception):
    pass


def install(app, settings, error):
    provider = Simbad(settings)
    app.state.catalog = provider

    @app.get('/api/catalog/search')
    def search(name: str | None = Query(None, min_length=1, max_length=100, pattern=r'^[ -~]+$'),
               ra: float | None = Query(None, ge=0, lt=360, allow_inf_nan=False),
               dec: float | None = Query(None, ge=-90, le=90, allow_inf_nan=False),
               radius: float = Query(.1, gt=0, le=.5, allow_inf_nan=False)):
        if (name is not None and (ra is not None or dec is not None)) or (name is None and (ra is None or dec is None)):
            raise error(422, 'invalid_request', 'Supply an exact name OR both RA and Dec; cone radius is at most 0.5 degrees')
        if name is not None and not name.strip():
            raise error(422, 'invalid_request', 'Name cannot be blank')
        try:
            return provider.search(name.strip() if name else None, ra, dec, radius)
        except CatalogBusy:
            raise error(429, 'catalog_rate_limit', 'Catalogue request limit reached; retry after one minute')
        except Exception:
            raise error(502, 'catalog_unavailable', 'SIMBAD lookup failed. Bundled targets and local FITS inspection remain available.')
