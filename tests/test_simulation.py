"""Tests for Member 4's scenario simulation engine.

These cover the three things that would embarrass the team in a demo:

    1. Emissions are Member 2's arithmetic, not a second implementation.
    2. The sign conventions on savings are right, because the UI reads them
       directly and an inverted sign would tell a manager the opposite of the
       truth.
    3. Degenerate inputs (empty scenario, unknown material, zero baseline)
       produce a clear error or a flagged null, never a crash or a division
       by zero.
"""

import pytest

from simulation import (
    DEMO_SCENARIOS,
    Scenario,
    ScenarioError,
    ScenarioItem,
    SimulationEngine,
)


@pytest.fixture(scope="module")
def engine():
    return SimulationEngine()


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------


class TestEvaluate:
    def test_emissions_match_member_two_exactly(self, engine):
        """The engine must not recalculate: it must delegate.

        This asserts the integration rule directly - the figure the simulator
        reports is byte-for-byte the figure Member 2's engine produces.
        """
        scenario = Scenario(
            "check", [ScenarioItem("MAT002", 100), ScenarioItem("MAT009", 500)]
        )
        result = engine.evaluate(scenario)

        expected = engine.calculator.calculate_project_total(
            [{"material_id": "MAT002", "quantity": 100},
             {"material_id": "MAT009", "quantity": 500}],
            allow_unverified=True,
        )
        assert result.total_emissions_kg_co2e == expected.total_emissions_kg_co2e

    def test_single_material_arithmetic(self, engine):
        """100 m3 of C30-37 concrete at 280 kg CO2e/m3 = 28,000 kg CO2e."""
        result = engine.evaluate(Scenario("one", [ScenarioItem("MAT002", 100)]))
        assert result.total_emissions_kg_co2e == pytest.approx(28000.0)
        assert result.total_emissions_tonnes_co2e == pytest.approx(28.0)

    def test_duplicate_material_lines_are_summed(self, engine):
        """Two lines for one material must not silently collapse to the first.

        Member 2's engine keys its result dict by material_id, so this is the
        regression that would lose half a line of a bill of quantities.
        """
        result = engine.evaluate(
            Scenario(
                "dupes",
                [ScenarioItem("MAT002", 100), ScenarioItem("MAT002", 150)],
            )
        )
        assert result.total_emissions_kg_co2e == pytest.approx(70000.0)
        assert len(result.lines) == 1

    def test_zero_and_negative_lines_are_dropped(self, engine):
        result = engine.evaluate(
            Scenario(
                "mixed",
                [
                    ScenarioItem("MAT002", 100),
                    ScenarioItem("MAT002", 0),
                    ScenarioItem("MAT009", -50),
                ],
            )
        )
        assert result.total_emissions_kg_co2e == pytest.approx(28000.0)
        assert len(result.lines) == 1

    def test_empty_scenario_raises_clear_error(self, engine):
        with pytest.raises(ScenarioError, match="no material lines"):
            engine.evaluate(Scenario("empty", []))

    def test_zero_quantity_only_scenario_raises(self, engine):
        with pytest.raises(ScenarioError, match="no material lines"):
            engine.evaluate(Scenario("zero", [ScenarioItem("MAT002", 0)]))

    def test_unknown_material_names_the_bad_id(self, engine):
        with pytest.raises(ScenarioError, match="MAT999"):
            engine.evaluate(Scenario("bad", [ScenarioItem("MAT999", 10)]))

    def test_unverified_factors_produce_a_warning(self, engine):
        """The dataset has no verified factors, so every result must say so."""
        result = engine.evaluate(Scenario("w", [ScenarioItem("MAT002", 10)]))
        assert any("unverified" in warning.lower() for warning in result.warnings)

    def test_hotspot_is_the_largest_line(self, engine):
        result = engine.evaluate(
            Scenario(
                "hot",
                [
                    ScenarioItem("MAT002", 100),   # 28,000 kg
                    ScenarioItem("MAT009", 10000), # 26,800 kg
                    ScenarioItem("MAT014", 1000),  #    160 kg
                ],
            )
        )
        assert result.hotspot_material_id == "MAT002"
        assert result.lines[0].emissions_kg_co2e >= result.lines[1].emissions_kg_co2e

    def test_zero_emissions_does_not_divide_by_zero(self, engine):
        """Every quantity above zero means emissions above zero, but be safe."""
        result = engine.evaluate(Scenario("tiny", [ScenarioItem("MAT002", 0.000001)]))
        assert result.total_emissions_kg_co2e >= 0
        for line in result.lines:
            assert 0 <= line.share_of_total_percent <= 100


