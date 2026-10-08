# Bitwarden's global Equivalent domains are vendored and on by default

rbw doesn't store the account's Equivalent domains, so qutewarden can't read the groups the user sees in the Bitwarden web vault. We vendor Bitwarden's global groups as a data file, generated from `bitwarden/server/src/Core/Utilities/StaticStore.cs`, and apply them by default, as the Bitwarden extension does, plus any groups the user adds in config. The source file is AGPL-3.0. GPL-3.0 §13 allows combining with it, so the data file keeps a header with its source and licence, and the README mentions it. The data is regenerated before each release.

Equivalent domains make more Items Candidates on a page, which loosens Security rule 5. On by default trades that for matching what Bitwarden users already expect. Two limits offset it: an Item that matches only through Equivalent domains is never Auto-filled, and the picker shows the domain it matched.

## Considered Options

- **Only the user's own groups**: safest, but logins like google.com on youtube.com would stop working for anyone coming from the extension.
- **Global groups behind an opt-in**: almost nobody would turn it on, and they'd be confused that it doesn't match like Bitwarden does.
- **Download the list at runtime**: another network request, and another way for matching to change underneath the user.

## Consequences

Global groups the user excluded in the web vault still apply in qutewarden. They can be turned off all at once with `matching.global_equivalent_domains = false`.
