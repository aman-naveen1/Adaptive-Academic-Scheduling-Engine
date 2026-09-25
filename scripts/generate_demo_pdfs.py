from pathlib import Path
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

OUT = Path(__file__).resolve().parents[1] / "demo" / "pdfs"
OUT.mkdir(parents=True, exist_ok=True)
styles = getSampleStyleSheet()

def make_pdf(path, title, headers, rows):
    doc = SimpleDocTemplate(str(path), pagesize=landscape(A4), rightMargin=24, leftMargin=24, topMargin=24, bottomMargin=24)
    story = [Paragraph(title, styles["Title"]), Spacer(1, 12)]
    table = Table([headers] + rows, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#17324D")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#EEF3F7")]),
    ]))
    story.append(table)
    doc.build(story)

classes = [
    ["Monday","09:00-10:00","DSA","Dr. Sharma","C-201","BSc-CS-3A"],
    ["Monday","10:00-11:00","DBMS","Prof. Iyer","C-201","BSc-CS-3A"],
    ["Monday","12:15-13:15","OS","Dr. Mehta","C-201","BSc-CS-3A"],
    ["Monday","14:00-15:00","Probability","Dr. Khan","C-201","BSc-CS-3A"],
    ["Tuesday","09:00-10:00","Software Engineering","Prof. Rao","C-201","BSc-CS-3A"],
    ["Tuesday","10:00-11:00","DSA","Dr. Sharma","C-201","BSc-CS-3A"],
    ["Tuesday","11:15-12:15","DBMS","Prof. Iyer","C-201","BSc-CS-3A"],
    ["Wednesday","09:00-10:00","OS","Dr. Mehta","C-201","BSc-CS-3A"],
    ["Wednesday","10:00-11:00","Probability","Dr. Khan","C-201","BSc-CS-3A"],
    ["Thursday","09:00-10:00","DSA","Dr. Sharma","C-201","BSc-CS-3A"],
    ["Thursday","10:00-11:00","DBMS","Prof. Iyer","C-201","BSc-CS-3A"],
    ["Friday","09:00-10:00","Software Engineering","Prof. Rao","C-201","BSc-CS-3A"],
]

make_pdf(OUT / "room_timetable_C201.pdf", "Room C-201 — Weekly Timetable",
         ["Day","Time","Course","Teacher","Room","Group"], classes)

make_pdf(OUT / "student_timetable_BSc-CS-3A.pdf", "Student Group BSc-CS-3A — Weekly Timetable",
         ["Day","Time","Course","Teacher","Room"], [r[:5] for r in classes])

availability = [
    ["Dr. Sharma","DSA","Monday","10:00-11:00; 11:15-12:15; 12:15-13:15; 14:00-15:00; 15:00-16:00"],
    ["Dr. Sharma","DSA","Tuesday","09:00-10:00; 10:00-11:00"],
    ["Dr. Sharma","DSA","Wednesday","11:15-12:15; 12:15-13:15"],
    ["Dr. Sharma","DSA","Thursday","09:00-10:00; 10:00-11:00"],
    ["Dr. Sharma","DSA","Friday","09:00-10:00"],
    ["Prof. Iyer","DBMS","Monday","10:00-11:00"],
    ["Prof. Iyer","DBMS","Tuesday","11:15-12:15"],
    ["Prof. Iyer","DBMS","Wednesday","09:00-10:00; 10:00-11:00"],
    ["Prof. Iyer","DBMS","Thursday","10:00-11:00"],
    ["Prof. Iyer","DBMS","Friday","10:00-11:00; 11:15-12:15"],
]
make_pdf(OUT / "teacher_availability.pdf", "Teacher Availability — Demo Dataset",
         ["Teacher","Qualified Course","Day","Available Slots"], availability)

rooms = [
    ["C-201","60","Lecture","Available"],
    ["C-202","60","Lecture","Available"],
    ["Lab-1","40","Computer Lab","Available"],
]
make_pdf(OUT / "rooms.pdf", "Room Inventory — Demo Dataset",
         ["Room","Capacity","Type","Status"], rooms)

print(f"Generated demo PDFs in {OUT}")