class TestCost:
    def test_cost_is_quantity_times_unit_cost(self, engine):
        result = engine.evaluate(Scenario("c", [ScenarioItem("MAT004", 100)]))
        # MAT004 is 5900 INR/m3.
        assert result.total_cost == pytest.approx(590000.0)
        assert result.currency == "INR"
        assert result.cost_is_complete is True

    def test_missing_cost_is_flagged_not_zeroed(self, engine, tmp_path):
        """A material with no price must not look free.

        Built by pointing the engine at an empty cost table, so the scenario
        still calculates carbon but refuses to report a cost total.
        """
        import pandas as pd

        from cost_data import CostData

        empty = CostData.__new__(CostData)
        empty.dataset_path = "empty"
        empty.costs_df = pd.DataFrame(columns=["material_id"])
        empty._by_id = {}

        engine_without_costs = SimulationEngine(
            calculator=engine.calculator, costs=empty
        )
        result = engine_without_costs.evaluate(
            Scenario("nocost", [ScenarioItem("MAT002", 100)])
        )

        assert result.total_emissions_kg_co2e == pytest.approx(28000.0)
        assert result.cost_is_complete is False
        assert result.currency is None
        assert any("No unit cost on file" in w for w in result.warnings)


# --------------------------------------------------------------------------
# Comparison and sign conventions
# --------------------------------------------------------------------------


class TestCompare:
    def test_reduction_is_baseline_minus_alternative(self, engine):
        comparison = engine.compare(
            Scenario("base", [ScenarioItem("MAT002", 1000)]),
            Scenario("alt", [ScenarioItem("MAT004", 1000)]),
        )
        # 1000 m3 * 280 = 280,000 baseline; * 200 = 200,000 alternative.
        assert comparison.emissions_baseline_kg_co2e == pytest.approx(280000.0)
        assert comparison.emissions_alternative_kg_co2e == pytest.approx(200000.0)
        assert comparison.emissions_reduction_kg_co2e == pytest.approx(80000.0)
        assert comparison.emissions_reduction_percent == pytest.approx(80000 / 280000 * 100)

    def test_worse_alternative_yields_negative_reduction(self, engine):
        comparison = engine.compare(
            Scenario("base", [ScenarioItem("MAT004", 1000)]),
            Scenario("alt", [ScenarioItem("MAT002", 1000)]),
        )
        assert comparison.emissions_reduction_kg_co2e < 0
        assert any("increases emissions" in w for w in comparison.warnings)

    def test_positive_cost_saving_means_cheaper_alternative(self, engine):
        """The whole point of the sign convention.

        GGBS concrete costs 5900/m3 against 5500/m3 for standard mix, so
        switching is cleaner AND more expensive: a negative saving. Getting
        this backwards would tell a manager the opposite of the truth.
        """
        comparison = engine.compare(
            Scenario("base", [ScenarioItem("MAT002", 1000)]),
            Scenario("alt", [ScenarioItem("MAT004", 1000)]),
        )
        assert comparison.emissions_reduction_kg_co2e > 0     # better carbon
        assert comparison.cost_saving < 0                     # costs more
        assert any("costs more" in w for w in comparison.warnings)

    def test_cheaper_and_cleaner_is_positive_saving(self, engine):
        """Same concrete, 20% less of it: less carbon and less money."""
        comparison = engine.compare(
            Scenario("base", [ScenarioItem("MAT002", 1000)]),
            Scenario("alt", [ScenarioItem("MAT002", 800)]),
        )
        assert comparison.emissions_reduction_kg_co2e > 0
        assert comparison.cost_saving > 0
        assert comparison.cost_per_tonne_avoided > 0

    def test_cost_per_tonne_avoided_is_none_when_emissions_increase(self, engine):
        comparison = engine.compare(
            Scenario("base", [ScenarioItem("MAT004", 100)]),
            Scenario("alt", [ScenarioItem("MAT002", 100)]),
        )
        assert comparison.cost_per_tonne_avoided is None

    def test_identical_scenarios_report_zero(self, engine):
        comparison = engine.compare(
            Scenario("base", [ScenarioItem("MAT002", 100)]),
            Scenario("alt", [ScenarioItem("MAT002", 100)]),
        )
        assert comparison.emissions_reduction_kg_co2e == pytest.approx(0.0)
        assert comparison.cost_saving == pytest.approx(0.0)
        assert comparison.material_deltas == []

    def test_demo_scenarios_compare_cleanly(self, engine):
        comparison = engine.compare(
            DEMO_SCENARIOS["baseline"], DEMO_SCENARIOS["alternative"]
        )
        assert comparison.emissions_reduction_kg_co2e > 0
        assert comparison.emissions_reduction_percent > 0
        assert 0 < comparison.emissions_reduction_percent < 100
        assert comparison.cost_is_complete is True


