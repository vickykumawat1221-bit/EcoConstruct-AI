"""Tests for the FastAPI application in main.py.

No test hits the network or needs a real API key: generate_ai_report is
replaced with a fake using monkeypatch, which is why it is imported into
main.py's namespace (`from ai_service import generate_ai_report`).

Run them with:
    venv\\Scripts\\python.exe -m pytest -v
"""

import logging

import pytest
from fastapi.testclient import TestClient

import ai_service
import main
from ai_service import (
    GeminiAPIError,
    GeminiNotConfiguredError,
    GeminiResponseError,
)
from main import app
from schemas import AIReport

# --------------------------------------------------------------------------
# Client + fixtures
# --------------------------------------------------------------------------

client = TestClient(app)


def valid_payload(**overrides):
    """A consistent request: materials add up to 9,000 kg CO2e."""
    payload = {
        "project_name": "Riverside Tower",
        "total_emissions_kg": 9000,
        "materials": [
            {"name": "Cement (OPC)", "quantity": 10, "unit": "tonne", "emissions_kg": 6000},
            {"name": "Reinforcing steel", "quantity": 12, "unit": "tonne", "emissions_kg": 2400},
            {"name": "Diesel (site use)", "quantity": 800, "unit": "litres", "emissions_kg": 600},
        ],
    }
    payload.update(overrides)
    return payload


def fake_report(**overrides):
    """Build a valid AIReport for the fakes to return."""
    fields = {
        "summary": "Cement accounts for half of the reported emissions.",
        "recommendations": [
            {
                "material": "Cement (OPC)",
                "priority": "HIGH",
                "action": "Request the supplier EPD and the clinker-to-cement ratio.",
                "reason": "50.00% of the project total.",
                "requires_validation": True,
            }
        ],
        "procurement_plan": ["Collect the cement supplier EPD."],
        "assumptions": ["Emission factors were supplied by the client."],
    }
    fields.update(overrides)
    return AIReport(**fields)


@pytest.fixture
def gemini_works(monkeypatch):
    """Make Gemini succeed. Returns a list recording the calls made."""
    calls = []

    def fake_generate(project_data, hotspots=None, **kwargs):
        calls.append({"project_data": project_data, "hotspots": hotspots})
        return fake_report()

    monkeypatch.setattr(main, "generate_ai_report", fake_generate)
    return calls


@pytest.fixture
def gemini_broken(monkeypatch):
    """Make Gemini raise, proving the fallback path works."""

    def fake_generate(project_data, hotspots=None, **kwargs):
        raise GeminiAPIError("The Gemini API call failed for model 'gemini-3.8-flash'")

    monkeypatch.setattr(main, "generate_ai_report", fake_generate)


# ==========================================================================
# GET / and GET /health
# ==========================================================================

