from __future__ import annotations

from copy import deepcopy
from datetime import date

from optimizer import DAYS, optimize_whole_timetable


def calendar_day_penalties(
    events,
    restricted_as_holiday=False,
    semester_start=None,
    semester_end=None,
):
    """Return blocked calendar-date counts by teaching weekday."""
    penalties = {day: 0 for day in DAYS}

    for event in events or []:
        try:
            d = date.fromisoformat(event["date"])
        except (KeyError, ValueError, TypeError):
            continue

        if semester_start is not None and d < semester_start:
            continue
        if semester_end is not None and d > semester_end:
            continue
        if d.weekday() >= 5:
            continue

        blocked = event.get("type") == "holiday" or (
            restricted_as_holiday and event.get("type") == "restricted_holiday"
        )
        if blocked:
            penalties[DAYS[d.weekday()]] += 1

    return penalties


def analyze_calendar_impact(
    data,
    events,
    restricted_as_holiday=False,
    weeks=16,
    semester_start=None,
    semester_end=None,
):
    """Estimate recurring sessions exposed to blocked calendar dates."""
    penalties = calendar_day_penalties(
        events,
        restricted_as_holiday,
        semester_start,
        semester_end,
    )
    classes = data.get("classes", [])
    impacted = []

    for cls in classes:
        lost = penalties.get(cls.get("day"), 0)
        if lost:
            impacted.append(
                {
                    "course": cls.get("course", "UNKNOWN"),
                    "group": cls.get("group", "UNKNOWN"),
                    "day": cls.get("day", "UNKNOWN"),
                    "slot": cls.get("slot", "UNKNOWN"),
                    "estimated_lost_sessions": lost,
                    "estimated_sessions": max(0, weeks - lost),
                }
            )

    total_lost = sum(x["estimated_lost_sessions"] for x in impacted)
    total_expected = weeks * len(classes)
    return {
        "weekday_blocked_dates": penalties,
        "impacted_sessions": impacted,
        "estimated_lost_sessions": total_lost,
        "estimated_expected_sessions": total_expected,
        "estimated_remaining_sessions": max(0, total_expected - total_lost),
    }


def _clone_with_calendar_cost(
    data,
    events,
    restricted_as_holiday=False,
    semester_start=None,
    semester_end=None,
):
    cloned = deepcopy(data)
    cloned["_calendar_day_penalties"] = calendar_day_penalties(
        events,
        restricted_as_holiday,
        semester_start,
        semester_end,
    )
    return cloned


def optimize_with_calendar(
    data,
    events=None,
    restricted_as_holiday=False,
    time_limit=15,
    semester_start=None,
    semester_end=None,
):
    """Run the global CP-SAT optimizer with semester-scoped calendar costs."""
    enriched = _clone_with_calendar_cost(
        data,
        events or [],
        restricted_as_holiday,
        semester_start,
        semester_end,
    )
    result = optimize_whole_timetable(enriched, time_limit=time_limit)

    if result.get("changed") or result.get("status") in {"OPTIMAL", "FEASIBLE"}:
        result.setdefault("reasons", []).append(
            "Calendar-aware objective penalizes recurring timetable slots that fall on blocked academic-calendar dates."
        )

    return result


def simulate_disruption(
    data,
    disruption_type,
    target_name,
    day=None,
    slot=None,
    time_limit=8,
):
    """Stress-test a timetable against a single teacher or room failure."""
    trial = deepcopy(data)
    classes = trial.get("classes", [])

    if disruption_type == "Teacher unavailable":
        affected = [x for x in classes if x.get("teacher") == target_name]

        blocked = {day_name: [] for day_name in DAYS}
        trial["teachers"] = [
            (
                {**teacher, "available_slots": blocked}
                if teacher.get("name") == target_name
                else teacher
            )
            for teacher in trial.get("teachers", [])
        ]

        if not affected:
            return {
                "status": "NO_MATCH",
                "summary": f"No classes use teacher {target_name}.",
            }

    elif disruption_type == "Room unavailable":
        affected = [x for x in classes if x.get("room") == target_name]
        trial["rooms"] = [
            room
            for room in trial.get("rooms", [])
            if room.get("name") != target_name
        ]

        if not affected:
            return {
                "status": "NO_MATCH",
                "summary": f"No classes use room {target_name}.",
            }

    else:
        return {"status": "INVALID", "summary": "Unknown disruption type."}

    result = optimize_whole_timetable(trial, time_limit=time_limit)
    if result.get("status") not in {"OPTIMAL", "FEASIBLE"}:
        return {
            "status": result.get("status", "INFEASIBLE"),
            "summary": "AASE could not find a feasible timetable after the simulated disruption.",
            "affected_classes": len(affected),
        }

    original = {
        (
            x["course"],
            x["group"],
            x["day"],
            x["slot"],
            x["teacher"],
            x["room"],
        )
        for x in classes
    }
    changed = [
        row
        for row in result.get("schedule", [])
        if (
            row["course"],
            row["group"],
            row["day"],
            row["slot"],
            row["teacher"],
            row["room"],
        )
        not in original
    ]

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
    teachers = sorted(
        {x.get("teacher") for x in data.get("classes", []) if x.get("teacher")}
    )
    rooms = sorted(
        {x.get("room") for x in data.get("classes", []) if x.get("room")}
    )

    teacher_results = []
    for teacher in teachers:
        result = simulate_disruption(
            data,
            "Teacher unavailable",
            teacher,
            time_limit=time_limit,
        )
        teacher_results.append(
            {
                "resource": teacher,
                "recoverable": result.get("status")
                in {"OPTIMAL", "FEASIBLE"},
            }
        )

    room_results = []
    for room in rooms:
        result = simulate_disruption(
            data,
            "Room unavailable",
            room,
            time_limit=time_limit,
        )
        room_results.append(
            {
                "resource": room,
                "recoverable": result.get("status")
                in {"OPTIMAL", "FEASIBLE"},
            }
        )

    checks = teacher_results + room_results
    recoverable = sum(1 for item in checks if item["recoverable"])
    robustness = round(100 * recoverable / len(checks), 1) if checks else 0.0

    return {
        "robustness_percent": robustness,
        "checks": len(checks),
        "recoverable_checks": recoverable,
        "teacher_results": teacher_results,
        "room_results": room_results,
    }
