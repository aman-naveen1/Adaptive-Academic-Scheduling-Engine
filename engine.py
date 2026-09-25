from pathlib import Path
import json
from io import BytesIO

SLOTS = ["09:00-10:00","10:00-11:00","11:15-12:15","12:15-13:15","14:00-15:00","15:00-16:00"]

def load_demo_data():
    return json.loads(Path("demo/data.json").read_text(encoding="utf-8"))

def parse_timetable_pdf(uploaded_file):
    from pypdf import PdfReader
    reader = PdfReader(BytesIO(uploaded_file.getvalue()))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return [{
        "day": "UNKNOWN", "slot": "UNKNOWN", "course": "PDF_TEXT",
        "teacher": "UNKNOWN", "room": "UNKNOWN", "group": "UNKNOWN",
        "source_text": text[:4000]
    }]

def gap_score(schedule, student_id):
    score = 0
    for day in ["Monday","Tuesday","Wednesday","Thursday","Friday"]:
        day_items = sorted([x for x in schedule if x["group"] == student_id and x["day"] == day],
                           key=lambda x: SLOTS.index(x["slot"]) if x["slot"] in SLOTS else 99)
        positions = [SLOTS.index(x["slot"]) for x in day_items if x["slot"] in SLOTS]
        score += sum(max(0, positions[i+1] - positions[i] - 1) for i in range(len(positions)-1))
    return score

def repair_schedule(data, absent_day, absent_slot, absent_teacher, student_id):
    schedule = [x.copy() for x in data["classes"]]
    target = next((x for x in schedule if x["day"] == absent_day and x["slot"] == absent_slot and x["teacher"] == absent_teacher), None)
    if not target:
        return {"changed": False, "summary": "No class matched that teacher/day/slot in the demo dataset.", "schedule": schedule, "reasons": []}

    original_gap = gap_score(schedule, student_id)
    candidates = []

    # First preference: move the same teacher's class to a slot they are available.
    teacher = next((t for t in data["teachers"] if t["name"] == target["teacher"]), None)
    for day in ["Monday","Tuesday","Wednesday","Thursday","Friday"]:
        for slot in SLOTS:
            if day == absent_day and slot == absent_slot:
                continue
            if teacher and slot not in teacher["available_slots"].get(day, []):
                continue
            if any(x["group"] == target["group"] and x["day"] == day and x["slot"] == slot for x in schedule):
                continue
            if any(x["teacher"] == target["teacher"] and x["day"] == day and x["slot"] == slot for x in schedule if x is not target):
                continue
            candidate = [x.copy() for x in schedule if x is not target]
            moved = target.copy()
            moved["day"], moved["slot"] = day, slot
            candidate.append(moved)
            candidates.append((gap_score(candidate, student_id), day, slot, target["teacher"], candidate))

    # Second preference: substitute a qualified teacher during the disrupted day.
    if not candidates:
        for t in data["teachers"]:
            if t["name"] == absent_teacher or target["course"] not in t.get("qualified_courses", []):
                continue
            for slot in SLOTS:
                if slot not in t["available_slots"].get(absent_day, []):
                    continue
                if any(x["teacher"] == t["name"] and x["day"] == absent_day and x["slot"] == slot for x in schedule):
                    continue
                if any(x["group"] == target["group"] and x["day"] == absent_day and x["slot"] == slot for x in schedule):
                    continue
                if any(x["room"] == target["room"] and x["day"] == absent_day and x["slot"] == slot for x in schedule):
                    continue
                candidate = [x.copy() for x in schedule if x is not target]
                moved = target.copy()
                moved["teacher"], moved["slot"] = t["name"], slot
                candidate.append(moved)
                candidates.append((gap_score(candidate, student_id), absent_day, slot, t["name"], candidate))

    if not candidates:
        return {"changed": False, "summary": "No feasible repair found without creating a direct conflict.", "schedule": schedule, "reasons": []}

    best = min(candidates, key=lambda x: (x[0], 0 if x[1] == absent_day else 1, SLOTS.index(x[2])))
    best_gap, new_day, new_slot, new_teacher, repaired = best
    reasons = [
        f"Original student idle-gap score: {original_gap}.",
        f"Repaired student idle-gap score: {best_gap}.",
        f"Moved {target['course']} for {target['group']} to {new_day} {new_slot}.",
        f"Teacher assigned: {new_teacher}.",
        "The selected slot avoids an existing group/teacher/room conflict."
    ]
    return {"changed": True, "summary": f"Repair found: {target['course']} moved to {new_day} {new_slot}.",
            "schedule": sorted(repaired, key=lambda x: (x["day"], SLOTS.index(x["slot"]) if x["slot"] in SLOTS else 99, x["room"])),
            "reasons": reasons}
