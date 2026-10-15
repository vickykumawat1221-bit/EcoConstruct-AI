import { useState } from "react";
import {
  Leaf,
  Plus,
  Trash2,
  Building2,
  Factory,
  TrendingDown,
  LayoutDashboard,
  Recycle,
  Activity,
} from "lucide-react";

import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

import "./App.css";

const FACTORS = {
  Cement: 0.85,
  Steel: 1.9,
  Bricks: 0.00022,
};

const INITIAL_MATERIALS = [
  { id: 1, name: "Cement", quantity: 120, unit: "tonnes" },
  { id: 2, name: "Steel", quantity: 30, unit: "tonnes" },
  { id: 3, name: "Bricks", quantity: 20000, unit: "pieces" },
];

function formatNumber(value) {
  return Number(value).toLocaleString("en-IN", {
    maximumFractionDigits: 2,
  });
}

export default function App() {
  const [materials, setMaterials] = useState(INITIAL_MATERIALS);
  const [materialName, setMaterialName] = useState("Cement");
  const [quantity, setQuantity] = useState("");
  const [projectName, setProjectName] = useState(
    "Green Building Project"
  );

  const totalEmissions = materials.reduce(
    (total, material) =>
      total + material.quantity * FACTORS[material.name],
    0
  );

  const chartData = materials.map((material) => ({
    name: material.name,
    emissions: Number(
      (material.quantity * FACTORS[material.name]).toFixed(2)
    ),
  }));

  const highestEmitter =
    chartData.length > 0
      ? chartData.reduce((a, b) =>
          a.emissions > b.emissions ? a : b
        )
      : null;

  function addMaterial(event) {
    event.preventDefault();

    const amount = Number(quantity);

    if (!Number.isFinite(amount) || amount <= 0) {
      alert("Please enter a quantity greater than zero.");
      return;
    }

    setMaterials((previous) => [
      ...previous,
      {
        id: Date.now(),
        name: materialName,
        quantity: amount,
        unit: materialName === "Bricks" ? "pieces" : "tonnes",
      },
    ]);

    setQuantity("");
  }

  function deleteMaterial(id) {
    setMaterials((previous) =>
      previous.filter((material) => material.id !== id)
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">
            <Leaf size={25} />
          </div>
          <div>
            <h2>EcoConstruct</h2>
            <p>AI Carbon Intelligence</p>
          </div>
        </div>

        <p className="side-label">WORKSPACE</p>

        <div className="nav-item active">
          <LayoutDashboard size={19} />
          <span>Carbon Dashboard</span>
        </div>

        <div className="nav-item">
          <Factory size={19} />
          <span>Materials</span>
        </div>

        <div className="nav-item">
          <TrendingDown size={19} />
          <span>Reduction Planner</span>
        </div>

        <div className="sidebar-note">
          <Recycle size={28} />
          <h3>Build greener.</h3>
          <p>
            Make smarter construction decisions with carbon
            intelligence.
          </p>
        </div>

        <div className="sidebar-footer">
          <Leaf size={18} />
          <span>EcoConstruct AI · Prototype</span>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div>
            <p className="eyebrow">SUSTAINABLE CONSTRUCTION</p>
            <h1>Carbon Dashboard</h1>
            <p className="subtitle">
              Monitor construction emissions and discover greener choices.
            </p>
          </div>

          <span className="status-pill">
            <span className="status-dot" />
            Demo project
          </span>
        </header>

        <section className="welcome-card">
          <div>
            <p className="welcome-label">
              <Leaf size={15} /> PROJECT OVERVIEW
            </p>

            <h2>Build with impact in mind.</h2>

            <p>
              Track construction material emissions and work toward
              more sustainable building practices.
            </p>

            <input
              className="project-input"
              aria-label="Project name"
              value={projectName}
              onChange={(event) => setProjectName(event.target.value)}
              placeholder="Enter project name"
            />
          </div>

          <div className="welcome-icon">
            <Building2 size={58} />
          </div>
        </section>

        <section className="stats-grid">
          <article className="stat-card">
            <div className="stat-top">
              <span>Total estimated emissions</span>
              <Factory size={21} />
            </div>
            <h2>{formatNumber(totalEmissions)}</h2>
            <p>kg CO₂e · illustrative factors</p>
          </article>

          <article className="stat-card">
            <div className="stat-top">
              <span>Material entries</span>
              <Building2 size={21} />
            </div>
            <h2>{materials.length}</h2>
            <p>Records in your inventory</p>
          </article>

          <article className="stat-card">
            <div className="stat-top">
              <span>Highest-emission material</span>
              <Activity size={21} />
            </div>
            <h2 className="highest-name">
              {highestEmitter ? highestEmitter.name : "—"}
            </h2>
            <p>
              {highestEmitter
                ? `${formatNumber(highestEmitter.emissions)} kg CO₂e`
                : "Add materials to begin"}
            </p>
          </article>
        </section>

        <section className="content-grid">
          <article className="panel">
            <div className="panel-heading">
              <div>
                <h3>Emissions by material</h3>
                <p>Estimated emissions for each material entry</p>
              </div>
              <span className="mini-badge">kg CO₂e</span>
            </div>

            <div className="chart-container">
              {chartData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={chartData}
                    margin={{
                      top: 10,
                      right: 10,
                      left: 0,
                      bottom: 5,
                    }}
                  >
                    <CartesianGrid
                      strokeDasharray="3 3"
                      vertical={false}
                    />
                    <XAxis dataKey="name" />
                    <YAxis />
                    <Tooltip
                      formatter={(value) => [
                        `${formatNumber(value)} kg CO₂e`,
                        "Emissions",
                      ]}
                    />
                    <Bar
                      dataKey="emissions"
                      fill="#21845b"
                      radius={[6, 6, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <p className="empty-chart">
                  Add materials to display the chart.
                </p>
              )}
            </div>
          </article>

          <article className="panel add-panel">
            <div className="panel-heading">
              <div>
                <h3>Add material</h3>
                <p>Update your project inventory</p>
              </div>
              <Plus size={23} />
            </div>

            <form onSubmit={addMaterial}>
              <label htmlFor="material">Material type</label>

              <select
                id="material"
                value={materialName}
                onChange={(event) =>
                  setMaterialName(event.target.value)
                }
              >
                <option value="Cement">Cement</option>
                <option value="Steel">Steel</option>
                <option value="Bricks">Bricks</option>
              </select>

              <label htmlFor="quantity">
                Quantity (
                {materialName === "Bricks" ? "pieces" : "tonnes"})
              </label>

              <input
                id="quantity"
                type="number"
                min="0.01"
                step="any"
                placeholder="Enter quantity"
                value={quantity}
                onChange={(event) => setQuantity(event.target.value)}
                required
              />

              <button className="primary-button" type="submit">
                <Plus size={18} />
                Add to inventory
              </button>
            </form>

            <p className="form-note">
              Your chart and emission totals update automatically.
            </p>
          </article>
        </section>

        <section className="panel materials-panel">
          <div className="panel-heading">
            <div>
              <h3>Material inventory</h3>
              <p>Materials currently included in your estimate</p>
            </div>

            <span className="count-badge">
              {materials.length} entries
            </span>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Material</th>
                  <th>Quantity</th>
                  <th>Emission factor</th>
                  <th>Estimated emissions</th>
                  <th>Action</th>
                </tr>
              </thead>

              <tbody>
                {materials.map((material) => (
                  <tr key={material.id}>
                    <td>
                      <span className="material-dot" />
                      {material.name}
                    </td>

                    <td>
                      {formatNumber(material.quantity)} {material.unit}
                    </td>

                    <td>{FACTORS[material.name]}</td>

                    <td className="emissions-cell">
                      {formatNumber(
                        material.quantity * FACTORS[material.name]
                      )}{" "}
                      kg CO₂e
                    </td>

                    <td>
                      <button
                        className="delete-button"
                        onClick={() => deleteMaterial(material.id)}
                        aria-label={`Delete ${material.name}`}
                        title="Delete material"
                        type="button"
                      >
                        <Trash2 size={17} />
                      </button>
                    </td>
                  </tr>
                ))}

                {materials.length === 0 && (
                  <tr>
                    <td colSpan="5" className="empty-state">
                      No materials added yet. Use the form above to begin.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="insights-grid">
          <article className="insight-card">
            <div className="insight-icon">
              <Leaf size={24} />
            </div>

            <div>
              <p className="insight-label">SUSTAINABILITY INSIGHT</p>

              <h3>
                {highestEmitter
                  ? `Review your ${highestEmitter.name.toLowerCase()} usage`
                  : "Start tracking your materials"}
              </h3>

              <p>
                {highestEmitter
                  ? `${highestEmitter.name} currently has the highest estimated emissions among the displayed material categories. Investigate verified lower-carbon alternatives with your project team.`
                  : "Add materials to begin exploring their estimated emissions."}
              </p>
            </div>
          </article>

          <article className="insight-card reduction-card">
            <div className="insight-icon">
              <TrendingDown size={24} />
            </div>

            <div>
              <p className="insight-label">COMING SOON</p>
              <h3>AI Reduction Planner</h3>
              <p>
                Future versions will suggest potential emission
                reduction strategies using verified data.
              </p>
            </div>
          </article>
        </section>

        <footer className="disclaimer">
          <strong>Important:</strong> Emission factors in this prototype
          are illustrative placeholders, not verified real-world values.
          Replace them with documented, source-verified factors before
          using the results for real construction decisions. This demo
          covers tracked materials only; transport, fuel, electricity,
          waste, and other lifecycle stages are not included.
        </footer>

        <div className="page-footer">
          <span>EcoConstruct AI</span>
          <span>Building a more sustainable future.</span>
        </div>
      </main>
    </div>
  );
}
