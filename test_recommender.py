"""Tests for schemas.py and recommender.py.

Run them with:
    venv\\Scripts\\python.exe -m pytest -v

The numbers used below are made-up test data. They are NOT real emission
factors - they only exist to check that the code behaves correctly.
"""

import pytest
from pydantic import ValidationError

from recommender import (
    ABSOLUTE_TOLERANCE_KG,
    generate_fallback_recommendations,
    identify_hotspots,
    validate_total_emissions,
)
from schemas import (
    AIReport,
    MaterialInput,
    RecommendationItem,
    RecommendationRequest,
)


# --------------------------------------------------------------------------
# Shared test data
# --------------------------------------------------------------------------

def make_material(name, quantity, unit, emissions_kg):
    """Small helper so the tests below stay readable."""
    return MaterialInput(
        name=name,
        quantity=quantity,
        unit=unit,
        emissions_kg=emissions_kg,
    )


@pytest.fixture
def sample_materials():
    """Total = 12,000 kg CO2e. Cement is the biggest hotspot at 50%."""
    return [
        make_material("Cement (OPC)", 10, "tonne", 6000),
        make_material("Ready-mix concrete C30/37", 40, "m3", 3000),
        make_material("Reinforcing steel", 12, "tonne", 2400),
        make_material("Diesel (site use)", 800, "litres", 600),
    ]


# ==========================================================================
# schemas.py - validation
# ==========================================================================

class TestMaterialInput:
    def test_accepts_a_normal_material(self):
        material = make_material("Cement (OPC)", 10, "tonne", 6000)
        assert material.name == "Cement (OPC)"
        assert material.quantity == 10
        assert material.emissions_kg == 6000

    def test_rejects_negative_quantity(self):
        with pytest.raises(ValidationError):
            make_material("Cement (OPC)", -10, "tonne", 6000)

    def test_rejects_negative_emissions(self):
        with pytest.raises(ValidationError):
            make_material("Cement (OPC)", 10, "tonne", -6000)

    def test_zero_is_allowed(self):
        material = make_material("Site water", 0, "m3", 0)
        assert material.quantity == 0
        assert material.emissions_kg == 0

    def test_rejects_blank_name(self):
        with pytest.raises(ValidationError):
            make_material("   ", 10, "tonne", 6000)


class TestRecommendationRequest:
    def test_nests_materials(self, sample_materials):
        request = RecommendationRequest(
            project_name="Riverside Tower",
            total_emissions_kg=12000,
            materials=sample_materials,
        )
        assert len(request.materials) == 4
        assert isinstance(request.materials[0], MaterialInput)

    def test_rejects_negative_total(self, sample_materials):
        with pytest.raises(ValidationError):
            RecommendationRequest(
                project_name="Riverside Tower",
                total_emissions_kg=-1,
                materials=sample_materials,
            )

    def test_materials_default_to_empty_list(self):
        request = RecommendationRequest(
            project_name="Riverside Tower",
            total_emissions_kg=0,
        )
        assert request.materials == []

    def test_materials_total_helper(self, sample_materials):
        request = RecommendationRequest(
            project_name="Riverside Tower",
            total_emissions_kg=12000,
            materials=sample_materials,
        )
        assert request.materials_total_emissions_kg == 12000

    def test_strips_whitespace_in_names(self, sample_materials):
        request = RecommendationRequest(
            project_name="  Riverside Tower  ",
            total_emissions_kg=12000,
            materials=sample_materials,
        )
        assert request.project_name == "Riverside Tower"


class TestRecommendationItem:
    def test_defaults_requires_validation_to_true(self):
        item = RecommendationItem(
            material="Cement (OPC)",
            priority="HIGH",
            action="Request the EPD.",
            reason="Largest single source.",
        )
        assert item.requires_validation is True

    def test_rejects_unknown_priority(self):
        with pytest.raises(ValidationError):
            RecommendationItem(
                material="Cement (OPC)",
                priority="CRITICAL",  # only HIGH / MEDIUM / LOW are allowed
                action="Request the EPD.",
                reason="Largest single source.",
            )


