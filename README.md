# AASE — Adaptive Academic Scheduling Engine

AASE is a constraint-based academic scheduling and disruption-management engine designed to **adapt an existing college timetable when real-world conditions change**.

It is built around a normalized data layer so the same optimization engine can consume data from PDFs/OCR today and a college ERP/API later.

## What AASE supports

- **SQLite scheduling database** for normalized timetable, teacher, room, student, absence and optimization-run data.
- **Timetable ingestion from PDF, CSV, XLSX and XLS.**
- **Local Tesseract OCR** as a free fallback for scanned/image PDFs.
- **Whole-timetable optimization** using OR-Tools CP-SAT.
- **Hard constraints** for student-group, teacher and room collisions.
- **Teacher qualification, availability and room-capacity constraints** when metadata is supplied.
- **Academic-calendar parsing** from PDF, CSV, XLSX and XLS.
- **Holiday and restricted-holiday awareness** with configurable institutional policy.
- **Calendar impact analysis** for recurring weekly schedules.
- **Disruption simulation** for teacher and room failures.
- **Robustness analysis** by stress-testing single-resource failures.
- **Explainable results** showing what changed and why.
- **ERP-agnostic architecture** so a future college API can replace the PDF/OCR ingestion path without rewriting the optimizer.

## Run locally

```bash
pip install -r requirements.txt
python -m streamlit run app.py
```

SQLite is built into Python. A local `aase.db` file is created automatically when the application starts; it is a runtime database and should not be committed to Git.

### Tesseract OCR

AASE uses local Tesseract for scanned PDFs. Install Tesseract 5.x on the machine running the app. If it is not on `PATH`, set `TESSERACT_CMD` to the full `tesseract.exe` path.

No Google Cloud account, API key or paid OCR service is required.

## Demo

The repository includes synthetic timetable/resource data in `demo/data.json`. The dashboard seeds this data into SQLite only when the database has no timetable records, so a new Streamlit browser session cannot overwrite an existing import.

For a realistic demonstration, use the supplied synthetic PDF timetable/calendar files or the PDF/CSV/XLSX/XLS upload controls in the dashboard.

## Architecture

```text
             College ERP / API
                    │
                    │ structured data
                    ▼
PDF ──→ PDF parser / Tesseract ──→ normalized SQLite database
CSV/XLSX/XLS ──────────────────────→ normalized SQLite database
                                      │
             Academic calendar ───────┤
             Teacher availability ────┤
             Room metadata ───────────┤
                                      ▼
                              AASE optimization layer
                              ├─ hard constraints
                              ├─ student-gap objective
                              ├─ calendar-aware objective
                              ├─ CP-SAT optimization
                              ├─ disruption simulation
                              └─ robustness analysis
                                      │
                                      ▼
                            repaired / optimized timetable
                                      │
                                      ▼
                              Streamlit dashboard
```

### Why SQL and OCR are both used

OCR is an **ingestion mechanism**, not the scheduling database. A scanned timetable is converted into structured records and then stored in SQLite. This keeps the optimizer independent from OCR quality and means the college can later replace:

```text
PDF → OCR → database
```

with:

```text
College ERP API → database
```

without changing the CP-SAT optimization layer.

## Dashboard

The Streamlit interface follows the visual language of a college ERP dashboard: left navigation, an institutional header, metric cards, a timeline-style daily timetable, data tables and dedicated administrative sections.

Main sections:

- **Dashboard** — today's classes, gap score, staff absences and managed rooms.
- **Time Table** — inspect/import timetable PDFs, CSVs and Excel files and persist them to SQLite.
- **Teachers** — qualifications, availability and absence records.
- **Rooms** — room inventory and capacity.
- **Academic Calendar** — parse and save holidays/events from PDF, CSV or Excel.
- **OCR Intake** — local Tesseract configuration and ingestion architecture.
- **Disruptions** — simulate teacher/room failures, including a specific teacher day/slot.
- **Optimization** — run CP-SAT/repair/robustness operations.
- **Reports** — optimization audit trail.

## Testing

Run the complete automated suite with:

```bash
python -m pytest -q
```

The regression suite covers document ingestion plus optimizer, calendar and SQLite failure modes that are especially easy to miss in the Streamlit UI.

## Design boundary

AASE is **ERP-agnostic**. It does not depend on PHP, MySQL or a specific college ERP. A future integration can send structured timetable/resource/calendar data to the database/service through an API.

The optimization core is deliberately independent from the presentation layer and from institution-specific ERP code.

## Limitations

This is a research/prototype project rather than a production registrar system. OCR extraction is best-effort, the default demo uses synthetic metadata, and the robustness percentage measures the tested single-resource scenarios. Real deployment would require institution-specific rules such as labs, room types, faculty workloads, maximum daily periods, semester-specific course requirements, authentication and approval/audit workflows.
