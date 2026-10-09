# Changelog

All notable changes to qutewarden are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

"v1" and "v2" are the names of the planning documents ([`docs/spec-v1.md`](docs/spec-v1.md), [`docs/spec-v2.md`](docs/spec-v2.md)): v1 is released as `0.1.0`, v2 will be `1.0.0`.

## [Unreleased]

## [0.1.0]

The first release: v1 as described in [`docs/spec-v1.md`](docs/spec-v1.md).

### Added

- `fill`: fill the username and password (or a TOTP code on OTP-only pages) of an Item that matches the current page, with a picker when several match and optional Auto-fill when exactly one does.
- `totp`: fill the TOTP code of a matching Item, or copy it with `totp.clipboard` on.
- `generate`: generate a password, save it to the vault, then fill it into a signup or change-password form.
- `vault`: pick from the whole vault, with a confirmed Mismatch fill for an Item that doesn't match the page, and optional copying of single fields with `vault.allow_copy` on.
- `unlock`, `lock`, `sync` and `status`.
- URI match with Bitwarden's match modes (`base_domain`, `host`, `starts_with`, `exact`, `regular_expression`, `never`).
- Secrets reach the page through a private named pipe, never through a qutebrowser command, and the page's origin is checked again inside the page just before filling.
- The `rbw` backend (rbw ≥ 1.15).
- A TOML config file, with every setting also available as a flag.
- A Nix flake and a Python package that install a single `qutewarden` command.
- `CHANGELOG.md`, `SECURITY.md` and GitHub issue templates.

### Changed

- The flake builds for Linux systems only; the darwin systems are gone. qutewarden relies on `$XDG_RUNTIME_DIR`, Wayland and X11, and has never run on macOS.

### Removed

- The `backend` setting and its `--backend` flag. A config file that still sets `backend` fails with an error saying the setting was removed.

### Fixed

- `generate` no longer fills the picked username into a focused input that doesn't look like a username field, such as a search box.
- The fuzzel confirmation for a Mismatch fill is always wide enough to read, whatever `fuzzel.ini` sets.

[Unreleased]: https://github.com/HefKer/qutewarden/compare/0.1.0...HEAD
[0.1.0]: https://github.com/HefKer/qutewarden/releases/tag/0.1.0
