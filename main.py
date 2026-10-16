"""FastAPI application for EcoConstruct AI - Member 3.

This file is the HTTP layer only. It does three things:

    1. accept and validate a RecommendationRequest (using schemas.py)
    2. run the deterministic analysis from recommender.py
    3. try Gemini via ai_service.py, and fall back to the rule-based
       recommendations if Gemini is unavailable or misbehaves

No calculation, no emission factor and no business rule lives here - those all
belong to recommender.py and schemas.py. If you find yourself writing an if
statement about carbon numbers in this file, it probably belongs elsewhere.

Run it with:
    venv\\Scripts\\python.exe -m uvicorn main:app --reload
"""

import logging
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from ai_service import AIReportError, generate_ai_report, redact_secrets
from api_materials import router as materials_router
from api_simulation import router as simulation_router
from recommender import (
    generate_fallback_recommendations,
    identify_hotspots,
    validate_total_emissions,
)
from schemas import (
    AIReport,
    ConsistencyCheck,
    Hotspot,
    RecommendationRequest,
    RecommendationResponse,
)

# --------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------

app = FastAPI(
    title="EcoConstruct AI",
    description=(
        "Construction carbon auditing: Member 2's emission engine and dataset, "
        "Member 3's hotspot ranking and Gemini-backed recommendations with a "
        "rule-based fallback, and Member 4's scenario simulator and dashboard "
        "feed."
    ),
    version="1.0.0",
)

# React dev server ports. 5173 is Vite's default and 5174 is what this
# project's vite.config.js uses when 5173 is already taken. 127.0.0.1 is
# included because "localhost" and "127.0.0.1" are different origins to the
# browser. The Vite dev proxy normally keeps requests same-origin, so these
# entries only matter when the frontend talks to the API directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5180",
        "http://127.0.0.1:5180",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Routers from the other three modules
# --------------------------------------------------------------------------
#
# Member 3's own endpoint (/api/recommendations) is defined at the bottom of
# this file. The routers below come from:
#
#   api_materials.py   Member 2's dataset and calculator, exposed over HTTP
#   api_simulation.py  Member 4's scenario simulator and dashboard feed
#
# They are mounted here as the single integration point for the whole team, so
# the process runs one app and the React dashboard talks to one origin. The
# engine is instantiated once and shared via services.py, so the dashboard,
# the simulator and the AI assistant all read the same datasets.

app.include_router(materials_router)
app.include_router(simulation_router)

# Friendly, non-technical reasons for the fallback. We deliberately do NOT put
# the raw exception text in the HTTP response: upstream error strings can
# carry internal detail, and the response should not be a second place for a
# secret to escape from. The full (already redacted) message goes to the log.
_FALLBACK_REASONS = {
    "GeminiNotConfiguredError": "the service is not configured with a Gemini API key",
    "GeminiAPIError": "the Gemini API call failed",
    "GeminiResponseError": "Gemini returned an unusable response",
}


def _friendly_fallback_reason(exc: AIReportError) -> str:
    """Turn an exception into a short, safe explanation for the client."""
    return _FALLBACK_REASONS.get(type(exc).__name__, type(exc).__name__)


# --------------------------------------------------------------------------
# Helper: build a fallback report from the rule-based recommendations
# --------------------------------------------------------------------------

def _build_fallback_report(
    project_name: str,
    hotspots: List[dict],
    consistency_check: dict,
    fallback_reason: str,
) -> AIReport:
    """Assemble an AIReport from the rule-based recommendations.

    We still return a full AIReport (rather than a different shape) so the
    React frontend can render `report` without special-casing the fallback.
    """
    recommendations = generate_fallback_recommendations(hotspots)

    total = consistency_check.get("calculated_total_kg", 0)
    material_count = len(hotspots)

    if material_count:
        summary = (
            f"{project_name}: {total:,.2f} kg CO2e across {material_count} "
            f"materials. These recommendations are rule-based and must be "
            f"confirmed by a reviewer."
        )
    else:
        summary = (
            f"{project_name}: no materials were supplied, so no hotspots could "
            f"be identified."
        )

    top_material = hotspots[0]["material"] if hotspots else None

    procurement_plan = []
    if top_material:
        procurement_plan.append(
            f"Start with the top hotspot: {top_material} "
            f"({hotspots[0]['percentage']:.2f}% of reported emissions)."
        )
    procurement_plan.append(
        "Collect an Environmental Product Declaration (EPD) or verified "
        "emission factor for each material in the hotspot list."
    )
    if material_count:
        procurement_plan.append(
            "Re-run this audit once the supplier data is in and compare "
            "against the current figures."
        )

    assumptions = [
        "This report was produced by the rule-based fallback, not by Gemini.",
        f"Fallback used because Gemini could not be used: {fallback_reason}.",
        "No emission factors, costs or savings were assumed or estimated.",
        consistency_check.get("message", ""),
    ]

    return AIReport(
        summary=summary,
        recommendations=recommendations,
        procurement_plan=procurement_plan,
        assumptions=[note for note in assumptions if note],
    )


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@app.get("/", tags=["meta"])
def read_root() -> dict:
    """Service banner: what this API is and which routes exist."""
    return {
        "service": "EcoConstruct AI",
        "version": app.version,
        "description": (
            "Construction carbon auditing, material comparison, AI "
            "recommendations and scenario simulation."
        ),
        "docs": "/docs",
        "endpoints": {
            "health": "GET /health",
            "materials": "GET /api/materials (Member 2)",
            "calculate": "POST /api/calculate (Member 2)",
            "compare_materials": "POST /api/compare-materials (Member 2)",
            "recommendations": "POST /api/recommendations (Member 3)",
            "simulate": "POST /api/simulate (Member 4)",
            "dashboard": "GET /api/dashboard, POST /api/dashboard (Member 4)",
            "default_scenarios": "GET /api/scenarios/default (Member 4)",
        },
    }


