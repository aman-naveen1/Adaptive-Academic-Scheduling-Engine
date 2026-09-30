from copy import deepcopy

from ortools.sat.python import cp_model

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
SLOTS = ["09:00-10:00", "10:00-11:00", "11:15-12:15", "12:15-13:15", "14:00-15:00", "15:00-16:00"]


def _student_count_for_class(course_class, data):
    explicit = course_class.get("student_count")
    if explicit is not None:
        return int(explicit)
    group = course_class.get("group")
    for student in data.get("students", []):
        if student.get("id") == group and student.get("size") is not None:
            return int(student.get("size") or 0)
    fallback = data.get("student_capacity")
    if fallback is not None:
        return int(fallback)
    return 0


def gap_penalty(schedule, group, day, slot):
    positions = sorted(SLOTS.index(x["slot"]) for x in schedule if x["group"] == group and x["day"] == day and x["slot"] in SLOTS)
    p = SLOTS.index(slot)
    if not positions:
        return 0
    left = max((x for x in positions if x < p), default=None)
    right = min((x for x in positions if x > p), default=None)
    return (max(0, p - left - 1) if left is not None else 0) + (max(0, right - p - 1) if right is not None else 0)


def _qualified_teachers(course_class, teachers):
    qualified = [name for name, teacher in teachers.items() if course_class["course"] in teacher.get("qualified_courses", [])]
    if not teachers:
        return [course_class["teacher"]]
    return qualified


def _add_gap_objective(model, candidates, classes):
    groups = sorted({c.get("group") for c in classes if c.get("group")})
    gap_terms = []
    for group in groups:
        for d in DAYS:
            occupancy = []
            for slot_index, slot in enumerate(SLOTS):
                vars_here = [v for i, choices in candidates.items() if classes[i].get("group") == group for v, cd, cs, _t, _r in choices if cd == d and cs == slot]
                occ = model.NewBoolVar(f"occ_{group}_{d}_{slot_index}")
                if vars_here:
                    for v in vars_here:
                        model.Add(v <= occ)
                    model.Add(occ <= sum(vars_here))
                else:
                    model.Add(occ == 0)
                occupancy.append(occ)
            for left in range(len(SLOTS)):
                for right in range(left + 1, len(SLOTS)):
                    middle = occupancy[left + 1:right]
                    adjacent = model.NewBoolVar(f"adj_{group}_{d}_{left}_{right}")
                    model.Add(adjacent <= occupancy[left])
                    model.Add(adjacent <= occupancy[right])
                    if middle:
                        model.Add(adjacent <= 1 - sum(middle))
                        model.Add(adjacent >= occupancy[left] + occupancy[right] - 1 - sum(middle))
                    else:
                        model.Add(adjacent >= occupancy[left] + occupancy[right] - 1)
                    gap_terms.append((right - left - 1) * adjacent)
    return gap_terms


