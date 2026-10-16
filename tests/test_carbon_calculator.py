"""
Tests for EcoConstruct AI Carbon Calculator

This test suite covers:
- Basic emissions calculation
- Multiple-material project totals
- Conversion between kg CO2e and tonnes CO2e
- Material comparisons
- Absolute and percentage reductions
- Carbon hotspot ranking
- Invalid and negative quantities
- Unknown material IDs
- Missing and unverified factors
- Incompatible units
- Empty input and zero-emission cases
- Dataset validation
"""

import pytest
import pandas as pd
import os
import tempfile
from backend.carbon_calculator import (
    CarbonCalculator,
    MaterialEmission,
    ProjectTotal,
    MaterialComparison,
    create_calculator
)


@pytest.fixture
def test_dataset():
    """Create a temporary test dataset with known emission factors."""
    data = {
        'material_id': ['TEST001', 'TEST002', 'TEST003', 'TEST004'],
        'material_name': ['Test Cement', 'Test Concrete', 'Test Steel', 'Unverified Material'],
        'category': ['Binders', 'Structural', 'Reinforcing', 'Structural'],
        'material_variant': ['Ordinary', 'C30', 'Rebar', 'Experimental'],
        'unit': ['kg', 'm3', 'kg', 'kg'],
        'emission_factor': [0.82, 280.0, 1.8, 5.0],
        'factor_unit': ['kg CO2e/kg', 'kg CO2e/m3', 'kg CO2e/kg', 'kg CO2e/kg'],
        'lifecycle_boundary': ['Cradle-to-gate', 'Cradle-to-gate', 'Cradle-to-gate', 'Cradle-to-gate'],
        'geography': ['Global', 'Global', 'Global', 'Global'],
        'source_name': ['Test Source', 'Test Source', 'Test Source', 'Test Source'],
        'source_url': ['http://test.com', 'http://test.com', 'http://test.com', 'http://test.com'],
        'source_year': [2023, 2023, 2023, 2023],
        'assumptions_or_notes': ['Test note', 'Test note', 'Test note', 'Test note'],
        'verification_status': ['verified', 'verified', 'verified', 'unverified']
    }
    df = pd.DataFrame(data)
    
    # Write to temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        df.to_csv(f.name, index=False)
        return f.name


@pytest.fixture
def calculator(test_dataset):
    """Create a CarbonCalculator instance with test data."""
    return CarbonCalculator(test_dataset)


class TestDatasetLoading:
    """Test dataset loading and validation."""
    
    def test_load_valid_dataset(self, test_dataset):
        """Test loading a valid dataset."""
        calc = CarbonCalculator(test_dataset)
        assert calc.materials_df is not None
        assert len(calc.materials_df) == 4
    
    def test_load_nonexistent_file(self):
        """Test loading a file that doesn't exist."""
        with pytest.raises(FileNotFoundError):
            CarbonCalculator('nonexistent_file.csv')
    
    def test_duplicate_material_ids(self):
        """Test detection of duplicate material IDs."""
        data = {
            'material_id': ['TEST001', 'TEST001'],
            'material_name': ['Test 1', 'Test 2'],
            'category': ['Binders', 'Binders'],
            'unit': ['kg', 'kg'],
            'emission_factor': [0.82, 0.82],
            'factor_unit': ['kg CO2e/kg', 'kg CO2e/kg'],
            'verification_status': ['verified', 'verified']
        }
        df = pd.DataFrame(data)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            df.to_csv(f.name, index=False)
            with pytest.raises(ValueError, match="Duplicate material IDs"):
                CarbonCalculator(f.name)
    
    def test_negative_emission_factor(self):
        """Test detection of negative emission factors."""
        data = {
            'material_id': ['TEST001'],
            'material_name': ['Test'],
            'category': ['Binders'],
            'unit': ['kg'],
            'emission_factor': [-0.82],
            'factor_unit': ['kg CO2e/kg'],
            'verification_status': ['verified']
        }
        df = pd.DataFrame(data)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            df.to_csv(f.name, index=False)
            with pytest.raises(ValueError, match="Negative emission factors"):
                CarbonCalculator(f.name)
    
    def test_missing_required_columns(self):
        """Test detection of missing required columns."""
        data = {
            'material_id': ['TEST001'],
            'material_name': ['Test']
        }
        df = pd.DataFrame(data)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            df.to_csv(f.name, index=False)
            with pytest.raises(ValueError, match="Missing required columns"):
                CarbonCalculator(f.name)


