# Submission hotfix — reproducible demo

Based on verified candidate 8e4a0c8422769076727af5c541fa9e3cad724a87.
Use branch fix/rj-m1-16h-submission-hotfix. This is a hackathon simulation, not
production banking or certified strategy superiority.

## Start with real data and backend

Requirements: Python 3.10+, Node 20+, Docker Desktop Linux engine, PostgreSQL.
The checked-in organizer CSV is authoritative (8,760 hourly rows, 16 columns).
Never regenerate it or label its naive source timestamps UTC.

PowerShell, repository root:

```powershell
Copy-Item .env.example .env
docker compose up -d db
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
$env:PYTHONPATH=".;backend"
python -c "from sqlalchemy import create_engine; from sqlalchemy.orm import Session; from app.config import settings; from app.persistence.migrations import apply_migrations; from app.persistence.repositories import DatasetRepository; from app.data.organizer import OrganizerDatasetSource; e=create_engine(settings.DATABASE_URL); print(apply_migrations(e)); s=Session(e); DatasetRepository(s).store(OrganizerDatasetSource().load()); s.commit(); s.close()"
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
Set-Location frontend
Copy-Item .env.example .env.local
npm ci
npm run dev -- --host 127.0.0.1
```

The frontend example sets VITE_USE_MOCKS=false and
VITE_API_BASE_URL=http://localhost:8000. Verify FastAPI mode, create a simulation,
then advance one hour. Check /health and /api/v1/runs/{id}/report.
Backtests support exactly 7/14/30 days. Explicitly send days when the parent
duration is not 168/336/720 steps; unsupported implicit durations return 422.
The current frontend already sends days explicitly.

## Recovered Member 1 demo

The actual Python module treasury_intelligence/four_tier_demo.py and public
demo exports were restored from frozen de48d6997ee176f72997c90cd2787a60be958828.
No missing CSV/report was fabricated.

```powershell
python -m treasury_intelligence.four_tier_demo
python scripts/export-openapi.py
```

The standalone demo is recommendation-only; its outputs are not executed
backtest returns. It may use its documented organizer-observation fixture when
a source CSV is not found. The real backend uses the checked-in organizer CSV.

## Publication admission

Public forecast_hourly_cashflows and hourly_ml_forecast accept
publication_delay_seconds (default 0). Fitted artifacts are accepted only when
their complete training/calibration source cutoff plus one hour plus that delay
is at or before decision as_of. Zero- and one-hour delay cases are regression
tested. A fitted but unavailable artifact raises ValueError; it is not silently
substituted or allowed through a short-history fallback.

New fits serialize cutoff_includes_calibration. Old pickles without that
provenance must be refitted before public admission; only trusted artifacts
should ever be deserialized. The low-level predict_path/evaluation helper keeps
its existing observed-data clock convention for frozen analytical compatibility;
it is not a publication-admission API. Historical applications must use the
public admission boundary with the configured delay and publication-eligible
input history. The backend already filters history to t+1h+delay <= decision T.

## Limitations to disclose

The RJ-M1-16H seven-day comparison is PRE-HOTFIX evidence, not re-certified here.
This hotfix changes public fitted-ML admission and API validation; default live
runtime continues to use the existing seasonal forecast. No strategy ranking
is certified. Natural bond/equity purchases are not exercised by default tier
limits; do not infer multi-asset superiority. Other scenario/duration acceptance
matrix tests may remain explicitly skipped unless configured.

Private test databases and raw verification logs stay outside Git. Do not commit
.env files, trusted model pickles, database files, node_modules or build output.
Existing approved evidence is preserved. See the final hotfix evidence report
for exact commands/results and which suites were actually rerun.

