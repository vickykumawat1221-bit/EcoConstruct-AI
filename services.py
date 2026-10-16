"""Shared, lazily-constructed service instances.

Member 2's `CarbonCalculator` reads and validates its CSV in `__init__`, and
Member 4's `CostData` does the same. Building one of those per request would
re-read both datasets on every dashboard poll, so the app keeps a single
instance of each and hands the same engine to every module.

This is also the seam tests use: `reset_services()` drops the cached instances
so a test can point the app at a fixture dataset without leaking that dataset
into the next test.
"""

from __future__ import annotations

from typing import Optional

from cost_data import CostData
from dashboard import DashboardBuilder
from simulation import SimulationEngine

_engine: Optional[SimulationEngine] = None
_dashboard_builder: Optional[DashboardBuilder] = None


def get_cost_data() -> CostData:
    """The shared cost table. Reads the CSV on first use only."""
    return get_engine().costs


def get_engine() -> SimulationEngine:
    """The shared simulation engine, which owns the carbon calculator too."""
    global _engine
    if _engine is None:
        _engine = SimulationEngine()
    return _engine


def get_dashboard_builder() -> DashboardBuilder:
    """The shared dashboard builder, sharing the one engine."""
    global _dashboard_builder
    if _dashboard_builder is None:
        _dashboard_builder = DashboardBuilder(engine=get_engine())
    return _dashboard_builder


def reset_services() -> None:
    """Drop cached instances. Called between tests that swap datasets."""
    global _engine, _dashboard_builder
    _engine = None
    _dashboard_builder = None
