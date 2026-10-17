# GIT MILESTONE RULE — MANDATORY

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
