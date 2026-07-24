"""Garmin Connect MCP server — read-only access to health, training, and activity data.

Auth: run `login.py` once to store Garmin OAuth tokens at ~/.garminconnect (or $GARMINTOKENS).
The server only reads that token store; it never sees your password.
"""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Annotated, Literal

from fastmcp import FastMCP
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)
from pydantic import Field

mcp = FastMCP("garmin-connect")

TOKEN_DIR = os.path.expanduser(os.environ.get("GARMINTOKENS", "~/.garminconnect"))
LOGIN_HINT = (
    "Garmin Connect authentication failed (missing/expired tokens). Ask the user to run "
    "the login script in the garmin-connect-mcp-server directory — `uv run python login.py` "
    "or `.venv/bin/python login.py` — then simply retry this tool; no restart is needed."
)
RATE_LIMIT_HINT = (
    "Garmin is rate limiting requests from this IP. Wait 30-60 minutes and retry. "
    "Do NOT re-run login.py — fresh login attempts extend the block."
)

_garmin = None
_garmin_lock = threading.Lock()

_RAISE = object()


def _client() -> Garmin:
    """Return a logged-in Garmin client, reusing tokens from the token store."""
    global _garmin
    with _garmin_lock:
        if _garmin is None:
            client = Garmin()
            try:
                client.login(TOKEN_DIR)
            except GarminConnectTooManyRequestsError as e:
                raise RuntimeError(RATE_LIMIT_HINT) from e
            except Exception as e:
                raise RuntimeError(f"{LOGIN_HINT} (underlying error: {type(e).__name__}: {e})") from e
            _garmin = client
        return _garmin


def _drop_client() -> None:
    """Forget the cached client so the next call re-reads the token store."""
    global _garmin
    with _garmin_lock:
        _garmin = None


def _api(method: str, *args, default=_RAISE, **kwargs):
    """Call a Garmin client method with auth-aware error translation.

    Auth errors drop the cached client (so a re-run of login.py takes effect without a
    restart) and always raise, as do rate limits. Other errors raise a labeled
    RuntimeError, or return `default` when one is given (for tolerant per-item fetches).
    """
    g = _client()
    try:
        return getattr(g, method)(*args, **kwargs)
    except GarminConnectAuthenticationError as e:
        _drop_client()
        raise RuntimeError(f"{method} failed: {LOGIN_HINT}") from e
    except GarminConnectTooManyRequestsError as e:
        raise RuntimeError(f"{method} aborted: {RATE_LIMIT_HINT}") from e
    except Exception as e:
        if default is not _RAISE:
            return default
        raise RuntimeError(
            f"{method} failed: {type(e).__name__}: {e}. This is not an authentication "
            "problem — do not re-run login.py; retry later or narrow the request."
        ) from e


_MAX_FETCH_WORKERS = 4


def _api_per_day(method: str, dates: list[str]) -> dict[str, object]:
    """Fetch `method` for many dates concurrently (bounded workers).

    Returns {date: payload-or-None}; None marks a non-auth failure for that day.
    Auth/rate-limit errors cancel the remaining fetches and propagate.
    """
    with ThreadPoolExecutor(max_workers=_MAX_FETCH_WORKERS) as ex:
        futures = {ds: ex.submit(_api, method, ds, default=None) for ds in dates}
        try:
            return {ds: f.result() for ds, f in futures.items()}
        except RuntimeError:
            ex.shutdown(cancel_futures=True)
            raise


def _parse_range(
    start_date: str | None,
    end_date: str | None,
    default_days: int,
    max_days: int,
) -> tuple[date, date]:
    """Validate an ISO date range with defaults, returning (start, end) inclusive."""
    try:
        end = date.fromisoformat(end_date) if end_date else date.today()
        start = date.fromisoformat(start_date) if start_date else end - timedelta(days=default_days - 1)
    except ValueError as e:
        raise RuntimeError(
            f"Invalid date: {e}. Use ISO format, e.g. start_date='2026-07-01', end_date='2026-07-07'."
        ) from e
    if start > end:
        raise RuntimeError(f"start_date {start} is after end_date {end}.")
    if (end - start).days + 1 > max_days:
        raise RuntimeError(
            f"Range {start}..{end} is {(end - start).days + 1} days; max is {max_days}. "
            "Call multiple times with smaller ranges."
        )
    return start, end


