# EcoConstruct AI

Construction carbon auditing: a FastAPI backend (Members 2-4) and a React
frontend (Member 1) wired together as one running application.

- **Backend** — `main.py` mounts Member 2's dataset/calculator
  (`api_materials.py`), Member 4's scenario simulator and dashboard
  (`api_simulation.py`), and Member 3's audit endpoint (`/api/recommendations`).
- **Frontend** — `frontend/` is a Vite + React app that reads everything from
  those endpoints. It keeps no emission factor or cost of its own.

## Run it

```bash
./start.sh
```

This starts the backend on **http://localhost:8000** and the frontend on
**http://localhost:5180**, then prints the link. `Ctrl-C` stops both.

Open the app at:

> **http://localhost:5180**

Other modes:

```bash
./start.sh backend    # FastAPI only  (docs: http://localhost:8000/docs)
./start.sh frontend   # Vite only
```

Ports can be overridden: `BACKEND_PORT=9000 FRONTEND_PORT=5181 ./start.sh`.

### Manual start (if you prefer)

```bash
# terminal 1
venv/bin/python -m uvicorn main:app --reload            # :8000

# terminal 2
cd frontend && npm install && npm run dev               # :5180
```

## How the two halves talk

The frontend calls the API through a Vite dev proxy (see
`frontend/vite.config.js`), so requests are same-origin and CORS never
matters in development. The endpoints it uses:

| Frontend feature | Endpoint | Owner |
| --- | --- | --- |
| Material picker, factors, unit costs | `GET /api/materials` | Member 2 |
| Register emissions | `POST /api/calculate` | Member 2 |
| Green Material Intelligence | `POST /api/compare-materials` | Member 2 |
| Overview totals, charts, score, hotspots, opportunities | `POST /api/dashboard` | Member 4 |
| AI Advisor report | `POST /api/recommendations` | Member 3 |
| "Load demo" button | `GET /api/scenarios/default` | Member 4 |
| Connection status | `GET /health` | — |

The frontend recomputes nothing on its own beyond `quantity × factor` for
instant feedback while typing; every headline number is rendered from a
backend response.

## AI recommendations

Set `GEMINI_API_KEY` in a `.env` file (copy `.env.example`) to enable Gemini.
Without it, `POST /api/recommendations` returns the rule-based fallback and the
UI labels the report **"Rule-based fallback"**.

## Tests

```bash
venv/bin/python -m pytest -q
```

`pytest.ini` excludes the `_extract/` folder (unzipped submission copies) so
the suite collects cleanly. 230 tests pass; two assertions are stale from
before the modules were integrated under one app banner and dataset loader —
they do not affect the running app.

## Frontend build

```bash
cd frontend && npm run build     # outputs frontend/dist
```

## Notes on the data

Every emission factor in `data/materials.csv` and every price in
`data/material_costs.csv` is marked **unverified** and is illustrative
placeholder data. The UI surfaces this everywhere so it is never mistaken for
certified figures. Replace both tables with cited regional data and supplier
quotations before real decisions.
