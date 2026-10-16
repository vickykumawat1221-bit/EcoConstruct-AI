"""Tests for ai_service.py.

No test in this file touches the network or needs a real API key. We pass a
FakeClient into generate_ai_report(client=...), which is exactly why the
`client` argument exists on that function.

Run them with:
    venv\\Scripts\\python.exe -m pytest -v
"""

import json

import pytest
from google.genai.errors import ClientError

import ai_service
from ai_service import (
    DEFAULT_MODEL,
    GeminiAPIError,
    GeminiNotConfiguredError,
    GeminiResponseError,
    generate_ai_report,
    get_api_key,
    get_client,
    get_model,
    reset_client_cache,
)
from recommender import identify_hotspots
from schemas import AIReport, RecommendationRequest

FAKE_KEY = "fake-api-key-for-tests-do-not-use-12345"


# ==========================================================================
# Fake Gemini objects
# ==========================================================================

class FakeResponse:
    """Stands in for google.genai.types.GenerateContentResponse."""

    def __init__(self, text):
        self.text = text


class FakeModels:
    """Stands in for client.models. Records the call so we can assert on it."""

    def __init__(self, text=None, error=None):
        self.text = text
        self.error = error
        self.calls = []

    def generate_content(self, *, model, contents, config=None):
        self.calls.append({"model": model, "contents": contents, "config": config})

        if self.error is not None:
            raise self.error

        return FakeResponse(self.text)


class FakeClient:
    """Stands in for genai.Client."""

    def __init__(self, text=None, error=None):
        self.models = FakeModels(text=text, error=error)


def collect_keys(node, acc):
    """Recursively gather every dict key inside a nested JSON structure."""
    if isinstance(node, dict):
        for key, value in node.items():
            acc.add(key)
            collect_keys(value, acc)
    elif isinstance(node, list):
        for item in node:
            collect_keys(item, acc)
    return acc


def gemini_json(**overrides):
    """Build a valid AIReport JSON payload, with optional field overrides."""
    payload = {
        "summary": "Cement dominates the footprint of this project.",
        "recommendations": [
            {
                "material": "Cement (OPC)",
                "priority": "HIGH",
                "action": "Request the supplier EPD and the clinker-to-cement ratio.",
                "reason": "Largest share of the supplied emissions.",
                "requires_validation": True,
            }
        ],
        "procurement_plan": ["Collect the cement supplier EPD."],
        "assumptions": ["Emission factors were supplied by the client."],
    }
    payload.update(overrides)
    return json.dumps(payload)


