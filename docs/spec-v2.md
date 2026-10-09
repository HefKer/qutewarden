# qutewarden v2 spec

This spec lists only what v2 changes or adds. Everything in [`spec-v1.md`](spec-v1.md), its Platform and Security rules included, still holds unless a section below says otherwise. Vocabulary follows `GLOSSARY.md`. Every feature names the Security rules it touches and how it still keeps them.

## Releases

1. **`0.1.0`**: v1 as it is on `main`, plus the fixes for #24, #25 and #26 and the [release hygiene](#release-hygiene) below. The repository goes public at this tag.
2. **`1.0.0`**: v2, built in public.

"v1" and "v2" stay the names of the planning documents; `CHANGELOG.md` maps them to these version numbers.

Order of work: release hygiene and #24–#26 → tag `0.1.0` and go public → [e2e harness](#testing) → v2 features, each with its own e2e tests → tag `1.0.0`.

## Platform

- **Linux only.** The flake drops the darwin systems. The code relies on `$XDG_RUNTIME_DIR`, Wayland and X11, and has never run on macOS.
- Everything else is as in v1.

## Security rule changes

- **Rule 5** becomes: *A Fill of a Login item happens only when the page's origin, checked again inside the page just before filling, is the same origin the userscript was given, **and** the Item is a Candidate. The one exception is a Mismatch fill the user has confirmed. A Fill of a Card item or Identity item happens only after the user picked it, and it too only after the origin check inside the page.* See ADR-0005.
- **Rule 5, Candidates**: an Item can now be a Candidate through Equivalent domains (ADR-0006).
- **Rule 6** adds: *For a Card item, a message or picker line may include the brand and the last 4 digits of the number, never more of it, and never the security code or expiry.* Values of Identity items count as secrets in messages, like custom field values.

The no-leak test (v1 Security rules) extends to card numbers, security codes, identity values and custom field values. The e2e harness adds the same scan over qutebrowser's whole debug log.

## Equivalent domains

- **Two sources:**
  - Bitwarden's global groups, vendored as `equivalent_domains.json`. A script in `scripts/` regenerates it from `bitwarden/server/src/Core/Utilities/StaticStore.cs`. The file keeps a header naming its source and its licence (AGPL-3.0); the README notes this. It is regenerated before each release.
  - The user's own groups, from `matching.equivalent_domains`.
