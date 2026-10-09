# Release smoke test (real qutebrowser)

Every flow, and the scan for secrets in qutebrowser's log, the basedir and process arguments, is covered by the automated e2e suite (`nix develop -c scripts/check --e2e`, ADR-0007), which runs against a local Vaultwarden with a scripted picker and pinentry. What's left by hand, before a release, is what that suite can't have: the real pickers, a real graphical pinentry, a real clipboard manager and real sites. Vocabulary: [`GLOSSARY.md`](../GLOSSARY.md).

Tick each box; note the qutebrowser, QtWebEngine and rbw versions at the top of your report.

## Setup

- [ ] Regenerate Bitwarden's global Equivalent domains with `nix develop -c scripts/update-equivalent-domains` and commit any change (ADR-0006).
- [ ] Build and install: `nix build` (or `nix profile install .`), then `./result/bin/qutewarden --version` prints the version being released.
- [ ] Link it where qutebrowser looks (`spawn --userscript` doesn't search `PATH`): `ln -sf "$PWD/result/bin/qutewarden" ~/.local/share/qutebrowser/userscripts/qutewarden`.
- [ ] Add the key bindings from the README (`,p` fill, `,t` totp, `,g` generate, `,v` vault, `,u` unlock, `,l` lock) and `:config-source`.
- [ ] `rbw` has a graphical `pinentry` (e.g. `pinentry-qt`, `pinentry-gnome3`, `pinentry-bemenu`, `pinentry-rofi`), because qutebrowser userscripts have no terminal; after changing it, `rbw stop-agent`.
- [ ] Use test Items only: a Login item for each real site below (with a TOTP secret on one of them), and one Re-prompt item.

## Pickers and pinentry

Once on Wayland with fuzzel (the default there) and once on X11 with rofi (the default there):

- [ ] `,l`, then on a real site's login page `,p`: the graphical pinentry appears first, then the picker, which lists the site's Items as `<name> — <username>`.
- [ ] Pick one: the form is filled and submits fine.
- [ ] Escape in the picker: nothing happens, no error.
- [ ] `,v`, pick an Item for another site: the confirmation lists `Page: <host>` and one `Item: <host> <path>` line per URI; with fuzzel the window is wide enough that no line is cut off (try an Item URI like `https://www.365chess.com.evil.example/signup.php`).
- [ ] Pick the Re-prompt item: the pinentry asks for the master password once.

## Clipboard manager

With a clipboard manager running (e.g. cliphist, clipman or copyq):

- [ ] `totp --totp-clipboard` on the site with TOTP: the code can be pasted, and after `totp.clipboard_clear_seconds` it's gone from the clipboard.
- [ ] `vault --vault-allow-copy`, `Copy password`: the clipboard manager's history doesn't keep the password (wl-copy sends it as sensitive), or note which manager keeps it.

## Real sites

On two or three real sites (one with a two-step login, one built with React or Vue):

- [ ] `,p` fills the login form and the site accepts it.
- [ ] On the two-step login, `,p` on each step fills what that step asks for.
- [ ] On a 2FA page, `,t` fills the current code and the site accepts it.
- [ ] On a change-password page, `,g` replaces the password and fills it; the site accepts it and `rbw get` shows it. Change it back afterwards.
- [ ] On a real checkout page (stop before paying), `card` with a test Card item lists it as `<name> — <brand> *<last 4>`, fills the number, expiry and security code (split or `<select>` expiry fields too, where the site has them) and doesn't submit.
- [ ] On a real address form (a shop's shipping page, say), `identity` with a test Identity item lists it by name, fills the name, address, country, email and phone, and doesn't submit.

## Clean up

- [ ] Delete the Items created by `generate`, revert any changed passwords, and restore any changed settings.
