"""Request and response models for Member 4's HTTP endpoints.

`schemas.py` belongs to Member 3 and is left untouched, so the simulate and
dashboard contracts live here. Every model mirrors a dataclass in
`simulation.py` / `dashboard.py` one-for-one, which lets the route handlers
build a response with `Model.model_validate(dataclass_instance)` thanks to
`from_attributes=True` - no hand-written mapping to drift out of sync.

Validation philosophy, consistent with the rest of the project:

    - Quantities must be greater than zero here, at the edge. Member 2's engine
      raises on a zero quantity, so accepting one would only turn a clear 422
      into a confusing 500.
    - `extra="forbid"` turns a typo in a field name into a helpful error instead
      of a silently ignored value.
    - Nothing in these models invents a default quantity, a default cost or a
      default emission factor. Defaults here are only structural (an empty
      list, a flag).
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid", from_attributes=True)


# --------------------------------------------------------------------------
# Scenario inputs
# --------------------------------------------------------------------------


class ScenarioItemInput(BaseModel):
    """One line of a bill of quantities sent by the client."""

    model_config = ConfigDict(extra="forbid")

    material_id: str = Field(
        ...,
        min_length=1,
        description="Material ID from GET /api/materials, e.g. 'MAT002'.",
    )
    quantity: float = Field(
        ...,
        gt=0,
        description=(
            "Quantity in the material's own dataset unit (kg, tonne, m3, "
            "liter, or brick 'unit'). Must be greater than zero."
        ),
    )
    note: str = Field(
        default="",
        description="Optional free text, e.g. 'Podium and basement slabs'.",
    )


class ScenarioInput(BaseModel):
    """A named scenario: a baseline, or a proposed alternative."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, description="Scenario name.")
    description: str = Field(
        default="", description="What this scenario represents."
    )
    items: List[ScenarioItemInput] = Field(
        ...,
        min_length=1,
        description="At least one material line is required.",
    )
    floor_area_m2: Optional[float] = Field(
        default=None,
        gt=0,
        description=(
            "Optional built floor area. When supplied, the dashboard reports "
            "carbon intensity in kg CO2e/m2 and a sustainability score."
        ),
    )


class SimulateRequest(BaseModel):
    """Body for POST /api/simulate.

    The alternative can be supplied in exactly one of two ways:

        1. Send `alternative` with a full item list.
        2. Send `changes` and let the engine derive it from the baseline.

    Sending both is allowed: `changes` is applied on top of the supplied
    alternative, so a designer can propose GGBS concrete *and* cut rebar tonnage
    in one call.
    """

    model_config = ConfigDict(extra="forbid")

    baseline: ScenarioInput = Field(
        ..., description="The scenario as currently designed."
    )
    alternative: Optional[ScenarioInput] = Field(
        default=None, description="A proposed alternative, item for item."
    )
    substitutions: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "'{from_material_id: to_material_id}'. Applied to the baseline to "
            "build an alternative, or on top of `alternative`."
        ),
    )
    quantity_changes: Dict[str, float] = Field(
        default_factory=dict,
        description="'{material_id: new_quantity}'. Applied after substitution.",
    )
    alternative_name: str = Field(
        default="Alternative scenario",
        description="Name for a derived alternative.",
    )

    def has_derived_changes(self) -> bool:
        """True when enough was supplied to derive an alternative."""
        return bool(self.substitutions or self.quantity_changes)


# --------------------------------------------------------------------------
# Simulation responses (mirror simulation.py dataclasses)
# --------------------------------------------------------------------------


class MaterialLineOut(BaseModel):
    model_config = _STRICT

    material_id: str
    material_name: str
    category: str
    quantity: float
    unit: str
    emission_factor: float
    factor_unit: str
    emissions_kg_co2e: float
    share_of_total_percent: float
    unit_cost: Optional[float] = None
    currency: Optional[str] = None
    cost_total: Optional[float] = None
    cost_verification_status: Optional[str] = None
    factor_verification_status: Optional[str] = None


class ScenarioResultOut(BaseModel):
    model_config = _STRICT

    scenario_name: str
    description: str
    total_emissions_kg_co2e: float
    total_emissions_tonnes_co2e: float
    total_cost: float
    currency: Optional[str] = None
    cost_is_complete: bool
    lines: List[MaterialLineOut] = Field(default_factory=list)
    emissions_by_category: Dict[str, float] = Field(default_factory=dict)
    cost_by_category: Dict[str, float] = Field(default_factory=dict)
    hotspot_material_id: Optional[str] = None
    hotspot_material_name: Optional[str] = None
    hotspot_share_percent: float = 0.0
    warnings: List[str] = Field(default_factory=list)


class MaterialDeltaOut(BaseModel):
    model_config = _STRICT

    material_id: str
    material_name: str
    change_type: str
    baseline_quantity: float
    alternative_quantity: float
    baseline_emissions_kg_co2e: float
    alternative_emissions_kg_co2e: float
    emissions_delta_kg_co2e: float
    cost_delta: Optional[float] = None
    unit: str
    alternative_material_id: Optional[str] = None
    alternative_material_name: Optional[str] = None


class ScenarioComparisonOut(BaseModel):
    model_config = _STRICT

    emissions_baseline_kg_co2e: float
    emissions_alternative_kg_co2e: float
    emissions_reduction_kg_co2e: float
    emissions_reduction_tonnes_co2e: float
    emissions_reduction_percent: float
    cost_baseline: float
    cost_alternative: float
    cost_saving: float
    cost_saving_percent: float
    currency: Optional[str] = None
    cost_is_complete: bool
    cost_per_tonne_avoided: Optional[float] = None
    material_deltas: List[MaterialDeltaOut] = Field(default_factory=list)
    changed_material_ids: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    sign_conventions: Dict[str, str] = Field(
        default_factory=dict,
        description="Restates how to read each signed figure, so the UI cannot "
        "render a saving as a cost.",
    )


class SimulateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline: ScenarioResultOut
    alternative: ScenarioResultOut
    comparison: ScenarioComparisonOut
    derived_alternative: bool = Field(
        default=False,
        description="True when the alternative was built from `changes` rather "
        "than supplied in full.",
    )


# --------------------------------------------------------------------------
# Dashboard request / response
# --------------------------------------------------------------------------


class DashboardRequest(BaseModel):
    """Body for POST /api/dashboard.

    Omit `scenario` to get the built-in demo scenario, which is what the
    endpoint does when a fresh install is first opened.
    """

    model_config = ConfigDict(extra="forbid")

    project_name: str = Field(
        default="EcoConstruct AI demo project",
        min_length=1,
        description="Name shown in the dashboard header.",
    )
    scenario: Optional[ScenarioInput] = Field(
        default=None,
        description="Scenario to summarise. Omit for the built-in demo.",
    )
    include_opportunities: bool = Field(
        default=True,
        description="Whether to compute the substitution opportunities.",
    )
    opportunity_limit: int = Field(
        default=5, ge=1, le=20, description="How many opportunities to return."
    )


class DashboardResponse(BaseModel):
    """The GET /api/dashboard payload.

    Declared loosely on purpose (`extra="allow"`): the payload is built by
    `dashboard.DashboardBuilder`, and Member 3 or Member 1 adding a field to it
    should not require a matching change here on the same day.
    """

    model_config = ConfigDict(extra="allow")

    project_name: str
    generated_at: str
