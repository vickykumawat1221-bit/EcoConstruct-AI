"""Gemini (Google Gen AI) integration for EcoConstruct AI - Member 3.

This module turns a project + its hotspots into a structured AIReport.

The rule that shapes this whole file: Gemini is allowed to *explain and
prioritise* the numbers we give it, but it is never allowed to *supply* new
numbers. All emission factors, quantities and totals come from the client data
in the request. Anything Gemini states that is not backed by the request must
be listed in `assumptions` so a human can check it.

Nothing in this file prints or returns the API key.
"""

import json
import os
from typing import Any, Dict, List, Mapping, Optional, Sequence

from google import genai
from google.genai import types
from google.genai.errors import APIError
from pydantic import ValidationError

from schemas import AIReport

# Loading a .env file is a convenience for local development. It is optional:
# if python-dotenv is not installed we just read real environment variables.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

ENV_API_KEY = "GEMINI_API_KEY"
ENV_MODEL = "GEMINI_MODEL"

# Verified against our live API key with 5 real AIReport requests per model:
#
#   gemini-3.5-flash-lite -> 5/5 success, ~2.5s  <-- chosen (only reliable one)
#   gemini-3.8-flash      -> 1/5 success, ~2.6s  (503 high demand)
#   gemini-3.6-flash      -> 0/5 success, ~0.8s  (503 high demand)
#   gemini-3.5-flash      -> 0/5 success, ~0.8s  (503 high demand)
#   gemini-2.5-flash      -> 404, permanently retired for new API keys
#
# Note: with a trivial "Say OK" prompt the bigger models answer fine, but with
# the full structured-output request they hit a contended capacity pool and
# 503. Always benchmark with the REAL payload, not a ping.
#
# Google flash capacity recovers over time. To re-check what your key can use,
# send the real AIReport request to each candidate - a model appearing in
# models.list() does NOT mean it works.
DEFAULT_MODEL = "gemini-3.5-flash-lite"

# Low temperature keeps the output factual and repeatable. This is an audit
# tool, not a creative writing task.
TEMPERATURE = 0.2
MAX_OUTPUT_TOKENS = 4096

# Upper bound on how long a single Gemini call may hang. Without this, an
# overloaded model (gemini-3.8-flash was observed taking 45s before a 504)
# blocks the HTTP request long enough that the fallback never gets a chance
# to run in time.
REQUEST_TIMEOUT_MS = 30_000

# Placeholder used anywhere a secret would otherwise be shown.
REDACTED = "***REDACTED***"


# --------------------------------------------------------------------------
# Exceptions
# --------------------------------------------------------------------------

class AIReportError(Exception):
    """Base class for every error this module raises."""


class GeminiNotConfiguredError(AIReportError):
    """Raised when GEMINI_API_KEY is missing, so the call cannot be made."""


class GeminiAPIError(AIReportError):
    """Raised when the Gemini API call itself fails (network, quota, 5xx...)."""


class GeminiResponseError(AIReportError):
    """Raised when Gemini replies, but the reply is not a usable AIReport."""


# --------------------------------------------------------------------------
# Environment / client helpers
# --------------------------------------------------------------------------

def get_api_key() -> str:
    """Read GEMINI_API_KEY from the environment.

    Raises:
        GeminiNotConfiguredError: if the variable is unset or blank.

    The key is returned to the caller (the SDK needs it) but is never logged,
    printed or included in any error message.
    """
    api_key = (os.getenv(ENV_API_KEY) or "").strip()

    if not api_key:
        raise GeminiNotConfiguredError(
            f"{ENV_API_KEY} is not set. Add it to your environment (or a .env "
            f"file) before generating an AI report."
        )

    return api_key


def _current_api_key() -> Optional[str]:
    """Read GEMINI_API_KEY without raising, for secret-scrubbing only.

    This is deliberately separate from get_api_key(): redaction must keep
    working even when the caller injected their own client and so we never
    strictly required a key. Returns None when the variable is not set.
    """
    return (os.getenv(ENV_API_KEY) or "").strip() or None