class TestBasicEmissionsCalculation:
    """Test basic emissions calculation for single materials."""
    
    def test_calculate_emissions(self, calculator):
        """Test basic emissions calculation."""
        result = calculator.calculate_emissions('TEST001', 100.0)
        assert result.material_id == 'TEST001'
        assert result.material_name == 'Test Cement'
        assert result.quantity == 100.0
        assert result.emission_factor == 0.82
        assert result.emissions_kg_co2e == 82.0
    
    def test_calculate_emissions_with_integer(self, calculator):
        """Test emissions calculation with integer quantity."""
        result = calculator.calculate_emissions('TEST001', 100)
        assert result.emissions_kg_co2e == 82.0
    
    def test_negative_quantity(self, calculator):
        """Test that negative quantities are rejected."""
        with pytest.raises(ValueError, match="Quantity cannot be negative"):
            calculator.calculate_emissions('TEST001', -10.0)
    
    def test_zero_quantity(self, calculator):
        """Test that zero quantities are rejected."""
        with pytest.raises(ValueError, match="Quantity cannot be zero"):
            calculator.calculate_emissions('TEST001', 0.0)
    
    def test_none_quantity(self, calculator):
        """Test that None quantities are rejected."""
        with pytest.raises(ValueError, match="Quantity cannot be None"):
            calculator.calculate_emissions('TEST001', None)
    
    def test_nonnumeric_quantity(self, calculator):
        """Test that non-numeric quantities are rejected."""
        with pytest.raises(ValueError, match="Quantity must be numeric"):
            calculator.calculate_emissions('TEST001', "100")
    
    def test_unknown_material_id(self, calculator):
        """Test that unknown material IDs are rejected."""
        with pytest.raises(ValueError, match="Material ID not found"):
            calculator.calculate_emissions('UNKNOWN', 100.0)
    
    def test_unverified_material_rejected_by_default(self, calculator):
        """Test that unverified materials are rejected by default."""
        with pytest.raises(ValueError, match="unverified emission factor"):
            calculator.calculate_emissions('TEST004', 100.0)
    
    def test_unverified_material_allowed(self, calculator):
        """Test that unverified materials can be used when explicitly allowed."""
        result = calculator.calculate_emissions('TEST004', 100.0, allow_unverified=True)
        assert result.material_id == 'TEST004'
        assert result.emissions_kg_co2e == 500.0
    
    def test_calculate_emissions_with_matching_unit(self, calculator):
        """Test emissions calculation with matching unit specified."""
        result = calculator.calculate_emissions('TEST001', 100.0, quantity_unit='kg')
        assert result.material_id == 'TEST001'
        assert result.emissions_kg_co2e == 82.0
    
    def test_calculate_emissions_with_mismatched_unit(self, calculator):
        """Test that mismatched units are rejected."""
        with pytest.raises(ValueError, match="Quantity unit 'tons' does not match material unit 'kg'"):
            calculator.calculate_emissions('TEST001', 100.0, quantity_unit='tons')
    
    def test_calculate_emissions_without_unit_parameter(self, calculator):
        """Test backward compatibility when unit parameter is omitted."""
        result = calculator.calculate_emissions('TEST001', 100.0)
        assert result.emissions_kg_co2e == 82.0


