"""HTTP layer for Member 2's dataset and calculator.

Member 2 shipped `backend/carbon_calculator.py` as a library with no HTTP
surface, but the team's Day 1 API contract includes
`GET /api/materials`, `POST /api/calculate` and `POST /api/compare-materials`.
As the integration owner, Member 4 provides that surface - and deliberately
adds no calculation of its own here:

    - GET  /api/materials            -> CarbonCalculator.get_all_materials()
    - POST /api/calculate            -> CarbonCalculator.calculate_project_total()
    - POST /api/compare-materials    -> CarbonCalculator.compare_materials()

Every emission number this module returns was produced by Member 2's engine.
The one thing Member 4 adds is the unit-cost columns, joined from
`cost_data.CostData` so the frontend's material picker can show carbon and
money side by side.

Error mapping: Member 2's engine raises plain `ValueError`. Those are
translated here into 404 (unknown material ID) or 422 (everything else), so a
typo in the frontend produces an actionable status code rather than a 500.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from services import get_cost_data, get_engine

router = APIRouter(tags=["carbon"])


# --------------------------------------------------------------------------
# Request models
# --------------------------------------------------------------------------


class MaterialQuantity(BaseModel):
    """One line of a bill of quantities for POST /api/calculate."""

    model_config = ConfigDict(extra="forbid")

    material_id: str = Field(..., min_length=1)
    quantity: float = Field(..., gt=0, description="In the material's dataset unit.")


class CalculateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: List[MaterialQuantity] = Field(
        ..., min_length=1, description="At least one material line."
    )
    allow_unverified: bool = Field(
        default=True,
        description=(
            "Whether to use emission factors marked unverified. Defaults to "
            "True because every factor in the current dataset is unverified; "
            "the response reports the status of each factor used."
        ),
    )


class CompareMaterialsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_material_id: str = Field(..., min_length=1)
    alternative_material_id: str = Field(..., min_length=1)
    quantity: float = Field(
        ..., gt=0, description="Quantity to compare, in the shared dataset unit."
    )
    allow_unverified: bool = Field(default=True)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _raise_http_error(exc: ValueError) -> None:
    """Translate Member 2's ValueError into a specific HTTP status."""
    message = str(exc)
    if "not found" in message.lower():
        raise HTTPException(status_code=404, detail=message) from exc
    raise HTTPException(status_code=422, detail=message) from exc


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@router.get("/api/materials", summary="List materials with emission factors and costs")
def list_materials(
    category: Optional[str] = None,
    include_unverified: bool = True,
) -> dict:
    """Return every material in Member 2's dataset, joined with unit costs.

    `include_unverified=False` filters to materials whose factor is marked
    verified. That currently returns nothing, because no factor in the dataset
    has been verified yet - which is a fact the frontend should be able to
    surface rather than paper over.
    """
    engine = get_engine()
    try:
        frame = engine.calculator.get_all_materials(verified_only=False)
        if category:
            frame = frame[frame["category"] == category]
        if not include_unverified:
            frame = frame[frame["verification_status"] == "verified"]
    except ValueError as exc:
        _raise_http_error(exc)
        raise  # unreachable; keeps type checkers happy

    costs = get_cost_data()
    materials: List[dict] = []

    for _, row in frame.iterrows():
        material_id = str(row["material_id"])
        unit_cost = costs.unit_cost_for(material_id)
        materials.append(
            {
                "material_id": material_id,
                "material_name": str(row["material_name"]),
                "material_variant": str(row.get("material_variant", "")),
                "category": str(row["category"]),
                "unit": str(row["unit"]),
                "emission_factor": float(row["emission_factor"]),
                "factor_unit": str(row["factor_unit"]),
                "lifecycle_boundary": str(row.get("lifecycle_boundary", "")),
                "geography": str(row.get("geography", "")),
                "source_name": str(row.get("source_name", "")),
                "source_url": str(row.get("source_url", "")),
                "source_year": (
                    None if row.get("source_year") is None else str(row["source_year"])
                ),
                "assumptions_or_notes": str(row.get("assumptions_or_notes", "")),
                "verification_status": str(row["verification_status"]),
                "unit_cost": unit_cost.unit_cost if unit_cost else None,
                "cost_currency": unit_cost.currency if unit_cost else None,
                "cost_basis": unit_cost.cost_basis if unit_cost else None,
                "cost_verification_status": (
                    unit_cost.verification_status if unit_cost else None
                ),
            }
        )

    return {
        "count": len(materials),
        "categories": sorted({m["category"] for m in materials}),
        "all_factors_verified": all(
            m["verification_status"] == "verified" for m in materials
        )
        if materials
        else False,
        "costs_are_verified": costs.costs_are_verified(),
        "materials": materials,
        "warnings": [
            "Emission factors and unit costs are illustrative placeholders, "
            "not certified data. Every factor and price in the current "
            "datasets is marked unverified."
        ],
    }


