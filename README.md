# Timetable Fixer

A college timetable repair engine that minimizes student gaps and resolves timetable disruptions caused by teacher unavailability.

## MVP
- Upload timetable PDFs for rooms/classes and a student timetable PDF.
- Store structured timetable data as JSON.
- Teacher availability/preferences.
- Repair a disrupted slot by moving a class to an available teacher/room/time.
- Prefer moves that reduce student idle gaps while avoiding conflicts.
- Demo dataset included so the project can be presented without real college documents.

## Run
pip install -r requirements.txt
streamlit run app.py
