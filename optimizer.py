from ortools.sat.python import cp_model

DAYS = ["Monday","Tuesday","Wednesday","Thursday","Friday"]
SLOTS = ["09:00-10:00","10:00-11:00","11:15-12:15","12:15-13:15","14:00-15:00","15:00-16:00"]

def optimize_timetable(data, student_id=None, absent_teacher=None, absent_day=None, absent_slot=None, time_limit=5):
    classes = [dict(x) for x in data.get("classes", [])]
    teachers = {x["name"]: x for x in data.get("teachers", [])}
    rooms = {x["name"]: x for x in data.get("rooms", [])}
    groups = sorted({x["group"] for x in classes})
    days = list(DAYS)
    slots = list(SLOTS)

    # Remove the disrupted session from the fixed baseline. It will be re-assigned by the solver.
    target = None
    if absent_teacher and absent_day and absent_slot:
        for x in classes:
            if x["teacher"] == absent_teacher and x["day"] == absent_day and x["slot"] == absent_slot:
                target = x
                break

    movable = [target] if target else []
    fixed = [x for x in classes if x is not target]

    model = cp_model.CpModel()
    variables = {}
    candidates = {}

    for idx, c in enumerate(movable):
        key = idx
        candidates[key] = []
        qualified = [t for t, info in teachers.items() if c["course"] in info.get("qualified_courses", [])]
        if c["teacher"] in teachers and c["teacher"] not in qualified:
            qualified.append(c["teacher"])
        qualified = qualified or [c["teacher"]]

        for d in days:
            for s_idx, s in enumerate(slots):
                for t in qualified:
                    availability = teachers.get(t, {}).get("available_slots", {})
                    if availability and s not in availability.get(d, []):
                        continue
                    for r in rooms:
                        if rooms[r].get("capacity", 0) < data.get("student_capacity", 0):
                            continue
                        # Existing fixed conflicts are hard constraints.
                        if any(x["group"] == c["group"] and x["day"] == d and x["slot"] == s for x in fixed):
                            continue
                        if any(x["teacher"] == t and x["day"] == d and x["slot"] == s for x in fixed):
                            continue
                        if any(x["room"] == r and x["day"] == d and x["slot"] == s for x in fixed):
                            continue
                        v = model.NewBoolVar(f"x_{idx}_{d}_{s_idx}_{t}_{r}")
                        candidates[key].append((v, d, s, t, r))
        if not candidates[key]:
            return {"changed": False, "status": "INFEASIBLE", "summary": "No feasible placement exists for the disrupted class."}
        model.Add(sum(v for v, *_ in candidates[key]) == 1)

    # No two solver-assigned classes may share group, teacher, or room.
    for resource_pos in [1, 3, 4]:
        buckets = {}
        for key_items in candidates.values():
            for v, d, s, t, r in key_items:
                resource = [d, s, t, r][resource_pos - 1]
                buckets.setdefault((d, s, resource), []).append(v)
        for vars_ in buckets.values():
            if len(vars_) > 1:
                model.Add(sum(vars_) <= 1)

    objective_terms = []
    for key_items in candidates.values():
        for v, d, s, t, r in key_items:
            c = movable[0]
            gap_cost = 0
            if student_id and c["group"] == student_id:
                before = [SLOTS.index(x["slot"]) for x in fixed if x["group"] == student_id and x["day"] == d]
                after = [SLOTS.index(x["slot"]) for x in fixed if x["group"] == student_id and x["day"] == d]
                pos = SLOTS.index(s)
                # Penalize placing a class between distant existing classes.
                if before:
                    gap_cost += max(0, pos - max(before) - 1)
                if after:
                    gap_cost += max(0, min(after) - pos - 1)
            move_cost = 0 if d == c["day"] and s == c["slot"] else 2
            teacher_change = 0 if t == c["teacher"] else 4
            room_change = 0 if r == c["room"] else 1
            objective_terms.append((gap_cost * 20 + move_cost + teacher_change + room_change) * v)
    if objective_terms:
        model.Minimize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"changed": False, "status": solver.StatusName(status), "summary": "CP-SAT could not find a feasible repair within the time limit."}

    repaired = [dict(x) for x in fixed]
    reasons = ["CP-SAT treated teacher, room, and student/group collisions as hard constraints.",
               "The objective penalizes student gaps, moving classes, changing teachers, and changing rooms."]
    for key_items in candidates.values():
        chosen = next((item for item in key_items if solver.Value(item[0])), None)
        if chosen:
            _, d, s, t, r = chosen
            moved = dict(movable[0])
            moved.update({"day": d, "slot": s, "teacher": t, "room": r})
            repaired.append(moved)
            reasons.append(f"{moved['course']} placed on {d} {s} with {t} in {r}.")

    return {
        "changed": True,
        "status": solver.StatusName(status),
        "summary": f"CP-SAT repair completed ({solver.StatusName(status).lower()}).",
        "schedule": sorted(repaired, key=lambda x: (DAYS.index(x["day"]), SLOTS.index(x["slot"]), x["room"])),
        "reasons": reasons,
    }
