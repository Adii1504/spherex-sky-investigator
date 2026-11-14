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

    def submit(self, operation, retain=False):
        with self.lock:
            if len(self.records) >= self.settings.cache_size:
                terminal = next((k for k, v in self.records.items() if v["status"] in ("succeeded", "failed")), None)
                if terminal is None: raise Busy()
                del self.records[terminal]
            if not self.slots.acquire(blocking=False): raise Busy()
            key = uuid.uuid4().hex
            record = {"job_id": key, "status": "queued", "progress": None, "result": None, "error": None}
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
                import httpx
                code = ("capability_unavailable" if isinstance(exc, CapabilityUnavailable) else
                        "upstream_timeout" if isinstance(exc, (TimeoutError, httpx.TimeoutException)) else "processing_failed")
                with self.lock:
                    if record["status"] == "running": record.update(status="failed", error={"code": code, "message": "Adapter operation failed", **({"details": {"capability": exc.capability}} if isinstance(exc, CapabilityUnavailable) else {})})
            finally:
                if timer: timer.cancel()
                self.slots.release()
        self.pool.submit(run)
        return record if retain else key

    def get(self, key):
        with self.lock:
            value = self.records.get(key)
            return dict(value) if value else None

    def close(self):
        self.pool.shutdown(wait=True, cancel_futures=True)
