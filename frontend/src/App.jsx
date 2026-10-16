import { useMemo, useState } from "react";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Building2,
  CheckCircle2,
  Download,
  Factory,
  Leaf,
  Lightbulb,
  Menu,
  Plus,
  Recycle,
  ShieldCheck,
  Target,
  Trash2,
  TrendingDown,
  X,
  Sprout,
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

const FACTORS = {
  Cement: { factor: 0.85, unit: "tonnes", description: "Cement production" },
  Steel: { factor: 1.9, unit: "tonnes", description: "Structural steel" },
  Bricks: { factor: 0.00022, unit: "bricks", description: "Conventional bricks" },
  Glass: { factor: 1.2, unit: "tonnes", description: "Construction glass" },
  Timber: { factor: 0.15, unit: "tonnes", description: "Timber material" },
};

const INITIAL_MATERIALS = [
  { id: 1, name: "Cement", amount: 120 },
  { id: 2, name: "Steel", amount: 30 },
  { id: 3, name: "Bricks", amount: 20000 },
];

/*
 * Illustrative comparison data for the prototype.
 * These are NOT verified Indian emission factors or market prices.
 * Replace with regional EPD/LCA data and local supplier quotations
 * before using for real construction decisions.
 */
const ALTERNATIVES = {
  Cement: [
    {
      name: "Blended cement",
      factor: 0.68,
      cost: 6900,
      unit: "tonnes",
      reason:
        "Compare approved blended cement products that meet the project's structural specifications.",
      checks: "Verify grade, applicable standards and supplier EPD.",
    },
    {
      name: "Lower-clinker cement",
      factor: 0.62,
      cost: 7200,
      unit: "tonnes",
      reason:
        "Explore products with lower clinker content where suitable for the intended application.",
      checks: "Engineer approval and product-specific carbon data required.",
    },
  ],
  Steel: [
    {
      name: "Recycled-content steel",
      factor: 1.25,
      cost: 65000,
      unit: "tonnes",
      reason:
        "Compare suppliers using recycled content and verified environmental declarations.",
      checks: "Verify grade, strength, traceability and EPD.",
    },
    {
      name: "Lower-carbon steel",
      factor: 1.1,
      cost: 70000,
      unit: "tonnes",
      reason:
        "Investigate steel produced through lower-emission manufacturing routes.",
      checks: "Check mill-specific emissions and technical compliance.",
    },
  ],
  Bricks: [
    {
      name: "Fly ash bricks",
      factor: 0.00016,
      cost: 8,
      unit: "bricks",
      reason:
        "Compare locally manufactured fly ash bricks with conventional masonry.",
      checks: "Verify strength, water absorption, standards and transport.",
    },
    {
      name: "AAC blocks",
      factor: 0.00018,
      cost: 65,
      unit: "bricks",
      reason:
        "Explore lightweight AAC masonry systems as an alternative to conventional bricks.",
      checks: "Compare equivalent wall area, thickness and thermal performance.",
    },
  ],
  Glass: [
    {
      name: "Recycled-content glass",
      factor: 0.95,
      cost: 95000,
      unit: "tonnes",
      reason:
        "Compare glass products with documented recycled content and supplier emissions.",
      checks: "Verify safety, performance, availability and EPD.",
    },
    {
      name: "High-performance glazing",
      factor: 1.05,
      cost: 110000,
      unit: "tonnes",
      reason:
        "Assess glazing that may improve building energy performance over its lifetime.",
      checks: "Compare whole-life impacts, specifications and energy modelling.",
    },
  ],
  Timber: [
    {
      name: "Certified timber",
      factor: 0.1,
      cost: 45000,
      unit: "tonnes",
      reason:
        "Consider responsibly sourced timber with documented chain of custody.",
      checks: "Verify certification, durability, treatment and fire requirements.",
    },
    {
      name: "Reclaimed timber",
      factor: 0.06,
      cost: 35000,
      unit: "tonnes",
      reason:
        "Investigate reusable timber from verified reclaimed sources.",
      checks: "Inspect structural condition, treatment and suitability.",
    },
  ],
};

