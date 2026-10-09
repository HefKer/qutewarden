# qutewarden

Bitwarden for [qutebrowser](https://qutebrowser.org/), doing the job of the Bitwarden browser extension, which doesn't exist for qutebrowser. It fills logins and TOTP codes, generates passwords, and lets you browse your vault.

## Why not the bundled `qute-bitwarden`?

qutebrowser's own `qute-bitwarden` userscript types usernames and passwords as fake keypresses, so they show up in plain text in `qute://log`; it picks Items by **name** instead of URI, so nothing stops it filling on a look-alike domain; and it can only fill.

qutewarden instead:

- passes secrets to the page through a private named pipe, never through qutebrowser's command log
- matches Items on their URIs with Bitwarden's own match modes (`base_domain`, `host`, `starts_with`, `exact`, `regular_expression`, `never`)
- checks the page's origin again, inside the page, just before filling
- also fills TOTP codes, generates and saves passwords, and lets you pick from the whole vault

See [ADR-0001](docs/adr/0001-standalone-replacement-for-upstream-userscript.md) and [ADR-0002](docs/adr/0002-secrets-reach-the-page-through-a-private-named-pipe.md).

## Commands

| Command | What it does |
|---|---|
| `fill` | Fill username and password (or a TOTP code on OTP-only pages) from the Items that match the page. With no match it syncs once and tries again; if there's still nothing, use `vault` |
| `totp` | Fill the TOTP code of a matching Item, or copy it if `totp.clipboard` is on |
| `generate` | Generate a password, save it to the vault, then fill it into a signup or change-password form. With no matching Item it creates one named after the host, using the username typed on the page (or asking for it); with one, it asks before replacing that Item's password; with several, you pick one or `new Item` |
| `vault` | Pick from the whole vault; filling an Item that doesn't match the page needs a confirmation. With `vault.allow_copy` on, a second menu offers `Fill`, `Copy password`, `Copy TOTP` and `Copy username` |
| `unlock` / `lock` / `sync` / `status` | Vault controls; `status` shows locked/unlocked and the last sync time |

The picker shows each Item as `<name> — <username>`.

## Requirements

- **Linux only.** qutewarden relies on `$XDG_RUNTIME_DIR`, Wayland and X11, and has never run on macOS.
- qutebrowser ≥ 3.0 (QtWebEngine)
- Python ≥ 3.11
- [`rbw`](https://github.com/doy/rbw) ≥ 1.15, logged in (`rbw login`). 1.15 is the first version that lists Item URIs without decrypting them ([ADR-0003](docs/adr/0003-rbw-1-15-and-match-types-from-its-db.md)).
- A graphical pinentry for `rbw`, because qutebrowser userscripts have no terminal: `rbw config set pinentry pinentry-qt` (or `pinentry-gnome3`, `pinentry-bemenu`, `pinentry-rofi`, …), then `rbw stop-agent`. A terminal-only pinentry fails with `rbw's pinentry needs a terminal`.
- A dmenu-compatible picker: by default `fuzzel --dmenu` on Wayland and `rofi -dmenu` on X11; set `picker` to use another one.
- Only for the clipboard opt-ins: `wl-copy`/`wl-paste` (wl-clipboard) on Wayland, `xclip` on X11

## Install

With Nix:

```sh
nix profile install github:HefKer/qutewarden
```

or as a flake input, adding `qutewarden.packages.${system}.default` to `environment.systemPackages` or `home.packages`. The flake installs only `qutewarden`; `rbw` and the picker come from your own configuration.

With pipx:

```sh
pipx install git+https://github.com/HefKer/qutewarden
```

Then make qutebrowser find it. `spawn --userscript` does **not** search `PATH`; a bare name is looked up only in qutebrowser's `userscripts` directories, so link the command there:

```sh
mkdir -p ~/.local/share/qutebrowser/userscripts
ln -sf "$(command -v qutewarden)" ~/.local/share/qutebrowser/userscripts/qutewarden
```

With `nix profile`, the link to `~/.nix-profile/bin/qutewarden` stays valid across upgrades. Alternatively, bind the absolute path, e.g. `spawn --userscript /run/current-system/sw/bin/qutewarden fill`.

## Key bindings

In qutebrowser's `config.py` (or with `:bind`, e.g. `:bind ,p spawn --userscript qutewarden fill`):

```python
config.bind(',p', 'spawn --userscript qutewarden fill')
config.bind(',t', 'spawn --userscript qutewarden totp')
config.bind(',g', 'spawn --userscript qutewarden generate')
config.bind(',v', 'spawn --userscript qutewarden vault')
config.bind(',u', 'spawn --userscript qutewarden unlock')
config.bind(',l', 'spawn --userscript qutewarden lock')
config.bind(',s', 'spawn --userscript qutewarden sync')
config.bind(',S', 'spawn --userscript qutewarden status')
```

Every setting can also be given as a flag **after** the subcommand, overriding the config file for that binding:

```python
config.bind(',P', 'spawn --userscript qutewarden fill --auto-fill --submit-after-fill')
config.bind(',G', 'spawn --userscript qutewarden generate --generator-length 32 --no-generator-symbols')
config.bind(',T', 'spawn --userscript qutewarden totp --totp-clipboard')
```

`qutewarden <subcommand> --help` lists every flag. From a terminal only `--help` and `--version` work; the subcommands need qutebrowser's userscript environment.

## Configuration

Settings live in `$XDG_CONFIG_HOME/qutewarden/config.toml` (usually `~/.config/qutewarden/config.toml`); `--config PATH` picks another file. A missing file means defaults; an unknown key or a wrong type is an error. This example sets every setting to its default:

```toml
# picker = "fuzzel --dmenu"         # unset: fuzzel --dmenu on Wayland, rofi -dmenu on X11
                                    # a string is split like a shell command; a list also works
auto_fill = false                   # fill without the picker when exactly one Item matches
insert_mode_after_fill = true
submit_after_fill = false

[matching]
default_mode = "base_domain"        # for URIs without a match mode: base_domain, host,
                                    # starts_with, exact, regular_expression, never

[generator]
length = 24                         # at least 4
uppercase = true
lowercase = true
digits = true
symbols = true

[totp]
clipboard = false                   # copy the code instead of filling it
clipboard_clear_seconds = 30

[vault]
allow_copy = false                  # offer copying a single field in `vault`
copy_clear_seconds = 30
```

| Setting | Flag |
|---|---|
| `picker` | `--picker CMD` |
| `auto_fill` | `--auto-fill` / `--no-auto-fill` |
| `insert_mode_after_fill` | `--insert-mode-after-fill` / `--no-insert-mode-after-fill` |
| `submit_after_fill` | `--submit-after-fill` / `--no-submit-after-fill` |
| `matching.default_mode` | `--matching-default-mode MODE` |
| `generator.length` | `--generator-length N` |
| `generator.uppercase` / `lowercase` / `digits` / `symbols` | `--generator-uppercase` / `--no-generator-uppercase`, and so on |
| `totp.clipboard` | `--totp-clipboard` / `--no-totp-clipboard` |
| `totp.clipboard_clear_seconds` | `--totp-clipboard-clear-seconds N` |
| `vault.allow_copy` | `--vault-allow-copy` / `--no-vault-allow-copy` |
| `vault.copy_clear_seconds` | `--vault-copy-clear-seconds N` |

The auto-lock timeout and the master password prompt (pinentry, which must be graphical; see [Requirements](#requirements)) are `rbw`'s: see `rbw config`.

## Security

By default qutewarden keeps to these rules:

1. No secret is ever part of a command sent to qutebrowser, because qutebrowser logs every userscript command to `qute://log`. Secrets reach the page through a named pipe (mode 0600, in a 0700 directory under `$XDG_RUNTIME_DIR/qutewarden/`) that qutebrowser reads with `jseval --file`.
2. No secret appears in process arguments or environment variables, ours or a child's. Secrets go to and from `rbw` only through stdin and stdout.
3. No secret is written to disk.
4. No secret goes on the clipboard unless you turn it on (`totp.clipboard`, `vault.allow_copy`), and then it is cleared after the configured time (only if the clipboard still holds it).
5. A Fill happens only when the page's origin, checked again inside the page just before filling, is the origin the userscript was started on, **and** the Item matches the page. The only exception is a Mismatch fill from `vault` that you confirmed after seeing the Item's URIs next to the page's address, all shown host first (or verbatim where that can't be done safely) and never shortened.
6. Messages show Item names, usernames and origins, never passwords, TOTP codes, notes or custom fields.

The no-leak test runs every subcommand against a fake vault and fails if a placeholder secret shows up in the FIFO, a child process's arguments or environment, or a message.

Limits:

- **No iframes.** `jseval` only runs in the top-level frame, so login forms inside iframes (some SSO and payment pages) can't be filled.
- **Clipboard opt-ins are a real Leak path.** Other programs and clipboard managers can read the clipboard until it is cleared. On Wayland, `wl-copy --sensitive` asks clipboard managers not to keep it; not all honour that.
- **No reply from the page.** qutewarden can't learn whether a Fill worked, so it says "filling `<name>`" before sending. If the origin check in the page fails (for example, you switched tab or the page navigated), nothing is filled and nothing is reported.
- **The page sees the filled values.** The fill script runs in its own isolated JavaScript world, so page scripts can't read its variables, but once a value is in a form field the page's own scripts can read it, as with any password manager.
- **`generate` saves before it fills**, so a failed save never leaves you with a password that exists only in the form. To create a new Item it runs twice: the first run copies the page's username into a `data-qutewarden-probe-<nonce>` attribute and spawns `qutewarden generate … --username-probe <nonce>`, which reads it from qutebrowser's DOM dump; only that second run generates the password ([ADR-0004](docs/adr/0004-generate-reads-the-username-back-through-the-dom-dump.md)). If no username comes back, the picker asks for it.
- qutewarden relies on the layout of rbw's local db file for URI match modes ([ADR-0003](docs/adr/0003-rbw-1-15-and-match-types-from-its-db.md)); it only ever reads that file.

To report a vulnerability, see [`SECURITY.md`](SECURITY.md).

### Network

qutewarden itself makes one kind of request: `tldextract` downloads the Public Suffix List at runtime and caches it under `$XDG_CACHE_HOME/qutewarden/tldextract`. Nothing else goes over the network except rbw's own traffic.

## AI use

Most of the code, tests and docs were written by AI coding agents (Claude Code), working from specs, ADRs and issues that the author wrote and reviewed. The author designed qutewarden, reviewed every change, and tested it by hand in qutebrowser. The Security rules are enforced by tests (the no-leak test, and from v2 the e2e log scan), not only by review. The agents' instructions are in [`AGENTS.md`](AGENTS.md) and [`docs/agents/`](docs/agents/), the decisions in [`docs/adr/`](docs/adr/).

## Development

```sh
nix develop -c scripts/check                    # ruff, pyright, full suite (incl. Playwright/Chromium tests of the fill JS)
nix develop -c scripts/check -m "not browser"   # same, tests without the browser
nix develop -c scripts/check --e2e              # also the e2e suite: real qutebrowser and rbw, local Vaultwarden
nix develop -c qutewarden-dev <subcommand>      # run this checkout's src/ against your real rbw
nix build                                       # the package; ./result/bin/qutewarden
git config core.hooksPath .githooks             # once per clone: run scripts/check before each commit
```

CI runs `scripts/check`, `nix build` and, as a separate job, the e2e suite on every PR. The e2e suite ([ADR-0007](docs/adr/0007-e2e-tests-run-real-rbw-and-qutebrowser-against-a-local-vaultwarden.md), `tests/e2e/`) runs offscreen qutebrowser and rbw against a throwaway Vaultwarden on 127.0.0.1, with its own rbw profile and XDG dirs under `/tmp`; it never touches your own vault. Before a release, go through the manual [smoke test](docs/e2e-checklist.md) in a real qutebrowser.

The design is in [`docs/spec-v1.md`](docs/spec-v1.md) and [`docs/spec-v2.md`](docs/spec-v2.md), the vocabulary in [`GLOSSARY.md`](GLOSSARY.md).

## Changes and issues

Releases are listed in [`CHANGELOG.md`](CHANGELOG.md). Bugs and feature requests go in [GitHub issues](https://github.com/HefKer/qutewarden/issues/new/choose), which offer a template for each and also track the planned work.

## License

[GPL-3.0-or-later](LICENSE)
