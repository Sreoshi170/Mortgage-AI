# Synthetic document regression fixtures

All fixtures in this directory are synthetic and contain no real borrower
information. Regenerate the text-bearing PDFs from the repository root with:

```powershell
python tools\generate_synthetic_document_fixtures.py
```

The fixture manifest records expected extraction and review behavior. The
runtime deliberately does not support image uploads; the blank scanned-PDF
fixture therefore verifies the safe no-text failure path rather than OCR.
