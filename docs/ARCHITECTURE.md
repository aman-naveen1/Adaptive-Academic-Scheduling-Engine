# Architecture

AASE is deliberately split into ingestion, normalized data, optimization and decision-support layers.

## 1. Ingestion

### Timetable
- Text PDFs can be parsed with pypdf.
- Scanned PDFs can be rendered with PyMuPDF and read with Tesseract OCR.
- OCR records retain confidence and source-page metadata for human review.

### Academic calendar
- PDF, CSV and XLSX calendars are normalized into dated events.
- Events are classified as holiday, restricted holiday or general academic event.
- Restricted holidays are policy-controlled rather than automatically treated as closures.

## 2. Normalized model

The optimizer consumes institution-neutral records:

- Course session: day, slot, course, teacher, room, group.
- Teacher: qualifications and availability.
- Room: capacity and availability.
- Student/group: enrollment information.
- Calendar event: date, event name and event type.

This keeps AASE independent from any particular ERP or database.

## 3. Optimization

The core solver uses OR-Tools CP-SAT.

A course placement is represented by a Boolean variable:

`x[class, day, slot, teacher, room]`

Hard constraints include:
- exactly one placement per class;
- no student-group collision;
- no teacher collision;
- no room collision;
- teacher qualification;
- teacher availability;
- room capacity when enrollment metadata is supplied.

The objective currently combines:
- student idle-gap penalty;
- calendar-disruption cost;
- movement cost;
- teacher-change cost;
- room-change cost.

The calendar cost is intentionally soft: a holiday on one Monday should not make every Monday impossible. Instead, recurring Monday placements receive a higher cost when that weekday has more blocked dates during the academic calendar.

## 4. Adaptive disruption simulation

AASE can remove a teacher or room from the available resource pool and rerun the global optimizer.

This produces a proposed recovery timetable rather than merely moving the directly affected class.

## 5. Robustness analysis

The robustness module performs single-resource stress tests:

`teacher unavailable`

and

`room unavailable`

For each tested resource, AASE asks whether CP-SAT can still find a feasible timetable. The resulting percentage is presented as a scenario-based robustness metric, not a guarantee.

## 6. Explainability

Every optimization operation returns:
- solver status;
- number of changed sessions;
- resulting schedule;
- reasons describing the hard constraints and objective priorities.

The UI is intentionally separate from the optimization core so the engine can later be exposed through a REST API or another interface.

## 7. Future architecture

A production deployment can use:

`ERP / CSV / PDF -> adapters -> AASE core -> proposed timetable -> approval workflow`

The PHP ERP does not need to be rewritten. An ERP adapter can translate its database/API representation into the normalized AASE model.
