from __future__ import annotations

from pathlib import Path
import shutil


def copy_installable_checkout(source: Path, destination: Path) -> Path:
    """Copy a checkout without carrying runtime/build residue into an install probe."""

    def ignore_runtime_residue(_directory: str, names: list[str]) -> set[str]:
        ignored = {
            name
            for name in names
            if name in {".git", ".research-artifacts", ".venv", "__pycache__", "build", "dist"}
            or name.endswith(".egg-info")
            or name.endswith((".pyc", ".pyo"))
        }
        return ignored

    shutil.copytree(source, destination, ignore=ignore_runtime_residue)
    return destination