@router.post("/api/calculate", summary="Calculate project emissions (Member 2 engine)")
def calculate(payload: CalculateRequest) -> dict:
    """Total a bill of quantities through Member 2's calculation engine."""
    engine = get_engine()
    items = [
        {"material_id": item.material_id, "quantity": item.quantity}
        for item in payload.items
    ]

    try:
        total = engine.calculator.calculate_project_total(
            items, allow_unverified=payload.allow_unverified
        )
    except ValueError as exc:
        _raise_http_error(exc)
        raise  # unreachable

    by_material = {}
    unverified: List[str] = []
    for material_id, emission in total.emissions_by_material.items():
        row = engine.calculator.get_material(
            material_id, allow_unverified=payload.allow_unverified
        )
        if str(row["verification_status"]) != "verified":
            unverified.append(material_id)
        by_material[material_id] = {
            "material_id": material_id,
            "material_name": emission.material_name,
            "quantity": emission.quantity,
            "unit": emission.unit,
            "emission_factor": emission.emission_factor,
            "factor_unit": emission.factor_unit,
            "emissions_kg_co2e": emission.emissions_kg_co2e,
            "emissions_tonnes_co2e": emission.emissions_kg_co2e / 1000,
            "share_percent": round(total.material_percentages.get(material_id, 0.0), 2),
        }

    return {
        "total_emissions_kg_co2e": total.total_emissions_kg_co2e,
        "total_emissions_tonnes_co2e": total.total_emissions_tonnes_co2e,
        "emissions_by_material": by_material,
        "emissions_by_category": total.emissions_by_category,
        "category_percentages": {
            key: round(value, 2) for key, value in total.category_percentages.items()
        },
        "unverified_factor_material_ids": sorted(unverified),
        "warnings": (
            [
                "Unverified emission factors were used for: "
                + ", ".join(sorted(unverified))
                + ". Replace with cited regional data before real decisions."
            ]
            if unverified
            else []
        ),
    }


@router.post(
    "/api/compare-materials",
    summary="Compare two materials for the same quantity (Member 2 engine)",
)
def compare_materials(payload: CompareMaterialsRequest) -> dict:
    """Like-for-like comparison of a baseline material against an alternative."""
    engine = get_engine()
    try:
        comparison = engine.calculator.compare_materials(
            payload.baseline_material_id,
            payload.alternative_material_id,
            payload.quantity,
            allow_unverified=payload.allow_unverified,
        )
    except ValueError as exc:
        _raise_http_error(exc)
        raise  # unreachable

    return {
        "baseline_material_id": comparison.baseline_material_id,
        "baseline_material_name": comparison.baseline_material_name,
        "baseline_emissions_kg_co2e": comparison.baseline_emissions,
        "alternative_material_id": comparison.alternative_material_id,
        "alternative_material_name": comparison.alternative_material_name,
        "alternative_emissions_kg_co2e": comparison.alternative_emissions,
        "absolute_reduction_kg_co2e": comparison.absolute_reduction,
        "percentage_reduction": comparison.percentage_reduction,
        "quantity": payload.quantity,
        "note": (
            "A positive absolute_reduction means the alternative emits less. "
            "Emission factors are unverified placeholders and costs are not "
            "included in this comparison."
        ),
    }
