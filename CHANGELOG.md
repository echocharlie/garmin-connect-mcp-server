# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[SemVer](https://semver.org/).

## [0.1.0] - 2026-07-23

Initial release.

### Added

- FastMCP server with six consolidated, read-only tools (all marked `readOnlyHint`):
  - `garmin_get_daily_summary` — per-day steps, resting HR, HRV, Body Battery, stress,
    intensity minutes, active calories
  - `garmin_get_sleep` — per-night score, stages, overnight HRV/SpO2/resting HR
  - `garmin_list_activities` — filterable activity list with training effect
  - `garmin_get_activity_detail` — single-activity deep dive; `detailed` mode adds lap
    splits and HR-zone breakdown
  - `garmin_get_training_status` — readiness, status, load, VO2max, HRV status, race
    predictions in one call
  - `garmin_get_body_composition` — weight/body-fat/muscle-mass entries
- `login.py` — one-time interactive sign-in (MFA-capable) against the
  `garminconnect` 0.3.x API; tokens stored at `~/.garminconnect` (or `$GARMINTOKENS`),
  password never persisted
- Compact markdown-table outputs with date-range caps and actionable error messages
- Graceful handling of accounts without watch data: `0.0` sensor readings render as
  missing, empty HR-zone tables are omitted, ride vs. run determines pace/speed units,
  and `garmin_get_training_status` explains missing device syncs instead of erroring
- Docs: README, non-technical [QUICKSTART](QUICKSTART.md), `requirements.txt` for
  pip/venv installs alongside `uv` support

### Notes

- Requires `garminconnect >= 0.3.6` (the 0.3.x rewrite removed the `garth` attribute;
  `login(tokenstore)` now persists tokens itself).
- Verified live against a real account: 126 activities (virtual rides, 2021–2023),
  including no-HR and with-HR activities, plus empty-account behavior for all health
  tools.
