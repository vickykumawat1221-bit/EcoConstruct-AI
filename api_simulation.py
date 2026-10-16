"""HTTP layer for Member 4: the scenario simulator and the dashboard feed.

Two endpoints, and they share the engine from `services.py` so a number shown
on the dashboard is the same number the simulator produced:

    POST /api/simulate    baseline vs alternative, with cost and carbon
    GET  /api/dashboard   the aggregated payload Member 1's React app renders
    POST /api/dashboard   the same payload for a caller-supplied scenario

Why both a GET and a POST for the dashboard: the team contract fixed the GET,
which has to work with no body, so GET returns the built-in demo scenario and
accepts a few query overrides. A real project cannot be described in a query
string, so POST takes the scenario in the body. Both run the same builder.

These routes contain no emission arithmetic. They translate JSON into
`simulation.Scenario` objects, hand them to the engine, and translate the
resulting dataclasses back out through `simulation_schemas`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query

from dashboard import default_scenario_payload
from services import get_dashboard_builder, get_engine
from simulation import Scenario, ScenarioError, ScenarioItem
from simulation_schemas import (
    DashboardRequest,
    DashboardResponse,
    ScenarioComparisonOut,
    ScenarioInput,
    ScenarioResultOut,
    SimulateRequest,
    SimulateResponse,
)

router = APIRouter(tags=["simulation"])

# Restated on every comparison response so the UI never has to remember which
# way round a signed number is.
SIGN_CONVENTIONS = {
    "emissions_reduction_kg_co2e": "baseline minus alternative; positive means the alternative emits less",
    "emissions_reduction_percent": "share of baseline emissions removed; positive means better",
    "cost_saving": "baseline cost minus alternative cost; positive means the alternative is cheaper",
    "cost_saving_percent": "share of baseline cost saved; positive means cheaper",
    "cost_per_tonne_avoided": "cost saving divided by tonnes CO2e avoided; negative means the cleaner option costs more",
    "material_deltas[].emissions_delta_kg_co2e": "alternative minus baseline; positive means the alternative is worse",
    "material_deltas[].cost_delta": "alternative minus baseline; positive means the alternative costs more",
}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _to_scenario(payload: ScenarioInput) -> Scenario:
    """Convert a validated request model into the engine's Scenario dataclass."""
    return Scenario(
        name=payload.name,
        description=payload.description,
        floor_area_m2=payload.floor_area_m2,
        items=[
            ScenarioItem(
                material_id=item.material_id,
                quantity=item.quantity,
                note=item.note,
            )
            for item in payload.items
        ],
    )


def _serialize_result(result) -> ScenarioResultOut:
    return ScenarioResultOut.model_validate(result)


def _serialize_comparison(comparison) -> ScenarioComparisonOut:
    payload = ScenarioComparisonOut.model_validate(comparison)
    # model_validate copies the dataclass fields; attach the conventions map
    # after validation because it is not a dataclass attribute.
    return payload.model_copy(update={"sign_conventions": SIGN_CONVENTIONS})


def _handle_scenario_error(exc: ScenarioError) -> None:
    """Scenario failures are client mistakes: report them as 422 with the reason."""
    raise HTTPException(status_code=422, detail=str(exc)) from exc


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@router.post(
    "/api/simulate",
    response_model=SimulateResponse,
    summary="Compare a baseline construction scenario against an alternative",
)
def simulate(payload: SimulateRequest) -> SimulateResponse:
    """Run a what-if comparison and report carbon and cost side by side.

    The alternative arrives either as a full scenario or as a set of `changes`
    applied to the baseline. Supplying both layers them: the changes are
    applied on top of the alternative you sent.
    """
    engine = get_engine()
    baseline = _to_scenario(payload.baseline)

    derived = False
    if payload.alternative is not None:
        alternative = _to_scenario(payload.alternative)
        if payload.has_derived_changes():
            alternative = engine.build_alternative(
                alternative,
                substitutions=payload.substitutions,
                quantity_changes=payload.quantity_changes,
                name=payload.alternative_name,
                description=alternative.description,
            )
            derived = True
    elif payload.has_derived_changes():
        alternative = engine.build_alternative(
            baseline,
            substitutions=payload.substitutions,
            quantity_changes=payload.quantity_changes,
            name=payload.alternative_name,
        )
        derived = True
    else:
        raise HTTPException(
            status_code=422,
            detail=(
                "Supply either an 'alternative' scenario or 'changes' "
                "('substitutions' and/or 'quantity_changes') to build one."
            ),
        )

    try:
        baseline_result = engine.evaluate(baseline)
        alternative_result = engine.evaluate(alternative)
        comparison = engine.compare_results(baseline_result, alternative_result)
    except ScenarioError as exc:
        _handle_scenario_error(exc)
        raise  # unreachable

    return SimulateResponse(
        baseline=_serialize_result(baseline_result),
        alternative=_serialize_result(alternative_result),
        comparison=_serialize_comparison(comparison),
        derived_alternative=derived,
    )


