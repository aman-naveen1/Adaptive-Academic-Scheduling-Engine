# AASE — Adaptive Academic Scheduling Engine

AASE is an OCR-enabled, constraint-based academic scheduling and disruption-management engine.

It started as a timetable repair project and now supports:

- **OCR timetable ingestion** from scanned PDFs.
- **Whole-timetable optimization** using OR-Tools CP-SAT.
- **Hard constraints** for student-group, teacher and room collisions.
- **Teacher qualification, availability and room-capacity constraints** when metadata is supplied.
- **Academic-calendar parsing** from PDF, CSV and XLSX.
- **Holiday and restricted-holiday awareness** with configurable institutional policy.
- **Calendar impact analysis** for recurring weekly schedules.
- **Disruption simulation** for teacher and room failures.
- **Robustness analysis** by stress-testing single-resource failures.
- **Explainable results** showing what changed and why.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

For OCR deployment, Tesseract must also be installed; Streamlit deployment uses `packages.txt` for the system package.

## Demo

The repository includes:

- `demo/data.json` — synthetic timetable and resource metadata.
- `demo/academic_calendar.csv` — synthetic academic calendar.
- `demo/AASE_DEMO.md` — demonstration walkthrough.

## How AASE works

```text
Timetable PDF ──→ OCR ──→ normalized classes ──┐
                                               │
Academic calendar ─→ holidays/RH ─────────────┤
                                               ↓
                                  AASE constraint engine
                                  ├─ CP-SAT optimization
                                  ├─ disruption simulation
                                  └─ robustness analysis
                                               ↓
                                  proposed timetable
                                  + impact + explanation
```

The academic calendar is intentionally modeled separately from the weekly timetable. A dated holiday blocks a specific calendar occurrence, not every occurrence of that weekday. AASE therefore converts calendar events into weekday-level soft costs and an impact report. Restricted holidays can be treated as blocked only when the institution selects that policy.

## Project structure

```text
adaptive-academic-scheduling-engine/
├── app.py
├── engine.py
├── optimizer.py
├── aase.py
├── calendar_parser.py
├── ocr_parser.py
├── requirements.txt
├── packages.txt
├── docs/
│   ├── ARCHITECTURE.md
│   └── AASE.md
├── demo/
│   ├── data.json
│   ├── academic_calendar.csv
│   └── AASE_DEMO.md
└── scripts/
```

## Design boundary

AASE is **ERP-agnostic**. It does not depend on PHP, MySQL or a specific college ERP. A future integration can send structured timetable/resource/calendar data to the engine through an API.

The project deliberately keeps the optimization core independent from the presentation layer and from any institution-specific ERP.

## Limitations

This is a research/prototype project rather than a production registrar system. OCR extraction is best-effort, the default demo uses synthetic metadata, and the robustness percentage measures only the tested single-resource scenarios. Real deployment would require institution-specific rules such as labs, room types, faculty workloads, maximum daily periods, semester-specific course requirements and approval/audit workflows.
