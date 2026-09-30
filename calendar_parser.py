from __future__ import annotations

from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
import csv
import re

DATE_PATTERNS = [
    re.compile(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b"),
    re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b"),
    re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})\b"),
    re.compile(r"\b([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})\b"),
]
MONTHS = {}
for number, name in enumerate([
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
], 1):
    MONTHS[name.lower()] = number
    MONTHS[name[:3].lower()] = number
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def _parse_date(text: str):
    for index, pattern in enumerate(DATE_PATTERNS):
        match = pattern.search(text)
        if not match:
            continue
        parts = match.groups()
        try:
            if index == 0:
                return date(int(parts[0]), int(parts[1]), int(parts[2]))
            if index == 1:
                return date(int(parts[2]), int(parts[1]), int(parts[0]))
            if index == 2:
                return date(int(parts[2]), MONTHS[parts[1].lower()], int(parts[0]))
            return date(int(parts[2]), MONTHS[parts[0].lower()], int(parts[1]))
        except (ValueError, KeyError):
            pass
    return None


def _parse_date_range(text: str):
    """Return every calendar date represented by a same-year date range."""
    # 24 Dec - 31 Dec 2026 / 24 December to 31 December 2026
    m = re.search(
        r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s*(?:-|–|—|to)\s*(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})\b",
        text,
        re.I,
    )
    if m:
        try:
            start = date(int(m.group(5)), MONTHS[m.group(2).lower()], int(m.group(1)))
            end = date(int(m.group(5)), MONTHS[m.group(4).lower()], int(m.group(3)))
            return _expand_range(start, end)
        except (ValueError, KeyError):
            return []

    # 24-31 Dec 2026 / 24–31 December 2026
    m = re.search(r"\b(\d{1,2})\s*(?:-|–|—|to)\s*(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})\b", text, re.I)
    if m:
        try:
            start = date(int(m.group(4)), MONTHS[m.group(3).lower()], int(m.group(1)))
            end = date(int(m.group(4)), MONTHS[m.group(3).lower()], int(m.group(2)))
            return _expand_range(start, end)
        except (ValueError, KeyError):
            return []
    return []


def _expand_range(start, end):
    if end < start or (end - start).days > 370:
        return []
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _classify(text: str):
    value = re.sub(r"\s+", " ", text.lower()).strip()
    # Resumption/opening events are not holidays just because they mention one.
    if re.search(r"\b(classes?|college|university)\s+(resume|reopen|re-start|restart)|resume\s+after|reopen\s+after", value):
        return "academic_event"
    if re.search(r"restricted\s+holiday|optional\s+holiday|\brestricted\b|[\(\[]\s*rh\s*[\)\]]|[-|:,]\s*rh\s*$", value):
        return "restricted_holiday"
    if re.search(r"public\s+holiday|national\s+holiday|holiday|vacation|college\s+closed|no\s+classes|closed\s+for\s+the\s+day", value):
        return "holiday"
    if re.search(r"\b(?:winter|summer|mid[- ]?semester|semester|term|diwali|christmas|spring|autumn)\s+break\b", value):
        return "holiday"
    return "academic_event"


def _event(date_value, text, source=""):
    return {
        "date": date_value.isoformat(),
        "name": re.sub(r"\s+", " ", text).strip(" -:|"),
        "type": _classify(text),
        "source": source,
    }


def _lines_from_file(uploaded_file):
    name = getattr(uploaded_file, "name", "calendar")
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(uploaded_file.getvalue()))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return text.splitlines(), "pdf_text"
    if suffix == ".csv":
        raw = uploaded_file.getvalue().decode("utf-8-sig", errors="replace")
        rows = csv.reader(raw.splitlines())
        return [" | ".join(cell.strip() for cell in row if cell.strip()) for row in rows], "csv"
    if suffix in {".xlsx", ".xls"}:
        import pandas as pd
        frame = pd.read_excel(BytesIO(uploaded_file.getvalue()), header=None)
        lines = [
            " | ".join(str(v).strip() for v in row.tolist() if str(v).strip() not in {"", "nan"})
            for _, row in frame.iterrows()
        ]
        return lines, "xlsx"
    raise ValueError("Supported calendar formats: PDF, CSV, XLSX.")


def _events_from_lines(lines, source):
    events = []
    for line in lines:
        if not line:
            continue
        range_dates = _parse_date_range(line)
        if range_dates:
            events.extend(_event(d, line, source) for d in range_dates)
            continue
        event_date = _parse_date(line)
        if event_date:
            events.append(_event(event_date, line, source))
    unique, seen = [], set()
    for item in events:
        key = (item["date"], item["type"], item["name"].lower())
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def parse_academic_calendar(uploaded_file, use_ocr=True):
    """Parse PDF/CSV/XLSX academic calendars into normalized dated events."""
    lines, source = _lines_from_file(uploaded_file)
    events = _events_from_lines(lines, source)
    warnings = []

    if not events and source == "pdf_text" and use_ocr:
        try:
            from ocr_parser import _ocr_pages
            pages = _ocr_pages(uploaded_file)
            events = _events_from_lines([line for page in pages for line in page["text"].splitlines()], "pdf_ocr")
            if events:
                warnings.append("PDF had no extractable text; calendar was recovered with local Tesseract OCR.")
        except Exception as exc:
            warnings.append(f"PDF text extraction found no dates and OCR fallback failed: {exc}")

    if not events:
        warnings.append("No dated calendar events were detected. Check the date format or export the calendar as text/CSV/XLSX.")
    return events, warnings


def _in_range(d, semester_start, semester_end):
    return semester_start <= d <= semester_end


def calendar_summary(events, semester_start=None, semester_end=None, restricted_as_holiday=False):
    parsed = []
    for event in events:
        try:
            parsed.append((datetime.fromisoformat(event["date"]).date(), event))
        except (KeyError, ValueError, TypeError):
            continue
    if semester_start is None or semester_end is None:
        dates = [d for d, _ in parsed]
        if dates:
            semester_start, semester_end = min(dates), max(dates)
        else:
            return {"semester_days": 0, "teaching_days": 0, "holiday_days": 0, "restricted_holiday_days": 0, "blocked_days": 0, "events": 0, "weekday_holiday_counts": {d: 0 for d in DAYS}}
    if semester_start > semester_end:
        raise ValueError("Semester start must be on or before semester end.")
    parsed = [(d, event) for d, event in parsed if _in_range(d, semester_start, semester_end)]
    holiday_dates = {d for d, e in parsed if e["type"] == "holiday"}
    restricted_dates = {d for d, e in parsed if e["type"] == "restricted_holiday"}
    blocked_dates = holiday_dates | (restricted_dates if restricted_as_holiday else set())
    weekday_holiday_counts = {d: 0 for d in DAYS}
    for d in blocked_dates:
        if d.weekday() < 5:
            weekday_holiday_counts[DAYS[d.weekday()]] += 1
    weekday = semester_start
    teaching_days = 0
    semester_days = 0
    while weekday <= semester_end:
        if weekday.weekday() < 5:
            semester_days += 1
            if weekday not in blocked_dates:
                teaching_days += 1
        weekday += timedelta(days=1)
    return {
        "semester_start": semester_start.isoformat(),
        "semester_end": semester_end.isoformat(),
        "semester_days": semester_days,
        "teaching_days": teaching_days,
        "holiday_days": len(holiday_dates),
        "restricted_holiday_days": len(restricted_dates),
        "blocked_days": len(blocked_dates),
        "events": len(parsed),
        "weekday_holiday_counts": weekday_holiday_counts,
    }
