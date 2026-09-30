import json
import os
import re
from pathlib import Path

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


def _service_account_credentials():
    """Load Google credentials without putting a service-account key in source control."""
    from google.oauth2 import service_account

    raw = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON", "").strip()
    if raw:
        return service_account.Credentials.from_service_account_info(json.loads(raw))

    path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if path and Path(path).exists():
        return service_account.Credentials.from_service_account_file(path)

    # Falls back to Application Default Credentials (useful on Google Cloud).
    return None


def _cloud_ocr_pdf(uploaded_file, project_id, location="us", processor_id=""):
    """Run Google Cloud Document AI OCR on a PDF and return text/layout metadata."""
    try:
        from google.api_core.client_options import ClientOptions
        from google.cloud import documentai_v1 as documentai
    except ImportError as exc:
        raise RuntimeError(
            "Google Cloud Document AI dependencies are missing. Install google-cloud-documentai."
        ) from exc

    if not project_id:
        raise RuntimeError("Google Cloud project ID is required for cloud OCR.")
    if not processor_id:
        raise RuntimeError("Google Document AI processor ID is required for cloud OCR.")

    credentials = _service_account_credentials()
    endpoint = f"{location}-documentai.googleapis.com" if location != "us" else "us-documentai.googleapis.com"
    client_options = ClientOptions(api_endpoint=endpoint)
    client = documentai.DocumentProcessorServiceClient(
        credentials=credentials, client_options=client_options
    )

    name = client.processor_path(project_id, location, processor_id)
    raw_document = documentai.RawDocument(
        content=uploaded_file.getvalue(), mime_type="application/pdf"
    )
    request = documentai.ProcessRequest(name=name, raw_document=raw_document)
    result = client.process_document(request=request)
    document = result.document

    text = document.text or ""
    return [{
        "page": index + 1,
        "text": page_text,
        "confidence": 100.0,
    } for index, page_text in enumerate(_page_texts(document, text))]


def _page_texts(document, full_text):
    """Recover page text from Document AI text anchors; fall back to whole text."""
    pages = []
    for page in document.pages:
        chunks = []
        for block in page.blocks:
            anchor = getattr(block, "layout", None).text_anchor if getattr(block, "layout", None) else None
            if not anchor:
                continue
            for segment in anchor.text_segments:
                start = int(segment.start_index or 0)
                end = int(segment.end_index or 0)
                chunks.append(full_text[start:end])
        pages.append("\n".join(chunks).strip())
    return pages or [full_text]


def parse_ocr_timetable(uploaded_file, default_group="OCR-GROUP", project_id="", location="us", processor_id=""):
    """Parse a timetable using cloud OCR. No local Tesseract executable is required."""
    pages = _cloud_ocr_pdf(
        uploaded_file,
        project_id=project_id,
        location=location,
        processor_id=processor_id,
    )
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
        warnings.append("Cloud OCR found no timetable rows matching the configured day/time patterns.")
    return records, pages, warnings
