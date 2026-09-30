from pathlib import Path
import json
from ingestion import parse_timetable_file

SLOTS = ["09:00-10:00","10:00-11:00","11:15-12:15","12:15-13:15","14:00-15:00","15:00-16:00"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def load_demo_data():
    return json.loads(Path("demo/data.json").read_text(encoding="utf-8"))


def parse_timetable_pdf(uploaded_file, use_ocr=False, default_group="OCR-GROUP", cloud_ocr_config=None):
    """Backward-compatible entry point: parse timetable PDF/CSV/XLSX."""
    records, _source = parse_timetable_file(uploaded_file, default_group=default_group, use_ocr=use_ocr)
    return records


def gap_score(schedule, student_id):
    score = 0
    for day in DAYS:
        day_items = sorted([x for x in schedule if x["group"] == student_id and x["day"] == day], key=lambda x: SLOTS.index(x["slot"]) if x["slot"] in SLOTS else 99)
        positions = [SLOTS.index(x["slot"]) for x in day_items if x["slot"] in SLOTS]
        score += sum(max(0, positions[i + 1] - positions[i] - 1) for i in range(len(positions) - 1))
    return score


def _free_room(room, day, slot, schedule, target=None):
    return not any(
        x is not target and x["room"] == room and x["day"] == day and x["slot"] == slot
        for x in schedule
    )


def repair_schedule(data, absent_day, absent_slot, absent_teacher, student_id):
    schedule = [x.copy() for x in data["classes"]]
    target = next((x for x in schedule if x["day"] == absent_day and x["slot"] == absent_slot and x["teacher"] == absent_teacher), None)
    if not target:
        return {"changed": False, "summary": "No class matched that teacher/day/slot in the demo dataset.", "schedule": schedule, "reasons": []}

    original_gap = gap_score(schedule, student_id)
    candidates = []
    teacher = next((t for t in data["teachers"] if t["name"] == target["teacher"]), None)
    for day in DAYS:
        for slot in SLOTS:
            if day == absent_day and slot == absent_slot:
                continue
            if teacher and slot not in teacher.get("available_slots", {}).get(day, []):
                continue
            if any(x is not target and x["group"] == target["group"] and x["day"] == day and x["slot"] == slot for x in schedule):
                continue
            if any(x is not target and x["teacher"] == target["teacher"] and x["day"] == day and x["slot"] == slot for x in schedule):
                continue
            if not _free_room(target["room"], day, slot, schedule, target):
                continue
            candidate = [x.copy() for x in schedule if x is not target]
            moved = target.copy()
            moved["day"], moved["slot"] = day, slot
            candidate.append(moved)
            candidates.append((gap_score(candidate, student_id), day, slot, target["teacher"], candidate))

    if not candidates:
        for t in data["teachers"]:
            if t["name"] == absent_teacher or target["course"] not in t.get("qualified_courses", []):
                continue
            for slot in SLOTS:
                if slot not in t.get("available_slots", {}).get(absent_day, []):
                    continue
                if any(x["teacher"] == t["name"] and x["day"] == absent_day and x["slot"] == slot for x in schedule):
                    continue
                if any(x["group"] == target["group"] and x["day"] == absent_day and x["slot"] == slot for x in schedule):
                    continue
                if not _free_room(target["room"], absent_day, slot, schedule, target):
                    continue
                candidate = [x.copy() for x in schedule if x is not target]
                moved = target.copy()
                moved["teacher"], moved["slot"] = t["name"], slot
                candidate.append(moved)
                candidates.append((gap_score(candidate, student_id), absent_day, slot, t["name"], candidate))

    if not candidates:
        return {"changed": False, "summary": "No feasible repair found without creating a direct conflict.", "schedule": schedule, "reasons": []}

    best_gap, new_day, new_slot, new_teacher, repaired = min(candidates, key=lambda x: (x[0], 0 if x[1] == absent_day else 1, DAYS.index(x[1]), SLOTS.index(x[2])))
    reasons = [
        f"Original student idle-gap score: {original_gap}.",
        f"Repaired student idle-gap score: {best_gap}.",
        f"Moved {target['course']} for {target['group']} to {new_day} {new_slot}.",
        f"Teacher assigned: {new_teacher}.",
        "The selected slot avoids existing group, teacher and room conflicts.",
    ]
    return {
        "changed": True,
        "summary": f"Repair found: {target['course']} moved to {new_day} {new_slot}.",
        "schedule": sorted(repaired, key=lambda x: (DAYS.index(x["day"]) if x["day"] in DAYS else 99, SLOTS.index(x["slot"]) if x["slot"] in SLOTS else 99, x["room"])),
        "reasons": reasons,
    }