const formatNumber = (number) =>
  new Intl.NumberFormat("en-IN", {
    maximumFractionDigits: 2,
  }).format(number);

const formatEmissions = (number) =>
  number >= 1000
    ? `${formatNumber(number / 1000)}k`
    : formatNumber(number);

function getMaterialEmissions(material) {
  return material.amount * FACTORS[material.name].factor;
}

function getSustainabilityScore(totalEmissions, materialCount) {
  if (totalEmissions === 0) return 100;

  const emissionsPenalty = Math.min(65, (totalEmissions / 250) * 65);
  const diversityBonus = Math.min(10, materialCount * 2);

  return Math.max(
    10,
    Math.min(100, Math.round(100 - emissionsPenalty + diversityBonus))
  );
}

function getRecommendations(materials, totalEmissions) {
  if (materials.length === 0 || totalEmissions === 0) {
    return [
      {
        title: "Add your construction materials",
        description:
          "Enter quantities to receive demonstration recommendations.",
        saving: "Waiting for data",
        type: "neutral",
      },
    ];
  }

  const sorted = [...materials].sort(
    (a, b) => getMaterialEmissions(b) - getMaterialEmissions(a)
  );

  const largest = sorted[0];
  const largestEmissions = getMaterialEmissions(largest);
  const largestShare = (largestEmissions / totalEmissions) * 100;

  const recommendations = [];

  if (largest.name === "Cement") {
    recommendations.push({
      title: "Explore lower-carbon concrete",
      description:
        "Compare approved blended cement options and supplier-specific environmental data.",
      saving: `${formatNumber(largestShare)}% of emissions`,
      type: "green",
    });
  } else if (largest.name === "Steel") {
    recommendations.push({
      title: "Review steel procurement",
      description:
        "Compare verified environmental declarations and suitable recycled-content steel.",
      saving: `${formatNumber(largestShare)}% of emissions`,
      type: "green",
    });
  } else {
    recommendations.push({
      title: "Review your largest material source",
      description:
        `Compare lower-impact alternatives for ${largest.name.toLowerCase()} and check technical requirements.`,
      saving: `${formatNumber(largestShare)}% of emissions`,
      type: "green",
    });
  }

  recommendations.push({
    title: "Set a carbon reduction target",
    description:
      "Use a reduction scenario to identify opportunities for lowering embodied carbon.",
    saving: `${formatNumber(totalEmissions * 0.1)} tCO₂e at 10%`,
    type: "blue",
  });

  recommendations.push({
    title: "Verify your emissions factors",
    description:
      "Replace demonstration factors with regional, supplier-specific or recognised lifecycle assessment data.",
    saving: "Recommended",
    type: "purple",
  });

  return recommendations;
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

function GreenMaterialIntelligence({ materials }) {
  const [selectedMaterial, setSelectedMaterial] = useState("Cement");
  const [selectedAlternative, setSelectedAlternative] = useState(0);
  const [comparisonQuantity, setComparisonQuantity] = useState("10");

  const quantity = Math.max(0, Number(comparisonQuantity) || 0);
  const alternatives = ALTERNATIVES[selectedMaterial] || [];
  const alternative = alternatives[selectedAlternative] || alternatives[0];
  const baseFactor = FACTORS[selectedMaterial].factor;

  const baselineEmissions = quantity * baseFactor;
  const alternativeEmissions = alternative
    ? quantity * alternative.factor
    : 0;

  const savedEmissions = Math.max(
    0,
    baselineEmissions - alternativeEmissions
  );

  const reductionPercent =
    baselineEmissions > 0
      ? (savedEmissions / baselineEmissions) * 100
      : 0;

  const currentCost =
    quantity *
    ({
      Cement: 7500,
      Steel: 72000,
      Bricks: 10,
      Glass: 100000,
      Timber: 40000,
    }[selectedMaterial]);

  const alternativeCost = quantity * (alternative?.cost || 0);

  const trackedMaterials = materials.filter(
    (material) => material.name === selectedMaterial
  );

  const trackedQuantity = trackedMaterials.reduce(
    (sum, material) => sum + material.amount,
    0
  );

  return (
    <section className="green-intelligence-section" id="green-materials">
      <div className="green-section-heading">
        <div>
          <div className="section-kicker">LOW-CARBON DECISION SUPPORT</div>
          <h2>Green Material Intelligence</h2>
          <p>
            Compare illustrative alternatives and explore possible carbon
            reductions before choosing construction materials.
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
              <p>Choose a material to compare options.</p>
            </div>
          </div>

          <div className="green-form-field">
            <label htmlFor="green-material">Conventional material</label>
            <select
              id="green-material"
              value={selectedMaterial}
              onChange={(event) => {
                setSelectedMaterial(event.target.value);
                setSelectedAlternative(0);
              }}
            >
              {Object.keys(ALTERNATIVES).map((name) => (
                <option value={name} key={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>

          <div className="green-form-field">
            <label htmlFor="green-quantity">
              Comparison quantity ({FACTORS[selectedMaterial].unit})
            </label>
            <input
              id="green-quantity"
              type="number"
              min="0"
              step="any"
              value={comparisonQuantity}
              onChange={(event) => setComparisonQuantity(event.target.value)}
            />
          </div>

          <div className="green-form-field">
            <label htmlFor="green-alternative">Alternative material</label>
            <select
              id="green-alternative"
              value={selectedAlternative}
              onChange={(event) =>
                setSelectedAlternative(Number(event.target.value))
              }
            >
              {alternatives.map((item, index) => (
                <option value={index} key={item.name}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>

          <div className="green-tracked-note">
            <Building2 size={17} />
            <span>
              Your register contains{" "}
              <strong>{formatNumber(trackedQuantity)}</strong>{" "}
              {FACTORS[selectedMaterial].unit} of {selectedMaterial.toLowerCase()}.
            </span>
          </div>

          <div className="green-demo-note">
            <ShieldCheck size={16} />
            Demo factors and costs only. Confirm supplier data and technical
            suitability before making decisions.
          </div>
        </article>

        <article className="panel green-results-panel">
          <div className="green-results-heading">
            <div>
              <div className="section-kicker">COMPARISON RESULTS</div>
              <h3>Potential carbon impact</h3>
            </div>
            <span className="green-demo-badge">
              <Sparkles size={13} />
              Demo model
            </span>
          </div>

          <div className="green-comparison-cards">
            <div className="green-comparison-card">
              <span>Conventional material</span>
              <h4>{selectedMaterial}</h4>
              <strong>{formatNumber(baselineEmissions)}</strong>
              <small>tCO₂e</small>
            </div>

            <div className="green-comparison-arrow">
              <ArrowDownRight size={21} />
            </div>

            <div className="green-comparison-card alternative-card">
              <span>Alternative option</span>
              <h4>{alternative?.name}</h4>
              <strong>{formatNumber(alternativeEmissions)}</strong>
              <small>tCO₂e</small>
            </div>
          </div>

          <div className="green-saving-banner">
            <div className="green-saving-icon">
              <TrendingDown size={23} />
            </div>
            <div>
              <span>Illustrative emissions difference</span>
              <strong>
                {formatNumber(savedEmissions)} tCO₂e
              </strong>
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
              <strong>₹{formatNumber(currentCost)}</strong>
            </div>
            <div>
              <span className="green-cost-icon">
                <IndianRupee size={16} />
              </span>
              <p>Alternative cost estimate</p>
              <strong>₹{formatNumber(alternativeCost)}</strong>
            </div>
          </div>

          <div className="green-alternative-advice">
            <div className="green-advice-icon">
              <Lightbulb size={18} />
            </div>
            <div>
              <h4>Recommendation to investigate</h4>
              <p>{alternative?.reason}</p>
              <small>{alternative?.checks}</small>
            </div>
          </div>
        </article>
      </div>

      <div className="green-disclaimer">
        <ShieldCheck size={17} />
        <p>
          <strong>Important:</strong> This prototype uses illustrative factors
          and price assumptions for demonstration. Material substitutions are
          not automatically equivalent by mass, function or structural
          performance. Validate quantities, costs, environmental data and
          engineering requirements before using results in practice.
        </p>
      </div>
    </section>
  );
}

function App() {
  const [materials, setMaterials] = useState(INITIAL_MATERIALS);
  const [projectName, setProjectName] = useState("Green Building Project");
  const [materialName, setMaterialName] = useState("Cement");
  const [amount, setAmount] = useState("");
  const [targetReduction, setTargetReduction] = useState(10);
  const [showForm, setShowForm] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [notice, setNotice] = useState("");

  const totalEmissions = useMemo(
    () =>
      materials.reduce(
        (total, material) => total + getMaterialEmissions(material),
        0
      ),
    [materials]
  );

  const score = getSustainabilityScore(totalEmissions, materials.length);

  const chartData = useMemo(() => {
    const categories = [
      { name: "Planning", share: 12 },
      { name: "Materials", share: 58 },
      { name: "Transport", share: 18 },
      { name: "Construction", share: 12 },
    ];

    return categories.map((item) => ({
      name: item.name,
      emissions: Number(((totalEmissions * item.share) / 100).toFixed(2)),
    }));
  }, [totalEmissions]);

  const materialData = useMemo(
    () =>
      materials
        .map((material) => ({
          name: material.name,
          emissions: Number(getMaterialEmissions(material).toFixed(4)),
        }))
        .sort((a, b) => b.emissions - a.emissions),
    [materials]
  );

  const highestEmitter = materialData[0];
  const recommendations = getRecommendations(materials, totalEmissions);
  const targetEmissions = totalEmissions * (1 - targetReduction / 100);

  const handleAddMaterial = (event) => {
    event.preventDefault();
    const parsedAmount = Number(amount);

    if (!Number.isFinite(parsedAmount) || parsedAmount <= 0) {
      setNotice("Please enter a quantity greater than zero.");
      return;
    }

    setMaterials((current) => [
      ...current,
      { id: Date.now(), name: materialName, amount: parsedAmount },
    ]);

    setAmount("");
    setShowForm(false);
    setNotice(`${materialName} added successfully.`);
  };

  const handleDeleteMaterial = (id) => {
    setMaterials((current) =>
      current.filter((material) => material.id !== id)
    );
    setNotice("Material removed.");
  };

  const handleExport = () => {
    const rows = [
      ["EcoConstruct AI — Demonstration Carbon Report"],
      ["Project", projectName],
      ["Estimated embodied emissions (tCO2e)", totalEmissions],
      ["Demonstration sustainability score", score],
      ["Target reduction (%)", targetReduction],
      ["Target emissions (tCO2e)", targetEmissions],
      [],
      ["Material", "Quantity", "Unit", "Demo factor", "Emissions (tCO2e)"],
      ...materials.map((material) => [
        material.name,
        material.amount,
        FACTORS[material.name].unit,
        FACTORS[material.name].factor,
        getMaterialEmissions(material),
      ]),
      [],
      ["Note", "Illustrative estimates only; verify all factors before real-world use."],
    ];

    const csv = rows
      .map((row) =>
        row
          .map((cell) => {
            const text = String(cell ?? "");
            return `"${text.replaceAll('"', '""')}"`;
          })
          .join(",")
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
              <span>Carbon insights</span>
              <span>●</span>
            </div>
          </div>

          <div className="sidebar-user">
            <div className="avatar">EC</div>
            <div>
              <strong>Project Workspace</strong>
              <span>Demo environment</span>
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
            <span className="live-status">
              <span className="live-dot" />
              Demo analysis active
            </span>
            <div className="topbar-avatar">
              <Leaf size={18} />
            </div>
          </div>
        </header>

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
            <button className="primary-button" onClick={handleExport}>
              <Download size={17} /> Export report
            </button>
          </section>

          {notice && (
            <div className="notice" role="status">
              <CheckCircle2 size={17} />
              <span>{notice}</span>
              <button className="notice-close" onClick={() => setNotice("")} aria-label="Dismiss message">
                <X size={16} />
              </button>
            </div>
          )}

          <section className="project-banner">
            <div className="project-banner-icon"><Building2 size={24} /></div>
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
              <span className="project-meta-dot" /> Local demo
            </div>
          </section>

          <section className="stats-grid">
            <StatCard
              title="Estimated Embodied Carbon"
              value={formatEmissions(totalEmissions)}
              unit="tCO₂e"
              icon={Factory}
              subtitle="Based on entered materials"
              tone="green"
            />
            <StatCard
              title="Sustainability Score"
              value={score}
              unit="/100"
              icon={Leaf}
              subtitle="Illustrative project indicator"
              tone="mint"
            />
            <StatCard
              title="Materials Tracked"
              value={materials.length}
              icon={Building2}
              subtitle="Material entries in this session"
              tone="blue"
            />
            <StatCard
              title="Reduction Scenario"
              value={formatEmissions((totalEmissions * targetReduction) / 100)}
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
                  <p>Illustrative lifecycle stage allocation</p>
                </div>
                <div className="panel-icon"><Activity size={19} /></div>
              </div>

              <div className="chart-legend">
                <span><i className="legend-dot primary-dot" /> Estimated emissions</span>
                <span className="chart-unit">tCO₂e</span>
              </div>

              <div className="chart-container">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData} margin={{ top: 12, right: 8, left: -15, bottom: 0 }}>
                    <defs>
                      <linearGradient id="emissionGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#24875a" stopOpacity={0.24} />
                        <stop offset="100%" stopColor="#24875a" stopOpacity={0.015} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="#e9efea" strokeDasharray="4 5" vertical={false} />
                    <XAxis dataKey="name" tick={{ fill: "#7c8d82", fontSize: 11 }} axisLine={false} tickLine={false} dy={10} />
                    <YAxis tick={{ fill: "#7c8d82", fontSize: 11 }} axisLine={false} tickLine={false} />
                    <Tooltip formatter={(value) => [`${formatNumber(value)} tCO₂e`, "Emissions"]} />
                    <Area type="monotone" dataKey="emissions" stroke="#218354" strokeWidth={3} fill="url(#emissionGradient)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>

              <div className="chart-footnote">
                <span className="chart-footnote-icon"><Activity size={15} /></span>
                <p>
                  Material quantities drive the total. Lifecycle stages are
                  illustrative allocations, not measured stage-level data.
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
                <div className="panel-icon"><Recycle size={19} /></div>
              </div>

              {materialData.length > 0 && totalEmissions > 0 ? (
                <>
                  <div className="donut-wrap">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie data={materialData} dataKey="emissions" nameKey="name" innerRadius="65%" outerRadius="88%" paddingAngle={3} stroke="none">
                          {materialData.map((entry, index) => (
                            <Cell
                              key={entry.name + index}
                              fill={["#238457", "#77bd8c", "#b6d9a8", "#4b9bb0", "#b9a5df"][index % 5]}
                            />
                          ))}
                        </Pie>
                        <Tooltip formatter={(value) => [`${formatNumber(value)} tCO₂e`, "Emissions"]} />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="donut-center">
                      <span>TOTAL</span>
                      <strong>{formatEmissions(totalEmissions)}</strong>
                      <small>tCO₂e</small>
                    </div>
                  </div>

                  <div className="material-legend">
                    {materialData.map((material, index) => (
                      <div className="material-legend-row" key={material.name}>
                        <div className="material-legend-name">
                          <span
                            className="material-legend-dot"
                            style={{ background: ["#238457", "#77bd8c", "#b6d9a8", "#4b9bb0", "#b9a5df"][index % 5] }}
                          />
                          <span>{material.name}</span>
                        </div>
                        <strong>
                          {totalEmissions > 0 ? formatNumber((material.emissions / totalEmissions) * 100) : "0"}%
                        </strong>
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
                  <p>Manage quantities used in your project</p>
                </div>
                <button className="secondary-button" onClick={() => setShowForm((current) => !current)}>
                  {showForm ? <X size={16} /> : <Plus size={16} />}
                  {showForm ? "Cancel" : "Add material"}
                </button>
              </div>

              {showForm && (
                <form className="add-material-form" onSubmit={handleAddMaterial}>
                  <div className="form-field">
                    <label htmlFor="material-type">Material</label>
                    <select id="material-type" value={materialName} onChange={(event) => setMaterialName(event.target.value)}>
                      {Object.keys(FACTORS).map((name) => <option key={name} value={name}>{name}</option>)}
                    </select>
                  </div>
                  <div className="form-field">
                    <label htmlFor="material-amount">Quantity ({FACTORS[materialName].unit})</label>
                    <input id="material-amount" type="number" min="0.0001" step="any" value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="Enter quantity" required />
                  </div>
                  <button type="submit" className="primary-button form-submit"><Plus size={16} /> Add</button>
                </form>
              )}

              <div className="table-scroll">
                <table className="materials-table">
                  <thead>
                    <tr><th>MATERIAL</th><th>QUANTITY</th><th>EMISSIONS</th><th>SHARE</th><th></th></tr>
                  </thead>
                  <tbody>
                    {materials.map((material) => {
                      const emissions = getMaterialEmissions(material);
                      const share = totalEmissions > 0 ? (emissions / totalEmissions) * 100 : 0;

                      return (
                        <tr key={material.id}>
                          <td>
                            <div className="table-material-name">
                              <span className={`material-icon material-${material.name.toLowerCase()}`}><Building2 size={17} /></span>
                              <div><strong>{material.name}</strong><span>{FACTORS[material.name].description}</span></div>
                            </div>
                          </td>
                          <td>{formatNumber(material.amount)}<span className="table-unit"> {FACTORS[material.name].unit}</span></td>
                          <td><strong>{formatNumber(emissions)}</strong><span className="table-unit"> tCO₂e</span></td>
                          <td>
                            <div className="share-cell">
                              <div className="share-track"><div className="share-fill" style={{ width: `${share}%` }} /></div>
                              <span>{formatNumber(share)}%</span>
                            </div>
                          </td>
                          <td>
                            <button className="delete-button" aria-label={`Delete ${material.name}`} title={`Delete ${material.name}`} onClick={() => handleDeleteMaterial(material.id)}>
                              <Trash2 size={16} />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {materials.length === 0 && <div className="empty-table">No materials added yet. Select “Add material” to begin.</div>}
              </div>

              <div className="table-footer">
                <span>{materials.length} material entries</span>
                <span>Total: <strong>{formatNumber(totalEmissions)} tCO₂e</strong></span>
              </div>
            </article>

            <article className="panel score-panel">
              <div className="panel-heading">
                <div>
                  <div className="section-kicker">PROJECT PERFORMANCE</div>
                  <h2>Sustainability score</h2>
                  <p>A simple demonstration indicator</p>
                </div>
                <div className="panel-icon"><ShieldCheck size={19} /></div>
              </div>

              <div className="score-display">
                <div className="score-ring" style={{ "--score-angle": `${score * 3.6}deg` }}>
                  <div className="score-ring-inner"><strong>{score}</strong><span>OUT OF 100</span></div>
                </div>
                <div className="score-summary">
                  <span className="score-status"><span /> Demo indicator</span>
                  <h3>{score >= 75 ? "Positive start" : score >= 50 ? "Room to improve" : "Review your footprint"}</h3>
                  <p>Use the material breakdown to identify where improvements could make the biggest difference.</p>
                </div>
              </div>

              <div className="score-disclaimer">
                <ShieldCheck size={16} />
                This is a prototype score, not a recognised green-building certification.
              </div>
            </article>
          </section>

          <GreenMaterialIntelligence materials={materials} />

          <section className="content-grid advisor-grid" id="advisor">
            <article className="panel advisor-panel">
              <div className="advisor-heading">
                <div className="advisor-icon"><Lightbulb size={22} /></div>
                <div>
                  <div className="section-kicker">SMART RECOMMENDATIONS</div>
                  <h2>Your Sustainability Advisor</h2>
                  <p>Rule-based demo insights based on your current material data.</p>
                </div>
                <span className="advisor-label">DEMO INSIGHTS</span>
              </div>

              <div className="recommendation-list">
                {recommendations.map((recommendation, index) => (
                  <div className="recommendation-item" key={recommendation.title}>
                    <div className={`recommendation-icon ${recommendation.type}`}>
                      {index === 0 ? <TrendingDown size={19} /> : index === 1 ? <ArrowUpRight size={19} /> : <CheckCircle2 size={19} />}
                    </div>
                    <div className="recommendation-copy">
                      <h3>{recommendation.title}</h3>
                      <p>{recommendation.description}</p>
                    </div>
                    <span className="recommendation-saving">{recommendation.saving}</span>
                  </div>
                ))}
              </div>

              {highestEmitter && (
                <div className="largest-emitter-note">
                  <span className="largest-emitter-icon"><Factory size={17} /></span>
                  <p>
                    <strong>{highestEmitter.name}</strong> is currently your largest estimated material emission source at{" "}
                    <strong>{formatNumber(highestEmitter.emissions)} tCO₂e</strong>.
                  </p>
                </div>
              )}
            </article>
          </section>

          <section className="panel goals-panel" id="goals">
            <div className="goals-main">
              <div className="goals-icon"><Target size={22} /></div>
              <div>
                <div className="section-kicker">CARBON REDUCTION PLANNER</div>
                <h2>Set a reduction scenario</h2>
                <p>Explore what a lower-emissions target could look like for this project's current estimate.</p>
              </div>
            </div>

            <div className="goals-controls">
              <label htmlFor="reduction-target">Target reduction <strong>{targetReduction}%</strong></label>
              <input id="reduction-target" className="range-input" type="range" min="5" max="50" step="5" value={targetReduction} onChange={(event) => setTargetReduction(Number(event.target.value))} />
              <div className="range-labels"><span>5%</span><span>50%</span></div>
            </div>

            <div className="goals-result">
              <span>Target emissions</span>
              <strong>{formatNumber(targetEmissions)} <small>tCO₂e</small></strong>
              <span className="goal-reduction"><ArrowDownRight size={15} /> {formatNumber(totalEmissions - targetEmissions)} tCO₂e reduction</span>
            </div>
          </section>

          <div className="data-notice">
            <ShieldCheck size={17} />
            <p>
              <strong>Prototype data notice:</strong> Emissions factors, score and lifecycle allocations are illustrative estimates. Replace them with verified regional or supplier data before using this tool for real construction decisions.
            </p>
          </div>

          <footer className="page-footer">
            <div className="footer-brand"><Leaf size={17} /><strong>EcoConstruct AI</strong></div>
            <span>Building a lower-carbon future, one decision at a time.</span>
            <span className="footer-version">HACKATHON PROTOTYPE · v1.0</span>
          </footer>
        </div>
      </main>
    </div>
  );
}

export default App;