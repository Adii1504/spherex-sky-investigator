"""Bound disposable image artifacts without touching source data or evidence."""
from pathlib import Path
import re


class CacheCapacity(ValueError):
    pass


def trim_directories(root, required, max_bytes, max_entries, protected=(), replacing=None):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if required > max_bytes or max_entries < 1:
        raise CacheCapacity('Generated result exceeds cache capacity; use fewer observations or a smaller image')
    candidates = []
    used = 0
    count = 0
    for directory in root.iterdir():
        if directory.name == replacing:
            continue
        # Only our hash-named, flat generated directories can be reclaimed.
        if (not re.fullmatch(r"[a-f0-9]{32}|[a-f0-9]{64}", directory.name)
                or directory.is_symlink() or directory.resolve().parent != root or not directory.is_dir()):
            continue
        files = list(directory.iterdir())
        if any(not f.is_file() or f.is_symlink() or f.suffix not in ('.png','.gif','.json') for f in files):
            continue
        size = sum(f.stat().st_size for f in files)
        used += size
        count += 1
        if directory.name not in protected:
            candidates.append((directory.stat().st_mtime_ns,directory,files,size))
    for _,directory,files,size in sorted(candidates):
        if used + required <= max_bytes and count < max_entries:
            break
        # Resolve and check again immediately before removing these generated files.
        if directory.resolve().parent != root or directory.is_symlink():
            continue
        try:
            for file in files:
                if file.resolve().parent != directory.resolve():
                    raise CacheCapacity('Generated cache contains an unexpected reference')
                file.unlink()
            directory.rmdir()
        except OSError:
            # Windows may briefly hold an image open while it is being served.
            # Reclaim another disposable entry instead of failing the request.
            continue
        used -= size
        count -= 1
    if used + required > max_bytes or count >= max_entries:
        raise CacheCapacity('Generated result exceeds cache capacity; use fewer observations or a smaller image')
