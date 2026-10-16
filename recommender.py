"""Rule-based carbon hotspot analysis for EcoConstruct AI - Member 3.

This module is the "no-AI" fallback layer. It works purely on the numbers the
client supplied, so it always runs even when Gemini is unavailable.

Three functions:
    identify_hotspots(materials)               -> which materials matter most
    validate_total_emissions(project_data)     -> does the client's total add up?
    generate_fallback_recommendations(hotspots)-> what to look into next

Design rules we follow on purpose:
    - Emissions are always in kg CO2e. We never rescale them.
    - We never invent emission factors, costs or carbon savings. Every "action"
      is phrased as something to request, review or verify, and every "reason"
      is grounded in the numbers the client gave us.
    - A total of 0 kg CO2e is a valid input and must not cause a division error.
"""

from typing import Any, Dict, List, Mapping, Optional, Sequence

from schemas import RecommendationItem

# --------------------------------------------------------------------------
# Tunable thresholds. Keeping them here (rather than inline) makes them easy
# to find and adjust once the team has real project data to test against.
# --------------------------------------------------------------------------

# A material at or above this share of project emissions is called HIGH.
HIGH_PRIORITY_PERCENT = 20.0

# A material at or above this share (but below HIGH) is called MEDIUM.
MEDIUM_PRIORITY_PERCENT = 10.0

# Tolerance when checking the client's total against the material sum.
# A small absolute allowance covers ordinary rounding; the relative allowance
# covers very large projects where a couple of kg is meaningless.
ABSOLUTE_TOLERANCE_KG = 1.0
RELATIVE_TOLERANCE = 0.01  # 1% of the calculated total

# How many decimal places to keep on the percentage column.
PERCENTAGE_DECIMALS = 2


# --------------------------------------------------------------------------
# Small internal helpers
# --------------------------------------------------------------------------

def _value_of(item: Any, field: str, default: Any = None) -> Any:
    """Read `field` from an object *or* a dict, so both styles work.

    Why? Because these functions may be called with Pydantic models
    (MaterialInput) from the service layer, or with plain JSON dictionaries
    straight from an HTTP body. Both should work.
    """
    if isinstance(item, Mapping):
        return item.get(field, default)
    return getattr(item, field, default)


def _to_float(value: Any) -> float:
    """Convert to float, treating None / '' / bad input as 0.0."""
    if value is None or value == "":
        return 0.0
    return float(value)


# --------------------------------------------------------------------------
# 1. identify_hotspots
# --------------------------------------------------------------------------

def identify_hotspots(materials: Optional[Sequence[Any]]) -> List[Dict[str, Any]]:
    """Rank materials by emissions and calculate each one's share of the total.

    Args:
        materials: A list of MaterialInput objects (or dicts with the same keys).
                   `None` or an empty list is allowed.

    Returns:
        A list of plain dicts sorted from highest to lowest emissions. Each dict
        has: rank, material, quantity, unit, emissions_kg, percentage.

        `rank` starts at 1 (the biggest emitter). `percentage` is that
        material's share of the project's total emissions, 0-100, rounded to
        PERCENTAGE_DECIMALS.

    Note on zero emissions:
        If the total is 0 kg CO2e we cannot compute a share, so every
        percentage is set to 0.0. This avoids a ZeroDivisionError and avoids
        inventing a ranking that the data does not support.
    """
    material_list = list(materials) if materials else []

    # Step 1: total up the emissions so we can work out each share.
    total_emissions = sum(
        _to_float(_value_of(material, "emissions_kg", 0)) for material in material_list
    )

    # Step 2: build one row per material.
    hotspots: List[Dict[str, Any]] = []
    for material in material_list:
        emissions = _to_float(_value_of(material, "emissions_kg", 0))

        if total_emissions > 0:
            percentage = (emissions / total_emissions) * 100.0
        else:
            percentage = 0.0

        hotspots.append(
            {
                "material": _value_of(material, "name", "unknown material"),
                "quantity": _to_float(_value_of(material, "quantity", 0)),
                "unit": _value_of(material, "unit", ""),
                "emissions_kg": emissions,
                "percentage": round(percentage, PERCENTAGE_DECIMALS),
            }
        )

    # Step 3: sort biggest first, then stamp the ranks.
    # Python's sort is stable, so materials with identical emissions keep the
    # order they were given in. That makes the output predictable in tests.
    hotspots.sort(key=lambda row: row["emissions_kg"], reverse=True)

    for position, row in enumerate(hotspots, start=1):
        row["rank"] = position

    return hotspots