def _days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _hm(seconds) -> str:
    """Seconds -> 'H:MM' string, or '-' if missing. 0 is a real value (0:00)."""
    if seconds is None:
        return "-"
    seconds = int(seconds)
    return f"{seconds // 3600}:{(seconds % 3600) // 60:02d}"


def _hms(seconds) -> str:
    """Seconds -> 'H:MM:SS' string, or '-' if missing. 0 is a real value (0:00:00)."""
    if seconds is None:
        return "-"
    return f"{_hm(seconds)}:{int(seconds) % 60:02d}"


def _km(meters) -> str:
    """Meters -> kilometers with 2 decimals, or '-' if missing/zero."""
    return f"{meters / 1000:.2f}" if meters else "-"


def _kg(grams) -> str:
    """Grams -> kilograms with 1 decimal, or '-' if missing/zero."""
    return f"{grams / 1000:.1f}" if grams else "-"


def _table(*cols: str) -> list[str]:
    """Markdown table header + separator rows derived from one column list."""
    return [" | ".join(cols), "|".join(["---"] * len(cols))]


def _cell(x) -> str:
    """Sanitize free-text (e.g. activity names) for markdown table cells and headings."""
    return str(x).replace("|", "\\|").replace("\n", " ").replace("\r", " ") if x is not None else "-"


def _first(*vals):
    """First value that is not None (0 is a real value)."""
    for v in vals:
        if v is not None:
            return v
    return None


def _v(x, fmt: str = "{}") -> str:
    """Format a possibly-missing value; '-' for None."""
    return fmt.format(x) if x is not None else "-"


def _n(x) -> str:
    """Format a count-like metric (HR, cadence, power, kcal): int, with 0/None as '-'.

    Garmin reports 0.0 for e.g. avg HR when no sensor was worn, so 0 means missing.
    """
    return str(int(round(x))) if x else "-"


def _pace_or_speed(type_key: str, speed_mps) -> str:
    """Pace (M:SS/km) for running types, km/h otherwise; '-' if missing."""
    if not speed_mps:
        return "-"
    if "running" in (type_key or ""):
        sec_per_km = 1000 / speed_mps
        return f"{int(sec_per_km // 60)}:{int(sec_per_km % 60):02d}/km"
    return f"{speed_mps * 3.6:.1f}km/h"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True})
