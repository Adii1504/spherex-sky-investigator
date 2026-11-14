import os
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class Settings:
    max_fov_arcmin: float = 30
    max_observations: int = 100
    workers: int = 2
    max_pending: int = 8
    timeout_seconds: float = 60
    cache_size: int = 128
    max_preview_bytes: int = 10_000_000
    max_output_bytes: int = 100_000_000
    max_sequence_bytes: int = 100_000_000
    max_cutout_bytes: int = 50_000_000
    max_archive_cache_bytes: int = 100_000_000
    preview_pixels: int = 192
    archive_collections: list[str] = field(default_factory=lambda: ["spherex_dr1", "spherex_qr3"])
    frontend_dir: Path = Path("frontend/dist")
    output_dir: Path = Path(".data/previews")
    cors_origins: list[str] = field(default_factory=list)
    trusted_hosts: list[str] = field(default_factory=lambda: ["irsa.ipac.caltech.edu"])

    def __post_init__(self):
        for key in ("max_fov_arcmin", "max_observations", "workers", "max_pending", "timeout_seconds", "cache_size", "max_preview_bytes", "max_output_bytes", "max_sequence_bytes", "max_cutout_bytes", "max_archive_cache_bytes", "preview_pixels"):
            value = getattr(self, key)
            if value <= 0 or not __import__("math").isfinite(value):
                raise ValueError(f"{key} must be finite and positive")

        if not 16 <= self.preview_pixels <= 512:
            raise ValueError("preview_pixels must be between 16 and 512")

    @classmethod
    def from_env(cls):
        values = {}
        for key in cls.__dataclass_fields__:
            raw = os.getenv("WHYLAB_" + key.upper())
            if raw is None: continue
            if key in ("cors_origins", "trusted_hosts", "archive_collections"): values[key] = [s.strip() for s in raw.split(",") if s.strip()]
            elif key in ("output_dir", "frontend_dir"): values[key] = Path(raw)
            elif key in ("timeout_seconds", "max_fov_arcmin"): values[key] = float(raw)
            else: values[key] = int(raw)
        return cls(**values)
