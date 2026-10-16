"""
Demonstration of the EcoConstruct AI Carbon Calculator
"""

from backend.carbon_calculator import CarbonCalculator

# Initialize the calculator
calculator = CarbonCalculator()

# Calculate emissions for 1000 kg of cement
material_id = 'MAT001'
quantity = 1000.0  # kg

result = calculator.calculate_emissions(material_id, quantity)

print("=" * 60)
print("CARBON EMISSION CALCULATION DEMONSTRATION")
print("=" * 60)
print()
print("INPUT:")
print(f"  Material ID:      {result.material_id}")
print(f"  Material Name:    {result.material_name}")
print(f"  Quantity:         {result.quantity} {result.unit}")
print(f"  Emission Factor: {result.emission_factor} {result.factor_unit}")
print()
print("FORMULA:")
print(f"  Emissions (kg CO2e) = Quantity × Emission Factor")
print(f"  Emissions (kg CO2e) = {result.quantity} × {result.emission_factor}")
print()
print("RESULT:")
print(f"  Emissions: {result.emissions_kg_co2e} kg CO2e")
print(f"  Emissions: {result.emissions_kg_co2e / 1000} tonnes CO2e")
print()
print("DATA SOURCE:")
print("  Source: ICE Database")
print("  Year: 2019")
print("  Lifecycle Boundary: Cradle-to-gate")
print("  Verification Status: verified")
print("=" * 60)
