"""Tests for Member 4's cost dataset loader.

The point of these tests is the behaviour the project depends on most: a
missing or absent price must be *reported*, never silently treated as zero.
"""

import os
import tempfile

import pytest

from cost_data import CostData, CostDataError, create_cost_data

COST_HEADER = (
    "material_id,unit,unit_cost,currency,cost_basis,source_name,"
    "source_note,verification_status"
)


def write_cost_csv(rows: str) -> str:
    """Write a temporary cost CSV and return its path."""
    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline=""
    )
    handle.write(COST_HEADER + "\n" + rows)
    handle.close()
    return handle.name


class TestDefaultDataset:
    def test_project_cost_dataset_loads(self):
        costs = CostData()
        assert costs.costs_df is not None
        assert len(costs.costs_df) == 15

    def test_every_emission_material_has_a_price(self):
        """No gap between Member 2's dataset and Member 4's cost table.

        A missing row here would silently make `cost_is_complete` false for
        any project touching that material, which is the kind of regression
        that is invisible until someone demos it.
        """
        from backend.carbon_calculator import create_calculator

        calculator = create_calculator()
        costs = CostData()

        for material_id in calculator.get_all_materials(verified_only=False)[
            "material_id"
        ]:
            assert costs.unit_cost_for(str(material_id)) is not None, (
                f"{material_id} is in materials.csv but has no unit cost"
            )

    def test_units_match_the_emission_dataset(self):
        """A price per the wrong unit would silently corrupt every total."""
        from backend.carbon_calculator import create_calculator

        calculator = create_calculator()
        costs = CostData()

        for _, row in calculator.get_all_materials(verified_only=False).iterrows():
            unit_cost = costs.unit_cost_for(str(row["material_id"]))
            assert unit_cost.unit == str(row["unit"])

    def test_costs_are_flagged_unverified(self):
        costs = CostData()
        assert costs.costs_are_verified() is False
        for cost in costs.all_costs():
            assert cost.verification_status == "unverified"
            assert cost.currency == "INR"


class TestLookup:
    def test_cost_for_quantity(self):
        costs = CostData()
        # MAT004 GGBS concrete is 5900 INR/m3.
        unit_cost = costs.unit_cost_for("MAT004")
        assert unit_cost.unit_cost == 5900.00
        assert unit_cost.cost_for(120) == 708000.00

    def test_unknown_material_returns_none(self):
        assert CostData().unit_cost_for("MAT999") is None

    def test_currency_for_single_currency(self):
        costs = CostData()
        assert costs.currency_for(["MAT001", "MAT002"]) == "INR"

    def test_currency_for_unknown_material_is_none(self):
        """None means "do not present this as one total", not "free"."""
        assert CostData().currency_for(["MAT001", "MAT999"]) is None

    def test_factory_matches_constructor(self):
        assert isinstance(create_cost_data(), CostData)


class TestValidation:
    def test_missing_file_raises(self):
        with pytest.raises(CostDataError, match="not found"):
            CostData("no_such_costs.csv")

    def test_missing_columns_raise(self):
        path = write_cost_csv("MAT001,kg,7.5,INR\n")
        try:
            with pytest.raises(CostDataError, match="Missing required columns"):
                CostData(path)
        finally:
            os.unlink(path)

    def test_duplicate_material_ids_raise(self):
        rows = (
            "MAT001,kg,7.5,INR,cost,s,note,unverified\n"
            "MAT001,kg,8.0,INR,cost,s,note,unverified\n"
        )
        path = write_cost_csv(rows)
        try:
            with pytest.raises(CostDataError, match="Duplicate"):
                CostData(path)
        finally:
            os.unlink(path)

    def test_negative_cost_raises(self):
        path = write_cost_csv("MAT001,kg,-1.0,INR,cost,s,note,unverified\n")
        try:
            with pytest.raises(CostDataError, match="Negative"):
                CostData(path)
        finally:
            os.unlink(path)

    def test_blank_currency_raises(self):
        """A missing currency must never default silently to a real one."""
        path = write_cost_csv("MAT001,kg,7.5,,cost,s,note,unverified\n")
        try:
            with pytest.raises(CostDataError, match="Missing currency"):
                CostData(path)
        finally:
            os.unlink(path)