class TestAIReport:
    def test_holds_recommendations_and_lists(self):
        report = AIReport(
            summary="Cement dominates the footprint.",
            recommendations=[
                RecommendationItem(
                    material="Cement (OPC)",
                    priority="HIGH",
                    action="Request the EPD.",
                    reason="50% of total.",
                )
            ],
            procurement_plan=["Ask supplier for cement EPD."],
            assumptions=["Supplier data not yet received."],
        )
        assert report.recommendations[0].material == "Cement (OPC)"
        assert report.procurement_plan == ["Ask supplier for cement EPD."]
        assert report.assumptions == ["Supplier data not yet received."]

    def test_lists_default_to_empty(self):
        report = AIReport(summary="Small project.")
        assert report.recommendations == []
        assert report.procurement_plan == []
        assert report.assumptions == []

    def test_rejects_non_string_summary(self):
        with pytest.raises(ValidationError):
            AIReport(summary=None)


# ==========================================================================
# 1. identify_hotspots
# ==========================================================================

class TestIdentifyHotspots:
    def test_returns_one_row_per_material(self, sample_materials):
        hotspots = identify_hotspots(sample_materials)
        assert len(hotspots) == len(sample_materials)

    def test_sorts_highest_emissions_first(self, sample_materials):
        hotspots = identify_hotspots(sample_materials)
        assert [row["material"] for row in hotspots] == [
            "Cement (OPC)",
            "Ready-mix concrete C30/37",
            "Reinforcing steel",
            "Diesel (site use)",
        ]

    def test_ranks_start_at_one(self, sample_materials):
        hotspots = identify_hotspots(sample_materials)
        assert [row["rank"] for row in hotspots] == [1, 2, 3, 4]

    def test_percentages_are_correct(self, sample_materials):
        hotspots = identify_hotspots(sample_materials)
        by_name = {row["material"]: row for row in hotspots}
        assert by_name["Cement (OPC)"]["percentage"] == 50.0
        assert by_name["Ready-mix concrete C30/37"]["percentage"] == 25.0
        assert by_name["Reinforcing steel"]["percentage"] == 20.0
        assert by_name["Diesel (site use)"]["percentage"] == 5.0

    def test_percentages_add_up_to_one_hundred(self, sample_materials):
        hotspots = identify_hotspots(sample_materials)
        total_percentage = sum(row["percentage"] for row in hotspots)
        assert total_percentage == pytest.approx(100.0, abs=0.05)

    def test_emissions_stay_in_kg_co2e(self, sample_materials):
        hotspots = identify_hotspots(sample_materials)
        assert sum(row["emissions_kg"] for row in hotspots) == 12000

    def test_carries_quantity_and_unit_through(self, sample_materials):
        hotspots = identify_hotspots(sample_materials)
        cement = hotspots[0]
        assert cement["quantity"] == 10
        assert cement["unit"] == "tonne"

    def test_zero_total_does_not_crash(self):
        materials = [
            make_material("Cement (OPC)", 0, "tonne", 0),
            make_material("Diesel (site use)", 0, "litres", 0),
        ]
        hotspots = identify_hotspots(materials)
        assert len(hotspots) == 2
        assert all(row["percentage"] == 0.0 for row in hotspots)
        assert all(row["emissions_kg"] == 0 for row in hotspots)

    def test_empty_input_returns_empty_list(self):
        assert identify_hotspots([]) == []
        assert identify_hotspots(None) == []

    def test_single_material_is_one_hundred_percent(self):
        hotspots = identify_hotspots([make_material("Diesel", 100, "litres", 250)])
        assert hotspots[0]["rank"] == 1
        assert hotspots[0]["percentage"] == 100.0

    def test_accepts_plain_dicts(self):
        hotspots = identify_hotspots(
            [{"name": "Cement", "quantity": 5, "unit": "tonne", "emissions_kg": 500}]
        )
        assert hotspots[0]["material"] == "Cement"
        assert hotspots[0]["percentage"] == 100.0


# ==========================================================================
# 2. validate_total_emissions
# ==========================================================================

