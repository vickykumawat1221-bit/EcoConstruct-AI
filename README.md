# EcoConstruct AI - Carbon Calculation & Dataset Module

## Overview

This module provides carbon emission calculations for construction materials as part of the EcoConstruct AI platform. It enables real-time construction carbon auditing, material comparisons, and carbon hotspot analysis.

**Module Owner:** Member 2 (Carbon Calculation and Dataset)

## Features

- **Dataset Management**: Load and validate construction material emission factors from CSV
- **Emissions Calculation**: Calculate carbon emissions using the formula: Emissions (kg CO2e) = Quantity × Emission Factor
- **Project Totals**: Aggregate emissions across multiple materials with category grouping
- **Material Comparisons**: Compare baseline and alternative materials to identify carbon reductions
- **Hotspot Analysis**: Rank materials by emissions to identify carbon hotspots
- **Validation**: Comprehensive input validation and error handling
- **Verification Status**: Distinguish between verified and unverified emission factors

## Technology Stack

- Python 3
- Pandas (data processing)
- CSV (dataset format)
- pytest (automated testing)

## Project Structure

```
EcoConstruct-AI/
├── data/
│   └── materials.csv          # Construction material emission factors
├── backend/
│   ├── __init__.py           # Package initialization
│   ├── carbon_calculator.py  # Core calculation engine
│   └── requirements.txt      # Python dependencies
├── tests/
│   └── test_carbon_calculator.py  # Automated test suite
├── .gitignore                # Git ignore rules
└── README.md                 # This file
```

## Installation Instructions (Windows)

### Prerequisites

- Python 3.8 or higher installed
- pip (Python package manager)

### Step 1: Clone or Download the Repository

```bash
git clone <repository-url>
cd EcoConstruct-AI
```

### Step 2: Install Dependencies

```bash
pip install -r backend/requirements.txt
```

Or install manually:

```bash
pip install pandas pytest
```

### Step 3: Verify Installation

Run the test suite to verify everything is working:

```bash
python -m pytest tests/test_carbon_calculator.py -v
```

All 34 tests should pass.

## Dataset Schema

The `data/materials.csv` file contains construction material emission factors with the following columns:

| Column | Description | Example |
|--------|-------------|---------|
| `material_id` | Unique identifier for the material | MAT001 |
| `material_name` | Human-readable material name | Cement |
| `category` | Material category (e.g., Binders, Structural) | Binders |
| `material_variant` | Specific variant or type | Ordinary Portland Cement |
| `unit` | Unit of measurement for quantity | kg |
| `emission_factor` | Emission factor value | 0.82 |
| `factor_unit` | Unit of the emission factor | kg CO2e/kg |
| `lifecycle_boundary` | Lifecycle assessment boundary | Cradle-to-gate |
| `geography` | Geographic applicability | Global |
| `source_name` | Name of data source | ICE Database |
| `source_url` | URL to source documentation | https://... |
| `source_year` | Year of source publication | 2019 |
| `assumptions_or_notes` | Additional context or assumptions | Typical value for Portland cement |
| `verification_status` | Verification status (verified/unverified) | verified |

## Calculation Formula and Units

**Basic Emissions Calculation:**

```
Emissions (kg CO2e) = Quantity × Emission Factor
```

**Example (Illustrative):**
- Material: Cement (MAT001)
- Quantity: 100 kg
- Emission Factor: 0.82 kg CO2e/kg (illustrative value)
- **Result: 82 kg CO2e** (illustrative calculation)

**Note:** This example uses illustrative emission factors. For real-world calculations, use verified factors with proper source documentation.

**Unit Conversions:**
- 1 tonne CO2e = 1,000 kg CO2e

**Unit Validation:**

The calculator now supports optional unit validation to prevent calculation errors:

```python
# With unit validation (recommended)
emission = calculator.calculate_emissions('MAT001', 100.0, quantity_unit='kg')

# Without unit validation (backward compatible)
emission = calculator.calculate_emissions('MAT001', 100.0)
```

