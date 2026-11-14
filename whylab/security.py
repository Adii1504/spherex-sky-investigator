from urllib.parse import urlparse
import httpx
import ssl
import time
import truststore

class TrustedRetriever:
    """Inject into archive wrappers. No redirects; bounded bytes and timeout."""
    def __init__(self, hosts, timeout=30, max_bytes=50_000_000):
        self.hosts, self.timeout, self.max_bytes = set(hosts), timeout, max_bytes

    def validate(self, url):
        p = urlparse(url)
        if p.scheme != "https" or p.hostname not in self.hosts or p.username or p.password or p.port not in (None, 443):
            raise ValueError("Untrusted archive URL")

    def get(self, url):
        self.validate(url)
        deadline = time.monotonic() + self.timeout
        context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        with httpx.stream("GET", url, timeout=self.timeout, follow_redirects=False, trust_env=False, verify=context) as response:
            if response.is_redirect: raise ValueError("Archive redirects are disabled")
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                if time.monotonic() > deadline: raise TimeoutError("Download deadline exceeded")
                size += len(chunk)
                if size > self.max_bytes: raise ValueError("Cutout exceeds size limit")
                chunks.append(chunk)
            return b"".join(chunks)
