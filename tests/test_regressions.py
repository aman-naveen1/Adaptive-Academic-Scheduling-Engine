from datetime import date
from io import BytesIO
from types import SimpleNamespace


def _upload(name, text):
    return SimpleNamespace(name=name, getvalue=lambda: text.encode("utf-8"))


def _base_data():
    slots = ["09:00-10:00", "10:00-11:00", "11:15-12:15", "12:15-13:15", "14:00-15:00", "15:00-16:00"]
    availability = {d: list(slots) for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]}
    return {
        "classes": [
            {"day": "Monday", "slot": "09:00-10:00", "course": "DSA", "teacher": "Vipin Rathi", "room": "C-201", "group": "BSc-CS-3A"},
            {"day": "Monday", "slot": "14:00-15:00", "course": "DBMS", "teacher": "Kamlesh Kumar", "room": "C-202", "group": "BSc-CS-3A"},
        ],
        "teachers": [
            {"name": "Vipin Rathi", "qualified_courses": ["DSA"], "available_slots": availability},
            {"name": "Kamlesh Kumar", "qualified_courses": ["DBMS"], "available_slots": availability},
        ],
        "rooms": [{"name": "C-201", "capacity": 60}, {"name": "C-202", "capacity": 60}],
        "students": [{"id": "BSc-CS-3A", "size": 5}],
    }


def test_abbreviated_month_and_range_parsing():
    from calendar_parser import _events_from_lines
    events = _events_from_lines(["24 Dec - 31 Dec 2026 Winter Break", "25 Dec 2026 Christmas"], "csv")
    assert sum(e["name"].endswith("Winter Break") for e in events) == 8
    assert any(e["date"] == "2026-12-25" for e in events)


def test_calendar_classification_does_not_call_resume_or_workshop_holidays():
    from calendar_parser import _classify
    assert _classify("Classes resume after Diwali holiday") == "academic_event"
    assert _classify("Tea break workshop") == "academic_event"
    assert _classify("Sarah Rh factor lecture") == "academic_event"


def test_calendar_penalties_deduplicate_same_date():
    from aase import calendar_day_penalties
    events = [
        {"date": "2026-10-02", "type": "holiday", "name": "Holiday"},
        {"date": "2026-10-02", "type": "holiday", "name": "Campus closed"},
    ]
    assert calendar_day_penalties(events)["Friday"] == 1


def test_group_size_precedes_global_student_capacity():
    from optimizer import _student_count_for_class
    data = {"students": [{"id": "G1", "size": 5}], "student_capacity": 90}
    assert _student_count_for_class({"group": "G1"}, data) == 5


def test_teacher_repair_blocks_only_absent_slot():
    from optimizer import optimize_timetable
    data = _base_data()
    result = optimize_timetable(data, absent_teacher="Vipin Rathi", absent_day="Monday", absent_slot="09:00-10:00", time_limit=3)
    assert result["status"] in {"OPTIMAL", "FEASIBLE"}
    assert any(x["teacher"] == "Vipin Rathi" and x["day"] == "Monday" and x["slot"] != "09:00-10:00" for x in result["schedule"])


def test_repair_works_without_teacher_metadata():
    from optimizer import optimize_timetable
    data = _base_data()
    data["teachers"] = []
    result = optimize_timetable(data, absent_teacher="Vipin Rathi", absent_day="Monday", absent_slot="09:00-10:00", time_limit=3)
    assert result["status"] in {"OPTIMAL", "FEASIBLE"}
    assert not any(x["teacher"] == "Vipin Rathi" and x["day"] == "Monday" and x["slot"] == "09:00-10:00" for x in result["schedule"])


def test_heuristic_repair_does_not_double_book_room():
    from engine import repair_schedule
    data = _base_data()
    data["classes"].append({"day": "Tuesday", "slot": "09:00-10:00", "course": "OS", "teacher": "Sheetal Singh", "room": "C-201", "group": "BSc-CS-3A"})
    data["teachers"].append({"name": "Sheetal Singh", "qualified_courses": ["OS"], "available_slots": {d: ["09:00-10:00"] for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]}})
    result = repair_schedule(data, "Monday", "09:00-10:00", "Vipin Rathi", "BSc-CS-3A")
    assert result["changed"]
    seen = set()
    for row in result["schedule"]:
        key = (row["day"], row["slot"], row["room"])
        assert key not in seen
        seen.add(key)


def test_database_demo_seed_does_not_overwrite_existing(tmp_path, monkeypatch):
    import database
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    database.init_db()
    imported = {"classes": [{"day": "Monday", "slot": "09:00-10:00", "course": "Imported", "teacher": "Vipin Rathi", "room": "C-201", "group": "G1"}], "teachers": [], "rooms": [{"name": "C-201", "capacity": 60}], "students": []}
    database.seed_from_data(imported, source="document_import", replace_classes=True)
    database.seed_from_data({"classes": [{"day": "Tuesday", "slot": "09:00-10:00", "course": "Demo", "teacher": "Demo", "room": "C-201", "group": "G1"}]}, source="demo", replace_classes=True)
    assert database.load_data()["classes"][0]["course"] == "Imported"


def test_database_import_replacement_clears_stale_resources(tmp_path, monkeypatch):
    import database
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    database.init_db()
    database.seed_from_data({"classes": [], "teachers": [{"name": "Old Teacher", "qualified_courses": []}], "rooms": [{"name": "OLD", "capacity": 60}], "students": []}, source="old", replace_classes=True)
    database.seed_from_data({"classes": [{"day": "Monday", "slot": "09:00-10:00", "course": "New", "teacher": "New Teacher", "room": "NEW", "group": "G1"}], "teachers": [{"name": "New Teacher", "qualified_courses": ["New"]}], "rooms": [{"name": "NEW", "capacity": 60}], "students": []}, source="document_import", replace_classes=True)
    data = database.load_data()
    assert {t["name"] for t in data["teachers"]} == {"New Teacher"}
    assert {r["name"] for r in data["rooms"]} == {"NEW"}


def test_dense_timetable_gap_objective_is_feasible():
    # Two occupied slots between another pair used to make the gap constraint infeasible.
    from optimizer import optimize_whole_timetable
    data = _base_data()
    data["classes"] = [
        {"day": "Monday", "slot": s, "course": "DSA", "teacher": "Vipin Rathi", "room": "C-201", "group": "BSc-CS-3A"}
        for s in ["09:00-10:00", "10:00-11:00", "11:15-12:15", "12:15-13:15"]
    ]
    result = optimize_whole_timetable(data, time_limit=3)
    assert result["status"] in {"OPTIMAL", "FEASIBLE"}


def test_rh_abbreviation_needs_to_be_a_tag():
    from calendar_parser import _classify
    assert _classify("Holi (RH)") == "restricted_holiday"
    assert _classify("Karva Chauth - RH") == "restricted_holiday"
    assert _classify("Rh factor lecture") == "academic_event"
