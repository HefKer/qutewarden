# Security policy

qutewarden handles your Bitwarden secrets, so security reports are welcome and taken seriously.

## Reporting a vulnerability

Report it privately through GitHub's [private vulnerability reporting](https://github.com/HefKer/qutewarden/security/advisories/new) ("Report a vulnerability" on the repository's Security tab). Please don't open a public issue, pull request or discussion for it.

Include what you did, what you expected, and what happened, along with your qutewarden, qutebrowser, QtWebEngine and rbw versions. Don't include real secrets: use a throwaway Item.

## What counts

- Any **Leak path**: any way a secret (password, TOTP code or secret, note text, custom field value) can end up somewhere other than the target form field, such as qutebrowser's log (`qute://log`), process arguments or environment variables, files on disk, the clipboard when the clipboard options are off, or a message.
- Any way around **Security rule 5**: a Fill on a page whose origin isn't the one the userscript was started on, or of an Item that doesn't match the page, without a Mismatch fill the user confirmed.

The Security rules are listed in the [README](README.md#security), along with the limits qutewarden knowingly has (for example, that page scripts can read a value once it is in a form field). Those limits aren't vulnerabilities on their own, but a way to make them worse is.

## Supported versions

Only the latest release gets security fixes.
