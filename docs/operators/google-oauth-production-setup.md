# Google OAuth production setup (operator)

This guide is for the product owner. **Do not** commit `client_id`, `client_secret`,
tokens, or test accounts to the repository or installer.

## Principles

- Desktop installed-app OAuth only (system browser, loopback `127.0.0.1`, PKCE).
- No KarriereKrake backend / token proxy.
- Separate Cloud projects for development and production.
- Calendar Mode A: FreeBusy only. Mode B: FreeBusy + `calendar.events.owned`.
- Never enable Maps / Places / Routes / Distance Matrix for KarriereKrake.

## Checklist

1. Create a Google Cloud project dedicated to KarriereKrake desktop OAuth.
2. Configure the OAuth consent screen (app name, support email, homepage, privacy policy).
3. Create an **Desktop** OAuth client. Treat any client secret as non-confidential
   (desktop apps cannot keep secrets).
4. Distribute credentials to the signed production build via your secure release process —
   not via git.
5. Request only the scopes the chosen mode needs; document them in the privacy policy.
6. Complete Google verification if Restricted/Sensitive scopes require it (Gmail readonly
   is Restricted and already a product consideration).
7. Test: connect → FreeBusy → approve event (Mode B) → disconnect (local delete + revoke
   when online) → ICS fallback with Google disconnected.

## What users must never do

Users must **not** create their own Cloud project or paste API keys into KarriereKrake
for maps or calendar. They sign in with their normal Google account through the official
consent screen.
