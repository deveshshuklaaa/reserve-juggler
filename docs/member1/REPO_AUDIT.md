# Repository Audit & Workstream Specification — Member 1

## 1. Executive Summary & Verification

- **Repository**: `https://github.com/deveshshuklaaa/reserve-juggler.git`
- **Assigned Feature Branch**: `feat/treasury-intelligence`
- **Base Commit**: `2e396f9` (`chore: initialize Reserve Juggler project`)
- **Remote Branches Audited**:
  - `origin/main`
  - `origin/develop`
  - `origin/feat/simulation-backend`
  - `origin/codex/backend-contracts`
  - `origin/frontend`
- **Current Working Tree Status**: Clean.

---

## 2. Repository Architecture & Component Inspection

The codebase contains four principal functional blocks:

| Directory | Current Contents | Responsibilities | Current Owner |
| :--- | :--- | :--- | :--- |
| `forecasting/` | `forecaster.py` (`CashFlowForecaster`) | Rolling window time-series heuristic flow & uncertainty forecasting | **Member 1** |
| `treasury_intelligence/` | *(To be created)* | Standalone quantitative treasury decision engine, reserve optimization, risk buffers | **Member 1** |
| `backend/` | FastAPI REST services, SQLAlchemy models, schemas, `backend/app/treasury/engine.py` (baseline adapter) | API gateway, persistence, database migrations, WebSocket streaming | Member 2 |
| `simulation/` | `generator.py` (`TransactionGenerator`) | Synthetic transaction event generator across scenarios | Member 2 |
| `database/` | PostgreSQL schemas & seed data | Data persistence & transactional state | Member 2 |
| `frontend/` | React 19 + Vite dashboard | User interface, telemetry display, simulation controls | Member 3 |
| `contracts/` | `openapi.yaml` | OpenAPI 3.0.3 single source of truth | Shared |
| `tests/` | Unit & integration tests for backend, forecasting, simulation, pipeline | Test harnesses | Respective owners |
| `docs/` | `decision-engine.md`, `member1/` | Mathematical formulas, decision rules, audit trails | Respective owners |

---

## 3. Mathematical & Quantitative Engine Placement

### Chosen Location: `treasury_intelligence/` & `forecasting/`
The standalone Python Quantitative Treasury Intelligence Engine is placed at root in `treasury_intelligence/`:
- **Isolation from I/O**: The engine contains zero database, ORM, or HTTP framework dependencies. It can be executed, benchmarked, and tested in any Python environment.
- **Precision & Safety Standards**:
  - Currency values handled in **integer cents** and **`Decimal`** for financial calculations to prevent floating point drift.
  - Risk parameters and spreads represented in **basis points (bps)**.
  - All timestamps strictly formatted in **ISO 8601 UTC**.
  - All stochastic models use explicit, reproducible random seeds.
- **Compatibility & Interface Preservation**:
  - `forecasting/forecaster.py` interfaces will be preserved/enhanced without breaking existing integration tests (`tests/forecasting/test_forecaster.py` and `tests/integration/test_treasury_pipeline.py`).
  - `backend/app/treasury/engine.py` functions as the Member 2 backend adapter. Member 1's standalone engine provides the robust mathematical core.

---

## 4. File Ownership & Boundary Matrix

To prevent merge conflicts and maintain clear responsibilities across team members:

```text
reserve-juggler/
├── treasury_intelligence/      <-- EXCLUSIVELY OWNED BY MEMBER 1
│   ├── __init__.py
│   ├── reserve.py             # Reserve formulas, safety corridors, uncertainty math
│   ├── policy.py              # Threshold rules, sweep/withdraw allocation logic
│   ├── metrics.py             # APY, idle cash ratio, reserve breach tracking
│   └── types.py               # Immutable types, Decimal converters, schema contracts
├── forecasting/                <-- CO-OWNED / ENHANCED BY MEMBER 1
│   ├── __init__.py
│   └── forecaster.py          # Quantile flow forecasting & uncertainty calibration
├── tests/
│   ├── treasury_intelligence/ <-- EXCLUSIVELY OWNED BY MEMBER 1
│   ├── forecasting/           <-- MAINTAINED BY MEMBER 1
│   ├── backend/               <-- OWNED BY MEMBER 2 (Do not touch)
│   ├── simulation/            <-- OWNED BY MEMBER 2 (Do not touch)
│   └── integration/           <-- SHARED (Preserve existing tests)
├── docs/member1/              <-- EXCLUSIVELY OWNED BY MEMBER 1
│   ├── REPO_AUDIT.md
│   └── PROGRESS.md
├── backend/                   <-- OWNED BY MEMBER 2 (Do not edit without agreement)
├── frontend/                  <-- OWNED BY MEMBER 3 (Do not edit without agreement)
└── contracts/openapi.yaml     <-- SHARED CONTRACT (Do not edit without agreement)
```

---

## 5. Verification Commands & Test Harness

### Full Suite Run Command:
```powershell
$env:PYTHONPATH=".;backend"
uv run --with pytest --with fastapi --with pydantic --with httpx --with sqlalchemy --with pydantic-settings pytest tests/ -v
```

### Member 1 Targeted Suite:
```powershell
$env:PYTHONPATH="."
uv run --with pytest pytest tests/forecasting tests/treasury_intelligence -v
```

### Baseline Test Results at Audit:
- `tests/backend/test_decision_engine.py`: 5 passed
- `tests/backend/test_health.py`: 3 passed
- `tests/forecasting/test_forecaster.py`: 2 passed
- `tests/integration/test_treasury_pipeline.py`: 1 passed
- `tests/simulation/test_simulator.py`: 3 passed
- **Total: 14 passed in 1.41s**