def garmin_get_daily_summary(
    start_date: Annotated[
        str | None, Field(description="ISO start date (inclusive), e.g. '2026-07-01'. Default: 6 days before end_date.")
    ] = None,
    end_date: Annotated[
        str | None,
        Field(description="ISO end date (inclusive). Default: today in the SERVER's local timezone — near midnight this can differ from the Garmin account's calendar day; pass explicit dates if it matters."),
    ] = None,
) -> str:
    """Day-by-day Garmin health metrics as a compact table (max 31 days, default last 7).

    Columns: date, steps, resting_hr (bpm), hrv_avg (ms overnight), hrv_status
    (balanced/unbalanced/low), bb_high/bb_low (Body Battery 0-100), stress_avg (0-100),
    intensity_min (moderate + 2x vigorous), active_kcal.
    For sleep detail use garmin_get_sleep; for workouts use garmin_list_activities.
    """
    start, end = _parse_range(start_date, end_date, default_days=7, max_days=31)
    rows = _table("date", "steps", "resting_hr", "hrv_avg", "hrv_status", "bb_high", "bb_low",
                  "stress_avg", "intensity_min", "active_kcal")
    dates = [d.isoformat() for d in _days(start, end)]
    summaries = _api_per_day("get_user_summary", dates)
    hrv_by_day = _api_per_day("get_hrv_data", dates)
    failed: list[str] = []
    for ds in dates:
        s = summaries[ds]
        if s is None:
            failed.append(ds)
            s = {}
        hrv = (hrv_by_day[ds] or {}).get("hrvSummary") or {}
        moderate = s.get("moderateIntensityMinutes")
        vigorous = s.get("vigorousIntensityMinutes")
        # Only compute when Garmin reported at least one component; otherwise a failed
        # or empty day would fabricate a plausible-looking 0.
        intensity = (moderate or 0) + 2 * (vigorous or 0) if (moderate is not None or vigorous is not None) else None
        stress = s.get("averageStressLevel")
        if stress is not None and stress < 0:
            stress = None  # Garmin uses -1/-2 as "insufficient data" sentinels
        rows.append(
            f"{ds} | {_v(s.get('totalSteps'))} | {_v(s.get('restingHeartRate'))} | "
            f"{_v(hrv.get('lastNightAvg'))} | {_v(hrv.get('status'))} | "
            f"{_v(s.get('bodyBatteryHighestValue'))} | {_v(s.get('bodyBatteryLowestValue'))} | "
            f"{_v(stress)} | {_v(intensity)} | "
            f"{_n(s.get('activeKilocalories'))}"
        )
    if failed:
        rows.append(
            f"\nNote: fetch failed (non-auth error) for {len(failed)} day(s): {', '.join(failed)} — "
            "their '-' cells mean 'fetch failed', not 'no data'."
        )
    return "\n".join(rows)


@mcp.tool(annotations={"readOnlyHint": True})
def garmin_get_sleep(
    start_date: Annotated[
        str | None, Field(description="ISO start date (inclusive). Default: 6 days before end_date.")
    ] = None,
    end_date: Annotated[
        str | None,
        Field(description="ISO end date (inclusive). Default: today. Each date refers to the night ENDING that morning."),
    ] = None,
) -> str:
    """Garmin sleep data per night as a compact table (max 31 days, default last 7).

    Columns: date (wake-up morning), score (0-100), quality, duration, deep, light, rem,
    awake (H:MM), overnight_hrv (ms), spo2_avg (%), resting_hr (bpm).
    Note: if the user also wears an Oura ring, oura_* tools report the same nights and
    may differ slightly; say which source you're citing.
    """
    start, end = _parse_range(start_date, end_date, default_days=7, max_days=31)
    rows = _table("date", "score", "quality", "duration", "deep", "light", "rem", "awake",
                  "overnight_hrv", "spo2_avg", "resting_hr")
    dates = [d.isoformat() for d in _days(start, end)]
    sleep_by_day = _api_per_day("get_sleep_data", dates)
    failed: list[str] = []
    for ds in dates:
        data = sleep_by_day[ds]
        if data is None:
            failed.append(ds)
            data = {}
        dto = data.get("dailySleepDTO") or {}
        scores = (dto.get("sleepScores") or {}).get("overall") or {}
        # Garmin has shipped these under multiple names and nesting levels
        # (dailySleepDTO.avgOvernightHrv vs avgSleepHRV vs top-level siblings).
        overnight_hrv = _first(
            dto.get("avgOvernightHrv"), dto.get("avgSleepHRV"),
            data.get("avgOvernightHrv"), data.get("avgSleepHRV"),
        )
        spo2 = _first(
            dto.get("averageSpO2Value"), dto.get("avgSpO2"),
            data.get("averageSpO2Value"), data.get("avgSpO2"), data.get("averageSpO2"),
        )
        resting_hr = _first(dto.get("restingHeartRate"), data.get("restingHeartRate"))
        rows.append(
            f"{ds} | {_v(scores.get('value'))} | {_v(scores.get('qualifierKey'))} | "
            f"{_hm(dto.get('sleepTimeSeconds'))} | {_hm(dto.get('deepSleepSeconds'))} | "
            f"{_hm(dto.get('lightSleepSeconds'))} | {_hm(dto.get('remSleepSeconds'))} | "
            f"{_hm(dto.get('awakeSleepSeconds'))} | {_v(overnight_hrv)} | "
            f"{_v(spo2)} | {_v(resting_hr)}"
        )
    if failed:
        rows.append(
            f"\nNote: fetch failed (non-auth error) for {len(failed)} night(s): {', '.join(failed)} — "
            "their '-' cells mean 'fetch failed', not 'no data'."
        )
    return "\n".join(rows)


