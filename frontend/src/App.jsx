import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Building2,
  CheckCircle2,
  Cpu,
  Database,
  Download,
  Factory,
  Gauge,
  Leaf,
  Lightbulb,
  Menu,
  Plus,
  Recycle,
  RefreshCw,
  ShieldCheck,
  Sprout,
  Target,
  Trash2,
  TrendingDown,
  Wifi,
  WifiOff,
  X,
  IndianRupee,
  Sparkles,
} from "lucide-react";

import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import "./App.css";
import { api } from "./api";

/*
 * EcoConstruct AI frontend.
 *
 * This component is a thin view over the FastAPI backend. It owns no emission
 * factor, no cost and no carbon arithmetic of its own:
 *
 *   GET  /api/materials            -> the material picker + factors + costs
 *   POST /api/calculate            -> authoritative per-item emissions
 *   POST /api/compare-materials    -> Green Material Intelligence
 *   POST /api/dashboard            -> totals, charts, score, hotspots, advice
 *   POST /api/recommendations      -> Member 3's hotspot report (Gemini/fallback)
 *
 * The UI recomputes nothing on its own except quantity x factor for immediate
 * feedback while typing; every headline number is rendered from the backend
 * response once the debounced request settles.
 */

const PIE_COLORS = [
  "#238457",
  "#77bd8c",
  "#b6d9a8",
  "#4b9bb0",
  "#b9a5df",
  "#e0a458",
  "#c98b8b",
];

// Used only if GET /api/scenarios/default is unavailable, so the dashboard is
// never empty on first load. The real values come from the backend.
const DEMO_FALLBACK = {
  floor_area_m2: 8500,
  items: [
    { material_id: "MAT002", quantity: 2400, note: "Podium and basement slabs" },
    { material_id: "MAT005", quantity: 310000, note: "Reinforcement to slabs and columns" },
    { material_id: "MAT010", quantity: 185000, note: "Roof and primary steel frame" },
    { material_id: "MAT006", quantity: 210000, note: "External masonry" },
    { material_id: "MAT007", quantity: 1650, note: "Blockwork and screeds" },
    { material_id: "MAT009", quantity: 24000, note: "Site plant and delivery fleet" },
  ],
};

const numberFormatter = new Intl.NumberFormat("en-IN", {
  maximumFractionDigits: 2,
});

const formatNumber = (value) => {
  const numeric = Number(value);
  return numberFormatter.format(Number.isFinite(numeric) ? numeric : 0);
};

// The backend works in kg CO2e everywhere; the UI presents tonnes.
const kgToTonnes = (kg) => (Number(kg) || 0) / 1000;
const formatTonnes = (kg) => formatNumber(kgToTonnes(kg));
const formatTonnesShort = (kg) => {
  const tonnes = kgToTonnes(kg);
  return Math.abs(tonnes) >= 1000 ? `${formatNumber(tonnes / 1000)}k` : formatNumber(tonnes);
};

const formatCurrency = (value, currency = "INR") => {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return "—";
  }
  try {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: currency || "INR",
      maximumFractionDigits: 0,
    }).format(Number(value));
  } catch {
    return `${currency} ${formatNumber(value)}`;
  }
};

const PRIORITY_TONE = { HIGH: "green", MEDIUM: "blue", LOW: "purple" };

function useDebouncedValue(value, delay) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

function StatCard({ title, value, unit, icon: Icon, subtitle, trend, tone }) {
  return (
    <article className="stat-card">
      <div className="stat-top">
        <span className={`stat-icon ${tone}`}>
          <Icon size={20} />
        </span>
        {trend && (
          <span className="trend-label">
            <ArrowDownRight size={14} />
            {trend}
          </span>
        )}
      </div>
      <p className="stat-title">{title}</p>
      <div className="stat-value-row">
        <h2>{value}</h2>
        {unit && <span className="stat-unit">{unit}</span>}
      </div>
      <p className="stat-subtitle">{subtitle}</p>
    </article>
  );
}

function PriorityTag({ priority }) {
  if (!priority) return null;
  return <span className={`priority-tag ${priority.toLowerCase()}`}>{priority}</span>;
}

/* ------------------------------------------------------------------ */
/* Green Material Intelligence: real like-for-like comparison          */
/* ------------------------------------------------------------------ */