@app.get("/health", tags=["meta"])
def read_health() -> dict:
    """Liveness check. Always cheap and never calls Gemini."""
    from services import get_engine

    status = {"status": "ok", "service": "EcoConstruct AI"}

    # The datasets are loaded lazily, so a broken CSV would otherwise only
    # surface when the first dashboard request arrived. Report it here, where
    # a run script or a monitor can see it.
    try:
        engine = get_engine()
        status["datasets"] = {
            "materials_loaded": engine.calculator.materials_df is not None,
            "costs_loaded": engine.costs.costs_df is not None,
            "material_count": (
                len(engine.calculator.materials_df)
                if engine.calculator.materials_df is not None
                else 0
            ),
        }
    except Exception as exc:  # noqa: BLE001 - health must never raise
        status["status"] = "degraded"
        status["error"] = f"{type(exc).__name__}: {exc}"

    return status


@app.post(
    "/api/recommendations",
    response_model=RecommendationResponse,
    tags=["audit"],
)
def create_recommendations(payload: RecommendationRequest) -> RecommendationResponse:
    """Audit a project and return hotspots plus a report.

    Flow:
        1. FastAPI has already validated the body against RecommendationRequest.
        2. Check the client's total against the material sum. If they disagree
           beyond the tolerance in recommender.validate_total_emissions(),
           reject with HTTP 422 - the percentages would be misleading.
        3. Rank the materials with identify_hotspots().
        4. Try Gemini. If that fails for any reason, use the rule-based
           recommendations instead and say so in `source`.
    """
    # --- Step 2: consistency check -------------------------------------
    # validate_total_emissions() returns a dict; it does not raise. The keys
    # we rely on are: status, within_tolerance, message, calculated_total_kg.
    check = validate_total_emissions(payload)

    if not check["within_tolerance"]:
        raise HTTPException(
            status_code=422,
            detail={
                "message": check["message"],
                "status": check["status"],
                "supplied_total_kg": check["supplied_total_kg"],
                "calculated_total_kg": check["calculated_total_kg"],
                "difference_kg": check["difference_kg"],
                "tolerance_kg": check["tolerance_kg"],
            },
        )

    # --- Step 3: rank the hotspots --------------------------------------
    hotspots = identify_hotspots(payload.materials)

    # --- Step 4: Gemini, with a fallback --------------------------------
    try:
        report = generate_ai_report(payload, hotspots)
        source = "gemini"
    except AIReportError as exc:
        # Covers a missing API key, a failed API call and an unusable reply.
        # redact_secrets() is applied here rather than trusting that every
        # exception was already scrubbed upstream - it costs nothing and stops
        # a credential from ever reaching the log file.
        logger.warning(
            "Gemini report generation failed (%s); using the rule-based "
            "fallback instead. Detail: %s",
            type(exc).__name__,
            redact_secrets(exc),
        )

        report = _build_fallback_report(
            project_name=payload.project_name,
            hotspots=hotspots,
            consistency_check=check,
            fallback_reason=_friendly_fallback_reason(exc),
        )
        source = "fallback"

    return RecommendationResponse(
        project_name=payload.project_name,
        source=source,
        hotspots=[Hotspot.model_validate(row) for row in hotspots],
        consistency_check=ConsistencyCheck.model_validate(check),
        report=report,
    )