@mcp.tool(annotations={"readOnlyHint": True})
def garmin_list_activities(
    start_date: Annotated[
        str | None, Field(description="ISO start date (inclusive). Default: 29 days before end_date.")
    ] = None,
    end_date: Annotated[
        str | None, Field(description="ISO end date (inclusive). Default: today.")
    ] = None,
    activity_type: Annotated[
        Literal["cycling", "running", "swimming", "multi_sport", "fitness_equipment", "hiking", "walking", "other"] | None,
        Field(
            description="Filter by Garmin PARENT category only — subtypes are rejected by the API. "
            "Subtypes roll up: virtual_ride/mountain_biking -> 'cycling'; treadmill/trail running -> "
            "'running'; strength training/indoor cardio -> 'fitness_equipment'. Omit for all types."
        ),
    ] = None,
    limit: Annotated[int, Field(ge=1, le=100, description="Max activities to return (newest first).")] = 20,
) -> str:
    """List Garmin activities in a date range as a compact table (max 90 days, default last 30).

    Columns: activity_id (for garmin_get_activity_detail), date, type, name, distance_km,
    duration (H:MM), avg_hr, max_hr, pace_or_speed, elev_gain_m, aerobic_te (training
    effect 0-5), anaerobic_te.
    """
    start, end = _parse_range(start_date, end_date, default_days=30, max_days=90)
    # Single-page fetch of limit+1 (to detect truncation) instead of the library's
    # get_activities_by_date, which paginates the ENTIRE range 20 at a time and would
    # make us throw away everything past `limit`. Same endpoint and params the library
    # uses internally.
    params = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "start": "0",
        "limit": str(limit + 1),
    }
    if activity_type:
        params["activityType"] = activity_type
    url = getattr(_client(), "garmin_connect_activities", "/activitylist-service/activities/search/activities")
    acts = _api("connectapi", url, params=params) or []
    if not acts:
        return f"No activities between {start} and {end}" + (f" of type '{activity_type}'." if activity_type else ".")
    truncated = len(acts) > limit
    acts = acts[:limit]
    rows = _table("activity_id", "date", "type", "name", "distance_km", "duration", "avg_hr",
                  "max_hr", "pace_or_speed", "elev_gain_m", "aerobic_te", "anaerobic_te")
    for a in acts:
        type_key = (a.get("activityType") or {}).get("typeKey", "-")
        pace = _pace_or_speed(type_key, a.get("averageSpeed"))
        rows.append(
            f"{a.get('activityId', '-')} | {str(a.get('startTimeLocal', '-'))[:10]} | {type_key} | "
            f"{_cell(a.get('activityName'))} | {_km(a.get('distance'))} | "
            f"{_hm(a.get('duration'))} | {_n(a.get('averageHR'))} | {_n(a.get('maxHR'))} | {pace} | "
            f"{_v(a.get('elevationGain'), '{:.0f}')} | {_v(a.get('aerobicTrainingEffect'), '{:.1f}')} | "
            f"{_v(a.get('anaerobicTrainingEffect'), '{:.1f}')}"
        )
    if truncated:
        rows.append(f"\nShowing the newest {limit}; more exist in this range — narrow it or raise limit.")
    return "\n".join(rows)


