from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re

import pandas as pd

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
SLOT_RE = re.compile(r"(\d{1,2})\s*[:.]?\s*(\d{2})\s*[-–]\s*(\d{1,2})\s*[:.]?\s*(\d{2})")
ALIASES = {
    "day": {"day", "weekday", "date_day"},
    "slot": {"slot", "time", "timing", "period", "time_slot"},
    "course": {"course", "subject", "subject_name", "paper", "course_name"},
    "teacher": {"teacher", "faculty", "professor", "instructor", "faculty_name"},
    "room": {"room", "classroom", "class_room", "venue", "room_no", "room_number"},
    "group": {"group", "section", "student_group", "class", "batch", "programme", "program"},
}


def _norm_column(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _canonical_columns(frame):
    mapping = {}
    for col in frame.columns:
        key = _norm_column(col)
        for canonical, aliases in ALIASES.items():
            if key == canonical or key in aliases:
                mapping[col] = canonical
                break
    return frame.rename(columns=mapping)


def _normalise_slot(value):
    match = SLOT_RE.search(str(value).strip())
    if not match:
        return None
    h1, m1, h2, m2 = map(int, match.groups())
    return f"{h1:02d}:{m1:02d}-{h2:02d}:{m2:02d}"


def _normalise_day(value):
    text = str(value).strip().lower()
    for day in DAYS:
        if text == day.lower() or text.startswith(day[:3].lower()):
            return day
    return str(value).strip() if text and text != "nan" else None


def parse_timetable_dataframe(frame, default_group="OCR-GROUP"):
    frame = _canonical_columns(frame.copy())
    required = ["day", "slot", "course", "teacher", "room"]
    missing = [c for c in required if c not in frame.columns]
    if missing:
        raise ValueError("Timetable file is missing required columns: " + ", ".join(missing))
    records = []
    for _, row in frame.iterrows():
        course = str(row.get("course", "")).strip()
        if not course or course.lower() == "nan":
            continue
        day, slot = _normalise_day(row.get("day", "")), _normalise_slot(row.get("slot", ""))
        if not day or not slot:
            continue
        def value(name, fallback="UNKNOWN"):
            text = str(row.get(name, fallback)).strip()
            return fallback if not text or text.lower() == "nan" else text
        records.append({"day": day, "slot": slot, "course": course, "teacher": value("teacher"), "room": value("room"), "group": value("group", default_group)})
    if not records:
        raise ValueError("No valid timetable rows were found in the uploaded file.")
    return records


def _split_text_line(line):
    return [x.strip() for x in re.split(r"\t+|\s{2,}|\|", line) if x.strip()]


def _extract_pdf_row(raw, current_day, default_group):
    slot_match = SLOT_RE.search(raw)
    if not slot_match:
        return None
    slot = _normalise_slot(slot_match.group(0))
    cleaned = SLOT_RE.sub(" ", raw).strip(" |:-")
    cleaned = re.sub(rf"^\s*{re.escape(current_day)}\b", "", cleaned, flags=re.I).strip(" |:-")
    room_match = re.search(r"\b(?:room\s*)?(?:c[- ]?\d+|lab[- ]?\d+)\b", cleaned, re.I)
    group_match = re.search(r"\b(?:bsc|bca|mca|section|sec|group|batch)[-A-Za-z0-9]*\b", cleaned, re.I)
    room = room_match.group(0).strip() if room_match else "UNKNOWN"
    group = group_match.group(0).strip() if group_match else default_group
    teacher_match = re.search(r"\b(?:dr|prof|mr|ms|mrs)\.?\s+[A-Za-z][A-Za-z .'-]+?(?=\s+(?:room\s*)?(?:c[- ]?\d+|lab[- ]?\d+)|\s+(?:bsc|bca|mca|section|sec|group|batch)\b|$)", cleaned, re.I)
    if teacher_match:
        teacher = teacher_match.group(0).strip()
        prefix = cleaned[:teacher_match.start()].strip(" |:-")
    else:
        boundary = len(cleaned)
        for match in (room_match, group_match):
            if match:
                boundary = min(boundary, match.start())
        middle = cleaned[:boundary].strip(" |:-")
        words = middle.split()
        if len(words) >= 3:
            teacher = " ".join(words[-2:])
            prefix = " ".join(words[:-2])
        elif len(words) == 2:
            teacher, prefix = words[-1], words[0]
        else:
            teacher, prefix = "UNKNOWN", middle
    course = prefix.strip(" |:-") or "UNKNOWN"
    return {"day": current_day, "slot": slot, "course": course, "teacher": teacher, "room": room, "group": group}


def parse_timetable_text(text, default_group="OCR-GROUP"):
    records = []
    current_day = None
    for raw in text.splitlines():
        if not raw.strip():
            continue
        for day in DAYS:
            if re.search(rf"\b{day}\b", raw, re.I):
                current_day = day
                break
        if current_day:
            row = _extract_pdf_row(raw, current_day, default_group)
            if row:
                records.append(row)
    return records


def parse_timetable_file(uploaded_file, default_group="OCR-GROUP", use_ocr=False):
    """Parse timetable PDF, CSV, XLSX or XLS. PDFs use text extraction first and Tesseract only when needed."""
    name = getattr(uploaded_file, "name", "timetable")
    suffix = Path(name).suffix.lower()
    if suffix == ".csv":
        return parse_timetable_dataframe(pd.read_csv(BytesIO(uploaded_file.getvalue())), default_group), "csv"
    if suffix in {".xlsx", ".xls"}:
        return parse_timetable_dataframe(pd.read_excel(BytesIO(uploaded_file.getvalue())), default_group), suffix.lstrip(".")
    if suffix != ".pdf":
        raise ValueError("Supported timetable formats: PDF, CSV, XLSX, XLS.")

    from pypdf import PdfReader
    reader = PdfReader(BytesIO(uploaded_file.getvalue()))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    records = parse_timetable_text(text, default_group)
    if records:
        return records, "pdf_text"
    if use_ocr:
        from ocr_parser import parse_ocr_timetable
        records, _, warnings = parse_ocr_timetable(uploaded_file, default_group=default_group)
        if not records:
            raise ValueError("PDF text extraction found no timetable rows and Tesseract OCR found no timetable rows. " + " ".join(warnings))
        return records, "pdf_ocr"
    raise ValueError("PDF contains no recognizable timetable rows. Enable Tesseract OCR for scanned PDFs.")


def parse_calendar_file(uploaded_file):
    """Read calendar documents into line-oriented text for the calendar parser."""
    name = getattr(uploaded_file, "name", "calendar")
    suffix = Path(name).suffix.lower()
    if suffix == ".csv":
        frame = pd.read_csv(BytesIO(uploaded_file.getvalue()), header=None)
    elif suffix in {".xlsx", ".xls"}:
        frame = pd.read_excel(BytesIO(uploaded_file.getvalue()), header=None)
    elif suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(uploaded_file.getvalue()))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    else:
        raise ValueError("Supported calendar formats: PDF, CSV, XLSX, XLS.")
    return "\n".join(" | ".join(str(v).strip() for v in row.tolist() if str(v).strip() not in {"", "nan"}) for _, row in frame.iterrows())
