"""Convenient local launcher; .env values are parsed literally, never executed."""
import os
from pathlib import Path
import re
import uvicorn

def main():
    config = Path(".env") if Path(".env").is_file() else Path(".env.example")
    if config.is_file():
        for line in config.read_text(encoding="utf-8").splitlines():
            match = re.fullmatch(r"(WHYLAB_[A-Z_]+)=(.*)", line.strip())
            if match: os.environ.setdefault(match[1], match[2])
    uvicorn.run("whylab.app:app", host="127.0.0.1", port=8000, workers=1)

if __name__ == "__main__": main()
