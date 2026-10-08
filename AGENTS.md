# AGENTS.md

## Checks

`nix develop -c scripts/check` runs ruff, pyright and the full suite; extra args go to pytest (`-m "not browser"`, a test path). A clean `main` passes, so any finding is yours. `nix develop -c qutewarden-dev <subcommand>` runs `src/` against the real rbw.

## Agent skills

### Issue tracker

Issues are tracked in this repo's GitHub Issues, managed with the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Uses the five default triage labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
