"""Convenient local launcher; .env values are parsed literally, never executed."""
import os
import argparse
from pathlib import Path
import re
import uvicorn

def main():
    parser = argparse.ArgumentParser(description="Run the combined WhyLab explorer and scientific processing viewer")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    config = Path(".env") if Path(".env").is_file() else Path(".env.example")
    if config.is_file():
        for line in config.read_text(encoding="utf-8").splitlines():
            match = re.fullmatch(r"(WHYLAB_[A-Z_]+)=(.*)", line.strip())
            if match: os.environ.setdefault(match[1], match[2])
    uvicorn.run("whylab.app:app", host="127.0.0.1", port=args.port, workers=1)

if __name__ == "__main__": main()