class TestValidateTotalEmissions:
    def test_exact_total_matches(self, sample_materials):
        request = RecommendationRequest(
            project_name="Riverside Tower",
            total_emissions_kg=12000,
            materials=sample_materials,
        )
        result = validate_total_emissions(request)
        assert result["status"] == "match"
        assert result["within_tolerance"] is True
        assert result["difference_kg"] == 0

    def test_small_rounding_difference_is_allowed(self, sample_materials):
        request = RecommendationRequest(
            project_name="Riverside Tower",
            total_emissions_kg=12000.4,  # rounding noise, under 1 kg
            materials=sample_materials,
        )
        result = validate_total_emissions(request)
        assert result["within_tolerance"] is True
        assert result["status"] == "match"

    def test_large_difference_is_flagged(self, sample_materials):
        request = RecommendationRequest(
            project_name="Riverside Tower",
            total_emissions_kg=20000,  # materials only add up to 12000
            materials=sample_materials,
        )
        result = validate_total_emissions(request)
        assert result["status"] == "mismatch"
        assert result["within_tolerance"] is False
        assert result["difference_kg"] == 8000

    def test_tolerance_scales_for_large_projects(self, sample_materials):
        """1% of a big number is more than the 1 kg absolute allowance."""
        request = RecommendationRequest(
            project_name="Riverside Tower",
            total_emissions_kg=1000000,
            materials=sample_materials,
        )
        result = validate_total_emissions(request)
        assert result["tolerance_kg"] > ABSOLUTE_TOLERANCE_KG

    def test_missing_total_is_reported(self, sample_materials):
        result = validate_total_emissions({"materials": sample_materials})
        assert result["status"] == "missing_total"
        assert result["within_tolerance"] is False
        assert result["calculated_total_kg"] == 12000

    def test_no_materials_and_zero_total_matches(self):
        request = RecommendationRequest(
            project_name="Empty project",
            total_emissions_kg=0,
        )
        result = validate_total_emissions(request)
        assert result["calculated_total_kg"] == 0
        assert result["within_tolerance"] is True
        assert result["status"] == "match"

    def test_accepts_plain_dict_project_data(self, sample_materials):
        result = validate_total_emissions(
            {
                "project_name": "Riverside Tower",
                "total_emissions_kg": 12000,
                "materials": sample_materials,
            }
        )
        assert result["status"] == "match"

    def test_message_mentions_both_totals(self, sample_materials):
        request = RecommendationRequest(
            project_name="Riverside Tower",
            total_emissions_kg=20000,
            materials=sample_materials,
        )
        result = validate_total_emissions(request)
        assert "20,000.00" in result["message"]
        assert "12,000.00" in result["message"]


# ==========================================================================
# 3. generate_fallback_recommendations
# ==========================================================================

