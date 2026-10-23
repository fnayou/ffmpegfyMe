# ffmpegfyMe agent workflow

## Worktree lanes
- Before linked-worktree work, apply `worktree-lanes` and report its lane census.
- Use Worktrunk (`wt`) for Git worktrees and Herdr integration to group each linked checkout under this project workspace.
- Run Docker Compose from the active worktree root so build context and bind mounts use that checkout.
- Keep one writer per worktree lane. Treat undeclared shared resources as unknown.

## Workers
- Delegate through Herdr Pi only, using provider `lmstudio` and model `flint@q3_k_xl`.
- Start each Pi worker in a newly split Herdr pane in the active worktree workspace. Leave the workspace root pane available so the operator can watch and interact with the worker.
- Keep worker writes inside the assigned worktree. Verify every result from Git and files.

## Engineering workflow
- Use `ask-matt` to select Matt Pocock’s workflow. Start in-repo planning with `grill-with-docs`.
- For multi-session work, use `to-spec` then `to-tickets`; implement with `implement` and `tdd`.
- Use `triage` for incoming GitHub issues. Use `pr` for every PR body and `gh` for GitHub operations.

## Git
- Use Conventional Commits.
- Merge into protected `main` through pull requests. Rebase is the only allowed merge method.

## Agent skills

### Issue tracker
GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels
Use Matt’s five defaults. See `docs/agents/triage-labels.md`.

### Domain docs
Single-context: root `GLOSSARY.md` and `docs/adr/`. See `docs/agents/domain.md`.
