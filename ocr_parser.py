import os
import re
from io import BytesIO

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
SLOT_PATTERNS = [
    (re.compile(r"09\s*[:.]?\s*00\s*[-–]\s*10\s*[:.]?\s*00"), "09:00-10:00"),
    (re.compile(r"10\s*[:.]?\s*00\s*[-–]\s*11\s*[:.]?\s*00"), "10:00-11:00"),
    (re.compile(r"11\s*[:.]?\s*15\s*[-–]\s*12\s*[:.]?\s*15"), "11:15-12:15"),
    (re.compile(r"12\s*[:.]?\s*15\s*[-–]\s*13\s*[:.]?\s*15"), "12:15-13:15"),
    (re.compile(r"14\s*[:.]?\s*00\s*[-–]\s*15\s*[:.]?\s*00"), "14:00-15:00"),
    (re.compile(r"15\s*[:.]?\s*00\s*[-–]\s*16\s*[:.]?\s*00"), "15:00-16:00"),
]


def _clean(value):
    return re.sub(r"\s+", " ", value or "").strip(" |:-")


def _extract_day(text):
    for day in DAYS:
        if re.search(rf"\b{day}\b", text, re.I) or re.search(rf"\b{day[:3]}\b", text, re.I):
            return day
    return None


def _extract_slot(text):
    for pattern, slot in SLOT_PATTERNS:
        if pattern.search(text):
            return slot
    return None


def _split_columns(line):
    return [_clean(p) for p in re.split(r"\t+|\s{2,}|\|", line) if _clean(p)]


def _ocr_pages(uploaded_file):
    """Run local Tesseract OCR against each rendered PDF page."""
    try:
        import fitz
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Install OCR dependencies with: python -m pip install -r requirements.txt") from exc

    # Allow advanced users to configure a non-default Tesseract installation.
    tesseract_cmd = os.getenv("TESSERACT_CMD", "").strip()
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    try:
        pytesseract.get_tesseract_version()
    except Exception as exc:
        raise RuntimeError(
            "Tesseract OCR is not installed or is not available on PATH. "
            "Install Tesseract OCR and restart your terminal, or set TESSERACT_CMD to the full tesseract.exe path."
        ) from exc

    document = fitz.open(stream=uploaded_file.getvalue(), filetype="pdf")
    pages = []
    try:
        for page_number, page in enumerate(document, start=1):
            # 2x rendering improves OCR accuracy for small timetable text.
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = pytesseract.image_to_string(image, config="--psm 6")
            pages.append({"page": page_number, "text": text, "confidence": None})
    finally:
        document.close()
    return pages


def parse_ocr_timetable(uploaded_file, default_group="OCR-GROUP"):
    """OCR a scanned timetable locally with Tesseract and normalize timetable rows."""
    pages = _ocr_pages(uploaded_file)
    records, warnings = [], []

    for page in pages:
        current_day = None
        for raw in page["text"].splitlines():
            line = _clean(raw)
            if not line:
                continue
            day = _extract_day(line)
            if day:
                current_day = day
            slot = _extract_slot(line)
            if not slot or not current_day:
                continue

            cleaned = line
            for pattern, _ in SLOT_PATTERNS:
                cleaned = pattern.sub(" ", cleaned)
            cols = _split_columns(cleaned)
            cols = [c for c in cols if c.lower() not in {current_day.lower(), current_day[:3].lower()}]

            course = cols[0] if cols else "UNKNOWN"
            teacher = next(
                (c for c in cols[1:] if re.search(r"\b(?:dr|prof|mr|ms|mrs)\.?\s*[a-z]", c, re.I)),
                "UNKNOWN",
            )
            room = next(
                (c for c in cols[1:] if re.search(r"\b(?:room|c[- ]?\d+|lab[- ]?\d+)\b", c, re.I)),
                "UNKNOWN",
            )
            group = next(
                (c for c in cols[1:] if re.search(r"(?:bsc|bca|mca|section|sec|group)", c, re.I)),
                default_group,
            )
            if teacher == "UNKNOWN" and len(cols) >= 2:
                teacher = cols[1]
            if room == "UNKNOWN" and len(cols) >= 3:
                room = cols[2]

            records.append({
                "day": current_day,
                "slot": slot,
                "course": course,
                "teacher": teacher,
                "room": room,
                "group": group,
                "ocr_confidence": page["confidence"],
                "source_page": page["page"],
            })

    if not records:
        warnings.append("Tesseract found no timetable rows matching the configured day/time patterns.")
    return records, pages, warnings