# --------------------------------------------------------------------------
# 2. validate_total_emissions
# --------------------------------------------------------------------------

def validate_total_emissions(
    project_data: Any,
    absolute_tolerance_kg: float = ABSOLUTE_TOLERANCE_KG,
    relative_tolerance: float = RELATIVE_TOLERANCE,
) -> Dict[str, Any]:
    """Check the client's stated total against the sum of its materials.

    Args:
        project_data: A RecommendationRequest (or a dict with
                      'total_emissions_kg' and 'materials').
        absolute_tolerance_kg: Tolerance in kg CO2e used for small projects.
        relative_tolerance: Tolerance as a fraction of the calculated total,
                            used for large projects.

    Returns:
        A dict with:
            supplied_total_kg   the total the client reported
            calculated_total_kg  the sum of the material emissions
            difference_kg       supplied minus calculated
            tolerance_kg        how much difference we are willing to accept
            within_tolerance    True if the two agree closely enough
            status              "match" | "mismatch" | "missing_total"
            message             a short human-readable explanation

    This function never raises for a wrong total - it reports the problem so
    the caller can decide what to do about it.
    """
    materials = _value_of(project_data, "materials", None) or []
    raw_supplied_total = _value_of(project_data, "total_emissions_kg", None)

    calculated_total = sum(
        _to_float(_value_of(material, "emissions_kg", 0)) for material in materials
    )

    if raw_supplied_total is None:
        return {
            "supplied_total_kg": None,
            "calculated_total_kg": calculated_total,
            "difference_kg": None,
            "tolerance_kg": 0.0,
            "within_tolerance": False,
            "status": "missing_total",
            "message": (
                "No total_emissions_kg was supplied, so the client total "
                "could not be checked against the material breakdown."
            ),
        }

    supplied_total = _to_float(raw_supplied_total)
    difference = supplied_total - calculated_total

    # The allowance is the larger of an absolute and a relative tolerance,
    # so tiny projects get a kg-scale allowance and huge projects get a
    # percentage-scale allowance instead of an unrealistically strict one.
    tolerance = max(
        absolute_tolerance_kg,
        relative_tolerance * calculated_total,
    )

    within_tolerance = abs(difference) <= tolerance

    if within_tolerance:
        message = (
            f"The reported total of {supplied_total:,.2f} kg CO2e agrees with "
            f"the material sum of {calculated_total:,.2f} kg CO2e "
            f"(difference {difference:+.2f} kg CO2e)."
        )
        status = "match"
    else:
        message = (
            f"The reported total of {supplied_total:,.2f} kg CO2e does not "
            f"agree with the material sum of {calculated_total:,.2f} kg CO2e "
            f"(difference {difference:+.2f} kg CO2e, allowed {tolerance:,.2f} "
            "kg CO2e). Check for missing line items, duplicated materials or "
            "a unit mix-up before trusting the percentages."
        )
        status = "mismatch"

    return {
        "supplied_total_kg": supplied_total,
        "calculated_total_kg": calculated_total,
        "difference_kg": round(difference, PERCENTAGE_DECIMALS),
        "tolerance_kg": round(tolerance, PERCENTAGE_DECIMALS),
        "within_tolerance": within_tolerance,
        "status": status,
        "message": message,
    }


# --------------------------------------------------------------------------
# 3. generate_fallback_recommendations
# --------------------------------------------------------------------------

