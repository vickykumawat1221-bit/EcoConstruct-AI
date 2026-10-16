"""
EcoConstruct AI - Carbon Calculation Module

This module provides carbon emission calculations for construction materials.
"""

from .carbon_calculator import (
    CarbonCalculator,
    MaterialEmission,
    ProjectTotal,
    MaterialComparison,
    create_calculator
)

__all__ = [
    'CarbonCalculator',
    'MaterialEmission',
    'ProjectTotal',
    'MaterialComparison',
    'create_calculator'
]
