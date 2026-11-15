"""Prepare an isolated, runnable copy of the supplied research toolset and data."""
import argparse
import json
from pathlib import Path
import shutil

from whylab.config import Settings
from whylab.dataset import safe_path, sha256, verify_package
from whylab.fits_preview.routes import ProductRegistry


def prepare(root, workspace):
    root, workspace = Path(root).resolve(), Path(workspace).resolve()
    if workspace.exists():
        raise ValueError("Workspace already exists; choose a new --workspace to retain earlier outputs")
    registry = ProductRegistry.load(root)
    packages = {entry["dataset"]["package_sha256"] for entry in registry.entries.values()
                if entry.get("dataset", {}).get("name") == "SPHEREx dataspace"}
    if len(packages) != 1:
        raise ValueError("Import exactly one dataspace package before preparing a workspace")
    package = root / "datasets" / ("dataspace-" + next(iter(packages))[:20])
    checksums = verify_package(package)
    tools = Path(__file__).resolve().parents[1] / "tools" / "dataspace"
    inventory = json.loads((tools / "source_inventory.json").read_text(encoding="utf-8"))
    for item in inventory["files"]:
        if sha256(safe_path(tools, item["filename"])) != item["sha256"]:
            raise ValueError("Preserved source inventory mismatch: " + item["filename"])
    workspace.mkdir(parents=True)
    for item in inventory["files"]:
        name = item["filename"]
        destination = workspace / ("data/metadata/" + Path(name).name if name.startswith("reference_metadata/") else name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tools / name, destination)
    # Final reviewed tables take precedence over historical reference tables.
    for name in checksums:
        if name.startswith("fits/"):
            destination = workspace / "data" / "observations" / Path(name).name
        elif name.startswith("metadata/"):
            destination = workspace / "data" / name
        else:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(package / name, destination)
    print("Prepared research workspace:", workspace)
    print("Run scripts with this directory as your working directory.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Settings.from_env().output_dir.resolve().parent)
    parser.add_argument("--workspace", type=Path, default=Path(".data/dataspace_work"))
    args = parser.parse_args()
    try:
        prepare(args.root, args.workspace)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Workspace preparation failed: {exc}\n")


if __name__ == "__main__":
    main()
