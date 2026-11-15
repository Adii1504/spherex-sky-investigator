"""Small result memoization; missing generated assets invalidate a cached result."""
from collections import OrderedDict
from copy import deepcopy
import threading
import os
from pathlib import Path


class ResultCache:
    def __init__(self, limit=32):
        self.limit = limit
        self.values = OrderedDict()
        self.lock = threading.RLock()

    def get(self, key):
        with self.lock:
            value = self.values.get(key)
            if value is None:
                return None
            payload, files = value
            try:
                if any(not path.is_file() or path.stat().st_size != size for path,size in files):
                    self.values.pop(key, None)
                    return None
                for directory in {path.parent for path,_ in files}:
                    os.utime(directory,None)
            except OSError:
                self.values.pop(key,None)
                return None
            self.values.move_to_end(key)
            return deepcopy(payload)

    def put(self, key, payload, root):
        root = Path(root).resolve()
        files = []
        def visit(value):
            if isinstance(value, dict):
                for item in value.values(): visit(item)
            elif isinstance(value, list):
                for item in value: visit(item)
            elif isinstance(value, str) and '/previews/' in value and value.startswith('/'):
                relative = value.split('/previews/',1)[1]
                path = (root / relative).resolve()
                if not path.is_relative_to(root) or not path.is_file():
                    raise ValueError('Generated result asset is unavailable')
                files.append((path,path.stat().st_size))
        visit(payload)
        with self.lock:
            self.values[key] = (deepcopy(payload),files)
            self.values.move_to_end(key)
            while len(self.values) > self.limit:
                self.values.popitem(last=False)
