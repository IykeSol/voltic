---
title: Voltic Prepaid Meter Analyzer
emoji: ⚡
colorFrom: blue
colorTo: indigo
sdk: gradio
app_file: app.py
pinned: false
---

# Voltic — Prepaid Meter Usage Pattern Analyzer

An AI-powered analytics dashboard for prepaid electricity meters. It learns a
household's consumption pattern, forecasts daily and weekly usage, estimates
when the prepaid balance will run out, detects abnormal usage (spikes, suspected
tampering, appliance faults) and turns it all into plain-English insights.

Built to feel like a real utility/fintech SaaS product — a calm, handcrafted
dashboard rather than a generic template.

- **Backend:** FastAPI + SQLite
- **ML:** scikit-learn (Random Forest Regressor, Isolation Forest)
- **AI insights:** Google Gemini (`gemini-2.0-flash-lite`) with an offline fallback
- **Frontend:** Hand-written HTML / CSS / vanilla JS + Chart.js
- **Deploy:** Docker, ready for Hugging Face Spaces (port 7860)

---

## Screenshots

> Placeholder — drop your own captures in `docs/` and update these links.

| Landing | Dashboard (dark) | Dashboard (light) |
| --- | --- | --- |
| `docs/landing.png` | `docs/dashboard-dark.png` | `docs/dashboard-light.png` |

---

## Features

- **Consumption pattern analysis** — daily/weekly usage, peak hours, weekday vs
  weekend behaviour, recharge cadence.
- **Usage forecasting** — tomorrow, the next 7 days and an estimated
  recharge-exhaustion date, driven by the trained Random Forest.
- **Anomaly detection** — Isolation Forest flags spikes, abnormal night usage
  (possible tampering) and appliance-fault patterns.
- **AI insights** — Gemini explains the numbers and gives savings/budget advice.
  Works fully offline via a deterministic fallback if no key/quota is available.
- **Appliance simulation** — estimates how much each appliance contributes.
- **Budget engine** — recommends an optimal recharge amount.
- **Smart alerts**, **activity heatmap**, **recharge timeline**.
- **Auth** — signup / login with JWT.
- **Exports** — CSV report and PDF summary.
- **Dark / light mode** with persistence.

---

## Project structure

```
ai-prepaid/
├── app/
│   ├── main.py            # FastAPI app, routes + static frontend
│   ├── config.py          # settings / env
│   ├── routes/            # auth, usage, ai, export
│   ├── services/          # analytics, forecast, anomaly, appliance, budget, report, insight
│   ├── ai/                # Gemini client + prompt templates
│   ├── models/            # Pydantic schemas
│   ├── database/          # SQLite layer + seeding
│   └── utils/             # security (JWT, password hashing)
├── frontend/              # index.html, login.html, dashboard.html, css/, js/, assets/
├── scripts/
│   ├── generate_dataset.py
│   ├── train_model.py
│   └── test_model.py
├── dataset/               # generated CSV (50k+ rows)
├── trained_models/        # saved .pkl models + metrics.json
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .gitignore
└── README.md
```

---

## Setup (local)

```bash
# 1. Create and activate a virtual environment
python -m venv venv

# macOS / Linux
source venv/bin/activate
# Windows
venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Generate the dataset (≈50,400 rows)
python scripts/generate_dataset.py

# 4. Train the models (Random Forest + Isolation Forest)
python scripts/train_model.py

# 5. (optional) Evaluate the saved models
python scripts/test_model.py

# 6. Run the backend (use `python -m` so it works even if uvicorn isn't on PATH)
python -m uvicorn app.main:app --reload
```

Then open **http://localhost:8000** (or `--port 7860`).

**Demo account:** `demo@meter.ng` / `demo1234` (pre-filled) — or click *Continue
with demo meter*. New signups start **empty**: you enter your household,
appliances and current prepaid balance, and the model predicts your usage,
7-day forecast, and how long the balance will last. Use **Recharge** to top up
(it shows how many units the amount buys) and **Edit meter** to adjust inputs.

---

## Gemini setup

1. Get a key from <https://aistudio.google.com/app/apikey>.
2. Copy `.env.example` to `.env` and set it:

   ```env
   GEMINI_API_KEY=your_key_here
   GEMINI_MODEL=gemini-2.0-flash-lite
   JWT_SECRET=change-this-to-a-long-random-string
   ```

If the key is missing, invalid, or out of quota, the app automatically falls
back to a built-in deterministic analysis — the dashboard never breaks.

---

## API reference

All `/usage/*`, `/ai/*` and `/export/*` endpoints require a
`Authorization: Bearer <token>` header.

| Method | Endpoint            | Description |
| ------ | ------------------- | ----------- |
| POST   | `/auth/signup`      | Create an account, returns a JWT |
| POST   | `/auth/login`       | Log in, returns a JWT |
| GET    | `/usage/summary`    | KPI summary (avg daily, balance, exhaustion, peak hour) |
| GET    | `/usage/history`    | Daily usage + recharge history (`?days=30`) |
| GET    | `/usage/forecast`   | Tomorrow, next 7 days, exhaustion date, spike probability |
| GET    | `/usage/anomalies`  | Recently detected anomalies |
| GET    | `/usage/peak-hours` | Average usage per hour of day |
| GET    | `/usage/heatmap`    | Weekday × hour activity matrix |
| GET    | `/usage/appliances` | Estimated appliance breakdown |
| GET    | `/usage/budget`     | Recommended recharge amount |
| POST   | `/ai/analyze`       | AI consumption analysis (`{ "focus": "..." }`) |
| GET    | `/export/csv`       | Download usage CSV |
| GET    | `/export/pdf`       | Download PDF summary |
| GET    | `/health`           | Health check |

Example:

```bash
TOKEN=$(curl -s -X POST localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@meter.ng","password":"demo1234"}' | jq -r .access_token)

curl -s localhost:8000/usage/summary -H "Authorization: Bearer $TOKEN" | jq
```

---

## How the model works

The dataset generator simulates Nigerian households on prepaid meters at hourly
resolution, with grid outages, weather effects, family-size differences,
appliance usage, recharge habits and income bands. It deliberately injects
measurement noise, missing readings and rare anomalies so the data is realistic
rather than perfectly clean.

- **Forecasting** — `RandomForestRegressor` predicts hourly kWh from operational
  context (time, weather, household profile, grid state, appliance run-times).
  Trained 80/20, it lands in a realistic **0.70–0.80 R²** band (not an
  overfit 0.95+). Metrics reported: MAE, RMSE, R².
- **Anomaly detection** — `IsolationForest` scores each reading against what is
  normal *for that hour of day*, so a 3 a.m. spike is caught even when its raw
  kWh looks ordinary.

Latest run (`trained_models/metrics.json`): **R² ≈ 0.74, MAE ≈ 0.10 kWh**.

---

## Docker

```bash
# Build and run (serves on http://localhost:7860)
docker compose up --build
```

The image installs dependencies, then generates the dataset and trains the
models at build time, so the container is fully self-contained.

---

## Hugging Face Spaces deployment

1. Create a new Space → **Docker** SDK (blank template).
2. Push this repository to the Space (the `Dockerfile` exposes port **7860**,
   which Spaces expects).
3. In **Settings → Variables and secrets**, add:
   - `GEMINI_API_KEY` (secret) — optional; the app runs without it.
   - `JWT_SECRET` (secret) — a long random string.
4. The Space builds the image (dataset + model are generated during build) and
   starts serving automatically.

---

## Notes

- This tool produces model-based estimates for guidance only.
- SQLite and generated artifacts are recreated automatically if deleted.
