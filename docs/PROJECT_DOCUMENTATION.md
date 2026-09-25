# AASE — Project Documentation

## 1. Project Overview

**AASE (Adaptive Academic Scheduling Engine)** is a constraint-based academic timetable optimization and disruption-management system.

The project is designed to solve a common problem in educational institutions: a timetable may be valid when created but become inefficient or infeasible when teachers, rooms, or academic-calendar events change.

AASE combines:

- OCR-based timetable extraction.
- Constraint programming using OR-Tools CP-SAT.
- Whole-timetable optimization.
- Academic-calendar parsing.
- Holiday and restricted-holiday awareness.
- Teacher and room disruption simulation.
- Timetable robustness analysis.
- Explainable optimization results.

AASE is intentionally **ERP-agnostic**. It can operate independently using uploaded files and can later be connected to an institutional ERP through an adapter or API.

---

## 2. Problem Statement

Traditional timetable systems generally generate a timetable once and store it in an ERP or administrative system.

The difficulty begins when the environment changes:

- A teacher becomes unavailable.
- A classroom becomes unavailable.
- A room does not have sufficient capacity.
- A timetable contains student idle gaps.
- Holidays reduce the number of teaching occurrences.
- Restricted holidays have institution-specific rules.
- A timetable that is technically feasible becomes difficult to operate.

Manually repairing such schedules can create secondary conflicts.

For example, moving one DSA class may cause:

1. a teacher collision;
2. a room collision;
3. a student-group collision;
4. excessive idle time;
5. another class to be displaced.

AASE treats timetable generation as a **constraint optimization problem** instead of a sequence of manual changes.

---

## 3. Objectives

### Primary objectives

1. Represent an academic timetable using a normalized data model.
2. Extract timetable information from PDFs, including scanned PDFs.
3. Detect and enforce hard scheduling constraints.
4. Optimize the complete timetable rather than repairing only one row.
5. Account for academic-calendar disruptions.
6. Simulate resource failures.
7. Estimate timetable robustness.
8. Explain the resulting scheduling decisions.

### Secondary objectives

- Keep the optimization engine independent of any specific ERP.
- Provide a simple interface for demonstration and experimentation.
- Make the system extensible for future institutional requirements.

---

## 4. System Architecture

`text
                    ┌──────────────────────┐
                    │   Timetable Source   │
                    │ PDF / Scanned PDF    │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │    OCR / Parser      │
                    │ PyMuPDF + Tesseract  │
                    └──────────┬───────────┘
                               │
                               ▼
┌──────────────────┐  ┌──────────────────────┐
│ Academic Calendar│─►│ Normalized Data Model │
│ PDF / CSV / XLSX │  │ Classes / Resources  │
└──────────────────┘  └──────────┬───────────┘
                                  │
                                  ▼
                    ┌──────────────────────┐
                    │   AASE Core Engine   │
                    │ OR-Tools CP-SAT      │
                    │ Constraint Engine    │
                    │ Calendar Intelligence│
                    └──────────┬───────────┘
                               │
                 ┌─────────────┼─────────────┐
                 ▼             ▼             ▼
          Optimization    Disruption     Robustness
             Result       Simulation      Analysis
                 │             │             │
                 └─────────────┼─────────────┘
                               ▼
                    ┌──────────────────────┐
                    │ Proposed Timetable   │
                    │ + Changes            │
                    │ + Impact             │
                    │ + Explanation        │
                    └──────────────────────┘
`

---

## 5. Technology Stack

| Component | Technology |
|---|---|
| Programming language | Python |
| Optimization | Google OR-Tools CP-SAT |
| User interface | Streamlit |
| PDF text extraction | pypdf |
| PDF rendering | PyMuPDF |
| OCR | Tesseract + pytesseract |
| Image processing | Pillow |
| Data handling | Pandas |
| Calendar formats | PDF, CSV, XLSX |
| Version control | Git / GitHub |

---

## 6. Core Data Model

