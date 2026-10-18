# Project Rules and Guidelines

## GIT MILESTONE RULE — MANDATORY

After completing **every meaningful milestone**, the agent MUST:

1. Run the relevant tests.
2. Run `git status`.
3. Review the diff for accidental/unrelated changes.
4. Create a focused commit with a descriptive message.
5. Push the completed milestone to the current remote feature branch.

Example:

```powershell
git status
git add <relevant files>
git commit -m "feat(ledger): implement checking ledger"
git push origin <current-feature-branch>
```

Do NOT wait until the entire feature or project is finished before pushing.

The purpose is to keep the remote repository continuously updated so the other team members can access and integrate the latest stable work.

### Milestone examples

Push after milestones such as:

- transaction generator complete
- historical data generation complete
- aggregator complete
- checking ledger complete
- vault ledger complete
- simulation clock complete
- treasury adapter complete
- full simulation step complete
- API endpoints complete
- scenarios complete
- backtesting complete
- metrics/report complete
- major bug fix complete

Do NOT create commits for every tiny edit.

Do NOT push code that is knowingly broken unless the milestone is explicitly a WIP checkpoint and the commit message clearly indicates that it is a WIP.

Before pushing, ensure the relevant tests pass.

If tests fail, fix the issue before pushing whenever reasonably possible.

Never force-push or rewrite shared branch history unless explicitly instructed.

## GRAPHIFY — MANDATORY PROJECT KNOWLEDGE GRAPH

Initialize and maintain **Graphify** for the Reserve Juggler repository.

Graphify is a project-understanding/documentation layer. It must reflect the actual repository and must NOT replace Git, source code, tests, database migrations, or API contracts as the source of truth.

### Initial setup

Before substantial implementation begins:

1. Inspect whether Graphify is already configured in the repository.
2. If it is not configured, initialize it using the project's existing Graphify setup/conventions.
3. Index the relevant project structure and relationships.
4. Do not create a separate unrelated Graphify project/folder if the existing setup supports repository-level configuration.
5. Do not modify application behavior merely to support Graphify.

The initial graph should capture, where supported:

- backend modules
- services
- simulation components
- transaction generator
- aggregator
- checking ledger
- vault ledger
- simulation clock
- treasury adapter
- Member 1 engine boundary
- FastAPI routes
- database tables/migrations
- frontend/backend API relationships
- scenario engine
- backtesting
- tests
- Docker/services
- important configuration/contracts

### Regular updates

After every meaningful milestone and before pushing the milestone to the remote branch:

1. Update Graphify so the graph reflects the latest implementation.
2. Verify that newly created modules, APIs, database relationships and dependencies are represented.
3. Remove or update stale relationships when code is significantly refactored.
4. Do not invent relationships that are not supported by the actual code.
5. Keep Graphify synchronized with the current Git commit.

Recommended sequence:

```text
Implement milestone
      ↓
Run tests
      ↓
Update Graphify
      ↓
Review git diff/status
      ↓
Commit
      ↓
Push to remote
```

### Important

Graphify must never become a reason to delay a working milestone.

If Graphify update fails:

- do NOT block the actual implementation
- record the failure
- continue with tests/commit/push
- retry Graphify synchronization when practical

Do not spend excessive tokens debugging Graphify during the hackathon.

The application source code, tests, database migrations and API contracts remain authoritative.

### Graphify accuracy rule

Never use Graphify to infer that something exists.

When making implementation decisions:

`Actual repository → tests/contracts → Graphify`

not:

`Graphify → assumed implementation`

Graphify should help the team understand:

- what components exist
- how they connect
- what depends on what
- where a change will propagate
- which modules belong to which team member

Keep the graph useful, current and concise.