@router.get(
    "/api/dashboard",
    response_model=DashboardResponse,
    summary="Aggregated dashboard payload (built-in demo scenario)",
)
def dashboard_summary(
    project_name: str = Query(
        default="EcoConstruct AI demo project", min_length=1, max_length=200
    ),
    floor_area_m2: Optional[float] = Query(
        default=None, gt=0, description="Override the demo scenario's floor area."
    ),
    include_opportunities: bool = Query(default=True),
) -> dict:
    """Return the dashboard payload for the built-in demo scenario.

    Exists so the frontend, a smoke test or a judge can hit one GET and see a
    fully populated dashboard without constructing a scenario first.
    """
    builder = get_dashboard_builder()
    engine = get_engine()

    scenario_input = ScenarioInput.model_validate(default_scenario_payload())
    if floor_area_m2 is not None:
        scenario_input = scenario_input.model_copy(
            update={"floor_area_m2": floor_area_m2}
        )

    try:
        result = engine.evaluate(_to_scenario(scenario_input))
    except ScenarioError as exc:
        _handle_scenario_error(exc)
        raise  # unreachable

    return builder.build(
        result,
        project_name=project_name,
        floor_area_m2=scenario_input.floor_area_m2,
        include_opportunities=include_opportunities,
    )


@router.post(
    "/api/dashboard",
    response_model=DashboardResponse,
    summary="Aggregated dashboard payload for a supplied scenario",
)
def dashboard_for_scenario(payload: DashboardRequest = Body(...)) -> dict:
    """Build the dashboard payload for the scenario in the request body."""
    builder = get_dashboard_builder()
    engine = get_engine()

    if payload.scenario is None:
        scenario_input = ScenarioInput.model_validate(default_scenario_payload())
    else:
        scenario_input = payload.scenario

    try:
        result = engine.evaluate(_to_scenario(scenario_input))
    except ScenarioError as exc:
        _handle_scenario_error(exc)
        raise  # unreachable

    return builder.build(
        result,
        project_name=payload.project_name,
        floor_area_m2=scenario_input.floor_area_m2,
        include_opportunities=payload.include_opportunities,
        opportunity_limit=payload.opportunity_limit,
    )


@router.get(
    "/api/scenarios/default",
    summary="The built-in baseline/alternative demo pair, as request bodies",
)
def default_scenarios() -> dict:
    """Both demo scenarios in the shape POST /api/simulate expects.

    Lets the frontend's "load the demo" button and a curl-based judge demo
    stay in sync with the engine without duplicating quantities in two places.
    """
    from simulation import DEMO_SCENARIOS

    def to_input(name: str, scenario) -> dict:
        return {
            "name": scenario.name,
            "description": scenario.description,
            "floor_area_m2": 8500,
            "items": [
                {
                    "material_id": item.material_id,
                    "quantity": item.quantity,
                    "note": item.note,
                }
                for item in scenario.items
            ],
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline": to_input("baseline", DEMO_SCENARIOS["baseline"]),
        "alternative": to_input("alternative", DEMO_SCENARIOS["alternative"]),
    }
