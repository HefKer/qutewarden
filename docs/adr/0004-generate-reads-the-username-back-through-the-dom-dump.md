# `generate` reads the username back through qutebrowser's DOM dump, in a second run

When `generate` creates a new Login item, it should use the username the user already typed on the signup page. A userscript can't get a value back from `jseval`: with `--quiet` there's no result at all, and without it the result goes to `message-info`, which is logged. So `generate` runs in two stages, and the username comes back through `QUTE_HTML`, the DOM dump qutebrowser writes for every userscript it spawns:

1. **Stage 1** (no Candidates, or the user picked "new Item"): generate nothing. Send a probe script through the fill route (ADR-0002) that checks `location.origin`, then copies the page's username field into the attribute `data-qutewarden-probe-<nonce>` on `<html>` (nonce: `secrets.token_hex(8)`). Then send `spawn --userscript <our absolute path> generate <the same settings flags> --username-probe <nonce>` and exit.
2. **Stage 2** (`--username-probe` given): read `data-qutewarden-probe-<nonce>` from the `<html>` element in `QUTE_HTML` with `html.parser`. If it's missing or empty, ask with the picker's text prompt ("Username"). Then generate the password, create the Item (named after the page's host, one URI for the page's origin, no match mode), and fill it in `new_password` mode; that fill also removes the probe attribute.

## Why this keeps the security rules

- The probe script carries no secret, and the password doesn't exist yet in stage 1: it is generated only in stage 2, after the username is known, and it reaches the page only through the pipe.
- What travels back is only the username, which is not a secret (rule 6 allows it in messages). It goes through a temp file qutebrowser itself writes and deletes; we write nothing to disk.
- The `spawn` line holds our path, settings flags and the nonce: nothing secret, so it's safe in `qute://log` (rule 1) and in our child's argv (rule 2).
- The nonce is lowercase hex (checked in both stages), so it can't inject into the attribute name or the command line. A page could rewrite the attribute (the DOM is shared with page scripts), but the page already controls its own username field, so it gains nothing; the value is only ever used as the new Item's username.

## Ordering (verified)

Stage 2 only works if qutebrowser runs the probe `jseval` before it dumps the DOM for the spawned script. Both are requests to the same tab's renderer, sent in the order of the FIFO lines, and `send_js` returns only after qutebrowser has read the script. Checked in real qutebrowser 3.7.0 (QtWebEngine 6.11.2, offscreen, 2026-10-07): a stage-1 script using `send_js` + `render_probe_js` and a stage-2 script reading `QUTE_HTML` found `data-qutewarden-probe-<nonce>="<typed value>"` on `<html>` in 4 of 4 runs. If a later qutebrowser breaks this, stage 2 simply finds no attribute and asks for the username.

## Considered Options

- **Always ask for the username**: simplest, but makes the user retype what's already on the page.
- **Return the value from `jseval` without `--quiet`**: it arrives as a statusbar message, logged, and never reaches our process.
- **Have the page send the value somewhere** (a local socket or file the page writes): needs a listener or a page-writable channel; far more attack surface than reading a dump qutebrowser already makes.

## Consequences

`generate` for a new Item is two processes; the second must be found by an absolute path (`sys.argv[0]`), because `spawn --userscript` doesn't search `PATH`. The hidden `--username-probe` flag is internal. If the user switches tabs between the stages, the second run sees the other tab's URL and dump; the probe attribute won't be there, so it asks, and the fill's origin check protects the page.