def get_model() -> str:
    """Read GEMINI_MODEL from the environment, or fall back to DEFAULT_MODEL."""
    model = (os.getenv(ENV_MODEL) or "").strip()
    return model or DEFAULT_MODEL


# Clients are cached per API key so we do not rebuild one on every request.
_CLIENT_CACHE: Dict[str, genai.Client] = {}


def get_client(api_key: Optional[str] = None) -> genai.Client:
    """Build (or reuse) a Google Gen AI client.

    Args:
        api_key: Optional explicit key. Normally left as None so the key is
                 read from the environment.
    """
    key = api_key if api_key is not None else get_api_key()

    if key not in _CLIENT_CACHE:
        # timeout bounds how long a single call can hang; see REQUEST_TIMEOUT_MS.
        _CLIENT_CACHE[key] = genai.Client(
            api_key=key,
            http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
        )

    return _CLIENT_CACHE[key]


def reset_client_cache() -> None:
    """Empty the client cache. Useful in tests and when the key is rotated."""
    _CLIENT_CACHE.clear()


def _redact(text: Any, *secrets: Optional[str]) -> str:
    """Replace any known secret inside `text` with REDACTED.

    This is a belt-and-braces guarantee: even if an underlying library ever
    echoed the API key back at us in an exception message, it will not escape.
    """
    cleaned = str(text)

    for secret in secrets:
        if secret:
            cleaned = cleaned.replace(secret, REDACTED)

    return cleaned


def redact_secrets(text: Any, *secrets: Optional[str]) -> str:
    """Public, default-safe version of _redact(), for other modules to use.

    Unlike _redact(), this ALWAYS also scrubs whatever GEMINI_API_KEY is
    currently set to, even if the caller forgets to pass it. That means a
    caller cannot accidentally write the key to a log file.

    Use this whenever logging or displaying text that originated from an
    external service, e.g. a Gemini error message.
    """
    return _redact(text, *secrets, _current_api_key())


# --------------------------------------------------------------------------
# Prompt building
# --------------------------------------------------------------------------

SYSTEM_INSTRUCTION = """\
You are a construction carbon auditor working on a project called
EcoConstruct AI. You receive a project's material breakdown in kg CO2e and a
list of its emission hotspots. You return a structured audit report.

ABSOLUTE RULES
1. Never invent emission factors. Every emissions_kg, quantity, percentage and
   total you mention must come from the JSON data you were given.
2. Never invent costs, prices, currency amounts or percentages.
3. Never invent carbon savings, reduction figures or "tonnes saved". This is
   the single most important rule: a carbon audit must not contain numbers
   nobody measured.
4. Phrase every "action" as something to request, review, verify or
   investigate (for example "request the supplier EPD", "review the mix
   design"), never as a guaranteed saving.
5. Only produce a recommendation for a material that appears in the supplied
   materials list. Do not introduce new materials.
6. Use only these priority values: HIGH, MEDIUM, LOW.
7. Base the priority on the emission share you were given.
8. If the stated project total and the sum of the materials disagree, say so
   in "assumptions".
9. If you are unsure about a figure, say so in "assumptions" rather than
   guessing.
10. Set "requires_validation" to true unless the underlying data is already
    verified by the client.

Write plainly. No preamble, no markdown, no code fences.
"""


