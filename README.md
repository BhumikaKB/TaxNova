# TaxNova — Smart Income Tax Assistant

A tax decision-support tool for Indian salaried employees: upload your Form 16, and TaxNova extracts your salary/TDS/deductions, calculates tax under both the Old and New regimes, and explains — in plain language — which one is better and why.

**What this is not:** an e-filing platform. TaxNova doesn't submit anything to the Income Tax Department. It's the tool you use *before* filing anywhere, to actually understand your own numbers.

---

## Setup

### 1. Python dependencies

```bash
pip install -r requirements.txt
```

### 2. OCR system dependencies (required for scanned Form 16s)

`pytesseract` and `pdf2image` in `requirements.txt` are Python wrappers — they need two separate system programs actually installed, which `pip` cannot install for you:

- **Tesseract OCR**
  - Windows: [UB-Mannheim build](https://github.com/UB-Mannheim/tesseract/wiki) — installer, then add the install folder to your PATH
  - macOS: `brew install tesseract`
  - Linux: `sudo apt-get install tesseract-ocr`
- **Poppler**
  - Windows: [poppler-windows releases](https://github.com/oschwartz10612/poppler-windows/releases) — unzip, add the `bin` folder to your PATH
  - macOS: `brew install poppler`
  - Linux: `sudo apt-get install poppler-utils`

**Restart your terminal/IDE after installing** — PATH changes need a fresh shell to take effect.

Without these, text-based Form 16 PDFs still work fine. Only *scanned* Form 16s need OCR, and the app will tell you clearly if it needs these tools and can't find them, rather than pretending your PDF is broken.

### 3. Environment variables

Copy `.env.example` to `.env` (or set these as real environment variables):

```
TAXNOVA_SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
FLASK_DEBUG=False
TAXNOVA_HTTPS=False
```

### 4. Run it

```bash
python app.py
```

Visit `http://127.0.0.1:5000`.

**For anything beyond your own local testing**, don't use `python app.py` — it's Flask's development server, not built for real traffic. Use Waitress instead (already in `requirements.txt`):

```bash
waitress-serve --host=0.0.0.0 --port=8000 app:app
```

---

## Running tests

```bash
python -m unittest discover -s tests -v
```

Tests run automatically on every push via GitHub Actions (`.github/workflows/tests.yml`).

---

## Updating to a new version

If you're replacing your project folder with a newer copy (from a new zip, a git pull, etc.), **copy your `database/database.db` out first and back in after** — a fresh copy of the project ships with an empty database, and losing this file means losing every registered account.

---

## Project structure

```
app.py                  Flask routes
config.py                App-wide settings (secret key, session, upload limits)
modules/
  auth/                  Registration, login, password reset
  history/                Saved calculation history
  pdf_processor/         Form 16 validation, text/OCR extraction, field parsing
  security/               Upload file validation (magic bytes, size, safe filenames)
  tax_engine/             Old/New regime tax calculation and comparison
templates/               Jinja2 HTML templates
static/                   CSS, JS, uploaded-file storage
tests/                    Unit + integration test suite
```

## Known limitations (documented, not hidden)

- No senior/super-senior citizen tax slabs
- No HRA exemption modeling — a known, deliberate scope limit (see comments in `modules/pdf_processor/field_extractor.py`)
- No capital gains, house property income, or multi-employer Form 16 support
- Section 80D/80CCD(1B)/80G are extracted from the PDF but not yet wired into the tax calculation itself — only Section 80C currently affects the computed result
