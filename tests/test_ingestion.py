from io import BytesIO

import pandas as pd
from reportlab.pdfgen import canvas

from calendar_parser import parse_academic_calendar
from ingestion import parse_timetable_file


class Upload:
    def __init__(self, name, data):
        self.name = name
        self._data = data

    def getvalue(self):
        return self._data


def timetable_frame():
    return pd.DataFrame([
        ["Monday", "09:00-10:00", "Data Structures & Algorithms", "Vipin Rathi", "C-201", "BSc-CS-3A"],
        ["Monday", "14:00-15:00", "Database Management Systems", "Kamlesh Kumar", "C-201", "BSc-CS-3A"],
        ["Tuesday", "09:00-10:00", "Operating Systems", "Sheetal Singh", "C-202", "BSc-CS-3A"],
        ["Friday", "17:30-18:30", "Probability & Statistics", "Nikhil Rajput", "C-201", "BSc-CS-3A"],
    ], columns=["day", "slot", "course", "teacher", "room", "group"])


def test_timetable_csv():
    frame = timetable_frame()
    upload = Upload("timetable.csv", frame.to_csv(index=False).encode())
    rows, source = parse_timetable_file(upload)
    assert source == "csv"
    assert len(rows) == 4
    assert rows[0]["teacher"] == "Vipin Rathi"
    assert rows[-1]["slot"] == "17:30-18:30"


def test_timetable_xlsx():
    frame = timetable_frame()
    buffer = BytesIO()
    frame.to_excel(buffer, index=False)
    upload = Upload("timetable.xlsx", buffer.getvalue())
    rows, source = parse_timetable_file(upload)
    assert source == "xlsx"
    assert len(rows) == 4
    assert rows[1]["course"] == "Database Management Systems"


def test_timetable_pdf_text():
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(50, 780, "Monday")
    pdf.drawString(50, 760, "09:00-10:00  Data Structures & Algorithms  Vipin Rathi  C-201  BSc-CS-3A")
    pdf.drawString(50, 740, "14:00-15:00  Database Management Systems  Kamlesh Kumar  C-201  BSc-CS-3A")
    pdf.save()
    upload = Upload("timetable.pdf", buffer.getvalue())
    rows, source = parse_timetable_file(upload, use_ocr=False)
    assert source == "pdf_text"
    assert len(rows) == 2
    assert rows[0]["day"] == "Monday"


def test_calendar_csv():
    frame = pd.DataFrame([
        ["2026-10-02", "Gandhi Jayanti"],
        ["2026-10-05", "Department Development Day", "restricted holiday"],
        ["2026-10-12", "College Foundation Day", "holiday"],
    ])
    upload = Upload("calendar.csv", frame.to_csv(index=False, header=False).encode())
    events, warnings = parse_academic_calendar(upload, use_ocr=False)
    assert len(events) == 3
    assert events[0]["date"] == "2026-10-02"
    assert events[1]["type"] == "restricted_holiday"
    assert not warnings


def test_calendar_xlsx():
    frame = pd.DataFrame({"date": ["2026-10-02", "2026-10-12"], "event": ["Gandhi Jayanti", "College Foundation Day holiday"]})
    buffer = BytesIO()
    frame.to_excel(buffer, index=False)
    upload = Upload("calendar.xlsx", buffer.getvalue())
    events, _ = parse_academic_calendar(upload, use_ocr=False)
    assert len(events) == 2


def test_calendar_pdf_text():
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(50, 780, "2026-10-02 Gandhi Jayanti")
    pdf.drawString(50, 760, "2026-10-05 Department Development Day restricted holiday")
    pdf.save()
    upload = Upload("calendar.pdf", buffer.getvalue())
    events, _ = parse_academic_calendar(upload, use_ocr=False)
    assert len(events) == 2
    assert events[1]["type"] == "restricted_holiday"
