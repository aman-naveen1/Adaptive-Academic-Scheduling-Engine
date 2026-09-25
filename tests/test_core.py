from datetime import date

from aase import analyze_calendar_impact, simulate_disruption
from calendar_parser import calendar_summary
from engine import load_demo_data
from optimizer import optimize_whole_timetable


def test_demo_respects_group_capacity():
    data = load_demo_data()
    result = optimize_whole_timetable(data, time_limit=3)

    assert result["status"] in {"OPTIMAL", "FEASIBLE"}
    assert result["schedule"]

    room_capacities = {
        room["name"]: room["capacity"]
        for room in data["rooms"]
    }
    group_sizes = {
        student["id"]: student["size"]
        for student in data["students"]
    }

    for row in result["schedule"]:
        assert room_capacities[row["room"]] >= group_sizes[row["group"]]


def test_unqualified_teacher_is_not_silently_reused():
    data = {
        "classes": [{
            "day": "Monday",
            "slot": "09:00-10:00",
            "course": "DBMS",
            "teacher": "Bad Teacher",
            "room": "R1",
            "group": "G1",
        }],
        "teachers": [
            {"name": "Bad Teacher", "qualified_courses": [], "available_slots": {}},
            {"name": "Good Teacher", "qualified_courses": ["DBMS"], "available_slots": {}},
        ],
        "rooms": [{"name": "R1", "capacity": 50}],
        "students": [{"id": "G1", "size": 30}],
    }

    result = optimize_whole_timetable(data, time_limit=3)

    assert result["status"] in {"OPTIMAL", "FEASIBLE"}
    assert result["schedule"][0]["teacher"] == "Good Teacher"


def test_teacher_disruption_removes_teacher_from_recovery():
    data = load_demo_data()
    result = simulate_disruption(
        data,
        "Teacher unavailable",
        "Dr. Sharma",
        time_limit=3,
    )

    if result["status"] in {"OPTIMAL", "FEASIBLE"}:
        assert all(row["teacher"] != "Dr. Sharma" for row in result["schedule"])


def test_calendar_summary_ignores_events_outside_semester():
    events = [
        {"date": "2026-06-01", "name": "Before", "type": "holiday"},
        {"date": "2026-08-03", "name": "Inside", "type": "holiday"},
        {"date": "2026-12-01", "name": "After", "type": "holiday"},
    ]

    summary = calendar_summary(
        events,
        date(2026, 7, 1),
        date(2026, 11, 30),
    )

    assert summary["holiday_days"] == 1
    assert summary["events"] == 1
    assert summary["blocked_days"] == 1


def test_calendar_impact_remaining_sessions_is_not_lost_session_count():
    data = {
        "classes": [
            {
                "day": "Monday",
                "slot": "09:00-10:00",
                "course": "A",
                "teacher": "T",
                "room": "R",
                "group": "G",
            },
            {
                "day": "Tuesday",
                "slot": "09:00-10:00",
                "course": "B",
                "teacher": "T2",
                "room": "R",
                "group": "G",
            },
        ]
    }
    events = [
        {"date": "2026-08-03", "name": "Holiday", "type": "holiday"},
    ]

    impact = analyze_calendar_impact(data, events, weeks=16)

    assert impact["estimated_lost_sessions"] == 1
    assert impact["estimated_expected_sessions"] == 32
    assert impact["estimated_remaining_sessions"] == 31
