# Secrets reach the page through a private named pipe, never through a qutebrowser command

qutebrowser logs every command a userscript sends it, word for word, to `qute://log` (`commands/userscripts.py`). Any secret sent as part of a command therefore leaks, and that includes `fake-key`, `insert-text` and inline `jseval`. To Fill, we create a named pipe in `$XDG_RUNTIME_DIR` that only the user can access, write the fill JavaScript (with the secret in it) to the pipe, and send `jseval --quiet --world=<isolated> --file <pipe>`. The log only records the pipe's path. The secret never touches disk. The fill code runs in a JavaScript context the page's scripts can't access, and it checks `location.origin` again before filling.

## Considered Options

- **Fake keystrokes or `insert-text`**: this is what the bundled script does. The values leak to the log.
- **Short-lived localhost HTTP server with a one-time token**: more moving parts, and the page itself can send requests to localhost.
- **Temp file with private permissions**: puts the secret on disk, even if only briefly.

## Consequences

The fill JavaScript runs in the top-level frame. From there it reaches same-origin iframes and fills forms in them (see the v2 amendment); cross-origin iframes are out of its reach and are left alone, with no message.

## Amendment (v2): same-origin iframes

The fill still runs in the top-level frame, but from there it also reaches the documents of same-origin iframes (`frame.contentDocument`) and fills a form in one of them, after checking that document's own `location.origin`. Every Fill does this: `fill`, `vault`, `totp`, `generate`, `card` and `identity`. Cross-origin iframes stay out of reach.