@mcp.tool(annotations={"readOnlyHint": True})
def garmin_get_activity_detail(
    activity_id: Annotated[int, Field(description="Numeric activity ID from garmin_list_activities.")],
    response_format: Annotated[
        Literal["concise", "detailed"],
        Field(description="'concise' = summary metrics only; 'detailed' adds per-lap splits and HR-zone time."),
    ] = "concise",
) -> str:
    """Deep-dive a single Garmin activity: distance, time, HR, pace/speed, cadence, power,
    elevation, calories, training effect — plus lap splits and heart-rate-zone breakdown
    in 'detailed' mode. Get activity_id from garmin_list_activities first.
    """
    a = _api("get_activity", activity_id) or {}
    if not a:
        raise RuntimeError(
            f"Activity {activity_id} returned no data. Check the ID via garmin_list_activities."
        )
    s = a.get("summaryDTO") or {}
    type_key = ((a.get("activityTypeDTO") or {}).get("typeKey")) or "-"
    lines = [
        f"# {_cell(a.get('activityName') or 'Activity')} ({type_key}) — id {activity_id}",
        f"start: {s.get('startTimeLocal', '-')}",
        f"distance_km: {_km(s.get('distance'))} | duration: {_hms(s.get('duration'))} | moving: {_hms(s.get('movingDuration'))}",
        f"avg_hr: {_n(s.get('averageHR'))} | max_hr: {_n(s.get('maxHR'))} | calories: {_n(s.get('calories'))}",
        f"pace_or_speed: {_pace_or_speed(type_key, s.get('averageSpeed'))}",
        f"elev_gain_m: {_v(s.get('elevationGain'), '{:.0f}')} | elev_loss_m: {_v(s.get('elevationLoss'), '{:.0f}')}",
        f"avg_cadence: {_n(s.get('averageRunCadence') or s.get('averageBikeCadence'))} | "
        f"avg_power_w: {_n(s.get('averagePower'))} | norm_power_w: {_n(s.get('normalizedPower'))}",
        f"aerobic_te: {_v(s.get('trainingEffect'), '{:.1f}')} | anaerobic_te: {_v(s.get('anaerobicTrainingEffect'), '{:.1f}')} | "
        f"training_load: {_v(s.get('activityTrainingLoad'), '{:.0f}')}",
    ]
    if response_format == "detailed":
        zones = _api("get_activity_hr_in_timezones", activity_id, default=[]) or []
        if any(z.get("secsInZone") for z in zones):
            lines += ["", "## Time in HR zones", *_table("zone", "time", "low_bpm")]
            for z in zones:
                lines.append(f"Z{z.get('zoneNumber', '?')} | {_hm(z.get('secsInZone'))} | {_v(z.get('zoneLowBoundary'))}")
        splits = (_api("get_activity_splits", activity_id, default={}) or {}).get("lapDTOs") or []
        if splits:
            lines += ["", "## Splits (laps)",
                      *_table("lap", "distance_km", "duration", "avg_hr", "pace_or_speed", "elev_gain_m")]
            for i, lap in enumerate(splits, 1):
                lines.append(
                    f"{i} | {_km(lap.get('distance'))} | {_hms(lap.get('duration'))} | "
                    f"{_n(lap.get('averageHR'))} | {_pace_or_speed(type_key, lap.get('averageSpeed'))} | "
                    f"{_v(lap.get('elevationGain'), '{:.0f}')}"
                )
    return "\n".join(lines)