class TestProjectTotals:
    """Test project-level emission calculations."""
    
    def test_calculate_project_total(self, calculator):
        """Test calculating total emissions for multiple materials."""
        materials = [
            {'material_id': 'TEST001', 'quantity': 100.0},
            {'material_id': 'TEST002', 'quantity': 2.0},
            {'material_id': 'TEST003', 'quantity': 50.0}
        ]
        result = calculator.calculate_project_total(materials)
        
        # Expected: 100*0.82 + 2*280 + 50*1.8 = 82 + 560 + 90 = 732 kg CO2e
        assert result.total_emissions_kg_co2e == 732.0
        assert result.total_emissions_tonnes_co2e == 0.732
        assert len(result.emissions_by_material) == 3
    
    def test_kg_to_tonnes_conversion(self, calculator):
        """Test conversion between kg and tonnes."""
        materials = [
            {'material_id': 'TEST001', 'quantity': 1000.0}
        ]
        result = calculator.calculate_project_total(materials)
        
        assert result.total_emissions_kg_co2e == 820.0
        assert result.total_emissions_tonnes_co2e == 0.82
    
    def test_empty_project(self, calculator):
        """Test that empty projects are rejected."""
        with pytest.raises(ValueError, match="Project cannot be empty"):
            calculator.calculate_project_total([])
    
    def test_material_percentages(self, calculator):
        """Test calculation of material percentage contributions."""
        materials = [
            {'material_id': 'TEST001', 'quantity': 100.0},
            {'material_id': 'TEST002', 'quantity': 2.0}
        ]
        result = calculator.calculate_project_total(materials)
        
        # Total: 82 + 560 = 642 kg CO2e
        # TEST001: 82/642 ≈ 12.77%
        # TEST002: 560/642 ≈ 87.23%
        assert abs(result.material_percentages['TEST001'] - 12.77) < 0.01
        assert abs(result.material_percentages['TEST002'] - 87.23) < 0.01
    
    def test_category_grouping(self, calculator):
        """Test grouping emissions by category."""
        materials = [
            {'material_id': 'TEST001', 'quantity': 100.0},
            {'material_id': 'TEST003', 'quantity': 50.0}
        ]
        result = calculator.calculate_project_total(materials)
        
        assert 'Binders' in result.emissions_by_category
        assert 'Reinforcing' in result.emissions_by_category
        assert result.emissions_by_category['Binders'] == 82.0
        assert result.emissions_by_category['Reinforcing'] == 90.0
    
    def test_category_percentages(self, calculator):
        """Test calculation of category percentage contributions."""
        materials = [
            {'material_id': 'TEST001', 'quantity': 100.0},
            {'material_id': 'TEST003', 'quantity': 50.0}
        ]
        result = calculator.calculate_project_total(materials)
        
        # Total: 82 + 90 = 172 kg CO2e
        # Binders: 82/172 ≈ 47.67%
        # Reinforcing: 90/172 ≈ 52.33%
        assert abs(result.category_percentages['Binders'] - 47.67) < 0.01
        assert abs(result.category_percentages['Reinforcing'] - 52.33) < 0.01


class TestMaterialComparison:
    """Test material comparison functionality."""
    
    def test_compare_materials(self, calculator):
        """Test comparing two materials."""
        result = calculator.compare_materials('TEST001', 'TEST003', 100.0)
        
        assert result.baseline_material_id == 'TEST001'
        assert result.alternative_material_id == 'TEST003'
        assert result.baseline_emissions == 82.0
        assert result.alternative_emissions == 180.0
        assert result.absolute_reduction == -98.0  # Alternative is higher
        assert abs(result.percentage_reduction - (-119.51)) < 0.01  # Negative means increase
    
    def test_compare_with_reduction(self, calculator):
        """Test comparison where alternative has lower emissions."""
        # TEST003 (steel) vs TEST001 (cement) - steel has higher emissions
        # Let's reverse to show reduction
        result = calculator.compare_materials('TEST003', 'TEST001', 100.0)
        
        assert result.baseline_emissions == 180.0
        assert result.alternative_emissions == 82.0
        assert result.absolute_reduction == 98.0
        assert abs(result.percentage_reduction - 54.44) < 0.01
    
    def test_compare_incompatible_units(self, calculator):
        """Test that materials with different units cannot be compared."""
        # TEST001 is in kg, TEST002 is in m3
        with pytest.raises(ValueError, match="Cannot compare materials with different units"):
            calculator.compare_materials('TEST001', 'TEST002', 100.0)
    
    def test_compare_with_zero_baseline(self):
        """Test comparison when baseline has zero emissions."""
        data = {
            'material_id': ['ZERO', 'NORMAL'],
            'material_name': ['Zero Emission', 'Normal'],
            'category': ['Test', 'Test'],
            'unit': ['kg', 'kg'],
            'emission_factor': [0.0, 1.0],
            'factor_unit': ['kg CO2e/kg', 'kg CO2e/kg'],
            'verification_status': ['verified', 'verified']
        }
        df = pd.DataFrame(data)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            df.to_csv(f.name, index=False)
            calc = CarbonCalculator(f.name)
            result = calc.compare_materials('ZERO', 'NORMAL', 100.0)
            assert result.percentage_reduction == 0.0


