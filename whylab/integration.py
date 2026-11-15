"""Opt-in built-in real-data adapters, replaceable by teammate wrappers."""
def build_adapters(settings, trusted_retriever):
    from teammate_integration import build_adapters as science_adapters
    return science_adapters(settings, trusted_retriever)
