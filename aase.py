from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date, timedelta

from optimizer import DAYS, SLOTS, optimize_timetable, optimize_whole_timetable


def calendar_day_penalties(events, restricted_as_holiday=False):
    """Return how many calendar-blocked dates occur on each teaching weekday."""
    penalties = {day: 0 for day in DAYS}
    for event in events or []:
        try:
            d = date.fromisoformat(event["date"])
        except (KeyError, ValueError):
            continue
        if d.weekday() >= 5:
            continue
        blocked = event.get("type") == "holiday" or (
            restricted_as_holiday and event.get("type") == "restricted_holiday"
        )
        if blocked:
            penalties[DAYS[d.weekday()]] += 1
    return penalties


def analyze_calendar_impact(data, events, restricted_as_holiday=False, weeks=16):
    """Estimate lost weekly sessions and identify courses exposed to calendar disruptions."""
    penalties = calendar_day_penalties(events, restricted_as_holiday)
    classes = data.get("classes", [])
    impacted = []
    for cls in classes:
        lost = penalties.get(cls.get("day"), 0)
        if lost:
            impacted.append({
                "course": cls.get("course", "UNKNOWN"),
                "group": cls.get("group", "UNKNOWN"),
                "day": cls.get("day", "UNKNOWN"),
                "slot": cls.get("slot", "UNKNOWN"),
                "estimated_lost_sessions": lost,
                "estimated_sessions": max(0, weeks - lost),
            })

    total = sum(x["estimated_lost_sessions"] for x in impacted)
    return {
        "weekday_blocked_dates": penalties,
        "impacted_sessions": impacted,
        "estimated_lost_sessions": sum(x["estimated_lost_sessions"] for x in impacted),
        "estimated_remaining_sessions": total,
    }


def _clone_with_calendar_cost(data, events, restricted_as_holiday=False):
    cloned = deepcopy(data)
    cloned["_calendar_day_penalties"] = calendar_day_penalties(events, restricted_as_holiday)
    return cloned


def optimize_with_calendar(data, events=None, restricted_as_holiday=False, time_limit=15):
    """Run the global CP-SAT optimizer with calendar-aware soft costs."""
    enriched = _clone_with_calendar_cost(data, events or [], restricted_as_holiday)
    result = optimize_whole_timetable(enriched, time_limit=time_limit)
    if result.get("changed") or result.get("status") in {"OPTIMAL", "FEASIBLE"}:
        result.setdefault("reasons", []).append(
            "Calendar-aware objective penalizes recurring timetable slots that fall on blocked academic-calendar dates."
        )
    return result


def simulate_disruption(data, disruption_type, target_name, day=None, slot=None, time_limit=8):
    """Stress-test a timetable against a single teacher or room failure."""
    trial = deepcopy(data)
    classes = trial.get("classes", [])

    if disruption_type == "Teacher unavailable":
        affected = [x for x in classes if x.get("teacher") == target_name]
        # Keep the teacher in the model but make every weekday unavailable.
        # This prevents the optimizer from silently falling back to the original teacher.
        blocked = {day: [] for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]}
        trial["teachers"] = [
            ({**t, "available_slots": blocked} if t.get("name") == target_name else t)
            for t in trial.get("teachers", [])
        ]
        if not affected:
            return {"status": "NO_MATCH", "summary": f"No classes use teacher {target_name}."}
    elif disruption_type == "Room unavailable":
        affected = [x for x in classes if x.get("room") == target_name]
        trial["rooms"] = [r for r in trial.get("rooms", []) if r.get("name") != target_name]
        if not affected:
            return {"status": "NO_MATCH", "summary": f"No classes use room {target_name}."}
    else:
        return {"status": "INVALID", "summary": "Unknown disruption type."}

    result = optimize_whole_timetable(trial, time_limit=time_limit)
    if result.get("status") not in {"OPTIMAL", "FEASIBLE"}:
        return {
            "status": result.get("status", "INFEASIBLE"),
            "summary": "AASE could not find a feasible timetable after the simulated disruption.",
            "affected_classes": len(affected),
        }

    original = {(x["course"], x["group"], x["day"], x["slot"], x["teacher"], x["room"]) for x in classes}
    changed = []
    for row in result.get("schedule", []):
        key_without_old = (row["course"], row["group"], row["day"], row["slot"], row["teacher"], row["room"])
        if key_without_old not in original:
            changed.append(row)

    return {
        "status": result.get("status"),
        "summary": f"AASE simulated {disruption_type.lower()} and produced a feasible recovery.",
        "affected_classes": len(affected),
        "changed_count": result.get("changed_count", len(changed)),
        "schedule": result.get("schedule", []),
        "reasons": result.get("reasons", []),
    }


def robustness_report(data, time_limit=5):
    """Measure how many single-resource disruptions remain recoverable."""
    teachers = sorted({x.get("teacher") for x in data.get("classes", []) if x.get("teacher")})
    rooms = sorted({x.get("room") for x in data.get("classes", []) if x.get("room")})

    teacher_results = []
    for teacher in teachers:
        result = simulate_disruption(data, "Teacher unavailable", teacher, time_limit=time_limit)
        teacher_results.append({"resource": teacher, "recoverable": result.get("status") in {"OPTIMAL", "FEASIBLE"}})

    room_results = []
    for room in rooms:
        result = simulate_disruption(data, "Room unavailable", room, time_limit=time_limit)
        room_results.append({"resource": room, "recoverable": result.get("status") in {"OPTIMAL", "FEASIBLE"}})

    checks = teacher_results + room_results
    recoverable = sum(1 for x in checks if x["recoverable"])
    robustness = round(100 * recoverable / len(checks), 1) if checks else 0.0

    return {
        "robustness_percent": robustness,
        "checks": len(checks),
        "recoverable_checks": recoverable,
        "teacher_results": teacher_results,
        "room_results": room_results,
    }
