import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

class Busy(Exception): pass

class Jobs:
    def __init__(self, settings):
        self.settings = settings
        self.pool = ThreadPoolExecutor(max_workers=settings.workers, thread_name_prefix="whylab")
        self.slots = threading.BoundedSemaphore(settings.workers + settings.max_pending)
        self.lock = threading.RLock()
        self.records = {}

    def submit(self, operation, retain=False, progress=None):
        with self.lock:
            if len(self.records) >= self.settings.cache_size:
                terminal = next((k for k, v in self.records.items() if v["status"] in ("succeeded", "failed")), None)
                if terminal is None: raise Busy()
                del self.records[terminal]
            if not self.slots.acquire(blocking=False): raise Busy()
            key = uuid.uuid4().hex
            record = {"job_id": key, "status": "queued", "progress": progress, "result": None, "error": None}
            self.records[key] = record
        def run():
            timer = None
            try:
                with self.lock: record["status"] = "running"
                def expire():
                    with self.lock:
                        if record["status"] == "running":
                            record.update(status="failed", error={"code": "job_timeout", "message": "Job exceeded execution deadline"})
                timer = threading.Timer(self.settings.timeout_seconds, expire)
                timer.daemon = True
                timer.start()
                result = operation()
                with self.lock:
                    if record["status"] == "running": record.update(status="succeeded", result=result)
            except Exception as exc:
                from .adapters import CapabilityUnavailable
                from .generated_cache import CacheCapacity
                import httpx
                code = ("capability_unavailable" if isinstance(exc, CapabilityUnavailable) else
                        "upstream_timeout" if isinstance(exc, (TimeoutError, httpx.TimeoutException)) else
                        "upstream_unreachable" if isinstance(exc, httpx.NetworkError) else
                        "upstream_http_error" if isinstance(exc, httpx.HTTPStatusError) else
                        "result_too_large" if isinstance(exc,CacheCapacity) else "processing_failed")
                message = {
                    "upstream_unreachable": "Cannot reach the upstream service. Check the server's network access and retry.",
                    "upstream_timeout": "The upstream service did not respond before the deadline. Retry or narrow the request.",
                    "upstream_http_error": "The upstream service returned an unsuccessful HTTP response. Retry later.",
                }.get(code, str(exc) if isinstance(exc,CacheCapacity) else "Adapter operation failed")
                if isinstance(exc,httpx.HTTPStatusError):
                    upstream=exc.response.status_code
                    service='NASA/IPAC IRSA' if exc.request.url.host=='irsa.ipac.caltech.edu' else 'The upstream service'
                    if upstream in (500,502,503,504):
                        message=f'{service} is temporarily unavailable (HTTP {upstream}). Retry later; restarting the application will not fix an upstream outage.'
                    elif upstream==429:
                        message=f'{service} is limiting requests (HTTP 429). Wait before retrying.'
                details = ({"capability": exc.capability} if isinstance(exc, CapabilityUnavailable) else
                           {"upstream_status": exc.response.status_code} if isinstance(exc, httpx.HTTPStatusError) else None)
                with self.lock:
                    if record["status"] == "running": record.update(status="failed", error={"code": code, "message": message, **({"details": details} if details else {})})
            finally:
                if timer: timer.cancel()
                self.slots.release()
        self.pool.submit(run)
        return record if retain else key

    def get(self, key):
        with self.lock:
            value = self.records.get(key)
            if value is None:return None
            result = dict(value)
            if isinstance(result['progress'],dict):result['progress']=dict(result['progress'])
            return result

    def close(self):
        self.pool.shutdown(wait=True, cancel_futures=True)