def _read(obj: Any, key: str, default: Any = None) -> Any:
    """Read `key` from an object or a dict, so both styles work."""
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _to_float(value: Any) -> float:
    """Convert to float, treating None / '' / bad input as 0.0."""
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _build_payload(project_data: Any, hotspots: Optional[Sequence[Mapping]]) -> Dict[str, Any]:
    """Turn the request into a plain JSON-serialisable dictionary.

    Note the two totals we send:
        total_emissions_kg_stated          what the client claimed
        total_emissions_kg_from_materials  what the material lines actually add to
    If these disagree we ask Gemini to record that as an assumption rather
    than silently picking one.
    """
    materials = list(_read(project_data, "materials", None) or [])
    hotspot_list = list(hotspots) if hotspots else []

    material_rows = [
        {
            "name": _read(material, "name", "unknown material"),
            "quantity": _to_float(_read(material, "quantity", 0)),
            "unit": _read(material, "unit", ""),
            "emissions_kg": _to_float(_read(material, "emissions_kg", 0)),
        }
        for material in materials
    ]

    hotspot_rows = [
        {
            "rank": hotspot.get("rank"),
            "material": hotspot.get("material"),
            "emissions_kg": hotspot.get("emissions_kg"),
            "percentage_of_total": hotspot.get("percentage"),
        }
        for hotspot in hotspot_list
    ]

    return {
        "project_name": _read(project_data, "project_name", "unnamed project"),
        "total_emissions_kg_stated": _read(project_data, "total_emissions_kg", None),
        "total_emissions_kg_from_materials": sum(
            row["emissions_kg"] for row in material_rows
        ),
        "unit": "kg CO2e",
        "materials": material_rows,
        "hotspots": hotspot_rows,
    }


def _build_user_prompt(project_data: Any, hotspots: Optional[Sequence[Mapping]]) -> str:
    """Build the user message: the project data plus the hotspot results."""
    payload = _build_payload(project_data, hotspots)

    pretty = json.dumps(payload, indent=2, ensure_ascii=False, default=str)

    return (
        "Produce the carbon audit report for this project using only the data "
        "below.\n\n"
        "PROJECT DATA (JSON):\n"
        f"{pretty}"
    )


# --------------------------------------------------------------------------
# Response parsing and validation
# --------------------------------------------------------------------------

def _read_response_text(response: Any) -> str:
    """Pull the raw JSON string out of a Gemini response.

    Raises:
        GeminiResponseError: if there is no text (empty answer, or the request
            was blocked before a candidate was produced).
    """
    raw = getattr(response, "text", None)

    if raw is None or not str(raw).strip():
        raise GeminiResponseError(
            "Gemini returned an empty response. This usually means the request "
            "was blocked by a safety filter or produced no candidates. Check "
            "the prompt feedback for details."
        )

    return str(raw)


def _parse_report(raw_text: str) -> AIReport:
    """Turn Gemini's JSON text into a validated AIReport.

    Raises:
        GeminiResponseError: if the text is not JSON, or does not match the
            AIReport model.
    """
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        # Truncate: a malformed response can be enormous and would make the
        # error message unreadable.
        snippet = raw_text[:300]
        raise GeminiResponseError(
            f"Gemini did not return valid JSON ({exc}). First 300 characters "
            f"were: {snippet!r}"
        ) from exc

    if not isinstance(payload, dict):
        raise GeminiResponseError(
            f"Gemini returned a {type(payload).__name__} instead of a JSON "
            f"object matching the AIReport model."
        )

    try:
        return AIReport.model_validate(payload)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise GeminiResponseError(
            f"Gemini's response did not match the AIReport model: {problems}"
        ) from exc


def _names_match(candidate: str, known: str) -> bool:
    """Loose name comparison used to catch invented materials.

    One name counts as matching the other if either contains the other, so
    "Cement" matches "Cement (OPC)". Case and surrounding spaces are ignored.
    """
    candidate = str(candidate).strip().lower()
    known = str(known).strip().lower()

    if not candidate or not known:
        return False

    return candidate in known or known in candidate


