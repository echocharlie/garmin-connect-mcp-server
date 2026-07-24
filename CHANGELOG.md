# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[SemVer](https://semver.org/).

## [0.2.1] - 2026-07-23

Remaining review items that didn't make the 15-finding report.

### Fixed

- `garmin_list_activities` fetches a single page of `limit+1` results from the same
  endpoint the library uses, instead of paginating the entire date range 20-at-a-time
  and discarding everything past `limit`.
- `login.py` refuses to run without an interactive terminal — `getpass` would
  otherwise echo the password in cleartext into captured output — and no longer
  duplicates the token-directory definition (imported from `server.py`).
- Date-defaulting tools document that "today" is the server's local day, which can
  differ from the Garmin account's day near midnight.

### Changed

- Cleanup: shared `_km`/`_kg`/`_table` formatting helpers replace repeated inline
  expressions and hand-counted table separators; `_hms` builds on `_hm`; `_pace`
  folded into its only caller; dead list-shape guards removed from training status.

## [0.2.0] - 2026-07-23

Fixes from a max-effort code review (PRs #1-#4).

### Fixed

- **Errors are no longer silently swallowed**: auth failures raise a re-login hint
  (and the server picks up fresh tokens on the next call — no restart needed), runtime
  rate limits raise advice that warns *against* re-running login.py, and per-day fetch
  failures are annotated in a footer instead of masquerading as missing data.
- `login.py` detects rate limiting by exception type (the old `"429"` string match
  never fired), no longer falls through to a credential+MFA login when offline or
  rate-limited, and supports `--force` to switch Garmin accounts.
- `activity_type` only accepts Garmin's parent categories (subtype keys like
  `virtual_ride` caused API 400s) and documents the subtype roll-up.
- Sleep HRV/SpO2/resting-HR are read across all key spellings/nesting levels Garmin
  has shipped; fabricated `0` intensity minutes and `-1`/`-2` stress sentinels render
  as missing; legitimate zeros (0:00 awake, 0s in zone, 0h recovery) now display.
- Activity names are escaped for markdown tables; body-composition fallback dates
  convert epoch-ms values.
- Docs: `fastmcp dev inspector` (the 2.x `fastmcp dev` syntax broke on fastmcp 3),
  Windows-valid `py` commands, GARMINTOKENS env-block requirement for Claude Desktop,
  and accurate token-lifetime wording; removed the inert `.env.example`.

### Changed

- Per-day fetches in daily summary and sleep run concurrently (bounded 4-worker pool):
  a 31-day summary drops from 62 sequential round-trips to a few seconds, with
  fail-fast cancellation on auth/rate-limit errors.
- Dependency pins gained upper bounds (`fastmcp>=3.4,<4`, `garminconnect>=0.3.6,<0.4`)
  so pip installs match the tested environment.

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
