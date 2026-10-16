"""Filesystem layout for EcoConstruct AI.

Three modules read datasets, and they sit at different depths:

    simulation.py / cost_data.py / dashboard.py   -> project root
    backend/carbon_calculator.py                   -> project root/backend (Member 2)

Member 2's own loader resolves `data/materials.csv` relative to itself and is
already correct, so it is left untouched. This module exists for the
root-level modules, which would otherwise resolve `data/` one directory too
high.

Instead of hard-coding "go up one level" - which is exactly the assumption that
breaks the moment a file moves - we walk up from this file until we find a
directory that contains `data/materials.csv`. That directory is the project
root, and it stays correct whether the caller lives at the root or in a
subpackage.
"""

from __future__ import annotations

import os

# File that always marks the project root. Chosen because Member 2's dataset
# is the one file the whole project cannot run without.
ROOT_MARKER = os.path.join("data", "materials.csv")

#: Absolute path of the project root. This module lives at the project root,
#: so one level up from this file is the root itself.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

#: Absolute path of the project root's `data/` directory.
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

#: Member 2's emission-factor dataset.
MATERIALS_CSV = os.path.join(DATA_DIR, "materials.csv")

#: Member 4's unit-cost dataset.
COSTS_CSV = os.path.join(DATA_DIR, "material_costs.csv")

#: Member 1's Vite frontend, relative to the project root.
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")


def find_project_root(start: str | None = None) -> str:
    """Walk up from `start` until ROOT_MARKER is found; fall back to this file.

    Args:
        start: Directory to begin the search from. Defaults to the directory
            containing this module.

    Returns:
        Absolute path of the project root.

    Raises:
        FileNotFoundError: if no ancestor directory contains ROOT_MARKER.
    """
    current = os.path.abspath(start or os.path.dirname(os.path.abspath(__file__)))

    while True:
        if os.path.exists(os.path.join(current, ROOT_MARKER)):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            # Reached the filesystem root without finding the marker.
            raise FileNotFoundError(
                f"Could not locate the project root: no ancestor of {current} "
                f"contains {ROOT_MARKER}."
            )
        current = parent
