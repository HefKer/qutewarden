# Changelog

All notable changes to qutewarden are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

"v1" and "v2" are the names of the planning documents ([`docs/spec-v1.md`](docs/spec-v1.md), [`docs/spec-v2.md`](docs/spec-v2.md)): v1 is released as `0.1.0`, v2 will be `1.0.0`.

## [Unreleased]

### Added

- A home-manager module, `homeManagerModules.default` (`programs.qutewarden`): installs qutewarden, links it as a qutebrowser userscript, writes `settings` to the config file and adds `keyBindings` to `programs.qutebrowser`.
- `card`: pick a Card item and fill the page's payment form (cardholder name, number, expiry and security code), found by `autocomplete` `cc-*` tokens or, without them, by name, id, label and placeholder. It never Auto-fills and never submits. Picker lines show the brand and last 4 digits of the number.

## [0.1.0] - 2026-10-08

The first release: v1 as described in [`docs/spec-v1.md`](docs/spec-v1.md).

### Added

- `fill`: fill the username and password (or a TOTP code on OTP-only pages) of an Item that matches the current page, with a picker when several match and optional Auto-fill when exactly one does.
- `totp`: fill the TOTP code of a matching Item, or copy it with `totp.clipboard` on.
- `generate`: generate a password, save it to the vault, then fill it into a signup or change-password form.
- `vault`: pick from the whole vault, with a confirmed Mismatch fill for an Item that doesn't match the page, and optional copying of single fields with `vault.allow_copy` on.
- `unlock`, `lock`, `sync` and `status`.
- URI match with Bitwarden's match modes (`base_domain`, `host`, `starts_with`, `exact`, `regular_expression`, `never`).
- Secrets reach the page through a private named pipe, never through a qutebrowser command, and the page's origin is checked again inside the page just before filling.
- The rbw Backend (rbw ≥ 1.15), the only Backend. There is no `backend` setting; a config file that sets one fails with an error saying the setting was removed.
- A TOML config file, with every setting also available as a flag.
- A Nix flake (Linux only) and a Python package that install a single `qutewarden` command.
- `CHANGELOG.md`, `SECURITY.md` and GitHub issue templates.

### Fixed

- `generate` no longer fills the picked username into a focused input that doesn't look like a username field, such as a search box.
- The fuzzel confirmation for a Mismatch fill is always wide enough to read, whatever `fuzzel.ini` sets.
- The GLOSSARY and the README's Security rule 5 describe the Mismatch fill confirmation as it now looks: the Item's URIs host first next to the page's address, never shortened.

[Unreleased]: https://github.com/HefKer/qutewarden/compare/0.1.0...HEAD
[0.1.0]: https://github.com/HefKer/qutewarden/releases/tag/0.1.0
