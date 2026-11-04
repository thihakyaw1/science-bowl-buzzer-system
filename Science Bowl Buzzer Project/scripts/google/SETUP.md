# Optional Google connection

The offline demo needs no Google account. Replace the placeholder IDs with your own.

1. Create your own Games folder, Player Names spreadsheet and Data Center sheet.
2. Add a Mapping tab to Player Names. Row 1: Port, Player ID, Player.
   Rows 2-17 correspond to P1-P16. Keep a stable ID with each person across seats.
3. In Data Center > Extensions > Apps Script, paste Code.gs.
   Fill SETTINGS.gamesFolder, SETTINGS.roster and SETTINGS.center with your IDs.
4. Deploy as a web app executing as owner. The original integration uses access
   Anyone and checks a private connection key. Account policies may restrict this.
5. Reload Data Center and choose Science Bowl > Set up connection key.
6. In the dashboard's Connect Google panel, enter your deployment /exec URL
   and key. Never publish the generated config/google_bridge.json.
7. Load player names, import subjects from a direct single-round PDF URL, then
   sync the game. Refresh analysis from Data Center when needed.

A deployed Google service is not included. Internet is needed for
sync and remote PDF downloads; cached player names and games work offline.
Retries update the same game. Statistics group by permanent player ID.
Earth Science/Astronomy combine under Earth and Space; General Science under
Energy. Blank/time-up rows are excluded from player accuracy.
