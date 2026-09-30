# AASE Tesseract OCR Setup

AASE uses **local Tesseract OCR** as its free fallback for scanned timetable PDFs.

## How document processing works

```text
Timetable PDF
     |
     +--> Native text extraction when the PDF contains selectable text
     |
     +--> Tesseract OCR when the PDF is scanned/image-based
                    |
                    v
             Timetable parser
                    |
                    v
             SQLite database
                    |
                    v
              CP-SAT optimizer
```

## 1. Install Tesseract on Windows

Install a Windows build of Tesseract OCR. The usual installation path is:

```text
C:\Program Files\Tesseract-OCR\tesseract.exe
```

Add the Tesseract installation directory to your Windows PATH, then open a new PowerShell window.

Verify it with:

```powershell
tesseract --version
```

## 2. Install Python dependencies

From the AASE repository:

```powershell
python -m pip install -r requirements.txt
```

The Python package `pytesseract` is the bridge between AASE and the Tesseract executable.

## 3. If Tesseract is not on PATH

Set the optional `TESSERACT_CMD` environment variable:

```powershell
$env:TESSERACT_CMD="C:\Program Files\Tesseract-OCR\tesseract.exe"
```

Or set it permanently through Windows Environment Variables.

## 4. Run AASE

```powershell
python -m streamlit run app.py
```

In **Time Table**:

1. Upload one or more timetable PDFs.
2. Enable **Use Tesseract OCR for scanned PDFs**.
3. Click **Import into AASE database**.
4. AASE renders each PDF page and sends it to local Tesseract.
5. The extracted timetable records are normalized and stored in SQLite.

## Privacy and cost

Tesseract runs locally. Timetable PDFs are not sent to a cloud OCR provider, so there is no Google Cloud account, API key, or per-page OCR charge.

This is the default OCR architecture for the AASE college-project prototype.
