"""Synchronous adapters run only in bounded workers; never in the event loop."""
from typing import Protocol
from .models import (Search, SearchResult, Observation, Sky, Cutout,
                     ProcessedSequence, VerificationResult)

class CapabilityUnavailable(Exception):
    def __init__(self, capability: str):
        self.capability = capability

class ArchiveAdapter(Protocol):
    available: bool
    def search(self, query: Search) -> SearchResult: ...
    def cutout(self, observation: Observation, sky: Sky) -> Cutout: ...

class SequenceAdapter(Protocol):
    available: bool
    def process(self, observations: list[Observation], cutouts: list[Cutout], sky: Sky) -> ProcessedSequence: ...

class MotionAdapter(Protocol):
    available: bool
    def verify(self, training: list[Observation], reserved: list[Observation], sky: Sky, archive: ArchiveAdapter) -> VerificationResult: ...

class Unavailable:
    available = False
    def __init__(self, capability): self.capability = capability
    def __getattr__(self, name):
        def missing(*args, **kwargs): raise CapabilityUnavailable(self.capability)
        return missing
