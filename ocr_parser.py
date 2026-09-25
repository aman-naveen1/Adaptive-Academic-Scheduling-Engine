from io import BytesIO
import re

DAYS = ["Monday","Tuesday","Wednesday","Thursday","Friday"]
SLOT_PATTERNS = [
    (re.compile(r"09\s*[:.]?\s*00\s*[-–]\s*10\s*[:.]?\s*00"), "09:00-10:00"),
    (re.compile(r"10\s*[:.]?\s*00\s*[-–]\s*11\s*[:.]?\s*00"), "10:00-11:00"),
    (re.compile(r"11\s*[:.]?\s*15\s*[-–]\s*12\s*[:.]?\s*15"), "11:15-12:15"),
    (re.compile(r"12\s*[:.]?\s*15\s*[-–]\s*13\s*[:.]?\s*15"), "12:15-13:15"),
    (re.compile(r"14\s*[:.]?\s*00\s*[-–]\s*15\s*[:.]?\s*00"), "14:00-15:00"),
    (re.compile(r"15\s*[:.]?\s*00\s*[-–]\s*16\s*[:.]?\s*00"), "15:00-16:00"),
]

def _ocr_pdf(uploaded_file, dpi=220):
    try:
        import fitz
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("OCR dependencies are missing. Install PyMuPDF, Pillow and pytesseract.") from exc
    document = fitz.open(stream=uploaded_file.getvalue(), filetype="pdf")
    pages = []
    for page_no, page in enumerate(document, start=1):
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        data = pytesseract.image_to_data(image, config="--psm 6", output_type=pytesseract.Output.DICT)
        text = pytesseract.image_to_string(image, config="--psm 6")
        confidence = [float(c) for c in data["conf"] if str(c).strip() not in ("", "-1")]
        pages.append({"page": page_no, "text": text,
                      "confidence": round(sum(confidence)/len(confidence), 1) if confidence else 0.0})
    document.close()
    return pages

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

def parse_ocr_timetable(uploaded_file, default_group="OCR-GROUP"):
    pages = _ocr_pdf(uploaded_file)
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
            teacher = next((c for c in cols[1:] if re.search(r"\b(?:dr|prof|mr|ms|mrs)\.?\s*[a-z]", c, re.I)), "UNKNOWN")
            room = next((c for c in cols[1:] if re.search(r"\b(?:room|c[- ]?\d+|lab[- ]?\d+)\b", c, re.I)), "UNKNOWN")
            group = next((c for c in cols[1:] if re.search(r"(?:bsc|bca|mca|section|sec|group)", c, re.I)), default_group)
            if teacher == "UNKNOWN" and len(cols) >= 2:
                teacher = cols[1]
            if room == "UNKNOWN" and len(cols) >= 3:
                room = cols[2]
            records.append({"day": current_day, "slot": slot, "course": course,
                            "teacher": teacher, "room": room, "group": group,
                            "ocr_confidence": page["confidence"], "source_page": page["page"]})
    if not records:
        warnings.append("OCR found no timetable rows matching the configured day/time patterns.")
    low = sum(r["ocr_confidence"] < 55 for r in records)
    if low:
        warnings.append(f"{low} extracted row(s) have low OCR confidence; review them before optimization.")
    return records, pages, warnings
