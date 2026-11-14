"""Start a real single-process Uvicorn server and exercise the public HTTP API."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


def main():
    root = Path(__file__).resolve().parents[1]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    env = {k: v for k, v in os.environ.items() if not k.startswith("WHYLAB_")}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with tempfile.TemporaryDirectory(prefix="whylab-smoke-") as folder:
        env["WHYLAB_OUTPUT_DIR"] = str(Path(folder) / "previews")
        with open(Path(folder) / "server.log", "w+") as log:
            runner = ("import sys, threading, uvicorn; "
                      "server = uvicorn.Server(uvicorn.Config('whylab.app:app', host='127.0.0.1', port=int(sys.argv[1]), workers=1)); "
                      "threading.Thread(target=lambda: (sys.stdin.buffer.read(1), setattr(server, 'should_exit', True)), daemon=True).start(); "
                      "server.run()")
            server = subprocess.Popen([sys.executable, "-c", runner, str(port)], cwd=root, env=env, stdin=subprocess.PIPE, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                for _ in range(100):
                    try:
                        with opener.open(base + "/api/v1/health", timeout=1) as response:
                            health = json.load(response)
                        break
                    except (urllib.error.URLError, ConnectionError):
                        if server.poll() is not None:
                            log.seek(0)
                            raise RuntimeError(log.read())
                        time.sleep(.1)
                else: raise RuntimeError("Server did not become ready")
                assert health["status"] == "ok"
                with opener.open(base + "/", timeout=2) as response:
                    assert b'SPHEREx WhyLab' in response.read()
                assert set(health["capabilities"].values()) == {"unavailable"}
                with opener.open(base + "/openapi.json", timeout=2) as response:
                    assert len(json.load(response)["paths"]) == 8
                request = urllib.request.Request(base + "/api/v1/observations/search", data=json.dumps({"ra_deg": 12, "dec_deg": -5, "fov_arcmin": 2}).encode(), headers={"Content-Type": "application/json"})
                try:
                    opener.open(request, timeout=2)
                    raise AssertionError("Missing adapter unexpectedly succeeded")
                except urllib.error.HTTPError as error:
                    assert error.code == 503
                    assert json.load(error)["code"] == "capability_unavailable"
                print("PASS: Uvicorn startup, HTTP health, React HTML, OpenAPI (8 paths), explicit archive 503")
            finally:
                if server.poll() is None:
                    server.stdin.write(b"x")
                    server.stdin.flush()
                try: server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()
                server.stdin.close()

if __name__ == "__main__": main()
