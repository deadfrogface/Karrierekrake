# Google OAuth verification screencast checklist

Record a continuous walkthrough for Google’s OAuth verification reviewers.

Generated from `integrations.google_oauth.screencast_checklist()`:

1. Show homepage with app description, ToS link, privacy policy link
2. Show in-app purpose text before opening the system browser
3. Demonstrate Gmail-only connect requesting only `gmail.readonly`
4. Demonstrate Calendar FreeBusy-only connect requesting only `calendar.freebusy`
5. Demonstrate scope upgrade only after enabling Calendar write / FreeBusy feature
6. Demonstrate partial consent: deny Calendar → Gmail still works
7. Demonstrate Disconnect Google (remote revoke + local keyring wipe)
8. Confirm no embedded WebView — system browser address bar visible
9. Confirm no `gmail.modify` / `mail.google.com` / full calendar in consent screen
10. Use approved test accounts listed in `docs/google/oauth-test-accounts.md`

## Tips

- Narrate which Cloud project (test vs production) is used.
- Show Settings → Datenschutz connect buttons and the confirmation copy.
- Keep the consent URL visible for several seconds.
