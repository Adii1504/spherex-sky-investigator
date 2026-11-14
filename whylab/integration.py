"""Opt-in built-in real-data adapters, replaceable by teammate wrappers."""
from .archive import IRSAArchive
from .science import BasicScience, ExploratoryMotion

def build_adapters(settings, trusted_retriever):
    trusted_retriever.max_bytes = settings.max_cutout_bytes
    science = BasicScience(settings)
    return IRSAArchive(settings, trusted_retriever), science, ExploratoryMotion(science)