class TestHotspotAnalysis:
    """Test carbon hotspot analysis."""
    
    def test_analyze_hotspots(self, calculator):
        """Test hotspot ranking."""
        materials = [
            {'material_id': 'TEST001', 'quantity': 100.0},  # 82 kg CO2e
            {'material_id': 'TEST002', 'quantity': 2.0},    # 560 kg CO2e
            {'material_id': 'TEST003', 'quantity': 50.0}     # 90 kg CO2e
        ]
        result = calculator.analyze_hotspots(materials)
        
        assert len(result) == 3
        # Should be sorted highest first: TEST002 (560), TEST003 (90), TEST001 (82)
        assert result[0].material_id == 'TEST002'
        assert result[1].material_id == 'TEST003'
        assert result[2].material_id == 'TEST001'
    
    def test_analyze_hotspots_empty(self, calculator):
        """Test hotspot analysis with empty project."""
        with pytest.raises(ValueError, match="Cannot analyze hotspots"):
            calculator.analyze_hotspots([])


class TestMaterialRetrieval:
    """Test material retrieval functions."""
    
    def test_get_material(self, calculator):
        """Test getting a single material."""
        material = calculator.get_material('TEST001')
        assert material['material_id'] == 'TEST001'
        assert material['material_name'] == 'Test Cement'
    
    def test_get_all_materials(self, calculator):
        """Test getting all materials."""
        all_materials = calculator.get_all_materials()
        assert len(all_materials) == 3  # Only verified by default
    
    def test_get_all_materials_including_unverified(self, calculator):
        """Test getting all materials including unverified."""
        all_materials = calculator.get_all_materials(verified_only=False)
        assert len(all_materials) == 4
    
    def test_get_materials_by_category(self, calculator):
        """Test filtering materials by category."""
        structural = calculator.get_materials_by_category('Structural')
        assert len(structural) == 1
        assert structural.iloc[0]['material_id'] == 'TEST002'


class TestFactoryFunction:
    """Test the factory function."""
    
    def test_create_calculator(self, test_dataset):
        """Test creating calculator via factory function."""
        calc = create_calculator(test_dataset)
        assert isinstance(calc, CarbonCalculator)
        assert calc.materials_df is not None


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_very_large_quantity(self, calculator):
        """Test calculation with very large quantities."""
        result = calculator.calculate_emissions('TEST001', 1e9)
        assert result.emissions_kg_co2e == 0.82e9
    
    def test_very_small_quantity(self, calculator):
        """Test calculation with very small quantities."""
        result = calculator.calculate_emissions('TEST001', 0.001)
        assert result.emissions_kg_co2e == 0.00082
    
    def test_project_with_single_material(self, calculator):
        """Test project total with only one material."""
        materials = [{'material_id': 'TEST001', 'quantity': 100.0}]
        result = calculator.calculate_project_total(materials)
        assert result.total_emissions_kg_co2e == 82.0
        assert result.material_percentages['TEST001'] == 100.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
