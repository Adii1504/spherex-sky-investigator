from urllib.parse import urlparse
import httpx
import ssl
import time
import truststore
import threading

class TrustedRetriever:
    """Inject into archive wrappers. No redirects; bounded bytes and timeout."""
    def __init__(self, hosts, timeout=30, max_bytes=50_000_000):
        self.hosts, self.timeout, self.max_bytes = set(hosts), timeout, max_bytes
        self._client = None
        self._client_lock = threading.Lock()

    def client(self):
        with self._client_lock:
            if self._client is None:
                context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                self._client = httpx.Client(timeout=self.timeout,follow_redirects=False,trust_env=False,verify=context)
            return self._client

    def close(self):
        with self._client_lock:
            if self._client is not None:
                self._client.close()
                self._client = None

    def validate(self, url):
        p = urlparse(url)
        if p.scheme != "https" or p.hostname not in self.hosts or p.username or p.password or p.port not in (None, 443):
            raise ValueError("Untrusted archive URL")

    def get(self, url):
        self.validate(url)
        deadline = time.monotonic() + self.timeout
        client = self.client()
        for attempt in range(2):
            remaining = deadline - time.monotonic()
            if remaining <= 0: raise TimeoutError("Download deadline exceeded")
            try:
                with client.stream("GET", url, timeout=remaining) as response:
                    if response.is_redirect: raise ValueError("Archive redirects are disabled")
                    response.raise_for_status()
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        if time.monotonic() > deadline: raise TimeoutError("Download deadline exceeded")
                        size += len(chunk)
                        if size > self.max_bytes: raise ValueError("Cutout exceeds size limit")
                        chunks.append(chunk)
                    return b"".join(chunks)
            except httpx.HTTPStatusError as exc:
                if attempt or exc.response.status_code not in (502, 503, 504) or deadline-time.monotonic() <= .25:
                    raise
                time.sleep(.2)