A timetable class is represented approximately as:

```json
{
  "day": "Monday",
  "slot": "09:00-10:00",
  "course": "DSA",
  "teacher": "Dr. Sharma",
  "room": "C-201",
  "group": "BSc-CS-3A"
}
```

### Teacher

```json
{
  "name": "Dr. Sharma",
  "qualified_courses": ["DSA"],
  "available_slots": {
    "Monday": ["10:00-11:00"],
    "Tuesday": ["09:00-10:00"]
  }
}
```

### Room

```json
{
  "name": "C-201",
  "capacity": 60
}
```

### Calendar event

```json
{
  "date": "2026-10-19",
  "name": "Diwali Holiday",
  "type": "holiday",
  "source": "academic_calendar.csv"
}
```

---

## 7. OCR Pipeline

AASE supports scanned timetable PDFs where normal PDF text extraction cannot retrieve useful text.

The OCR pipeline is:

`text
PDF
 ↓
PyMuPDF renders page as image
 ↓
Tesseract OCR
 ↓
Detected text + confidence
 ↓
Day detection
 ↓
Time-slot detection
 ↓
Column parsing
 ↓
Course / teacher / room / group extraction
 ↓
Normalized timetable records
`

Each extracted record can retain:

- OCR confidence.
- Source page number.

Low-confidence records are surfaced to the user for review.

### OCR limitation

The parser currently uses known weekday and time-slot patterns. Highly irregular tables, merged cells, unusual abbreviations, handwriting, or radically different layouts may require parser customization.

---

## 8. Constraint Optimization

AASE uses **OR-Tools CP-SAT** to solve the timetable as a constraint optimization problem.

A Boolean decision variable can be viewed as:

`text
x[class, day, slot, teacher, room]
`

where:

`text
x = 1 → the class is assigned to that combination
x = 0 → it is not
`

### Hard constraint: one placement

Every class must receive exactly one valid placement.

`text
Σ x[class, day, slot, teacher, room] = 1
`

### Student/group collision

A group cannot attend two classes simultaneously.

### Teacher collision

A teacher cannot teach two classes simultaneously.

### Room collision

A room cannot host two classes simultaneously.

### Teacher qualification

A teacher must be qualified to teach the course.

### Teacher availability

If availability information exists, the teacher can only be assigned during permitted periods.

### Room capacity

A room must have sufficient capacity for the enrolled group when enrollment information is available.

---

## 9. Optimization Objective

AASE does not merely search for any feasible timetable.

It attempts to minimize a weighted cost consisting of:

1. Student idle gaps.
2. Calendar disruption exposure.
3. Unnecessary timetable movement.
4. Teacher changes.
5. Room changes.

Conceptually:

`text
Total Cost =
    Gap Cost
  + Calendar Cost
  + Movement Cost
  + Teacher Change Cost
  + Room Change Cost
`

The current implementation gives student idle gaps the strongest influence.

---

## 10. Academic Calendar Intelligence

Academic calendars are parsed separately from weekly timetable data.

Supported inputs:

- PDF
- CSV
- XLSX

AASE classifies detected events into:

- `holiday`
- `restricted_holiday`
- `academic_event`

### Why the calendar is separate

A weekly timetable does not represent individual calendar dates.

For example:

`text
Monday timetable
      ↓
Monday Aug 3
Monday Aug 10
Monday Aug 17 ← Holiday
Monday Aug 24
...
`

One Monday holiday does **not** mean every Monday is unavailable.

AASE therefore converts calendar events into weekday-level scheduling costs and impact estimates.

### Restricted holidays

Restricted holidays are configurable.

The administrator can choose:

- **Not blocked** — classes may still occur.
- **Blocked** — treat the date as unavailable.

This avoids assuming that every institution follows the same restricted-holiday policy.

---

## 11. Calendar Impact Analysis

AASE can estimate which recurring timetable sessions are exposed to blocked calendar dates.

Example:

