"""Writable source/output libraries for developer and installed applications."""
import os
from pathlib import Path

def workspaceRoot():
    override = os.environ.get("CT3D_WORKSPACE_ROOT")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    source_root = Path(__file__).resolve().parents[2]
    if (source_root / "CT3D_产品原则.md").is_file():
        return str(source_root)
    # Installed applications may live in read-only Program Files.
    return os.path.join(os.path.expanduser("~"), "CT3D")

def inputDirectory():
    path = os.path.join(workspaceRoot(), "input")
    os.makedirs(path, exist_ok=True)
    return path

def outputPath(filename=""):
    path = os.path.join(workspaceRoot(), "output")
    os.makedirs(path, exist_ok=True)
    return os.path.join(path, filename) if filename else path
