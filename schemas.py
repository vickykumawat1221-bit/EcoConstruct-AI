"""Data models for EcoConstruct AI - Member 3.

These Pydantic models describe the shape of the data that flows through the
carbon auditing service:

    RecommendationRequest  (what a user sends in)
        -> recommender.py analyses it ...
        -> AIReport           (what the service sends back)

Units used everywhere in this project:
    emissions        kg CO2e  (kilograms of carbon dioxide equivalent)
    quantity         whatever the `unit` field says, e.g. kg, tonne, m3, litres

No emission factors, costs or savings are hard-coded anywhere in this file.
All numbers are supplied by the caller (or by another team member's dataset).
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# The three priority levels used throughout the project.
Priority = Literal["HIGH", "MEDIUM", "LOW"]


class MaterialInput(BaseModel):
    """A single line item from a construction material bill of quantities.

    Example:
        MaterialInput(
            name="Cement (OPC)",
            quantity=12.5,
            unit="tonne",
            emissions_kg=7500.0,
        )

    Validation rules:
        - name and unit must not be blank
        - quantity and emissions_kg must be zero or greater (never negative)
    """

    # extra="forbid" turns typos into clear errors instead of silently
    # ignoring them (e.g. "emision_kg" instead of "emissions_kg").
    # str_strip_whitespace trims accidental spaces from the ends of strings.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(
        ...,
        min_length=1,
        description="Material description, e.g. 'Cement (OPC)'.",
    )
    quantity: float = Field(
        ...,
        ge=0,
        description="How much of the material was used. Must be >= 0.",
    )
    unit: str = Field(
        ...,
        min_length=1,
        description="Unit that `quantity` is measured in, e.g. kg, tonne, m3.",
    )
    emissions_kg: float = Field(
        ...,
        ge=0,
        description="Emissions for this material in kg CO2e. Must be >= 0.",
    )


class RecommendationRequest(BaseModel):
    """Everything the recommender needs for one project.

    The client sends `project_name`, its own `total_emissions_kg`, and the
    material breakdown. We do not overwrite the client's total: the point of
    validate_total_emissions() is to compare it against the material sum so
    any disagreement is reported rather than hidden.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    project_name: str = Field(
        ...,
        min_length=1,
        description="Name of the project being audited.",
    )
    total_emissions_kg: float = Field(
        ...,
        ge=0,
        description="Project total emissions in kg CO2e as reported by the client.",
    )
    materials: List[MaterialInput] = Field(
        default_factory=list,
        description="Material breakdown for the project.",
    )

    @property
    def materials_total_emissions_kg(self) -> float:
        """Convenience helper: the sum of all material emissions."""
        return sum(material.emissions_kg for material in self.materials)


class RecommendationItem(BaseModel):
    """One suggested improvement for one material.

    `action` is deliberately phrased as something to *investigate or request*
    (collect an EPD, review a mix design) rather than as a promise, because we
    do not invent emission factors, costs or carbon savings.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    material: str = Field(
        ...,
        min_length=1,
        description="Material this recommendation applies to.",
    )
    priority: Priority = Field(
        ...,
        description="HIGH, MEDIUM or LOW based on the material's emission share.",
    )
    action: str = Field(
        ...,
        min_length=1,
        description="What to do next, phrased as a step to investigate.",
    )
    reason: str = Field(
        ...,
        min_length=1,
        description="Why this was suggested, grounded in the supplied data.",
    )
    requires_validation: bool = Field(
        default=True,
        description="True when a human/engineer must verify before acting.",
    )


class AIReport(BaseModel):
    """The final audit report returned to the client.

    `procurement_plan` and `assumptions` are ordered lists of short strings so
    the UI can render them as steps / bullet points without extra parsing.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    summary: str = Field(
        ...,
        min_length=1,
        description="Short plain-text summary of the project's carbon profile.",
    )
    recommendations: List[RecommendationItem] = Field(
        default_factory=list,
        description="Ranked improvement suggestions, highest priority first.",
    )
    procurement_plan: List[str] = Field(
        default_factory=list,
        description="Ordered procurement actions (ask suppliers for data, etc.).",
    )
    assumptions: List[str] = Field(
        default_factory=list,
        description="Assumptions and data gaps that still need to be confirmed.",
    )


# --------------------------------------------------------------------------
# HTTP layer models (used by main.py). These describe the API response and
# mirror the plain dicts that recommender.py already returns - they do not
# replace or duplicate the domain models above.
# --------------------------------------------------------------------------

# Which engine produced the report in this response.
ReportSource = Literal["gemini", "fallback"]

# The three statuses validate_total_emissions() can produce.
ConsistencyStatus = Literal["match", "mismatch", "missing_total"]


class Hotspot(BaseModel):
    """One row of identify_hotspots() output, typed for the JSON response.

    Field names deliberately match the keys recommender.identify_hotspots()
    already produces, so `Hotspot.model_validate(row)` works directly.
    """

    model_config = ConfigDict(extra="forbid")

    rank: int = Field(..., description="1 = biggest emitter.")
    material: str = Field(..., min_length=1)
    quantity: float = Field(..., ge=0)
    unit: str = Field(..., min_length=1)
    emissions_kg: float = Field(..., ge=0, description="kg CO2e.")
    percentage: float = Field(..., ge=0, le=100, description="Share of total, 0-100.")


class ConsistencyCheck(BaseModel):
    """The result of recommender.validate_total_emissions().

    Field names deliberately match the keys that function already returns, so
    `ConsistencyCheck.model_validate(result)` works directly.
    """

    model_config = ConfigDict(extra="forbid")

    supplied_total_kg: Optional[float] = Field(
        default=None, ge=0, description="Total the client reported."
    )
    calculated_total_kg: float = Field(
        ..., ge=0, description="Sum of the material emissions."
    )
    difference_kg: Optional[float] = Field(
        default=None, description="Supplied minus calculated."
    )
    tolerance_kg: float = Field(
        ..., ge=0, description="Difference we are willing to accept, kg CO2e."
    )
    within_tolerance: bool = Field(
        ..., description="True when the two totals agree closely enough."
    )
    status: ConsistencyStatus = Field(
        ..., description="match, mismatch or missing_total."
    )
    message: str = Field(..., min_length=1, description="Human-readable explanation.")


class RecommendationResponse(BaseModel):
    """The JSON body returned by POST /api/recommendations."""

    model_config = ConfigDict(extra="forbid")

    project_name: str = Field(..., min_length=1)
    source: ReportSource = Field(
        ...,
        description="'gemini' if the AI report succeeded, 'fallback' if the "
        "rule-based recommendations were used instead.",
    )
    hotspots: List[Hotspot] = Field(
        default_factory=list,
        description="Materials ranked by emissions, biggest first.",
    )
    consistency_check: ConsistencyCheck = Field(
        ..., description="Whether the reported total agrees with the materials."
    )
    report: AIReport = Field(..., description="The audit report itself.")