# rbw ≥ 1.15, with URI match modes read from rbw's local db file

`list_logins` must return every Login item with its URIs and their match modes, without decrypting any Item. rbw asks for the master password every time it decrypts a field of a Re-prompt item, so calling `rbw get` per Item would prompt over and over on every Fill. `rbw list --raw` lists Items without that prompt, but it only includes URIs from 1.15.0 on, and never their match mode. The match mode (`match_type`) is stored unencrypted in rbw's local db file (`$XDG_CACHE_HOME/rbw[-<profile>]/<server>:<email>.json`). So the rbw Backend requires rbw ≥ 1.15 (checked with `rbw --version`), takes id, name, username and URIs from `rbw list --raw`, and joins in `match_type`, the Re-prompt flag and whether a TOTP is set from the db file, which it only ever reads. If the two lists of an Item's URIs have different lengths (rbw drops URIs it can't decrypt), those URIs get the `never` mode rather than a guessed one. `get_secrets` makes a single `rbw get --raw` call and computes the TOTP code itself, so it doesn't decrypt twice.

Saving goes through stdin, never arguments: rbw 1.15's `rbw add` and `rbw edit` read the password (first line) and notes (the rest) from stdin when it isn't a terminal, and don't open `$EDITOR` (`src/edit.rs`). Because `rbw edit` replaces the notes too, `update_password` sends the existing notes back after the new password, and refuses to save when a notes line starts with `#`, since rbw would silently drop it.

## Considered Options

- **Keep rbw ≥ 1.14 and call `rbw get --raw` for every Item**: a master password prompt per Re-prompt item on every Fill.
- **Ignore match modes**: every URI would use `matching.default_mode`, which can fill on origins the user excluded with `never` or narrowed with `exact`.

## Consequences

We depend on rbw's db file layout, which isn't a public interface. A missing or unreadable file is reported with the hint `rbw sync`. The last sync time shown by `status` is that file's modification time, because rbw has no command for it.

## Amendment (v2): item types and linked custom fields

`rbw get --raw` gives Card and Identity values without a type tag, and leaves out what a linked custom field stands for. The rbw Backend therefore also reads each Item's type and each linked field's `linked_id` from the same db file, again only reading it.
