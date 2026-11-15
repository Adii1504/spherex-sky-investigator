"""Server-owned local product registry and bounded, identity-keyed artifact cache."""
import hashlib
import json
import threading
import os
from concurrent.futures import Future
from pathlib import Path
from fastapi import Depends, Query
from fastapi.responses import FileResponse, Response
from ..generated_cache import trim_directories, CacheCapacity
from .reader import read, json_safe
from .quality import report
from .preview import render


class ProductRegistry:
    """Trusted local manifest only. Paths are never accepted from HTTP callers."""
    def __init__(self, root, entries=None):
        self.root = Path(root).resolve()
        self.entries = entries or {}

    @classmethod
    def load(cls, root):
        path = Path(root) / "fits_manifest.json"
        return cls(root, json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {})

    def resolve(self, product_id):
        entry = self.entries.get(product_id)
        if entry is None:
            raise KeyError(product_id)
        path = (self.root / entry["path"]).resolve()
        if not path.is_relative_to(self.root) or not path.is_file():
            raise FileNotFoundError("Approved product file unavailable")
        return path, entry


class ArtifactCache:
    def __init__(self, settings, registry):
        self.settings, self.registry = settings, registry
        self.root = settings.output_dir.resolve() / "fits"
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.inflight = {}

    def artifacts(self, product_id, override=None, radius=3., size=512):
        return self.payloads(product_id, override, radius, size)[0]

    def payloads(self, product_id, override=None, radius=3., size=512):
        path, entry = self.registry.resolve(product_id)
        position = override or entry.get("predicted_position") or {
            "ra_deg": None, "dec_deg": None, "astrometry_status": "unavailable"}
        # Validate trusted-manifest coordinates with the same rules as overrides.
        position = validate_position(position)
        identity = path.stat()
        if identity.st_size > self.settings.max_cutout_bytes:
            raise ValueError("FITS product exceeds configured byte limit")
        key = hashlib.sha256(json.dumps(["fits-preview-3", product_id, entry, str(path), identity.st_dev,
            identity.st_ino, identity.st_size, identity.st_mtime_ns, identity.st_ctime_ns,
            position, radius, size, "p1-p99-asinh10-native"], sort_keys=True, allow_nan=False).encode()).hexdigest()
        with self.lock:
            directory = self.root / key
            if all((directory / name).is_file() for name in ("preview.png", "metadata.json", "quality_report.json")):
                try:
                    payloads = {name:(directory/name).read_bytes() for name in ('preview.png','metadata.json','quality_report.json')}
                    if not payloads['preview.png'].startswith(b'\x89PNG'):
                        raise ValueError('Incomplete preview')
                    json.loads(payloads['metadata.json']); json.loads(payloads['quality_report.json'])
                    os.utime(directory,None)
                    return directory,payloads
                except (OSError, ValueError):
                    pass  # A damaged generated artifact is regenerated from its source.
            future = self.inflight.get(key)
            owner = future is None
            if owner:
                future = Future()
                self.inflight[key] = future
        if not owner:
            return future.result()
        try:
            # Only requests for this exact product wait; other products can render.
            frame = read(path)
            quality = report(frame, position, radius)
            quality.update(product_id=product_id, label=entry.get("label"),
                           provenance_status=entry.get("provenance_status", "unconfirmed"))
            png, rendering = render(frame, quality, size)
            metadata = json_safe({**frame.metadata, "product_id": product_id,
                "position": position, "rendering": rendering,
                "label": entry.get("label"), "provenance_status": entry.get("provenance_status", "unconfirmed")})
            payloads = {"preview.png": png,
                "metadata.json": json.dumps(metadata, allow_nan=False, indent=2).encode(),
                "quality_report.json": json.dumps(quality, allow_nan=False, indent=2).encode()}
            if len(png) > self.settings.max_preview_bytes:
                raise CacheFull()
            # Source identity must remain unchanged during processing.
            after = path.stat()
            if (after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_ino) != (identity.st_size, identity.st_mtime_ns, identity.st_ctime_ns, identity.st_ino):
                raise ValueError("Product changed during processing")
            with self.lock:
                try:
                    other_bytes = sum(p.stat().st_size for p in self.settings.output_dir.glob('*.png'))
                    trim_directories(self.root,sum(map(len,payloads.values())),
                        max(0,self.settings.max_output_bytes-other_bytes),self.settings.cache_size,
                        protected=self.inflight,replacing=key)
                except CacheCapacity as exc:
                    raise CacheFull() from exc
                directory.mkdir(exist_ok=True)
                for name, data in payloads.items():
                    temporary = directory / (name+'.tmp')
                    temporary.write_bytes(data)
                    temporary.replace(directory/name)
                value = (directory,payloads)
                future.set_result(value)
                return value
        except BaseException as exc:
            with self.lock:
                for name in ('preview.png.tmp','metadata.json.tmp','quality_report.json.tmp'):
                    temporary = directory/name
                    try:
                        if temporary.is_file() and temporary.resolve().parent == directory.resolve():
                            temporary.unlink()
                    except OSError:
                        pass
            future.set_exception(exc)
            raise
        finally:
            with self.lock:
                self.inflight.pop(key,None)