function GreenMaterialIntelligence({ catalog, opportunities }) {
  const comparable = useMemo(
    () => catalog.filter((m) => Number.isFinite(Number(m.emission_factor))),
    [catalog],
  );

  const [baseId, setBaseId] = useState("");
  const [altId, setAltId] = useState("");
  const [quantity, setQuantity] = useState("10");
  const [result, setResult] = useState(null);
  const [state, setState] = useState("idle");
  const [error, setError] = useState("");

  const baseMeta = comparable.find((m) => m.material_id === baseId) || null;

  // Alternatives mirror the engine's own pairing rule (simulation.py
  // suggest_substitutions): same category AND same unit. That keeps the
  // comparison like-for-like and guarantees Member 2's compare_materials()
  // accepts it instead of rejecting a cross-unit request.
  const alternatives = useMemo(() => {
    if (!baseMeta) return [];
    return comparable
      .filter(
        (m) =>
          m.material_id !== baseMeta.material_id &&
          m.category === baseMeta.category &&
          m.unit === baseMeta.unit,
      )
      .sort((a, b) => a.emission_factor - b.emission_factor);
  }, [comparable, baseMeta]);

  // Pick a sensible default baseline: one that actually has an alternative.
  useEffect(() => {
    if (!comparable.length || baseId) return;
    const withAlternatives =
      comparable.find((m) =>
        comparable.some(
          (o) =>
            o.material_id !== m.material_id &&
            o.category === m.category &&
            o.unit === m.unit,
        ),
      ) || comparable[0];
    setBaseId(withAlternatives.material_id);
  }, [comparable, baseId]);

  useEffect(() => {
    if (!baseMeta) return;
    const first = alternatives.find((m) => m.material_id !== baseId);
    setAltId(first ? first.material_id : "");
    setResult(null);
  }, [baseId, baseMeta, alternatives]);

  const parsedQuantity = Math.max(0, Number(quantity) || 0);
  const debouncedQuantity = useDebouncedValue(parsedQuantity, 300);
  const debouncedAltId = useDebouncedValue(altId, 300);

  useEffect(() => {
    if (!baseId || !debouncedAltId || debouncedQuantity <= 0) {
      setResult(null);
      setState("idle");
      return undefined;
    }
    let cancelled = false;
    setState("loading");
    setError("");
    api
      .compareMaterials({
        baseline_material_id: baseId,
        alternative_material_id: debouncedAltId,
        quantity: debouncedQuantity,
        allow_unverified: true,
      })
      .then((data) => {
        if (cancelled) return;
        setResult(data);
        setState("ok");
      })
      .catch((err) => {
        if (cancelled) return;
        setResult(null);
        setState("error");
        setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [baseId, debouncedAltId, debouncedQuantity]);

  const altMeta = comparable.find((m) => m.material_id === (result?.alternative_material_id || altId)) || null;

  const baselineEmissionsKg = result
    ? result.baseline_emissions_kg_co2e
    : baseMeta
      ? parsedQuantity * baseMeta.emission_factor
      : 0;
  const alternativeEmissionsKg = result
    ? result.alternative_emissions_kg_co2e
    : altMeta
      ? parsedQuantity * altMeta.emission_factor
      : 0;
  const savedKg = Math.max(0, baselineEmissionsKg - alternativeEmissionsKg);
  const reductionPercent =
    baselineEmissionsKg > 0 ? (savedKg / baselineEmissionsKg) * 100 : 0;

  const currency = baseMeta?.cost_currency || altMeta?.cost_currency || "INR";
  const baselineCost = baseMeta?.unit_cost != null ? parsedQuantity * baseMeta.unit_cost : null;
  const alternativeCost = altMeta?.unit_cost != null ? parsedQuantity * altMeta.unit_cost : null;

  const topOpportunity = opportunities?.[0] || null;

  return (
    <section className="green-intelligence-section" id="green-materials">
      <div className="green-section-heading">
        <div>
          <div className="section-kicker">LOW-CARBON DECISION SUPPORT</div>
          <h2>Green Material Intelligence</h2>
          <p>
            Compare materials through the carbon engine. Every figure below is
            calculated by the backend from the shared dataset.
          </p>
        </div>
        <div className="green-heading-icon">
          <Sprout size={25} />
        </div>
      </div>

      <div className="green-intelligence-grid">
        <article className="panel green-controls-panel">
          <div className="green-panel-title">
            <div className="panel-icon">
              <Recycle size={19} />
            </div>
            <div>
              <h3>Material comparison</h3>
              <p>Choose a material and a replacement of the same unit.</p>
            </div>
          </div>

          <div className="green-form-field">
            <label htmlFor="green-material">Conventional material</label>
            <select
              id="green-material"
              value={baseId}
              onChange={(event) => setBaseId(event.target.value)}
              disabled={!comparable.length}
            >
              {comparable.map((m) => (
                <option value={m.material_id} key={m.material_id}>
                  {m.material_name} · {m.material_variant || m.material_id}
                </option>
              ))}
            </select>
          </div>

          <div className="green-form-field">
            <label htmlFor="green-quantity">
              Comparison quantity ({baseMeta?.unit || "unit"})
            </label>
            <input
              id="green-quantity"
              type="number"
              min="0"
              step="any"
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
            />
          </div>

          <div className="green-form-field">
            <label htmlFor="green-alternative">Alternative material</label>
            <select
              id="green-alternative"
              value={altId}
              onChange={(event) => setAltId(event.target.value)}
              disabled={!alternatives.length}
            >
              {alternatives.length ? (
                alternatives.map((m) => (
                  <option value={m.material_id} key={m.material_id}>
                    {m.material_name} · {m.material_variant || m.material_id}
                  </option>
                ))
              ) : (
                <option value="">No same-unit alternative available</option>
              )}
            </select>
          </div>

          <div className="green-tracked-note">
            <Building2 size={17} />
            <span>
              Engine factor for {baseMeta?.material_name || "—"}:{" "}
              <strong>
                {baseMeta ? `${formatNumber(baseMeta.emission_factor)} ${baseMeta.factor_unit}` : "—"}
              </strong>
            </span>
          </div>

          <div className="green-demo-note">
            <ShieldCheck size={16} />
            {baseMeta?.verification_status === "verified"
              ? "This factor is marked verified in the dataset."
              : "Factors are illustrative placeholders. Confirm supplier data before deciding."}
          </div>
        </article>

        <article className="panel green-results-panel">
          <div className="green-results-heading">
            <div>
              <div className="section-kicker">COMPARISON RESULTS</div>
              <h3>Potential carbon impact</h3>
            </div>
            <span className="green-demo-badge">
              <Cpu size={13} />
              Live engine
            </span>
          </div>

          <div className="green-comparison-cards">
            <div className="green-comparison-card">
              <span>Conventional material</span>
              <h4>{baseMeta?.material_name || "—"}</h4>
              <strong>{formatTonnes(baselineEmissionsKg)}</strong>
              <small>tCO₂e</small>
            </div>

            <div className="green-comparison-arrow">
              <ArrowDownRight size={21} />
            </div>

            <div className="green-comparison-card alternative-card">
              <span>Alternative option</span>
              <h4>{altMeta?.material_name || "—"}</h4>
              <strong>{formatTonnes(alternativeEmissionsKg)}</strong>
              <small>tCO₂e</small>
            </div>
          </div>

          <div className="green-saving-banner">
            <div className="green-saving-icon">
              <TrendingDown size={23} />
            </div>
            <div>
              <span>Illustrative emissions difference</span>
              <strong>{formatTonnes(savedKg)} tCO₂e</strong>
            </div>
            <div className="green-saving-percent">
              {formatNumber(reductionPercent)}%
              <small>lower</small>
            </div>
          </div>

          <div className="green-cost-grid">
            <div>
              <span className="green-cost-icon">
                <IndianRupee size={16} />
              </span>
              <p>Conventional cost estimate</p>
              <strong>{formatCurrency(baselineCost, currency)}</strong>
            </div>
            <div>
              <span className="green-cost-icon">
                <IndianRupee size={16} />
              </span>
              <p>Alternative cost estimate</p>
              <strong>{formatCurrency(alternativeCost, currency)}</strong>
            </div>
          </div>

          {state === "error" && (
            <div className="inline-error">
              <AlertTriangle size={16} /> {error}
            </div>
          )}

          <div className="green-alternative-advice">
            <div className="green-advice-icon">
              <Lightbulb size={18} />
            </div>
            <div>
              <h4>Recommendation to investigate</h4>
              {topOpportunity ? (
                <>
                  <p>
                    The engine ranks <strong>{topOpportunity.alternative_material_name}</strong> as
                    the best substitution for <strong>{topOpportunity.material_name}</strong>, saving
                    about {formatTonnes(topOpportunity.emissions_reduction_kg_co2e)} tCO₂e for this project.
                  </p>
                  <small>{topOpportunity.note}</small>
                </>
              ) : (
                <>
                  <p>
                    Add materials to the register to see the substitutions the engine ranks highest
                    for this project.
                  </p>
                  <small>Substitutions are indicative and require design-team validation.</small>
                </>
              )}
            </div>
          </div>
        </article>
      </div>

      <div className="green-disclaimer">
        <ShieldCheck size={17} />
        <p>
          <strong>Important:</strong> Material substitutions are not automatically
          equivalent by mass, function or structural performance. Validate quantities,
          costs, environmental data and engineering requirements before using results
          in practice.
        </p>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Substitution opportunities from the engine                          */
/* ------------------------------------------------------------------ */

function OpportunitiesPanel({ opportunities }) {
  if (!opportunities?.length) return null;
  return (
    <article className="panel opportunities-panel" id="opportunities">
      <div className="panel-heading">
        <div>
          <div className="section-kicker">ENGINE OPPORTUNITIES</div>
          <h2>Substitutions worth investigating</h2>
          <p>Ranked by carbon reduction for this exact project</p>
        </div>
        <div className="panel-icon">
          <Gauge size={19} />
        </div>
      </div>

      <div className="opp-list">
        {opportunities.map((op) => (
          <div className="opp-item" key={`${op.material_id}-${op.alternative_material_id}`}>
            <div className="opp-swap">
              <strong>{op.material_name}</strong>
              <ArrowUpRight size={15} />
              <strong>{op.alternative_material_name}</strong>
            </div>
            <div className="opp-metrics">
              <span className="opp-reduction">
                −{formatTonnes(op.emissions_reduction_kg_co2e)} tCO₂e
              </span>
              <span className="opp-share">
                {formatNumber(op.emissions_reduction_percent_of_material)}% of that material
              </span>
              <span className="opp-cost">
                {op.cost_saving === null || op.cost_saving === undefined
                  ? "cost: unknown"
                  : `cost delta ${formatCurrency(op.cost_saving, op.currency || "INR")}`}
              </span>
            </div>
          </div>
        ))}
      </div>

      <div className="chart-footnote">
        <span className="chart-footnote-icon">
          <ShieldCheck size={15} />
        </span>
        <p>Every substitution requires engineering validation and a supplier quotation.</p>
      </div>
    </article>
  );
}

/* ------------------------------------------------------------------ */
/* Main application                                                    */
/* ------------------------------------------------------------------ */

function App() {
  const [catalog, setCatalog] = useState([]);
  const [connection, setConnection] = useState("connecting");
  const [connectionError, setConnectionError] = useState("");
  const [health, setHealth] = useState(null);

  const [register, setRegister] = useState([]);
  const [projectName, setProjectName] = useState("Green Building Project");
  const [floorArea, setFloorArea] = useState("8500");

  const [dashboard, setDashboard] = useState(null);
  const [dashState, setDashState] = useState("idle");
  const [dashError, setDashError] = useState("");

  const [advisor, setAdvisor] = useState(null);
  const [advisorState, setAdvisorState] = useState("idle");
  const [advisorError, setAdvisorError] = useState("");

  const [targetReduction, setTargetReduction] = useState(10);
  const [showForm, setShowForm] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [notice, setNotice] = useState("");

  const [newMaterialId, setNewMaterialId] = useState("");
  const [newQuantity, setNewQuantity] = useState("");

  const catalogById = useMemo(
    () => new Map(catalog.map((m) => [m.material_id, m])),
    [catalog],
  );

  /* ---------------- bootstrap: health, catalog, demo seed ----------- */
  const bootstrap = useCallback(async () => {
    setConnection("connecting");
    setConnectionError("");
    try {
      const [healthResult, materials, defaults] = await Promise.all([
        api.health(),
        api.getMaterials(),
        api.defaultScenarios().catch(() => null),
      ]);
      setHealth(healthResult);
      setCatalog(materials.materials || []);
      setConnection("ok");

      const seed = defaults?.baseline?.items?.length
        ? {
            floor_area_m2: defaults.baseline.floor_area_m2 ?? DEMO_FALLBACK.floor_area_m2,
            items: defaults.baseline.items,
          }
        : DEMO_FALLBACK;

      setFloorArea(String(seed.floor_area_m2 ?? ""));
      setRegister(
        seed.items.map((item, index) => ({
          id: `seed-${index}`,
          materialId: item.material_id,
          quantity: item.quantity,
          note: item.note || "",
        })),
      );
      setNewMaterialId((current) => current || materials.materials?.[0]?.material_id || "");
    } catch (err) {
      setConnection("error");
      setConnectionError(err.message);
    }
  }, []);

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  /* ---------------- dashboard: debounced POST /api/dashboard -------- */
  const scenarioPayload = useMemo(() => {
    const items = register
      .map((line) => ({
        material_id: line.materialId,
        quantity: Number(line.quantity),
        note: line.note || "",
      }))
      .filter((item) => item.material_id && Number.isFinite(item.quantity) && item.quantity > 0);

    if (!items.length) return null;

    const area = Number(floorArea);
    return {
      project_name: projectName.trim() || "Untitled project",
      include_opportunities: true,
      opportunity_limit: 5,
      scenario: {
        name: projectName.trim() || "Current project",
        description: "Live material register from the dashboard",
        floor_area_m2: Number.isFinite(area) && area > 0 ? area : null,
        items,
      },
    };
  }, [register, projectName, floorArea]);

  const debouncedScenarioPayload = useDebouncedValue(scenarioPayload, 350);

  useEffect(() => {
    if (!debouncedScenarioPayload) {
      setDashboard(null);
      setDashState("idle");
      setDashError("");
      return undefined;
    }
    let cancelled = false;
    setDashState("loading");
    api
      .dashboard(debouncedScenarioPayload)
      .then((data) => {
        if (cancelled) return;
        setDashboard(data);
        setDashState("ok");
        setDashError("");
      })
      .catch((err) => {
        if (cancelled) return;
        setDashboard(null);
        setDashState("error");
        setDashError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [debouncedScenarioPayload]);

  /* ---------------- derived register rows (from backend factors) ---- */
  const registerRows = useMemo(
    () =>
      register
        .map((line) => {
          const meta = catalogById.get(line.materialId);
          if (!meta) return null;
          const quantity = Number(line.quantity) || 0;
          return {
            ...line,
            meta,
            quantity,
            emissionsKg: quantity * meta.emission_factor,
            cost:
              meta.unit_cost != null ? quantity * meta.unit_cost : null,
          };
        })
        .filter(Boolean),
    [register, catalogById],
  );

  const localTotalKg = useMemo(
    () => registerRows.reduce((sum, row) => sum + row.emissionsKg, 0),
    [registerRows],
  );
  const localCost = useMemo(
    () =>
      registerRows.every((row) => row.cost === null)
        ? null
        : registerRows.reduce((sum, row) => sum + (row.cost || 0), 0),
    [registerRows],
  );

  /* ---------------- authoritative values from the dashboard --------- */
  const totals = dashboard?.totals || null;
  const totalKg = totals ? totals.emissions_kg_co2e : localTotalKg;
  const totalTonnes = kgToTonnes(totalKg);
  const totalCost = totals ? totals.cost : localCost;
  const currency = totals?.currency || registerRows[0]?.meta?.cost_currency || "INR";
  const costComplete = totals ? totals.cost_is_complete : registerRows.every((r) => r.cost !== null);

  const byMaterial = useMemo(() => {
    if (dashboard?.emissions_by_material?.length) {
      return dashboard.emissions_by_material.map((row, index) => ({
        key: row.material_id,
        name: row.material_name,
        unit: row.unit,
        emissionsKg: row.emissions_kg_co2e,
        share: row.share_percent,
        cost: row.cost,
        priority: row.priority,
        color: PIE_COLORS[index % PIE_COLORS.length],
      }));
    }
    return registerRows.map((row, index) => ({
      key: `${row.materialId}-${row.id}`,
      name: row.meta.material_name,
      unit: row.meta.unit,
      emissionsKg: row.emissionsKg,
      share: localTotalKg > 0 ? (row.emissionsKg / localTotalKg) * 100 : 0,
      cost: row.cost,
      priority: null,
      color: PIE_COLORS[index % PIE_COLORS.length],
    }));
  }, [dashboard, registerRows, localTotalKg]);

  const byCategory = useMemo(() => {
    if (dashboard?.emissions_by_category?.length) {
      return dashboard.emissions_by_category.map((row) => ({
        name: row.category,
        emissionsKg: row.emissions_kg_co2e,
      }));
    }
    const grouped = new Map();
    registerRows.forEach((row) => {
      const category = row.meta.category;
      grouped.set(category, (grouped.get(category) || 0) + row.emissionsKg);
    });
    return [...grouped.entries()].map(([name, emissionsKg]) => ({ name, emissionsKg }));
  }, [dashboard, registerRows]);

  const intensity = dashboard?.intensity || null;
  const score = intensity?.sustainability_score ?? null;

  const recommendations = useMemo(() => {
    if (dashboard?.recommendations?.length) {
      const hotspotByName = new Map((dashboard.hotspots || []).map((h) => [h.material, h]));
      return dashboard.recommendations.map((rec) => ({
        ...rec,
        share: hotspotByName.get(rec.material)?.percentage ?? null,
      }));
    }
    return [];
  }, [dashboard]);

  const topHotspot = dashboard?.hotspots?.[0] || null;

  /* ---------------- actions ---------------------------------------- */
  const handleAddMaterial = (event) => {
    event.preventDefault();
    const quantity = Number(newQuantity);
    if (!newMaterialId) {
      setNotice("Choose a material first.");
      return;
    }
    if (!Number.isFinite(quantity) || quantity <= 0) {
      setNotice("Please enter a quantity greater than zero.");
      return;
    }
    setRegister((current) => [
      ...current,
      { id: `line-${Date.now()}`, materialId: newMaterialId, quantity, note: "" },
    ]);
    setNewQuantity("");
    setShowForm(false);
    setNotice(`${catalogById.get(newMaterialId)?.material_name || "Material"} added.`);
  };

  const handleDeleteMaterial = (id) => {
    setRegister((current) => current.filter((line) => line.id !== id));
    setNotice("Material removed.");
  };

  const handleClearRegister = () => {
    setRegister([]);
    setDashboard(null);
    setAdvisor(null);
    setNotice("Material register cleared.");
  };

  const handleLoadDemo = async () => {
    try {
      const defaults = await api.defaultScenarios();
      setProjectName("Green Building Project");
      setFloorArea(String(defaults.baseline.floor_area_m2 ?? DEMO_FALLBACK.floor_area_m2));
      setRegister(
        defaults.baseline.items.map((item, index) => ({
          id: `demo-${index}`,
          materialId: item.material_id,
          quantity: item.quantity,
          note: item.note || "",
        })),
      );
      setNotice("Demo project loaded from the backend.");
    } catch (err) {
      setNotice(`Could not load the demo: ${err.message}`);
    }
  };

  const handleExport = () => {
    const rows = [
      ["EcoConstruct AI — Carbon Report"],
      ["Project", projectName],
      ["Floor area (m2)", floorArea || ""],
      ["Estimated embodied emissions (tCO2e)", totalTonnes],
      ["Estimated material cost", totalCost ?? ""],
      ["Currency", currency],
      ["Sustainability score", score ?? "not available"],
      ["Rating", intensity?.rating ?? ""],
      ["Target reduction (%)", targetReduction],
      ["Target emissions (tCO2e)", totalTonnes * (1 - targetReduction / 100)],
      [],
      ["Material ID", "Material", "Variant", "Category", "Quantity", "Unit", "Factor", "Factor unit", "Emissions (tCO2e)", "Share (%)", "Cost"],
      ...registerRows.map((row) => [
        row.materialId,
        row.meta.material_name,
        row.meta.material_variant,
        row.meta.category,
        row.quantity,
        row.meta.unit,
        row.meta.emission_factor,
        row.meta.factor_unit,
        kgToTonnes(row.emissionsKg),
        localTotalKg > 0 ? (row.emissionsKg / localTotalKg) * 100 : 0,
        row.cost ?? "",
      ]),
      [],
      ["Note", "Emission factors and costs are illustrative placeholders. Verify before real-world use."],
    ];

    const csv = rows
      .map((row) =>
        row
          .map((cell) => `"${String(cell ?? "").replaceAll('"', '""')}"`)
          .join(","),
      )
      .join("\n");

    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "ecoconstruct-carbon-report.csv";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setNotice("Your CSV report has been downloaded.");
  };

  const runAdvisor = useCallback(async () => {
    const materials = registerRows
      .filter((row) => row.quantity > 0)
      .map((row) => ({
        name: row.meta.material_name,
        quantity: row.quantity,
        unit: row.meta.unit,
        emissions_kg: row.emissionsKg,
      }));

    if (!materials.length) {
      setAdvisorState("error");
      setAdvisorError("Add at least one material before running the audit.");
      return;
    }

    const total = materials.reduce((sum, item) => sum + item.emissions_kg, 0);
    setAdvisorState("loading");
    setAdvisorError("");
    try {
      const data = await api.recommendations({
        project_name: projectName.trim() || "Untitled project",
        total_emissions_kg: Number(total.toFixed(6)),
        materials,
      });
      setAdvisor(data);
      setAdvisorState("ok");
    } catch (err) {
      setAdvisor(null);
      setAdvisorState("error");
      setAdvisorError(err.message);
    }
  }, [registerRows, projectName]);

  const categories = useMemo(
    () => [...new Set(catalog.map((m) => m.category))].sort(),
    [catalog],
  );

  const connected = connection === "ok";
  const dashLoading = dashState === "loading";

  return (
    <div className="app-shell">
      {sidebarOpen && (
        <button
          className="mobile-backdrop"
          aria-label="Close navigation"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside className={`sidebar ${sidebarOpen ? "sidebar-open" : ""}`}>
        <div className="brand">
          <div className="brand-mark">
            <Leaf size={23} />
          </div>
          <div>
            <h1>EcoConstruct</h1>
            <span>AI SUSTAINABILITY</span>
          </div>
          <button
            className="icon-button mobile-close"
            onClick={() => setSidebarOpen(false)}
            aria-label="Close menu"
          >
            <X size={19} />
          </button>
        </div>

        <div className="workspace-label">WORKSPACE</div>

        <nav className="sidebar-nav">
          <a className="nav-link active" href="#overview" onClick={() => setSidebarOpen(false)}>
            <BarChart3 size={19} /> Overview
          </a>
          <a className="nav-link" href="#materials" onClick={() => setSidebarOpen(false)}>
            <Building2 size={19} /> Materials
          </a>
          <a className="nav-link" href="#green-materials" onClick={() => setSidebarOpen(false)}>
            <Sprout size={19} /> Green Materials
            <span className="nav-badge">NEW</span>
          </a>
          <a className="nav-link" href="#analytics" onClick={() => setSidebarOpen(false)}>
            <Activity size={19} /> Analytics
          </a>
          <a className="nav-link" href="#advisor" onClick={() => setSidebarOpen(false)}>
            <Lightbulb size={19} /> AI Advisor
          </a>
          <a className="nav-link" href="#goals" onClick={() => setSidebarOpen(false)}>
            <Target size={19} /> Carbon Goals
          </a>
        </nav>

        <div className="sidebar-bottom">
          <div className="sidebar-eco-card">
            <div className="eco-card-icon">
              <Recycle size={20} />
            </div>
            <h3>Build greener.</h3>
            <p>Better material decisions start with better data.</p>
            <div className="eco-card-line">
              <span>Engine connected</span>
              <span>{connected ? "●" : "○"}</span>
            </div>
          </div>

          <div className="sidebar-user">
            <div className="avatar">EC</div>
            <div>
              <strong>Project Workspace</strong>
              <span>
                {connected
                  ? `${catalog.length} materials · ${health?.datasets?.costs_loaded ? "costs loaded" : "costs pending"}`
                  : "Backend offline"}
              </span>
            </div>
          </div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="topbar-left">
            <button
              className="icon-button mobile-menu"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open menu"
            >
              <Menu size={21} />
            </button>
            <div className="breadcrumb">
              Workspace <span>/</span> <strong>Overview</strong>
            </div>
          </div>

          <div className="topbar-right">
            <span className={`live-status ${connected ? "" : "offline"}`}>
              {connected ? (
                <>
                  <span className="live-dot" /> Engine connected
                </>
              ) : (
                <>
                  <WifiOff size={14} /> Backend offline
                </>
              )}
            </span>
            <div className="topbar-avatar">
              <Leaf size={18} />
            </div>
          </div>
        </header>

        {dashLoading && <div className="loading-bar" />}

        <div className="page-content" id="overview">
          <section className="page-heading">
            <div>
              <div className="eyebrow">
                <span className="eyebrow-line" />
                CONSTRUCTION INTELLIGENCE
              </div>
              <h1>Carbon Overview</h1>
              <p>
                Understand your project's footprint. Discover smarter ways to build.
              </p>
            </div>
            <div className="heading-actions">
              <button className="secondary-button" onClick={handleLoadDemo}>
                <Database size={16} /> Load demo
              </button>
              <button className="primary-button" onClick={handleExport}>
                <Download size={17} /> Export report
              </button>
            </div>
          </section>

          {connection === "error" && (
            <div className="conn-banner" role="alert">
              <AlertTriangle size={18} />
              <div>
                <strong>Cannot reach the backend.</strong>
                <span>
                  {connectionError} Start it with <code>./start.sh</code> (FastAPI on
                  port 8000) and retry.
                </span>
              </div>
              <button className="secondary-button" onClick={bootstrap}>
                <RefreshCw size={15} /> Retry
              </button>
            </div>
          )}

          {notice && (
            <div className="notice" role="status">
              <CheckCircle2 size={17} />
              <span>{notice}</span>
              <button
                className="notice-close"
                onClick={() => setNotice("")}
                aria-label="Dismiss message"
              >
                <X size={16} />
              </button>
            </div>
          )}

          <section className="project-banner">
            <div className="project-banner-icon">
              <Building2 size={24} />
            </div>
            <div className="project-name-wrap">
              <label htmlFor="project-name">CURRENT PROJECT</label>
              <input
                id="project-name"
                className="project-name-input"
                value={projectName}
                onChange={(event) => setProjectName(event.target.value)}
                maxLength={100}
              />
            </div>
            <div className="project-banner-meta">
              <label className="floor-area-field">
                <span>Floor area (m²)</span>
                <input
                  type="number"
                  min="1"
                  step="any"
                  value={floorArea}
                  onChange={(event) => setFloorArea(event.target.value)}
                  aria-label="Floor area in square metres"
                />
              </label>
              <span className="project-meta-dot" /> Estimated cost{" "}
              <strong>{formatCurrency(totalCost, currency)}</strong>
              {!costComplete && <em> (incomplete)</em>}
            </div>
          </section>

          <section className="stats-grid">
            <StatCard
              title="Estimated Embodied Carbon"
              value={formatTonnesShort(totalKg)}
              unit="tCO₂e"
              icon={Factory}
              subtitle={totals ? "From the carbon engine" : "From current register"}
              tone="green"
            />
            <StatCard
              title="Sustainability Score"
              value={score ?? "—"}
              unit={score != null ? `/100 · ${intensity.rating}` : ""}
              icon={Leaf}
              subtitle={
                score != null
                  ? `${formatNumber(intensity.emissions_kg_per_m2)} kg CO₂e/m²`
                  : "Add a floor area (m²) to score"
              }
              tone="mint"
            />
            <StatCard
              title="Materials Tracked"
              value={registerRows.length}
              icon={Building2}
              subtitle={`${byCategory.length} categories in play`}
              tone="blue"
            />
            <StatCard
              title="Reduction Scenario"
              value={formatTonnesShort((totalKg * targetReduction) / 100)}
              unit="tCO₂e"
              icon={TrendingDown}
              subtitle={`${targetReduction}% below current estimate`}
              trend="Target"
              tone="purple"
            />
          </section>

          <section className="content-grid" id="analytics">
            <article className="panel emissions-panel">
              <div className="panel-heading">
                <div>
                  <div className="section-kicker">EMISSIONS BREAKDOWN</div>
                  <h2>Project carbon profile</h2>
                  <p>Emissions by material category (cradle-to-gate)</p>
                </div>
                <div className="panel-icon">
                  <Activity size={19} />
                </div>
              </div>

              <div className="chart-legend">
                <span>
                  <i className="legend-dot primary-dot" /> Estimated emissions
                </span>
                <span className="chart-unit">tCO₂e</span>
              </div>

              <div className="chart-container">
                {byCategory.length ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart
                      data={byCategory.map((row) => ({
                        name: row.name,
                        emissions: Number(kgToTonnes(row.emissionsKg).toFixed(4)),
                      }))}
                      margin={{ top: 12, right: 8, left: -15, bottom: 0 }}
                    >
                      <defs>
                        <linearGradient id="emissionGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#24875a" stopOpacity={0.24} />
                          <stop offset="100%" stopColor="#24875a" stopOpacity={0.015} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke="#e9efea" strokeDasharray="4 5" vertical={false} />
                      <XAxis
                        dataKey="name"
                        tick={{ fill: "#7c8d82", fontSize: 11 }}
                        axisLine={false}
                        tickLine={false}
                        dy={10}
                      />
                      <YAxis tick={{ fill: "#7c8d82", fontSize: 11 }} axisLine={false} tickLine={false} />
                      <Tooltip formatter={(value) => [`${formatNumber(value)} tCO₂e`, "Emissions"]} />
                      <Area
                        type="monotone"
                        dataKey="emissions"
                        stroke="#218354"
                        strokeWidth={3}
                        fill="url(#emissionGradient)"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="empty-state">
                    <Activity size={28} />
                    <p>Add materials to see the category profile.</p>
                  </div>
                )}
              </div>

              <div className="chart-footnote">
                <span className="chart-footnote-icon">
                  <Activity size={15} />
                </span>
                <p>
                  Categories come straight from the emission-factor dataset. Transport,
                  waste, water and end-of-life are excluded.
                </p>
              </div>
            </article>

            <article className="panel materials-chart-panel">
              <div className="panel-heading">
                <div>
                  <div className="section-kicker">MATERIAL INTELLIGENCE</div>
                  <h2>Carbon by material</h2>
                  <p>Where your footprint comes from</p>
                </div>
                <div className="panel-icon">
                  <Recycle size={19} />
                </div>
              </div>

              {byMaterial.length > 0 && totalKg > 0 ? (
                <>
                  <div className="donut-wrap">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={byMaterial.map((row) => ({ name: row.name, emissions: row.emissionsKg }))}
                          dataKey="emissions"
                          nameKey="name"
                          innerRadius="65%"
                          outerRadius="88%"
                          paddingAngle={3}
                          stroke="none"
                        >
                          {byMaterial.map((row) => (
                            <Cell key={row.key} fill={row.color} />
                          ))}
                        </Pie>
                        <Tooltip formatter={(value) => [`${formatTonnes(value)} tCO₂e`, "Emissions"]} />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="donut-center">
                      <span>TOTAL</span>
                      <strong>{formatTonnesShort(totalKg)}</strong>
                      <small>tCO₂e</small>
                    </div>
                  </div>

                  <div className="material-legend">
                    {byMaterial.map((row) => (
                      <div className="material-legend-row" key={row.key}>
                        <div className="material-legend-name">
                          <span className="material-legend-dot" style={{ background: row.color }} />
                          <span>{row.name}</span>
                          <PriorityTag priority={row.priority} />
                        </div>
                        <strong>{formatNumber(row.share)}%</strong>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <div className="empty-state">
                  <Recycle size={28} />
                  <p>Add materials to see your carbon breakdown.</p>
                </div>
              )}
            </article>
          </section>

          <section className="content-grid lower-grid" id="materials">
            <article className="panel material-table-panel">
              <div className="panel-heading table-heading">
                <div>
                  <div className="section-kicker">RESOURCE INVENTORY</div>
                  <h2>Material register</h2>
                  <p>Pick materials from the dataset — quantities use each material's own unit</p>
                </div>
                <div className="table-actions">
                  {registerRows.length > 0 && (
                    <button className="secondary-button" onClick={handleClearRegister}>
                      <Trash2 size={16} /> Clear
                    </button>
                  )}
                  <button
                    className="secondary-button"
                    onClick={() => setShowForm((current) => !current)}
                    disabled={!catalog.length}
                  >
                    {showForm ? <X size={16} /> : <Plus size={16} />}
                    {showForm ? "Cancel" : "Add material"}
                  </button>
                </div>
              </div>

              {showForm && (
                <form className="add-material-form" onSubmit={handleAddMaterial}>
                  <div className="form-field">
                    <label htmlFor="material-type">Material</label>
                    <select
                      id="material-type"
                      value={newMaterialId}
                      onChange={(event) => setNewMaterialId(event.target.value)}
                    >
                      {categories.map((category) => (
                        <optgroup label={category} key={category}>
                          {catalog
                            .filter((m) => m.category === category)
                            .map((m) => (
                              <option value={m.material_id} key={m.material_id}>
                                {m.material_name} · {m.material_variant || m.material_id}
                              </option>
                            ))}
                        </optgroup>
                      ))}
                    </select>
                  </div>
                  <div className="form-field">
                    <label htmlFor="material-amount">
                      Quantity ({catalogById.get(newMaterialId)?.unit || "unit"})
                    </label>
                    <input
                      id="material-amount"
                      type="number"
                      min="0.0001"
                      step="any"
                      value={newQuantity}
                      onChange={(event) => setNewQuantity(event.target.value)}
                      placeholder="Enter quantity"
                      required
                    />
                  </div>
                  <button type="submit" className="primary-button form-submit">
                    <Plus size={16} /> Add
                  </button>
                </form>
              )}

              <div className="table-scroll">
                <table className="materials-table">
                  <thead>
                    <tr>
                      <th>MATERIAL</th>
                      <th>QUANTITY</th>
                      <th>EMISSIONS</th>
                      <th>COST</th>
                      <th>SHARE</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {registerRows.map((row) => {
                      const share = localTotalKg > 0 ? (row.emissionsKg / localTotalKg) * 100 : 0;
                      return (
                        <tr key={row.id}>
                          <td>
                            <div className="table-material-name">
                              <span className="material-icon">
                                <Building2 size={17} />
                              </span>
                              <div>
                                <strong>{row.meta.material_name}</strong>
                                <span>
                                  {row.meta.material_variant || row.meta.category} ·{" "}
                                  {row.meta.verification_status}
                                </span>
                              </div>
                            </div>
                          </td>
                          <td>
                            {formatNumber(row.quantity)}
                            <span className="table-unit"> {row.meta.unit}</span>
                          </td>
                          <td>
                            <strong>{formatTonnes(row.emissionsKg)}</strong>
                            <span className="table-unit"> tCO₂e</span>
                          </td>
                          <td>{formatCurrency(row.cost, row.meta.cost_currency || currency)}</td>
                          <td>
                            <div className="share-cell">
                              <div className="share-track">
                                <div className="share-fill" style={{ width: `${share}%` }} />
                              </div>
                              <span>{formatNumber(share)}%</span>
                            </div>
                          </td>
                          <td>
                            <button
                              className="delete-button"
                              aria-label={`Delete ${row.meta.material_name}`}
                              title={`Delete ${row.meta.material_name}`}
                              onClick={() => handleDeleteMaterial(row.id)}
                            >
                              <Trash2 size={16} />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {registerRows.length === 0 && (
                  <div className="empty-table">
                    No materials added yet. Select “Add material” to begin.
                  </div>
                )}
              </div>

              <div className="table-footer">
                <span>{registerRows.length} material entries</span>
                <span>
                  Total: <strong>{formatTonnes(totalKg)} tCO₂e</strong>
                  {" · "}
                  <strong>{formatCurrency(totalCost, currency)}</strong>
                </span>
              </div>
            </article>

            <article className="panel score-panel">
              <div className="panel-heading">
                <div>
                  <div className="section-kicker">PROJECT PERFORMANCE</div>
                  <h2>Sustainability score</h2>
                  <p>Backend rubric on carbon intensity</p>
                </div>
                <div className="panel-icon">
                  <ShieldCheck size={19} />
                </div>
              </div>

              {score != null ? (
                <>
                  <div className="score-display">
                    <div className="score-ring" style={{ "--score-angle": `${score * 3.6}deg` }}>
                      <div className="score-ring-inner">
                        <strong>{score}</strong>
                        <span>OUT OF 100</span>
                      </div>
                    </div>
                    <div className="score-summary">
                      <span className="score-status">
                        <span /> Rating {intensity.rating} · {intensity.label}
                      </span>
                      <h3>{intensity.label}</h3>
                      <p>
                        {formatNumber(intensity.emissions_kg_per_m2)} kg CO₂e/m² over{" "}
                        {formatNumber(intensity.floor_area_m2)} m².
                      </p>
                    </div>
                  </div>

                  <div className="score-disclaimer">
                    <ShieldCheck size={16} />
                    {intensity.rubric}
                  </div>
                </>
              ) : (
                <div className="empty-state">
                  <Gauge size={28} />
                  <p>
                    {intensity?.note ||
                      "Add a floor area (m²) and at least one material to compute an intensity score."}
                  </p>
                </div>
              )}
            </article>
          </section>

          <GreenMaterialIntelligence catalog={catalog} opportunities={dashboard?.opportunities} />

          <OpportunitiesPanel opportunities={dashboard?.opportunities} />

          <section className="content-grid advisor-grid" id="advisor">
            <article className="panel advisor-panel">
              <div className="advisor-heading">
                <div className="advisor-icon">
                  <Lightbulb size={22} />
                </div>
                <div>
                  <div className="section-kicker">SMART RECOMMENDATIONS</div>
                  <h2>Your Sustainability Advisor</h2>
                  <p>Hotspot ranking from the shared engine.</p>
                </div>
                <span className="advisor-label">
                  {advisor ? (advisor.source === "gemini" ? "GEMINI" : "RULE-BASED") : "LIVE"}
                </span>
              </div>

              <div className="recommendation-list">
                {recommendations.length ? (
                  recommendations.map((rec, index) => (
                    <div className="recommendation-item" key={`${rec.material}-${index}`}>
                      <div className={`recommendation-icon ${PRIORITY_TONE[rec.priority] || "purple"}`}>
                        {rec.priority === "HIGH" ? (
                          <TrendingDown size={19} />
                        ) : rec.priority === "MEDIUM" ? (
                          <ArrowUpRight size={19} />
                        ) : (
                          <CheckCircle2 size={19} />
                        )}
                      </div>
                      <div className="recommendation-copy">
                        <h3>
                          {rec.material} <PriorityTag priority={rec.priority} />
                        </h3>
                        <p>{rec.action}</p>
                        <small className="recommendation-reason">{rec.reason}</small>
                      </div>
                      <span className="recommendation-saving">
                        {rec.share != null ? `${formatNumber(rec.share)}% of emissions` : "Investigate"}
                      </span>
                    </div>
                  ))
                ) : (
                  <div className="recommendation-item">
                    <div className="recommendation-icon purple">
                      <CheckCircle2 size={19} />
                    </div>
                    <div className="recommendation-copy">
                      <h3>Add your construction materials</h3>
                      <p>Enter quantities to receive engine-backed recommendations.</p>
                    </div>
                    <span className="recommendation-saving">Waiting for data</span>
                  </div>
                )}
              </div>

              {topHotspot && (
                <div className="largest-emitter-note">
                  <span className="largest-emitter-icon">
                    <Factory size={17} />
                  </span>
                  <p>
                    <strong>{topHotspot.material}</strong> is the largest emission source at{" "}
                    <strong>{formatTonnes(topHotspot.emissions_kg)} tCO₂e</strong> (
                    {formatNumber(topHotspot.percentage)}% of the project).
                  </p>
                </div>
              )}

              <div className="advisor-actions">
                <button
                  className="primary-button"
                  onClick={runAdvisor}
                  disabled={advisorState === "loading" || !registerRows.length}
                >
                  {advisorState === "loading" ? (
                    <RefreshCw size={16} className="spin" />
                  ) : (
                    <Sparkles size={16} />
                  )}
                  {advisorState === "loading" ? "Generating report…" : "Generate AI report"}
                </button>
                {advisorError && (
                  <span className="inline-error">
                    <AlertTriangle size={15} /> {advisorError}
                  </span>
                )}
              </div>

              {advisor && (
                <div className="ai-report">
                  <div className="ai-report-summary">
                    <span className="ai-source-badge">
                      {advisor.source === "gemini" ? <Sparkles size={13} /> : <Cpu size={13} />}
                      {advisor.source === "gemini" ? "Gemini report" : "Rule-based fallback"}
                    </span>
                    <p>{advisor.report.summary}</p>
                  </div>

                  {advisor.report.procurement_plan?.length > 0 && (
                    <div className="ai-report-block">
                      <h4>Procurement plan</h4>
                      <ol>
                        {advisor.report.procurement_plan.map((step, index) => (
                          <li key={`${index}-${step}`}>{step}</li>
                        ))}
                      </ol>
                    </div>
                  )}

                  {advisor.report.assumptions?.length > 0 && (
                    <div className="ai-report-block">
                      <h4>Assumptions & data gaps</h4>
                      <ul>
                        {advisor.report.assumptions.map((item, index) => (
                          <li key={`${index}-${item}`}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </article>
          </section>

          <section className="panel goals-panel" id="goals">
            <div className="goals-main">
              <div className="goals-icon">
                <Target size={22} />
              </div>
              <div>
                <div className="section-kicker">CARBON REDUCTION PLANNER</div>
                <h2>Set a reduction scenario</h2>
                <p>
                  Explore what a lower-emissions target could look like for this project's
                  current estimate.
                </p>
              </div>
            </div>

            <div className="goals-controls">
              <label htmlFor="reduction-target">
                Target reduction <strong>{targetReduction}%</strong>
              </label>
              <input
                id="reduction-target"
                className="range-input"
                type="range"
                min="5"
                max="50"
                step="5"
                value={targetReduction}
                onChange={(event) => setTargetReduction(Number(event.target.value))}
              />
              <div className="range-labels">
                <span>5%</span>
                <span>50%</span>
              </div>
            </div>

            <div className="goals-result">
              <span>Target emissions</span>
              <strong>
                {formatNumber(totalTonnes * (1 - targetReduction / 100))} <small>tCO₂e</small>
              </strong>
              <span className="goal-reduction">
                <ArrowDownRight size={15} />{" "}
                {formatNumber((totalTonnes * targetReduction) / 100)} tCO₂e reduction
              </span>
            </div>
          </section>

          <div className="data-notice">
            <ShieldCheck size={17} />
            <div>
              <p>
                <strong>Prototype data notice:</strong> Emission factors and unit costs are
                illustrative placeholders and every row is marked unverified in the dataset.
                Replace them with verified regional or supplier data before using this tool for
                real construction decisions.
              </p>
              {dashboard?.warnings?.length > 0 && (
                <ul className="warning-list">
                  {dashboard.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              )}
              {dashboard?.data_quality && (
                <p className="data-quality-line">
                  <Wifi size={14} /> {dashboard.data_quality.emission_factors_used} factors used ·{" "}
                  {dashboard.data_quality.emission_factors_unverified?.length || 0} unverified ·{" "}
                  {dashboard.data_quality.costs_are_verified ? "costs verified" : "costs unverified"}
                </p>
              )}
              {dashState === "error" && (
                <div className="inline-error">
                  <AlertTriangle size={15} /> {dashError}
                </div>
              )}
            </div>
          </div>

          <footer className="page-footer">
            <div className="footer-brand">
              <Leaf size={17} />
              <strong>EcoConstruct AI</strong>
            </div>
            <span>Building a lower-carbon future, one decision at a time.</span>
            <span className="footer-version">
              {connected ? "ENGINE CONNECTED · API v1.0.0" : "HACKATHON PROTOTYPE · v1.0"}
            </span>
          </footer>
        </div>
      </main>
    </div>
  );
}

export default App;