# Keyword rules. The FIRST rule whose keyword appears in the material name
# wins, so order matters: "ready-mix concrete" should be treated as concrete,
# not cement, even though it contains binders.
#
# The `action` text only ever asks for data, reviews or verification. It never
# states a factor, a cost or a saving, because we are not allowed to invent
# those numbers here.
_FALLBACK_RULES = [
    {
        "category": "concrete",
        "keywords": ("concrete", "ready mix", "ready-mix", "precast"),
        "action": (
            "Request the mix design and the Environmental Product Declaration "
            "(EPD) from the supplier, then evaluate mixes with lower binder "
            "content or higher supplementary cementitious materials. Have the "
            "structural engineer confirm any change before it is used."
        ),
    },
    {
        "category": "cement",
        "keywords": (
            "cement",
            "binder",
            "fly ash",
            "ggbs",
            "slag",
            "clinker",
        ),
        "action": (
            "Request the supplier EPD and the clinker-to-cement ratio for the "
            "cement used, and evaluate a lower clinker content or an approved "
            "supplementary cementitious material with the design team."
        ),
    },
    {
        "category": "steel",
        "keywords": ("steel", "rebar", "reinforcement", "metal"),
        "action": (
            "Request mill certificates and the EPD for the grade and country of "
            "origin, and evaluate higher recycled content, offcut or "
            "cut-and-weld options with the supplier and design team."
        ),
    },
    {
        "category": "diesel",
        "keywords": ("diesel", "fuel oil", "gas oil"),
        "action": (
            "Reconcile the fuel entry against the site equipment schedule and "
            "meter readings, then review idling limits, haul routes and "
            "alternative equipment with the plant manager."
        ),
    },
]

# Used when nothing above matches.
_GENERIC_RULE = {
    "category": "other",
    "keywords": (),
    "action": (
        "Collect the supplier EPD or verified emission factor for this "
        "material, confirm the unit and quantity with the quantity surveyor, "
        "and re-check this entry against the project's own records."
    ),
}


def _match_rule(material_name: str) -> Dict[str, Any]:
    """Return the first rule that matches `material_name`, else the generic rule."""
    lowered = str(material_name).strip().lower()

    for rule in _FALLBACK_RULES:
        for keyword in rule["keywords"]:
            if keyword in lowered:
                return rule

    return _GENERIC_RULE


def _priority_for(hotspot: Mapping[str, Any]) -> str:
    """Turn a hotspot's share of emissions into HIGH / MEDIUM / LOW.

    The top emitter is always HIGH (even if the whole project is small),
    because it is the best place to start looking.
    """
    percentage = _to_float(hotspot.get("percentage", 0))
    rank = int(_to_float(hotspot.get("rank", 0)))

    if rank == 1 or percentage >= HIGH_PRIORITY_PERCENT:
        return "HIGH"
    if percentage >= MEDIUM_PRIORITY_PERCENT:
        return "MEDIUM"
    return "LOW"


def generate_fallback_recommendations(
    hotspots: Optional[Sequence[Mapping[str, Any]]],
) -> List[RecommendationItem]:
    """Turn hotspots into rule-based recommendations (no AI involved).

    Args:
        hotspots: Output of identify_hotspots() - a list of dicts with
                  'material', 'rank', 'emissions_kg' and 'percentage'.
                  `None` or an empty list is allowed.

    Returns:
        A list of RecommendationItem objects, in the same (highest emissions
        first) order as the hotspots given.

        Every item has requires_validation=True, because these are rule-based
        heuristics that a person should confirm before acting on.
    """
    hotspot_list = list(hotspots) if hotspots else []

    recommendations: List[RecommendationItem] = []

    for hotspot in hotspot_list:
        material_name = str(hotspot.get("material", "unknown material"))
        rule = _match_rule(material_name)
        priority = _priority_for(hotspot)

        emissions = _to_float(hotspot.get("emissions_kg", 0))
        percentage = _to_float(hotspot.get("percentage", 0))
        rank = int(_to_float(hotspot.get("rank", 0)))

        # The reason only repeats numbers we were actually given.
        reason = (
            f"{material_name} is rank {rank} of the supplied materials at "
            f"{emissions:,.2f} kg CO2e, which is {percentage:.2f}% of the "
            f"project total ({rule['category']} category)."
        )

        recommendations.append(
            RecommendationItem(
                material=material_name,
                priority=priority,
                action=rule["action"],
                reason=reason,
                requires_validation=True,
            )
        )

    return recommendations