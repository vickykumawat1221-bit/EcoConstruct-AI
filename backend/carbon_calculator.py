"""
EcoConstruct AI - Carbon Calculation Engine

This module provides carbon emission calculations for construction materials.
It supports dataset loading, validation, emissions calculations, project totals,
material comparisons, and carbon hotspot analysis.
"""

import pandas as pd
from typing import Dict, List, Optional, Union, Tuple
from dataclasses import dataclass
import os


@dataclass
class MaterialEmission:
    """Result of a single material emission calculation."""
    material_id: str
    material_name: str
    quantity: float
    unit: str
    emission_factor: float
    factor_unit: str
    emissions_kg_co2e: float
    share_of_total: Optional[float] = None


@dataclass
class ProjectTotal:
    """Result of a multi-material project emission calculation."""
    total_emissions_kg_co2e: float
    total_emissions_tonnes_co2e: float
    emissions_by_material: Dict[str, MaterialEmission]
    emissions_by_category: Dict[str, float]
    material_percentages: Dict[str, float]
    category_percentages: Dict[str, float]


@dataclass
class MaterialComparison:
    """Result of comparing two materials."""
    baseline_material_id: str
    baseline_material_name: str
    baseline_emissions: float
    alternative_material_id: str
    alternative_material_name: str
    alternative_emissions: float
    absolute_reduction: float
    percentage_reduction: float


