# Demo PDF fixtures

Run:

    pip install -r requirements.txt
    python scripts/generate_demo_pdfs.py

This creates four synthetic PDFs under `demo/pdfs/`:

- `room_timetable_C201.pdf`
- `student_timetable_BSc-CS-3A.pdf`
- `teacher_availability.pdf`
- `rooms.pdf`

Presentation scenario:
1. Start the Streamlit app.
2. Keep **Use demo data** enabled.
3. Select **Monday / 09:00-10:00 / Dr. Sharma**.
4. Click **Repair timetable**.
5. Explain that the engine searches feasible alternatives and scores them by student idle-gap cost while respecting teacher/group conflicts.

The PDFs are synthetic and contain no real student or college data.
