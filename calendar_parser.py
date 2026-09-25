from __future__ import annotations

from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
import csv
import re


DATE_PATTERNS = [
    re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b"),
    re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})\b"),
    re.compile(r"\b([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})\b"),
]

MONTHS = {name.lower(): i for i, name in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"], 1
)}

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def _parse_date(text: str):
    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        parts = match.groups()
        try:
            if len(parts[1]) <= 2 and parts[1].isdigit():
                return date(int(parts[2]), int(parts[1]), int(parts[0]))
            if parts[1].lower() in MONTHS:
                return date(int(parts[2]), MONTHS[parts[1].lower()], int(parts[0]))
            if parts[0].lower() in MONTHS:
                return date(int(parts[2]), MONTHS[parts[0].lower()], int(parts[1]))
        except ValueError:
            pass
    return None


def _classify(text: str):
    value = text.lower()
    if re.search(r"restricted\s+holiday|optional\s+holiday|restricted|optional holiday|rh\b", value):
        return "restricted_holiday"
    if re.search(r"holiday|vacation|break|closed|no classes|college closed", value):
        return "holiday"
    return "academic_event"


def _event(date_value, text, source=""):
    return {
        "date": date_value.isoformat(),
        "name": re.sub(r"\s+", " ", text).strip(" -:|"),
        "type": _classify(text),
        "source": source,
    }


def parse_academic_calendar(uploaded_file):
    """Parse PDF/CSV/XLSX academic calendars into normalized dated events."""
    name = getattr(uploaded_file, "name", "calendar")
    suffix = Path(name).suffix.lower()

    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(uploaded_file.getvalue()))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        lines = text.splitlines()
    elif suffix == ".csv":
        raw = uploaded_file.getvalue().decode("utf-8-sig", errors="replace")
        rows = csv.reader(raw.splitlines())
        lines = [" | ".join(cell.strip() for cell in row if cell.strip()) for row in rows]
    elif suffix in {".xlsx", ".xls"}:
        import pandas as pd
        frame = pd.read_excel(BytesIO(uploaded_file.getvalue()), header=None)
        lines = [" | ".join(str(v).strip() for v in row.tolist() if str(v).strip() not in {"", "nan"})
                 for _, row in frame.iterrows()]
    else:
        raise ValueError("Supported calendar formats: PDF, CSV, XLSX.")

    events = []
    warnings = []
    for line in lines:
        if not line or not _parse_date(line):
            continue
        event_date = _parse_date(line)
        if event_date:
            events.append(_event(event_date, line, name))

    # Deduplicate by date/type/name while preserving source order.
    unique = []
    seen = set()
    for item in events:
        key = (item["date"], item["type"], item["name"].lower())
        if key not in seen:
            seen.add(key)
            unique.append(item)

    if not unique:
        warnings.append("No dated calendar events were detected. Check the date format or export the calendar as text/CSV/XLSX.")

    return unique, warnings


def calendar_summary(events, semester_start=None, semester_end=None, restricted_as_holiday=False):
    parsed = []
    for event in events:
        try:
            parsed.append((datetime.fromisoformat(event["date"]).date(), event))
        except (KeyError, ValueError):
            continue

    if semester_start is None or semester_end is None:
        dates = [d for d, _ in parsed]
        if dates:
            semester_start, semester_end = min(dates), max(dates)
        else:
            return {
                "semester_days": 0, "teaching_days": 0, "holiday_days": 0,
                "restricted_holiday_days": 0, "blocked_days": 0, "events": 0,
                "weekday_holiday_counts": {d: 0 for d in DAYS},
            }

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
