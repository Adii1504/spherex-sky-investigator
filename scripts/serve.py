"""Container entry point: honor the host's PORT and retain one shared-state worker."""
import os
import sys


def main():
    port = int(os.environ.get("PORT", "8000"))
    if not 1 <= port <= 65535:
        raise SystemExit("PORT must be between 1 and 65535")
    os.execvp(sys.executable, [
        sys.executable, "-m", "uvicorn", "whylab.app:app",
        "--host", "0.0.0.0", "--port", str(port), "--workers", "1",
    ])


if __name__ == "__main__":
    main()
