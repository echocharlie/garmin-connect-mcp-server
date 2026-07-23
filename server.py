"""Garmin Connect MCP server — read-only access to health, training, and activity data.

Auth: run `login.py` once to store Garmin OAuth tokens at ~/.garminconnect (or $GARMINTOKENS).
The server only reads that token store; it never sees your password.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Annotated, Literal

from fastmcp import FastMCP
from pydantic import Field

mcp = FastMCP("garmin-connect")

TOKEN_DIR = os.path.expanduser(os.environ.get("GARMINTOKENS", "~/.garminconnect"))
LOGIN_HINT = (
    "No valid Garmin Connect tokens found. Ask the user to run `python login.py` in the "
    "garmin-connect-mcp-server directory to sign in (handles MFA), then retry."
)

_garmin = None


def _client():
    """Return a logged-in Garmin client, reusing tokens from the token store."""
    global _garmin
    if _garmin is not None:
        return _garmin
    try:
        from garminconnect import Garmin
    except ImportError as e:
        raise RuntimeError(
            "The 'garminconnect' package is not installed. Run `uv sync` (or `pip install garminconnect`)."
        ) from e
    try:
        client = Garmin()
        client.login(TOKEN_DIR)
    except Exception as e:
        raise RuntimeError(f"{LOGIN_HINT} (underlying error: {type(e).__name__}: {e})") from e
    _garmin = client
    return _garmin


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
    """Seconds -> 'H:MM' string, or '-' if missing."""
    if not seconds:
        return "-"
    seconds = int(seconds)
    return f"{seconds // 3600}:{(seconds % 3600) // 60:02d}"


def _hms(seconds) -> str:
    """Seconds -> 'H:MM:SS' string, or '-' if missing."""
    if not seconds:
        return "-"
    seconds = int(seconds)
    return f"{seconds // 3600}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def _v(x, fmt: str = "{}") -> str:
    """Format a possibly-missing value; '-' for None."""
    return fmt.format(x) if x is not None else "-"


def _n(x) -> str:
    """Format a count-like metric (HR, cadence, power, kcal): int, with 0/None as '-'.

    Garmin reports 0.0 for e.g. avg HR when no sensor was worn, so 0 means missing.
    """
    return str(int(round(x))) if x else "-"


def _pace_or_speed(type_key: str, speed_mps) -> str:
    """Pace for running types, km/h otherwise."""
    if "running" in (type_key or ""):
        return _pace(speed_mps)
    return f"{speed_mps * 3.6:.1f}km/h" if speed_mps else "-"


def _pace(speed_mps) -> str:
    """m/s -> 'M:SS/km' pace string."""
    if not speed_mps:
        return "-"
    sec_per_km = 1000 / speed_mps
    return f"{int(sec_per_km // 60)}:{int(sec_per_km % 60):02d}/km"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True})
def garmin_get_daily_summary(
    start_date: Annotated[
        str | None, Field(description="ISO start date (inclusive), e.g. '2026-07-01'. Default: 6 days before end_date.")
    ] = None,
    end_date: Annotated[
        str | None, Field(description="ISO end date (inclusive). Default: today.")
    ] = None,
) -> str:
    """Day-by-day Garmin health metrics as a compact table (max 31 days, default last 7).

    Columns: date, steps, resting_hr (bpm), hrv_avg (ms overnight), hrv_status
    (balanced/unbalanced/low), bb_high/bb_low (Body Battery 0-100), stress_avg (0-100),
    intensity_min (moderate + 2x vigorous), active_kcal.
    For sleep detail use garmin_get_sleep; for workouts use garmin_list_activities.
    """
    start, end = _parse_range(start_date, end_date, default_days=7, max_days=31)
    g = _client()
    rows = [
        "date | steps | resting_hr | hrv_avg | hrv_status | bb_high | bb_low | stress_avg | intensity_min | active_kcal",
        "---|---|---|---|---|---|---|---|---|---",
    ]
    for d in _days(start, end):
        ds = d.isoformat()
        try:
            s = g.get_user_summary(ds) or {}
        except Exception:
            s = {}
        try:
            hrv = (g.get_hrv_data(ds) or {}).get("hrvSummary") or {}
        except Exception:
            hrv = {}
        moderate = s.get("moderateIntensityMinutes") or 0
        vigorous = s.get("vigorousIntensityMinutes") or 0
        rows.append(
            f"{ds} | {_v(s.get('totalSteps'))} | {_v(s.get('restingHeartRate'))} | "
            f"{_v(hrv.get('lastNightAvg'))} | {_v(hrv.get('status'))} | "
            f"{_v(s.get('bodyBatteryHighestValue'))} | {_v(s.get('bodyBatteryLowestValue'))} | "
            f"{_v(s.get('averageStressLevel'))} | {moderate + 2 * vigorous} | "
            f"{_n(s.get('activeKilocalories'))}"
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
    g = _client()
    rows = [
        "date | score | quality | duration | deep | light | rem | awake | overnight_hrv | spo2_avg | resting_hr",
        "---|---|---|---|---|---|---|---|---|---|---",
    ]
    for d in _days(start, end):
        ds = d.isoformat()
        try:
            data = g.get_sleep_data(ds) or {}
        except Exception:
            data = {}
        dto = data.get("dailySleepDTO") or {}
        scores = (dto.get("sleepScores") or {}).get("overall") or {}
        rows.append(
            f"{ds} | {_v(scores.get('value'))} | {_v(scores.get('qualifierKey'))} | "
            f"{_hm(dto.get('sleepTimeSeconds'))} | {_hm(dto.get('deepSleepSeconds'))} | "
            f"{_hm(dto.get('lightSleepSeconds'))} | {_hm(dto.get('remSleepSeconds'))} | "
            f"{_hm(dto.get('awakeSleepSeconds'))} | {_v(dto.get('avgOvernightHrv'))} | "
            f"{_v(dto.get('averageSpO2Value'))} | {_v(dto.get('restingHeartRate'))}"
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
        str | None,
        Field(
            description="Garmin type key filter, e.g. 'running', 'cycling', 'swimming', "
            "'strength_training', 'walking'. Omit for all types."
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
    g = _client()
    try:
        acts = g.get_activities_by_date(start.isoformat(), end.isoformat(), activity_type) or []
    except Exception as e:
        raise RuntimeError(f"Failed to fetch activities: {type(e).__name__}: {e}. {LOGIN_HINT}") from e
    if not acts:
        return f"No activities between {start} and {end}" + (f" of type '{activity_type}'." if activity_type else ".")
    total = len(acts)
    acts = acts[:limit]
    rows = [
        "activity_id | date | type | name | distance_km | duration | avg_hr | max_hr | pace_or_speed | elev_gain_m | aerobic_te | anaerobic_te",
        "---|---|---|---|---|---|---|---|---|---|---|---",
    ]
    for a in acts:
        dist = a.get("distance")
        type_key = (a.get("activityType") or {}).get("typeKey", "-")
        pace = _pace_or_speed(type_key, a.get("averageSpeed"))
        rows.append(
            f"{a.get('activityId', '-')} | {str(a.get('startTimeLocal', '-'))[:10]} | {type_key} | "
            f"{a.get('activityName', '-')} | {f'{dist / 1000:.2f}' if dist else '-'} | "
            f"{_hm(a.get('duration'))} | {_n(a.get('averageHR'))} | {_n(a.get('maxHR'))} | {pace} | "
            f"{_v(a.get('elevationGain'), '{:.0f}')} | {_v(a.get('aerobicTrainingEffect'), '{:.1f}')} | "
            f"{_v(a.get('anaerobicTrainingEffect'), '{:.1f}')}"
        )
    if total > limit:
        rows.append(f"\nShowing {limit} of {total}; narrow the date range or raise limit to see more.")
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
    g = _client()
    try:
        a = g.get_activity(activity_id) or {}
    except Exception as e:
        raise RuntimeError(
            f"Could not fetch activity {activity_id}: {type(e).__name__}: {e}. "
            "Check the ID via garmin_list_activities."
        ) from e
    s = a.get("summaryDTO") or {}
    type_key = ((a.get("activityTypeDTO") or {}).get("typeKey")) or "-"
    dist = s.get("distance")
    lines = [
        f"# {a.get('activityName', 'Activity')} ({type_key}) — id {activity_id}",
        f"start: {s.get('startTimeLocal', '-')}",
        f"distance_km: {f'{dist / 1000:.2f}' if dist else '-'} | duration: {_hms(s.get('duration'))} | moving: {_hms(s.get('movingDuration'))}",
        f"avg_hr: {_n(s.get('averageHR'))} | max_hr: {_n(s.get('maxHR'))} | calories: {_n(s.get('calories'))}",
        f"pace_or_speed: {_pace_or_speed(type_key, s.get('averageSpeed'))}",
        f"elev_gain_m: {_v(s.get('elevationGain'), '{:.0f}')} | elev_loss_m: {_v(s.get('elevationLoss'), '{:.0f}')}",
        f"avg_cadence: {_n(s.get('averageRunCadence') or s.get('averageBikeCadence'))} | "
        f"avg_power_w: {_n(s.get('averagePower'))} | norm_power_w: {_n(s.get('normalizedPower'))}",
        f"aerobic_te: {_v(s.get('trainingEffect'), '{:.1f}')} | anaerobic_te: {_v(s.get('anaerobicTrainingEffect'), '{:.1f}')} | "
        f"training_load: {_v(s.get('activityTrainingLoad'), '{:.0f}')}",
    ]
    if response_format == "detailed":
        try:
            zones = g.get_activity_hr_in_timezones(activity_id) or []
        except Exception:
            zones = []
        if any(z.get("secsInZone") for z in zones):
            lines += ["", "## Time in HR zones", "zone | time | low_bpm", "---|---|---"]
            for z in zones:
                lines.append(f"Z{z.get('zoneNumber', '?')} | {_hm(z.get('secsInZone'))} | {_v(z.get('zoneLowBoundary'))}")
        try:
            splits = (g.get_activity_splits(activity_id) or {}).get("lapDTOs") or []
        except Exception:
            splits = []
        if splits:
            lines += ["", "## Splits (laps)", "lap | distance_km | duration | avg_hr | pace_or_speed | elev_gain_m", "---|---|---|---|---|---"]
            for i, lap in enumerate(splits, 1):
                ld = lap.get("distance")
                lines.append(
                    f"{i} | {f'{ld / 1000:.2f}' if ld else '-'} | {_hms(lap.get('duration'))} | "
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
    g = _client()
    today = date.today().isoformat()
    lines = [f"# Garmin training snapshot — {today}"]

    try:
        tr = g.get_training_readiness(today)
        tr = (tr[0] if isinstance(tr, list) and tr else tr) or {}
        if tr.get("score") is not None:
            line = f"training_readiness: {tr['score']} ({_v(tr.get('level'))})"
            if tr.get("recoveryTime"):
                line += f" | recovery_time_hr: {round(tr['recoveryTime'] / 60, 1)}"
            lines.append(line)
    except Exception:
        lines.append("training_readiness: unavailable (device may not support it)")

    try:
        ts = g.get_training_status(today) or {}
        latest = (ts.get("mostRecentTrainingStatus") or {}).get("latestTrainingStatusData") or {}
        for dev in latest.values():
            acute = dev.get("acuteTrainingLoadDTO") or {}
            lines.append(
                f"training_status: {_v(dev.get('trainingStatusFeedbackPhrase') or dev.get('trainingStatus'))} | "
                f"acute_load: {_v(acute.get('acuteTrainingLoad') if isinstance(acute, dict) else None)}"
            )
            break
        vo2 = (ts.get("mostRecentVO2Max") or {}).get("generic") or {}
        if vo2.get("vo2MaxPreciseValue") or vo2.get("vo2MaxValue"):
            lines.append(f"vo2max: {vo2.get('vo2MaxPreciseValue') or vo2.get('vo2MaxValue')}")
    except Exception:
        lines.append("training_status: unavailable")

    try:
        hrv = (g.get_hrv_data(today) or {}).get("hrvSummary") or {}
        if hrv:
            lines.append(
                f"hrv: last_night_avg {_v(hrv.get('lastNightAvg'))}ms | "
                f"weekly_avg {_v(hrv.get('weeklyAvg'))}ms | status {_v(hrv.get('status'))}"
            )
    except Exception:
        lines.append("hrv: unavailable")

    try:
        rp = g.get_race_predictions() or {}
        if isinstance(rp, list):
            rp = rp[0] if rp else {}
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
    except Exception:
        pass

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
    g = _client()
    try:
        data = g.get_body_composition(start.isoformat(), end.isoformat()) or {}
    except Exception as e:
        raise RuntimeError(f"Failed to fetch body composition: {type(e).__name__}: {e}. {LOGIN_HINT}") from e
    entries = data.get("dateWeightList") or []
    if not entries:
        return f"No body composition entries between {start} and {end}."
    rows = [
        "date | weight_kg | body_fat_pct | muscle_mass_kg | body_water_pct | bmi",
        "---|---|---|---|---|---",
    ]
    for e in entries:
        weight = e.get("weight")
        muscle = e.get("muscleMass")
        rows.append(
            f"{e.get('calendarDate', str(e.get('date', '-'))[:10])} | "
            f"{f'{weight / 1000:.1f}' if weight else '-'} | {_v(e.get('bodyFat'), '{:.1f}')} | "
            f"{f'{muscle / 1000:.1f}' if muscle else '-'} | {_v(e.get('bodyWater'), '{:.1f}')} | "
            f"{_v(e.get('bmi'), '{:.1f}')}"
        )
    return "\n".join(rows)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