class CarbonCalculator:
    """Main carbon calculation engine."""
    
    REQUIRED_COLUMNS = [
        'material_id', 'material_name', 'category', 'unit',
        'emission_factor', 'factor_unit', 'verification_status'
    ]
    
    def __init__(self, dataset_path: str = None):
        """
        Initialize the carbon calculator.
        
        Args:
            dataset_path: Path to the materials CSV file. If None, uses default path.
        """
        if dataset_path is None:
            # Default to data/materials.csv relative to this file
            module_dir = os.path.dirname(os.path.abspath(__file__))
            dataset_path = os.path.join(
                os.path.dirname(module_dir), 'data', 'materials.csv'
            )
        
        self.dataset_path = dataset_path
        self.materials_df: Optional[pd.DataFrame] = None
        self._load_dataset()
    
    def _load_dataset(self) -> None:
        """Load and validate the materials dataset."""
        if not os.path.exists(self.dataset_path):
            raise FileNotFoundError(
                f"Dataset file not found: {self.dataset_path}"
            )
        
        try:
            self.materials_df = pd.read_csv(self.dataset_path)
        except Exception as e:
            raise ValueError(f"Failed to read CSV file: {e}")
        
        self._validate_dataset()
    
    def _validate_dataset(self) -> None:
        """Validate the dataset structure and content."""
        if self.materials_df is None:
            raise ValueError("Dataset not loaded")
        
        # Check required columns
        missing_columns = [
            col for col in self.REQUIRED_COLUMNS 
            if col not in self.materials_df.columns
        ]
        if missing_columns:
            raise ValueError(
                f"Missing required columns: {missing_columns}"
            )
        
        # Check for duplicate material IDs
        if self.materials_df['material_id'].duplicated().any():
            duplicates = self.materials_df[
                self.materials_df['material_id'].duplicated()
            ]['material_id'].tolist()
            raise ValueError(
                f"Duplicate material IDs found: {duplicates}"
            )
        
        # Validate emission factors are non-negative
        if (self.materials_df['emission_factor'] < 0).any():
            invalid = self.materials_df[
                self.materials_df['emission_factor'] < 0
            ]['material_id'].tolist()
            raise ValueError(
                f"Negative emission factors found for materials: {invalid}"
            )
        
        # Validate emission factors are numeric
        if not pd.api.types.is_numeric_dtype(self.materials_df['emission_factor']):
            raise ValueError("Emission factor column must be numeric")
    
    def get_material(self, material_id: str, 
                     allow_unverified: bool = False) -> pd.Series:
        """
        Get a material by ID.
        
        Args:
            material_id: The material ID to look up
            allow_unverified: Whether to allow unverified emission factors
            
        Returns:
            Pandas Series with material data
            
        Raises:
            ValueError: If material not found or validation fails
        """
        if self.materials_df is None:
            raise ValueError("Dataset not loaded")
        
        material = self.materials_df[
            self.materials_df['material_id'] == material_id
        ]
        
        if material.empty:
            raise ValueError(f"Material ID not found: {material_id}")
        
        material = material.iloc[0]
        
        # Check verification status
        if not allow_unverified and material['verification_status'] != 'verified':
            raise ValueError(
                f"Material {material_id} has unverified emission factor. "
                "Set allow_unverified=True to use it."
            )
        
        # Check for missing emission factor
        if pd.isna(material['emission_factor']):
            raise ValueError(
                f"Material {material_id} has missing emission factor"
            )
        
        return material
    
    def calculate_emissions(
        self,
        material_id: str,
        quantity: float,
        quantity_unit: str = None,
        allow_unverified: bool = False
    ) -> MaterialEmission:
        """
        Calculate emissions for a single material.
        
        Formula: Emissions (kg CO2e) = Quantity × Emission factor
        
        Args:
            material_id: The material ID
            quantity: The quantity of material used
            quantity_unit: The unit of the quantity (must match material's unit)
            allow_unverified: Whether to allow unverified emission factors
            
        Returns:
            MaterialEmission object with calculation results
            
        Raises:
            ValueError: If inputs are invalid or units are incompatible
        """
        # Validate quantity
        if quantity is None:
            raise ValueError("Quantity cannot be None")
        
        if not isinstance(quantity, (int, float)):
            raise ValueError(f"Quantity must be numeric, got {type(quantity)}")
        
        if quantity < 0:
            raise ValueError(f"Quantity cannot be negative: {quantity}")
        
        if quantity == 0:
            raise ValueError("Quantity cannot be zero")
        
        # Get material data
        material = self.get_material(material_id, allow_unverified)
        
        # Validate unit compatibility if quantity_unit is provided
        if quantity_unit is not None:
            if quantity_unit != material['unit']:
                raise ValueError(
                    f"Quantity unit '{quantity_unit}' does not match material unit '{material['unit']}'. "
                    f"Material {material_id} requires quantities in {material['unit']}."
                )
        
        # Calculate emissions
        emissions = quantity * material['emission_factor']
        
        return MaterialEmission(
            material_id=material['material_id'],
            material_name=material['material_name'],
            quantity=quantity,
            unit=material['unit'],
            emission_factor=material['emission_factor'],
            factor_unit=material['factor_unit'],
            emissions_kg_co2e=emissions
        )
    
    def calculate_project_total(
        self,
        materials: List[Dict[str, Union[str, float]]],
        allow_unverified: bool = False
    ) -> ProjectTotal:
        """
        Calculate total emissions for a project with multiple materials.
        
        Args:
            materials: List of dicts with 'material_id' and 'quantity'
            allow_unverified: Whether to allow unverified emission factors
            
        Returns:
            ProjectTotal object with aggregated results
            
        Raises:
            ValueError: If inputs are invalid or project is empty
        """
        if not materials:
            raise ValueError("Project cannot be empty")
        
        emissions_by_material = {}
        emissions_by_category = {}
        
        # Calculate emissions for each material
        for item in materials:
            material_id = item['material_id']
            quantity = item['quantity']
            
            emission = self.calculate_emissions(
                material_id, quantity, quantity_unit=None, allow_unverified=allow_unverified
            )
            emissions_by_material[material_id] = emission
            
            # Group by category
            material = self.get_material(material_id, allow_unverified)
            category = material['category']
            emissions_by_category[category] = (
                emissions_by_category.get(category, 0) + emission.emissions_kg_co2e
            )
        
        # Calculate totals
        total_kg = sum(e.emissions_kg_co2e for e in emissions_by_material.values())
        total_tonnes = total_kg / 1000
        
        # Calculate percentages
        material_percentages = {
            mat_id: (emission.emissions_kg_co2e / total_kg * 100) if total_kg > 0 else 0
            for mat_id, emission in emissions_by_material.items()
        }
        
        category_percentages = {
            cat: (emissions / total_kg * 100) if total_kg > 0 else 0
            for cat, emissions in emissions_by_category.items()
        }
        
        # Add share of total to each material emission
        for mat_id, emission in emissions_by_material.items():
            emission.share_of_total = material_percentages[mat_id]
        
        return ProjectTotal(
            total_emissions_kg_co2e=total_kg,
            total_emissions_tonnes_co2e=total_tonnes,
            emissions_by_material=emissions_by_material,
            emissions_by_category=emissions_by_category,
            material_percentages=material_percentages,
            category_percentages=category_percentages
        )
    
    def compare_materials(
        self,
        baseline_material_id: str,
        alternative_material_id: str,
        quantity: float,
        allow_unverified: bool = False
    ) -> MaterialComparison:
        """
        Compare emissions between a baseline and alternative material.
        
        Args:
            baseline_material_id: The baseline material ID
            alternative_material_id: The alternative material ID
            quantity: The quantity to compare (must be in compatible units)
            allow_unverified: Whether to allow unverified emission factors
            
        Returns:
            MaterialComparison object with comparison results
            
        Raises:
            ValueError: If inputs are invalid or units are incompatible
        """
        # Calculate baseline emissions
        baseline_emission = self.calculate_emissions(
            baseline_material_id, quantity, quantity_unit=None, allow_unverified=allow_unverified
        )
        
        # Calculate alternative emissions
        alternative_emission = self.calculate_emissions(
            alternative_material_id, quantity, quantity_unit=None, allow_unverified=allow_unverified
        )
        
        # Check unit compatibility
        baseline_mat = self.get_material(baseline_material_id, allow_unverified)
        alt_mat = self.get_material(alternative_material_id, allow_unverified)
        
        if baseline_mat['unit'] != alt_mat['unit']:
            raise ValueError(
                f"Cannot compare materials with different units: "
                f"{baseline_mat['unit']} vs {alt_mat['unit']}. "
                "Ensure quantities are in compatible units."
            )
        
        # Calculate reductions
        absolute_reduction = baseline_emission.emissions_kg_co2e - alternative_emission.emissions_kg_co2e
        
        if baseline_emission.emissions_kg_co2e > 0:
            percentage_reduction = (
                absolute_reduction / baseline_emission.emissions_kg_co2e * 100
            )
        else:
            percentage_reduction = 0.0
        
        return MaterialComparison(
            baseline_material_id=baseline_material_id,
            baseline_material_name=baseline_mat['material_name'],
            baseline_emissions=baseline_emission.emissions_kg_co2e,
            alternative_material_id=alternative_material_id,
            alternative_material_name=alt_mat['material_name'],
            alternative_emissions=alternative_emission.emissions_kg_co2e,
            absolute_reduction=absolute_reduction,
            percentage_reduction=percentage_reduction
        )
    
    def analyze_hotspots(
        self,
        materials: List[Dict[str, Union[str, float]]],
        allow_unverified: bool = False
    ) -> List[MaterialEmission]:
        """
        Identify carbon hotspots by ranking materials by emissions.
        
        Args:
            materials: List of dicts with 'material_id' and 'quantity'
            allow_unverified: Whether to allow unverified emission factors
            
        Returns:
            List of MaterialEmission objects sorted by emissions (highest first)
        """
        if not materials:
            raise ValueError("Cannot analyze hotspots for empty project")
        
        # Calculate emissions for all materials
        emissions_list = []
        for item in materials:
            material_id = item['material_id']
            quantity = item['quantity']
            
            emission = self.calculate_emissions(
                material_id, quantity, quantity_unit=None, allow_unverified=allow_unverified
            )
            emissions_list.append(emission)
        
        # Sort by emissions (highest first)
        emissions_list.sort(
            key=lambda x: x.emissions_kg_co2e, 
            reverse=True
        )
        
        return emissions_list
    
    def get_all_materials(self, verified_only: bool = True) -> pd.DataFrame:
        """
        Get all materials from the dataset.
        
        Args:
            verified_only: If True, return only verified materials
            
        Returns:
            DataFrame of materials
        """
        if self.materials_df is None:
            raise ValueError("Dataset not loaded")
        
        if verified_only:
            return self.materials_df[
                self.materials_df['verification_status'] == 'verified'
            ].copy()
        return self.materials_df.copy()
    
    def get_materials_by_category(self, category: str, 
                                   verified_only: bool = True) -> pd.DataFrame:
        """
        Get materials filtered by category.
        
        Args:
            category: The category to filter by
            verified_only: If True, return only verified materials
            
        Returns:
            DataFrame of materials in the category
        """
        if self.materials_df is None:
            raise ValueError("Dataset not loaded")
        
        filtered = self.materials_df[
            self.materials_df['category'] == category
        ]
        
        if verified_only:
            filtered = filtered[
                filtered['verification_status'] == 'verified'
            ]
        
        return filtered.copy()


def create_calculator(dataset_path: str = None) -> CarbonCalculator:
    """
    Factory function to create a CarbonCalculator instance.
    
    Args:
        dataset_path: Optional path to the materials CSV file
        
    Returns:
        CarbonCalculator instance
    """
    return CarbonCalculator(dataset_path)
