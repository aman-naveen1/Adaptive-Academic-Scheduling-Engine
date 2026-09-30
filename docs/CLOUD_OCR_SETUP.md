# AASE Cloud OCR Setup

AASE now uses **Google Cloud Document AI** for scanned timetable PDFs. Local Tesseract is no longer required.

## 1. Create a Google Cloud project

Create or select a Google Cloud project and enable the **Document AI API**.

## 2. Create an OCR processor

In Google Cloud Document AI, create an OCR processor and note:

- Project ID
- Processor location (`us` or `eu`)
- Processor ID

## 3. Credentials

AASE supports Google Application Default Credentials and service-account credentials.

### Local development

Set:

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS="C:\path\to\service-account.json"
$env:GOOGLE_CLOUD_PROJECT="your-project-id"
$env:DOCUMENT_AI_PROCESSOR_ID="your-processor-id"
```

Do **not** commit the service-account JSON to GitHub.

For hosted deployments, `GOOGLE_APPLICATION_CREDENTIALS_JSON` can contain the JSON credential object as a secret. Prefer the platform's secret manager rather than storing credentials in the repository.

## 4. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

There is deliberately no `pytesseract` dependency and no Tesseract executable to install.

## 5. Run AASE

```powershell
python -m streamlit run app.py
```

In the sidebar:

1. Turn off **Use demo timetable**.
2. Enable **Use cloud OCR for scanned PDFs**.
3. Enter the Google Cloud Project ID and Document AI processor ID.
4. Upload one or more timetable PDFs.
5. Run the desired scheduling operation.

## OCR flow

```text
Timetable PDF
     |
     v
Streamlit upload
     |
     +--> Native PDF extraction (when OCR is off)
     |
     +--> Google Cloud Document AI (when OCR is on)
                    |
                    v
              Extracted text/layout
                    |
                    v
             AASE timetable parser
                    |
                    v
             Structured schedule
                    |
                    v
               CP-SAT optimizer
```

## Security notes

- Never commit service-account JSON files.
- Never put API credentials directly into `app.py`.
- Use environment variables or deployment secrets.
- For a college deployment, create a dedicated least-privilege service account rather than using a personal Google account.
- Timetable PDFs may contain student/faculty information. Confirm the college's data/privacy policy before sending real documents to a cloud processor.
