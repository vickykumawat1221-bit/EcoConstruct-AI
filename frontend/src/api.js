/**
 * API client for the EcoConstruct AI FastAPI backend.
 *
 * Every number the UI shows comes from these endpoints - the backend owns the
 * emission factors, the costs, the calculations, the hotspot ranking and the
 * AI/fallback report. The frontend does not keep a second copy of any factor.
 *
 * During development Vite proxies `/api` and `/health` to the backend on
 * http://localhost:8000 (see vite.config.js), so requests are same-origin and
 * CORS never comes into play. In a build you can point VITE_API_BASE at a
 * deployed backend instead.
 */

const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

/** Error carrying the HTTP status and the backend's message. */
export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function describeDetail(body, status) {
  if (!body) return `Request failed with status ${status}.`;
  if (typeof body === "string") return body;
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail)) {
    // Pydantic validation errors: [{ loc, msg, type }, ...]
    return body.detail
      .map((item) => {
        const where = Array.isArray(item.loc) ? item.loc.slice(1).join(".") : "";
        return where ? `${where}: ${item.msg}` : item.msg;
      })
      .join("; ");
  }
  if (body.detail) return JSON.stringify(body.detail);
  if (body.message) return body.message;
  return `Request failed with status ${status}.`;
}

async function request(path, { method = "GET", body } = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (error) {
    throw new ApiError(
      "Cannot reach the EcoConstruct backend. Is it running on port 8000?",
      0,
      error?.message,
    );
  }

  const text = await response.text();
  let parsed = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }

  if (!response.ok) {
    throw new ApiError(describeDetail(parsed, response.status), response.status, parsed);
  }

  return parsed;
}

export const api = {
  /** Liveness + dataset status. */
  health: () => request("/health"),

  /** Member 2's dataset joined with Member 4's unit costs. */
  getMaterials: ({ category, includeUnverified = true } = {}) => {
    const params = new URLSearchParams();
    if (category) params.set("category", category);
    params.set("include_unverified", String(includeUnverified));
    return request(`/api/materials?${params.toString()}`);
  },

  /** Total a bill of quantities through Member 2's engine. */
  calculate: (items, allowUnverified = true) =>
    request("/api/calculate", {
      method: "POST",
      body: { items, allow_unverified: allowUnverified },
    }),

  /** Compare a baseline material against an alternative for one quantity. */
  compareMaterials: (payload) =>
    request("/api/compare-materials", { method: "POST", body: payload }),

  /** The aggregated dashboard payload for a supplied scenario. */
  dashboard: (payload) => request("/api/dashboard", { method: "POST", body: payload }),

  /** Baseline vs alternative scenario, with carbon and cost. */
  simulate: (payload) => request("/api/simulate", { method: "POST", body: payload }),

  /** The built-in demo baseline/alternative pair. */
  defaultScenarios: () => request("/api/scenarios/default"),

  /** Member 3's audit: hotspots plus a Gemini-or-fallback report. */
  recommendations: (payload) =>
    request("/api/recommendations", { method: "POST", body: payload }),
};