def optimize_whole_timetable(data, time_limit=15):
    classes = [dict(x) for x in data.get("classes", [])]
    teachers = {x["name"]: x for x in data.get("teachers", [])}
    rooms = {x["name"]: x for x in data.get("rooms", [])}
    calendar_penalties = data.get("_calendar_day_penalties", {})
    if not classes or not rooms:
        return {"changed": False, "status": "INVALID", "summary": "Need classes and rooms."}

    model = cp_model.CpModel()
    candidates = {}
    for i, c in enumerate(classes):
        qualified = _qualified_teachers(c, teachers)
        choices = []
        student_count = _student_count_for_class(c, data)
        for d in DAYS:
            for s in SLOTS:
                for t in qualified:
                    avail = teachers.get(t, {}).get("available_slots", {})
                    if avail and s not in avail.get(d, []):
                        continue
                    for r, room in rooms.items():
                        capacity = room.get("capacity")
                        if student_count and capacity is not None and int(capacity) < student_count:
                            continue
                        v = model.NewBoolVar(f"x_{i}_{d}_{s}_{t}_{r}")
                        choices.append((v, d, s, t, r))
        if not choices:
            return {"changed": False, "status": "INFEASIBLE", "summary": f"No feasible placement for {c['course']}."}
        candidates[i] = choices
        model.Add(sum(v for v, *_ in choices) == 1)

    for resource in ("group", "teacher", "room"):
        buckets = {}
        for i, choices in candidates.items():
            for v, d, s, t, r in choices:
                value = {"group": classes[i]["group"], "teacher": t, "room": r}[resource]
                buckets.setdefault((d, s, value), []).append(v)
        for vs in buckets.values():
            model.Add(sum(vs) <= 1)

    objective = _add_gap_objective(model, candidates, classes)
    for i, choices in candidates.items():
        c = classes[i]
        for v, d, s, t, r in choices:
            cost = (
                calendar_penalties.get(d, 0) * 8
                + (0 if (d, s) == (c["day"], c["slot"]) else 3)
                + (0 if t == c["teacher"] else 5)
                + (0 if r == c["room"] else 1)
            )
            objective.append(cost * v)
    model.Minimize(sum(objective))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"changed": False, "status": solver.StatusName(status), "summary": "No globally feasible timetable found within the time limit."}

    out, changed = [], 0
    for i, choices in candidates.items():
        _, d, s, t, r = next(x for x in choices if solver.Value(x[0]))
        c = dict(classes[i])
        if (d, s, t, r) != (c["day"], c["slot"], c["teacher"], c["room"]):
            changed += 1
        c.update(day=d, slot=s, teacher=t, room=r)
        out.append(c)

    reasons = [
        "Teacher, room and student-group collisions are hard constraints.",
        "Student idle gaps are optimized from the solved timetable, not the original timetable.",
        "Unnecessary changes to existing slots, teachers and rooms are penalized.",
    ]
    if calendar_penalties:
        reasons.append("Calendar-aware costs discourage recurring placements on blocked academic-calendar weekdays.")
    return {
        "changed": changed > 0,
        "status": solver.StatusName(status),
        "changed_count": changed,
        "summary": f"Global optimization completed: {changed} of {len(classes)} sessions changed.",
        "schedule": sorted(out, key=lambda x: (DAYS.index(x["day"]), SLOTS.index(x["slot"]), x["room"])),
        "reasons": reasons,
    }


def optimize_timetable(data, student_id=None, absent_teacher=None, absent_day=None, absent_slot=None, time_limit=5):
    """Repair one teacher disruption at the affected day/slot."""
    classes = [dict(x) for x in data.get("classes", [])]
    target = next((x for x in classes if x["teacher"] == absent_teacher and x["day"] == absent_day and x["slot"] == absent_slot), None)
    if not target:
        return {"changed": False, "status": "NO_MATCH", "summary": "No class matched that teacher/day/slot.", "schedule": classes, "reasons": []}

    trial = deepcopy(data)
    existing = {t.get("name") for t in trial.get("teachers", [])}
    replacement = []
    for teacher in trial.get("teachers", []):
        if teacher.get("name") == absent_teacher:
            slots = {d: list(v) for d, v in teacher.get("available_slots", {}).items()}
            slots.setdefault(absent_day, list(SLOTS))
            slots[absent_day] = [s for s in slots[absent_day] if s != absent_slot]
            replacement.append({**teacher, "available_slots": slots})
        else:
            replacement.append(teacher)
    if absent_teacher not in existing:
        replacement.append({"name": absent_teacher, "qualified_courses": [target["course"]], "available_slots": {d: ([s for s in SLOTS if not (d == absent_day and s == absent_slot)]) for d in DAYS}})
    trial["teachers"] = replacement

    result = optimize_whole_timetable(trial, time_limit=time_limit)
    if result.get("status") not in ("OPTIMAL", "FEASIBLE"):
        return {"changed": False, "status": result.get("status", "INFEASIBLE"), "summary": "No feasible repair found.", "schedule": classes, "reasons": result.get("reasons", [])}
    result["summary"] = "CP-SAT repair found a globally consistent timetable around the teacher disruption."
    result.setdefault("reasons", []).append(f"{absent_teacher} was unavailable only for {absent_day} {absent_slot} during this repair.")
    return result