@mcp.tool(annotations={"readOnlyHint": True})
def garmin_get_training_status() -> str:
    """Current Garmin training snapshot in one call: training readiness score, training
    status (e.g. productive/maintaining/strained), acute load, VO2max, HRV status, and
    race time predictions (5K/10K/half/marathon). Use this for 'how is my training going /
    how recovered am I' questions; combine with oura_* readiness for cross-source checks.
    """
    today = date.today().isoformat()
    lines = [f"# Garmin training snapshot — {today}"]

    tr = _api("get_training_readiness", today, default=None)  # library returns list[dict]
    tr = tr[0] if tr else {}
    if tr.get("score") is not None:
        line = f"training_readiness: {tr['score']} ({_v(tr.get('level'))})"
        if tr.get("recoveryTime") is not None:
            line += f" | recovery_time_hr: {round(tr['recoveryTime'] / 60, 1)}"
        lines.append(line)

    ts = _api("get_training_status", today, default=None) or {}
    latest = (ts.get("mostRecentTrainingStatus") or {}).get("latestTrainingStatusData") or {}
    dev = next(iter(latest.values()), None)
    if dev:
        acute = dev.get("acuteTrainingLoadDTO") or {}
        lines.append(
            f"training_status: {_v(dev.get('trainingStatusFeedbackPhrase') or dev.get('trainingStatus'))} | "
            f"acute_load: {_v(acute.get('acuteTrainingLoad'))}"
        )
    vo2 = (ts.get("mostRecentVO2Max") or {}).get("generic") or {}
    if vo2.get("vo2MaxPreciseValue") or vo2.get("vo2MaxValue"):
        lines.append(f"vo2max: {vo2.get('vo2MaxPreciseValue') or vo2.get('vo2MaxValue')}")

    hrv = (_api("get_hrv_data", today, default=None) or {}).get("hrvSummary") or {}
    if hrv:
        lines.append(
            f"hrv: last_night_avg {_v(hrv.get('lastNightAvg'))}ms | "
            f"weekly_avg {_v(hrv.get('weeklyAvg'))}ms | status {_v(hrv.get('status'))}"
        )

    rp = _api("get_race_predictions", default=None) or {}  # no-arg form returns one dict
    preds = [
        (label, rp.get(key))
        for label, key in [
            ("5K", "time5K"),
            ("10K", "time10K"),
            ("half", "timeHalfMarathon"),
            ("marathon", "timeMarathon"),
        ]
        if rp.get(key)
    ]
    if preds:
        lines.append("race_predictions: " + " | ".join(f"{lbl} {_hms(t)}" for lbl, t in preds))

    if len(lines) == 1:
        return (
            f"# Garmin training snapshot — {today}\n"
            "No training data available. This account has no recent device syncs — training "
            "readiness, status, VO2max, and race predictions require a compatible Garmin watch. "
            "Activity history may still exist: try garmin_list_activities."
        )
    return "\n".join(lines)


@mcp.tool(annotations={"readOnlyHint": True})
def garmin_get_body_composition(
    start_date: Annotated[
        str | None, Field(description="ISO start date (inclusive). Default: 29 days before end_date.")
    ] = None,
    end_date: Annotated[
        str | None, Field(description="ISO end date (inclusive). Default: today.")
    ] = None,
) -> str:
    """Body composition entries (Garmin Index scale or manual) as a table (max 90 days,
    default last 30). Columns: date, weight_kg, body_fat_pct, muscle_mass_kg,
    body_water_pct, bmi. Only days with a measurement appear.
    """
    start, end = _parse_range(start_date, end_date, default_days=30, max_days=90)
    data = _api("get_body_composition", start.isoformat(), end.isoformat()) or {}
    entries = data.get("dateWeightList") or []
    if not entries:
        return f"No body composition entries between {start} and {end}."
    rows = _table("date", "weight_kg", "body_fat_pct", "muscle_mass_kg", "body_water_pct", "bmi")
    for e in entries:
        when = e.get("calendarDate")
        if not when:
            # Fallback 'date' field is epoch milliseconds, not a date string.
            ts = e.get("date")
            when = date.fromtimestamp(ts / 1000).isoformat() if isinstance(ts, (int, float)) else "-"
        rows.append(
            f"{when} | "
            f"{_kg(e.get('weight'))} | {_v(e.get('bodyFat'), '{:.1f}')} | "
            f"{_kg(e.get('muscleMass'))} | {_v(e.get('bodyWater'), '{:.1f}')} | "
            f"{_v(e.get('bmi'), '{:.1f}')}"
        )
    return "\n".join(rows)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
