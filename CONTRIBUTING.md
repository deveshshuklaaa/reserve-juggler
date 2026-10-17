# Reserve Juggler — Team Collaboration Playbook

Welcome to the **Reserve Juggler** engineering repository for **HackForge 2026**.

To ensure velocity during the 24-hour sprint without merge friction, follow this collaboration guide.

---

## 1. Team Workstreams & Responsibilities

| Workstream | Focus Area | Primary Directories | Key Deliverables |
| :--- | :--- | :--- | :--- |
| **Workstream A** | Transaction simulation & forecasting | `simulation/`, `forecasting/` | Synthetic generator, volatility spikes, flow predictor |
| **Workstream B** | Database & treasury decision engine | `backend/`, `database/` | Quant reserve formula, state machine, REST endpoints |
| **Workstream C** | Frontend dashboard & integration | `frontend/`, `contracts/` | Liquidity dashboard, visual telemetry, scenario triggers |

---

## 2. Branching Strategy

Our repository uses a protected branch model:

```text
main
  ↑
develop
  ↑
feature branch (e.g. feat/treasury-engine)
```

- **`main`**: Production-ready demo releases. Strictly protected. Never commit directly.
- **`develop`**: Integration target for all feature PRs.
- **Feature Branches**:
  - `feat/transaction-simulator`
  - `feat/forecasting`
  - `feat/treasury-engine`
  - `feat/database`
  - `feat/frontend`
  - `feat/stress-testing`
  - `fix/<issue-name>`

### Feature Branch Lifecycle:
1. Branch off `develop`:
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b feat/treasury-engine
   ```
2. Verify changes locally against tests and contracts:
   ```bash
   pytest tests/
   ```
3. Commit with standard conventional commit syntax:
   - `feat(treasury): implement quantile reserve calculation`
   - `test(forecasting): add uncertainty boundary test`
   - `fix(backend): correct float precision on snapshot balance`
4. Open a Pull Request into `develop`.
5. After review and CI green check, merge into `develop`.

---

## 3. Engineering Philosophy & Guidelines

- **Working > complicated**: If a 10-line heuristic runs stably and is defensible, use it over an uncalibrated black-box deep model.
- **Measurable > impressive-sounding**: Track yield earned, cash utilization percentage, and reserve breach count.
- **Explainable > black-box**: Provide explicit human-readable reasons for every `HOLD`, `SWEEP`, and `WITHDRAW` decision.
- **Tested > claimed**: Write automated unit tests for every math function and critical endpoint.
- **Contract as Source of Truth**: All payloads must conform to [`contracts/openapi.yaml`](contracts/openapi.yaml).