If you provide `quantity_unit`, the calculator validates that it matches the material's expected unit. Mismatched units (e.g., providing "tons" for a material specified in "kg") will raise a clear error message.

## Source and Lifecycle Boundary Limitations

### IMPORTANT: Data Verification Status

**All emission factors in the current dataset are marked as UNVERIFIED/ILLUSTRATIVE.**

The dataset contains 15 construction materials with emission factors that are **illustrative values for demonstration purposes only**. These factors are NOT verified and should NOT be used for real-world carbon accounting without proper source documentation.

### What Makes a Factor Verified?

A verified emission factor requires:
- **Specific source citation**: Exact document name, report number, or database entry
- **Direct link to data**: URL pointing to the specific data entry (not a generic homepage)
- **Material specification**: Complete description of material composition, mix design, or product specification
- **Lifecycle boundary**: Clear statement of what is included (cradle-to-gate, cradle-to-grave, etc.)
- **Units**: Explicit definition of both quantity unit and emission factor unit
- **Geographic scope**: Specific region or clear statement of global applicability
- **Year**: Publication year of the source data

### Current Dataset Limitations

The current dataset lacks:
- Specific source citations (only generic homepage URLs are provided)
- Exact data entry references (no page numbers, table references, or database IDs)
- Complete material specifications (e.g., concrete mix proportions, brick dimensions)
- Unit definitions (e.g., MAT006 uses "unit" without defining what one unit represents)

### Data Sources Listed

