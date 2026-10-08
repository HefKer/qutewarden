# e2e spike

Throwaway scripts that showed the e2e harness in ADR-0007 works: a real `qutewarden fill` in offscreen qutebrowser, through real rbw, against a local Vaultwarden, with the filled password absent from qutebrowser's debug log. All secrets here are dummies. The harness ticket turns these into `tests/e2e/` and deletes this directory.

| File | What it is |
|---|---|
| `register.py URL EMAIL PW` | Registers an account (PBKDF2 600k, HKDF, type-2 EncStrings, RSA keypair). Needs `cryptography`. |
| `items.py URL EMAIL PW` | Logs in and creates a Login (four match modes, TOTP, hidden and linked fields), a Re-prompt Login, a Card and an Identity. |
| `fake-pinentry` | Assuan pinentry that answers `GETPIN` with `$FAKE_PIN`. |
| `fake-picker` | dmenu-style picker: logs each request to `$FAKE_PICKER_LOG` and answers with the next regex from `$FAKE_PICKER_ANSWERS`, or `CANCEL`. |
| `server.py PORT LOGFILE` | Test login page that POSTs its origin and field values to `/report`. |
| `run-qutebrowser.sh` | Offscreen qutebrowser with debug JSON logging and `*.example.com` mapped to the test server. `$QB_BASEDIR` must be a short path. |
| `sway.cfg` | Config for headless sway (`WLR_BACKENDS=headless WLR_RENDERER=pixman`), used for wl-clipboard. |

Vaultwarden: `DATA_FOLDER=<tmp> ROCKET_ADDRESS=127.0.0.1 ROCKET_PORT=<port> SIGNUPS_ALLOWED=true WEB_VAULT_ENABLED=false DOMAIN=http://127.0.0.1:<port> vaultwarden`. rbw: `RBW_PROFILE=e2e`, its own `XDG_*` dirs under a short `/tmp` path, `rbw config set base_url http://127.0.0.1:<port>` and `pinentry` set to `fake-pinentry`.
