"""Pytest configuration for the whole project.

The modules sit at the project root (`main.py`, `simulation.py`, ...) while
Member 2's engine is a package (`backend/carbon_calculator.py`) and Member 4's
new tests live in `tests/`. Putting the project root on `sys.path` here means
`import main` and `from backend.carbon_calculator import ...` both work no
matter which directory pytest was invoked from.

Member 3's existing tests at the root are left exactly as they were; this file
only guarantees they can be collected from the same run as everyone else's.
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