The dataset references these organizations, but lacks specific citations:
- **ICE Database** (https://www.ice-database.com/) - Generic homepage, no specific data entries
- **World Steel Association** (https://www.worldsteel.org/) - Generic homepage, no specific data entries
- **DEFRA** (https://www.gov.uk/government/collections/greenhouse-gas-reporting-conversion-factors) - Collection URL, no specific factor pages

### How to Verify Factors

To mark a factor as "verified":
1. Locate the exact data entry in the source database
2. Record the specific document name, page/table number, or database ID
3. Provide a direct link to the specific data entry
4. Document the complete material specification
5. Confirm the lifecycle boundary matches your use case
6. Update the `verification_status` column to "verified"

### Lifecycle Boundaries

All current factors use **cradle-to-gate** boundaries, which include:
- Raw material extraction
- Material processing
- Manufacturing
- Transport to factory gate

**Not included:**
- Construction site emissions (use diesel factors separately)
- Use-phase emissions
- End-of-life/disposal emissions

### Geographic Limitations

Most factors are global averages. Actual emissions vary by:
- Manufacturing processes
- Energy mix of production location
- Transportation distances
- Local supplier practices

### Important Notes

- **Actual results depend on material specifications, manufacturing processes, geography, and lifecycle assumptions**
- Unverified factors are excluded from calculations by default
- Materials with incompatible units cannot be directly compared
- Structural suitability of alternative materials requires engineering validation
- This module does not assess structural performance or durability

## Usage Examples

### Example 1: Calculate Emissions for a Single Material

```python
from backend.carbon_calculator import CarbonCalculator

# Initialize calculator (uses default data/materials.csv)
calculator = CarbonCalculator()

# Calculate emissions for 100 kg of cement
# Note: allow_unverified=True is required since current factors are illustrative
emission = calculator.calculate_emissions('MAT001', 100.0, allow_unverified=True)

print(f"Material: {emission.material_name}")
print(f"Emissions: {emission.emissions_kg_co2e} kg CO2e")
```

### Example 2: Calculate Project Total for Multiple Materials

```python
from backend.carbon_calculator import CarbonCalculator

calculator = CarbonCalculator()

# Define project materials
materials = [
    {'material_id': 'MAT001', 'quantity': 1000.0},  # 1000 kg cement
    {'material_id': 'MAT002', 'quantity': 10.0},    # 10 m3 concrete
    {'material_id': 'MAT005', 'quantity': 500.0},   # 500 kg steel
]

# Calculate total emissions (allow_unverified=True for illustrative factors)
project_total = calculator.calculate_project_total(materials, allow_unverified=True)

print(f"Total Emissions: {project_total.total_emissions_kg_co2e} kg CO2e")
print(f"Total Emissions: {project_total.total_emissions_tonnes_co2e} tonnes CO2e")
print(f"By Category: {project_total.emissions_by_category}")
```

### Example 3: Compare Two Materials

```python
from backend.carbon_calculator import CarbonCalculator

calculator = CarbonCalculator()

# Compare conventional concrete with low-carbon concrete
# Note: allow_unverified=True is required since current factors are illustrative
comparison = calculator.compare_materials(
    baseline_material_id='MAT002',  # Conventional concrete
    alternative_material_id='MAT003',  # Low-carbon with fly ash
    quantity=10.0,  # 10 m3
    allow_unverified=True
)

print(f"Baseline Emissions: {comparison.baseline_emissions} kg CO2e")
print(f"Alternative Emissions: {comparison.alternative_emissions} kg CO2e")
print(f"Absolute Reduction: {comparison.absolute_reduction} kg CO2e")
print(f"Percentage Reduction: {comparison.percentage_reduction:.2f}%")
```

### Example 4: Carbon Hotspot Analysis

```python
from backend.carbon_calculator import CarbonCalculator

calculator = CarbonCalculator()

materials = [
    {'material_id': 'MAT001', 'quantity': 1000.0},
    {'material_id': 'MAT002', 'quantity': 10.0},
    {'material_id': 'MAT005', 'quantity': 500.0},
]

# Rank materials by emissions (highest first)
# Note: allow_unverified=True is required since current factors are illustrative
hotspots = calculator.analyze_hotspots(materials, allow_unverified=True)

for i, hotspot in enumerate(hotspots, 1):
    print(f"{i}. {hotspot.material_name}: {hotspot.emissions_kg_co2e} kg CO2e")
```

### Example 5: Browse Available Materials

```python
from backend.carbon_calculator import CarbonCalculator

calculator = CarbonCalculator()

# Get all materials (including unverified since all current factors are illustrative)
all_materials = calculator.get_all_materials(verified_only=False)
print(all_materials[['material_id', 'material_name', 'category', 'unit', 'verification_status']])

# Get materials by category
structural_materials = calculator.get_materials_by_category('Structural', verified_only=False)
print(structural_materials[['material_id', 'material_name']])
```

## Test Instructions

### Run All Tests

```bash
python -m pytest tests/test_carbon_calculator.py -v
```

### Run Specific Test Class

```bash
python -m pytest tests/test_carbon_calculator.py::TestBasicEmissionsCalculation -v
```

### Run with Coverage

```bash
pip install pytest-cov
python -m pytest tests/test_carbon_calculator.py --cov=backend --cov-report=html
```

### Test Coverage

The test suite includes 34 tests covering:
- Dataset loading and validation
- Basic emissions calculations
- Project totals and aggregations
- Material comparisons
- Carbon hotspot analysis
- Error handling (invalid inputs, unknown materials, etc.)
- Edge cases (very large/small quantities, zero baselines)

## Integration Instructions for Teammates

### For Member 1: React Frontend and Dashboard

The calculation engine can be imported directly or exposed via API endpoints.

**Direct Import (if using Python backend):**

```python
from backend.carbon_calculator import CarbonCalculator, create_calculator

calculator = create_calculator()

# Get all materials for dropdown
materials = calculator.get_all_materials(verified_only=True)

# Calculate emissions
emission = calculator.calculate_emissions(material_id, quantity)

# Calculate project total
project_total = calculator.calculate_project_total(materials_list)
```

**Suggested API Endpoints (to be agreed with backend owner):**

1. `GET /api/materials` - Return list of available materials
2. `POST /api/calculate` - Calculate emissions for one or more materials
3. `POST /api/compare-materials` - Compare two materials

**Response Schema for Project Total:**

```json
{
  "total_emissions_kg_co2e": 732.0,
  "total_emissions_tonnes_co2e": 0.732,
  "emissions_by_material": {
    "MAT001": {
      "material_id": "MAT001",
      "material_name": "Cement",
      "quantity": 100.0,
      "unit": "kg",
      "emissions_kg_co2e": 82.0,
      "share_of_total": 11.2
    }
  },
  "emissions_by_category": {
    "Binders": 82.0,
    "Structural": 650.0
  }
}
```

### For Member 3: AI Sustainability Recommendations

Use the hotspot analysis to identify high-emission materials for recommendations.

```python
from backend.carbon_calculator import CarbonCalculator

calculator = CarbonCalculator()

# Get carbon hotspots
hotspots = calculator.analyze_hotspots(materials_list)

# Pass hotspots to AI recommendation engine
# The top hotspots indicate where carbon reduction would have the most impact
for hotspot in hotspots[:3]:  # Top 3 hotspots
    material_info = calculator.get_material(hotspot.material_id)
    # Generate recommendations based on material category and emissions
```

**Hotspot Data Structure:**

```python
MaterialEmission(
    material_id="MAT002",
    material_name="Conventional concrete",
    quantity=10.0,
    unit="m3",
    emission_factor=280.0,
    factor_unit="kg CO2e/m3",
    emissions_kg_co2e=2800.0,
    share_of_total=75.5
)
```

### For Member 4: Scenario Simulation and Digital Twin

The calculation functions are designed to be reusable for scenario simulations.

```python
from backend.carbon_calculator import CarbonCalculator

calculator = CarbonCalculator()

# Scenario 1: Baseline
baseline_materials = [
    {'material_id': 'MAT002', 'quantity': 10.0},
    {'material_id': 'MAT005', 'quantity': 500.0}
]
baseline_total = calculator.calculate_project_total(baseline_materials)

# Scenario 2: With low-carbon alternatives
scenario_materials = [
    {'material_id': 'MAT003', 'quantity': 10.0},  # Low-carbon concrete
    {'material_id': 'MAT005', 'quantity': 500.0}
]
scenario_total = calculator.calculate_project_total(scenario_materials)

# Compare scenarios
reduction = baseline_total.total_emissions_kg_co2e - scenario_total.total_emissions_kg_co2e
```

**Key Functions for Scenario Simulation:**

- `calculate_emissions()` - Single material calculation
- `calculate_project_total()` - Multi-material aggregation
- `compare_materials()` - Direct material comparison
- `analyze_hotspots()` - Identify priority areas

All functions accept the `allow_unverified` parameter if you want to include experimental materials in scenarios.

## Error Handling

The calculator validates inputs and raises clear error messages:

- **Negative quantities**: `ValueError: Quantity cannot be negative`
- **Unknown material ID**: `ValueError: Material ID not found`
- **Unverified factors**: `ValueError: Material has unverified emission factor`
- **Incompatible units**: `ValueError: Cannot compare materials with different units`
- **Empty project**: `ValueError: Project cannot be empty`

## Unverified Emission Factors

Currently, all emission factors in the dataset are marked as **verified**. If you add new materials without credible sources, mark them as `unverified` in the `verification_status` column. Unverified factors are excluded from calculations by default.

To use unverified factors:

```python
emission = calculator.calculate_emissions('MAT_ID', quantity, allow_unverified=True)
```

## Security and Best Practices

- No API keys or secrets are included in this module
- Virtual environment files are excluded via `.gitignore`
- Environment variable files (`.env`) are excluded from version control
- The module does not make external network requests
- All data is read from local CSV files

## Future Enhancements

Potential improvements for future iterations:
- Add more materials and emission factors
- Include regional/geographic variants
- Add transport distance calculations
- Support for custom lifecycle boundaries
- Integration with EPD (Environmental Product Declaration) databases
- Material substitution suggestions based on structural requirements

## License

This module is part of the EcoConstruct AI hackathon project.

## Contact

For questions about this module, contact Member 2 (Carbon Calculation and Dataset).