# ==========================================================================
# Shared fixtures
# ==========================================================================

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Every test starts with no API key and no model set, and a clean cache."""
    monkeypatch.delenv(ai_service.ENV_API_KEY, raising=False)
    monkeypatch.delenv(ai_service.ENV_MODEL, raising=False)
    reset_client_cache()
    yield
    reset_client_cache()


@pytest.fixture
def api_key_set(monkeypatch):
    monkeypatch.setenv(ai_service.ENV_API_KEY, FAKE_KEY)


@pytest.fixture
def sample_request():
    return RecommendationRequest(
        project_name="Riverside Tower",
        total_emissions_kg=12000,
        materials=[
            {
                "name": "Cement (OPC)",
                "quantity": 10,
                "unit": "tonne",
                "emissions_kg": 6000,
            },
            {
                "name": "Reinforcing steel",
                "quantity": 12,
                "unit": "tonne",
                "emissions_kg": 2400,
            },
        ],
    )


@pytest.fixture
def sample_hotspots(sample_request):
    return identify_hotspots(sample_request.materials)


# ==========================================================================
# Configuration
# ==========================================================================

class TestConfiguration:
    def test_missing_api_key_raises_clear_error(self):
        with pytest.raises(GeminiNotConfiguredError) as info:
            get_api_key()

        assert ai_service.ENV_API_KEY in str(info.value)

    def test_blank_api_key_also_raises(self, monkeypatch):
        monkeypatch.setenv(ai_service.ENV_API_KEY, "   ")
        with pytest.raises(GeminiNotConfiguredError):
            get_api_key()

    def test_api_key_is_read_from_environment(self, monkeypatch):
        monkeypatch.setenv(ai_service.ENV_API_KEY, FAKE_KEY)
        assert get_api_key() == FAKE_KEY

    def test_model_defaults_when_env_not_set(self):
        assert get_model() == DEFAULT_MODEL

    def test_model_comes_from_environment(self, monkeypatch):
        monkeypatch.setenv(ai_service.ENV_MODEL, "gemini-3.5-flash-lite")
        assert get_model() == "gemini-3.5-flash-lite"

    def test_blank_model_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv(ai_service.ENV_MODEL, "  ")
        assert get_model() == DEFAULT_MODEL

    def test_client_cache_reuses_the_same_client(self, api_key_set):
        first = get_client()
        second = get_client()
        assert first is second

    def test_reset_client_cache_clears_it(self, api_key_set):
        first = get_client()
        reset_client_cache()
        assert get_client() is not first


# ==========================================================================
# Happy path
# ==========================================================================

class TestGenerateAiReportSuccess:
    def test_returns_a_validated_ai_report(self, api_key_set, sample_request, sample_hotspots):
        client = FakeClient(text=gemini_json())

        report = generate_ai_report(sample_request, sample_hotspots, client=client)

        assert isinstance(report, AIReport)
        assert report.summary.startswith("Cement dominates")
        assert len(report.recommendations) == 1
        assert report.recommendations[0].material == "Cement (OPC)"
        assert report.recommendations[0].priority == "HIGH"

    def test_uses_the_model_from_the_environment(
        self, api_key_set, monkeypatch, sample_request, sample_hotspots
    ):
        monkeypatch.setenv(ai_service.ENV_MODEL, "gemini-3.5-flash-lite")
        client = FakeClient(text=gemini_json())

        generate_ai_report(sample_request, sample_hotspots, client=client)

        assert client.models.calls[0]["model"] == "gemini-3.5-flash-lite"

    def test_model_argument_overrides_the_environment(
        self, api_key_set, sample_request, sample_hotspots
    ):
        client = FakeClient(text=gemini_json())

        generate_ai_report(
            sample_request, sample_hotspots, client=client, model="some-other-model"
        )

        assert client.models.calls[0]["model"] == "some-other-model"

    def test_requests_json_matching_the_ai_report_schema(
        self, api_key_set, sample_request, sample_hotspots
    ):
        client = FakeClient(text=gemini_json())
        generate_ai_report(sample_request, sample_hotspots, client=client)

        config = client.models.calls[0]["config"]
        assert config.response_mime_type == "application/json"
        # See the comment in ai_service.py: response_schema sends snake_case
        # keys that the Gemini API rejects with a 400.
        assert config.response_schema is None
        assert config.response_json_schema is not None

    def test_uses_response_json_schema_not_response_schema(
        self, api_key_set, sample_request, sample_hotspots
    ):
        """Regression guard for the 400 'Invalid JSON payload received' bug.

        google-genai 2.31.0 emits snake_case keys when given a Pydantic model
        via response_schema. The Gemini API rejects those outright, so the
        endpoint silently degraded to the rule-based fallback. This test
        fails if anyone switches back to response_schema.
        """
        client = FakeClient(text=gemini_json())
        generate_ai_report(sample_request, sample_hotspots, client=client)

        config = client.models.calls[0]["config"]
        assert getattr(config, "response_schema", None) is None
        assert config.response_json_schema == AIReport.model_json_schema()

    def test_payload_sent_to_gemini_has_no_snake_case_schema_keys(
        self, api_key_set, sample_request, sample_hotspots
    ):
        """Capture the REAL request body and assert the API would accept it.

        This does not call the network: it swaps out the SDK's request method
        and inspects the dict the SDK was going to send.
        """
        client = FakeClient(text=gemini_json())
        generate_ai_report(sample_request, sample_hotspots, client=client)

        config = client.models.calls[0]["config"]
        payload = json.loads(json.dumps(config.response_json_schema))

        keys = set()
        collect_keys(payload, keys)

        # These are the keys that triggered the 400 on the API side.
        assert "additional_properties" not in keys
        assert "min_length" not in keys
        assert "property_ordering" not in keys

        # And the camelCase equivalents should be present instead.
        assert "additionalProperties" in keys
        assert "minLength" in keys

    def test_schema_describes_the_ai_report_fields(
        self, api_key_set, sample_request, sample_hotspots
    ):
        client = FakeClient(text=gemini_json())
        generate_ai_report(sample_request, sample_hotspots, client=client)

        schema = client.models.calls[0]["config"].response_json_schema
        assert set(schema["properties"]) == {
            "summary",
            "recommendations",
            "procurement_plan",
            "assumptions",
        }
        # A real JSON Schema (not a Gemini Schema object).
        assert "$defs" in schema or "$ref" in schema or "properties" in schema

    def test_sends_the_project_data_and_hotspots_to_gemini(
        self, api_key_set, sample_request, sample_hotspots
    ):
        client = FakeClient(text=gemini_json())

        generate_ai_report(sample_request, sample_hotspots, client=client)

        prompt = client.models.calls[0]["contents"]
        assert "Riverside Tower" in prompt
        assert "Cement (OPC)" in prompt
        assert "Reinforcing steel" in prompt
        assert "hotspots" in prompt
        # The ranked hotspot share must reach the model (6000 / 8400 = 71.43%).
        assert "71.43" in prompt
        assert "kg CO2e" in prompt

    def test_prompt_contains_the_no_invention_rules(
        self, api_key_set, sample_request, sample_hotspots
    ):
        client = FakeClient(text=gemini_json())

        generate_ai_report(sample_request, sample_hotspots, client=client)

        system = client.models.calls[0]["config"].system_instruction
        assert "Never invent emission factors" in system
        assert "Never invent costs" in system
        assert "Never invent carbon savings" in system

    def test_works_without_hotspots(self, api_key_set, sample_request):
        client = FakeClient(text=gemini_json())

        report = generate_ai_report(sample_request, None, client=client)

        assert report.summary
        assert client.models.calls[0]["contents"]

    def test_works_with_plain_dict_project_data(self, api_key_set, sample_hotspots):
        client = FakeClient(text=gemini_json())

        report = generate_ai_report(
            {
                "project_name": "Riverside Tower",
                "total_emissions_kg": 12000,
                "materials": [{"name": "Cement (OPC)", "quantity": 10,
                               "unit": "tonne", "emissions_kg": 6000}],
            },
            sample_hotspots,
            client=client,
        )

        assert report.summary

    def test_handles_a_zero_emission_project(self, api_key_set):
        request = RecommendationRequest(project_name="Empty site", total_emissions_kg=0)
        client = FakeClient(text=gemini_json(recommendations=[]))

        report = generate_ai_report(request, [], client=client)

        assert report.recommendations == []


# ==========================================================================
# Failure handling
# ==========================================================================

class TestFailureHandling:
    def test_missing_api_key_raises_before_any_api_call(
        self, sample_request, sample_hotspots, monkeypatch
    ):
        """With no client injected and no key, we must fail before building one."""

        def explode(*args, **kwargs):
            raise AssertionError("a real Gemini client must not be built")

        monkeypatch.setattr(ai_service, "get_client", explode)

        with pytest.raises(GeminiNotConfiguredError):
            generate_ai_report(sample_request, sample_hotspots)

    def test_injected_client_needs_no_api_key(self, sample_request, sample_hotspots):
        """Supplying your own client means GEMINI_API_KEY is not consulted."""
        client = FakeClient(text=gemini_json())

        report = generate_ai_report(sample_request, sample_hotspots, client=client)

        assert report.summary

    def test_sdk_client_error_becomes_gemini_api_error(
        self, api_key_set, sample_request, sample_hotspots
    ):
        client = FakeClient(
            error=ClientError(code=400, response_json={"error": {"message": "bad request"}})
        )

        with pytest.raises(GeminiAPIError) as info:
            generate_ai_report(sample_request, sample_hotspots, client=client)

        assert "gemini" in str(info.value).lower()

    def test_unexpected_exception_also_becomes_gemini_api_error(
        self, api_key_set, sample_request, sample_hotspots
    ):
        client = FakeClient(error=ConnectionResetError("connection dropped"))

        with pytest.raises(GeminiAPIError):
            generate_ai_report(sample_request, sample_hotspots, client=client)

    def test_invalid_json_raises_response_error(
        self, api_key_set, sample_request, sample_hotspots
    ):
        client = FakeClient(text="Sorry, I cannot help with that.")

        with pytest.raises(GeminiResponseError) as info:
            generate_ai_report(sample_request, sample_hotspots, client=client)

        assert "valid JSON" in str(info.value)

    def test_json_array_instead_of_object_is_rejected(
        self, api_key_set, sample_request, sample_hotspots
    ):
        client = FakeClient(text="[1, 2, 3]")

        with pytest.raises(GeminiResponseError):
            generate_ai_report(sample_request, sample_hotspots, client=client)

    def test_schema_violation_is_rejected(
        self, api_key_set, sample_request, sample_hotspots
    ):
        """priority must be HIGH / MEDIUM / LOW - anything else must fail."""
        client = FakeClient(
            text=gemini_json(
                recommendations=[
                    {
                        "material": "Cement (OPC)",
                        "priority": "CRITICAL",  # not allowed
                        "action": "Request the EPD.",
                        "reason": "Largest share.",
                    }
                ]
            )
        )

        with pytest.raises(GeminiResponseError) as info:
            generate_ai_report(sample_request, sample_hotspots, client=client)

        assert "priority" in str(info.value)

    def test_missing_required_field_is_rejected(
        self, api_key_set, sample_request, sample_hotspots
    ):
        client = FakeClient(text=json.dumps({"recommendations": []}))  # no summary

        with pytest.raises(GeminiResponseError):
            generate_ai_report(sample_request, sample_hotspots, client=client)

    def test_empty_response_is_rejected(
        self, api_key_set, sample_request, sample_hotspots
    ):
        client = FakeClient(text=None)

        with pytest.raises(GeminiResponseError) as info:
            generate_ai_report(sample_request, sample_hotspots, client=client)

        assert "empty response" in str(info.value)

    def test_whitespace_only_response_is_rejected(
        self, api_key_set, sample_request, sample_hotspots
    ):
        client = FakeClient(text="   ")

        with pytest.raises(GeminiResponseError):
            generate_ai_report(sample_request, sample_hotspots, client=client)


# ==========================================================================
# Secret handling
# ==========================================================================

class TestSecretHandling:
    def test_api_key_never_appears_in_an_api_error_message(
        self, api_key_set, sample_request, sample_hotspots
    ):
        """Even if the SDK echoed the key back at us, it must not escape."""
        leaky_error = ClientError(
            code=401,
            response_json={
                "error": {"message": f"Invalid key {FAKE_KEY} supplied"}
            },
        )
        client = FakeClient(error=leaky_error)

        with pytest.raises(GeminiAPIError) as info:
            generate_ai_report(sample_request, sample_hotspots, client=client)

        assert FAKE_KEY not in str(info.value)
        assert ai_service.REDACTED in str(info.value)

    def test_api_key_never_appears_in_a_response_error_message(
        self, api_key_set, sample_request, sample_hotspots
    ):
        client = FakeClient(text=f"not json {FAKE_KEY}")

        with pytest.raises(GeminiResponseError) as info:
            generate_ai_report(sample_request, sample_hotspots, client=client)

        assert FAKE_KEY not in str(info.value)

    def test_api_key_is_never_sent_in_the_prompt(
        self, api_key_set, sample_request, sample_hotspots
    ):
        client = FakeClient(text=gemini_json())

        generate_ai_report(sample_request, sample_hotspots, client=client)

        assert FAKE_KEY not in client.models.calls[0]["contents"]

    def test_redact_helper_replaces_the_secret(self):
        assert FAKE_KEY not in ai_service._redact(f"key is {FAKE_KEY}", FAKE_KEY)

    def test_redact_helper_tolerates_none(self):
        assert ai_service._redact("nothing to hide", None) == "nothing to hide"


# ==========================================================================
# Hallucination guard
# ==========================================================================

class TestHallucinationGuard:
    def test_invented_material_is_dropped_and_recorded(
        self, api_key_set, sample_request, sample_hotspots
    ):
        client = FakeClient(
            text=gemini_json(
                recommendations=[
                    {
                        "material": "Cement (OPC)",
                        "priority": "HIGH",
                        "action": "Request the supplier EPD.",
                        "reason": "Largest share.",
                    },
                    {
                        "material": "Hempcrete blocks",  # never supplied
                        "priority": "LOW",
                        "action": "Buy hempcrete.",
                        "reason": "Model invented this.",
                    },
                ]
            )
        )

        report = generate_ai_report(sample_request, sample_hotspots, client=client)

        materials = [r.material for r in report.recommendations]
        assert materials == ["Cement (OPC)"]
        assert any("Hempcrete blocks" in note for note in report.assumptions)

    def test_shortened_material_name_is_accepted(
        self, api_key_set, sample_request, sample_hotspots
    ):
        """'Cement' should still match 'Cement (OPC)'."""
        client = FakeClient(
            text=gemini_json(
                recommendations=[
                    {
                        "material": "cement",
                        "priority": "HIGH",
                        "action": "Request the supplier EPD.",
                        "reason": "Largest share.",
                    }
                ]
            )
        )

        report = generate_ai_report(sample_request, sample_hotspots, client=client)

        assert len(report.recommendations) == 1

    def test_nothing_is_dropped_when_all_materials_are_known(
        self, api_key_set, sample_request, sample_hotspots
    ):
        client = FakeClient(text=gemini_json())

        report = generate_ai_report(sample_request, sample_hotspots, client=client)

        assert len(report.recommendations) == 1
        assert not any("Removed" in note for note in report.assumptions)

    def test_guard_skipped_when_client_sent_no_materials(self, api_key_set):
        request = RecommendationRequest(project_name="Empty site", total_emissions_kg=0)
        client = FakeClient(
            text=gemini_json(
                recommendations=[
                    {
                        "material": "Anything at all",
                        "priority": "LOW",
                        "action": "Check it.",
                        "reason": "No source data to check against.",
                    }
                ]
            )
        )

        report = generate_ai_report(request, [], client=client)

        assert len(report.recommendations) == 1

    def test_original_assumptions_are_preserved_when_dropping(
        self, api_key_set, sample_request, sample_hotspots
    ):
        client = FakeClient(
            text=gemini_json(
                assumptions=["Client-supplied factors."],
                recommendations=[
                    {
                        "material": "Aluminium framing",
                        "priority": "LOW",
                        "action": "Check it.",
                        "reason": "Invented.",
                    }
                ],
            )
        )

        report = generate_ai_report(sample_request, sample_hotspots, client=client)

        assert report.assumptions[0] == "Client-supplied factors."
        assert len(report.assumptions) == 2


# ==========================================================================
# No real network access
# ==========================================================================

class TestNoNetworkAccess:
    def test_suite_runs_with_no_api_key_configured(self, sample_request, sample_hotspots):
        """The whole suite must be runnable on a machine with no key at all."""
        import os

        assert ai_service.ENV_API_KEY not in os.environ

        # get_api_key() complains, but an injected client still works fine.
        with pytest.raises(GeminiNotConfiguredError):
            get_api_key()

        report = generate_ai_report(
            sample_request,
            sample_hotspots,
            client=FakeClient(text=gemini_json()),
        )
        assert report.summary

    def test_generate_ai_report_with_fake_client_never_builds_a_real_client(
        self, api_key_set, sample_request, sample_hotspots, monkeypatch
    ):
        def explode():
            raise AssertionError("a real Gemini client must not be built in tests")

        monkeypatch.setattr(ai_service, "get_client", explode)

        client = FakeClient(text=gemini_json())
        report = generate_ai_report(sample_request, sample_hotspots, client=client)

        assert report.summary