"""IRSA SIA2 and IBE integration. No synthetic fallback."""
from collections import OrderedDict
from datetime import timezone
import hashlib
import io
import math
import re
import threading
import time
from urllib.parse import urlencode, urlsplit
import numpy as np
from astropy.io.votable import parse
from astropy.time import Time
from .models import Observation, Provenance, SearchResult, Cutout

COLLECTIONS = {"spherex_dr1", "spherex_dr1_deep", "spherex_qr3", "spherex_qr3_deep"}
PRODUCT = re.compile(r"level2_(\d{4}W\d{2}_[0-9][A-Z]_\d{4}_[1-4])D([1-6])_spx_(l2b-v[\w.-]+)\.fits$")

class IRSAArchive:
    available = True

    def __init__(self, settings, retriever):
        if not settings.archive_collections or not set(settings.archive_collections) <= COLLECTIONS:
            raise ValueError("Only supported SPHEREx spectral-image collections are allowed")
        self.settings, self.retriever = settings, retriever
        self.cache = OrderedDict()
        self.cache_bytes = 0
        self.lock = threading.RLock()

    def search(self, query):
        observations, warnings, queried = {}, [], []
        deadline = time.monotonic() + self.settings.timeout_seconds
        for collection in self.settings.archive_collections:
            if time.monotonic() > deadline: raise TimeoutError("Archive search deadline exceeded")
            params = {"COLLECTION": collection, "POS": f"CIRCLE {query.ra_deg} {query.dec_deg} {query.fov_arcmin / 60 / math.sqrt(2)}", "MAXREC": self.settings.max_observations + 1}
            if query.start_utc or query.end_utc:
                lo = Time(query.start_utc).mjd if query.start_utc else "-Inf"
                hi = Time(query.end_utc).mjd if query.end_utc else "+Inf"
                params["TIME"] = f"{lo} {hi}"
            document = parse(io.BytesIO(self.retriever.get("https://irsa.ipac.caltech.edu/SIA?" + urlencode(params))))
            statuses = [info for resource in document.resources for info in resource.infos if info.name == "QUERY_STATUS"]
            if any(str(i.value).upper() == "ERROR" for i in statuses): raise ValueError("IRSA rejected SIA query")
            if any(str(i.value).upper() == "OVERFLOW" for i in statuses): warnings.append(f"{collection}: archive result truncated")
            queried.append(collection)
            tables = list(document.iter_tables())
            if not tables: raise ValueError("IRSA returned no result table")
            table = tables[0].to_table(use_names_over_ids=True)
            for row in table:
                def get(name):
                    value = row[name] if name in table.colnames else None
                    return None if value is None or np.ma.is_masked(value) else value
                url = str(get("access_url") or "")
                self.retriever.validate(url)
                parsed = urlsplit(url)
                if not parsed.path.startswith("/ibe/data/spherex/") or parsed.query or parsed.fragment: raise ValueError("Unexpected SPHEREx access URL")
                match = PRODUCT.fullmatch(parsed.path.rsplit("/", 1)[-1])
                if not match: raise ValueError("Cannot establish canonical SPHEREx exposure identity")
                exposure, detector, version = match.groups()
                timestamp = get("t_min")
                if timestamp is None: continue
                start = Time(float(timestamp), format="mjd").to_datetime(timezone=timezone.utc)
                end_mjd = get("t_max")
                end = Time(float(end_mjd), format="mjd").to_datetime(timezone=timezone.utc) if end_mjd is not None else start
                if query.start_utc and end < query.start_utc or query.end_utc and start > query.end_utc: continue
                lo, hi = get("em_min"), get("em_max")
                identifier = hashlib.sha256(url.encode()).hexdigest()[:24]
                observations[identifier] = Observation(id=identifier, exposure_id="spherex:" + exposure, observed_at=start, release=collection, product_id=parsed.path.rsplit("/", 1)[-1], detector=detector, provenance=Provenance(archive="NASA/IPAC IRSA", source_url=url, citation="SPHEREx public spectral image products"), file_wavelength_um=(float(lo) * 1e6, float(hi) * 1e6) if lo is not None and hi is not None else None, position_wavelength_um=None, quality={"calibration_level": int(get("calib_level")) if get("calib_level") is not None else None, "pipeline_product_version": version})
            if len(observations) >= self.settings.max_observations:
                warnings.append("Observation limit reached; narrow dates or field for additional coverage")
                break
        ordered = sorted(observations.values(), key=lambda o: (o.observed_at, o.detector or ""))[:self.settings.max_observations]
        if not ordered: warnings.append("No SPHEREx spectral images found for this query")
        warnings.append("File wavelength ranges are not selected-position wavelengths; search coverage may include only part of the field")
        return SearchResult(observations=ordered, coverage_summary={"count": len(ordered), "collections_queried": queried, "collections_configured": self.settings.archive_collections, "search_shape": "cone enclosing requested square", "complete": not any("truncat" in w or "limit reached" in w for w in warnings) and len(queried) == len(self.settings.archive_collections)}, warnings=warnings)

    def cutout(self, observation, sky):
        url = observation.provenance.source_url
        self.retriever.validate(url)
        p = urlsplit(url)
        if not p.path.startswith("/ibe/data/spherex/") or not PRODUCT.fullmatch(p.path.rsplit("/", 1)[-1]) or p.query or p.fragment:
            raise ValueError("Invalid stored SPHEREx product")
        key = hashlib.sha256((url + sky.model_dump_json()).encode()).hexdigest()
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key].model_copy(deep=True)
        params = {"center": f"{sky.ra_deg},{sky.dec_deg}", "size": sky.fov_arcmin / 60, "gzip": "false"}
        data = self.retriever.get(url + "?" + urlencode(params))
        if len(data) > self.settings.max_cutout_bytes: raise ValueError("Cutout too large")
        if not data.startswith(b"SIMPLE"): raise ValueError("Archive response is not a FITS image")
        result = Cutout(observation_id=observation.id, data=data, media_type="application/fits", metadata={"service": "IRSA IBE", "fov_arcmin": sky.fov_arcmin, "product_id": observation.product_id})
        with self.lock:
            # Another worker may have fetched the same immutable cutout.
            if key in self.cache: return self.cache[key].model_copy(deep=True)
            if len(data) <= self.settings.max_archive_cache_bytes:
                while self.cache and (self.cache_bytes + len(data) > self.settings.max_archive_cache_bytes or len(self.cache) >= self.settings.cache_size):
                    _, removed = self.cache.popitem(last=False)
                    self.cache_bytes -= len(removed.data)
                self.cache[key] = result
                self.cache_bytes += len(data)
        return result.model_copy(deep=True)
