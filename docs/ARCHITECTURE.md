# Architecture

## Core entities
- Course session: day, slot, course, teacher, room, student/group.
- Teacher availability: available slots, unavailable slots, qualifications, preferred minimum break.
- Room: capacity and availability.
- Student/group: enrolled sessions.

## Repair strategy
1. Detect the disrupted session.
2. Generate candidate slots and teacher substitutions.
3. Reject hard conflicts: student/group collision, teacher collision, room collision, unavailable teacher.
4. Score remaining candidates by student idle-gap cost, then movement/change cost.
5. Return the lowest-cost feasible repair with an explanation.

## Production solver
The MVP uses a deterministic heuristic. A production version can model the schedule as a constraint optimization problem using OR-Tools CP-SAT:
- Boolean variable x[class, day, slot, room, teacher].
- Hard constraints for one teacher, room and group per slot.
- Soft objectives for student gap minutes, teacher preferences, room changes and excessive consecutive teaching.