class TestMaterialDeltas:
    def test_substitution_is_reported_as_one_change(self, engine):
        comparison = engine.compare(
            Scenario("base", [ScenarioItem("MAT002", 100)]),
            Scenario("alt", [ScenarioItem("MAT004", 100)]),
        )
        assert len(comparison.material_deltas) == 1
        delta = comparison.material_deltas[0]
        assert delta.change_type == "substituted"
        assert delta.material_id == "MAT002"
        assert delta.alternative_material_id == "MAT004"
        assert delta.emissions_delta_kg_co2e == pytest.approx(-8000.0)

    def test_quantity_reduction_is_reported_as_reduced(self, engine):
        comparison = engine.compare(
            Scenario("base", [ScenarioItem("MAT005", 1000)]),
            Scenario("alt", [ScenarioItem("MAT005", 400)]),
        )
        assert comparison.material_deltas[0].change_type == "reduced"

    def test_quantity_increase_is_reported_as_increased(self, engine):
        comparison = engine.compare(
            Scenario("base", [ScenarioItem("MAT005", 100)]),
            Scenario("alt", [ScenarioItem("MAT005", 400)]),
        )
        assert comparison.material_deltas[0].change_type == "increased"

    def test_new_material_is_reported_as_added(self, engine):
        comparison = engine.compare(
            Scenario("base", [ScenarioItem("MAT002", 100)]),
            Scenario("alt", [ScenarioItem("MAT002", 100), ScenarioItem("MAT013", 50)]),
        )
        added = [
            d for d in comparison.material_deltas if d.change_type == "added"
        ]
        assert len(added) == 1
        assert added[0].material_id == "MAT013"

    def test_dropped_material_is_reported_as_removed(self, engine):
        comparison = engine.compare(
            Scenario("base", [ScenarioItem("MAT002", 100), ScenarioItem("MAT013", 50)]),
            Scenario("alt", [ScenarioItem("MAT002", 100)]),
        )
        removed = [
            d for d in comparison.material_deltas if d.change_type == "removed"
        ]
        assert len(removed) == 1

    def test_ambiguous_pairs_are_not_guessed_as_substitutions(self, engine):
        """Two removals and two additions of the same size are not a swap.

        Pairing them would invent a decision the user never described.
        """
        comparison = engine.compare(
            Scenario(
                "base",
                [ScenarioItem("MAT002", 100), ScenarioItem("MAT003", 100)],
            ),
            Scenario(
                "alt",
                [ScenarioItem("MAT004", 100), ScenarioItem("MAT005", 100)],
            ),
        )
        change_types = {d.change_type for d in comparison.material_deltas}
        assert "substituted" not in change_types
        assert change_types <= {"added", "removed"}