`text
Monday → 3 blocked dates
Tuesday → 1 blocked date
Wednesday → 0 blocked dates
`

A recurring Monday session has greater calendar-disruption exposure than a recurring Wednesday session.

The system reports affected course/group/day combinations so an administrator can identify vulnerable parts of the timetable.

---

## 12. Disruption Simulation

AASE can simulate resource failures.

### Teacher failure

Example:

`text
Scenario:
Dr. Sharma becomes unavailable.
        ↓
Remove teacher availability.
        ↓
Run global CP-SAT optimization.
        ↓
Find feasible replacement timetable.
`

### Room failure

The same process can be applied to a classroom.

`text
Scenario:
C-201 becomes unavailable.
        ↓
Remove the room.
        ↓
Re-optimize the timetable.
        ↓
Measure whether a feasible schedule remains.
`

The important distinction is that AASE does not simply move the affected class. It attempts to find a **globally consistent timetable after the disruption**.

---

## 13. Robustness Analysis

AASE can stress-test the timetable against individual resource failures.

For every teacher and room:

`text
Remove resource
      ↓
Run optimizer
      ↓
Feasible?
  /       \
Yes       No
`

The system calculates:

`text
Robustness =
(recoverable scenarios / tested scenarios) × 100
`

For example:

`text
20 scenarios tested
17 recoverable

Robustness = 85%
`

### Interpretation

This is a **scenario-based decision-support metric**, not a mathematical guarantee that the timetable will survive all real-world disruptions.

---

## 14. Explainability

Every optimization result can provide:

- Solver status.
- Number of changed sessions.
- Resulting timetable.
- Hard constraints used.
- Objective priorities.
- Calendar-aware reasoning where applicable.

Example:

`text
Solver status: FEASIBLE

12 sessions analyzed
2 sessions changed

Reasons:
• No teacher collisions allowed.
• No room collisions allowed.
• Student idle gaps are strongly penalized.
• Existing assignments are preferred when feasible.
• Calendar-disrupted weekdays receive additional cost.
`

---

## 15. User Workflow

### Normal timetable optimization

`text
Upload timetable
      ↓
Review extracted data
      ↓
Upload academic calendar (optional)
      ↓
Run AASE
      ↓
CP-SAT optimization
      ↓
Review proposed timetable
`

### Disruption simulation

`text
Load timetable
      ↓
Select teacher/room failure
      ↓
Run simulation
      ↓
AASE re-optimizes
      ↓
Review recovery timetable
`

### Robustness analysis

`text
Load timetable
      ↓
Run robustness analysis
      ↓
Test teacher failures
      ↓
Test room failures
      ↓
Review recoverability metric
`

---

## 16. Software Engineering Design Principles

The project demonstrates several software engineering principles.

### Separation of concerns

The application separates:

- UI
- OCR
- calendar parsing
- timetable data
- optimization
- disruption analysis

### Modularity

The main components are independently reusable:

- `engine.py`
- `ocr_parser.py`
- `calendar_parser.py`
- `optimizer.py`
- `aase.py`
- `app.py`

### Extensibility

Institution-specific constraints can be added without rewriting the entire application.

Potential future constraints include:

- Laboratory requirements.
- Maximum teaching periods per day.
- Faculty workload limits.
- Consecutive-class preferences.
- Lunch periods.
- Course frequency requirements.
- Section-specific room requirements.

### ERP independence

The optimization engine does not depend on a particular ERP implementation.

A future adapter can transform ERP data into the normalized AASE model.

---

## 17. Testing Strategy

The project should be tested at several levels.

### Unit testing

Test individual functions such as:

- Calendar date parsing.
- Holiday classification.
- OCR extraction helpers.
- Gap calculation.
- Calendar impact calculation.

### Integration testing

Test workflows such as:

`text
PDF → OCR → timetable → optimizer
`

and:

`text
Calendar → parser → calendar impact → optimizer
`

### Constraint testing

Verify that generated timetables never contain:

- Two classes for the same group at the same time.
- Two classes for the same teacher at the same time.
- Two classes in the same room at the same time.

### Disruption testing

Test:

- Teacher unavailable.
- Room unavailable.
- No feasible replacement.
- Multiple affected sessions.

### User acceptance testing

Use realistic timetable and academic-calendar documents and manually verify the extracted information before accepting the optimized result.

---

## 18. Limitations

AASE is currently a **research/prototype system**, not a production registrar platform.

Important limitations include:

1. OCR extraction is best-effort.
2. Real institutions may use different timetable layouts.
3. Calendar documents may contain complex tables that require custom parsing.
4. The default demo metadata is synthetic.
5. Some real scheduling constraints are not yet modeled.
6. Robustness testing currently focuses on single teacher/room failures.
7. Calendar impact is currently represented as a weekday-level cost rather than exact dated class-occurrence scheduling.
8. Production deployment would require authentication, approval workflows, audit logs and institutional data validation.

These limitations are deliberate boundaries for the current project version.

---

## 19. Future Expansion

The architecture allows several future research directions.

### Exact semester occurrence scheduling

Instead of optimizing only the weekly pattern, the engine could model every dated teaching occurrence.

This would allow it to reason about:

- Required teaching hours.
- Missed classes.
- Makeup classes.
- Semester completion.
- Exact holiday effects.

### Advanced robustness

The simulator could test combinations such as:

`text
Teacher unavailable
+
Room unavailable
+
Holiday disruption
`

### Institutional constraint profiles

Different colleges could define their own scheduling policies through configuration files instead of modifying the source code.

### ERP/API adapters

A future integration layer could connect AASE to:

- PHP ERP systems.
- REST APIs.
- MySQL/MariaDB-backed systems.
- CSV/Excel exports.

The AASE core would remain unchanged.

---

## 20. Project Significance

AASE demonstrates how a real-world administrative problem can be transformed into a formal computational optimization problem.

Instead of:

> "Move this class somewhere else."

AASE asks:

> "Given the complete set of institutional constraints and disruptions, what feasible timetable minimizes the overall operational cost?"

That distinction is the central engineering idea of the project.

---

## 21. Demonstration Scenario

For a software engineering demonstration, the following sequence showcases the project effectively:

### Demo 1 — Baseline

Load the synthetic timetable and show the current schedule.

### Demo 2 — Calendar

Upload the academic calendar and show:

- holidays;
- restricted holidays;
- teaching-day calculation;
- affected timetable sessions.

### Demo 3 — Optimization

Run calendar-aware optimization and compare the resulting timetable.

### Demo 4 — Teacher disruption

Simulate a teacher becoming unavailable and show the globally repaired timetable.

### Demo 5 — Room disruption

Remove a classroom and demonstrate the recovery process.

### Demo 6 — Robustness

Run the robustness analysis and show how many tested resource failures remain recoverable.

This sequence demonstrates **requirements analysis, modular design, constraint modeling, optimization, exception handling, testing and explainability** rather than only showing a user interface.

---

## 22. Repository Structure

`text
adaptive-academic-scheduling-engine/
├── app.py
├── engine.py
├── optimizer.py
├── aase.py
├── calendar_parser.py
├── ocr_parser.py
├── requirements.txt
├── packages.txt
├── README.md
│
├── docs/
│   ├── ARCHITECTURE.md
│   └── AASE.md
│
├── demo/
│   ├── data.json
│   ├── academic_calendar.csv
│   └── AASE_DEMO.md
│
└── scripts/
`

---

## 23. Conclusion

AASE provides a modular foundation for adaptive academic timetable management.

The finalized prototype combines:

`text
OCR
+
Calendar Intelligence
+
Constraint Programming
+
Disruption Simulation
+
Robustness Analysis
+
Explainability
`

The system is intentionally independent of any particular ERP, allowing it to remain a standalone academic project while preserving a realistic path toward institutional deployment.