class TestMetaRoutes:
    def test_root_returns_service_banner(self):
        response = client.get("/")
        assert response.status_code == 200
        body = response.json()
        assert body["service"] == "EcoConstruct AI - Member 3"
        assert "recommendations" in body["endpoints"]

    def test_health_returns_ok(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_health_does_not_call_gemini(self, gemini_works):
        client.get("/health")
        assert gemini_works == []


# ==========================================================================
# POST /api/recommendations - happy path
# ==========================================================================

class TestRecommendationsSuccess:
    def test_returns_200(self, gemini_works):
        response = client.post("/api/recommendations", json=valid_payload())
        assert response.status_code == 200

    def test_response_has_the_five_expected_keys(self, gemini_works):
        body = client.post("/api/recommendations", json=valid_payload()).json()
        assert set(body.keys()) == {
            "project_name",
            "source",
            "hotspots",
            "consistency_check",
            "report",
        }

    def test_project_name_is_echoed_back(self, gemini_works):
        body = client.post("/api/recommendations", json=valid_payload()).json()
        assert body["project_name"] == "Riverside Tower"

    def test_source_is_gemini_when_the_call_succeeds(self, gemini_works):
        body = client.post("/api/recommendations", json=valid_payload()).json()
        assert body["source"] == "gemini"

    def test_hotspots_are_ranked_biggest_first(self, gemini_works):
        body = client.post("/api/recommendations", json=valid_payload()).json()
        names = [row["material"] for row in body["hotspots"]]
        assert names == ["Cement (OPC)", "Reinforcing steel", "Diesel (site use)"]
        assert [row["rank"] for row in body["hotspots"]] == [1, 2, 3]

    def test_hotspot_percentages_are_correct(self, gemini_works):
        body = client.post("/api/recommendations", json=valid_payload()).json()
        top = body["hotspots"][0]
        assert top["emissions_kg"] == 6000
        assert top["percentage"] == 66.67  # 6000 / 9000

    def test_consistency_check_is_a_match(self, gemini_works):
        body = client.post("/api/recommendations", json=valid_payload()).json()
        check = body["consistency_check"]
        assert check["status"] == "match"
        assert check["within_tolerance"] is True
        assert check["calculated_total_kg"] == 9000

    def test_report_is_the_ai_report(self, gemini_works):
        body = client.post("/api/recommendations", json=valid_payload()).json()
        assert body["report"]["summary"].startswith("Cement accounts")
        assert body["report"]["recommendations"][0]["material"] == "Cement (OPC)"

    def test_the_recommender_actually_ran(self, gemini_works):
        """Gemini must receive the hotspots computed by the recommender."""
        client.post("/api/recommendations", json=valid_payload())

        assert len(gemini_works) == 1
        hotspots_sent = gemini_works[0]["hotspots"]
        assert hotspots_sent[0]["material"] == "Cement (OPC)"
        assert hotspots_sent[0]["rank"] == 1

    def test_works_with_no_materials(self, gemini_works):
        response = client.post(
            "/api/recommendations",
            json={"project_name": "Empty site", "total_emissions_kg": 0, "materials": []},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["hotspots"] == []


# ==========================================================================
# POST /api/recommendations - invalid input
# ==========================================================================

class TestInvalidInput:
    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({}, id="empty body"),
            pytest.param({"total_emissions_kg": 100}, id="missing project_name"),
            pytest.param({"project_name": "X"}, id="missing total"),
            pytest.param(
                {"project_name": "X", "total_emissions_kg": -5, "materials": []},
                id="negative total",
            ),
            pytest.param(
                {
                    "project_name": "X",
                    "total_emissions_kg": 100,
                    "materials": [{"name": "Cement", "quantity": -1,
                                   "unit": "t", "emissions_kg": 10}],
                },
                id="negative quantity",
            ),
            pytest.param(
                {
                    "project_name": "X",
                    "total_emissions_kg": 100,
                    "materials": [{"name": "Cement", "quantity": 1,
                                   "unit": "t", "emissions_kg": -10}],
                },
                id="negative emissions",
            ),
            pytest.param(
                {
                    "project_name": "X",
                    "total_emissions_kg": 100,
                    "materials": [{"name": "Cement", "quantity": 1,
                                   "unit": "t", "emissions_kg": 10,
                                   "typo_field": 1}],
                },
                id="unknown material field",
            ),
        ],
    )
    def test_invalid_bodies_get_422(self, payload):
        response = client.post("/api/recommendations", json=payload)
        assert response.status_code == 422

    def test_invalid_input_never_calls_gemini(self, gemini_works):
        client.post("/api/recommendations", json={"project_name": "X"})
        assert gemini_works == []

    def test_validation_errors_are_json(self):
        response = client.post("/api/recommendations", json={})
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], list)


# ==========================================================================
# POST /api/recommendations - inconsistent totals
# ==========================================================================

