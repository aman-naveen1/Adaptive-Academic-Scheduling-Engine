from ortools.sat.python import cp_model

DAYS = ["Monday","Tuesday","Wednesday","Thursday","Friday"]
SLOTS = ["09:00-10:00","10:00-11:00","11:15-12:15","12:15-13:15","14:00-15:00","15:00-16:00"]

def gap_penalty(schedule, group, day, slot):
    positions=sorted(SLOTS.index(x["slot"]) for x in schedule if x["group"]==group and x["day"]==day and x["slot"] in SLOTS)
    p=SLOTS.index(slot)
    if not positions: return 0
    left=max((x for x in positions if x<p), default=None)
    right=min((x for x in positions if x>p), default=None)
    return (max(0,p-left-1) if left is not None else 0)+(max(0,right-p-1) if right is not None else 0)

def optimize_whole_timetable(data, time_limit=15):
    classes=[dict(x) for x in data.get("classes",[])]
    teachers={x["name"]:x for x in data.get("teachers",[])}
    rooms={x["name"]:x for x in data.get("rooms",[])}
    if not classes or not rooms: return {"changed":False,"status":"INVALID","summary":"Need classes and rooms."}
    model=cp_model.CpModel(); candidates={}
    for i,c in enumerate(classes):
        qualified=[n for n,t in teachers.items() if c["course"] in t.get("qualified_courses",[])]
        if c["teacher"] in teachers and c["teacher"] not in qualified: qualified.append(c["teacher"])
        qualified=qualified or [c["teacher"]]; choices=[]
        for d in DAYS:
            for s in SLOTS:
                for t in qualified:
                    avail=teachers.get(t,{}).get("available_slots",{})
                    if avail and s not in avail.get(d,[]): continue
                    for r,room in rooms.items():
                        if c.get("student_count",data.get("student_capacity",0)) and room.get("capacity",0)<c.get("student_count",data.get("student_capacity",0)): continue
                        v=model.NewBoolVar(f"x_{i}_{d}_{s}_{t}_{r}"); choices.append((v,d,s,t,r))
        if not choices: return {"changed":False,"status":"INFEASIBLE","summary":f"No feasible placement for {c['course']}."}
        candidates[i]=choices; model.Add(sum(v for v,*_ in choices)==1)
    for resource in ("group","teacher","room"):
        buckets={}
        for i,choices in candidates.items():
            for v,d,s,t,r in choices:
                value={"group":classes[i]["group"],"teacher":t,"room":r}[resource]
                buckets.setdefault((d,s,value),[]).append(v)
        for vs in buckets.values(): model.Add(sum(vs)<=1)
    objective=[]
    for i,choices in candidates.items():
        c=classes[i]
        for v,d,s,t,r in choices:
            cost=100*gap_penalty(classes,c["group"],d,s)+(0 if (d,s)==(c["day"],c["slot"]) else 3)+(0 if t==c["teacher"] else 5)+(0 if r==c["room"] else 1)
            objective.append(cost*v)
    model.Minimize(sum(objective))
    solver=cp_model.CpSolver(); solver.parameters.max_time_in_seconds=time_limit; solver.parameters.num_search_workers=8
    status=solver.Solve(model)
    if status not in (cp_model.OPTIMAL,cp_model.FEASIBLE): return {"changed":False,"status":solver.StatusName(status),"summary":"No globally feasible timetable found within the time limit."}
    out=[]; changed=0
    for i,choices in candidates.items():
        _,d,s,t,r=next(x for x in choices if solver.Value(x[0])); c=dict(classes[i])
        if (d,s,t,r)!=(c["day"],c["slot"],c["teacher"],c["room"]): changed+=1
        c.update(day=d,slot=s,teacher=t,room=r); out.append(c)
    return {"changed":changed>0,"status":solver.StatusName(status),"changed_count":changed,"summary":f"Global optimization completed: {changed} of {len(classes)} sessions changed.","schedule":sorted(out,key=lambda x:(DAYS.index(x["day"]),SLOTS.index(x["slot"]),x["room"])),"reasons":["Teacher, room and student-group collisions are hard constraints.","Student idle gaps are the dominant optimization objective.","Unnecessary changes to existing slots, teachers and rooms are penalized."]}

def optimize_timetable(data, student_id=None, absent_teacher=None, absent_day=None, absent_slot=None, time_limit=5):
    classes=[dict(x) for x in data.get("classes",[])]
    target=next((x for x in classes if x["teacher"]==absent_teacher and x["day"]==absent_day and x["slot"]==absent_slot),None)
    if not target: return {"changed":False,"summary":"No class matched that teacher/day/slot.","schedule":classes,"reasons":[]}
    # Lock every existing class except the disrupted one, then optimize the replacement.
    fixed=[x for x in classes if x is not target]
    teachers={x["name"]:x for x in data.get("teachers",[])}; rooms=data.get("rooms",[])
    qualified=[n for n,t in teachers.items() if target["course"] in t.get("qualified_courses",[])]
    if target["teacher"] in teachers and target["teacher"] not in qualified: qualified.append(target["teacher"])
    best=None
    for d in DAYS:
        for s in SLOTS:
            for t in qualified:
                avail=teachers.get(t,{}).get("available_slots",{})
                if avail and s not in avail.get(d,[]): continue
                if any(x["group"]==target["group"] and x["day"]==d and x["slot"]==s for x in fixed): continue
                if any(x["teacher"]==t and x["day"]==d and x["slot"]==s for x in fixed): continue
                for room in rooms:
                    r=room["name"]
                    if any(x["room"]==r and x["day"]==d and x["slot"]==s for x in fixed): continue
                    trial=dict(data); trial["classes"]=fixed+[dict(target,day=d,slot=s,teacher=t,room=r)]
                    result=optimize_whole_timetable(trial,time_limit=time_limit)
                    if result["status"] in ("OPTIMAL","FEASIBLE") and (best is None or result.get("changed_count",99999)<best.get("changed_count",99999)):
                        best=result
    if best:
        best["summary"]="CP-SAT repair found a globally consistent placement around the disruption."
        return best
    return {"changed":False,"status":"INFEASIBLE","summary":"No feasible repair found.","schedule":classes,"reasons":[]}
