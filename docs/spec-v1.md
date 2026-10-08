# qutewarden v1 spec

qutewarden does in qutebrowser what the Bitwarden browser extension does elsewhere. It replaces qutebrowser's bundled `qute-bitwarden` userscript; ADR-0001 explains why. Vocabulary follows `GLOSSARY.md`.

## Platform

- Python ≥ 3.11 (config is parsed with `tomllib`)
- qutebrowser ≥ 3.0 on QtWebEngine (QtWebKit isn't supported)
- Backend: `rbw` ≥ 1.15. 1.14 is the first version that enforces master password re-prompt; 1.15 adds URIs to `rbw list --raw`, which listing Items without a re-prompt storm needs (ADR-0003).
- License: GPL-3.0-or-later
- Delivery: a Python package with a Nix flake that installs a single `qutewarden` command. Users bind its subcommands with `spawn --userscript qutewarden <subcommand> [flags]`. The fill JavaScript ships inside the package.

## Security rules

No rule may be broken by default. See ADR-0002 for how filling meets them.

1. No secret is ever part of a command sent to qutebrowser through `QUTE_FIFO`, because qutebrowser logs every such command to `qute://log`.
2. No secret appears in process arguments or environment variables, ours or a child's. Secrets go to and from the Backend only through stdin and stdout.
3. No secret is written to disk, whether a temp file or any other file.
4. No secret goes on the clipboard unless the user turns it on (`totp.clipboard`, `vault.allow_copy`). Clipboard contents are cleared after a set time.
5. A Fill happens only when the page's origin, checked again inside the page just before filling, is the same origin the userscript was given, **and** the Item is a Candidate. The one exception is a Mismatch fill the user has confirmed.
6. Messages from qutewarden may include Item names, usernames and origins. They never include passwords, TOTP codes or secrets, note text, or custom field values.

A test enforces 1, 2 and 6. It runs every subcommand against a fake Backend whose secrets are known placeholder strings, and fails if any placeholder appears in what was sent to the FIFO, in a child process's arguments or environment, or in a message.

## How a secret reaches the page

1. Create a named pipe (`mkfifo`, mode 0600) inside a directory only the user can access (0700) under `$XDG_RUNTIME_DIR/qutewarden/`. Give it a unique name per run.
2. Write `jseval --quiet --world=<isolated world id> --file <pipe path>` to `QUTE_FIFO`.
3. Write the generated fill JavaScript to the pipe, with secrets embedded as JSON string literals. qutebrowser's `open()` blocks until the data is there.
4. Remove the pipe.

The fill JavaScript first checks that `location.origin` matches the expected origin, and gives up silently if it doesn't. qutewarden can't receive a reply from the page, so it reports the outcome beforehand, in neutral wording.

`jseval` only runs in the top-level frame, so login forms inside iframes aren't supported.

## URI match

- Each URI on a Login item has a match mode: `base_domain`, `host`, `starts_with`, `exact`, `regular_expression` or `never`. These behave as they do in Bitwarden.
- A URI with no mode uses `matching.default_mode` (default `base_domain`).
- Base domains come from the Public Suffix List, via `tldextract`, with its cache kept under the qutewarden cache directory.
- An Item is a **Candidate** when any of its URIs match the page. Item names are never used for matching.
- Equivalent domains are left for v2.

## Subcommands

### `fill`
1. Get the page URL from `QUTE_URL`. If the vault is locked, unlock it (the Backend handles pinentry).
2. Work out the Candidates. If there are none, sync once and try again. If there are still none, show an error that mentions `vault`.
3. With exactly one Candidate and `auto_fill` on, use it straight away. Otherwise show the picker; each line shows the Item name and username.
4. If the page has only an OTP-style field and no password field, fill the chosen Candidate's TOTP code. Otherwise fill the username and password.
5. If `insert_mode_after_fill` is on, enter insert mode. Submit the form only if `submit_after_fill` is on.

### `totp`
Pick a Candidate, as in steps 1–3 of `fill`, then fill its TOTP code. If `totp.clipboard` is on, copy the code instead of filling it, and clear the clipboard after `totp.clipboard_clear_seconds`.

### `generate`
1. Generate a password using the `generator.*` settings.
2. Save it to the vault **before** filling:
   - No Candidates: create a Login item named after the page's host, with a URI for the page's origin and no match mode. The username is read from the page's username field if possible, otherwise asked for with a text prompt in the picker. A username asked for in the picker is also filled into the page's username field in step 3, if that field is empty.
   - One Candidate: ask "Replace password for `<username>` on `<name>`?", then update it. The old password goes into the Item's history.
   - Several Candidates: pick one, or choose "new Item".
3. Fill the password into the page's new-password fields (`autocomplete="new-password"`, or the password fields if there are no such fields; confirmation fields too).

### `vault`
Pick from **every** Login item. If the choice is a Candidate, Fill as normal. If it isn't, show a confirmation listing the Item's URIs next to the page's origin, and Fill only if the user agrees (a Mismatch fill). When `vault.allow_copy` is on, there's also a choice to copy a single field, which is cleared after `vault.copy_clear_seconds`.

### `unlock`, `lock`, `sync`, `status`
Thin wrappers around the Backend. `status` shows locked/unlocked and the last sync time with `message-info`. The auto-lock timeout and the master password prompt are left to `rbw`.

## Finding form fields (fill JavaScript)

- If an input is focused, start from it and fill it and the matching fields in the same `<form>`, or in the nearest common ancestor when there's no form.
- With no focused input, use heuristics: `autocomplete` attributes (`username`, `email`, `current-password`, `new-password`, `one-time-code`), `type=password`, then the nearest visible text, email or tel input before the password field. Hidden and disabled fields are skipped.
- On multi-step logins, fill whichever fields are present now.
- Set each value through the native value setter, then fire `input` and `change` (bubbling) so framework-managed forms pick it up.

## Config

The file is `$XDG_CONFIG_HOME/qutewarden/config.toml`. Every setting can be overridden with a command-line flag of the same name.

| Setting | Default |
|---|---|
| `picker` | auto-detect: `fuzzel --dmenu` on Wayland, `rofi -dmenu` on X11 |
| `auto_fill` | `false` |
| `backend` | `"rbw"` |
| `insert_mode_after_fill` | `true` |
| `submit_after_fill` | `false` |
| `matching.default_mode` | `"base_domain"` |
| `generator.length` | `24` |
| `generator.uppercase` / `lowercase` / `digits` / `symbols` | all `true` |
| `totp.clipboard` | `false` |
| `totp.clipboard_clear_seconds` | `30` |
| `vault.allow_copy` | `false` |
| `vault.copy_clear_seconds` | `30` |

## Backend interface

Built so `bw` can be added in v2 without changing callers. The calls are: `is_unlocked`, `unlock`, `lock`, `sync`, `status`, `list_logins` (no secrets: id, name, username, URIs with their modes), `get_secrets(id)` (password and TOTP code, through stdout only), `create_login`, `update_password`. The `rbw` implementation (rbw ≥ 1.15) lists Items with `rbw list --raw` plus the match modes from rbw's local db file, reads secrets with one `rbw get --raw` per Item, uses the other `rbw` subcommands for the rest, and passes secrets to `rbw add` and `rbw edit` through stdin, never through arguments. rbw 1.15 reads stdin when it isn't a terminal and doesn't open `$EDITOR` (confirmed in its source; see ADR-0003).

## Testing

- pytest unit tests for URI match, choosing Candidates, config, and each subcommand, run against a fake Backend and a fake `QUTE_FIFO`
- The no-leak test described under Security rules
- Playwright with Chromium for the fill JavaScript, against sample HTML login pages: single-step, two-step, signup, OTP, React-controlled inputs, and an origin mismatch
- A manual end-to-end checklist in real qutebrowser: `docs/e2e-checklist.md`

## Not in v1

`bw` backend, saving new logins when a form is submitted, updating a password when it changes, filling cards and identities, custom fields, equivalent domains, iframe login forms, a home-manager module.
