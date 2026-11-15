# Supplied dataspace research scripts

All 26 Python files here are byte-for-byte copies of the files supplied by the
user. `source_inventory.json` records their SHA-256 hashes, along with the 40
historical reference tables/reports in `reference_metadata/`. Those historical
tables include superseded coordinates and excluded products; the application
imports only the separately checked `final_dataset` package.

The scripts are a research toolset, not a FastAPI application. Several execute
queries, downloads, prompts, or output writes at module scope. The server never
imports or executes them. In particular, `main.py` is an archive downloader,
and `retry_rdraconis_download.py` prompts for a URL.

See [dataset integration](../../docs/dataspace-integration.md) for importing the
package, preparing an isolated workspace, and running the offline validation
pipeline. All original script names are retained so sibling imports work.