class CacheFull(Exception):
    pass


def validate_position(position):
    from pydantic import BaseModel, ConfigDict, Field, model_validator
    class Position(BaseModel):
        model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
        ra_deg: float | None = Field(default=None, ge=0, lt=360)
        dec_deg: float | None = Field(default=None, ge=-90, le=90)
        astrometry_status: str = Field(min_length=1, max_length=120, pattern=r"^[ -~]+$")

        @model_validator(mode="after")
        def pair(self):
            if (self.ra_deg is None) != (self.dec_deg is None):
                raise ValueError("Both predicted coordinates are required")
            return self
    return Position.model_validate(position).model_dump()


def install(app, settings, registry, error):
    cache = ArtifactCache(settings, registry or ProductRegistry.load(settings.output_dir.parent))
    app.state.fits_preview = cache
    from ..targets import install as install_targets
    install_targets(app, cache.registry, error)

    def options(ra_deg: float | None = Query(None, ge=0, lt=360, allow_inf_nan=False),
                dec_deg: float | None = Query(None, ge=-90, le=90, allow_inf_nan=False),
                astrometry_status: str | None = Query(None, min_length=1, max_length=120, pattern=r"^[ -~]+$"),
                aperture_radius: float = Query(3., gt=0, le=512, allow_inf_nan=False),
                render_size: int = Query(512, ge=32, le=1024)):
        values = (ra_deg, dec_deg, astrometry_status)
        if any(v is not None for v in values) and not all(v is not None for v in values):
            raise error(422, "invalid_request", "Overrides require ra_deg, dec_deg and astrometry_status together")
        position = None if ra_deg is None else dict(ra_deg=ra_deg, dec_deg=dec_deg, astrometry_status=astrometry_status)
        return position, aperture_radius, render_size

    def get(product_id, opts):
        try:
            return cache.payloads(product_id, *opts)[1]
        except KeyError:
            raise error(404, "product_not_found", "Product not found")
        except FileNotFoundError:
            raise error(503, "product_unavailable", "Approved FITS file unavailable")
        except CacheFull:
            raise error(503, "cache_full", "This FITS result exceeds the preview budget. Try a smaller render size.")
        except Exception:
            raise error(422, "fits_processing_failed", "FITS product or stored prediction could not be processed")

    # Synchronous endpoints are executed in FastAPI's thread pool, not the async loop.
    @app.get("/api/observations/{product_id}/preview")
    def preview(product_id: str, opts=Depends(options)):
        return Response(get(product_id, opts)['preview.png'], media_type="image/png")

    @app.get("/api/observations/{product_id}/quality")
    def quality(product_id: str, opts=Depends(options)):
        return json.loads(get(product_id, opts)['quality_report.json'])

    @app.get("/api/observations/{product_id}/fits")
    def download_fits(product_id: str):
        try:
            path, entry = cache.registry.resolve(product_id)
        except KeyError:
            raise error(404, "product_not_found", "Product not found")
        except FileNotFoundError:
            raise error(503, "product_unavailable", "Approved FITS file unavailable")
        return FileResponse(path, media_type="application/fits", filename=path.name)
