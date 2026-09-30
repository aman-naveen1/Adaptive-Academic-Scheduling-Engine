# AASE — Adaptive Academic Scheduling Engine

AASE is a constraint-based academic scheduling and disruption-management engine designed to **adapt an existing college timetable when real-world conditions change**.

It is built around a normalized data layer so the same optimization engine can consume data from PDFs/OCR today and a college ERP/API later.

## What AASE supports

- **SQLite scheduling database** for normalized timetable, teacher, room, student, absence and optimization-run data.
- **PDF timetable ingestion** with direct text extraction.
- **Cloud OCR ingestion** for scanned PDFs using Google Cloud Document AI; local Tesseract is not required.
- **Whole-timetable optimization** using OR-Tools CP-SAT.
- **Hard constraints** for student-group, teacher and room collisions.
- **Teacher qualification, availability and room-capacity constraints** when metadata is supplied.
- **Academic-calendar parsing** from PDF, CSV and XLSX.
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

For cloud OCR, configure Google Cloud Document AI credentials through environment variables. Never commit service-account keys to the repository.

Example:

```bash
GOOGLE_CLOUD_PROJECT=your-project-id
DOCUMENT_AI_PROCESSOR_ID=your-processor-id
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

## Demo

The repository includes synthetic timetable/resource data in `demo/data.json`. The dashboard seeds this data into SQLite on first run so you can immediately demonstrate the system without a college ERP.

For a realistic demonstration, use the supplied synthetic PDF timetable/calendar files or the PDF/CSV/XLSX upload controls in the dashboard.

## Architecture

```text
             College ERP / API
                    │
                    │ structured data
                    ▼
PDF ──→ PDF parser / Cloud OCR ──→ normalized SQLite database
                                      │
             Academic calendar ───────┤
             Teacher availability ────┤
             Room metadata ───────────┤
                                      ▼
                              AASE optimization layer
                              ├─ hard constraints
                              ├─ soft objectives
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
- **Time Table** — inspect/import timetable PDFs and persist them to SQLite.
- **Teachers** — qualifications, availability and absence records.
- **Rooms** — room inventory and capacity.
- **Academic Calendar** — parse and save holidays/events.
- **OCR Intake** — cloud OCR configuration and ingestion architecture.
- **Disruptions** — simulate teacher/room failures.
- **Optimization** — run CP-SAT/repair/robustness operations.
- **Reports** — optimization audit trail.

## Design boundary

AASE is **ERP-agnostic**. It does not depend on PHP, MySQL or a specific college ERP. A future integration can send structured timetable/resource/calendar data to the database/service through an API.

The optimization core is deliberately independent from the presentation layer and from institution-specific ERP code.

## Limitations

This is a research/prototype project rather than a production registrar system. OCR extraction is best-effort, the default demo uses synthetic metadata, and the robustness percentage measures only the tested single-resource scenarios. Real deployment would require institution-specific rules such as labs, room types, faculty workloads, maximum daily periods, semester-specific course requirements, authentication and approval/audit workflows.
