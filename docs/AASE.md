# AASE — Adaptive Academic Scheduling Engine

AASE extends Timetable Fixer from timetable repair into a disruption-aware scheduling engine.

## Capabilities

- OCR timetable ingestion from scanned PDFs.
- Whole-timetable CP-SAT optimization.
- Teacher and room disruption simulation.
- Calendar-aware scheduling costs.
- Academic-calendar parsing from PDF, CSV and XLSX.
- Holiday and restricted-holiday classification.
- Semester calendar impact analysis.
- Robustness testing against single-resource failures.

## Calendar model

The academic calendar is deliberately kept separate from the weekly timetable. AASE maps dated calendar events to weekdays and uses the number of blocked dates on each weekday as a soft scheduling cost.

This avoids the incorrect assumption that one holiday makes every occurrence of that weekday unavailable.

For example, if Monday has three holidays during a 16-week semester and Tuesday has one, a recurring Monday class carries a higher calendar-disruption cost.

Restricted holidays can be treated as:
- **Not blocked** — default; the institution may still conduct classes.
- **Blocked** — administrator-selected policy.

## Disruption simulation

AASE can stress-test a schedule by removing:
- a teacher;
- a room.

The optimizer then attempts to produce a globally feasible replacement timetable.

## Robustness

The robustness report performs single-resource failure tests and reports the percentage of tested teacher/room failures for which CP-SAT can still find a feasible schedule.

This is a decision-support metric, not a guarantee of real-world resilience.

## Future ERP integration

The core engine remains ERP-agnostic. A future PHP/ERP adapter can provide structured classes, teachers, rooms and calendar events without changing AASE's optimization logic.
