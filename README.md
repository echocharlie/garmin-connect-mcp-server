# garmin-connect-mcp-server

A read-only [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that
gives Claude Desktop access to your Garmin Connect data — daily health metrics, sleep,
activities, training status, and body composition.

> **Non-technical?** Follow the step-by-step [QUICKSTART](QUICKSTART.md) instead.

## Why this exists

Garmin's official APIs (Health API, Activity API) are only available through the
[Garmin Connect Developer Program](https://developer.garmin.com/gc-developer-program/overview/),
which is gated to approved businesses. This server instead uses the well-established
unofficial [`garminconnect`](https://github.com/cyberjunky/python-garminconnect) Python
library, which signs in with your own Garmin account using the same OAuth flow as the
official Garmin Connect mobile app. No developer program membership, no API keys — you
log in once and the long-lived tokens refresh themselves on use.

Unlike most Garmin MCP servers (which expose 60–110 thin endpoint wrappers), this one
follows [Anthropic's tool-design guidance](https://www.anthropic.com/engineering/writing-tools-for-agents):
six consolidated, purpose-built tools that return compact tables designed for an LLM's
context window.

## Tools

| Tool | What it returns |
|---|---|
| `garmin_get_daily_summary` | Per-day steps, resting HR, overnight HRV + status, Body Battery high/low, stress, intensity minutes, active calories (≤31 days/call) |
| `garmin_get_sleep` | Per-night sleep score, quality, stage durations (deep/light/REM/awake), overnight HRV, SpO2, resting HR (≤31 days/call) |
| `garmin_list_activities` | Activity list with IDs, distance, duration, HR, pace/speed, elevation, training effect; filterable by type (≤90 days/call) |
| `garmin_get_activity_detail` | One activity in depth: pace/power/cadence/calories, plus lap splits and HR-zone breakdown in `detailed` mode |
| `garmin_get_training_status` | Training readiness, training status, acute load, VO2max, HRV status, and 5K/10K/half/marathon race predictions in one call |
| `garmin_get_body_composition` | Weight, body fat %, muscle mass, body water, BMI from a Garmin Index scale or manual entries (≤90 days/call) |

All tools are **read-only** and marked with `readOnlyHint` — nothing is ever written to
your Garmin account. Tools degrade gracefully: an account with no watch data returns
clearly-empty tables rather than errors (activity-only accounts, e.g. from a Tacx
trainer, still get full activity data).

## Requirements

- Python 3.12+ (required by `garminconnect` 0.3.x)
- A free [Garmin Connect](https://connect.garmin.com) account (no device required to
  test auth; data appears once a device or app syncs to the account)
- [Claude Desktop](https://claude.ai/download) to use the tools (optional for development)

## Install

With [uv](https://docs.astral.sh/uv/) (recommended):

```bash
uv sync
```

Without uv (plain venv + pip) — macOS/Linux:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Windows (PowerShell):

```powershell
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

Both paths create the environment in `.venv/`, so the Claude Desktop config below is
identical either way.

## Authenticate (one time)

```bash
uv run python login.py            # or: .venv/bin/python login.py
```

Enter your Garmin email and password (plus MFA code if enabled). OAuth tokens are saved
to `~/.garminconnect` and refresh themselves on use. **Your password is never stored** —
only the tokens are. Re-run the same command whenever tokens expire, or with `--force`
to switch to a different Garmin account.

To store tokens somewhere else, set the `GARMINTOKENS` env var — but note it must then
be set in **both** places: in your shell when running `login.py`, and in the Claude
Desktop config's `env` block (GUI apps don't inherit your shell environment):

```json
"garmin": {
  "command": "...",
  "args": ["..."],
  "env": { "GARMINTOKENS": "/path/to/tokens" }
}
```

## Test locally (optional)

```bash
uv run fastmcp dev inspector server.py      # or: .venv/bin/fastmcp dev inspector server.py
```

This opens the MCP Inspector in your browser to exercise each tool by hand.

## Install in Claude Desktop

> Prefer not to hand-edit JSON? The [QUICKSTART](QUICKSTART.md) has a copy-paste
> prompt that asks Claude (Claude Code, or Claude Desktop with file access) to write
> this config for you.

Edit `claude_desktop_config.json`:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

(Claude Desktop → Settings → Developer → Edit Config opens it for you.) Add:

```json
{
  "mcpServers": {
    "garmin": {
      "command": "/ABSOLUTE/PATH/TO/garmin-connect-mcp-server/.venv/bin/python",
      "args": ["/ABSOLUTE/PATH/TO/garmin-connect-mcp-server/server.py"]
    }
  }
}
```

On Windows, `command` is `C:\\...\\garmin-connect-mcp-server\\.venv\\Scripts\\python.exe`.
No `env` block or secrets are needed — auth comes from the token store. **Fully quit and
reopen Claude Desktop** (it reads the config only on launch), then try:
*"What were my Garmin workouts this month?"*

## Troubleshooting

- **`429` / rate limited during login** — Garmin rate-limits its SSO endpoint by IP.
  Don't retry in a loop; wait 30–60 minutes or switch networks (a phone hotspot changes
  your IP) and run `login.py` again.
- **Authentication failed / token errors** — re-run the login script
  (`uv run python login.py` or `.venv/bin/python login.py`); tokens die if you change
  your Garmin password or Garmin revokes them. The running server picks up fresh
  tokens on the next tool call — no restart needed.
- **Tools return empty tables / all `-`** — the account has no synced data for that
  range. Health metrics (sleep, HRV, Body Battery, training status) require a Garmin
  watch; activities can come from any source that syncs to Garmin Connect (trainer,
  Zwift, phone app).
- **Login suddenly breaks for everyone** — Garmin occasionally changes their SSO flow,
  which temporarily breaks the unofficial library until it's patched. Update with
  `uv sync --upgrade` (or `.venv/bin/pip install -U garminconnect`) and retry.
- **Claude Desktop doesn't show the tools** — check the config file for JSON errors
  (a trailing comma breaks the whole file), verify both paths are absolute and the
  `.venv` exists, then fully quit and reopen the app.

## How it works

```
Claude Desktop ──stdio──> server.py (FastMCP, 6 read-only tools)
                              │
                              ├── reads OAuth tokens from ~/.garminconnect
                              │      (written once by login.py; auto-refreshed)
                              │
                              └── garminconnect (unofficial lib, >= 0.3.6)
                                     └── Garmin Connect private web API
```

- [server.py](server.py) — the MCP server; never sees your password, only reads tokens.
- [login.py](login.py) — one-time interactive sign-in (handles MFA); saves tokens.

## Fair warning

This uses Garmin Connect's private web API via your personal account — technically a
gray area under Garmin's ToS, though it's the same approach used for years by
Home Assistant integrations and many other community projects without issue. Use
reasonable request volumes and your own account. This project is not affiliated with
or endorsed by Garmin.

## Development

```bash
uv run python -m compileall server.py login.py   # syntax check
uv run fastmcp dev inspector server.py           # manual tool testing
```

Tool design notes: tools are namespaced `garmin_*` to compose cleanly with sibling
health MCP servers (Oura, Strava, …); outputs are compact markdown tables (roughly
40 tokens/day-row); date ranges are capped per call with actionable error messages.

## License

[MIT](LICENSE)
