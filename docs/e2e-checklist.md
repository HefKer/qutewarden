# End-to-end checklist (real qutebrowser)

Manual steps that exercise every subcommand in a real qutebrowser with a real `rbw` vault. Run them before a release and after changing the fill route, the fill JavaScript, or the rbw Backend. Vocabulary: [`GLOSSARY.md`](../GLOSSARY.md).

Tick each box; note the qutebrowser, QtWebEngine and rbw versions at the top of your report.

## Setup

- [ ] Build and install: `nix build` (or `nix profile install .`), then `./result/bin/qutewarden --version` prints `qutewarden 0.1.0`.
- [ ] Link it where qutebrowser looks (`spawn --userscript` doesn't search `PATH`): `ln -sf "$PWD/result/bin/qutewarden" ~/.local/share/qutebrowser/userscripts/qutewarden`.
- [ ] Add the key bindings from the README (`,p` fill, `,t` totp, `,g` generate, `,v` vault, `,u` unlock, `,l` lock, `,s` sync, `,S` status) and `:config-source`.
- [ ] `rbw --version` is ≥ 1.15 and `rbw login` has been done.
- [ ] `rbw config show` has a graphical `pinentry` (e.g. `pinentry-qt`, `pinentry-gnome3`, `pinentry-bemenu`, `pinentry-rofi`), because qutebrowser userscripts have no terminal. After changing it, run `rbw stop-agent`.
- [ ] Use a **test vault or test Items** only. Create:
  - **A**: Login item for a site you can log in to (e.g. a throwaway account), URI with no match mode, with a TOTP secret. Note its password, username and current TOTP code: you'll search the log for them.
  - **B**: a second Login item with a URI on the same base domain as A (two Candidates).
  - **C**: a Login item whose URI has match mode `never` for that site.
  - **R**: a Re-prompt item (master password re-prompt on) for some site.
- [ ] Make sure every userscript command reaches the log: `:set logging.level.ram debug` (the default) — qutebrowser logs each FIFO line as `Got userscript command: …` at debug level. Restart qutebrowser as `qutebrowser --loglines 100000` so `qute://log` starts empty and keeps the whole session (it holds only the last 2000 lines by default, which drops the early runs before the final log search).

## unlock / lock / status / sync

- [ ] `,l` (lock): `rbw unlocked` in a terminal now fails.
- [ ] `,S` (status): message says the vault is locked and shows a last sync time.
- [ ] `,u` (unlock): pinentry appears; after entering the master password, `,S` says unlocked.
- [ ] `,u` again while unlocked: no pinentry, no error.
- [ ] `,s` (sync): no error; `,S` shows a newer last sync time.
- [ ] Wrong master password / cancel pinentry on `,u`: a readable error message, no traceback, qutebrowser stays responsive.

## fill

- [ ] `,l`, then on A's login page `,p`: pinentry appears first, then the picker.
- [ ] Picker shows A and B as `<name> — <username>`; C (`never`) is **not** listed; R is listed only if its URI matches.
- [ ] Pick A: the message reads `qutewarden: filling <name> (<username>)`; username and password are filled; insert mode is on.
- [ ] The form submits fine (fields were picked up by the page; try a React/Vue site too).
- [ ] Cancel the picker (Escape): nothing happens, no error.
- [ ] Two-step login (username page, then password page): `,p` on page 1 fills the username only; `,p` on page 2 fills the password.
- [ ] OTP-only page (after the password step of A's 2FA): `,p` fills A's TOTP code.
- [ ] With only one Candidate and `fill --auto-fill` bound: fills without the picker.
- [ ] `fill --submit-after-fill`: the form is submitted after filling.
- [ ] `fill --no-insert-mode-after-fill`: stays in normal mode.
- [ ] Page with no Candidates: after one sync, the error mentions `vault`.
- [ ] On a `file://` or `qute://` page: an error, and nothing is fetched from rbw (no pinentry for R).
- [ ] Origin check: press `,p`, and while the picker is open switch to another tab on a different site, then pick A. Nothing is filled in the other tab.
- [ ] R (Re-prompt item): listing the picker does **not** ask for the master password; picking R asks once.
- [ ] Login form inside an iframe: not filled (known limit), no error that breaks the page.

## totp

- [ ] On A's 2FA page with the code field focused: `,t` shows `qutewarden: filling TOTP for <name> (<username>)` and fills the current code.
- [ ] Without focus: `,t` still finds the field (`autocomplete=one-time-code` or a code-like name).
- [ ] `totp --totp-clipboard`: the code is copied, not filled; the message reads `copied TOTP for <name> (<username>); clipboard clears in 30 s` and doesn't contain the code. After `totp.clipboard_clear_seconds` (30 s) the clipboard is empty — unless you copied something else meanwhile, which must be left alone.
- [ ] Item without TOTP: error `<name> (<username>) has no TOTP`.
- [ ] With neither `wl-copy` nor `xclip` on `PATH`, `totp --totp-clipboard`: error `no clipboard tool found …`, and no pinentry for a Re-prompt item (checked before any secret is fetched).

## generate

- [ ] Signup page of a site with **no** Item, username typed in the form: `,g` runs twice (ADR-0004): the first run probes the username and spawns `generate … --probe-origin <origin> --username-probe <16 hex>`, the second a Login item named after the host, with the page's origin as URI (no match mode) and the typed username; check with `rbw get --full <name>`. The new-password and confirmation fields are filled with the same password, and it equals `rbw get <name>`. The message reads `saved new password, filling <host> (<username>)`.
- [ ] Same, with a non-default flag (`generate --generator-length 32`): the second run keeps it (the saved password has 32 characters).
- [ ] Same, but with the username field empty: the picker asks for a username.
- [ ] Change-password page of A (one Candidate): `,g` asks "Replace password for `<username>` on `<name>`?"; Yes updates A and fills; `rbw get --full` shows the old password in A's history; A's notes are unchanged.
- [ ] Answer No: nothing is saved or filled.
- [ ] Two Candidates (A and B): the "Replace password" picker offers both and `new Item`; `new Item` behaves like the no-Item case.
- [ ] `generate --generator-length 32 --no-generator-symbols`: the saved password has 32 characters and no symbols.
- [ ] Save fails (e.g. network down, or `rbw lock` while the picker is open and cancel pinentry): error message, **nothing** is filled.

## vault

- [ ] `,v` lists every Login item, not just Candidates.
- [ ] Pick a Candidate: fills as `fill` does (`filling <name> (<username>)`), no confirmation.
- [ ] Pick an Item that isn't a Candidate (e.g. C): the confirmation `Fill <name> (<username>) on <origin>?` lists `Page: <origin>` and `Item: <uri>` lines; No fills nothing; Yes fills (Mismatch fill).
- [ ] With `vault.allow_copy` off: picking an Item goes straight to filling; no copy choices.
- [ ] `vault --vault-allow-copy`: after picking an Item, a second menu offers `Fill`, `Copy password`, `Copy TOTP` (Items with TOTP) and `Copy username` (Items with a username). Each copy puts the value on the clipboard, says `copied <field> for <name> (<username>); clipboard clears in 30 s` without the value, and clears it after `vault.copy_clear_seconds` unless you copied something else meanwhile. `Fill` behaves as without the flag.

## No secret in qutebrowser's log or elsewhere

After running everything above:

- [ ] Open `qute://log?level=vdebug` and search (Ctrl+F) for A's password, A's current and recent TOTP codes, the generated passwords, and any copied field: **no hits**. The log should show only `message-info`/`message-error`, `mode-enter insert`, `jseval --quiet --world=213 --file …/qutewarden/fill-….js` and (from `generate`) `spawn --userscript …/qutewarden generate … --probe-origin <origin> --username-probe <nonce>` lines from qutewarden.
- [ ] Also search `qute://log` for any Item notes or custom field values: no hits.
- [ ] `:messages` (or the statusbar history) shows only Item names, usernames and origins.
- [ ] `ls -la $XDG_RUNTIME_DIR/qutewarden/`: directory is `drwx------`, and no `fill-*.js` pipes are left behind.
- [ ] While a fill is pending (picker open), `ps -eo args | grep -E 'rbw|qutewarden|wl-copy|xclip'` shows no secret in any argv.
- [ ] `grep -r` for A's password in `~/.local/share/qutebrowser`, `~/.cache/qutebrowser`, `~/.cache/qutewarden` and `/tmp`: no hits.
- [ ] `:process` for the last qutewarden runs: their stdout/stderr contain no secrets.
- [ ] Quick freeze check: kill the userscript during a fill (`pkill -f 'qutewarden-wrapped fill'` with the picker open; the Nix wrapper runs it as `.qutewarden-wrapped`) — qutebrowser stays responsive.

## Clean up

- [ ] Delete the Items created by `generate`, revert A's password if needed, and restore any changed logging settings.
