"""SPHEREx WhyLab Processing Module."""
import os
from pathlib import Path
from threading import RLock

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parents[2] / ".data" / "mplcache"))
# Matplotlib's global pyplot state is shared by API and bounded worker threads.
PROCESSING_LOCK = RLock()