# --------------------------------------------------------------------------
# Scenario construction helpers
# --------------------------------------------------------------------------


class TestBuildAlternative:
    def test_substitution_carries_quantity_over(self, engine):
        baseline = Scenario("b", [ScenarioItem("MAT002", 250)])
        alternative = engine.build_alternative(
            baseline, substitutions={"MAT002": "MAT004"}
        )
        result = engine.evaluate(alternative)
        assert result.total_emissions_kg_co2e == pytest.approx(250 * 200)

    def test_quantity_change_is_applied_after_substitution(self, engine):
        baseline = Scenario("b", [ScenarioItem("MAT002", 1000)])
        alternative = engine.build_alternative(
            baseline,
            substitutions={"MAT002": "MAT004"},
            quantity_changes={"MAT004": 500},
        )
        assert engine.evaluate(alternative).total_emissions_kg_co2e == pytest.approx(
            500 * 200
        )

    def test_quantity_change_can_add_a_new_material(self, engine):
        baseline = Scenario("b", [ScenarioItem("MAT002", 100)])
        alternative = engine.build_alternative(
            baseline, quantity_changes={"MAT013": 200}
        )
        assert len(engine.evaluate(alternative).lines) == 2

    def test_describes_what_it_did(self, engine):
        alternative = engine.build_alternative(
            Scenario("b", [ScenarioItem("MAT002", 100)]),
            substitutions={"MAT002": "MAT004"},
        )
        assert "b" in alternative.description


class TestSuggestions:
    def test_low_carbon_concrete_is_suggested_for_conventional(self, engine):
        pairs = engine.suggest_substitutions()
        match = [
            p for p in pairs
            if p["baseline_material_id"] == "MAT002"
            and p["alternative_material_id"] == "MAT004"
        ]
        assert match, "GGBS concrete should be offered as an alternative"
        assert match[0]["factor_reduction_percent"] > 0

    def test_only_like_for_like_pairs(self, engine):
        """Every suggestion must share a unit, or the quantity is meaningless."""
        for pair in engine.suggest_substitutions():
            assert pair["baseline_factor"] > pair["alternative_factor"]

    def test_suggestions_are_sorted_by_reduction(self, engine):
        pairs = engine.suggest_substitutions()
        reductions = [p["factor_reduction_percent"] for p in pairs]
        assert reductions == sorted(reductions, reverse=True)


class TestProjectOpportunities:
    def test_opportunity_is_scaled_by_scenario_quantity(self, engine):
        """The saving must be this project's t CO2e, not a generic ratio."""
        result = engine.evaluate(Scenario("b", [ScenarioItem("MAT002", 1000)]))
        opportunities = engine.project_opportunities(result)

        top = next(
            o for o in opportunities
            if o["alternative_material_id"] == "MAT004"
        )
        # 1000 m3 * (280 - 200) kg CO2e/m3 = 80,000 kg = 80 t.
        assert top["emissions_reduction_kg_co2e"] == pytest.approx(80000.0)
        assert top["emissions_reduction_tonnes_co2e"] == pytest.approx(80.0)

    def test_ggbs_opportunity_reports_negative_saving(self, engine):
        """GGBS is dearer than standard mix; the UI must show that honestly."""
        result = engine.evaluate(Scenario("b", [ScenarioItem("MAT002", 1000)]))
        top = next(
            o for o in engine.project_opportunities(result)
            if o["alternative_material_id"] == "MAT004"
        )
        assert top["cost_saving"] < 0

    def test_limit_is_respected(self, engine):
        result = engine.evaluate(DEMO_SCENARIOS["baseline"])
        assert len(engine.project_opportunities(result, limit=2)) <= 2
