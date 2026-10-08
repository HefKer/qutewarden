# Coding standards

Read during review. `scripts/check` already enforces lint (ruff, 100 columns), types (pyright) and the GLOSSARY words in `tests/test_glossary.py`; what follows is what no check can see.

## Sources

- **Security rules**: the numbered rules in `README.md` § Security. A change that touches secrets, child processes, messages, the clipboard or the FIFO is checked against every rule, and cites the rule number in a finding.
- **Vocabulary**: `GLOSSARY.md`. Domain words in names, messages, docstrings and docs use the glossary term. The `_Avoid_` words that also have an everyday meaning (password, site, login, match, insert, client, store) are a judgement call: flag them only when they stand for the glossary concept.
- **Decisions**: `docs/adr/`. A change that contradicts an ADR either amends the ADR in the same diff or is a finding.

## Rules

- **Docs move with behaviour.** When a change alters what a function, error class or subcommand does, its docstring, the README, GLOSSARY and `docs/e2e-checklist.md` lines that describe it change in the same diff. A stale description is a finding.
- **Errors carry fixed text.** Messages and `BackendError` text are built from constants and Item names, usernames and origins (Security rule 6), never from a Backend's stdout or stderr.
- **New secret paths get a leak test.** Code that newly handles a password, TOTP code or secret field is covered by a test asserting the secret marker stays out of the FIFO, argv, environment and messages (the `test_no_leak.py` / `SECRET_MARKER` pattern).
- **Test files keep one layout.** Imports and module constants at the top, fixtures from `conftest.py` and `tests/fakes/`, sentence-style test names that state the behaviour.
