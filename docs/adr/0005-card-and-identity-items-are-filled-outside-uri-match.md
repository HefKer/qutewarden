# Card and Identity items are filled by explicit pick, outside URI match

Card items and Identity items have no URIs, so they can never be Candidates, and v1's Security rule 5 would make every such Fill a Mismatch fill with a confirmation. We give them their own subcommands, `card` and `identity`, which pick from every Item of that type and fill it with no Mismatch confirmation. Rule 5 now asks for a Candidate only from Login items; for Cards and Identities it asks only that the user picked the Item, and the origin check inside the page still runs. To limit the cost of a wrong fill, these subcommands never Auto-fill and never submit the form, whatever `auto_fill` and `submit_after_fill` say.

## Considered Options

- **Put them in `vault` and confirm every Fill**: on checkout and address forms you'd confirm the same thing every time, so people would learn to confirm without looking.
- **Let users add URIs to Cards and Identities**: Bitwarden doesn't support that, so we'd need a second matching scheme kept outside the vault.

## Consequences

Any page can receive a Card or Identity the user picks, including a phishing page. The user's choice of Item is the only guard. Rule 6 allows the brand and last 4 digits of a card number in the picker, so the user can tell cards apart.