class TestInconsistentTotals:
    def test_mismatched_total_gets_422(self, gemini_works):
        response = client.post(
            "/api/recommendations",
            json=valid_payload(total_emissions_kg=20000),  # materials add to 9000
        )
        assert response.status_code == 422

    def test_422_detail_explains_the_problem(self, gemini_works):
        response = client.post(
            "/api/recommendations",
            json=valid_payload(total_emissions_kg=20000),
        )
        detail = response.json()["detail"]
        assert detail["status"] == "mismatch"
        assert "does not agree" in detail["message"]
        assert detail["supplied_total_kg"] == 20000
        assert detail["calculated_total_kg"] == 9000
        assert detail["difference_kg"] == 11000
        assert detail["tolerance_kg"] == 90.0  # 1% of 9,000

    def test_inconsistent_total_never_calls_gemini(self, gemini_works):
        """No point paying for an API call on data we already know is wrong."""
        client.post(
            "/api/recommendations",
            json=valid_payload(total_emissions_kg=20000),
        )
        assert gemini_works == []

    def test_total_below_the_material_sum_is_also_rejected(self, gemini_works):
        response = client.post(
            "/api/recommendations",
            json=valid_payload(total_emissions_kg=100),
        )
        assert response.status_code == 422

    def test_small_rounding_difference_is_accepted(self, gemini_works):
        """Within the recommender's 1 kg tolerance, so it must pass."""
        response = client.post(
            "/api/recommendations",
            json=valid_payload(total_emissions_kg=9000.4),
        )
        assert response.status_code == 200
        assert response.json()["consistency_check"]["status"] == "match"

    def test_no_materials_but_nonzero_total_is_rejected(self, gemini_works):
        response = client.post(
            "/api/recommendations",
            json={"project_name": "X", "total_emissions_kg": 500, "materials": []},
        )
        assert response.status_code == 422

    def test_single_material_that_matches_itself_is_accepted(self, gemini_works):
        response = client.post(
            "/api/recommendations",
            json={
                "project_name": "Small job",
                "total_emissions_kg": 250,
                "materials": [
                    {"name": "Diesel", "quantity": 100, "unit": "litres",
                     "emissions_kg": 250}
                ],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["hotspots"][0]["percentage"] == 100.0


# ==========================================================================
# POST /api/recommendations - Gemini failure -> fallback
# ==========================================================================

class TestGeminiFallback:
    def test_api_failure_returns_200_with_fallback_source(self, gemini_broken):
        response = client.post("/api/recommendations", json=valid_payload())
        assert response.status_code == 200
        assert response.json()["source"] == "fallback"

    def test_fallback_still_returns_hotspots_and_consistency_check(self, gemini_broken):
        body = client.post("/api/recommendations", json=valid_payload()).json()
        assert body["hotspots"][0]["material"] == "Cement (OPC)"
        assert body["consistency_check"]["status"] == "match"

    def test_fallback_recommendations_come_from_the_recommender(self, gemini_broken):
        body = client.post("/api/recommendations", json=valid_payload()).json()
        materials = [r["material"] for r in body["report"]["recommendations"]]
        assert materials == ["Cement (OPC)", "Reinforcing steel", "Diesel (site use)"]

    def test_fallback_priority_is_set(self, gemini_broken):
        body = client.post("/api/recommendations", json=valid_payload()).json()
        top = body["report"]["recommendations"][0]
        assert top["priority"] == "HIGH"
        assert top["requires_validation"] is True

    def test_fallback_explains_itself_in_assumptions(self, gemini_broken):
        body = client.post("/api/recommendations", json=valid_payload()).json()
        assumptions = " ".join(body["report"]["assumptions"])
        assert "rule-based fallback" in assumptions
        assert "No emission factors, costs or savings" in assumptions

    def test_fallback_mentions_the_top_hotspot_in_the_plan(self, gemini_broken):
        body = client.post("/api/recommendations", json=valid_payload()).json()
        assert "Cement (OPC)" in body["report"]["procurement_plan"][0]

    def test_missing_api_key_also_falls_back(self, monkeypatch):
        def fake_generate(project_data, hotspots=None, **kwargs):
            raise GeminiNotConfiguredError("GEMINI_API_KEY is not set.")

        monkeypatch.setattr(main, "generate_ai_report", fake_generate)

        response = client.post("/api/recommendations", json=valid_payload())
        assert response.status_code == 200
        assert response.json()["source"] == "fallback"

    def test_malformed_gemini_reply_also_falls_back(self, monkeypatch):
        def fake_generate(project_data, hotspots=None, **kwargs):
            raise GeminiResponseError("Gemini did not return valid JSON.")

        monkeypatch.setattr(main, "generate_ai_report", fake_generate)

        response = client.post("/api/recommendations", json=valid_payload())
        assert response.status_code == 200
        assert response.json()["source"] == "fallback"

    def test_fallback_does_not_leak_the_api_key(self, monkeypatch):
        """The route must not echo raw upstream error text to the client."""
        fake_key = "sk-leaky-key-99999"

        def fake_generate(project_data, hotspots=None, **kwargs):
            raise GeminiAPIError(f"Auth failed for key {fake_key}")

        monkeypatch.setattr(main, "generate_ai_report", fake_generate)

        body = client.post("/api/recommendations", json=valid_payload()).text
        assert fake_key not in body

    def test_fallback_does_not_leak_the_api_key_to_the_log(self, monkeypatch, caplog):
        """Regression: the server log must be scrubbed too, not just the body.

        The route used to log the raw exception on the assumption that
        ai_service had already redacted it. Anything that reached the logger
        unredacted would write a live credential to disk.
        """
        fake_key = "sk-leaky-key-88888"
        monkeypatch.setenv(ai_service.ENV_API_KEY, fake_key)

        def fake_generate(project_data, hotspots=None, **kwargs):
            raise GeminiAPIError(f"Auth failed for key {fake_key}")

        monkeypatch.setattr(main, "generate_ai_report", fake_generate)

        with caplog.at_level(logging.WARNING):
            client.post("/api/recommendations", json=valid_payload())

        assert fake_key not in caplog.text
        assert caplog.text  # the warning itself must still be emitted

    def test_redact_secrets_hides_the_current_env_key(self, monkeypatch):
        monkeypatch.setenv(ai_service.ENV_API_KEY, "sk-env-key-77777")
        assert "sk-env-key-77777" not in ai_service.redact_secrets("key=sk-env-key-77777")

    def test_redact_secrets_leaves_harmless_text_untouched(self):
        """It must be safe to call with only the text, and be a no-op when
        there is nothing secret to remove."""
        assert ai_service.redact_secrets("nothing secret here") == "nothing secret here"

    def test_fallback_reason_is_friendly_not_raw_exception_text(self, monkeypatch):
        """The client gets a short reason, not the raw Gemini error string."""
        def fake_generate(project_data, hotspots=None, **kwargs):
            raise GeminiAPIError("401 UNAUTHENTICATED at /v1beta/models internal-node-7")

        monkeypatch.setattr(main, "generate_ai_report", fake_generate)

        body = client.post("/api/recommendations", json=valid_payload()).text
        assert "internal-node-7" not in body
        assert "the Gemini API call failed" in body

    @pytest.mark.parametrize(
        "error, expected_reason",
        [
            (GeminiNotConfiguredError("x"), "not configured with a Gemini API key"),
            (GeminiAPIError("x"), "the Gemini API call failed"),
            (GeminiResponseError("x"), "Gemini returned an unusable response"),
        ],
    )
    def test_each_error_type_maps_to_a_clear_reason(self, monkeypatch, error, expected_reason):
        def fake_generate(project_data, hotspots=None, **kwargs):
            raise error

        monkeypatch.setattr(main, "generate_ai_report", fake_generate)

        body = client.post("/api/recommendations", json=valid_payload()).text
        assert expected_reason in body

    def test_fallback_with_no_materials(self, gemini_broken):
        response = client.post(
            "/api/recommendations",
            json={"project_name": "Empty site", "total_emissions_kg": 0, "materials": []},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["source"] == "fallback"
        assert body["report"]["recommendations"] == []
        assert "no materials" in body["report"]["summary"]


# ==========================================================================
# CORS configuration
# ==========================================================================

class TestCors:
    def test_preflight_from_react_dev_server_is_allowed(self):
        response = client.options(
            "/api/recommendations",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"

    def test_127_0_0_1_origin_is_allowed_too(self):
        response = client.options(
            "/api/recommendations",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"

    def test_unknown_origin_is_not_allowed(self):
        response = client.options(
            "/api/recommendations",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert "access-control-allow-origin" not in response.headers

    def test_real_request_carries_the_cors_header(self, gemini_works):
        response = client.post(
            "/api/recommendations",
            json=valid_payload(),
            headers={"Origin": "http://localhost:5173"},
        )
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


# ==========================================================================
# OpenAPI / docs
# ==========================================================================

class TestOpenApi:
    def test_schema_is_generated(self):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        assert "/api/recommendations" in response.json()["paths"]

    def test_docs_page_loads(self):
        assert client.get("/docs").status_code == 200