- `matching.global_equivalent_domains` (default `true`) turns the global groups on or off. Groups excluded or added in the Bitwarden web vault aren't visible to qutewarden (rbw doesn't store them), and the README says so.
- Equivalent domains apply only to URIs whose match mode is `base_domain` (set explicitly, or through `matching.default_mode`). A URI's base domain matches the page when both are in the same group.
- **Picker**: a Candidate that matches only through Equivalent domains shows the domain it matched, e.g. `Google — me@gmail.com (google.com)`.
- **Auto-fill** happens only when the single Candidate matches through a URI directly. When it matches through Equivalent domains, the picker opens.
- Rules touched: 5 (more Candidates, chosen by the user's own vault and config, and visible in the picker).

## Card and Identity items

New subcommands `card` and `identity`. See ADR-0005.

1. Unlock as in `fill`, then show the picker with every Card item (or Identity item).
   - Card lines: `<name> — <brand> *<last 4>`. Re-prompt Card items show `<name>` only, because reading the number would ask for the master password on every listing.
   - Identity lines: `<name>`.
2. Fill the chosen Item into the page. Auto-fill never applies.
3. `insert_mode_after_fill` applies as usual. `submit_after_fill` **never** applies to either subcommand: an unwanted card submit can be a purchase, and identity fills are usually one step in a longer form.

Finding fields (fill JavaScript):

- Mainly by `autocomplete` tokens.
  - Card: `cc-name`, `cc-given-name`, `cc-family-name`, `cc-number`, `cc-exp`, `cc-exp-month`, `cc-exp-year`, `cc-csc`, `cc-type`.
  - Identity: `honorific-prefix`, `given-name`, `additional-name`, `family-name`, `organization`, `street-address`, `address-line1`–`3`, `address-level1`/`2`, `postal-code`, `country`/`country-name`, `email`, `tel`, `username`.
- When there's no `autocomplete`, fall back to heuristics on `name`, `id`, the label and the placeholder.
- The form scope is v1's: the focused input's `<form>`, else the nearest common ancestor, else the whole page.
- **Expiry**:
  - a single field gets `MM/YY`, or `MM/YYYY` when its `maxlength`, `placeholder` or `pattern` asks for it;
  - split fields are filled separately;
  - a `<select>` takes the option whose value or text matches.
- Fields the Item has no value for are left alone.

`vault` stays Logins only. There is no copy option for Card or Identity items in v2.

## Custom fields

`fill`, `card` and `identity` also fill the chosen Item's custom fields.

- A custom field fills an input whose `name`, `id`, label, `aria-label` or placeholder equals the field's name. The comparison is case-insensitive and ignores surrounding whitespace. Only inputs in the built-in fill's scope count: the focused input's `<form>`, else its nearest ancestor that holds another field, else the whole page. Fields that don't match anything are skipped.
- Kinds:
  - **text** and **hidden** set the input's value;
  - **boolean** sets a checkbox (or radio button) on or off;
  - **linked** fills the built-in value it stands for (username or password for Login items, a card or identity value otherwise).
- Linked fields: `rbw get --raw` leaves out what a linked field stands for, so the rbw Backend reads `linked_id` from rbw's db file (amendment to ADR-0003).
- A custom field never overrides a field that the built-in username, password, card or identity logic already filled.
- Rules touched: 6. Every custom field value, including text, counts as a secret in messages.

## Iframes

- **Same-origin iframes: always on.** The fill JavaScript also searches frames it can reach from the top frame (`frame.contentDocument`, inside a `SecurityError` guard). They have the top page's origin, so rule 5 and the origin check are unchanged: the check covers each frame's own `location.origin`.
- **Cross-origin iframes: conditional on a spike.** They would be behind `iframes.cross_origin` (default `false`), using a greasemonkey script that runs in every frame. The home-manager module installs it when the setting is on; otherwise the README shows how. Before building it, a `/prototype` spike must show all of:
  1. The Item is a Candidate for the **frame's** origin, and that origin is checked inside the frame just before filling.
  2. No secret reaches the top page's scripts, a FIFO command, process arguments, the environment or disk.
  3. The greasemonkey script holds no secret, and it accepts fill data only from qutewarden's own fill script, not from page scripts.
  4. The new route is written down as an ADR alongside ADR-0002.

  If the spike can't show all four, cross-origin iframes move to "Not in v2", and the README limit becomes "only same-origin iframes".

## Config

| Setting | Default | Flag |
|---|---|---|
| `backend` | **removed** | **removed** |
| `matching.global_equivalent_domains` | `true` | `--matching-global-equivalent-domains` / `--no-…` |
| `matching.equivalent_domains` | `[]` (a list of lists of base domains) | none (config only) |
| `iframes.cross_origin` | `false` (only if the spike passes) | `--iframes-cross-origin` / `--no-…` |

A config file that still sets `backend` is an error that says the setting was removed.

## Backend interface

- `list_logins` is joined by listing calls for Card and Identity items, with no secrets: id, name, the Re-prompt flag, and for Cards the brand and last 4 digits when the Item isn't a Re-prompt item.
- `get_secrets(id)` returns the whole typed Item: Login, Card or Identity values plus its custom fields, with linked fields resolved.
- rbw: `rbw get --raw` gives Card and Identity values without a type tag, so the item type comes from the db file (which ADR-0003 already reads), not from guessing at keys.

## home-manager module

`programs.qutewarden`, exported as `homeManagerModules.default` from the flake:

| Option | Does |
|---|---|
| `enable` | installs the package and links it into `$XDG_DATA_HOME/qutebrowser/userscripts/qutewarden` |
| `package` | defaults to this flake's package |
| `settings` | written to `$XDG_CONFIG_HOME/qutewarden/config.toml` |
| `keyBindings` | e.g. `{ ",p" = "fill"; ",P" = "fill --auto-fill"; }`, added to `programs.qutebrowser.keyBindings.normal` as `spawn --userscript qutewarden …`. Default `{}`. |

With `settings.iframes.cross_origin = true`, the module also adds the greasemonkey script through `programs.qutebrowser.greasemonkey`. A test evaluates the module (e.g. a flake check that builds a home-manager configuration using it).

## Testing

See ADR-0007. A new e2e suite runs real qutebrowser (offscreen) and real rbw against a local Vaultwarden seeded with a dummy account. Nothing in it touches the developer's own vault.

- **Fixtures** (pytest, session-scoped where they can be):
  - Vaultwarden on a free port in a temp dir.
  - A Python seed script that does Bitwarden's client-side crypto to register the account and create Items: Logins covering every match mode, TOTP, every custom field kind, a Re-prompt item, Cards and Identities. Every secret contains a unique marker.
  - rbw isolated with `RBW_PROFILE` and its own XDG dirs, under a short `/tmp` path (Unix socket path limit), using a scripted pinentry that logs each call.
  - A scripted dmenu-style picker that logs each request and answers from a queue.
  - A local HTTP server for test pages. qutebrowser's `host-resolver-rules` maps `*.example.com` (and other test domains, for Equivalent domains and iframes) to it, so each page has its own origin. Pages POST their field values to the server.
  - Headless sway with wl-clipboard, and Xvfb with xclip, for the clipboard tests. `*_clear_seconds` is set to about 2 s.
  - qutebrowser with `--json-logging --debug`, a short `--basedir`, and the userscript pointing at `src/`. Tests send it commands over IPC and wait for the "Process finished" log line.
- **Scenarios**: every flow in today's `docs/e2e-checklist.md`, plus each v2 feature as it lands.
- **No-leak scan**: at the end, every marker is searched for in qutebrowser's whole log, the basedir, `/proc/*/cmdline` and `environ` snapshots taken during runs, and qutewarden's runtime dir. Commands the test sends over IPC are logged word for word, so they never contain a marker.
- **Running it**: its own pytest marker, `e2e`, run by `scripts/check --e2e`, and not by the pre-commit hook. In CI it's a separate job on every PR. On the runner, lift Ubuntu's restriction on unprivileged user namespaces so Chromium's sandbox works; if that fails, use `qt.chromium.sandboxing = disable-all` in CI only.
- **Versions**: only those pinned in `flake.lock`. The README's minimum versions remain stated, not tested.
- `docs/e2e-checklist.md` shrinks to a manual smoke test before a release: the real picker (fuzzel and rofi), a real graphical pinentry, a real clipboard manager, and two or three real sites.
- The spike scripts that proved this works are in `docs/e2e-spike/`. The harness ticket turns them into `tests/e2e/` and deletes that directory.

## Release hygiene

For `0.1.0`:

- **`CHANGELOG.md`** in the Keep a Changelog format.
- **`SECURITY.md`**: how to report a vulnerability privately (GitHub private vulnerability reporting, turned on in the repo settings), what counts (any Leak path or any bypass of rule 5), and the supported version.
- **README**:
  - Remove "early development" and "bw planned for v2".
  - **AI use**: most of the code, tests and docs were written by AI coding agents (Claude Code) working from specs, ADRs and issues the author wrote and reviewed; the author designed it, reviewed every change, and tested it by hand in qutebrowser. The Security rules are enforced by tests (the no-leak test, and from v2 the e2e log scan), not only by review. Point to `AGENTS.md`, `docs/agents/` and `docs/adr/`.
  - **Network**: `tldextract` downloads the Public Suffix List at runtime and caches it. Nothing else goes over the network except rbw's own traffic.
  - **Platform**: Linux only.
  - A conciseness pass over the whole README.
- **Flake**: drop the darwin systems.
- **Config**: remove `backend`.
- **GitHub**: repo description and topics, issue templates (bug, feature), branch protection on `main` that requires CI.
- Distribution stays the flake plus GitHub releases. PyPI and nixpkgs come later.

## Not in v2

- **`bw` backend.** `bw` takes its session key only from `BW_SESSION` or `--session`, so every call would put a secret in the environment or arguments (rule 2). It doesn't enforce master password re-prompt. `bw serve` has no authentication against other local processes.
- **Saving new logins on submit, and updating a changed password.** qutebrowser has no way for a page to notify a userscript without a keypress. The only way to read values back is the `QUTE_HTML` dump, which qutebrowser writes to `$TMPDIR` (rule 3). A local listener for the page to post to could be called by any website.
- Copying Card or Identity values. A NixOS module. PyPI and nixpkgs packages. Testing against several versions of qutebrowser and rbw.
- Cross-origin iframes, if the spike fails.
