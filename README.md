# Reserve Juggler — The Idle Cash Problem

[![CI](https://github.com/deveshshuklaaa/reserve-juggler/actions/workflows/ci.yml/badge.svg)](https://github.com/deveshshuklaaa/reserve-juggler/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Hackathon: HackForge 2026](https://img.shields.io/badge/HackForge-2026-blueviolet.svg)](https://hackforge2026.dev)

A quantitative treasury decision engine that continuously processes a synthetic transaction stream, forecasts near-term liquidity requirements, estimates forecast uncertainty, calculates a recommended liquid reserve, and determines automated capital allocations.

---

## 1. Project Overview

- **Project**: Reserve Juggler
- **Hackathon**: HackForge 2026 (24-Hour Hackathon)
- **Problem Statement**: THE RESERVE JUGGLER — The Idle Cash Problem

### The Problem
Modern digital banks and fintech platforms struggle to strike a defensible balance between immediate liquidity requirements and yield optimization. Holding excess cash in non-interest-bearing checking accounts guarantees zero shortfall risk but forfeits significant yield (the "idle cash penalty"). Conversely, over-allocating capital to yield vaults exposes the institution to costly intraday overdraft penalties, operational fire drills, or emergency liquidation fees during unexpected transaction spikes.

### The Solution
**Reserve Juggler** is an uncertainty-aware quantitative treasury decision engine. It continuously evaluates high-frequency transaction aggregates, projects expected cash flow net drains over rolling forecast horizons, constructs probabilistic safety buffers, and deterministically allocates capital between checking and yield vaults.

---

## 2. Core Pipeline Architecture

```text
Transaction Simulator
        ↓
Transaction Ingestion
        ↓
Real-Time Aggregator
        ↓
Forecasting Engine
        ↓
Reserve / Risk Engine
        ↓
Treasury Decision Engine
        ↓
Checking Account / Yield Vault Simulation
        ↓
Decision Explanation + Audit Log
        ↓
Frontend Dashboard
```

```text
Transactions → Aggregation → Forecast → Uncertainty → Required Reserve → Treasury Decision → Simulated Execution → Financial Metrics
```

---

## 3. Decision Matrix

At each evaluation cycle, the decision engine computes the recommended liquid reserve $R_{req}$ and deployable cash $\Delta = C - R_{req}$:

- **`HOLD`**: Checking balance is inside the optimal risk-neutral equilibrium corridor ($|C - R_{req}| \le \text{band}$). No capital movement is required.
- **`SWEEP`**: Checking balance significantly exceeds the reserve requirement ($C > R_{req} + \text{threshold}$). Excess deployable liquidity is swept to the yield vault.
- **`WITHDRAW`**: Checking balance falls below safety threshold ($C < R_{req}$) and the vault holds sufficient liquidity to replenish checking.
- **`LIQUIDITY_WARNING`**: Total consolidated liquid capital ($C + V$) cannot cover the required reserve corridor under extreme stress. Immediate operator notification and emergency protocol triggered.

Detailed formulas and parameter rules are documented in [`docs/decision-engine.md`](docs/decision-engine.md).

---

## 4. Important Limitation

> **Important Limitation**: This repository is a hackathon prototype operating exclusively on synthetic transaction data and simulated banking balances. It does not connect to real customer accounts, real money movement rails, or production banking infrastructure.

---

## 5. Repository Structure

```text
reserve-juggler/
│
├── frontend/             # React 19 + Vite modern dark-mode dashboard
│
├── backend/              # FastAPI core REST API & Treasury decision service
│   └── app/
│       ├── routers/      # Health, Treasury, Transactions, Simulation
│       └── treasury/     # Quant reserve formulas & decision rules
│
├── forecasting/          # Time-series flow forecasting & uncertainty estimation
│
├── simulation/           # Synthetic transaction generators & stress scenarios
│
├── database/             # PostgreSQL schemas & seed data
│   ├── migrations/       # 001_initial_schema.sql
│   └── seeds/            # 001_seed_data.sql
│
├── contracts/            # OpenAPI 3.0.3 specification (Single source of truth)
│
├── tests/                # Test suites
│   ├── backend/          # API & decision engine tests
│   ├── forecasting/      # Forecaster unit tests
│   ├── simulation/       # Synthetic stream generator tests
│   └── integration/      # End-to-end treasury pipeline tests
│
├── docs/                 # Architectural & mathematical documentation
│
├── scripts/              # Automation & health diagnostic scripts
│
├── .github/workflows/    # Continuous Integration pipeline
│
├── docker-compose.yml    # Multi-container local orchestration
├── .env.example          # Environment variable template
├── .gitignore            # Git exclusion rules
├── README.md             # Project documentation
└── CONTRIBUTING.md       # Team workflow & branch strategy
```

---

## 6. Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.10+ (for local development)
- Node.js 20+ (for frontend development)
- PowerShell (Windows) or Bash

### 1. Configure Environment
```powershell
Copy-Item .env.example .env
```

### 2. Start Full Stack via Docker
```powershell
docker compose up -d --build
```

### 3. Verify Health Check
```powershell
.\scripts\health-check.ps1
```

- **Frontend Dashboard**: http://localhost:3000
- **Backend API Docs**: http://localhost:8000/docs
- **OpenAPI Contract**: [`contracts/openapi.yaml`](contracts/openapi.yaml)

---

## 7. Testing

Run all test suites locally:

```powershell
# Backend & Decision Engine tests
python -m pytest tests/backend tests/forecasting tests/simulation tests/integration -v
```

---

## 8. Team Collaboration & Workstreams

- **Workstream A**: Transaction Simulation + Forecasting Engine (`simulation/`, `forecasting/`)
- **Workstream B**: Database + Treasury/Risk Engine (`backend/`, `database/`)
- **Workstream C**: Frontend Dashboard + Contract Integration (`frontend/`)

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for branch policies and developer guidelines.
