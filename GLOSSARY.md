# qutewarden

A qutebrowser integration with a Bitwarden vault that does the job of the Bitwarden browser extension, which doesn't exist for qutebrowser.

## Language

**Vault**:
The user's Bitwarden collection of Items, reached through a Backend.
_Avoid_: Database, store

**Item**:
A single stored secret record in the Vault. Its type is Login, Card, Identity, Secure Note or SSH Key.
_Avoid_: Entry, cipher, credential, password (when meaning the whole record)

**Login item**:
An Item of type Login: a username, a password, an optional TOTP secret, and a list of URIs.
_Avoid_: Account, site, login (bare)

**URI match**:
The rule that decides whether a Login item applies to a page, taken from one of the item's URIs and its match mode (base domain, host, starts-with, exact, regular expression, never). Items are matched on URI match only, never on their name.
_Avoid_: Name matching, domain lookup

**Candidate**:
A Login item whose URI match applies to the current page, so it can be filled there.
_Avoid_: Match, suggestion, result

**Fill**:
Putting an Item's values into the form fields of the current page after the user picks it.
_Avoid_: Autotype, insert, paste

**Auto-fill**:
A Fill that happens without the picker, because there is exactly one Candidate. It is off unless the user turns it on.
_Avoid_: Autologin, instant fill

**Mismatch fill**:
A Fill of an Item that isn't a Candidate, chosen from the whole vault. It happens only after the user confirms they've seen the Item's URIs next to the page's origin.
_Avoid_: Force fill, override

**Re-prompt item**:
An Item that is marked to need the master password again before any of its secrets are used.
_Avoid_: Protected item, locked item

**Backend**:
An external Bitwarden client program that gives access to the Vault, such as `rbw` or the official `bw` CLI.
_Avoid_: Provider, driver, client

**Leak path**:
Any route by which a secret could end up somewhere other than the target form field, such as qutebrowser's log, the clipboard, process arguments, or files on disk.
