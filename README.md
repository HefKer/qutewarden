# qutewarden

Bitwarden for [qutebrowser](https://qutebrowser.org/). It fills logins and TOTP codes, generates passwords, and lets you browse your vault, doing the job of the Bitwarden browser extension, which doesn't exist for qutebrowser.

> **Status:** early development. The v1 design is in [`docs/spec-v1.md`](docs/spec-v1.md), and the work is tracked in [GitHub issues](https://github.com/HefKer/qutewarden/issues).

## Why not the bundled `qute-bitwarden`?

qutebrowser includes a `qute-bitwarden` userscript, but:

- it types credentials as fake keypresses, so they show up in plain text in `qute://log`
- it picks Items by **name** instead of URI, so nothing stops it filling on a look-alike domain
- it can only fill

qutewarden instead:

- passes secrets to the page through a private named pipe, so they never go through qutebrowser's command log
- matches Items on their URIs with Bitwarden's own match modes
- checks the page's origin again just before filling

See [ADR-0001](docs/adr/0001-standalone-replacement-for-upstream-userscript.md) and [ADR-0002](docs/adr/0002-secrets-reach-the-page-through-a-private-named-pipe.md).

## Planned features (v1)

| Command | What it does |
|---|---|
| `fill` | Fill username and password (or a TOTP code on OTP-only pages) from the Items that match the current page |
| `totp` | Fill the TOTP code |
| `generate` | Generate a password, save it to the vault, then fill it into a signup or change-password form |
| `vault` | Pick from the whole vault; filling an Item that doesn't match the page needs a confirmation |
| `unlock` / `lock` / `sync` / `status` | Vault controls |

## Requirements

- qutebrowser ≥ 3.0 (QtWebEngine)
- Python ≥ 3.11
- [`rbw`](https://github.com/doy/rbw) ≥ 1.14, logged in (`rbw login`)
- A dmenu-compatible picker, such as `fuzzel` or `rofi`

Support for the official `bw` CLI is planned for v2.

## Usage (planned)

```python
# config.py
config.bind(',p', 'spawn --userscript qutewarden fill')
config.bind(',t', 'spawn --userscript qutewarden totp')
config.bind(',g', 'spawn --userscript qutewarden generate')
config.bind(',v', 'spawn --userscript qutewarden vault')
```

Settings live in `$XDG_CONFIG_HOME/qutewarden/config.toml`; see the Config section of the spec.

## License

[GPL-3.0-or-later](LICENSE)
