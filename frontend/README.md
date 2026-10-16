# EcoConstruct AI — frontend

React + Vite single-page app. It is a view over the FastAPI backend and holds
no emission factor, cost or carbon arithmetic of its own.

## Run

From the project root, `./start.sh` starts both halves. To run this half alone:

```bash
npm install
npm run dev        # http://localhost:5180
```

`vite.config.js` proxies `/api`, `/health`, `/docs` and `/openapi.json` to the
backend at `http://localhost:8000`, so the browser stays on one origin. Point
at a different backend with `VITE_BACKEND_URL`, or set `VITE_API_BASE` to talk
to a deployed API without the proxy.

## What it calls

| Feature | Endpoint |
| --- | --- |
| Material picker + factors + costs | `GET /api/materials` |
| Register emissions | `POST /api/calculate` |
| Green Material Intelligence | `POST /api/compare-materials` |
| Overview, charts, score, hotspots, opportunities | `POST /api/dashboard` |
| AI Advisor report | `POST /api/recommendations` |
| Load-demo button | `GET /api/scenarios/default` |
| Connection status | `GET /health` |

All requests live in `src/api.js`. `src/App.jsx` renders the responses.

## Build

```bash
npm run build      # -> dist/
npm run preview    # serves the build on :4174
```