class TestGenerateFallbackRecommendations:
    def test_returns_one_recommendation_per_hotspot(self, sample_materials):
        hotspots = identify_hotspots(sample_materials)
        recommendations = generate_fallback_recommendations(hotspots)
        assert len(recommendations) == len(hotspots)

    def test_returns_recommendation_item_objects(self, sample_materials):
        hotspots = identify_hotspots(sample_materials)
        recommendations = generate_fallback_recommendations(hotspots)
        assert all(isinstance(r, RecommendationItem) for r in recommendations)

    def test_keeps_hotspot_order(self, sample_materials):
        hotspots = identify_hotspots(sample_materials)
        recommendations = generate_fallback_recommendations(hotspots)
        assert recommendations[0].material == "Cement (OPC)"

    def test_top_emitter_is_high_priority(self, sample_materials):
        hotspots = identify_hotspots(sample_materials)
        recommendations = generate_fallback_recommendations(hotspots)
        assert recommendations[0].priority == "HIGH"

    def test_smallest_emitter_is_low_priority(self, sample_materials):
        hotspots = identify_hotspots(sample_materials)
        recommendations = generate_fallback_recommendations(hotspots)
        assert recommendations[-1].priority == "LOW"

    def test_medium_priority_band(self):
        """A material between 10% and 20% of the total -> MEDIUM."""
        hotspots = identify_hotspots(
            [
                make_material("Cement (OPC)", 1, "tonne", 1000),
                make_material("Timber", 1, "m3", 150),  # 150 / 1150 = 13.04%
            ]
        )
        recommendations = generate_fallback_recommendations(hotspots)
        assert recommendations[1].priority == "MEDIUM"

    def test_high_priority_band_starts_at_twenty_percent(self):
        """A material at exactly 20% of the total is already HIGH."""
        hotspots = identify_hotspots(
            [
                make_material("Cement (OPC)", 1, "tonne", 800),
                make_material("Timber", 1, "m3", 200),  # 200 / 1000 = 20%
            ]
        )
        recommendations = generate_fallback_recommendations(hotspots)
        assert recommendations[1].priority == "HIGH"

    @pytest.mark.parametrize(
        "material_name, expected_word",
        [
            ("Cement (OPC)", "clinker"),
            ("Ready-mix concrete C30/37", "mix design"),
            ("Reinforcing steel", "mill certificates"),
            ("Diesel (site use)", "equipment schedule"),
            ("Screed sand", "supplier EPD"),
        ],
    )
    def test_each_category_gets_its_own_action(self, material_name, expected_word):
        """Cement/concrete/steel/diesel get tailored advice; others get generic."""
        hotspots = identify_hotspots([make_material(material_name, 1, "unit", 100)])
        recommendations = generate_fallback_recommendations(hotspots)
        assert expected_word.lower() in recommendations[0].action.lower()

    def test_everything_requires_validation(self, sample_materials):
        hotspots = identify_hotspots(sample_materials)
        recommendations = generate_fallback_recommendations(hotspots)
        assert all(r.requires_validation is True for r in recommendations)

    def test_reason_uses_the_supplied_numbers(self, sample_materials):
        hotspots = identify_hotspots(sample_materials)
        recommendations = generate_fallback_recommendations(hotspots)
        cement = recommendations[0]
        assert "6,000.00 kg CO2e" in cement.reason
        assert "50.00%" in cement.reason
        assert "rank 1" in cement.reason

    def test_actions_do_not_promise_carbon_savings(self, sample_materials):
        """We must not invent savings, so no action claims a reduction."""
        hotspots = identify_hotspots(sample_materials)
        recommendations = generate_fallback_recommendations(hotspots)
        banned_words = ("save", "saving", "reduce emissions by", "% cheaper", "kg co2 saved")
        for recommendation in recommendations:
            action = recommendation.action.lower()
            assert not any(word in action for word in banned_words)

    def test_empty_hotspots_returns_empty_list(self):
        assert generate_fallback_recommendations([]) == []
        assert generate_fallback_recommendations(None) == []

    def test_zero_emissions_hotspot_is_still_handled(self):
        """A 0 kg CO2e material must not break the reason string."""
        hotspots = identify_hotspots(
            [
                make_material("Cement (OPC)", 0, "tonne", 0),
                make_material("Site water", 0, "m3", 0),
            ]
        )
        recommendations = generate_fallback_recommendations(hotspots)
        assert len(recommendations) == 2
        assert recommendations[0].priority == "HIGH"
        assert "0.00%" in recommendations[0].reason


# ==========================================================================
# End-to-end: schemas -> hotspot analysis -> report model
# ==========================================================================

class TestEndToEnd:
    def test_request_flows_through_to_a_valid_report(self, sample_materials):
        request = RecommendationRequest(
            project_name="Riverside Tower",
            total_emissions_kg=12000,
            materials=sample_materials,
        )

        check = validate_total_emissions(request)
        hotspots = identify_hotspots(request.materials)
        recommendations = generate_fallback_recommendations(hotspots)

        report = AIReport(
            summary=(
                f"{request.project_name}: "
                f"{check['calculated_total_kg']:,.0f} kg CO2e across "
                f"{len(request.materials)} materials."
            ),
            recommendations=recommendations,
            procurement_plan=[
                "Collect supplier EPDs for the four highest ranked materials.",
                "Re-check the client total after any data corrections.",
            ],
            assumptions=[
                "Emission factors come from the client, not from this module.",
            ],
        )

        # Pydantic re-validates on assignment, so this proves the data is clean.
        assert len(report.recommendations) == 4
        assert report.recommendations[0].material == "Cement (OPC)"
        assert check["within_tolerance"] is True