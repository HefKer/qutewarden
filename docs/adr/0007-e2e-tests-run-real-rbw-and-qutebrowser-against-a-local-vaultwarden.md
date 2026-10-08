# End-to-end tests run real rbw and real qutebrowser against a local Vaultwarden

v1's end-to-end check was a manual checklist run against the developer's own vault. For v2, the e2e tests start a Vaultwarden server on 127.0.0.1, register a dummy account and create its Items with a small Python script that does Bitwarden's client-side crypto, then run the real `rbw` (isolated with `RBW_PROFILE` and its own XDG dirs) and the real qutebrowser (offscreen) against it, with a scripted pinentry and picker. We test with real rbw because the parts most likely to break without anyone noticing are where we meet it: the db file layout (ADR-0003), stdin handling in `rbw add` and `rbw edit`, and pinentry. Only the manual steps that need real UI or real sites remain manual.

## Considered Options

- **A throwaway account on bitwarden.com**: needs the network, credentials stored in CI, and runs into rate limits.
- **A fake `rbw` command**: fast, but it would test none of the rbw-specific behaviour above.
- **Seeding with `bw` or `rbw`**: neither can register an account. `rbw add` only creates simple Logins, and `bw` refuses plain http.
- **A committed Vaultwarden data dir**: an opaque binary fixture. Seeding fresh takes about a second.

## Consequences

The seed script copies Bitwarden's client-side crypto and has to change if Vaultwarden stops accepting its registration format. Tests only cover the qutebrowser, rbw and Vaultwarden versions pinned in `flake.lock`.
