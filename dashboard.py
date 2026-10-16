"""Dashboard aggregation for EcoConstruct AI - Member 4.

This is the integration seam of the project. `GET /api/dashboard` is what
Member 1's React app renders, and this module builds that payload by
*composing* the other three members' work rather than reimplementing any of
it:

    Member 2  backend/carbon_calculator.py  ->  every emission factor and the
                                               emissions themselves, via
                                               simulation.SimulationEngine
    Member 3  recommender.py               ->  hotspot ranking, priority
                                               labels and the rule-based
                                               recommendations
    Member 4  cost_data.py / simulation.py ->  costs, scenarios, opportunities

Nothing here recalculates emissions. Every `emissions_kg_co2e` in the payload
originates in Member 2's `calculate_project_total()`, which is the whole point
of the integration rule: one number, one owner, no silent second opinion.

Deliberate choices worth knowing about before editing:

    - The dashboard never calls Gemini. `GET /api/dashboard` stays fast and
      always available; the AI narrative is a separate call to
      `POST /api/recommendations`, which the UI makes on demand.
    - Hotspots come from Member 3's `identify_hotspots()`, fed with rows built
      from this module's material lines, so the priority badges in the UI are
      the same ones Member 3's assistant reasons about.
    - The sustainability score is a documented prototype rubric, and it
      returns `null` - never a made-up number - when the scenario has no floor
      area to compute an intensity against.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from recommender import (
    generate_fallback_recommendations,
    identify_hotspots,
    validate_total_emissions,
)
from simulation import ScenarioResult, SimulationEngine

# --------------------------------------------------------------------------
# Sustainability score rubric
# --------------------------------------------------------------------------
#
# Carbon intensity of materials only (cradle-to-gate), in kg CO2e per m2 of
# built floor area. The bands are a prototype rubric chosen for a hackathon
# demo - they are NOT a published benchmark, and no standard (RICS, LETI,
# EN 15978) is being claimed here. They are exported in the payload so the UI
# can show the user exactly which band produced which score.

SCORE_BANDS = [
    {"max_intensity": 300, "min_score": 90, "rating": "A", "label": "Low intensity"},
    {"max_intensity": 500, "min_score": 75, "rating": "B", "label": "Moderate intensity"},
    {"max_intensity": 800, "min_score": 60, "rating": "C", "label": "High intensity"},
    {"max_intensity": 1200, "min_score": 40, "rating": "D", "label": "Very high intensity"},
    {"max_intensity": None, "min_score": 0, "rating": "E", "label": "Extremely high intensity"},
]

SCORE_RUBRIC_NOTE = (
    "Prototype rubric based on cradle-to-gate material intensity in kg CO2e/m2. "
    "Bands are illustrative and are not derived from a published standard. "
    "Scores exclude transport, construction waste, water and end-of-life."
)


def score_for_intensity(intensity_kg_per_m2: float) -> Dict[str, object]:
    """Map an intensity figure onto the documented score bands.

    Each band spans from the previous band's ceiling up to its own ceiling, and
    scores from the next band's `min_score` up to its own `min_score`. The
    score is interpolated linearly inside the band, so a higher intensity
    always produces a lower or equal score:

        band A:  0 - 300 kg CO2e/m2   ->  90 (at 0) up to 75 (at 300)
        band B:  300 - 500           ->  75 (at 300) up to 60 (at 500)
        band C:  500 - 800           ->  60 (at 500) up to 40 (at 800)
        band D:  800 - 1200          ->  40 (at 800) up to 0 (at 1200)
        band E:  above 1200          ->  0

    Raises:
        ValueError: if the intensity is negative.
    """
    if intensity_kg_per_m2 < 0:
        raise ValueError(
            f"Carbon intensity cannot be negative: {intensity_kg_per_m2}"
        )

    for index, band in enumerate(SCORE_BANDS):
        ceiling = band["max_intensity"]
        if ceiling is not None and intensity_kg_per_m2 > ceiling:
            continue

        floor_intensity = (
            float(SCORE_BANDS[index - 1]["max_intensity"]) if index > 0 else 0.0
        )
        score_floor = float(band["min_score"])
        score_ceiling = (
            float(SCORE_BANDS[index + 1]["min_score"])
            if index + 1 < len(SCORE_BANDS)
            else score_floor
        )

        if ceiling is None:
            # Open-ended top band: the project is already at or past the worst
            # band, so pin the score to its floor.
            ratio = 1.0
        else:
            span = float(ceiling) - floor_intensity
            ratio = (intensity_kg_per_m2 - floor_intensity) / span if span > 0 else 0.0
            ratio = max(0.0, min(1.0, ratio))

        # Interpolate upwards: ratio 0 (band floor, lowest intensity) -> this
        # band's own min_score, which is the better end of the scale;
        # ratio 1 (band ceiling) -> the next band's min_score, the worse end.
        score = score_floor + ratio * (score_ceiling - score_floor)

        return {
            "score": int(round(score)),
            "rating": band["rating"],
            "label": band["label"],
            "band_max_intensity": ceiling,
            "intensity_kg_per_m2": round(intensity_kg_per_m2, 2),
        }

    # Unreachable: SCORE_BANDS always ends with a band whose ceiling is None.
    raise AssertionError("SCORE_BANDS must end with an open-ended band")


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------


class DashboardBuilder:
    """Turns an evaluated scenario into the `GET /api/dashboard` payload.

    The engine is injected so tests can pass a stubbed one, and so the
    FastAPI app can keep a single shared instance instead of reloading the
    dataset on every request.
    """

    def __init__(self, engine: Optional[SimulationEngine] = None) -> None:
        self.engine = engine or SimulationEngine()

    def build(
        self,
        result: ScenarioResult,
        project_name: str,
        floor_area_m2: Optional[float] = None,
        include_opportunities: bool = True,
        opportunity_limit: int = 5,
    ) -> Dict[str, object]:
        """Build the full dashboard payload for one evaluated scenario."""
        # --- Hotspots and recommendations: Member 3's logic, fed our rows --
        hotspot_input = [
            {
                "name": line.material_name,
                "quantity": line.quantity,
                "unit": line.unit,
                "emissions_kg": line.emissions_kg_co2e,
            }
            for line in result.lines
        ]
        hotspots = identify_hotspots(hotspot_input)

        # Member 3 owns the HIGH/MEDIUM/LOW thresholds, so reuse its own
        # priority function rather than restating 20% / 10% here.
        recommendations = generate_fallback_recommendations(hotspots)
        priority_by_material = {
            rec.material: rec.priority for rec in recommendations
        }
        for hotspot in hotspots:
            hotspot["priority"] = priority_by_material.get(
                hotspot["material"], "LOW"
            )

        # --- Consistency check: Member 3's tolerance logic -----------------
        # The supplied total is what Member 2's engine calculated, so this is
        # a genuine round-trip check of the pipeline rather than a formality:
        # it would fail if a line were dropped between calculation and rollup.
        consistency = validate_total_emissions(
            {
                "total_emissions_kg": result.total_emissions_kg_co2e,
                "materials": hotspot_input,
            }
        )

        # --- Charts --------------------------------------------------------
        by_material = [
            {
                "material_id": line.material_id,
                "material_name": line.material_name,
                "category": line.category,
                "quantity": round(line.quantity, 4),
                "unit": line.unit,
                "emission_factor": line.emission_factor,
                "factor_unit": line.factor_unit,
                "emissions_kg_co2e": round(line.emissions_kg_co2e, 2),
                "emissions_tonnes_co2e": round(line.emissions_kg_co2e / 1000, 4),
                "share_percent": round(line.share_of_total_percent, 2),
                "cost": (
                    round(line.cost_total, 2) if line.cost_total is not None else None
                ),
                "priority": priority_by_material.get(line.material_name, "LOW"),
            }
            for line in result.lines
        ]

        by_category = self._category_rows(result)

        # --- Intensity and score -------------------------------------------
        if floor_area_m2 and floor_area_m2 > 0:
            kg_per_m2 = result.total_emissions_kg_co2e / floor_area_m2
            scored = score_for_intensity(kg_per_m2)
            intensity: Dict[str, object] = {
                "floor_area_m2": round(floor_area_m2, 2),
                "emissions_kg_per_m2": scored["intensity_kg_per_m2"],
                "sustainability_score": scored["score"],
                "rating": scored["rating"],
                "label": scored["label"],
                "band_max_intensity": scored["band_max_intensity"],
                "rubric": SCORE_RUBRIC_NOTE,
                "note": None,
            }
        else:
            # No denominator, so no score. Reporting 0 or a guess here would be
            # worse than reporting nothing.
            intensity = {
                "floor_area_m2": floor_area_m2,
                "emissions_kg_per_m2": None,
                "sustainability_score": None,
                "rating": None,
                "label": None,
                "band_max_intensity": None,
                "rubric": SCORE_RUBRIC_NOTE,
                "note": (
                    "No floor area was supplied for this scenario, so carbon "
                    "intensity (kg CO2e/m2) and the sustainability score are "
                    "not reported."
                ),
            }

        # --- Opportunities ---------------------------------------------------
        opportunities: List[Dict[str, object]] = []
        if include_opportunities:
            opportunities = self.engine.project_opportunities(
                result, limit=opportunity_limit
            )

        # --- Data quality ---------------------------------------------------
        factors_unverified = [
            line.material_id
            for line in result.lines
            if line.factor_verification_status != "verified"
        ]
        missing_costs = [
            line.material_id for line in result.lines if not line.has_cost
        ]

        warnings = list(result.warnings)
        if not factors_unverified:
            warnings.append(
                "All emission factors used here are marked verified in the "
                "dataset."
            )

        return {
            "project_name": project_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scenario": {
                "name": result.scenario_name,
                "description": result.description,
                "floor_area_m2": floor_area_m2,
            },
            "totals": {
                "emissions_kg_co2e": round(result.total_emissions_kg_co2e, 2),
                "emissions_tonnes_co2e": round(
                    result.total_emissions_tonnes_co2e, 4
                ),
                "cost": round(result.total_cost, 2),
                "currency": result.currency,
                "cost_is_complete": result.cost_is_complete,
                "material_count": len(result.lines),
            },
            "intensity": intensity,
            "emissions_by_material": by_material,
            "emissions_by_category": by_category,
            "hotspots": hotspots,
            "recommendations": [
                {
                    "material": rec.material,
                    "priority": rec.priority,
                    "action": rec.action,
                    "reason": rec.reason,
                    "requires_validation": rec.requires_validation,
                }
                for rec in recommendations
            ],
            "opportunities": opportunities,
            "consistency_check": consistency,
            "data_quality": {
                "emission_factors_used": len(result.lines),
                "emission_factors_unverified": sorted(factors_unverified),
                "costs_are_verified": self.engine.costs.costs_are_verified(),
                "materials_without_cost": sorted(missing_costs),
            },
            "warnings": list(dict.fromkeys(warnings)),
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _category_rows(self, result: ScenarioResult) -> List[Dict[str, object]]:
        """Category rollup: emissions from Member 2, cost from Member 4.

        Emissions are taken from `result.emissions_by_category`, which is
        Member 2's own grouping. Cost is summed here only because Member 2 has
        no cost model.
        """
        total = result.total_emissions_kg_co2e
        rows: List[Dict[str, object]] = []

        for category, emissions in result.emissions_by_category.items():
            rows.append(
                {
                    "category": category,
                    "emissions_kg_co2e": round(emissions, 2),
                    "emissions_tonnes_co2e": round(emissions / 1000, 4),
                    "share_percent": round(emissions / total * 100, 2)
                    if total > 0
                    else 0.0,
                    "cost": round(result.cost_by_category.get(category, 0.0), 2),
                    "cost_is_complete": result.cost_is_complete,
                }
            )

        rows.sort(key=lambda row: float(row["emissions_kg_co2e"]), reverse=True)
        return rows


def default_scenario_payload() -> Dict[str, object]:
    """The built-in demo scenario, as `POST /api/simulate` accepts it.

    Lets a fresh install show a populated dashboard without the user having to
    type a bill of quantities first. Quantities are the illustrative ones from
    simulation.DEMO_SCENARIOS.
    """
    from simulation import DEMO_SCENARIOS

    baseline = DEMO_SCENARIOS["baseline"]
    return {
        "name": baseline.name,
        "description": baseline.description,
        "floor_area_m2": 8500,
        "items": [
            {"material_id": item.material_id, "quantity": item.quantity, "note": item.note}
            for item in baseline.items
        ],
    }
