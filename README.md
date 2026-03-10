# Cellhub Scanner

A Windows desktop application for extracting structured table data from telecom/phone bill PDFs using character-level text extraction and regex pattern matching.

---

## Features

- **PDF upload** — drag-and-drop or browse; supports up to 80-page PDFs
- **Char-by-char text extraction** — uses pdfplumber to reconstruct visual lines with proper spacing
- **Bill type detection** — keyword scoring identifies known carriers (Telkom Mobile, Vodacom, MTN, Cell C)
- **Regex table extraction** — configurable per-column patterns with type casting and transforms
- **Gemini Portal** — for unknown bill types, generates a structured prompt for Gemini web chat and parses the JSON response to create new regex patterns
- **Accuracy scoring** — validates Gemini-generated patterns against sample rows; provides a colour-coded score
- **Export** — CSV or Excel (.xlsx) with auto-sized columns, frozen header, and metadata sheet
- **Google Drive upload** — OAuth2 authenticated upload to a selected Drive folder

---

## Installation

```bash
# 1. Clone / download the project
cd Cellhub_scanner

# 2. Create a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate      # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run
python main.py
```

---

## Usage

### Standard workflow (known bill type)

1. Launch `python main.py`
2. Upload page → Browse or drag-and-drop a telecom bill PDF
3. Click **Process** — the app detects the bill type and extracts the table
4. Preview page — review the extracted rows
5. Export page — choose CSV or Excel, pick a save location, click Export
6. Optionally upload to Google Drive

### New bill type workflow

When the app cannot identify the bill type:

1. The **Gemini Portal** page opens automatically
2. Click **Open Gemini →** to open Google Gemini in your browser
3. Upload your PDF in Gemini chat
4. Copy the generated prompt from the app and send it to Gemini
5. Copy Gemini's JSON response and paste it into the text area in the app
6. Click **Parse Response & Continue →**
7. Review and edit the column patterns in the **Pattern Editor**
8. Click **Save Patterns & Process PDF →**
9. The accuracy score is shown in the Preview page

---

## Google Drive Setup (optional)

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create or select a project
3. Enable **Google Drive API** under APIs & Services → Library
4. Go to **APIs & Services → Credentials**
5. Click **Create Credentials → OAuth 2.0 Client IDs**
6. Choose **Desktop application**
7. Download the JSON file
8. Save it to: `config/credentials/client_secret.json`

On first use, a browser window will open for OAuth2 consent. The token is cached in `config/token.json` for subsequent sessions.

---

## Supported Bill Types (built-in)

| ID | Carrier |
|----|---------|
| `telkom_mobile` | Telkom Mobile |
| `vodacom` | Vodacom |
| `mtn` | MTN |
| `cell_c` | Cell C |

New bill types are added dynamically via the Gemini Portal and stored in `patterns/patterns.json`.

---

## Building a Windows Executable

```bash
pip install pyinstaller
pyinstaller cellhub_scanner.spec
# Output: dist/CellhubScanner.exe
```

---

## Project Structure

```
cellhub_scanner/
├── main.py                      # Entry point
├── requirements.txt
├── cellhub_scanner.spec         # PyInstaller build spec
├── ui/                          # customtkinter UI pages
│   ├── app_window.py            # Root window + sidebar navigation
│   ├── upload_page.py           # PDF upload + processing
│   ├── gemini_portal_page.py    # Manual Gemini workflow
│   ├── pattern_editor_page.py   # Review/edit Gemini-returned patterns
│   ├── preview_page.py          # Table preview + accuracy badge
│   ├── export_page.py           # CSV/Excel export + Drive prompt
│   ├── drive_upload_dialog.py   # Google Drive folder picker + upload
│   └── pattern_list_page.py     # Manage saved bill type patterns
├── core/
│   ├── pdf_extractor.py         # Char-level PDF text extraction
│   ├── bill_detector.py         # Bill type keyword detection
│   ├── table_builder.py         # Regex-based table construction
│   ├── accuracy_scorer.py       # Pattern accuracy evaluation
│   └── exporter.py              # CSV / Excel export
├── integrations/
│   └── drive_client.py          # Google Drive OAuth2 + upload
├── patterns/
│   ├── pattern_manager.py       # Load/save/validate patterns
│   └── patterns.json            # Per-carrier regex schemas
└── config/
    └── credentials/
        └── client_secret.json   # Google OAuth2 credentials (not committed)
```