def _drop_unknown_materials(report: AIReport, project_data: Any) -> AIReport:
    """Remove recommendations about materials the client never supplied.

    This is the guard against a hallucinated material reaching the client. If
    a recommendation names something that is not in the request, we drop it
    and record exactly what was removed in `assumptions`, so nothing
    disappears silently.

    Note: this is a deliberately simple containment check. A genuine synonym
    that shares no text with the original name (for example "Steel rebar" vs
    "Reinforcing steel") will be dropped. Tune the rule if that bites you.
    """
    known_names = [
        str(_read(material, "name", "")).strip()
        for material in (_read(project_data, "materials", None) or [])
    ]
    known_names = [name for name in known_names if name]

    # If the client sent no materials there is nothing to verify against.
    if not known_names:
        return report

    kept: List[Any] = []
    removed: List[str] = []

    for recommendation in report.recommendations:
        if any(_names_match(recommendation.material, known) for known in known_names):
            kept.append(recommendation)
        else:
            removed.append(recommendation.material)

    if not removed:
        return report

    note = (
        f"Removed {len(removed)} Gemini recommendation(s) that referred to "
        f"materials not present in the request data: {', '.join(removed)}."
    )

    return report.model_copy(
        update={
            "recommendations": kept,
            "assumptions": [*report.assumptions, note],
        }
    )


# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------

def generate_ai_report(
    project_data: Any,
    hotspots: Optional[Sequence[Mapping]] = None,
    client: Optional[genai.Client] = None,
    model: Optional[str] = None,
) -> AIReport:
    """Ask Gemini for a structured audit report and validate the answer.

    Args:
        project_data: A RecommendationRequest (or an equivalent dict) holding
                      project_name, total_emissions_kg and materials.
        hotspots: Output of identify_hotspots() - the ranked emission hotspots.
        client: Optional pre-built Google Gen AI client. Tests pass a fake one
                here so no real API key or network call is needed. When you
                supply your own client we do not read GEMINI_API_KEY at all.
        model: Optional model name override. Normally left as None so
               GEMINI_MODEL is used.

    Returns:
        A validated AIReport.

    Raises:
        GeminiNotConfiguredError: GEMINI_API_KEY is missing and no client was
                                  supplied.
        GeminiAPIError: the Gemini call failed.
        GeminiResponseError: Gemini replied but the reply was unusable.
    """
    # Resolve configuration first so we fail fast, before doing any work.
    # The key is read here purely so we can scrub it out of any error text.
    api_key = _current_api_key()

    # We only strictly need the key when we are the ones building the client.
    if client is not None:
        gemini_client = client
    else:
        api_key = get_api_key()
        gemini_client = get_client(api_key)

    model_name = model if model else get_model()

    user_prompt = _build_user_prompt(project_data, hotspots)

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        # STRUCTURED OUTPUT - do not "simplify" this back to
        # response_schema=AIReport.
        #
        # In google-genai 2.31.0, response_schema sends the JSON Schema with
        # snake_case keys ("additional_properties", "min_length"), and the
        # Gemini API rejects that with:
        #     400 INVALID_ARGUMENT: Invalid JSON payload received.
        #     Unknown name "additional_properties" at
        #     'generation_config.response_schema': Cannot find field.
        #
        # response_json_schema is the SDK's supported path for passing a JSON
        # Schema directly. It keeps proper camelCase keys plus $defs/$ref,
        # which the API accepts. Verified working against the live API.
        response_mime_type="application/json",
        response_json_schema=AIReport.model_json_schema(),
        temperature=TEMPERATURE,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )

    try:
        response = gemini_client.models.generate_content(
            model=model_name,
            contents=user_prompt,
            config=config,
        )
    except APIError as exc:
        raise GeminiAPIError(
            f"The Gemini API call failed for model '{model_name}': "
            f"{_redact(exc, api_key)}"
        ) from exc
    except Exception as exc:
        # Covers transport problems the SDK does not wrap in APIError.
        raise GeminiAPIError(
            f"Could not complete the Gemini API call for model "
            f"'{model_name}': {_redact(exc, api_key)}"
        ) from exc

    raw_text = _read_response_text(response)

    try:
        report = _parse_report(raw_text)
    except GeminiResponseError as exc:
        # Scrub here too: the JSON snippet in the message came from the API.
        raise GeminiResponseError(_redact(exc, api_key)) from exc

    return _drop_unknown_materials(report, project_data)